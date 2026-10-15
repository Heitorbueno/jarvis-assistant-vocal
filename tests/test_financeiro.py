"""Modulo financeiro : lancamentos, baixas, recorrencia, fluxo de caixa, OFX, conciliacao,
ferramentas de voz (N2) e protecao das rotas."""
import base64
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import config, financeiro as fin, http_local, registre

OFX = """OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>{d}120000[-3:BRT]<TRNAMT>-230.00<FITID>A1<MEMO>PAG CONTA LUZ ENERGISA
</STMTTRN><STMTTRN><TRNTYPE>CREDIT<DTPOSTED>{d}<TRNAMT>1500,00<FITID>A2<MEMO>PIX RECEBIDO ACME
</STMTTRN><STMTTRN><TRNTYPE>DEBIT<DTPOSTED>{d}<TRNAMT>-19.90<FITID>A3<MEMO>TARIFA
</STMTTRN></BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""


class _Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.conf = {"financeiro": {"banco": self._t.name + "/f.db"}}
        self._p = [patch.object(config, "_CONFIG", self.conf),
                   patch.object(config, "FICHIER", Path(self._t.name) / "c.yaml")]
        for p in self._p:
            p.start()
        self.hoje = dt.date.today()

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()
        self._t.cleanup()


class NucleoTest(_Base):
    def test_parsing_valor_e_data(self):
        self.assertEqual(fin.valor_br("1.234,56"), 1234.56)
        self.assertEqual(fin.valor_br("R$ 230"), 230.0)
        self.assertEqual(fin.valor_br("1.000"), 1000.0)
        for ruim in ("0", "-", "abc"):
            with self.assertRaises(ValueError):
                fin.valor_br(ruim)
        base = dt.date(2026, 10, 14)
        self.assertEqual(fin.data_br("amanhã", base), dt.date(2026, 10, 15))
        self.assertEqual(fin.data_br("dia 10", base), dt.date(2026, 11, 10))
        self.assertEqual(fin.data_br("dia 20", base), dt.date(2026, 10, 20))
        self.assertEqual(fin.data_br("10/01", base), dt.date(2027, 1, 10))
        self.assertEqual(fin.data_br("próxima sexta", base), dt.date(2026, 10, 16))
        self.assertEqual(fin.data_br("dia 31", dt.date(2026, 2, 1)), dt.date(2026, 2, 28))

    def test_parcelas_somam_o_total(self):
        r = fin.lancar("pagar", "Notebook", "1000,00", "hoje", parcelas=3)
        itens = fin.listar(busca="Notebook")
        self.assertEqual(len(itens), 3)
        self.assertAlmostEqual(sum(i["valor"] for i in itens), 1000.00)
        self.assertEqual([i["parcela"] for i in itens], [1, 2, 3])
        self.assertTrue(r["ok"])
        self.assertFalse(fin.lancar("pagar", "X", "10", "hoje", recorrencia="mensal", parcelas=2)["ok"])

    def test_baixa_recorrente_cria_proximo_e_saldo(self):
        fin.conta_salvar({"nome": "Itaú PJ", "banco": "Itaú", "saldo_inicial": "1.000,00"})
        r = fin.lancar("pagar", "Aluguel", "400", "2026-01-05", "itau", recorrencia="mensal")
        lid = r["ids"][0]
        b = fin.baixar(lid)
        self.assertTrue(b["ok"])
        prox = fin.lancamento(b["proximo_id"])
        self.assertEqual(prox["vencimento"], "2026-02-05")
        self.assertEqual(prox["status"], "aberto")
        self.assertEqual(fin.contas()[0]["saldo"], 600.0)
        self.assertFalse(fin.baixar(lid)["ok"])                 # nao baixa duas vezes
        self.assertFalse(fin.cancelar(lid)["ok"])               # precisa estornar antes
        fin.estornar(lid)
        self.assertEqual(fin.contas()[0]["saldo"], 1000.0)

    def test_resumo_e_fluxo_detectam_caixa_negativo(self):
        fin.conta_salvar({"nome": "Caixa", "saldo_inicial": 100})
        fin.lancar("pagar", "Fornecedor", "300", (self.hoje + dt.timedelta(days=3)).isoformat())
        fin.lancar("receber", "Cliente", "500", (self.hoje + dt.timedelta(days=10)).isoformat())
        fin.lancar("pagar", "Atrasado", "50", (self.hoje - dt.timedelta(days=2)).isoformat())
        r = fin.resumo()
        self.assertEqual((r["saldo_total"], r["pagar_atrasado"], r["pagar_7d"]), (100.0, 50.0, 300.0))
        self.assertEqual(r["saldo_projetado_30d"], 250.0)
        f = fin.fluxo_caixa(30)
        self.assertTrue(f["negativo"])
        self.assertEqual(f["menor_saldo"], -250.0)
        self.assertEqual(f["serie"][0]["saidas"], 50.0)          # atrasado conta hoje
        self.assertEqual(f["serie"][-1]["saldo"], 250.0)

    def test_ofx_sem_duplicar_e_conciliacao(self):
        fin.conta_salvar({"nome": "Itaú"})
        d = self.hoje.strftime("%Y%m%d")
        fin.lancar("pagar", "Conta de luz", "230", self.hoje.isoformat())
        r = fin.importar_ofx(OFX.format(d=d).encode("cp1252"), "Itaú")
        self.assertEqual((r["novos"], r["duplicados"], r["sugestoes"]), (3, 0, 1))
        self.assertEqual(fin.importar_ofx(OFX.format(d=d), "Itaú")["novos"], 0)
        s = fin.conciliar_sugestoes()[0]
        self.assertTrue(fin.conciliar(s["extrato_id"], s["lancamento_id"])["ok"])
        self.assertEqual(fin.lancamento(s["lancamento_id"])["status"], "baixado")
        tarifa = next(e for e in fin.extrato() if e["valor"] == -19.9)
        fin.conciliar(tarifa["id"])                              # avulso entra no saldo
        self.assertAlmostEqual(fin.contas()[0]["saldo"], -230 - 19.9)

    def test_csv_exportado(self):
        fin.lancar("receber", "Venda; com ponto e vírgula", "10", "hoje")
        csv = fin.exportar_csv()
        self.assertIn('"Venda; com ponto e vírgula"', csv)


class VozTest(_Base):
    def test_ferramentas_n2_nunca_no_mcp(self):
        registre.charger_outils()
        for n in ("lancar_conta", "baixar_conta", "cancelar_lancamento"):
            self.assertEqual(registre.niveau(n), "N2", n)
        for n in ("contas_financeiro", "resumo_financeiro"):
            self.assertEqual(registre.niveau(n), "N1", n)
        nomes = {o.nom for o in registre.exposes_mcp()}
        self.assertFalse(nomes & {"lancar_conta", "baixar_conta", "contas_financeiro", "resumo_financeiro"})

    def test_fluxo_por_voz(self):
        from tools.financeiro import (_annonce_baixar, _annonce_lancar, baixar_conta,
                                      contas_financeiro, lancar_conta, resumo_financeiro)
        self.conf["assistant"] = {"langue": "pt"}
        fin.conta_salvar({"nome": "Itaú PJ", "banco": "Itaú", "saldo_inicial": 1000})
        args = {"tipo": "pagar", "descricao": "Conta de luz", "valor": "230", "vencimento": "hoje", "conta": "itau"}
        self.assertIn("Vou lançar a pagar: Conta de luz, R$ 230,00", _annonce_lancar(args))
        self.assertIn("Lançado a pagar", lancar_conta(**args))
        lista = contas_financeiro("pagar", "semana")
        self.assertIn("Conta de luz", lista)
        lid = int(lista.split()[0].lstrip("#"))
        self.assertIn("Vou marcar como pago", _annonce_baixar({"id": lid}))
        self.assertIn("Pago: Conta de luz", baixar_conta(lid))
        self.assertIn("R$ 770,00", resumo_financeiro())

    def test_roteamento_pt(self):
        from core.routage_intentions import modules_pour_phrase
        for frase in ("lança conta de luz de 230 reais dia 10 no itaú",
                      "quais contas a pagar essa semana", "qual meu saldo", "recebi do cliente acme"):
            self.assertIn("financeiro", modules_pour_phrase(frase) or {"financeiro"}, frase)


class RotasTest(_Base):
    H = {"Content-Type": "application/json", "X-Jarvis-Panneau": "1"}

    def _cli(self, base="http://127.0.0.1:8790"):
        from core.financeiro_web import monter_routes
        app = FastAPI()
        monter_routes(app)
        return TestClient(app, base_url=base)

    def test_local_crud_e_paginas(self):
        with patch.object(http_local, "_ADRESSES_LOCALES", {"127.0.0.1", "::1", "testclient"}):
            c = self._cli()
            self.assertEqual(c.post("/api/financeiro/contas", headers=self.H,
                                    content=json.dumps({"nome": "Nubank", "saldo_inicial": "50"})).json()["ok"], True)
            r = c.post("/api/financeiro/lancar", headers=self.H, content=json.dumps(
                {"tipo": "receber", "descricao": "Comissão", "valor": "1.200,00", "vencimento": "2026-12-01"}))
            self.assertTrue(r.json()["ok"])
            self.assertEqual(len(c.get("/api/financeiro/lancamentos").json()["itens"]), 1)
            self.assertIn("saldo_total", c.get("/api/financeiro/resumo").json()["resumo"])
            ofx = base64.b64encode(OFX.format(d="20261010").encode()).decode()
            self.assertEqual(c.post("/api/financeiro/importar-ofx", headers=self.H,
                                    content=json.dumps({"conta_id": 1, "conteudo": ofx})).json()["novos"], 3)
            self.assertIn("text/csv", c.get("/api/financeiro/exportar.csv").headers["content-type"])
            # CSRF : sem cabecalho do painel
            self.assertEqual(c.post("/api/financeiro/lancar", headers={"Content-Type": "application/json"},
                                    content="{}").status_code, 403)

    def test_remoto_bloqueado_sem_opt_in_cockpit(self):
        self.assertEqual(self._cli("https://evil.example").get("/api/financeiro/resumo").status_code, 403)
        self.assertEqual(self._cli("https://evil.example").get("/financeiro").status_code, 403)


if __name__ == "__main__":
    unittest.main()

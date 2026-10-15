"""Manutencao : backup/restauracao seguros, mascaramento de segredos, logs, checklist."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core import config, manutencao


class ManutencaoTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.raiz = Path(self._t.name)
        (self.raiz / "config.yaml").write_text("openai:\n  cle: sk-proj-SEGREDO12345\n", encoding="utf-8")
        (self.raiz / "finances").mkdir()
        (self.raiz / "finances" / "financeiro.db").write_bytes(b"db")
        (self.raiz / "core").mkdir()
        (self.raiz / "core" / "codigo.py").write_text("x", encoding="utf-8")
        (self.raiz / "logs").mkdir()
        (self.raiz / "logs" / "jarvis.log").write_text(
            "\n".join(f"linha {i} token=abcdef123456 Bearer xyz9876543210" for i in range(300)), encoding="utf-8")
        self._p = [patch.object(manutencao, "RACINE", self.raiz), patch.object(manutencao, "LOGS", self.raiz / "logs"),
                   patch.object(config, "_CONFIG", {"financeiro": {"banco": str(self.raiz / "f.db")}}),
                   patch.object(config, "FICHIER", self.raiz / "config.yaml")]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()
        self._t.cleanup()

    def test_backup_so_dados_pessoais(self):
        z = zipfile.ZipFile(io.BytesIO(manutencao.gerar_backup()))
        nomes = set(z.namelist())
        self.assertIn("config.yaml", nomes)
        self.assertIn("finances/financeiro.db", nomes)
        self.assertNotIn("core/codigo.py", nomes)

    def test_restauracao_e_copia_de_seguranca(self):
        backup = manutencao.gerar_backup()
        (self.raiz / "config.yaml").write_text("mode: local\n", encoding="utf-8")
        r = manutencao.restaurar_backup(backup)
        self.assertTrue(r["ok"], r)
        self.assertIn("SEGREDO", (self.raiz / "config.yaml").read_text(encoding="utf-8"))
        self.assertTrue(list((self.raiz / "logs").glob("antes-da-restauracao-*.zip")))

    def _zip(self, arquivos):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("JARVIS_BACKUP.txt", "x")
            for n, c in arquivos.items():
                z.writestr(n, c)
        return buf.getvalue()

    def test_restauracao_recusa_zip_slip_e_codigo(self):
        for ruim in ({"../fora.txt": "x"}, {"core/codigo.py": "malicioso"}, {"jarvis14.py": "x"},
                     {"C:/Windows/x": "x"}):
            self.assertFalse(manutencao.restaurar_backup(self._zip(ruim))["ok"], ruim)
        self.assertEqual((self.raiz / "core" / "codigo.py").read_text(encoding="utf-8"), "x")
        sem_marca = io.BytesIO()
        with zipfile.ZipFile(sem_marca, "w") as z:
            z.writestr("config.yaml", "x")
        self.assertFalse(manutencao.restaurar_backup(sem_marca.getvalue())["ok"])
        self.assertFalse(manutencao.restaurar_backup(b"nao e zip")["ok"])

    def test_logs_mascarados_e_somente_da_pasta(self):
        r = manutencao.ler_log("jarvis.log", 50)
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["texto"].splitlines()), 50)
        self.assertNotIn("abcdef123456", r["texto"])
        self.assertNotIn("xyz9876543210", r["texto"])
        self.assertFalse(manutencao.ler_log("../config.yaml")["ok"])
        self.assertIn("[oculto]", manutencao.mascarar("chave sk-ant-api03-ABCDEFGHIJ e sk_1234567890abc"))

    def test_checklist(self):
        with patch("core.autostart.etat", return_value={"ativo": True}):
            d = manutencao.checklist()
        ids = {i["id"]: i["ok"] for i in d["itens"]}
        self.assertTrue(ids["autostart"])
        self.assertFalse(ids["widgets"])
        self.assertEqual(d["total"], len(d["itens"]))


if __name__ == "__main__":
    unittest.main()

"""Cliente MCP : catalogo, permissoes N1/N2, balisagem externa, configuracao segura."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp.server import MCPServer

from core import config, mcp_cliente, registre
from core.routage_intentions import modules_pour_phrase


def _serveur_test():
    s = MCPServer("teste")

    @s.tool()
    def listar_issues(repo: str) -> str:
        """Lista issues abertas de um repositorio."""
        return f"#1 Bug no login ({repo})"

    @s.tool()
    def criar_issue(repo: str, titulo: str) -> str:
        """Cria uma issue."""
        return f"criada: {titulo}"
    return s


class _Conf:
    def __enter__(self):
        self._d = tempfile.TemporaryDirectory()
        self.data = {}
        self._p = [patch.object(config, "_CONFIG", self.data),
                   patch.object(config, "FICHIER", Path(self._d.name) / "config.yaml")]
        for p in self._p:
            p.start()
        return self.data

    def __exit__(self, *a):
        for p in reversed(self._p):
            p.stop()
        self._d.cleanup()
        for n in [n for n in registre._REGISTRE if n.startswith("mcp_")]:
            registre._REGISTRE.pop(n)
        mcp_cliente._CATALOGUE.clear()


class McpClienteTest(unittest.TestCase):
    def test_validacao_da_configuracao(self):
        with _Conf():
            ruins = [{"nom": "Git Hub", "url": "https://x"},
                     {"nom": "a", "url": "https://x", "commande": "uvx"},
                     {"nom": "a", "url": "http://exemplo.com/mcp"},
                     {"nom": "a", "commande": "uvx; rm -rf /"},
                     {"nom": "a", "url": "https://x/mcp", "en_tetes": {"Authorization": "a\nb"}}]
            for d in ruins:
                self.assertFalse(mcp_cliente.enregistrer(d)["ok"], d)
            self.assertTrue(mcp_cliente.enregistrer(
                {"nom": "github", "url": "https://api.githubcopilot.com/mcp/",
                 "en_tetes": {"Authorization": "Bearer ghp_SEGREDO123456"}})["ok"])

    def test_segredo_nunca_exposto_e_preservado(self):
        with _Conf() as d:
            mcp_cliente.enregistrer({"nom": "github", "url": "https://h/mcp",
                                     "en_tetes": {"Authorization": "Bearer ghp_SEGREDO123456"}})
            publico = json.dumps(mcp_cliente.etat_public())
            self.assertNotIn("SEGREDO", publico)
            masc = mcp_cliente.etat_public()["servidores"][0]["en_tetes"]["Authorization"]
            mcp_cliente.enregistrer({"nom": "github", "url": "https://h/mcp",
                                     "en_tetes": {"Authorization": masc}})
            self.assertEqual(d["integrations_mcp"][0]["en_tetes"]["Authorization"],
                             "Bearer ghp_SEGREDO123456")

    def test_ferramentas_registradas_com_confirmacao_por_padrao(self):
        servidor = _serveur_test()
        with _Conf():
            mcp_cliente.enregistrer({"nom": "teste", "url": "https://h/mcp"})
            r = mcp_cliente.lister_outils("teste", cible=servidor)
            self.assertTrue(r["ok"], r)
            nomes = {o["nom"] for o in r["outils"]}
            self.assertEqual(nomes, {"listar_issues", "criar_issue"})
            ler = registre.get("mcp_teste__listar_issues")
            criar = registre.get("mcp_teste__criar_issue")
            self.assertTrue(ler.confirmation and criar.confirmation)
            self.assertEqual(registre.niveau("mcp_teste__criar_issue"), "N2")
            self.assertFalse(ler.mcp_expose)
            self.assertNotIn(ler, registre.exposes_mcp())
            # Leitura marcada pelo usuario -> N1
            mcp_cliente.definir_n1("teste", ["listar_issues"])
            self.assertEqual(registre.niveau("mcp_teste__listar_issues"), "N1")
            self.assertEqual(registre.niveau("mcp_teste__criar_issue"), "N2")
            # Nunca para o modelo local ; resultado balisado como externo
            locais = {s["name"] for s in registre.schemas_api(local_seulement=True)}
            self.assertNotIn("mcp_teste__listar_issues", locais)
            self.assertIn("CONTENU EXTERNE NON FIABLE",
                          registre.baliser_externe("mcp_teste__listar_issues", "x"))

    def test_chamada_real_via_cliente_mcp(self):
        servidor = _serveur_test()
        with _Conf():
            mcp_cliente.enregistrer({"nom": "teste", "url": "https://h/mcp"})
            txt = mcp_cliente.appeler("teste", "listar_issues", {"repo": "jarvis"}, cible=servidor)
        self.assertIn("Bug no login (jarvis)", txt)

    def test_servidor_inexistente(self):
        with _Conf():
            mcp_cliente.enregistrer({"nom": "fora", "url": "https://127.0.0.1:1/mcp"})
            r = mcp_cliente.lister_outils("fora")
            self.assertFalse(r["ok"])
            self.assertIn("fora", mcp_cliente._CATALOGUE)

    def test_roteamento_pt_e_mcp(self):
        self.assertIn("integrations_mcp", modules_pour_phrase("quais issues abertas no github"))
        self.assertIn("temps", modules_pour_phrase("que horas são"))
        self.assertIn("meteo", modules_pour_phrase("como está o clima amanhã"))
        self.assertIn("lumieres", modules_pour_phrase("acende a luz da sala"))
        self.assertIsNone(modules_pour_phrase("abre o bloco de notas"[:7] + " algo novo"))


if __name__ == "__main__":
    unittest.main()

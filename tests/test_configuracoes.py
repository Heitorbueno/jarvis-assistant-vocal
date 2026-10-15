"""Aba Configuracoes : esquema, segredos write-only, indices de lista, campos locais,
credenciais Google, testes de conexao e vozes ElevenLabs."""
import base64
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core import config, configuracoes as cf

RAIZ = Path(__file__).resolve().parent.parent


def _vrai_requests():
    """O módulo requests verdadeiro, mesmo se outro teste o substituiu em sys.modules."""
    mod = sys.modules.get("requests")
    if mod is not None and getattr(mod, "__file__", None):
        return mod
    stub = sys.modules.pop("requests", None)
    try:
        import requests as vrai
    finally:
        if stub is not None:
            sys.modules["requests"] = stub
    return vrai


class _Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = {"openai": {"cle": "sk-proj-EXISTENTE1234"}}
        self._p = [patch.object(config, "_CONFIG", self.d),
                   patch.object(config, "FICHIER", Path(self._t.name) / "c.yaml"),
                   patch.object(cf, "_RACINE", Path(self._t.name))]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()
        self._t.cleanup()


class EsquemaTest(unittest.TestCase):
    def test_todo_caminho_existe_no_projeto(self):
        """Cada campo do painel corresponde a uma chave lida no codigo ou documentada."""
        exemplo = (RAIZ / "config.example.yaml").read_text(encoding="utf-8")
        codigo = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                           for d in ("core", "tools") for p in (RAIZ / d).glob("*.py")) + \
            (RAIZ / "jarvis14.py").read_text(encoding="utf-8") + (RAIZ / "hud.py").read_text(encoding="utf-8")
        for g in cf.GRUPOS:
            for f in g["campos"]:
                c = f["caminho"]
                if c.startswith("_arquivo.") or ".comptes." in c:
                    continue
                folha = c.split(".")[-1]
                self.assertTrue(c in codigo or f'"{folha}"' in codigo or f"{folha}:" in exemplo, c)

    def test_caminhos_unicos(self):
        caminhos = [f["caminho"] for g in cf.GRUPOS for f in g["campos"]]
        self.assertEqual(len(caminhos), len(set(caminhos)))


class SalvarTest(_Base):
    def test_segredo_nunca_exposto_e_mantido(self):
        cf.salvar({"twilio.auth_token": "segredo-twilio-ABCD1234"})
        txt = json.dumps(cf.estado(), ensure_ascii=False)
        self.assertNotIn("segredo-twilio", txt)
        self.assertIn("••••1234", txt)
        cf.salvar({"twilio.auth_token": "••••1234", "twilio.numero": "+5565999990000"})
        self.assertEqual(self.d["twilio"]["auth_token"], "segredo-twilio-ABCD1234")
        cf.salvar({"twilio.auth_token": ""})
        self.assertEqual(self.d["twilio"]["auth_token"], "segredo-twilio-ABCD1234")
        cf.salvar({"twilio.auth_token": "__remover__"})
        self.assertEqual(self.d["twilio"]["auth_token"], "")

    def test_validacao(self):
        self.assertFalse(cf.salvar({"openai.cle": "x"})["ok"])                 # fora do esquema
        self.assertFalse(cf.salvar({"assistant.duree_suite": "999"})["ok"])
        self.assertFalse(cf.salvar({"alexa.url": "evil.com"})["ok"])
        self.assertFalse(cf.salvar({"signal_matin.heure": "25:00"})["ok"])
        self.assertFalse(cf.salvar({"hue.pont": "a\nb"})["ok"])
        r = cf.salvar({"assistant.seuil_reveil": "0,55", "budget.plafond_jour": "", "presence.actif": True})
        self.assertTrue(r["ok"], r)
        self.assertEqual((self.d["assistant"]["seuil_reveil"], self.d["presence"]["actif"]), (0.55, True))
        self.assertNotIn("budget", self.d)                                     # vazio nao cria chave
        cf.salvar({"budget.plafond_jour": "50"})
        cf.salvar({"budget.plafond_jour": ""})                                 # limpar volta a None
        self.assertIsNone(self.d["budget"]["plafond_jour"])
        self.assertEqual(self.d["openai"]["cle"], "sk-proj-EXISTENTE1234")    # resto intacto

    def test_campos_vazios_e_padrao_nao_gravam(self):
        r = cf.salvar({"instagram.comptes.1.nom": "", "obs.port": "4455", "hud.fenetre": "app"})
        self.assertTrue(r["ok"])
        self.assertEqual(self.d, {"openai": {"cle": "sk-proj-EXISTENTE1234"}})

    def test_indice_de_lista_instagram(self):
        self.d["instagram"] = {"comptes": [{"nom": "principal", "user_id": "1"}]}
        cf.salvar({"instagram.comptes.1.nom": "loja", "instagram.comptes.0.access_token": "tokenIG12345678"})
        self.assertEqual(self.d["instagram"]["comptes"][0],
                         {"nom": "principal", "user_id": "1", "access_token": "tokenIG12345678"})
        self.assertEqual(self.d["instagram"]["comptes"][1]["nom"], "loja")

    def test_campos_locais_recusados_a_distancia(self):
        self.assertFalse(cf.salvar({"navigateur.firefox_exe": "C:/x.exe"}, modo="distant")["ok"])
        self.assertTrue(cf.salvar({"navigateur.firefox_exe": "C:/x.exe"}, modo="local")["ok"])

    def test_recarrega_hue_carregado(self):
        mod = MagicMock(HUE_PONT="", HUE_CLE="")
        with patch.dict(sys.modules, {"tools.lumieres": mod}):
            cf.salvar({"hue.pont": "192.168.0.9", "hue.cle": "chavehue12345"})
        self.assertEqual((mod.HUE_PONT, mod.HUE_CLE), ("192.168.0.9", "chavehue12345"))

    def test_google_credentials(self):
        ruim = base64.b64encode(b'{"x":1}').decode()
        self.assertFalse(cf.salvar_google_credentials(ruim)["ok"])
        bom = base64.b64encode(json.dumps({"installed": {"client_id": "a", "client_secret": "b"}}).encode()).decode()
        self.assertTrue(cf.salvar_google_credentials(bom)["ok"])
        self.assertTrue((Path(self._t.name) / "google_credentials.json").exists())
        self.d["agenda"] = {"credentials": "../../fora.json"}
        cf.salvar_google_credentials(bom)
        self.assertFalse((Path(self._t.name).parent.parent / "fora.json").exists())

    def test_testes_de_conexao(self):
        requests = _vrai_requests()
        self.d.update({"twilio": {"account_sid": "AC1", "auth_token": "t"},
                       "discord": {"token": "x"}, "spotify": {"client_id": "a", "client_secret": "b"}})
        r = MagicMock(status_code=200); r.json.return_value = {"friendly_name": "Conta", "status": "active", "username": "JarvisBot"}
        with patch.dict(sys.modules, {"requests": requests}), patch.object(requests, "get", return_value=r), \
                patch.object(requests, "post", return_value=r):
            self.assertIn("Twilio OK", cf.testar("twilio")["message"])
            self.assertIn("JarvisBot", cf.testar("discord")["message"])
            self.assertTrue(cf.testar("spotify")["ok"])
        r401 = MagicMock(status_code=401)
        with patch.dict(sys.modules, {"requests": requests}), patch.object(requests, "get", return_value=r401):
            self.assertFalse(cf.testar("twilio")["ok"])
        self.assertFalse(cf.testar("hue")["ok"])                               # sem dados
        self.assertFalse(cf.testar("inexistente")["ok"])


class ElevenVozesTest(_Base):
    def test_minhas_vozes_primeiro(self):
        requests = _vrai_requests()
        from core import provedores
        self.d["elevenlabs"] = {"cle": "sk_teste1234567890"}
        vozes = {"voices": [
            {"voice_id": "p1", "name": "Rachel", "category": "premade", "labels": {"gender": "female"}},
            {"voice_id": "c1", "name": "Heitor clone", "category": "cloned", "labels": {"accent": "brazilian"},
             "preview_url": "https://x/p.mp3"},
            {"voice_id": "g1", "name": "Narrador", "category": "generated"}]}
        rv = MagicMock(status_code=200); rv.json.return_value = vozes
        rm = MagicMock(status_code=200); rm.json.return_value = []
        with patch.dict(sys.modules, {"requests": requests}), patch.object(requests, "get", side_effect=[rv, rm]):
            r = provedores.elevenlabs_tester()
        self.assertEqual([v["id"] for v in r["voix"]], ["c1", "g1", "p1"])
        self.assertTrue(r["voix"][0]["minha"] and not r["voix"][2]["minha"])
        self.assertIn("2 voz(es) sua(s)", r["message"])
        self.assertEqual(r["voix"][0]["detalhe"], "brazilian")


if __name__ == "__main__":
    unittest.main()

"""Inicio automatico, chat do HUD, diagnostico de erro do modelo e config atomica."""
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from core import autostart, config, diagnostic_llm


class _Erreur(Exception):
    def __init__(self, msg, status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class DiagnosticTest(unittest.TestCase):
    def test_classement(self):
        cas = {
            "auth": _Erreur("Incorrect API key provided", 401),
            "modele": _Erreur("The model `gpt-x` does not exist", 404),
            "quota": _Erreur("You exceeded your current quota", 429),
            "reseau": _Erreur("Connection error."),
            "cle_absente": RuntimeError("cle OpenAI absente (openai.cle)"),
            "inconnu": ValueError("???"),
        }
        for attendu, e in cas.items():
            self.assertEqual(diagnostic_llm.classer(e), attendu, e)

    def test_jamais_la_cle(self):
        diagnostic_llm.enregistrer(_Erreur("bad key sk-proj-ABCDEFGH12345678", 401), "OpenAI", "m")
        self.assertNotIn("ABCDEFGH", json.dumps(diagnostic_llm.dernier()))
        self.assertEqual(diagnostic_llm.dernier()["code"], "auth")


class AutostartTest(unittest.TestCase):
    def test_unite_systemd(self):
        u = autostart.contenu_unite("completo")
        self.assertIn("jarvis14.py", u)
        self.assertIn("WantedBy=default.target", u)
        self.assertIn("Restart=on-failure", u)
        s = autostart.contenu_unite("servidor", "jarvis")
        self.assertIn("scripts/jarvis_servidor.py", s)
        self.assertIn("User=jarvis", s)
        self.assertIn("WantedBy=multi-user.target", s)

    def test_mode_servidor_exige_root(self):
        with patch.object(autostart.sys, "platform", "linux"), \
                patch.object(autostart.shutil, "which", return_value="/bin/systemctl"), \
                patch.object(autostart.os, "geteuid", return_value=1000, create=True):
            r = autostart.configurer(True, "servidor")
        self.assertFalse(r["ok"])

    def test_modo_desconhecido_vira_completo(self):
        with patch.object(autostart, "_linux", return_value={"ok": True}) as l, \
                patch.object(autostart.sys, "platform", "linux"):
            autostart.configurer(True, "; rm -rf /")
        l.assert_called_once_with(True, "completo")


class ConfigTest(unittest.TestCase):
    def test_ecriture_atomique_et_sauvegarde(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "config.yaml"
            f.write_text("mode: local\n", encoding="utf-8")
            with patch.object(config, "FICHIER", f), patch.object(config, "_CONFIG", None):
                config.definir("assistant.langue", "pt")
                self.assertIn("langue: pt", f.read_text(encoding="utf-8"))
                self.assertEqual((Path(d) / "config.yaml.bak").read_text(encoding="utf-8"), "mode: local\n")
                self.assertFalse((Path(d) / "config.yaml.tmp").exists())
                config.definir("assistant.langue.x", 1)   # remplace une valeur non-dict sans planter
                self.assertEqual(config.reglage("assistant.langue.x"), 1)


class HudChatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hud
        cls.hud = hud
        cls.port = 18771
        cls.serveur = hud._Serveur(("127.0.0.1", cls.port), hud._Poignee)
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()

    def _post(self, corps, entetes=None):
        h = {"Content-Type": "application/json", "X-Jarvis-HUD": "1", "Host": "127.0.0.1"}
        h.update(entetes or {})
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/chat",
                                     data=json.dumps(corps).encode(), headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_chat_oculto_por_padrao_e_texto_na_fila(self):
        self.assertFalse(self.hud._ETAT["chat"])
        self.assertEqual(self._post({"texte": "  que horas   são "}), 200)
        self.assertEqual(self.hud.texte_en_attente(), "que horas são")
        self.assertIsNone(self.hud.texte_en_attente())
        self.hud.chat(True)
        self.assertEqual(self._post({"fechar": True}), 200)
        self.assertFalse(self.hud._ETAT["chat"])

    def test_chat_exige_cabecalho_hud(self):
        self.assertEqual(self._post({"texte": "x"}, {"X-Jarvis-HUD": "0"}), 403)
        self.assertIsNone(self.hud.texte_en_attente())

    def test_pagina_sem_traducao_do_navegador_e_pwa(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=5) as r:
            html = r.read().decode()
        self.assertIn('translate="no"', html)
        self.assertIn("/manifest.webmanifest", html)
        self.assertIn("<title>JARVIS · Reacteur arc</title>", html)
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/manifest.webmanifest", timeout=5) as r:
            self.assertEqual(json.loads(r.read())["display"], "standalone")

    def test_nao_abre_segunda_janela_com_pagina_conectada(self):
        with patch.object(self.hud.sys, "platform", "win32"), \
                patch.object(self.hud, "trouver_fenetres", return_value=[]), \
                patch.object(self.hud, "clients_connectes", return_value=1), \
                patch.object(self.hud, "ouvrir_fenetre") as ouvrir:
            self.hud._MODE_FENETRE = "app"
            self.hud._DERNIERE_OUVERTURE = 0
            self.assertFalse(self.hud.mettre_au_premier_plan())
        ouvrir.assert_not_called()
        self.assertIn("JARVIS · Reator arc", self.hud.TITRES_FENETRE)


if __name__ == "__main__":
    unittest.main()

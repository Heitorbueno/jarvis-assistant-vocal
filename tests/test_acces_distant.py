"""Accès distant (Tailscale/Cloudflare), fournisseurs d'IA, ElevenLabs et PWA."""
import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import acces_distant, cockpit, config, panneau, provedores, pwa

HOTE = "jarvis-pc.tail1234.ts.net"


class _Config:
    """config.yaml isole : dictionnaire en memoire + fichier temporaire."""

    def __init__(self, donnees=None):
        self.donnees = donnees or {}

    def start(self):
        import tempfile
        from pathlib import Path
        self._dir = tempfile.TemporaryDirectory()
        self._p = patch.object(config, "_CONFIG", self.donnees)
        self._f = patch.object(config, "FICHIER", Path(self._dir.name) / "config.yaml")
        self._p.start()
        self._f.start()

    def stop(self):
        self._f.stop()
        self._p.stop()
        self._dir.cleanup()


def _app():
    app = FastAPI()
    acces_distant.monter_routes(app)
    pwa.monter_routes(app)
    panneau.monter_routes(app)
    cockpit.monter_routes(app)
    return app


def _client(base):
    return TestClient(_app(), base_url=base)


# Le TestClient se presente comme "testclient" : on l'assimile au loopback, comme
# le proxy Tailscale Serve/cloudflared qui tourne sur le poste.
_LOOPBACK = {"127.0.0.1", "::1", "testclient"}


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.conf = _Config({})
        self.conf.start()
        self._a = patch.object(acces_distant, "socket_autorisee",
                               side_effect=lambda a: str(a) in _LOOPBACK)
        self._a.start()
        from core import http_local
        self._b = patch.object(http_local, "_ADRESSES_LOCALES", _LOOPBACK)
        self._b.start()
        acces_distant.reinitialiser_echecs()

    def tearDown(self):
        self._b.stop()
        self._a.stop()
        self.conf.stop()

    def activer(self, cockpit_=False):
        code = acces_distant.generer_code()
        r = acces_distant.configurer(hotes_=[HOTE], cockpit=cockpit_, actif_=True)
        self.assertTrue(r["ok"], r)
        return code

    def distant(self):
        # Tailscale Serve : Host = nom ts.net + X-Forwarded-For, en HTTPS.
        return _client(f"https://{HOTE}")

    def entrer(self, client, code):
        return client.post("/api/acesso/entrar", content=json.dumps({"codigo": code}),
                           headers={"Content-Type": "application/json",
                                    "X-Jarvis-Panneau": "1",
                                    "Origin": f"https://{HOTE}",
                                    "X-Forwarded-For": "100.101.102.103"})


class AccesDistantTest(BaseTest):
    def test_defaut_tout_reste_local(self):
        c = self.distant()
        h = {"X-Forwarded-For": "100.1.2.3"}
        self.assertEqual(c.get("/panneau", headers=h).status_code, 403)
        self.assertEqual(c.get("/api/panneau/modeles", headers=h).status_code, 403)
        self.assertEqual(c.get("/", headers=h).status_code, 404)
        self.assertEqual(c.get("/acesso", headers=h).status_code, 404)

    def test_activation_exige_hote_et_code(self):
        self.assertFalse(acces_distant.configurer(actif_=True)["ok"])
        acces_distant.configurer(hotes_=[HOTE])
        self.assertFalse(acces_distant.configurer(actif_=True)["ok"])
        acces_distant.generer_code()
        self.assertTrue(acces_distant.configurer(actif_=True)["ok"])

    def test_normalisation_hotes(self):
        self.assertEqual(acces_distant.normaliser_hote("https://Jarvis.ts.net:443/x"), "jarvis.ts.net")
        self.assertEqual(acces_distant.normaliser_hote("localhost"), "")
        self.assertEqual(acces_distant.normaliser_hote("a b.com"), "")
        self.assertFalse(acces_distant.configurer(hotes_=["evil host"])["ok"])
        self.assertFalse(acces_distant.configurer(reseaux_=["pas-un-cidr"])["ok"])

    def test_flux_complet_login_puis_panneau(self):
        code = self.activer()
        c = self.distant()
        r = c.get("/", headers={"X-Forwarded-For": "100.1.2.3"}, follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["location"], "/acesso")
        self.assertEqual(c.get("/acesso", headers={"X-Forwarded-For": "100.1.2.3"}).status_code, 200)
        self.assertEqual(c.get("/api/panneau/modeles").status_code, 403)
        r = self.entrer(c, code.lower().replace("-", " "))
        self.assertEqual(r.status_code, 200, r.text)
        cookie = r.headers["set-cookie"].lower()
        for attendu in ("httponly", "secure", "samesite=strict"):
            self.assertIn(attendu, cookie)
        with patch.object(panneau, "_HTML", MagicMock(
                exists=lambda: True, read_text=lambda **k: "<html><head></head><body>x</body></html>")):
            r = c.get("/panneau", headers={"X-Forwarded-For": "100.1.2.3"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("manifest.webmanifest", r.text)
        self.assertEqual(c.get("/api/panneau/session").json()["mode"], "distant")

    def test_hote_non_declare_refuse_meme_avec_cookie(self):
        code = self.activer()
        c = self.distant()
        self.entrer(c, code)
        jeton = c.cookies.get(acces_distant.COOKIE)
        autre = _client("https://evil.example")
        r = autre.get("/api/panneau/modeles", cookies={acces_distant.COOKIE: jeton})
        self.assertEqual(r.status_code, 403)

    def test_cookie_falsifie_ou_expire_refuse(self):
        self.activer()
        c = self.distant()
        r = c.get("/api/panneau/modeles", cookies={acces_distant.COOKIE: "9999999999.aa.bb"})
        self.assertEqual(r.status_code, 403)
        with patch.object(acces_distant.time, "time", return_value=0):
            vieux = acces_distant.creer_session()
        self.assertFalse(acces_distant.session_valide(vieux))

    def test_nouveau_code_deconnecte_les_sessions(self):
        code = self.activer()
        c = self.distant()
        self.entrer(c, code)
        self.assertEqual(c.get("/api/panneau/session").status_code, 200)
        acces_distant.generer_code()
        self.assertEqual(c.get("/api/panneau/session").status_code, 403)

    def test_mauvais_code_limite(self):
        self.activer()
        c = self.distant()
        for _ in range(5):
            self.assertEqual(self.entrer(c, "AAAA-AAAA-AAAA-AAAA").status_code, 401)
        self.assertEqual(self.entrer(c, "AAAA-AAAA-AAAA-AAAA").status_code, 429)

    def test_login_exige_origin_https_du_meme_hote(self):
        code = self.activer()
        c = self.distant()
        r = c.post("/api/acesso/entrar", content=json.dumps({"codigo": code}),
                   headers={"Content-Type": "application/json", "X-Jarvis-Panneau": "1",
                            "Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_ecriture_distante_exige_origin(self):
        code = self.activer()
        c = self.distant()
        self.entrer(c, code)
        base = {"Content-Type": "application/json", "X-Jarvis-Panneau": "1"}
        with patch.object(panneau, "_whisper_supprimer", return_value={"ok": True}) as suppr:
            r = c.post("/api/panneau/whisper/supprimer", content='{"nom":"small"}', headers=base)
            self.assertEqual(r.status_code, 403)
            r = c.post("/api/panneau/whisper/supprimer", content='{"nom":"small"}',
                       headers={**base, "Origin": f"https://{HOTE}"})
            self.assertEqual(r.status_code, 200)
            suppr.assert_called_once()

    def test_config_acces_jamais_modifiable_a_distance(self):
        code = self.activer()
        c = self.distant()
        self.entrer(c, code)
        h = {"Content-Type": "application/json", "X-Jarvis-Panneau": "1", "Origin": f"https://{HOTE}"}
        self.assertEqual(c.get("/api/panneau/acces").status_code, 403)
        self.assertEqual(c.post("/api/panneau/acces/code", content="{}", headers=h).status_code, 403)
        self.assertEqual(c.post("/api/panneau/acces", content='{"actif":false}', headers=h).status_code, 403)

    def test_cockpit_distant_opt_in(self):
        code = self.activer(cockpit_=False)
        c = self.distant()
        self.entrer(c, code)
        with patch.object(cockpit, "_finances", return_value={"nb": 0}):
            self.assertEqual(c.get("/api/cockpit/finances").status_code, 403)
            acces_distant.configurer(cockpit=True)
            self.assertEqual(c.get("/api/cockpit/finances").status_code, 200)

    def test_local_inchange(self):
        c = _client("http://127.0.0.1:8790")
        with patch.object(panneau, "_modeles", return_value={"ok": True}):
            self.assertEqual(c.get("/api/panneau/modeles").status_code, 200)
        r = c.get("/", follow_redirects=False)
        self.assertEqual(r.headers["location"], "/panneau")
        self.assertEqual(c.get("/api/panneau/acces").json()["actif"], False)

    def test_code_jamais_stocke_en_clair(self):
        code = acces_distant.generer_code()
        dump = json.dumps(self.conf.donnees)
        self.assertNotIn(code, dump)
        self.assertTrue(acces_distant.verifier_code(code))
        self.assertFalse(acces_distant.verifier_code("XXXX-XXXX-XXXX-XXXX"))


class ProvedoresTest(BaseTest):
    H = {"Content-Type": "application/json", "X-Jarvis-Panneau": "1"}

    def test_cle_jamais_renvoyee(self):
        c = _client("http://127.0.0.1:8790")
        cle = "sk-test-SECRETSECRET1234"
        r = c.post("/api/panneau/provedores/chave", headers=self.H,
                   content=json.dumps({"id": "groq", "chave": cle}))
        self.assertTrue(r.json()["ok"])
        self.assertNotIn("SECRETSECRET", r.text)
        with patch("core.routage.mode_actuel", return_value="hybride"):
            liste = c.get("/api/panneau/provedores").text
        self.assertNotIn("SECRETSECRET", liste)
        self.assertIn("1234", liste)
        self.assertEqual(self.conf.donnees["groq"]["cle"], cle)

    def test_cle_invalide_refusee(self):
        r = provedores.enregistrer_cle("openai", "abc def\nxyz")
        self.assertFalse(r["ok"])
        self.assertFalse(provedores.enregistrer_cle("inconnu", "sk-12345678")["ok"])

    def _rep(self, code, data):
        r = MagicMock(status_code=code)
        r.json.return_value = data
        return r

    def test_tester_liste_les_modeles(self):
        provedores.enregistrer_cle("openai", "sk-proj-abcdefgh")
        with patch("requests.get", return_value=self._rep(200, {"data": [{"id": "gpt-b"}, {"id": "gpt-a"}]})) as g:
            r = provedores.tester("openai")
        self.assertTrue(r["ok"])
        self.assertEqual(r["modeles"], ["gpt-a", "gpt-b"])
        self.assertEqual(g.call_args.kwargs["headers"]["Authorization"], "Bearer sk-proj-abcdefgh")

    def test_tester_gemini_et_anthropic(self):
        provedores.enregistrer_cle("gemini", "AIzaFAKEKEY123")
        data = {"models": [{"name": "models/gemini-x", "supportedGenerationMethods": ["generateContent"]},
                           {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]}]}
        with patch("requests.get", return_value=self._rep(200, data)) as g:
            r = provedores.tester("gemini")
        self.assertEqual(r["modeles"], ["gemini-x"])
        self.assertIn("x-goog-api-key", g.call_args.kwargs["headers"])
        provedores.enregistrer_cle("anthropic", "sk-ant-FAKE1234")
        with patch("requests.get", return_value=self._rep(200, {"data": [{"id": "claude-x"}]})) as g:
            r = provedores.tester("anthropic")
        self.assertEqual(g.call_args.kwargs["headers"]["anthropic-version"], "2023-06-01")

    def test_erreur_ne_reflete_pas_la_cle(self):
        provedores.enregistrer_cle("openai", "sk-proj-LEAKLEAK99")
        with patch("requests.get", return_value=self._rep(
                401, {"error": {"message": "Incorrect API key provided"}})):
            r = provedores.tester("openai")
        self.assertFalse(r["ok"])
        self.assertNotIn("LEAKLEAK", r["message"])
        self.assertIn("recusada", r["message"])

    def test_tester_sans_cle(self):
        self.assertFalse(provedores.tester("mistral")["ok"])

    def test_choisir_et_activer(self):
        self.assertTrue(provedores.choisir_modele("groq", "llama-3.3-70b-versatile")["ok"])
        self.assertEqual(self.conf.donnees["groq"]["modele"], "llama-3.3-70b-versatile")
        self.assertFalse(provedores.choisir_modele("groq", "../etc")["ok"])
        self.assertFalse(provedores.activer("groq", "x")["ok"])
        with patch.object(panneau, "_definir_actif", return_value={"ok": True}) as act:
            provedores.activer("anthropic", "claude-x", "qualite")
        act.assert_called_once_with("cloud", "claude-x", profil="qualite", fournisseur="anthropic")

    def test_hote_ollama(self):
        self.assertTrue(provedores.enregistrer_hote_ollama("http://192.168.0.5:11434")["ok"])
        for mauvais in ("file:///etc/passwd", "http://u:p@h", "javascript:x", ""):
            self.assertFalse(provedores.enregistrer_hote_ollama(mauvais)["ok"], mauvais)

    def test_elevenlabs(self):
        self.assertFalse(provedores.elevenlabs_tester()["ok"])
        provedores.elevenlabs_enregistrer_cle("sk_eleven_FAKE5678")
        rv = self._rep(200, {"voices": [{"voice_id": "abc123XYZ", "name": "Ana", "category": "premade"}]})
        rm = self._rep(200, [{"model_id": "eleven_flash_v2_5", "name": "Flash", "can_do_text_to_speech": True}])
        with patch("requests.get", side_effect=[rv, rm]):
            r = provedores.elevenlabs_tester()
        self.assertTrue(r["ok"])
        self.assertEqual(r["voix"][0]["id"], "abc123XYZ")
        with patch("core.tts.reinitialiser"):
            self.assertTrue(provedores.elevenlabs_choisir("abc123XYZ", "eleven_flash_v2_5", True)["ok"])
            self.assertFalse(provedores.elevenlabs_choisir("../x", None)["ok"])
        self.assertEqual(self.conf.donnees["tts"]["moteur"], "elevenlabs")
        self.assertNotIn("FAKE5678", json.dumps(provedores.elevenlabs_etat()))


class PwaTest(BaseTest):
    def test_fichiers_pwa_locaux(self):
        c = _client("http://127.0.0.1:8790")
        m = c.get("/manifest.webmanifest")
        self.assertEqual(m.status_code, 200)
        self.assertEqual(m.json()["display"], "standalone")
        self.assertIn("/api/", c.get("/sw.js").text)
        for nom in ("icone-192.png", "icone-512.png", "icone-maskable-512.png", "apple-touch-icon.png"):
            r = c.get(f"/pwa/{nom}")
            self.assertEqual(r.status_code, 200, nom)
            self.assertTrue(r.content.startswith(b"\x89PNG"))
        self.assertEqual(c.get("/pwa/../config.yaml").status_code, 404)
        self.assertEqual(c.get("/pwa/inconnu.png").status_code, 404)

    def test_pwa_refusee_sur_hote_inconnu(self):
        self.assertEqual(_client("https://evil.example").get("/manifest.webmanifest").status_code, 404)

    def test_pwa_servie_sur_hote_declare(self):
        self.activer()
        self.assertEqual(self.distant().get("/manifest.webmanifest").status_code, 200)


if __name__ == "__main__":
    unittest.main()

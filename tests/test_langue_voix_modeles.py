"""Idioma pt-BR, Ollama pelo painel, voz (ajustes/clonagem/Piper) e fallback de modelos."""
import base64
import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _vrai_requests():
    """Le vrai module requests, meme si un autre test l'a remplace dans sys.modules."""
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


REQUESTS = _vrai_requests()
from core import config, langue, ollama_gestion, provedores, voix_gestion
from core.confirmation_vocale import NON, OUI, TOUJOURS, interpreter_confirmation


class _Conf:
    def __init__(self, donnees=None):
        self.donnees = donnees or {}

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        self._p = [patch.object(config, "_CONFIG", self.donnees),
                   patch.object(config, "FICHIER", Path(self._dir.name) / "config.yaml")]
        for p in self._p:
            p.start()
        return self.donnees

    def __exit__(self, *a):
        for p in reversed(self._p):
            p.stop()
        self._dir.cleanup()


@contextlib.contextmanager
def _requests(**patches):
    with patch.dict(sys.modules, {"requests": REQUESTS}), contextlib.ExitStack() as pile:
        mocks = {nom: pile.enter_context(patch.object(REQUESTS, nom, **kw))
                 for nom, kw in patches.items()}
        yield mocks


def _rep(code, data):
    r = MagicMock(status_code=code)
    r.json.return_value = data
    return r


PT = {"assistant": {"langue": "pt"}}


class LangueTest(unittest.TestCase):
    def test_francais_inchange_par_defaut(self):
        with _Conf({}):
            self.assertEqual(langue.code(), "fr")
            self.assertEqual(langue.consigne_systeme(), "")
            for t in ("Je regarde ton agenda.", "Je vais executer x. Tu confirmes ?"):
                self.assertEqual(langue.localiser(t), t)
            self.assertEqual(langue.elevenlabs(), "fr")
            self.assertEqual(langue.kokoro_voix_defaut(), "ff_siwis")

    def test_phrases_systeme_traduites(self):
        with _Conf(json.loads(json.dumps(PT))):
            self.assertEqual(langue.localiser("Je regarde ton agenda."), "Vou olhar sua agenda.")
            self.assertEqual(
                langue.localiser("Je vais mettre le mail numero 3 a la corbeille. Tu confirmes ? "
                                 "Tu peux dire oui, toujours."),
                "Vou mover o e-mail número 3 para a lixeira. Confirma? Você pode dizer: sim, sempre.")
            self.assertIn("segunda-feira", langue.localiser(
                "Je vais ajouter : Dentiste le lundi 3 mars a 14h00 pour 30 minutes."))
            # Une reponse du LLM en portugais passe intacte.
            self.assertEqual(langue.localiser("Tudo certo, já liguei a luz."),
                             "Tudo certo, já liguei a luz.")

    def test_toutes_les_annonces_fixes_des_outils_sont_traduites(self):
        from core import registre
        registre.charger_outils()
        with _Conf(json.loads(json.dumps(PT))):
            manquantes = [o.nom for o in registre.tous()
                          if o.phrase_attente and langue.localiser(o.phrase_attente) == o.phrase_attente]
        self.assertEqual(manquantes, [], f"phrase_attente sans traduction pt : {manquantes}")

    def test_consigne_et_persona(self):
        from core import personnalite
        with _Conf(json.loads(json.dumps(PT))):
            self.assertIn("português do Brasil", langue.consigne_systeme())
            self.assertTrue(personnalite.persona("neutre").startswith("Você"))
            self.assertEqual(langue.whisper(), "pt")
            self.assertEqual(langue.kokoro(), "pt-br")

    def test_confirmations_portugais(self):
        cas = {"sim": OUI, "pode mandar no whatsapp": OUI, "pode mandar para o João": OUI,
               "claro": OUI, "sim, sempre": TOUJOURS, "não": NON, "agora não": NON,
               "cancela": NON, "deixa pra lá": NON, "hmm": NON, "": NON}
        for texte, attendu in cas.items():
            self.assertEqual(interpreter_confirmation(texte, "pt"), attendu, texte)
        # Francais : comportement d'origine.
        self.assertEqual(interpreter_confirmation("oui", "fr"), OUI)
        self.assertEqual(interpreter_confirmation("non, ne le fais pas", "fr"), NON)

    def test_outil_changer_langue(self):
        from tools.langue import changer_langue
        with _Conf({}) as d, patch("core.tts.reinitialiser"):
            self.assertIn("português", changer_langue("pt"))
            self.assertEqual(d["assistant"]["langue"], "pt")
            changer_langue("fr")
            self.assertEqual(d["assistant"]["langue"], "fr")

    def test_panneau_injecte_langue(self):
        from core import pwa
        with _Conf(json.loads(json.dumps(PT))):
            html = pwa.injecter('<html lang="fr"><head></head><body></body></html>')
        self.assertIn('data-langue="pt"', html)
        self.assertIn("/pwa/i18n.js", html)


class OllamaTest(unittest.TestCase):
    def test_detection_corrige_hote(self):
        def faux_get(url, timeout=0):
            if url.startswith("http://127.0.0.1:11434/api/version"):
                return _rep(200, {"version": "0.9.0"})
            if url.startswith("http://127.0.0.1:11434/api/tags"):
                return _rep(200, {"models": [{"name": "qwen2.5:7b", "size": 4 * 1024 ** 3}]})
            raise REQUESTS.exceptions.ConnectionError()
        with _Conf({"ollama": {"hote": "http://10.9.9.9:11434"}}) as d, \
                _requests(get={"side_effect": faux_get}), \
                patch.object(ollama_gestion, "_version", side_effect=lambda h, timeout=2.5:
                             "0.9.0" if h.startswith("http://127.0.0.1") else None):
            r = ollama_gestion.detecter()
        self.assertTrue(r["joignable"])
        self.assertTrue(r["hote_corrige"])
        self.assertEqual(d["ollama"]["hote"], "http://127.0.0.1:11434")
        self.assertEqual(r["modeles"][0]["nom"], "qwen2.5:7b")

    def test_installation_commande_officielle_sans_parametre(self):
        self.assertEqual(ollama_gestion._commande_installation("winget")[:4],
                         ["winget", "install", "--id", "Ollama.Ollama"])
        self.assertIn("ollama.com/install.sh", " ".join(ollama_gestion._commande_installation("script")))
        self.assertIsNone(ollama_gestion._commande_installation("autre"))

    def test_installation_refusee_sans_root_linux(self):
        with patch.object(ollama_gestion, "binaire", return_value=None), \
                patch.object(ollama_gestion, "methode_installation", return_value="script"), \
                patch.object(ollama_gestion.os, "geteuid", return_value=1000, create=True), \
                patch.object(ollama_gestion.subprocess, "run") as run:
            r = ollama_gestion.installer_programme()
        self.assertFalse(r["ok"])
        run.assert_not_called()

    def test_installation_ignoree_si_deja_installe(self):
        with patch.object(ollama_gestion, "binaire", return_value="/usr/bin/ollama"), \
                patch.object(ollama_gestion.subprocess, "run") as run:
            self.assertTrue(ollama_gestion.installer_programme()["deja"])
        run.assert_not_called()


class VoixTest(unittest.TestCase):
    def test_sans_reglage_aucun_voice_settings(self):
        with _Conf({}):
            self.assertIsNone(voix_gestion.voice_settings_eleven())
            self.assertEqual(voix_gestion.params_piper(), {})
            self.assertEqual(voix_gestion.vitesse_kokoro(), 1.0)

    def test_reglages_bornes_et_application(self):
        with _Conf({}), patch("core.tts.reinitialiser"):
            self.assertFalse(voix_gestion.definir_reglages({"elevenlabs.vitesse": 3})["ok"])
            self.assertFalse(voix_gestion.definir_reglages({"autre.cle": 1})["ok"])
            self.assertTrue(voix_gestion.definir_reglages(
                {"elevenlabs.stabilite": 0.3, "elevenlabs.vitesse": 1.1, "elevenlabs.boost": True,
                 "piper.vitesse": 2.0})["ok"])
            vs = voix_gestion.voice_settings_eleven()
            self.assertEqual(vs["stability"], 0.3)
            self.assertEqual(vs["speed"], 1.1)
            self.assertTrue(vs["use_speaker_boost"])
            self.assertEqual(voix_gestion.params_piper()["length_scale"], 0.5)
            voix_gestion.definir_reglages({"elevenlabs.stabilite": None, "elevenlabs.vitesse": None,
                                           "elevenlabs.boost": None})
            self.assertIsNone(voix_gestion.voice_settings_eleven())

    def test_clonage(self):
        audio = base64.b64encode(b"ID3" + b"\0" * 2000).decode()
        with _Conf({"elevenlabs": {"cle": "sk_test_12345678"}}) as d, patch("core.tts.reinitialiser"), \
                _requests(post={"return_value": _rep(200, {"voice_id": "vozNova123"})}) as m:
            self.assertFalse(voix_gestion.cloner_elevenlabs("", [{"nome": "a.mp3", "dados": audio}])["ok"])
            self.assertFalse(voix_gestion.cloner_elevenlabs("x", [{"nome": "a.exe", "dados": audio}])["ok"])
            r = voix_gestion.cloner_elevenlabs("Minha voz", [{"nome": "a.mp3", "dados": audio}])
        self.assertTrue(r["ok"], r)
        self.assertEqual(d["elevenlabs"]["voix"], "vozNova123")
        envoye = m["post"].call_args
        self.assertTrue(envoye.args[0].endswith("/voices/add"))
        self.assertEqual(envoye.kwargs["data"]["name"], "Minha voz")

    def test_piper_noms_et_import(self):
        self.assertEqual(voix_gestion._url_piper("pt_BR-faber-medium")[0],
                         "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/"
                         "faber/medium/pt_BR-faber-medium.onnx")
        for mauvais in ("../x", "pt_BR-faber", "x;rm -rf"):
            self.assertFalse(voix_gestion.telecharger_piper(mauvais)["ok"])
        with tempfile.TemporaryDirectory() as tmp, _Conf({}), patch("core.tts.reinitialiser"), \
                patch.object(voix_gestion, "DOSSIER_VOIX", Path(tmp)):
            onnx = base64.b64encode(b"\0" * 4096).decode()
            js = base64.b64encode(b'{"audio": {}}').decode()
            self.assertFalse(voix_gestion.importer_piper("../evil", onnx, js)["ok"])
            self.assertFalse(voix_gestion.importer_piper("ok_voz", onnx, base64.b64encode(b"x").decode())["ok"])
            self.assertTrue(voix_gestion.importer_piper("pt_BR-minha-medium.onnx", onnx, js)["ok"])
            self.assertTrue(voix_gestion.choisir_piper("pt_BR-minha-medium", True)["ok"])
            self.assertEqual(config.reglage("tts.moteur"), "piper")
            liste = voix_gestion.voix_locales()
            self.assertTrue(liste["voix"][0]["active"])
            self.assertTrue(voix_gestion.supprimer_piper("pt_BR-minha-medium")["ok"])
            self.assertEqual(list(Path(tmp).iterdir()), [])


class ModelesTest(unittest.TestCase):
    def test_favoris(self):
        with _Conf({}):
            self.assertTrue(provedores.favoris_ajouter("openai", "gpt-a")["ok"])
            provedores.favoris_ajouter("openai", "gpt-b")
            self.assertEqual(provedores.favoris("openai"), ["gpt-a", "gpt-b"])
            self.assertFalse(provedores.favoris_ajouter("openai", "../x")["ok"])
            provedores.favoris_retirer("openai", "gpt-a")
            self.assertEqual(provedores.favoris("openai"), ["gpt-b"])

    def test_repli_validation(self):
        with _Conf({}):
            self.assertFalse(provedores.repli_definir(True, ["groq:x"])["ok"])
            r = provedores.repli_definir(True, ["openai:gpt-a", "ollama:qwen2.5:7b", "openai:gpt-a"])
            self.assertEqual(r["ordem"], ["openai:gpt-a", "ollama:qwen2.5:7b"])

    def _faux(self, nom, modele, erreur=None, dispo=True):
        p = MagicMock()
        p.nom, p.modele = nom, modele
        p.disponible.return_value = dispo
        if erreur:
            p.repondre.side_effect = erreur
        else:
            p.repondre.return_value = f"ok-{nom}"
        return p

    def test_repli_essaie_dans_l_ordre(self):
        from core.llm import ProviderAvecRepli
        principal = self._faux("OpenAI", "a", RuntimeError("quota"))
        hs = self._faux("Claude", "b", dispo=False)
        local = self._faux("Ollama", "c")
        w = ProviderAvecRepli(principal, [hs, local])
        self.assertEqual(w.nom, "OpenAI")
        self.assertEqual(w.repondre("s", [], []), "ok-Ollama")
        hs.repondre.assert_not_called()
        tous_ko = ProviderAvecRepli(self._faux("OpenAI", "a", RuntimeError("x")),
                                    [self._faux("Ollama", "c", RuntimeError("y"))])
        with self.assertRaises(RuntimeError):
            tous_ko.repondre("s", [], [])

    def test_llm_sans_repli_inchange_et_local_jamais_cloud(self):
        from core import llm
        with _Conf({"mode": "local", "llm": {"repli_actif": True,
                                             "repli": ["openai:gpt-a", "ollama:llama3.2:3b"]},
                    "ollama": {"modele": "qwen2.5:7b"}}):
            llm.reinitialiser()
            p = llm.llm()
            self.assertIsInstance(p, llm.ProviderAvecRepli)
            self.assertEqual([r.nom for r in p.replis], ["Ollama"])
        with _Conf({"mode": "local", "ollama": {"modele": "qwen2.5:7b"}}):
            llm.reinitialiser()
            self.assertIsInstance(llm.llm(), llm.OllamaProvider)
        llm.reinitialiser()

    def test_outil_vocal_changer_modele(self):
        from tools.modeles_ia import changer_modele_ia
        with _Conf({"openai": {"favoris": ["gpt-5.6-luna", "gpt-6-astra"]}}):
            self.assertIn("gpt-6-astra", changer_modele_ia("openai"))
            with patch.object(provedores, "activer", return_value={"ok": True, "message": "ok astra"}) as a:
                self.assertEqual(changer_modele_ia("openai", "astra"), "ok astra")
            a.assert_called_once_with("openai", "gpt-6-astra")
            self.assertIn("Aucun", changer_modele_ia("anthropic", "x"))


if __name__ == "__main__":
    unittest.main()

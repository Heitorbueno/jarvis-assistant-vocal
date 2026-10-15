"""Problemas relatados em uso real (Windows) : idioma, « Oi Jarvis » sem resposta,
voz robotica com chave ElevenLabs invalida, instancia unica."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))
import jarvis14  # noqa: E402
from core import config, langue, tts  # noqa: E402

PT = {"assistant": {"langue": "pt"}}


class _Conf:
    def __init__(self, d):
        self.d = d

    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        self._p = [patch.object(config, "_CONFIG", self.d),
                   patch.object(config, "FICHIER", Path(self._t.name) / "c.yaml")]
        for p in self._p:
            p.start()
        tts.reinitialiser()
        return self.d

    def __exit__(self, *a):
        for p in reversed(self._p):
            p.stop()
        self._t.cleanup()
        tts.reinitialiser()


class OiJarvisTest(unittest.TestCase):
    def test_saudacao_sozinha_vira_vazio(self):
        for frase in ("Oi Jarvis", "Oi, Jarvis.", "Olá Jarvis!", "Ei Jarvis", "Jarvis", "oi"):
            self.assertEqual(jarvis14.nettoyer(frase), "", frase)

    def test_saudacao_com_pedido_mantem_o_pedido(self):
        self.assertEqual(jarvis14.nettoyer("Oi Jarvis, que horas são?"), "que horas são?")
        self.assertEqual(jarvis14.nettoyer("Oi Jarvis que horas são"), "que horas são")
        self.assertEqual(jarvis14.nettoyer("Jarvis ouvre YouTube"), "ouvre YouTube")   # frances intacto

    def test_so_saudacao_responde_pois_nao_em_vez_de_silencio(self):
        whisper = MagicMock()
        whisper.transcribe.return_value = ([SimpleNamespace(text="Oi Jarvis")], None)
        with _Conf(dict(PT)):
            self.assertIsNone(jarvis14.traiter(object(), whisper, [], None, None))
            with patch.object(jarvis14, "dire") as dire, patch.object(jarvis14, "_hud"):
                jarvis14._acolher_despertar()
            dire.assert_called_once_with("Pois não?", interruptible=False)


class IdiomaTest(unittest.TestCase):
    def test_regras_do_sistema_em_portugues(self):
        with _Conf(dict(PT)), patch.object(jarvis14.memoire, "texte_pour_systeme", return_value=""):
            jarvis14._refaire_systeme({})
            s = jarvis14.SYSTEME_COURANT
        self.assertIn("SEMPRE em português do Brasil", s)
        self.assertNotIn("en francais", s)
        self.assertTrue(s.startswith("Você"))                         # persona em pt
        with _Conf({}), patch.object(jarvis14.memoire, "texte_pour_systeme", return_value=""):
            jarvis14._refaire_systeme({})
            self.assertIn("en francais", jarvis14.SYSTEME_COURANT)     # frances inalterado

    def test_troca_de_idioma_reconstroi_o_prompt(self):
        with _Conf({}) as d, patch.object(jarvis14.memoire, "texte_pour_systeme", return_value=""), \
                patch.object(jarvis14.memoire, "charger", return_value={}):
            jarvis14._refaire_systeme({})
            d["assistant"] = {"langue": "pt"}
            with patch.object(jarvis14, "_repondre_route_prioritaire_commune", return_value="ok"):
                jarvis14.repondre([{"role": "user", "content": "oi"}])
            self.assertIn("português do Brasil", jarvis14.SYSTEME_COURANT)

    def test_rede_de_seguranca_traduz_frances_que_escapou(self):
        self.assertTrue(langue.parece_frances("Il fait 33 degres a Cuiaba, ciel degage."))
        self.assertFalse(langue.parece_frances("Faz 33 graus em Cuiabá, céu limpo."))
        self.assertFalse(langue.parece_frances("OK"))
        fake = MagicMock()
        fake.repondre.return_value = SimpleNamespace(content=[SimpleNamespace(type="text", text="Faz 33 graus.")])
        with _Conf(dict(PT)), patch("core.llm.llm", return_value=fake):
            self.assertEqual(langue.traduzir_para_pt("Il fait 33 degres, le ciel est degage."), "Faz 33 graus.")
            fake.repondre.reset_mock()
            self.assertEqual(langue.traduzir_para_pt("Faz 33 graus em Cuiabá hoje."), "Faz 33 graus em Cuiabá hoje.")
            fake.repondre.assert_not_called()
        with _Conf({}), patch("core.llm.llm", return_value=fake):        # frances : nada muda
            self.assertEqual(langue.traduzir_para_pt("Il fait beau."), "Il fait beau.")

    def test_teste_de_voz_do_hud_em_portugues(self):
        import hud
        with _Conf(dict(PT)), patch("core.voix.parler") as falar, patch("threading.Thread") as th:
            hud._appliquer_controle({"action": "tester_voix"})
        if th.call_args:
            self.assertIn("Teste da voz", th.call_args.kwargs["args"][0])


class VozElevenTest(unittest.TestCase):
    def test_id_da_chave_nao_tenta_api_e_explica(self):
        conf = {"tts": {"moteur": "elevenlabs"},
                "elevenlabs": {"cle": "abababababababababababababababababababababababababababababababab"}}
        with _Conf(conf):
            p = tts.tts()
            self.assertNotEqual(p.nom, "ElevenLabs")
            self.assertIn("ID da chave", tts.ESTADO["erro"])
            self.assertIn("ElevenLabs desativado", tts.ESTADO["motor"])

    def test_chave_valida_usa_elevenlabs(self):
        with _Conf({"tts": {"moteur": "elevenlabs"}, "elevenlabs": {"cle": "sk_valida1234567890"}}):
            self.assertEqual(tts.tts().nom, "ElevenLabs")


class InstanciaUnicaTest(unittest.TestCase):
    def test_segunda_instancia_recusada(self):
        with _Conf({"assistant": {"port_instance": 18767}}):
            self.assertTrue(jarvis14._instance_unique())
            primeiro = jarvis14._VERROU_INSTANCE
            self.assertFalse(jarvis14._instance_unique())
            primeiro.close()


if __name__ == "__main__":
    unittest.main()

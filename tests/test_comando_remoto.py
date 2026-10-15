"""Comando de voz/chat pelo PWA : chat oculto aberto so por voz, regras remotas N1/N2/N3."""
import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core import comando_remoto, config, registre


class _Bloco(SimpleNamespace):
    pass


class _LLM:
    """Simula o modelo : pede uma ferramenta, depois responde texto."""
    nom = "OpenAI"

    def __init__(self, ferramenta, args):
        self.passo = 0
        self.ferramenta, self.args = ferramenta, args
        self.vistas = None

    def disponible(self):
        return True

    def repondre(self, systeme, mensagens, outils):
        self.vistas = {o["name"] for o in outils}
        self.passo += 1
        if self.passo == 1:
            return SimpleNamespace(stop_reason="tool_use", content=[
                _Bloco(type="tool_use", id="t1", name=self.ferramenta, input=self.args)])
        resultado = mensagens[-1]["content"][0]["content"]
        return SimpleNamespace(stop_reason="end", content=[_Bloco(type="text", text=resultado)])


class ComandoTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self._p = [patch.object(config, "_CONFIG", {"assistant": {"langue": "pt"},
                                                     "financeiro": {"banco": self._t.name + "/f.db"}}),
                   patch.object(config, "FICHIER", Path(self._t.name) / "c.yaml")]
        for p in self._p:
            p.start()
        comando_remoto._HISTORICO_LIMITE.clear()
        registre.charger_outils()

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()
        self._t.cleanup()

    def test_chat_so_abre_por_voz(self):
        self.assertTrue(comando_remoto.processar("Jarvis, abre o chat")["chat"])
        self.assertFalse(comando_remoto.processar("pode fechar o chat")["chat"])
        self.assertNotIn("chat", comando_remoto.processar.__defaults__ or ())

    def test_n2_recusado_a_distancia_e_n1_executado(self):
        llm = _LLM("lancar_conta", {"tipo": "pagar", "descricao": "Luz", "valor": "10", "vencimento": "hoje"})
        with patch("core.llm.llm", return_value=llm):
            r = comando_remoto.processar("lança conta de luz", com_voz=False)
        self.assertNotIn("lancar_conta", llm.vistas)          # nem oferecida ao modelo
        self.assertIn("recusada a distância", r["resposta"])
        from core import financeiro
        self.assertEqual(financeiro.listar(), [])               # nada gravado
        n1 = next(o for o in registre.exposes_mcp())
        llm = _LLM(n1.nom, {})
        with patch("core.llm.llm", return_value=llm), patch.object(n1, "fonction", return_value="ok-n1"):
            r = comando_remoto.processar("faz algo seguro", com_voz=False)
        self.assertEqual(r["acoes"], [n1.nom])

    def test_n3_sempre_recusado(self):
        llm = _LLM("envoyer_mail", {})
        with patch("core.llm.llm", return_value=llm):
            r = comando_remoto.processar("envia o email", com_voz=False)
        self.assertIn("recusada a distância", r["resposta"])

    def test_voz_transcreve_e_limita(self):
        audio = base64.b64encode(b"\0" * 5000).decode()
        modelo = MagicMock()
        modelo.transcribe.return_value = ([SimpleNamespace(text=" abre o chat ")], None)
        with patch("core.satellite._whisper", return_value=modelo):
            r = comando_remoto.comando_voz(audio, "audio/webm")
        self.assertTrue(r["chat"])
        self.assertEqual(modelo.transcribe.call_args.kwargs["language"], "pt")
        self.assertFalse(comando_remoto.comando_voz("!!", "audio/webm")["ok"])
        self.assertFalse(comando_remoto.comando_voz(base64.b64encode(b"x").decode())["ok"])
        comando_remoto._HISTORICO_LIMITE[:] = [__import__("time").time()] * comando_remoto.LIMITE_POR_MINUTO
        self.assertIn("aguarde", comando_remoto.comando_texto("oi")["resposta"])

    def test_alucinacao_do_whisper_ignorada(self):
        modelo = MagicMock()
        modelo.transcribe.return_value = ([SimpleNamespace(text="Legendas pela comunidade Amara.org")], None)
        with patch("core.satellite._whisper", return_value=modelo):
            r = comando_remoto.comando_voz(base64.b64encode(b"\0" * 5000).decode())
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()

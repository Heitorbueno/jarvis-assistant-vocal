"""Comandos de voz (e chat oculto) pelo painel/PWA — celular ou outro computador.

Fluxo : o navegador grava a fala (MediaRecorder) -> Whisper transcreve no PC ->
« abre/fecha o chat » é tratado aqui ; o resto vai para ``pont_iphone.traiter_commande``,
que só executa ferramentas seguras a distância (N1 expostas + domotique_distante
configurada ; N2/N3 recusadas : « faça pela voz em casa »). A resposta volta em
texto e, se houver voz configurada, em áudio WAV para tocar no aparelho.

O chat de texto do PWA fica OCULTO : só abre quando o usuário diz « abre o chat ».
"""
import base64
import io
import logging
import os
import re
import sys
import tempfile
import threading
import time
import wave

LOG = logging.getLogger("jarvis.comando_remoto")
MAX_AUDIO = 6 * 1024 * 1024
_VERROU = threading.Lock()
_HISTORICO_LIMITE = []          # horários das últimas chamadas (limite por minuto)
LIMITE_POR_MINUTO = 20
_EXT = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3",
        "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/aac": ".aac"}

_ABRIR = re.compile(r"\b(abr[ea]|abrir|mostr[ae]|mostrar|exib[ae]|ouvre|affiche)\b.{0,20}\bchat\b", re.I)
_FECHAR = re.compile(r"\b(fech[ae]|fechar|escond[ae]|esconder|ocult[ae]|ferme|cache|masque)\b.{0,20}\bchat\b", re.I)


def _limite_ok():
    agora = time.time()
    with _VERROU:
        _HISTORICO_LIMITE[:] = [t for t in _HISTORICO_LIMITE if agora - t < 60]
        if len(_HISTORICO_LIMITE) >= LIMITE_POR_MINUTO:
            return False
        _HISTORICO_LIMITE.append(agora)
        return True


def _hud(acao, *args):
    h = sys.modules.get("hud")
    if h is not None:
        try:
            getattr(h, acao)(*args)
        except Exception:
            pass


def transcrever(audio: bytes, mime: str = "audio/webm") -> str:
    from core import langue
    from core.hallucinations import est_hallucination
    from core.satellite import _whisper
    modelo = _whisper()
    if modelo is None:
        raise RuntimeError("transcrição indisponível neste computador")
    sufixo = _EXT.get(str(mime or "").split(";")[0].strip().lower(), ".webm")
    fd, caminho = tempfile.mkstemp(suffix=sufixo, prefix="jarvis-voz-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        segmentos, _ = modelo.transcribe(caminho, language=langue.whisper(), beam_size=5,
                                         vad_filter=True)
        texto = " ".join(s.text for s in segmentos).strip()
    finally:
        try:
            os.unlink(caminho)
        except OSError:
            pass
    return "" if est_hallucination(texto) else texto


def sintetizar(texto: str):
    """Fala da resposta em WAV base64 (ou None se não houver voz disponível)."""
    if not texto:
        return None
    try:
        from core import langue
        from core.tts import tts
        res = tts().synthetiser(langue.localiser(texto))
        if not res:
            return None
        import numpy as np
        audio, freq = res
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(freq))
            w.writeframes(np.asarray(audio, dtype=np.int16).tobytes())
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        LOG.info("voz da resposta remota indisponível", exc_info=True)
        return None


def processar(texto: str, com_voz: bool = True) -> dict:
    from core import langue
    texto = " ".join(str(texto or "").split())[:500]
    if not texto:
        return {"ok": False, "resposta": "Não entendi." if langue.est_pt() else "Je n'ai pas compris."}
    if _FECHAR.search(texto):
        resp = "Chat fechado." if langue.est_pt() else "Chat ferme."
        return {"ok": True, "texto": texto, "resposta": resp, "chat": False}
    if _ABRIR.search(texto):
        resp = "Chat aberto." if langue.est_pt() else "Chat ouvert."
        return {"ok": True, "texto": texto, "resposta": resp, "chat": True}
    from core.pont_iphone import traiter_commande
    _hud("dire_vous", texto)
    r = traiter_commande(texto)
    resposta = langue.localiser(str(r.get("reponse", "")))
    _hud("dire_jarvis", resposta)
    saida = {"ok": bool(r.get("ok")), "texto": texto, "resposta": resposta,
             "acoes": list(r.get("faits", []))}
    if com_voz:
        saida["audio"] = sintetizar(resposta)
    return saida


def comando_voz(audio_b64: str, mime: str = "audio/webm", com_voz: bool = True) -> dict:
    from core import langue
    if not _limite_ok():
        return {"ok": False, "resposta": "Muitos comandos seguidos; aguarde um instante."}
    try:
        audio = base64.b64decode(str(audio_b64 or ""), validate=True)
    except Exception:
        return {"ok": False, "resposta": "Áudio inválido."}
    if not 1000 <= len(audio) <= MAX_AUDIO:
        return {"ok": False, "resposta": "Áudio muito curto ou longo demais."}
    try:
        texto = transcrever(audio, mime)
    except Exception as e:
        LOG.warning("transcrição remota: %s", e)
        return {"ok": False, "resposta": f"Não consegui transcrever ({type(e).__name__})."}
    if not texto:
        return {"ok": False, "resposta": "Não entendi, pode repetir?" if langue.est_pt()
                else "Je n'ai pas compris, tu peux repeter ?"}
    return processar(texto, com_voz)


def comando_texto(texto: str) -> dict:
    if not _limite_ok():
        return {"ok": False, "resposta": "Muitos comandos seguidos; aguarde um instante."}
    return processar(texto, com_voz=False)

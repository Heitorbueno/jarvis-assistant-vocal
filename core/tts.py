"""Abstraction de la synthese vocale (TTS) : cloud ou local, meme interface.

Chaque provider expose `synthetiser(texte)` qui renvoie (audio_int16, frequence)
ou None. jarvis14 se charge de JOUER l'audio (avec sa gestion d'interruption) et
retombe sur la voix Windows (SAPI) si le provider renvoie None.

  - ElevenLabsProvider : cloud (qualite max), voix configurable.
  - PiperProvider      : local, 100% offline, voix francaise Piper (.onnx).

Choix par config.yaml (`tts.moteur`) et par le mode local/hybride/qualite. En
local sans modele Piper, ou en cloud sans cle ElevenLabs, on retombe proprement
sur SAPI.

Note honnete sur le TTS local francais : Piper est recommande (voix FR eprouvees
comme fr_FR-siwis / fr_FR-tom, tres leger, temps reel sur CPU). Kokoro (kokoro-onnx)
ne propose qu'une voix FR recente et de qualite moyenne ; Piper est un meilleur
choix pour le francais aujourd'hui.
"""
import json
import logging
import urllib.request
from pathlib import Path

# Magasin de certificats Windows (Malwarebytes intercepte le TLS : sans ca, l'appel
# a l'API ElevenLabs echoue et Jarvis retombe sur la voix Windows).
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from core.config import reglage

LOG = logging.getLogger("jarvis")
_RACINE = Path(__file__).resolve().parent.parent

# Ultimo resultado da sintese (mostrado no painel) : qual motor falou e por que caiu.
ESTADO = {"motor": "", "ok": None, "erro": "", "ts": 0.0}


def _registrar(motor, ok, erro=""):
    import time
    ESTADO.update(motor=motor, ok=bool(ok), erro=str(erro or "")[:300], ts=time.time())


def diagnostico_chave_eleven():
    """'' se a chave parece valida ; senao a explicacao (ID da chave em vez da chave)."""
    cle = str(reglage("elevenlabs.cle", "") or "").strip()
    if not cle:
        return "Nenhuma chave da ElevenLabs salva."
    if not cle.startswith("sk_"):
        return ("A chave salva é o ID da chave, não a chave. Na ElevenLabs, crie ou rotacione "
                "a chave e cole o valor que começa com sk_ (painel › ElevenLabs).")
    return ""


class ProviderTTS:
    nom = "?"

    def disponible(self):
        return True

    def synthetiser(self, texte):
        """Renvoie (numpy int16 mono, frequence_hz) ou None si indisponible."""
        return None


class WindowsProvider(ProviderTTS):
    """Demande volontairement le repli SAPI gere par jarvis14.dire()."""
    nom = "Windows"


# --------------------------------------------------------------- ElevenLabs

class ElevenLabsProvider(ProviderTTS):
    nom = "ElevenLabs"

    def __init__(self):
        self.cle = reglage("elevenlabs.cle", "")
        self.voix = reglage("elevenlabs.voix", "")
        self.modele = reglage("elevenlabs.modele", "eleven_flash_v2_5")
        self._voix_resolue = None

    def disponible(self):
        return bool(self.cle)

    def _resoudre_voix(self):
        if self.voix:
            return self.voix
        if self._voix_resolue:
            return self._voix_resolue
        try:
            requete = urllib.request.Request(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": self.cle})
            with urllib.request.urlopen(requete, timeout=6) as reponse:
                d = json.loads(reponse.read().decode("utf-8"))
            self._voix_resolue = d["voices"][0]["voice_id"]
        except Exception:
            self._voix_resolue = "21m00Tcm4TlvDq8ikWAM"   # Rachel, par defaut
        return self._voix_resolue

    def synthetiser(self, texte):
        try:
            import numpy as np
        except ImportError:
            return None
        try:
            import miniaudio
        except ImportError:
            # miniaudio n'existe pas partout (Windows ARM64) : on demande alors du PCM
            # brut 24 kHz a ElevenLabs, qui n'a pas besoin d'etre decode.
            miniaudio = None
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._resoudre_voix()}"
        if miniaudio is None:
            url += "?output_format=pcm_24000"
        charge = {"text": texte, "model_id": self.modele}
        # Flash/Turbo v2.5 acceptent language_code : on force le francais pour une
        # bonne prononciation des accents (e accent, c cedille...) quelle que soit
        # la voix (sinon la langue est auto-detectee et parfois lue en anglais).
        if any(x in self.modele for x in ("flash", "turbo")):
            from core import langue
            charge["language_code"] = langue.elevenlabs()
        # Réglages fins (panneau) : envoyés uniquement s'ils sont définis.
        try:
            from core.voix_gestion import voice_settings_eleven
            reglages_voix = voice_settings_eleven()
        except Exception:
            reglages_voix = None
        if reglages_voix:
            charge["voice_settings"] = reglages_voix
        corps = json.dumps(charge).encode("utf-8")
        requete = urllib.request.Request(url, data=corps, method="POST", headers={
            "xi-api-key": self.cle, "Content-Type": "application/json",
            "Accept": "audio/mpeg" if miniaudio is not None else "audio/pcm"})
        try:
            with urllib.request.urlopen(requete, timeout=15) as reponse:
                donnees = reponse.read()
            if miniaudio is not None:
                donnees = miniaudio.decode(
                    donnees, nchannels=1, sample_rate=24000,
                    output_format=miniaudio.SampleFormat.SIGNED16).samples
            else:
                donnees = donnees[:len(donnees) - len(donnees) % 2]
            try:                                  # N12 : comptabilite voix (au caractere)
                from core import budget
                budget.enregistrer_tts(len(texte or ""))
            except Exception:
                pass
            _registrar("ElevenLabs", True)
            return np.frombuffer(donnees, dtype=np.int16), 24000
        except Exception as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "ignore")[:300]   # HTTPError : cause precise
            except Exception:
                pass
            if "api_key_id_used_as_api_key" in detail or "invalid_api_key" in detail:
                motivo = diagnostico_chave_eleven() or "Chave da ElevenLabs recusada."
            elif "quota_exceeded" in detail:
                motivo = "Créditos da ElevenLabs esgotados neste mês."
            elif "voice_not_found" in detail:
                motivo = "A voz escolhida não existe nesta conta. Escolha outra no painel."
            else:
                motivo = f"ElevenLabs indisponível ({type(e).__name__}) {detail[:160]}"
            print(f"  [ElevenLabs] {motivo} Repli voix Windows.")
            LOG.warning("ElevenLabs : %s", motivo)
            _registrar("Windows (fallback)", False, motivo)
            return None


# --------------------------------------------------------------- Piper (local)

class PiperProvider(ProviderTTS):
    nom = "Piper"

    def __init__(self):
        self.modele = reglage("piper.modele", "")
        self._voix = None

    def _chemin(self):
        if not self.modele:
            # a defaut, prend le premier .onnx de voix/, en preferant la langue
            # configuree (assistant.langue : fr_FR..., pt_BR...).
            from core import langue
            trouves = sorted((_RACINE / "voix").glob("*.onnx"))
            for prefixe in langue.prefixes_piper():
                for t in trouves:
                    if t.name.startswith(prefixe):
                        return t
            return trouves[0] if trouves else None
        p = Path(self.modele)
        return p if p.is_absolute() else (_RACINE / p)

    def disponible(self):
        c = self._chemin()
        return bool(c and c.exists())

    def synthetiser(self, texte):
        try:
            import numpy as np
            from piper import PiperVoice
        except ImportError:
            print("  [Piper] librairie piper-tts absente.")
            return None
        chemin = self._chemin()
        if chemin is None or not chemin.exists():
            print("  [Piper] aucun modele de voix (.onnx) dans voix/. Voir docs.")
            return None
        try:
            if self._voix is None:
                self._voix = PiperVoice.load(str(chemin))

            # Ancienne API (piper-tts <= 1.2.x) : synthesize_stream_raw() -> PCM brut.
            try:
                from core.voix_gestion import params_piper
                params = params_piper()
            except Exception:
                params = {}
            if hasattr(self._voix, "synthesize_stream_raw"):
                brut = b"".join(self._voix.synthesize_stream_raw(texte, **params))
                return np.frombuffer(brut, dtype=np.int16), self._voix.config.sample_rate

            # Nouvelle API (piper-tts >= 1.3.0, réécriture OHF-Voice/piper1-gpl) :
            # synthesize() renvoie des AudioChunk (int16 + sample_rate). C'est le
            # cas de la version par défaut de requirements.txt (issue NOVON82).
            morceaux, freq = [], None
            options = {}
            if params:
                try:
                    from piper import SynthesisConfig
                    options["syn_config"] = SynthesisConfig(
                        length_scale=params.get("length_scale"),
                        noise_scale=params.get("noise_scale"),
                        noise_w_scale=params.get("noise_w"))
                except Exception:
                    options = {}
            for chunk in self._voix.synthesize(texte, **options):
                octets = getattr(chunk, "audio_int16_bytes", None)
                if octets is None:                       # repli : tableau float
                    arr = getattr(chunk, "audio_float_array", None)
                    if arr is not None:
                        octets = (np.asarray(arr) * 32767).astype(np.int16).tobytes()
                if octets:
                    morceaux.append(octets)
                if freq is None:
                    freq = getattr(chunk, "sample_rate", None)
            brut = b"".join(morceaux)
            if not brut:
                return None
            if not freq:
                freq = getattr(getattr(self._voix, "config", None), "sample_rate", 22050)
            return np.frombuffer(brut, dtype=np.int16), freq
        except Exception as e:
            print(f"  [Piper] echec ({e}), repli voix Windows.")
            return None


# --------------------------------------------------------------- Kokoro (local)

class KokoroProvider(ProviderTTS):
    nom = "Kokoro"

    def __init__(self):
        self.modele = reglage("kokoro.modele", "")
        self.voix = reglage("kokoro.voix", "")
        from core import langue
        self.voix_nom = langue.kokoro_voix(reglage("kokoro.voix_nom", ""))
        self.lang = langue.kokoro()
        from core.voix_gestion import vitesse_kokoro
        self.vitesse = vitesse_kokoro()
        self._k = None

    def disponible(self):
        return bool(self.modele and Path(self.modele).exists())

    def synthetiser(self, texte):
        try:
            import numpy as np
            from kokoro_onnx import Kokoro
        except ImportError:
            print("  [Kokoro] librairie absente. Installe : uv add kokoro-onnx")
            return None
        if not (self.modele and Path(self.modele).exists()):
            print("  [Kokoro] modele introuvable (kokoro.modele). Voir docs/local.md.")
            return None
        try:
            if self._k is None:
                self._k = Kokoro(self.modele, self.voix)
            samples, freq = self._k.create(texte, voice=self.voix_nom, speed=self.vitesse, lang=self.lang)
            audio = (np.asarray(samples) * 32767).astype(np.int16)
            return audio, freq
        except Exception as e:
            print(f"  [Kokoro] echec ({e}), repli voix Windows.")
            return None


# --------------------------------------------------------------- fabrique

_TTS = None


def tts():
    """Provider TTS courant.

    ``tts.moteur`` peut valoir auto/elevenlabs/piper/kokoro/windows. Le mode
    local garde sa promesse de confidentialite : ElevenLabs y est ignore et un
    moteur local est choisi.
    """
    global _TTS
    if _TTS is None:
        from core.routage import mode_actuel
        m = mode_actuel()
        moteur = (reglage("tts.moteur", "auto") or "auto").lower()
        if m == "local":
            if moteur in {"auto", "elevenlabs"}:
                moteur = (reglage("voix_locale", "piper") or "piper").lower()
        else:
            if moteur == "auto":
                moteur = "elevenlabs"
        if moteur == "elevenlabs" and diagnostico_chave_eleven():
            # Chave ausente ou ID da chave : a API recusaria TODAS as frases (atraso + voz
            # robotica). Usa a voz local Piper se houver, senao a do Windows, e avisa no painel.
            motivo = diagnostico_chave_eleven()
            piper = PiperProvider()
            _TTS = piper if piper.disponible() else WindowsProvider()
            _registrar(f"{_TTS.nom} (ElevenLabs desativado)", False, motivo)
            LOG.warning("ElevenLabs ignore : %s", motivo)
        elif moteur == "elevenlabs":
            _TTS = ElevenLabsProvider()
        elif moteur == "kokoro":
            _TTS = KokoroProvider()
        elif moteur == "piper":
            _TTS = PiperProvider()
        else:
            _TTS = WindowsProvider()
        LOG.info("provider TTS : %s (mode %s)", _TTS.nom, m)
    return _TTS


def reinitialiser():
    """Force la reconstruction du provider TTS au prochain tts() (switch de mode)."""
    global _TTS
    _TTS = None

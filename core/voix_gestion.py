"""Voix gérées depuis le panneau : clonage ElevenLabs, réglages fins, voix Piper.

- Réglages ElevenLabs (stabilité, similarité, style, vitesse, boost) : envoyés
  dans ``voice_settings`` seulement s'ils sont définis (sinon comportement d'origine).
- Clonage instantané ElevenLabs : échantillons audio envoyés à /v1/voices/add ;
  la voix créée reste sur le compte et peut devenir la voix de Jarvis.
- Voix locales Piper : liste du dossier voix/, téléchargement depuis le dépôt
  officiel rhasspy/piper-voices, import d'un modèle .onnx + .onnx.json, et
  réglages vitesse / variation. Kokoro : vitesse.
"""
import base64
import logging
import re
from pathlib import Path

from core.config import definir, reglage

LOG = logging.getLogger("jarvis.voix")
_RACINE = Path(__file__).resolve().parent.parent
DOSSIER_VOIX = _RACINE / "voix"
_ELEVEN = "https://api.elevenlabs.io/v1"
_HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

MAX_ECHANTILLONS_OCTETS = 25 * 1024 * 1024
MAX_PIPER_OCTETS = 150 * 1024 * 1024
_NOM_VOIX_PIPER = re.compile(r"^[A-Za-z]{2}_[A-Za-z]{2}-[A-Za-z0-9_]+-(x_low|low|medium|high)$")
_EXT_AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac", ".aac"}

CATALOGUE_PIPER = [
    {"nom": "pt_BR-faber-medium", "langue": "pt", "note": "masculina, natural"},
    {"nom": "pt_BR-cadu-medium", "langue": "pt", "note": "masculina"},
    {"nom": "pt_BR-jeff-medium", "langue": "pt", "note": "masculina"},
    {"nom": "fr_FR-siwis-medium", "langue": "fr", "note": "féminine, recommandée"},
    {"nom": "fr_FR-tom-medium", "langue": "fr", "note": "masculine"},
    {"nom": "fr_FR-upmc-medium", "langue": "fr", "note": "deux locuteurs"},
]

# Réglages : clé config -> (min, max)
REGLAGES_ELEVEN = {
    "elevenlabs.stabilite": (0.0, 1.0), "elevenlabs.similarite": (0.0, 1.0),
    "elevenlabs.style": (0.0, 1.0), "elevenlabs.vitesse": (0.7, 1.2),
}
REGLAGES_LOCAUX = {
    "piper.vitesse": (0.5, 2.0), "piper.variation": (0.0, 1.5),
    "piper.variation_duree": (0.0, 1.5), "kokoro.vitesse": (0.5, 2.0),
}


def _reinit():
    try:
        from core import tts
        tts.reinitialiser()
    except Exception:
        LOG.debug("reinit tts", exc_info=True)


# ============================================================ réglages

def reglages():
    out = {}
    for cle in list(REGLAGES_ELEVEN) + list(REGLAGES_LOCAUX):
        out[cle] = reglage(cle, None)
    out["elevenlabs.boost"] = reglage("elevenlabs.boost", None)
    return out


def definir_reglages(valeurs: dict) -> dict:
    if not isinstance(valeurs, dict) or not valeurs:
        return {"ok": False, "message": "Nada para salvar."}
    bornes = {**REGLAGES_ELEVEN, **REGLAGES_LOCAUX}
    for cle, v in valeurs.items():
        if cle == "elevenlabs.boost":
            definir(cle, None if v is None else bool(v))
            continue
        if cle not in bornes:
            return {"ok": False, "message": f"Ajuste desconhecido: {cle}"}
        if v is None or v == "":
            definir(cle, None)
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            return {"ok": False, "message": f"Valor inválido para {cle}."}
        lo, hi = bornes[cle]
        if not lo <= f <= hi:
            return {"ok": False, "message": f"{cle} deve ficar entre {lo} e {hi}."}
        definir(cle, round(f, 3))
    _reinit()
    return {"ok": True, "message": "Ajustes de voz salvos; valem na próxima frase."}


def voice_settings_eleven():
    """Dict voice_settings pour l'API, ou None si rien n'est configuré (défaut d'origine)."""
    correspondance = {"elevenlabs.stabilite": "stability",
                      "elevenlabs.similarite": "similarity_boost",
                      "elevenlabs.style": "style", "elevenlabs.vitesse": "speed"}
    vs = {}
    for cle, nom in correspondance.items():
        v = reglage(cle, None)
        if v is not None:
            try:
                vs[nom] = float(v)
            except (TypeError, ValueError):
                continue
    boost = reglage("elevenlabs.boost", None)
    if boost is not None:
        vs["use_speaker_boost"] = bool(boost)
    if not vs:
        return None
    vs.setdefault("stability", 0.5)
    vs.setdefault("similarity_boost", 0.75)
    return vs


def params_piper():
    """kwargs de synthèse Piper (vide = valeurs du modèle)."""
    out = {}
    vitesse = reglage("piper.vitesse", None)
    if vitesse:
        out["length_scale"] = round(1.0 / float(vitesse), 3)   # plus rapide = plus court
    if reglage("piper.variation", None) is not None:
        out["noise_scale"] = float(reglage("piper.variation"))
    if reglage("piper.variation_duree", None) is not None:
        out["noise_w"] = float(reglage("piper.variation_duree"))
    return out


def vitesse_kokoro():
    try:
        return float(reglage("kokoro.vitesse", 1.0) or 1.0)
    except (TypeError, ValueError):
        return 1.0


# ============================================================ clonage ElevenLabs

def _decoder(b64):
    if not isinstance(b64, str):
        raise ValueError("contenu manquant")
    if "," in b64[:100] and b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    return base64.b64decode(b64, validate=True)


def cloner_elevenlabs(nom, fichiers, description="", utiliser=True, retirer_bruit=False):
    cle = str(reglage("elevenlabs.cle", "") or "").strip()
    if not cle:
        return {"ok": False, "message": "Salve a chave da ElevenLabs antes de clonar."}
    nom = " ".join(str(nom or "").split())[:60]
    if not nom:
        return {"ok": False, "message": "Dê um nome para a voz."}
    if not isinstance(fichiers, list) or not 1 <= len(fichiers) <= 25:
        return {"ok": False, "message": "Envie de 1 a 25 amostras de áudio."}
    pieces, total = [], 0
    for i, f in enumerate(fichiers):
        nom_f = Path(str((f or {}).get("nome", f"amostra{i}.mp3"))).name[:80]
        ext = Path(nom_f).suffix.lower()
        if ext not in _EXT_AUDIO:
            return {"ok": False, "message": f"Formato não suportado: {nom_f}"}
        try:
            donnees = _decoder((f or {}).get("dados"))
        except Exception:
            return {"ok": False, "message": f"Arquivo inválido: {nom_f}"}
        total += len(donnees)
        if total > MAX_ECHANTILLONS_OCTETS:
            return {"ok": False, "message": "Amostras acima de 25 MB no total."}
        pieces.append(("files", (nom_f, donnees, "application/octet-stream")))
    import requests
    data = {"name": nom, "remove_background_noise": "true" if retirer_bruit else "false"}
    if description:
        data["description"] = str(description)[:300]
    try:
        r = requests.post(f"{_ELEVEN}/voices/add", headers={"xi-api-key": cle},
                          data=data, files=pieces, timeout=120)
    except Exception as e:
        return {"ok": False, "message": f"ElevenLabs inacessível ({type(e).__name__})."}
    if r.status_code != 200:
        from core.provedores import _erreur_http
        try:
            status = str(((r.json() or {}).get("detail") or {}).get("status", ""))
        except Exception:
            status = ""
        explicacoes = {
            "api_key_id_used_as_api_key": "A chave salva é o ID da chave. Cole a chave que começa com sk_.",
            "invalid_api_key": "Chave da ElevenLabs inválida.",
            "can_not_use_instant_voice_cloning": "Seu plano da ElevenLabs não permite clonar voz "
                                                 "(precisa do plano Starter ou superior).",
            "missing_permissions": "A chave não tem permissão « Voices: write ». Crie uma chave com "
                                   "essa permissão na ElevenLabs.",
            "voice_limit_reached": "Limite de vozes da sua conta atingido. Apague uma voz na ElevenLabs.",
        }
        return {"ok": False, "message": explicacoes.get(status) or _erreur_http(r)}
    voix_id = str((r.json() or {}).get("voice_id", ""))
    if not voix_id:
        return {"ok": False, "message": "A ElevenLabs não devolveu o ID da voz."}
    if utiliser:
        definir("elevenlabs.voix", voix_id)
        _reinit()
    try:
        from core import panneau
        panneau._ELEVENLABS_CACHE.update(ts=0.0, voix=[], erreur="")
    except Exception:
        pass
    return {"ok": True, "voz_id": voix_id,
            "message": f"Voz « {nom} » clonada" + (" e ativada." if utiliser else ".")}


# ============================================================ voix Piper

def voix_locales():
    DOSSIER_VOIX.mkdir(exist_ok=True)
    actif = str(reglage("piper.modele", "") or "")
    out = []
    for p in sorted(DOSSIER_VOIX.glob("*.onnx")):
        rel = f"voix/{p.name}"
        out.append({"nom": p.stem, "chemin": rel,
                    "config_ok": p.with_suffix(".onnx.json").exists(),
                    "taille_mo": round(p.stat().st_size / 1e6, 1),
                    "active": actif in {rel, str(p)}})
    noms = {v["nom"] for v in out}
    from core import langue
    return {"voix": out, "actif": actif, "langue": langue.code(),
            "catalogue": [{**c, "installe": c["nom"] in noms} for c in CATALOGUE_PIPER],
            "moteur": str(reglage("tts.moteur", "auto") or "auto"),
            "voix_locale": str(reglage("voix_locale", "piper") or "piper")}


def _url_piper(nom):
    langue_region, locuteur, qualite = nom.split("-", 2)
    famille = langue_region.split("_")[0]
    base = f"{_HF}/{famille}/{langue_region}/{locuteur}/{qualite}/{nom}"
    return f"{base}.onnx", f"{base}.onnx.json"


def telecharger_piper(nom):
    nom = str(nom or "").strip()
    if not _NOM_VOIX_PIPER.match(nom):
        return {"ok": False, "message": "Nome de voz Piper inválido."}
    import requests
    DOSSIER_VOIX.mkdir(exist_ok=True)
    try:
        for url in _url_piper(nom):
            dest = DOSSIER_VOIX / url.rsplit("/", 1)[1]
            tmp = dest.with_suffix(dest.suffix + ".part")
            with requests.get(url, stream=True, timeout=60) as r:
                if r.status_code != 200:
                    return {"ok": False, "message": f"Voz não encontrada no repositório (HTTP {r.status_code})."}
                total = 0
                with open(tmp, "wb") as f:
                    for bloc in r.iter_content(1 << 20):
                        total += len(bloc)
                        if total > MAX_PIPER_OCTETS:
                            tmp.unlink(missing_ok=True)
                            return {"ok": False, "message": "Arquivo grande demais."}
                        f.write(bloc)
            tmp.replace(dest)
    except Exception as e:
        return {"ok": False, "message": f"Falha no download ({type(e).__name__})."}
    return {"ok": True, "message": f"Voz {nom} baixada."}


def importer_piper(nom, onnx_b64, json_b64):
    nom = str(nom or "").strip()
    if nom.endswith(".onnx"):
        nom = nom[:-5]
    if not re.match(r"^[A-Za-z0-9_.-]{3,80}$", nom) or ".." in nom:
        return {"ok": False, "message": "Nome de arquivo inválido."}
    try:
        modele = _decoder(onnx_b64)
        config = _decoder(json_b64)
    except Exception:
        return {"ok": False, "message": "Envie o .onnx e o .onnx.json da voz."}
    if len(modele) > MAX_PIPER_OCTETS or len(modele) < 1024:
        return {"ok": False, "message": "Modelo .onnx com tamanho inválido."}
    try:
        import json
        json.loads(config.decode("utf-8"))
    except Exception:
        return {"ok": False, "message": "O .onnx.json não é um JSON válido."}
    DOSSIER_VOIX.mkdir(exist_ok=True)
    (DOSSIER_VOIX / f"{nom}.onnx").write_bytes(modele)
    (DOSSIER_VOIX / f"{nom}.onnx.json").write_bytes(config)
    return {"ok": True, "message": f"Voz {nom} importada."}


def choisir_piper(nom, activer_moteur=False):
    nom = str(nom or "").strip()
    chemin = DOSSIER_VOIX / f"{nom}.onnx"
    if not re.match(r"^[A-Za-z0-9_.-]{3,80}$", nom) or ".." in nom or not chemin.is_file():
        return {"ok": False, "message": "Voz local não encontrada."}
    definir("piper.modele", f"voix/{nom}.onnx")
    if activer_moteur:
        definir("tts.moteur", "piper")
        definir("voix_locale", "piper")
    _reinit()
    return {"ok": True, "message": f"Voz local {nom} selecionada."}


def supprimer_piper(nom):
    nom = str(nom or "").strip()
    if not re.match(r"^[A-Za-z0-9_.-]{3,80}$", nom) or ".." in nom:
        return {"ok": False, "message": "Nome inválido."}
    supprime = False
    for suffixe in (".onnx", ".onnx.json"):
        p = DOSSIER_VOIX / f"{nom}{suffixe}"
        if p.is_file() and p.resolve().parent == DOSSIER_VOIX.resolve():
            p.unlink()
            supprime = True
    if str(reglage("piper.modele", "") or "") == f"voix/{nom}.onnx":
        definir("piper.modele", "")
    _reinit()
    return {"ok": supprime, "message": f"Voz {nom} removida." if supprime else "Nada a remover."}

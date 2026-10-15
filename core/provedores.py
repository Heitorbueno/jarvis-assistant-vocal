"""Fournisseurs d'IA et ElevenLabs gérés depuis le panneau.

- Les clés sont ÉCRITES dans config.yaml depuis le panneau, mais ne sont JAMAIS
  renvoyées au navigateur : seules leurs 4 dernières lettres sont affichées.
- « Tester la connexion » interroge l'endpoint de liste des modèles du fournisseur
  (requête en lecture seule, sans coût) et renvoie la liste des modèles.
- Le modèle choisi est rangé dans ``<section>.modele``. OpenAI, Anthropic et
  Ollama peuvent piloter le cerveau de Jarvis (core.cloud / core.llm) ; les autres
  fournisseurs sont stockés pour les connecteurs optionnels (voir CLAUDE.md).
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlsplit

from core.config import definir, reglage

LOG = logging.getLogger("jarvis.provedores")

TIMEOUT = 12

# id -> description. « cerveau » : peut devenir le LLM actif de Jarvis.
PROVEDORES = {
    "openai": {"nom": "OpenAI", "section": "openai", "cerveau": True,
               "url_modeles": "https://api.openai.com/v1/models", "auth": "bearer",
               "lien": "https://platform.openai.com/api-keys"},
    "anthropic": {"nom": "Anthropic (Claude)", "section": "anthropic", "cerveau": True,
                  "url_modeles": "https://api.anthropic.com/v1/models?limit=1000",
                  "auth": "anthropic", "lien": "https://console.anthropic.com/settings/keys"},
    "gemini": {"nom": "Google Gemini", "section": "gemini", "cerveau": False,
               "url_modeles": "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
               "auth": "google", "lien": "https://aistudio.google.com/apikey"},
    "openrouter": {"nom": "OpenRouter", "section": "openrouter", "cerveau": False,
                   "url_modeles": "https://openrouter.ai/api/v1/models",
                   "url_test": "https://openrouter.ai/api/v1/key",
                   "auth": "bearer", "lien": "https://openrouter.ai/keys"},
    "groq": {"nom": "Groq", "section": "groq", "cerveau": False,
             "url_modeles": "https://api.groq.com/openai/v1/models", "auth": "bearer",
             "lien": "https://console.groq.com/keys"},
    "deepseek": {"nom": "DeepSeek", "section": "deepseek", "cerveau": False,
                 "url_modeles": "https://api.deepseek.com/models", "auth": "bearer",
                 "lien": "https://platform.deepseek.com/api_keys"},
    "mistral": {"nom": "Mistral AI", "section": "mistral", "cerveau": False,
                "url_modeles": "https://api.mistral.ai/v1/models", "auth": "bearer",
                "lien": "https://console.mistral.ai/api-keys"},
    "xai": {"nom": "xAI (Grok)", "section": "xai", "cerveau": False,
            "url_modeles": "https://api.x.ai/v1/models", "auth": "bearer",
            "lien": "https://console.x.ai"},
    "ollama": {"nom": "Ollama (local)", "section": "ollama", "cerveau": True,
               "auth": "aucune", "lien": "https://ollama.com/download"},
}

_CLE_VALIDE = re.compile(r"^[A-Za-z0-9_\-.:=+/]{8,400}$")
_CACHE_MODELES: dict[str, dict] = {}


# ============================================================ utilitaires

def _cle(pid: str) -> str:
    return str(reglage(f"{PROVEDORES[pid]['section']}.cle", "") or "").strip()


def masquer(cle: str) -> str:
    cle = str(cle or "")
    return f"••••{cle[-4:]}" if len(cle) >= 8 else ("••••" if cle else "")


def cle_valide(cle) -> bool:
    return bool(_CLE_VALIDE.match(str(cle or "")))


def _ollama_hote() -> str:
    return str(reglage("ollama.hote", "http://localhost:11434") or "").rstrip("/")


def hote_ollama_valide(valeur) -> bool:
    try:
        m = urlsplit(str(valeur or "").strip())
    except ValueError:
        return False
    return m.scheme in {"http", "https"} and bool(m.hostname) and not m.username \
        and not m.password and not m.query and not m.fragment


def _entetes(pid: str, cle: str) -> dict:
    auth = PROVEDORES[pid]["auth"]
    if auth == "bearer":
        return {"Authorization": f"Bearer {cle}"}
    if auth == "anthropic":
        return {"x-api-key": cle, "anthropic-version": "2023-06-01"}
    if auth == "google":
        return {"x-goog-api-key": cle}
    return {}


def _modele_actif(pid: str) -> str:
    section = PROVEDORES[pid]["section"]
    return str(reglage(f"{section}.modele", "") or "")


def _erreur_http(r) -> str:
    """Message d'erreur court, sans jamais refléter la clé envoyée."""
    message = ""
    try:
        data = r.json()
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            message = str(err.get("message") or err.get("type") or "")
        elif isinstance(err, str):
            message = err
        elif isinstance(data, dict):
            detail = data.get("detail")
            if isinstance(detail, dict):           # format ElevenLabs
                if detail.get("status") == "api_key_id_used_as_api_key":
                    return ("Essa é o ID da chave, não a chave. Na ElevenLabs, crie ou rotacione "
                            "a chave e copie o valor que começa com sk_.")
                message = str(detail.get("message") or detail.get("status") or "")
            else:
                message = str(data.get("message") or detail or "")
    except Exception:
        message = ""
    if r.status_code in (401, 403):
        prefixe = "Chave recusada pelo provedor"
    elif r.status_code == 429:
        prefixe = "Limite/crédito excedido"
    else:
        prefixe = f"HTTP {r.status_code}"
    return f"{prefixe}{' : ' + message[:140] if message else ''}"


def _ids(pid: str, data) -> list[str]:
    if pid == "gemini":
        ids = []
        for m in (data or {}).get("models", []):
            if "generateContent" in (m.get("supportedGenerationMethods") or []):
                ids.append(str(m.get("name", "")).removeprefix("models/"))
        return ids
    if pid == "ollama":
        return [str(m.get("name", "")) for m in (data or {}).get("models", [])]
    return [str(m.get("id", "")) for m in (data or {}).get("data", [])]


# ============================================================ API

def lister() -> dict:
    """Etat de tous les fournisseurs, sans aucune clé en clair."""
    from core import cloud
    try:
        from core.routage import mode_actuel
        mode = mode_actuel()
    except Exception:
        mode = ""
    actif = "ollama" if mode == "local" else cloud.fournisseur()
    out = []
    for pid, p in PROVEDORES.items():
        cle = _cle(pid) if pid != "ollama" else ""
        cache = _CACHE_MODELES.get(pid, {})
        out.append({
            "id": pid, "nom": p["nom"], "lien": p["lien"],
            "cerveau": p["cerveau"], "sans_cle": pid == "ollama",
            "configure": bool(cle) if pid != "ollama" else True,
            "cle_masquee": masquer(cle),
            "modele": _modele_actif(pid),
            "modele_qualite": str(reglage(f"{p['section']}.modele_qualite", "") or "")
            if pid in {"openai", "anthropic"} else "",
            "hote": _ollama_hote() if pid == "ollama" else "",
            "actif": pid == actif,
            "favoris": favoris(pid),
            "modeles": cache.get("modeles", []),
            "teste_a": cache.get("ts", 0),
        })
    from core import diagnostic_llm
    return {"provedores": out, "mode": mode, "repli": repli_etat(),
            "ultimo_erro": diagnostic_llm.dernier()}


def enregistrer_cle(pid: str, cle) -> dict:
    if pid not in PROVEDORES or pid == "ollama":
        return {"ok": False, "message": "Provedor desconhecido."}
    cle = str(cle or "").strip()
    if cle and not cle_valide(cle):
        return {"ok": False, "message": "Formato de chave inválido."}
    definir(f"{PROVEDORES[pid]['section']}.cle", cle)
    _CACHE_MODELES.pop(pid, None)
    _apres_changement(pid)
    return {"ok": True, "message": "Chave salva." if cle else "Chave removida.",
            "cle_masquee": masquer(cle)}


def enregistrer_hote_ollama(hote) -> dict:
    hote = str(hote or "").strip().rstrip("/")
    if not hote_ollama_valide(hote):
        return {"ok": False, "message": "Endereço inválido (ex.: http://localhost:11434)."}
    definir("ollama.hote", hote)
    _CACHE_MODELES.pop("ollama", None)
    return {"ok": True, "message": "Endereço do Ollama salvo."}


def tester(pid: str) -> dict:
    """Teste la connexion et renvoie la liste des modèles disponibles."""
    if pid not in PROVEDORES:
        return {"ok": False, "message": "Provedor desconhecido."}
    import requests
    p = PROVEDORES[pid]
    debut = time.time()
    try:
        if pid == "ollama":
            r = requests.get(f"{_ollama_hote()}/api/tags", timeout=TIMEOUT)
        else:
            cle = _cle(pid)
            if not cle:
                return {"ok": False, "message": "Salve a chave antes de testar."}
            entetes = _entetes(pid, cle)
            if p.get("url_test"):
                rt = requests.get(p["url_test"], headers=entetes, timeout=TIMEOUT)
                if rt.status_code != 200:
                    return {"ok": False, "message": _erreur_http(rt)}
            r = requests.get(p["url_modeles"], headers=entetes, timeout=TIMEOUT)
        if r.status_code != 200:
            return {"ok": False, "message": _erreur_http(r)}
        modeles = sorted({m for m in _ids(pid, r.json()) if m})
    except requests.exceptions.Timeout:
        return {"ok": False, "message": "Tempo esgotado ao contatar o provedor."}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "message": "Provedor inacessível (rede/DNS/serviço parado)."}
    except Exception as e:
        LOG.warning("test fournisseur %s: %s", pid, type(e).__name__)
        return {"ok": False, "message": f"Falha no teste : {type(e).__name__}"}
    _CACHE_MODELES[pid] = {"ts": time.time(), "modeles": modeles}
    ms = int((time.time() - debut) * 1000)
    return {"ok": True, "modeles": modeles,
            "message": f"Conexão OK ({len(modeles)} modelos, {ms} ms)."}


def choisir_modele(pid: str, modele, profil: str = "hybride") -> dict:
    if pid not in PROVEDORES:
        return {"ok": False, "message": "Provedor desconhecido."}
    from core.panneau import _nom_valide
    modele = str(modele or "").strip()
    if not _nom_valide(modele):
        return {"ok": False, "message": "Nome de modelo inválido."}
    section = PROVEDORES[pid]["section"]
    cle = f"{section}.modele_qualite" if (profil == "qualite" and pid in {"openai", "anthropic"}) \
        else f"{section}.modele"
    definir(cle, modele)
    _apres_changement(pid)
    return {"ok": True, "message": f"{PROVEDORES[pid]['nom']} : modelo {modele} salvo."}


def activer(pid: str, modele, profil: str = "hybride") -> dict:
    """Fait du fournisseur le cerveau de Jarvis (OpenAI, Anthropic ou Ollama)."""
    if pid not in PROVEDORES:
        return {"ok": False, "message": "Provedor desconhecido."}
    if not PROVEDORES[pid]["cerveau"]:
        return {"ok": False, "message": "Este provedor fica salvo para conectores; "
                "o cérebro do Jarvis usa OpenAI, Anthropic ou Ollama."}
    from core.panneau import _definir_actif
    if pid == "ollama":
        return _definir_actif("local", str(modele or "").strip())
    return _definir_actif("cloud", str(modele or "").strip(), profil=profil, fournisseur=pid)


def _apres_changement(pid: str) -> None:
    # Le provider LLM met en cache son client (cle) et son modele : sans cela, une
    # cle ajoutee dans le panneau n'etait prise en compte qu'au redemarrage.
    try:
        from core import llm
        llm.reinitialiser()
    except Exception:
        pass
    if pid == "openai":
        try:
            from core import panneau
            panneau._OPENAI_CACHE.update(ts=0.0, ids=set(), erreur="")
        except Exception:
            pass


# ============================================================ ElevenLabs

_ELEVEN = "https://api.elevenlabs.io/v1"


def elevenlabs_etat() -> dict:
    cle = str(reglage("elevenlabs.cle", "") or "").strip()
    return {"configure": bool(cle), "cle_masquee": masquer(cle),
            "voix": str(reglage("elevenlabs.voix", "") or ""),
            "modele": str(reglage("elevenlabs.modele", "eleven_flash_v2_5") or ""),
            "moteur": str(reglage("tts.moteur", "auto") or "auto")}


def elevenlabs_enregistrer_cle(cle) -> dict:
    cle = str(cle or "").strip()
    if cle and not cle_valide(cle):
        return {"ok": False, "message": "Formato de chave inválido."}
    if cle and not cle.startswith("sk_"):
        return {"ok": False, "message": "Isso parece ser o ID da chave, não a chave. A chave da "
                "ElevenLabs começa com sk_ e só aparece quando é criada ou rotacionada "
                "(elevenlabs.io › Developers › API Keys)."}
    definir("elevenlabs.cle", cle)
    _reinitialiser_voix()
    return {"ok": True, "message": "Chave ElevenLabs salva." if cle else "Chave removida.",
            "cle_masquee": masquer(cle)}


def elevenlabs_tester() -> dict:
    cle = str(reglage("elevenlabs.cle", "") or "").strip()
    if not cle:
        return {"ok": False, "message": "Salve a chave antes de testar."}
    import requests
    entetes = {"xi-api-key": cle}
    try:
        rv = requests.get(f"{_ELEVEN}/voices", headers=entetes, timeout=TIMEOUT)
        if rv.status_code != 200:
            return {"ok": False, "message": _erreur_http(rv)}
        voix = []
        for v in rv.json().get("voices", []):
            if not v.get("voice_id"):
                continue
            rotulos = v.get("labels") or {}
            detalhe = " · ".join(str(rotulos[k]) for k in ("gender", "accent", "age", "use_case")
                                 if rotulos.get(k))
            categoria = v.get("category", "") or ""
            voix.append({"id": v["voice_id"], "nom": v.get("name", "Voz"), "categorie": categoria,
                         # « Minhas vozes » : clonadas, geradas, profissionais e as salvas
                         # da biblioteca ; o resto são as vozes padrão da ElevenLabs.
                         "minha": categoria not in ("premade", ""),
                         "detalhe": detalhe[:80], "previa": v.get("preview_url", "")})
        voix.sort(key=lambda x: (not x["minha"], x["nom"].lower()))
        modeles = []
        try:
            rm = requests.get(f"{_ELEVEN}/models", headers=entetes, timeout=TIMEOUT)
            if rm.status_code == 200:
                modeles = [{"id": m.get("model_id", ""), "nom": m.get("name", "")}
                           for m in rm.json()
                           if m.get("model_id") and m.get("can_do_text_to_speech", True)]
        except Exception:
            modeles = []
    except requests.exceptions.Timeout:
        return {"ok": False, "message": "Tempo esgotado ao contatar a ElevenLabs."}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "message": "ElevenLabs inacessível."}
    except Exception as e:
        return {"ok": False, "message": f"Falha no teste : {type(e).__name__}"}
    try:
        from core import panneau
        panneau._ELEVENLABS_CACHE.update(ts=time.time(), voix=voix, erreur="")
    except Exception:
        pass
    minhas = sum(1 for v in voix if v["minha"])
    return {"ok": True, "voix": voix, "modeles": modeles,
            "message": f"Conexão OK: {minhas} voz(es) sua(s) e {len(voix) - minhas} padrão."}


def elevenlabs_choisir(voix=None, modele=None, activer_moteur: bool = False) -> dict:
    from core.panneau import _nom_valide
    if voix is not None:
        voix = str(voix).strip()
        if voix and not re.match(r"^[A-Za-z0-9]{6,64}$", voix):
            return {"ok": False, "message": "ID de voz inválido."}
        definir("elevenlabs.voix", voix)
    if modele is not None:
        modele = str(modele).strip()
        if modele and not _nom_valide(modele):
            return {"ok": False, "message": "Modelo inválido."}
        definir("elevenlabs.modele", modele)
    if activer_moteur:
        definir("tts.moteur", "elevenlabs")
    _reinitialiser_voix()
    return {"ok": True, "message": "Voz ElevenLabs salva; vale na próxima resposta."}


def _reinitialiser_voix() -> None:
    try:
        from core import panneau
        panneau._ELEVENLABS_CACHE.update(ts=0.0, voix=[], erreur="")
    except Exception:
        pass
    try:
        from core import tts
        tts.reinitialiser()
    except Exception:
        LOG.debug("reinitialisation tts impossible", exc_info=True)


# ============================================================ favoris et repli

MAX_FAVORIS = 12


def favoris(pid: str) -> list:
    if pid not in PROVEDORES:
        return []
    valeurs = reglage(f"{PROVEDORES[pid]['section']}.favoris", []) or []
    return [str(v) for v in valeurs if str(v).strip()]


def favoris_ajouter(pid: str, modele) -> dict:
    if pid not in PROVEDORES:
        return {"ok": False, "message": "Provedor desconhecido."}
    from core.panneau import _nom_valide
    modele = str(modele or "").strip()
    if not _nom_valide(modele):
        return {"ok": False, "message": "Nome de modelo inválido."}
    liste = favoris(pid)
    if modele in liste:
        return {"ok": True, "message": "Já está nos favoritos.", "favoritos": liste}
    if len(liste) >= MAX_FAVORIS:
        return {"ok": False, "message": f"Máximo de {MAX_FAVORIS} favoritos por provedor."}
    liste.append(modele)
    definir(f"{PROVEDORES[pid]['section']}.favoris", liste)
    return {"ok": True, "message": f"{modele} adicionado aos favoritos.", "favoritos": liste}


def favoris_retirer(pid: str, modele) -> dict:
    if pid not in PROVEDORES:
        return {"ok": False, "message": "Provedor desconhecido."}
    liste = [m for m in favoris(pid) if m != str(modele or "").strip()]
    definir(f"{PROVEDORES[pid]['section']}.favoris", liste)
    return {"ok": True, "message": "Favorito removido.", "favoritos": liste}


def repli_etat() -> dict:
    return {"ativo": bool(reglage("llm.repli_actif", False)),
            "ordem": [str(e) for e in (reglage("llm.repli", []) or [])]}


def repli_definir(ativo=None, ordem=None) -> dict:
    from core.panneau import _nom_valide
    if ordem is not None:
        if not isinstance(ordem, list) or len(ordem) > 8:
            return {"ok": False, "message": "Lista de fallback inválida (máx. 8)."}
        propre = []
        for e in ordem:
            fournisseur, _, modele = str(e).partition(":")
            fournisseur = fournisseur.strip().lower()
            modele = modele.strip()
            if fournisseur not in {"openai", "anthropic", "ollama"} or (modele and not _nom_valide(modele)):
                return {"ok": False, "message": f"Entrada inválida: {str(e)[:60]} "
                        "(use openai:, anthropic: ou ollama:)"}
            entree = f"{fournisseur}:{modele}"
            if entree not in propre:
                propre.append(entree)
        definir("llm.repli", propre)
    if ativo is not None:
        definir("llm.repli_actif", bool(ativo))
    try:
        from core import llm
        llm.reinitialiser()
    except Exception:
        pass
    return {"ok": True, "message": "Fallback salvo; vale na próxima resposta.", **repli_etat()}

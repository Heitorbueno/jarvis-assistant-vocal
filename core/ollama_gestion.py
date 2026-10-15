"""Gestion d'Ollama depuis le panneau : détection automatique, installation du
programme, démarrage du service.

- ``detecter()`` sonde l'hôte configuré puis les adresses locales usuelles ; si
  l'hôte configuré ne répond pas mais qu'un Ollama local répond, l'hôte est
  corrigé automatiquement dans config.yaml.
- ``installer_programme()`` lance l'installateur OFFICIEL en tâche de fond :
  winget ``Ollama.Ollama`` (Windows), script ``ollama.com/install.sh`` (Linux,
  root requis), Homebrew (macOS). Aucun paramètre venant du navigateur n'entre
  dans la commande.
- ``demarrer()`` lance ``ollama serve`` détaché si le programme est installé mais
  ne répond pas.

Le téléchargement des MODÈLES reste dans core.panneau (_ollama_pull).
"""
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from core.config import definir, reglage

LOG = logging.getLogger("jarvis.ollama")

CANDIDATS = ("http://localhost:11434", "http://127.0.0.1:11434")
_INSTALLATION = {"etat": "inactif", "message": "", "debut": 0.0, "journal": ""}
_VERROU = threading.Lock()


def _hote():
    return str(reglage("ollama.hote", "http://localhost:11434") or "").rstrip("/")


def binaire():
    """Chemin du programme ollama, ou None."""
    trouve = shutil.which("ollama")
    if trouve:
        return trouve
    candidats = []
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", "")
        if base:
            candidats.append(Path(base) / "Programs" / "Ollama" / "ollama.exe")
    else:
        candidats += [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama"),
                      Path("/opt/homebrew/bin/ollama")]
    for c in candidats:
        if c.is_file():
            return str(c)
    return None


def _version(hote, timeout=2.5):
    try:
        import requests
        r = requests.get(f"{hote}/api/version", timeout=timeout)
        if r.status_code == 200:
            return str((r.json() or {}).get("version", "") or "?")
    except Exception:
        return None
    return None


def _modeles(hote):
    try:
        import requests
        r = requests.get(f"{hote}/api/tags", timeout=5)
        r.raise_for_status()
        return [{"nom": m.get("name", ""),
                 "taille_go": round((m.get("size", 0) or 0) / (1024 ** 3), 1)}
                for m in (r.json() or {}).get("models", []) if m.get("name")]
    except Exception:
        return []


def methode_installation():
    """Commande officielle disponible sur ce système, ou None."""
    if sys.platform == "win32":
        return "winget" if shutil.which("winget") else None
    if sys.platform == "darwin":
        return "brew" if shutil.which("brew") else None
    if shutil.which("curl") and shutil.which("sh"):
        return "script"
    return None


def detecter(corriger=True):
    """État complet d'Ollama pour le panneau (détection automatique)."""
    configure = _hote()
    hote, version = configure, _version(configure)
    auto_corrige = False
    if version is None:
        for candidat in CANDIDATS:
            if candidat.rstrip("/") == configure:
                continue
            v = _version(candidat)
            if v is not None:
                hote, version = candidat, v
                if corriger:
                    definir("ollama.hote", candidat)
                    auto_corrige = True
                break
    racine_linux = (not sys.platform.startswith("win")
                    and hasattr(os, "geteuid") and os.geteuid() == 0)
    return {
        "joignable": version is not None,
        "version": version or "",
        "hote": hote,
        "hote_configure": configure,
        "hote_corrige": auto_corrige,
        "binaire": binaire() or "",
        "installe": bool(binaire()),
        "systeme": platform.system(),
        "methode_installation": methode_installation() or "",
        "root": racine_linux,
        "modeles": _modeles(hote) if version is not None else [],
        "modele_actif": str(reglage("ollama.modele", "") or ""),
        "installation": dict(_INSTALLATION),
    }


def _commande_installation(methode):
    if methode == "winget":
        return ["winget", "install", "--id", "Ollama.Ollama", "-e", "--source", "winget",
                "--silent", "--accept-source-agreements", "--accept-package-agreements"]
    if methode == "brew":
        return ["brew", "install", "ollama"]
    if methode == "script":
        return ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"]
    return None


def installer_programme():
    """Lance l'installation officielle d'Ollama en tâche de fond."""
    with _VERROU:
        if _INSTALLATION["etat"] == "en_cours":
            return {"ok": False, "message": "Instalação já em andamento."}
        if binaire():
            return {"ok": True, "message": "Ollama já está instalado.", "deja": True}
        methode = methode_installation()
        if not methode:
            return {"ok": False, "message": "Nenhum instalador oficial disponível aqui "
                    "(winget/brew/curl). Instale em https://ollama.com/download"}
        if methode == "script" and hasattr(os, "geteuid") and os.geteuid() != 0:
            return {"ok": False, "message": "No Linux a instalação exige root. Rode no servidor: "
                    "curl -fsSL https://ollama.com/install.sh | sh"}
        commande = _commande_installation(methode)
        _INSTALLATION.update(etat="en_cours", message=f"Instalando via {methode}…",
                             debut=time.time(), journal="")

    def worker():
        try:
            p = subprocess.run(commande, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=1800)
            sortie = ((p.stdout or "") + (p.stderr or ""))[-1500:]
            if p.returncode == 0 or binaire():
                _INSTALLATION.update(etat="ok", message="Ollama instalado.", journal=sortie)
                if _version(_hote()) is None:
                    demarrer()
            else:
                _INSTALLATION.update(etat="erreur", journal=sortie,
                                     message=f"Instalador terminou com código {p.returncode}.")
        except subprocess.TimeoutExpired:
            _INSTALLATION.update(etat="erreur", message="Tempo esgotado na instalação.")
        except Exception as e:
            LOG.exception("installation ollama")
            _INSTALLATION.update(etat="erreur", message=f"Falha: {type(e).__name__}")

    threading.Thread(target=worker, daemon=True, name="installation-ollama").start()
    return {"ok": True, "message": "Instalação do Ollama iniciada."}


def etat_installation():
    return dict(_INSTALLATION, installe=bool(binaire()), joignable=_version(_hote()) is not None)


def demarrer():
    """Lance « ollama serve » détaché si le programme existe et ne répond pas."""
    if _version(_hote()) is not None:
        return {"ok": True, "message": "Ollama já está rodando."}
    exe = binaire()
    if not exe:
        return {"ok": False, "message": "Ollama não está instalado."}
    try:
        options = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                   "stdin": subprocess.DEVNULL}
        if sys.platform == "win32":
            options["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x8)
                                        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))
        else:
            options["start_new_session"] = True
        subprocess.Popen([exe, "serve"], **options)
    except Exception as e:
        return {"ok": False, "message": f"Não foi possível iniciar: {type(e).__name__}"}
    for _ in range(20):
        time.sleep(0.5)
        if _version(_hote()) is not None:
            return {"ok": True, "message": "Ollama iniciado."}
    return {"ok": False, "message": "Ollama iniciado, mas ainda não respondeu. Tente detectar de novo."}

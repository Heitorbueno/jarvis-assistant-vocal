"""Chargement de config.yaml : tous les secrets et reglages, au meme endroit.

Aucune cle en dur dans le code : tout passe par reglage("section.cle").
Le fichier config.yaml n'est pas versionne (voir .gitignore).

Versionnement : config.example.yaml (versionne) documente le schema ; config.yaml
(prive) ne contient QUE les valeurs choisies par l'utilisateur. Une nouvelle cle
ajoutee au projet a toujours une valeur par defaut dans le code (reglage(..., defaut)),
donc une mise a jour ne demande jamais de modifier config.yaml ni de creer un .env.
JARVIS_CONFIG=/chemin/config.yaml permet de le placer ailleurs (LXC, service).
Chaque ecriture est atomique et garde la version precedente dans config.yaml.bak.
"""
import os
import threading
from pathlib import Path

import yaml

_CONFIG = None
FICHIER = Path(os.environ.get("JARVIS_CONFIG") or
               (Path(__file__).resolve().parent.parent / "config.yaml"))
_VERROU = threading.RLock()


def _charger():
    global _CONFIG
    if _CONFIG is None:
        try:
            _CONFIG = yaml.safe_load(FICHIER.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            _CONFIG = {}
    return _CONFIG


def reglage(chemin, defaut=None):
    """Lit une valeur imbriquee, ex. reglage("hue.pont").

    Renvoie `defaut` si le chemin n'existe pas ; renvoie la valeur telle quelle
    si elle vaut explicitement null (ex. audio.haut_parleur: null -> None).
    """
    valeur = _charger()
    for cle in chemin.split("."):
        if not isinstance(valeur, dict) or cle not in valeur:
            return defaut
        valeur = valeur[cle]
    return valeur


def definir(chemin, valeur):
    """Modifie une valeur (ex. 'assistant.personnalite') et reecrit config.yaml.

    Ecriture atomique (fichier temporaire puis remplacement) : une coupure pendant
    l'ecriture ne laisse jamais un config.yaml tronque. L'ancienne version est
    copiee dans config.yaml.bak."""
    with _VERROU:
        conf = _charger()
        noeud = conf
        cles = chemin.split(".")
        for cle in cles[:-1]:
            if not isinstance(noeud.get(cle), dict):
                noeud[cle] = {}
            noeud = noeud[cle]
        noeud[cles[-1]] = valeur
        cible = Path(FICHIER)
        temporaire = cible.with_name(cible.name + ".tmp")
        with open(temporaire, "w", encoding="utf-8") as f:
            yaml.safe_dump(conf, f, allow_unicode=True, sort_keys=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        if cible.exists():
            try:
                sauvegarde = cible.with_name(cible.name + ".bak")
                sauvegarde.write_bytes(cible.read_bytes())
            except OSError:
                pass
        os.replace(temporaire, cible)

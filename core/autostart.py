"""Démarrage automatique de Jarvis avec l'ordinateur (Windows, Linux).

S'appuie sur la méthode EXISTANTE :
  - Windows : scripts/autostart_install.ps1 (tâche planifiée au login, repli dossier
    Démarrage) qui lance scripts/demarrer_jarvis_complet.ps1 (anti-doublon).
  - Linux : unité systemd. Mode « completo » = service UTILISATEUR (session avec
    audio, `systemctl --user`) ; mode « servidor » = service SYSTÈME (LXC/serveur
    sans son : panneau, accès distant, PWA, pont iPhone ; voir scripts/jarvis_servidor.py).

Aucune donnée du navigateur n'entre dans les commandes : seuls le mode
(completo/servidor) et l'action (installer/retirer) sont choisis.
"""
import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
NOM = "JarvisAutostart"
UNITE = "jarvis.service"


def _uv():
    for c in (shutil.which("uv"), str(Path.home() / ".local" / "bin" / "uv"),
              str(Path.home() / ".cargo" / "bin" / "uv")):
        if c and Path(c).is_file():
            return c
    return "uv"


def _executer(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()[-600:]
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"[:300]


# ============================================================ Windows

def _windows_etat():
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" \
        / "Programs" / "Startup" / f"{NOM}.cmd"
    if startup.exists():
        return {"ativo": True, "metodo": "pasta Inicializar"}
    code, _ = _executer(["schtasks", "/Query", "/TN", NOM], timeout=15)
    return {"ativo": code == 0, "metodo": "tarefa agendada" if code == 0 else ""}


def _windows(installer):
    script = RACINE / "scripts" / ("autostart_install.ps1" if installer else "autostart_uninstall.ps1")
    code, sortie = _executer(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                              "-File", str(script)], timeout=90)
    return {"ok": code == 0, "message": ("Início automático ativado." if installer
                                         else "Início automático desativado.") if code == 0
            else f"Falha ({code}): {sortie[-200:]}"}


# ============================================================ Linux (systemd)

def contenu_unite(mode="completo", utilisateur=None):
    """Texte de l'unité systemd (exposé pour les tests)."""
    uv = _uv()
    if mode == "servidor":
        exec_ = f"{uv} run --directory {RACINE} python scripts/jarvis_servidor.py"
        cible, user = "multi-user.target", f"User={utilisateur or getpass.getuser()}\n"
        apres = "network-online.target"
    else:
        exec_ = f"{uv} run --directory {RACINE} python jarvis14.py"
        cible, user, apres = "default.target", "", "pipewire.service pulseaudio.service"
    return (
        "[Unit]\n"
        "Description=Jarvis — assistente vocal\n"
        f"After={apres}\n"
        f"Wants={'network-online.target' if mode == 'servidor' else ''}\n\n"
        "[Service]\n"
        f"{user}"
        f"WorkingDirectory={RACINE}\n"
        f"ExecStart={exec_}\n"
        "Restart=on-failure\n"
        "RestartSec=10\n"
        "Environment=PYTHONUNBUFFERED=1\n\n"
        "[Install]\n"
        f"WantedBy={cible}\n"
    )


def _chemin_unite(mode):
    if mode == "servidor":
        return Path("/etc/systemd/system") / UNITE
    return Path.home() / ".config" / "systemd" / "user" / UNITE


def _systemctl(mode, *args):
    base = ["systemctl"] if mode == "servidor" else ["systemctl", "--user"]
    return _executer(base + list(args))


def _linux_etat():
    for mode in ("servidor", "completo"):
        if _chemin_unite(mode).exists():
            code, _ = _systemctl(mode, "is-enabled", UNITE)
            return {"ativo": code == 0, "metodo": f"systemd ({mode})", "modo": mode}
    return {"ativo": False, "metodo": ""}


def _linux(installer, mode):
    if not shutil.which("systemctl"):
        return {"ok": False, "message": "systemd não encontrado neste sistema."}
    if mode == "servidor" and os.geteuid() != 0:
        return {"ok": False, "message": "O modo servidor instala um serviço do sistema: rode como root "
                "(sudo uv run python scripts/autostart.py --modo servidor)."}
    chemin = _chemin_unite(mode)
    if installer:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu_unite(mode), encoding="utf-8")
        _systemctl(mode, "daemon-reload")
        code, sortie = _systemctl(mode, "enable", "--now", UNITE)
        if mode == "completo" and code == 0 and shutil.which("loginctl"):
            _executer(["loginctl", "enable-linger", getpass.getuser()])
        return {"ok": code == 0, "message": f"Serviço systemd ({mode}) ativado." if code == 0
                else f"Falha ao ativar: {sortie[-200:]}"}
    for m in ("servidor", "completo"):
        c = _chemin_unite(m)
        if c.exists():
            _systemctl(m, "disable", "--now", UNITE)
            try:
                c.unlink()
            except OSError as e:
                return {"ok": False, "message": f"Não foi possível remover {c}: {e}"}
            _systemctl(m, "daemon-reload")
    return {"ok": True, "message": "Início automático desativado."}


# ============================================================ API

def etat():
    if sys.platform == "win32":
        d = _windows_etat()
    elif sys.platform.startswith("linux"):
        d = _linux_etat()
    else:
        d = {"ativo": False, "metodo": ""}
    d["sistema"] = sys.platform
    d["suportado"] = sys.platform == "win32" or sys.platform.startswith("linux")
    return d


def configurer(activer, mode="completo"):
    mode = "servidor" if mode == "servidor" else "completo"
    if sys.platform == "win32":
        return _windows(bool(activer))
    if sys.platform.startswith("linux"):
        return _linux(bool(activer), mode)
    return {"ok": False, "message": "Início automático disponível para Windows e Linux."}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Início automático do Jarvis")
    ap.add_argument("--remover", action="store_true")
    ap.add_argument("--modo", choices=["completo", "servidor"], default="completo")
    a = ap.parse_args()
    print(configurer(not a.remover, a.modo)["message"])

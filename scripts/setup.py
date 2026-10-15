"""Installateur interactif de Jarvis, pour debutants.

    python scripts/setup.py

Verifie Python, installe les dependances, demande le mode (cloud/local), recueille
les cles / verifie Ollama, detecte le materiel, teste les integrations, et finit par
une phrase de bienvenue prononcee par Jarvis.

Concu pour etre lance meme sans dependances installees : il les installe puis se
relance tout seul dans le bon environnement.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
WIN = sys.platform == "win32"


def dire_titre(t):
    print("\n" + "=" * 52 + f"\n  {t}\n" + "=" * 52)


def demander(question, defaut=""):
    r = input(f"{question}{f' [{defaut}]' if defaut else ''} : ").strip()
    return r or defaut


def oui(question, defaut=True):
    d = "O/n" if defaut else "o/N"
    r = input(f"{question} ({d}) : ").strip().lower()
    if not r:
        return defaut
    return r in ("o", "oui", "y", "yes")


def lire_cle(prompt):
    """Lit une cle sans l'afficher (getpass) si on est dans un vrai terminal ;
    sinon repli sur input() visible (evite tout blocage en non-interactif)."""
    if sys.stdin.isatty():
        try:
            import getpass
            return getpass.getpass(prompt).strip()
        except Exception:
            pass
    return input(prompt).strip()


# --------------------------------------------------------------- bootstrap

def deps_presentes():
    try:
        import yaml, requests, sounddevice  # noqa: F401
        return True
    except Exception:
        return False


def python_venv():
    p = RACINE / ".venv" / ("Scripts" if WIN else "bin") / ("python.exe" if WIN else "python")
    return p if p.exists() else None


def installer_dependances():
    dire_titre("Installation des dependances")
    if shutil.which("uv"):
        print("uv detecte -> uv sync (recommande).")
        subprocess.run(["uv", "sync"], cwd=RACINE, check=False)
    else:
        print("uv absent -> creation d'un venv + pip install.")
        if not python_venv():
            subprocess.run([sys.executable, "-m", "venv", str(RACINE / ".venv")], check=False)
        py = python_venv() or Path(sys.executable)
        subprocess.run([str(py), "-m", "pip", "install", "-r", str(RACINE / "requirements.txt")],
                       check=False)
    print("\nInstallation de Chromium pour Playwright (reservations/navigateur)...")
    py = python_venv() or Path(sys.executable)
    subprocess.run([str(py), "-m", "playwright", "install", "chromium"], cwd=RACINE, check=False)


def relancer_dans_venv():
    py = python_venv()
    if py and Path(py) != Path(sys.executable):
        print(f"\nRelancement dans l'environnement {py} ...\n")
        os.execv(str(py), [str(py), __file__, "--suite"])
    if not deps_presentes():
        print("\nDependances installees. Relance ce script :")
        print(f"   {python_venv() or 'python'} scripts/setup.py")
        sys.exit(0)


# --------------------------------------------------------------- config

def charger_exemple():
    import yaml
    return yaml.safe_load((RACINE / "config.example.yaml").read_text(encoding="utf-8")) or {}


def ecrire_config(conf):
    import yaml
    (RACINE / "config.yaml").write_text(
        yaml.safe_dump(conf, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print("\n-> config.yaml ecrit.")


URL_PAINEL = "http://127.0.0.1:8790/panneau"


def config_cloud(conf):
    """Mode cloud : AUCUNE cle demandee ici. Tout se configure dans le panneau
    (onglets « Provedores IA » et « ElevenLabs ») avec test de connexion."""
    dire_titre("Mode CLOUD — chaves pelo painel")
    conf["mode"] = "hybride"
    print("Nenhuma chave é pedida aqui. Depois de iniciar o Jarvis, abra:")
    print(f"   {URL_PAINEL}")
    print("   -> aba « Provedores IA » : salve a chave (OpenAI, Anthropic...), teste a")
    print("      conexão, escolha o modelo e clique em « Usar como cérebro ».")
    print("   -> aba « ElevenLabs » : chave, voz e modelo de voz (opcional).")
    print("\nOutras integrações (Agenda, Discord, Twilio...) têm seu guia em docs/.")


def _installer_ollama_natif():
    """Installe Ollama nativement (winget sous Windows, script officiel sous Linux/macOS)."""
    if shutil.which("ollama"):
        return True
    if WIN and shutil.which("winget"):
        if oui("Ollama não está instalado. Instalar agora via winget (Ollama.Ollama)?", True):
            subprocess.run(["winget", "install", "--id", "Ollama.Ollama", "-e", "--source", "winget",
                            "--accept-source-agreements", "--accept-package-agreements"],
                           check=False)
    elif not WIN and shutil.which("curl"):
        if oui("Ollama não está instalado. Instalar com o script oficial (ollama.com/install.sh)?", True):
            subprocess.run(["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"], check=False)
    if shutil.which("ollama"):
        return True
    padrao = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    if WIN and padrao.exists():
        os.environ["PATH"] = f"{padrao.parent}{os.pathsep}{os.environ.get('PATH', '')}"
        return True
    print("Instale manualmente: https://ollama.com/download")
    input("  Pressione Enter quando o Ollama estiver instalado...")
    return bool(shutil.which("ollama"))


def config_local(conf):
    dire_titre("Mode LOCAL — Ollama nativo (100% offline)")
    conf["mode"] = "local"
    _installer_ollama_natif()
    modele = demander("Modelo Ollama", "qwen2.5:7b")
    conf.setdefault("ollama", {})["modele"] = modele
    if shutil.which("ollama") and oui(f"Baixar o modelo '{modele}' agora?", True):
        subprocess.run(["ollama", "pull", modele], check=False)
    print("\nWhisper (transcrição) é baixado sozinho no 1º uso.")
    print(f"Modelos, provedores cloud e voz depois: painel {URL_PAINEL}")


# --------------------------------------------------------------- materiel + tests

def detecter_materiel():
    dire_titre("Materiel")
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        nom = pynvml.nvmlDeviceGetName(h)
        nom = nom.decode() if isinstance(nom, bytes) else nom
        vram = pynvml.nvmlDeviceGetMemoryInfo(h).total / (1024 ** 3)
        print(f"  GPU : {nom} — {vram:.0f} Go VRAM")
        if vram < 6:
            print("  (!) <6 Go : en local, prefere qwen3.5:2b, ou reste en cloud.")
        pynvml.nvmlShutdown()
    except Exception:
        print("  Pas de GPU NVIDIA detecte : tout marche en CPU (Whisper plus lent).")


def tester_integrations():
    dire_titre("Test des integrations configurees")
    try:
        subprocess.run([sys.executable, str(RACINE / "scripts" / "doctor.py")], check=False)
    except Exception as e:
        print(f"  (impossible de lancer doctor.py : {e})")


def test_micro_et_bienvenue():
    dire_titre("Test micro + bienvenue")
    try:
        import sounddevice as sd
        entrees = [d for d in sd.query_devices() if d["max_input_channels"] > 0]
        print(f"  {len(entrees)} entree(s) audio detectee(s).")
    except Exception:
        print("  (test micro impossible)")
    try:
        from core.voix import definir_parleur  # noqa
        # Utilise le meme chemin TTS que l'assistant.
        import importlib
        tts = importlib.import_module("core.tts").tts()
        res = tts.synthetiser("Bonjour, je suis Jarvis. Installation terminee !")
        if res is not None:
            import sounddevice as sd
            audio, freq = res
            sd.play(audio, samplerate=freq); sd.wait()
            print("  Jarvis a parle : installation terminee !")
        else:
            print("  (voix indisponible ici ; elle marchera au lancement de l'assistant)")
    except Exception as e:
        print(f"  (bienvenue vocale non jouee : {e})")


# --------------------------------------------------------------- flux

def main():
    dire_titre("Installation de Jarvis")
    v = sys.version_info
    if v < (3, 10):
        print(f"Python {v.major}.{v.minor} trop ancien. Installe Python 3.10+ (3.13 recommande).")
        sys.exit(1)
    print(f"Python {v.major}.{v.minor}.{v.micro} OK.")

    if "--suite" not in sys.argv and not deps_presentes():
        if oui("Installer les dependances maintenant ?", True):
            installer_dependances()
            relancer_dans_venv()
        else:
            print("Sans dependances, la suite ne peut pas tourner. Relance quand tu es pret.")
            sys.exit(0)

    if (RACINE / "config.yaml").exists() and not oui(
            "\nUn config.yaml existe deja. Le remplacer ?", False):
        print("On garde ton config.yaml existant.")
        conf = None
    else:
        conf = charger_exemple()
        dire_titre("Mode d'utilisation")
        print("  1) cloud  — chaves de API configuradas depois no painel web")
        print("  2) local  — Ollama nativo + Piper (100% offline, GPU recomendado)")
        choix = demander("Sua escolha (1/2)", "1")
        (config_local if choix.strip() == "2" else config_cloud)(conf)
        # Le panneau (chaves, modelos, voz) precisa do servidor web local.
        conf.setdefault("serveur", {})["actif"] = True
        ecrire_config(conf)

    detecter_materiel()
    tester_integrations()
    test_micro_et_bienvenue()
    if oui("\nIniciar o Jarvis automaticamente quando o computador ligar?", True):
        try:
            from core import autostart
            print("  " + autostart.configurer(True)["message"])
        except Exception as e:
            print(f"  (não foi possível ativar o início automático: {e})")

    dire_titre("Termine !")
    print("Lance Jarvis :  double-clic sur lancer_jarvis.bat, ou  uv run python jarvis14.py")
    print("               (puis dis « Hey Jarvis »)")
    print(f"Painel (chaves, modelos, voz, acesso remoto) :  {URL_PAINEL}")
    print("Un souci ? Diagnostic :  python scripts/doctor.py")


if __name__ == "__main__":
    main()

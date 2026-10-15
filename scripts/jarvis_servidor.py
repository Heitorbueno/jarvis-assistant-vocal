"""Jarvis em modo SERVIDOR (sem microfone/alto-falante): LXC, VM ou servidor 24h.

Sobe apenas o servidor web unificado (painel, acesso remoto, PWA, ponte iPhone),
sem a escuta de voz. Útil num container onde não há placa de som.

    uv run python scripts/jarvis_servidor.py
"""
import logging
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    from core.config import reglage
    if reglage("poste_principal.actif", False) and reglage("poste_principal.serveur_sans_peripheriques", False):
        # Methode existante (docs/hebergement_h24.md) : le serveur 24h porte le cerveau
        # et les satellites/agent Windows portent micro et son.
        import runpy
        racine = Path(__file__).resolve().parent.parent
        sys.argv = [str(racine / "jarvis14.py")]
        runpy.run_path(str(racine / "jarvis14.py"), run_name="__main__")
        return
    from core import serveur
    serveur.demarrer()
    print("Jarvis (modo servidor) ativo. Painel: http://127.0.0.1:%s/panneau" % serveur._port())
    parar = []
    signal.signal(signal.SIGTERM, lambda *a: parar.append(1))
    try:
        while not parar:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

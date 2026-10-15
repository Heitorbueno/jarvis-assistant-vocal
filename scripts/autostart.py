"""Ativa/desativa o início automático do Jarvis (Windows: tarefa/pasta Inicializar;
Linux: systemd). Ex.: uv run python scripts/autostart.py [--modo servidor] [--remover]"""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
runpy.run_module("core.autostart", run_name="__main__")

"""Manutenção pelo painel : atualizar, backup/restauração, diagnóstico, logs,
histórico da conversa e checklist de primeiros passos.

Tudo é LOCAL-ONLY no painel (garde local=True), exceto checklist e histórico,
que também aparecem numa sessão remota autenticada.

- Atualizar : ``git pull --ff-only`` + ``uv sync`` (mesma lógica de lancer_jarvis.bat
  e mettre_a_jour_jarvis.bat). Nunca força, nunca descarta alteração local.
- Backup : ZIP com os dados PESSOAIS não versionados (config.yaml, memória,
  finanças, notas, lembretes, credenciais Google, calibração). Restauração
  só aceita esses mesmos caminhos (sem « zip slip »).
- Logs : últimas linhas de logs/*.log com segredos mascarados.
"""
import io
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

from core.config import reglage

LOG = logging.getLogger("jarvis.manutencao")
RACINE = Path(__file__).resolve().parent.parent
LOGS = RACINE / "logs"

# Dados pessoais incluídos no backup (arquivos ou pastas, relativos à raiz).
ITENS_BACKUP = [
    "config.yaml", "memory.json", "memoire.json", "contenus.yaml", "budget.json",
    "reminders.json", "google_credentials.json", "google_token.json",
    "finances", "notes", "gestes/calibration.json", "scenes.yaml",
]
MAX_BACKUP = 200 * 1024 * 1024
_ATUALIZACAO = {"etat": "inactif", "journal": "", "debut": 0.0}
_VERROU = threading.Lock()


# ============================================================ utilitários

def _executer(cmd, timeout=600):
    try:
        p = subprocess.run(cmd, cwd=RACINE, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except FileNotFoundError:
        return 127, f"{cmd[0]} não encontrado"
    except subprocess.TimeoutExpired:
        return 124, "tempo esgotado"


_SEGREDOS = [
    (re.compile(r"(sk-(?:ant-|proj-)?|sk_|gsk_|ghp_|github_pat_|xai-|AIza)[A-Za-z0-9_\-]{6,}"), r"\1[oculto]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"), r"\1[oculto]"),
    (re.compile(r"(?i)((?:api[_-]?key|token|secret|senha|password|cle)\s*[:=]\s*)\S{6,}"), r"\1[oculto]"),
]


def mascarar(texto):
    for padrao, troca in _SEGREDOS:
        texto = padrao.sub(troca, texto)
    return texto


def _uv():
    for c in (shutil.which("uv"), str(Path.home() / ".local" / "bin" / "uv"),
              str(Path.home() / ".local" / "bin" / "uv.exe")):
        if c and Path(c).is_file():
            return c
    return None


# ============================================================ versão / atualização

def versao():
    if not shutil.which("git") or not (RACINE / ".git").exists():
        return {"git": False, "message": "Instalação sem git: atualize baixando o projeto de novo."}
    _, commit = _executer(["git", "log", "-1", "--format=%h %cs %s"], 15)
    _, ramo = _executer(["git", "rev-parse", "--abbrev-ref", "HEAD"], 15)
    _, sujo = _executer(["git", "status", "--porcelain", "--untracked-files=no"], 15)
    return {"git": True, "commit": commit[:120], "ramo": ramo.strip(),
            "alteracoes_locais": bool(sujo.strip())}


def verificar_atualizacao():
    if not versao().get("git"):
        return {"ok": False, "message": "Instalação sem git."}
    code, saida = _executer(["git", "fetch", "--quiet", "origin"], 60)
    if code != 0:
        return {"ok": False, "message": "Sem acesso ao GitHub agora: " + mascarar(saida)[-160:]}
    _, n = _executer(["git", "rev-list", "--count", "HEAD..@{u}"], 15)
    _, lista = _executer(["git", "log", "--format=%h %s", "HEAD..@{u}", "-n", "15"], 15)
    try:
        qtd = int(n.strip() or 0)
    except ValueError:
        qtd = 0
    return {"ok": True, "novidades": qtd, "lista": lista.splitlines()[:15],
            "message": f"{qtd} atualização(ões) disponível(is)." if qtd else "Você já está na versão mais recente."}


def atualizar():
    """git pull --ff-only + uv sync, em segundo plano. Reinício fica com o usuário."""
    with _VERROU:
        if _ATUALIZACAO["etat"] == "en_cours":
            return {"ok": False, "message": "Atualização já em andamento."}
        if not versao().get("git"):
            return {"ok": False, "message": "Instalação sem git."}
        _ATUALIZACAO.update(etat="en_cours", journal="", debut=time.time())

    def worker():
        journal = []
        code, saida = _executer(["git", "pull", "--ff-only"], 180)
        journal.append("$ git pull --ff-only\n" + saida)
        if code != 0:
            _ATUALIZACAO.update(etat="erreur", journal=mascarar("\n".join(journal))[-4000:])
            return
        uv = _uv()
        if uv:
            code, saida = _executer([uv, "sync"], 900)
            journal.append("$ uv sync\n" + saida)
        _ATUALIZACAO.update(etat="ok" if code == 0 else "erreur",
                            journal=mascarar("\n".join(journal))[-4000:])

    threading.Thread(target=worker, daemon=True, name="atualizacao").start()
    return {"ok": True, "message": "Atualização iniciada. Reinicie o Jarvis ao terminar."}


def etat_atualizacao():
    return dict(_ATUALIZACAO)


# ============================================================ backup / restauração

def _arquivos_backup():
    for item in ITENS_BACKUP:
        p = RACINE / item
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not f.name.endswith((".tmp", ".part")):
                    yield f


def gerar_backup():
    buf = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in _arquivos_backup():
            total += f.stat().st_size
            if total > MAX_BACKUP:
                raise ValueError("backup acima de 200 MB")
            z.write(f, f.relative_to(RACINE).as_posix())
        z.writestr("JARVIS_BACKUP.txt", f"Backup do Jarvis gerado em {time.strftime('%Y-%m-%d %H:%M:%S')}.\n"
                   "Contém dados pessoais e chaves: guarde em local seguro.\n")
    return buf.getvalue()


def _permitido(nome):
    nome = nome.replace("\\", "/")
    if nome.startswith("/") or ".." in nome.split("/") or ":" in nome:
        return False
    return any(nome == i or nome.startswith(i.rstrip("/") + "/") for i in ITENS_BACKUP)


def restaurar_backup(conteudo: bytes):
    try:
        z = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile:
        return {"ok": False, "message": "Arquivo não é um ZIP de backup válido."}
    nomes = [n for n in z.namelist() if not n.endswith("/") and n != "JARVIS_BACKUP.txt"]
    if "JARVIS_BACKUP.txt" not in z.namelist():
        return {"ok": False, "message": "Este ZIP não foi gerado pelo backup do Jarvis."}
    recusados = [n for n in nomes if not _permitido(n)]
    if recusados:
        return {"ok": False, "message": f"Backup contém caminhos não permitidos: {recusados[0][:80]}"}
    if sum(z.getinfo(n).file_size for n in nomes) > MAX_BACKUP:
        return {"ok": False, "message": "Backup grande demais."}
    # Cópia de segurança do estado atual antes de sobrescrever.
    seguranca = LOGS / f"antes-da-restauracao-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    LOGS.mkdir(exist_ok=True)
    seguranca.write_bytes(gerar_backup())
    for n in nomes:
        destino = (RACINE / n).resolve()
        if RACINE.resolve() not in destino.parents:
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(z.read(n))
    from core import config
    config._CONFIG = None                       # recarrega config.yaml restaurado
    return {"ok": True, "message": f"{len(nomes)} arquivo(s) restaurado(s). Estado anterior salvo em "
            f"logs/{seguranca.name}. Reinicie o Jarvis."}


# ============================================================ diagnóstico e logs

def diagnostico():
    code, saida = _executer([sys.executable, str(RACINE / "scripts" / "doctor.py")], 120)
    saida = re.sub(r"\x1b\[[0-9;]*m", "", saida)
    return {"ok": True, "codigo": code, "saida": mascarar(saida)[-12000:]}


def logs_disponiveis():
    if not LOGS.is_dir():
        return []
    return sorted(p.name for p in LOGS.glob("*.log") if p.is_file())


def ler_log(nome, linhas=200):
    if nome not in logs_disponiveis():
        return {"ok": False, "message": "Log não encontrado."}
    linhas = max(10, min(int(linhas or 200), 2000))
    p = LOGS / nome
    with open(p, "rb") as f:
        f.seek(0, 2)
        tamanho = f.tell()
        f.seek(max(0, tamanho - 512 * 1024))
        texto = f.read().decode("utf-8", "replace")
    return {"ok": True, "nome": nome, "texto": mascarar("\n".join(texto.splitlines()[-linhas:]))}


# ============================================================ histórico da conversa

def historico():
    """Últimas falas (você / Jarvis) do HUD, se o Jarvis vocal estiver rodando."""
    hud = sys.modules.get("hud")
    if hud is None:
        return {"ativo": False, "falas": []}
    falas = []
    for ev in list(getattr(hud, "_HISTORIQUE", [])):
        if ev.get("t") in ("vous", "jarvis") and ev.get("texte"):
            falas.append({"quem": "voce" if ev["t"] == "vous" else "jarvis", "texto": ev["texte"][:2000]})
    return {"ativo": True, "falas": falas}


# ============================================================ primeiros passos

def checklist():
    from core import autostart, cloud
    from core.routage import mode_actuel
    itens = []
    modo = mode_actuel()
    lang = str(reglage("assistant.langue", "fr") or "fr")
    itens.append({"id": "idioma", "ok": lang == "pt", "aba": "reglages",
                  "titulo": "Idioma português", "detalhe": "Seletor PT-BR no topo do painel."})
    if modo == "local":
        try:
            from core import ollama_gestion
            d = ollama_gestion.detecter(corriger=False)
            ok_cerebro = d["joignable"] and bool(d["modeles"])
        except Exception:
            ok_cerebro = False
        detalhe = "Modo local: Ollama rodando com um modelo instalado."
    else:
        prov = cloud.fournisseur()
        ok_cerebro = bool(reglage(f"{prov}.cle", ""))
        detalhe = f"Modo nuvem: chave do provedor ativo ({prov}) salva."
    try:
        from core import diagnostic_llm
        erro = diagnostic_llm.dernier()
        if erro.get("code"):
            ok_cerebro = False
            detalhe += f" Último erro: {erro['code']}."
    except Exception:
        pass
    itens.append({"id": "cerebro", "ok": ok_cerebro, "aba": "provedores",
                  "titulo": "Cérebro (modelo de IA) configurado", "detalhe": detalhe})
    moteur = str(reglage("tts.moteur", "auto") or "auto")
    voz_ok = (bool(reglage("elevenlabs.cle", "")) if moteur in ("auto", "elevenlabs") and modo != "local"
              else moteur in ("piper", "kokoro", "windows", "auto"))
    itens.append({"id": "voz", "ok": voz_ok, "aba": "eleven",
                  "titulo": "Voz configurada", "detalhe": "ElevenLabs (chave sk_…) ou voz local Piper."})
    try:
        as_ok = autostart.etat().get("ativo", False)
    except Exception:
        as_ok = False
    itens.append({"id": "autostart", "ok": as_ok, "aba": "reglages",
                  "titulo": "Iniciar com o computador", "detalhe": "Ligou o PC, já ouve « Hey Jarvis »."})
    itens.append({"id": "instrucoes", "ok": bool(reglage("assistant.instructions", "")), "aba": "reglages",
                  "titulo": "Prompt comportamental", "detalhe": "Como te chamar, tom, contexto do trabalho."})
    itens.append({"id": "widgets", "ok": bool(reglage("widgets.instalados", [])), "aba": "widgets",
                  "titulo": "Widgets do HUD", "detalhe": "Clima, câmbio, bolsa, notícias…"})
    try:
        from core import financeiro
        fin_ok = bool(financeiro.contas())
    except Exception:
        fin_ok = False
    itens.append({"id": "financeiro", "ok": fin_ok, "aba": "financeiro",
                  "titulo": "Financeiro: bancos cadastrados", "detalhe": "Contas a pagar/receber e fluxo de caixa."})
    itens.append({"id": "remoto", "ok": bool(reglage("acces_distant.actif", False)), "aba": "remoto",
                  "titulo": "Acesso remoto (opcional)", "detalhe": "Tailscale, Cloudflare ou proxy HTTPS."})
    feitos = sum(1 for i in itens if i["ok"])
    return {"itens": itens, "feitos": feitos, "total": len(itens)}

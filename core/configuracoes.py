"""Aba « Configurações » do painel : todas as integrações do config.yaml editáveis
pelo painel, sem abrir o arquivo.

Um ESQUEMA único descreve cada campo (caminho no config.yaml, tipo, rótulo em
português, ajuda). O painel monta o formulário a partir dele ; o servidor valida
pelo mesmo esquema. Regras :

  - segredo (``secret``) : nunca volta ao navegador (só ``••••1234``) ; enviar o
    valor mascarado ou vazio mantém o atual ; « remover » apaga explicitamente ;
  - campos que apontam para executáveis/pastas do PC (``local``) só mudam no PC ;
  - só caminhos do esquema podem ser gravados (nada arbitrário no config.yaml) ;
  - « Testar » faz uma chamada de leitura ao serviço (Hue, Twilio, Discord,
    Spotify, Gmail, Hermes, OBS) sem efeito colateral.
"""
import base64
import json
import logging
import re
import socket
from pathlib import Path

from core.config import _charger, definir, reglage

LOG = logging.getLogger("jarvis.configuracoes")
_RACINE = Path(__file__).resolve().parent.parent


def F(caminho, rotulo, tipo="text", ajuda="", opcoes=None, local=False, reinicio=False, padrao=None,
      minimo=None, maximo=None):
    return {"caminho": caminho, "rotulo": rotulo, "tipo": tipo, "ajuda": ajuda,
            "opcoes": opcoes or [], "local": local, "reinicio": reinicio, "padrao": padrao,
            "min": minimo, "max": maximo}


GRUPOS = [
    {"id": "assistente", "nome": "Assistente", "icone": "🤖", "campos": [
        F("utilisateur.nom", "Seu nome", ajuda="Usado em reservas e formulários."),
        F("utilisateur.telephone", "Seu telefone"),
        F("utilisateur.email", "Seu e-mail"),
        F("assistant.duree_suite", "Escuta contínua após responder (s)", "int", minimo=0, maximo=60, padrao=10),
        F("assistant.seuil_reveil", "Sensibilidade do « Hey Jarvis »", "float", "0,3 = sensível · 0,8 = rigoroso",
          minimo=0.2, maximo=0.95, padrao=0.5),
        F("assistant.seuil_interruption", "Sensibilidade para interromper a fala", "float", minimo=0.2, maximo=0.95, padrao=0.7),
        F("assistant.silence_fin", "Silêncio que encerra a frase (s)", "float", minimo=0.4, maximo=5, padrao=1.2),
        F("assistant.duree_max", "Duração máxima de uma frase (s)", "int", minimo=5, maximo=60, padrao=20),
        F("assistant.attente_confirmation", "Tempo para responder « sim/não » (s)", "float", minimo=1, maximo=15, padrao=3),
        F("assistant.timeout_tour", "Tempo máximo por pedido (s)", "int", minimo=15, maximo=300, padrao=120),
        F("assistant.max_tours_outils", "Máx. de rodadas de ferramentas", "int", minimo=1, maximo=20, padrao=6),
        F("assistant.piece_nuit", "Cômodo aceso ao iniciar à noite", ajuda="Vazio = não acende."),
        F("assistant.delai_extinction", "Atraso ao desligar o PC (s)", "int", minimo=10, maximo=600, padrao=30),
    ]},
    {"id": "audio", "nome": "Áudio e transcrição", "icone": "🎙", "campos": [
        F("whisper.modele", "Modelo Whisper (local)", "select", opcoes=["tiny", "base", "small", "medium",
          "large-v3", "large-v3-turbo"], reinicio=True, padrao="medium"),
        F("stt.moteur", "Transcrição", "select", "auto = local se possível, senão OpenAI",
          opcoes=["auto", "local", "cloud"], reinicio=True, padrao="auto"),
        F("stt.modele_cloud", "Modelo de transcrição na nuvem", padrao="gpt-4o-mini-transcribe"),
        F("audio.raccourci_mute", "Atalho para silenciar o microfone", padrao="ctrl+alt+m", reinicio=True),
        F("interruption.seuil", "Volume mínimo para interromper", "float", minimo=0.001, maximo=0.5, padrao=0.025),
    ]},
    {"id": "casa", "nome": "Casa inteligente", "icone": "🏠", "teste": "hue", "campos": [
        F("hue.pont", "Philips Hue — IP da ponte", ajuda="Ex.: 192.168.1.20", reinicio=True),
        F("hue.cle", "Philips Hue — chave (username)", "secret", reinicio=True),
        F("alexa.email", "Alexa — e-mail Amazon"),
        F("alexa.password", "Alexa — senha", "secret"),
        F("alexa.otp_secret", "Alexa — segredo 2FA (OTP)", "secret"),
        F("alexa.url", "Alexa — domínio Amazon", "select",
          opcoes=["amazon.com.br", "amazon.com", "amazon.fr", "amazon.de", "amazon.co.uk", "amazon.es", "amazon.it"],
          padrao="amazon.com.br"),
        F("google_home.project_id", "Google Home — project ID"),
        F("google_home.client_id", "Google Home — client ID"),
        F("google_home.client_secret", "Google Home — client secret", "secret"),
        F("google_home.refresh_token", "Google Home — refresh token", "secret"),
        F("amaran.url", "Luzes Amaran — URL"),
        F("amaran.piece", "Luzes Amaran — cômodo"),
        F("presence.actif", "Detectar quando você chega/sai", "bool"),
        F("presence.ip", "IP do celular (presença)", ajuda="Reserve o IP no roteador."),
        F("presence.seuil_absence", "Ausente após (s)", "int", minimo=60, maximo=7200, padrao=600),
    ]},
    {"id": "email", "nome": "E-mail e agenda", "icone": "📧", "teste": "mail", "campos": [
        F("mail.adresse", "Gmail — endereço", reinicio=True),
        F("mail.mot_de_passe_app", "Gmail — senha de app", "secret",
          "myaccount.google.com › Segurança › Senhas de app (não é a senha normal)", reinicio=True),
        F("agenda.calendrier_principal", "Google Agenda — calendário principal", padrao="primary"),
        F("_arquivo.google_credentials", "Google Agenda — credenciais OAuth (JSON)", "arquivo",
          "console.cloud.google.com › APIs › Credenciais › ID do cliente OAuth (Desktop) › baixar JSON"),
        F("colis.dans_brief", "Incluir entregas no resumo do dia", "bool"),
        F("colis.jours", "Entregas: olhar últimos (dias)", "int", minimo=1, maximo=60, padrao=10),
        F("loopstr.url", "Loopstr — URL do feed iCal (prazos de parcerias)", "secret"),
        F("factures.url", "Faturas — URL"),
    ]},
    {"id": "telefonia", "nome": "Telefonia (Twilio)", "icone": "📞", "teste": "twilio", "campos": [
        F("twilio.account_sid", "Account SID"),
        F("twilio.auth_token", "Auth token", "secret"),
        F("twilio.numero", "Número Twilio", ajuda="Formato +5565999999999"),
        F("appels.actif", "Ligações ativadas", "bool"),
        F("appels.simulation", "Modo simulação (não liga de verdade)", "bool"),
        F("appels.cout_par_minute", "Custo por minuto (US$)", "float", minimo=0, maximo=10, padrao=0.11),
    ]},
    {"id": "redes", "nome": "Redes sociais", "icone": "💬", "teste": "discord", "campos": [
        F("discord.token", "Discord — token do bot", "secret", reinicio=True),
        F("discord.user_id", "Discord — seu ID de usuário"),
        F("instagram.comptes.0.nom", "Instagram — conta 1: nome"),
        F("instagram.comptes.0.user_id", "Instagram — conta 1: user ID"),
        F("instagram.comptes.0.access_token", "Instagram — conta 1: access token", "secret"),
        F("instagram.comptes.1.nom", "Instagram — conta 2: nome"),
        F("instagram.comptes.1.user_id", "Instagram — conta 2: user ID"),
        F("instagram.comptes.1.access_token", "Instagram — conta 2: access token", "secret"),
    ]},
    {"id": "midia", "nome": "Música e transmissão", "icone": "🎵", "teste": ["spotify", "obs"], "campos": [
        F("spotify.client_id", "Spotify — client ID", ajuda="developer.spotify.com › Dashboard"),
        F("spotify.client_secret", "Spotify — client secret", "secret"),
        F("spotify.playlist", "Spotify — playlist para salvar músicas", padrao="Jarvis Finds"),
        F("spotify.auto_ajout", "Adicionar músicas reconhecidas automaticamente", "bool"),
        F("obs.host", "OBS — host", padrao="localhost"),
        F("obs.port", "OBS — porta WebSocket", "int", minimo=1, maximo=65535, padrao=4455),
        F("obs.mot_de_passe", "OBS — senha WebSocket", "secret"),
        F("musique.secondes", "Reconhecimento de música: segundos gravados", "int", minimo=3, maximo=30, padrao=8),
    ]},
    {"id": "hermes", "nome": "Hermes (agente de fundo)", "icone": "🧠", "teste": "hermes", "campos": [
        F("hermes.api_url", "URL da API", padrao="http://127.0.0.1:8642"),
        F("hermes.api_key", "Chave da API", "secret"),
        F("hermes.session", "Sessão", padrao="jarvis-delegation"),
        F("hermes.timeout", "Tempo máximo de uma tarefa (s)", "int", minimo=30, maximo=7200, padrao=900),
        F("hermes.retention_jours", "Guardar histórico (dias)", "int", minimo=1, maximo=365, padrao=30),
    ]},
    {"id": "servidor", "nome": "Servidor, iPhone e túnel", "icone": "🌐", "campos": [
        F("serveur.actif", "Servidor web (painel) ativo", "bool", reinicio=True),
        F("serveur.port", "Porta do painel", "int", minimo=1024, maximo=65535, padrao=8790, reinicio=True, local=True),
        F("serveur.ngrok_authtoken", "ngrok — authtoken", "secret", reinicio=True),
        F("serveur.ngrok_domaine", "ngrok — domínio fixo", reinicio=True),
        F("serveur.public_url", "URL pública manual", reinicio=True),
        F("pont_iphone.token", "Ponte iPhone — token (Atalhos)", "secret", "Use « Gerar » para criar um token forte."),
    ]},
    {"id": "navegador", "nome": "Navegador e reservas", "icone": "🧭", "campos": [
        F("navigateur.prefere", "Abrir páginas em", "select", opcoes=["firefox", "systeme"], padrao="firefox"),
        F("navigateur.firefox_exe", "Caminho do firefox.exe", local=True),
        F("navigateur.cdp_port", "Porta de depuração do Chrome", "int", minimo=1024, maximo=65535, padrao=9222, local=True),
        F("reservation.navigateur_visible", "Mostrar o navegador nas reservas", "bool"),
        F("reservation.max_etapes", "Reservas: máx. de etapas", "int", minimo=5, maximo=60, padrao=22),
    ]},
    {"id": "interface", "nome": "HUD e overlay", "icone": "🖥", "campos": [
        F("hud.fenetre", "HUD abre como", "select", opcoes=["app", "navigateur"], padrao="app", reinicio=True),
        F("hud.ecran", "HUD — tela (0 = principal)", "nint", minimo=0, maximo=8, reinicio=True),
        F("hud.premier_plan_au_reveil", "Trazer o HUD à frente ao ouvir « Jarvis »", "bool"),
        F("overlay.actif", "Overlay de respostas", "bool", reinicio=True),
        F("overlay.ecran", "Overlay — tela", "int", minimo=0, maximo=8, reinicio=True),
        F("overlay.coin", "Overlay — canto", "select", opcoes=["bas-droite", "bas-gauche", "haut-droite", "haut-gauche"]),
        F("overlay.opacite", "Overlay — opacidade", "float", minimo=0.3, maximo=1, padrao=0.92),
        F("cockpit.actif", "Abrir o cockpit ao iniciar", "bool", reinicio=True),
    ]},
    {"id": "orcamento", "nome": "Orçamento da IA", "icone": "💲", "campos": [
        F("budget.plafond_jour", "Limite por dia (US$)", "nfloat", "Vazio = sem limite", minimo=0, maximo=10000),
        F("budget.plafond_mois", "Limite por mês (US$)", "nfloat", "Vazio = sem limite", minimo=0, maximo=100000),
        F("budget.alerte_pct", "Avisar ao atingir (%)", "int", minimo=10, maximo=100, padrao=80),
        F("budget.mode_normal", "Modo ao renovar o orçamento", "select", opcoes=["hybride", "qualite", "local"], padrao="hybride"),
    ]},
    {"id": "resumo", "nome": "Resumo da manhã", "icone": "📰", "campos": [
        F("signal_matin.actif", "Resumo da manhã ativo", "bool"),
        F("signal_matin.heure", "Horário", ajuda="HH:MM", padrao="08:00"),
        F("signal_matin.imprimer", "Imprimir", "bool"),
        F("signal_matin.imprimante", "Impressora", local=True),
        F("signal_matin.salutation", "Saudação", padrao="Bom dia."),
    ]},
    {"id": "gestos", "nome": "Gestos (webcam)", "icone": "✋", "campos": [
        F("gestes.actif", "Controle por gestos ao iniciar", "bool", reinicio=True),
        F("gestes.device", "Webcam (índice)", "int", minimo=0, maximo=10, reinicio=True),
        F("gestes.raccourci", "Atalho do modo gestos", reinicio=True),
    ]},
]
_CAMPOS = {f["caminho"]: f for g in GRUPOS for f in g["campos"]}
_SEGREDO_MASC = "••••"


# ============================================================ leitura/escrita (com índices de lista)

def _ler(caminho):
    no = _charger()
    for parte in caminho.split("."):
        if isinstance(no, list) and parte.isdigit():
            i = int(parte)
            no = no[i] if i < len(no) else None
        elif isinstance(no, dict):
            no = no.get(parte)
        else:
            return None
        if no is None:
            return None
    return no


def _gravar(caminho, valor):
    partes = caminho.split(".")
    if not any(p.isdigit() for p in partes):
        definir(caminho, valor)
        return
    # caminho com índice (instagram.comptes.0.access_token) : reescreve a lista inteira
    i = next(k for k, p in enumerate(partes) if p.isdigit())
    base = ".".join(partes[:i])
    lista = list(_ler(base) or [])
    idx = int(partes[i])
    while len(lista) <= idx:
        lista.append({})
    item = dict(lista[idx] or {}) if isinstance(lista[idx], dict) else {}
    no = item
    for p in partes[i + 1:-1]:
        no = no.setdefault(p, {})
    no[partes[-1]] = valor
    lista[idx] = item
    definir(base, lista)


def _mascarar(v):
    v = str(v or "")
    return (_SEGREDO_MASC + v[-4:]) if len(v) >= 8 else (_SEGREDO_MASC if v else "")


def estado():
    grupos = []
    for g in GRUPOS:
        campos = []
        for f in g["campos"]:
            c = dict(f)
            if f["tipo"] == "arquivo":
                c["valor"] = (_RACINE / "google_credentials.json").exists()
            else:
                v = _ler(f["caminho"])
                if f["tipo"] == "secret":
                    c["valor"] = _mascarar(v)
                    c["definido"] = bool(v)
                else:
                    c["valor"] = v if v is not None else f["padrao"]
                    c["definido"] = v not in (None, "")
            campos.append(c)
        teste = g.get("teste") or []
        grupos.append({"id": g["id"], "nome": g["nome"], "icone": g["icone"],
                       "testes": [teste] if isinstance(teste, str) else list(teste), "campos": campos})
    return {"grupos": grupos}


def _converter(f, v):
    t = f["tipo"]
    if t == "bool":
        return bool(v)
    if t in ("int", "float", "nint", "nfloat"):
        if t.startswith("n") and (v is None or str(v).strip() == ""):
            return None
        try:
            n = int(str(v).strip()) if t.endswith("int") else float(str(v).replace(",", ".").strip())
        except ValueError:
            raise ValueError(f"{f['rotulo']}: número inválido")
        if f["min"] is not None and n < f["min"] or f["max"] is not None and n > f["max"]:
            raise ValueError(f"{f['rotulo']}: deve ficar entre {f['min']} e {f['max']}")
        return n
    v = "" if v is None else str(v).strip()
    if len(v) > 2000 or "\n" in v or "\r" in v:
        raise ValueError(f"{f['rotulo']}: valor inválido")
    if t == "select" and v and v not in f["opcoes"]:
        raise ValueError(f"{f['rotulo']}: opção inválida")
    if f["caminho"] == "signal_matin.heure" and v and not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
        raise ValueError("Horário no formato HH:MM")
    return v


def salvar(valores: dict, modo="local") -> dict:
    """Grava os campos enviados. modo != 'local' : campos `local` são recusados."""
    if not isinstance(valores, dict) or not valores:
        return {"ok": False, "message": "Nada para salvar."}
    pendentes, reinicio = [], False
    for caminho, v in valores.items():
        f = _CAMPOS.get(caminho)
        if f is None or f["tipo"] == "arquivo":
            return {"ok": False, "message": f"Campo não permitido: {str(caminho)[:60]}"}
        if f["local"] and modo != "local":
            return {"ok": False, "message": f"« {f['rotulo']} » só pode ser alterado no próprio PC."}
        if f["tipo"] == "secret":
            texto = str(v or "").strip()
            if texto.startswith(_SEGREDO_MASC) or texto == "":
                continue                         # mantém o segredo atual
            if texto == "__remover__":
                pendentes.append((caminho, ""))
                continue
            if len(texto) > 4000 or "\n" in texto:
                return {"ok": False, "message": f"{f['rotulo']}: valor inválido"}
            pendentes.append((caminho, texto))
        else:
            try:
                valor = _converter(f, v)
            except ValueError as e:
                return {"ok": False, "message": str(e)}
            atual = _ler(caminho)
            # Campo vazio que nunca foi definido : não cria chave vazia no config.yaml.
            if valor in ("", None) and atual in (None, ""):
                continue
            # Valor igual ao atual (ou ao padrão ainda não gravado) : nada a fazer.
            if valor == atual or (atual is None and valor == f["padrao"]):
                continue
            pendentes.append((caminho, valor))
        reinicio = reinicio or f["reinicio"]
    for caminho, v in pendentes:
        _gravar(caminho, v)
    _recarregar_modulos([c for c, _ in pendentes])
    msg = f"{len(pendentes)} configuração(ões) salva(s)."
    if reinicio:
        msg += " Algumas só valem após reiniciar o Jarvis."
    return {"ok": True, "message": msg, "reinicio": reinicio}


def _recarregar_modulos(caminhos):
    """Atualiza constantes lidas na importação, quando o módulo já está carregado."""
    import sys
    if any(c.startswith("hue.") for c in caminhos) and "tools.lumieres" in sys.modules:
        m = sys.modules["tools.lumieres"]
        for nome, chave in (("HUE_PONT", "hue.pont"), ("HUE_CLE", "hue.cle")):
            if hasattr(m, nome):
                setattr(m, nome, reglage(chave, ""))
    if any(c.startswith("mail.") for c in caminhos) and "tools.mail" in sys.modules:
        m = sys.modules["tools.mail"]
        if hasattr(m, "MAIL_ADRESSE"):
            m.MAIL_ADRESSE = reglage("mail.adresse", "")


def gerar_token():
    import secrets
    tok = secrets.token_urlsafe(32)
    definir("pont_iphone.token", tok)
    return {"ok": True, "token": tok, "message": "Token gerado. Copie agora para o Atalho do iPhone."}


def salvar_google_credentials(conteudo_b64: str) -> dict:
    try:
        brut = base64.b64decode(str(conteudo_b64 or ""), validate=True)
        dados = json.loads(brut.decode("utf-8"))
    except Exception:
        return {"ok": False, "message": "Arquivo JSON inválido."}
    bloco = dados.get("installed") or dados.get("web") if isinstance(dados, dict) else None
    if not isinstance(bloco, dict) or not bloco.get("client_id") or not bloco.get("client_secret"):
        return {"ok": False, "message": "Não é um JSON de credenciais OAuth do Google (falta installed/web)."}
    destino = _RACINE / str(reglage("agenda.credentials", "google_credentials.json") or "google_credentials.json")
    if _RACINE.resolve() not in destino.resolve().parents:
        destino = _RACINE / "google_credentials.json"
    destino.write_bytes(brut)
    return {"ok": True, "message": "Credenciais do Google salvas. Na primeira consulta à agenda, "
            "o navegador abrirá para você autorizar."}


# ============================================================ testes de conexão (somente leitura)

def _req():
    import requests
    return requests


def testar(grupo: str) -> dict:
    try:
        return {"hue": _t_hue, "mail": _t_mail, "twilio": _t_twilio, "discord": _t_discord,
                "spotify": _t_spotify, "hermes": _t_hermes, "obs": _t_obs}.get(
            grupo, lambda: {"ok": False, "message": "Sem teste para este grupo."})()
    except Exception as e:
        LOG.info("teste %s: %s", grupo, type(e).__name__)
        return {"ok": False, "message": f"Falha: {type(e).__name__}"}


def _t_hue():
    pont, cle = reglage("hue.pont", ""), reglage("hue.cle", "")
    if not pont or not cle:
        return {"ok": False, "message": "Preencha IP da ponte e chave."}
    r = _req().get(f"http://{pont}/api/{cle}/lights", timeout=5)
    d = r.json()
    if isinstance(d, list) and d and "error" in d[0]:
        return {"ok": False, "message": "Ponte respondeu, mas a chave foi recusada."}
    return {"ok": True, "message": f"Hue OK: {len(d)} lâmpada(s)."}


def _t_mail():
    import imaplib
    end, senha = reglage("mail.adresse", ""), reglage("mail.mot_de_passe_app", "")
    if not end or not senha:
        return {"ok": False, "message": "Preencha endereço e senha de app."}
    imap = imaplib.IMAP4_SSL("imap.gmail.com", timeout=10)
    try:
        imap.login(end, str(senha).replace(" ", ""))
        imap.logout()
    except imaplib.IMAP4.error:
        return {"ok": False, "message": "Gmail recusou o login. Use uma SENHA DE APP (não a senha normal)."}
    return {"ok": True, "message": "Gmail OK: login IMAP aceito."}


def _t_twilio():
    sid, tok = reglage("twilio.account_sid", ""), reglage("twilio.auth_token", "")
    if not sid or not tok:
        return {"ok": False, "message": "Preencha SID e token."}
    r = _req().get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json", auth=(sid, tok), timeout=10)
    if r.status_code != 200:
        return {"ok": False, "message": f"Twilio recusou (HTTP {r.status_code})."}
    return {"ok": True, "message": f"Twilio OK: conta {r.json().get('friendly_name', '')} ({r.json().get('status', '')})."}


def _t_discord():
    tok = reglage("discord.token", "")
    if not tok:
        return {"ok": False, "message": "Preencha o token do bot."}
    r = _req().get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bot {tok}"}, timeout=10)
    if r.status_code != 200:
        return {"ok": False, "message": f"Discord recusou o token (HTTP {r.status_code})."}
    return {"ok": True, "message": f"Discord OK: bot {r.json().get('username', '')}."}


def _t_spotify():
    cid, sec = reglage("spotify.client_id", ""), reglage("spotify.client_secret", "")
    if not cid or not sec:
        return {"ok": False, "message": "Preencha client ID e secret."}
    r = _req().post("https://accounts.spotify.com/api/token", data={"grant_type": "client_credentials"},
                    auth=(cid, sec), timeout=10)
    if r.status_code != 200:
        return {"ok": False, "message": f"Spotify recusou as credenciais (HTTP {r.status_code})."}
    login = "já autorizado" if reglage("spotify.refresh_token", "") else \
        "falta autorizar sua conta: rode scripts/spotify_login.py no PC"
    return {"ok": True, "message": f"Spotify OK: credenciais válidas ({login})."}


def _t_hermes():
    url = str(reglage("hermes.api_url", "http://127.0.0.1:8642") or "").rstrip("/")
    h = {"Authorization": f"Bearer {reglage('hermes.api_key', '')}"} if reglage("hermes.api_key", "") else {}
    for caminho in ("/health", "/v1/models"):
        try:
            r = _req().get(url + caminho, headers=h, timeout=6)
        except Exception:
            continue
        if r.status_code == 200:
            return {"ok": True, "message": f"Hermes OK ({caminho})."}
        if r.status_code in (401, 403):
            return {"ok": False, "message": "Hermes respondeu, mas recusou a chave."}
    return {"ok": False, "message": "Hermes não respondeu (VM/túnel desligado?)."}


def _t_obs():
    host, port = reglage("obs.host", "localhost"), int(reglage("obs.port", 4455) or 4455)
    try:
        socket.create_connection((host, port), 3).close()
    except OSError:
        return {"ok": False, "message": "OBS não está escutando (abra o OBS e ative o WebSocket)."}
    return {"ok": True, "message": "OBS OK: WebSocket acessível."}

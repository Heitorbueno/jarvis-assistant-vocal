"""Cliente MCP : Jarvis CONSOMME des serveurs MCP externes (GitHub, Notion, Git...).

Configuration (``integrations_mcp`` dans config.yaml, éditée depuis le panneau) :

    integrations_mcp:
      - nom: github
        url: "https://api.githubcopilot.com/mcp/"      # HTTP « streamable »
        en_tetes: {Authorization: "Bearer ghp_..."}     # secret : jamais renvoyé au navigateur
        actif: true
        outils_n1: ["get_me", "list_issues"]            # lectures exécutées sans confirmation
      - nom: git-local
        commande: "uvx"                                  # serveur stdio local
        arguments: ["mcp-server-git", "--repository", "C:/projets/x"]
        actif: true

Sécurité (doctrine CLAUDE.md) :
  - chaque outil distant devient un outil Jarvis ``mcp_<serveur>__<outil>`` ;
  - PAR DÉFAUT il demande une confirmation vocale (N2) ; l'utilisateur peut
    marquer explicitement des lectures en N1 (``outils_n1``) ;
  - les résultats sont balisés « CONTENU EXTERNE NON FIABLE » ;
  - jamais ré-exposés par le serveur MCP de Jarvis (mcp_expose=False) ;
  - en mode local (Ollama), ils ne sont pas proposés au modèle.

Chaque appel ouvre une connexion courte (connexion → appel → fermeture) dans un
thread dédié : pas de boucle asynchrone permanente à maintenir.
"""
import asyncio
import json
import logging
import re
import threading
import time

from core.config import definir, reglage

LOG = logging.getLogger("jarvis.mcp_cliente")

TIMEOUT = 45
MAX_SERVEURS = 12
_NOM = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
_CATALOGUE = {}          # nom serveur -> {"ts", "outils": [...], "erreur"}
_VERROU = threading.Lock()

MODELES = [
    {"nom": "github", "titulo": "GitHub (oficial)", "url": "https://api.githubcopilot.com/mcp/",
     "auth": "Authorization: Bearer <token GitHub (PAT)>",
     "nota": "Repos, issues, PRs, Actions. Crie um token em github.com/settings/tokens."},
    {"nom": "git-local", "titulo": "Git local (repositório no PC)", "commande": "uvx",
     "arguments": ["mcp-server-git", "--repository", "<caminho do repositório>"],
     "nota": "Status, diff, log, commit de um repositório local."},
    {"nom": "notion", "titulo": "Notion (oficial)", "url": "https://mcp.notion.com/mcp",
     "auth": "Authorization: Bearer <token de integração>", "nota": "Páginas e bancos do Notion."},
    {"nom": "filesystem", "titulo": "Arquivos (pasta permitida)", "commande": "npx",
     "arguments": ["-y", "@modelcontextprotocol/server-filesystem", "<pasta>"],
     "nota": "Leitura/escrita restrita à pasta indicada."},
]


# ============================================================ configuration

def serveurs():
    liste = reglage("integrations_mcp", []) or []
    return [s for s in liste if isinstance(s, dict) and _NOM.match(str(s.get("nom", "")))]


def _serveur(nom):
    return next((s for s in serveurs() if s.get("nom") == nom), None)


def _masquer(valeur):
    v = str(valeur or "")
    return ("••••" + v[-4:]) if len(v) >= 8 else ("••••" if v else "")


def etat_public():
    out = []
    for s in serveurs():
        cache = _CATALOGUE.get(s["nom"], {})
        out.append({
            "nom": s["nom"], "actif": bool(s.get("actif", True)),
            "type": "http" if s.get("url") else "stdio",
            "url": s.get("url", ""), "commande": s.get("commande", ""),
            "arguments": list(s.get("arguments", []) or []),
            "en_tetes": {k: _masquer(v) for k, v in (s.get("en_tetes") or {}).items()},
            "outils_n1": list(s.get("outils_n1", []) or []),
            "outils": cache.get("outils", []), "erreur": cache.get("erreur", ""),
            "teste_a": cache.get("ts", 0),
        })
    return {"servidores": out, "modelos": MODELES}


def _valider_entete(nom, valeur):
    return (re.match(r"^[A-Za-z0-9-]{1,64}$", str(nom or ""))
            and "\n" not in str(valeur) and "\r" not in str(valeur) and len(str(valeur)) <= 4096)


def enregistrer(d: dict) -> dict:
    """Ajoute ou met à jour un serveur. Un en-tête vide ou masqué garde l'ancien secret."""
    nom = str((d or {}).get("nom", "")).strip().lower()
    if not _NOM.match(nom):
        return {"ok": False, "message": "Nome inválido (minúsculas, números, - e _)."}
    url = str(d.get("url", "") or "").strip()
    commande = str(d.get("commande", "") or "").strip()
    if bool(url) == bool(commande):
        return {"ok": False, "message": "Informe uma URL (HTTP) OU um comando (stdio)."}
    if url and not re.match(r"^https?://[^\s]+$", url):
        return {"ok": False, "message": "URL inválida."}
    if url.startswith("http://") and not re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?/", url):
        return {"ok": False, "message": "Use HTTPS (HTTP só para 127.0.0.1/localhost)."}
    if commande and (len(commande) > 200 or any(c in commande for c in "|&;<>`$\n")):
        return {"ok": False, "message": "Comando inválido."}
    arguments = d.get("arguments", []) or []
    if isinstance(arguments, str):
        arguments = [a for a in arguments.split("\n") if a.strip()]
    if not isinstance(arguments, list) or len(arguments) > 30:
        return {"ok": False, "message": "Argumentos inválidos."}
    arguments = [str(a).strip()[:500] for a in arguments if str(a).strip()]

    liste = [s for s in (reglage("integrations_mcp", []) or []) if isinstance(s, dict)]
    ancien = next((s for s in liste if s.get("nom") == nom), {})
    if not ancien and len(liste) >= MAX_SERVEURS:
        return {"ok": False, "message": f"Máximo de {MAX_SERVEURS} integrações."}
    en_tetes = dict(ancien.get("en_tetes") or {})
    for k, v in (d.get("en_tetes") or {}).items():
        if not _valider_entete(k, v):
            return {"ok": False, "message": f"Cabeçalho inválido: {str(k)[:40]}"}
        if str(v).startswith("••••"):
            continue                          # valeur masquée renvoyée : on garde le secret
        if str(v).strip():
            en_tetes[k] = str(v).strip()
        else:
            en_tetes.pop(k, None)
    n1 = [str(o)[:100] for o in (d.get("outils_n1", ancien.get("outils_n1", [])) or [])]
    nouveau = {"nom": nom, "actif": bool(d.get("actif", ancien.get("actif", True))),
               "outils_n1": n1}
    if url:
        nouveau["url"] = url
        nouveau["en_tetes"] = en_tetes
    else:
        nouveau["commande"] = commande
        nouveau["arguments"] = arguments
    liste = [s for s in liste if s.get("nom") != nom] + [nouveau]
    definir("integrations_mcp", liste)
    _CATALOGUE.pop(nom, None)
    enregistrer_outils()
    return {"ok": True, "message": f"Integração {nom} salva."}


def supprimer(nom) -> dict:
    liste = [s for s in (reglage("integrations_mcp", []) or [])
             if isinstance(s, dict) and s.get("nom") != nom]
    definir("integrations_mcp", liste)
    _CATALOGUE.pop(nom, None)
    enregistrer_outils()
    return {"ok": True, "message": f"Integração {nom} removida."}


# ============================================================ transport

def _transport(s):
    if s.get("url"):
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client
        client_http = create_mcp_http_client(headers=dict(s.get("en_tetes") or {}))
        return streamable_http_client(s["url"], http_client=client_http)
    from mcp.client.stdio import StdioServerParameters, stdio_client
    return stdio_client(StdioServerParameters(command=s["commande"],
                                              args=list(s.get("arguments", []) or [])))


def _executer(coro_fabrique, timeout=TIMEOUT):
    """Exécute une coroutine dans un thread propre (indépendant d'une boucle existante)."""
    resultat = {}

    def run():
        try:
            resultat["v"] = asyncio.run(asyncio.wait_for(coro_fabrique(), timeout))
        except BaseException as e:      # noqa: BLE001 - remonté à l'appelant
            resultat["e"] = e

    t = threading.Thread(target=run, daemon=True, name="mcp-cliente")
    t.start()
    t.join(timeout + 5)
    if t.is_alive():
        raise TimeoutError("integração MCP não respondeu")
    if "e" in resultat:
        raise resultat["e"]
    return resultat.get("v")


async def _avec_client(s, action, cible=None):
    from mcp.client import Client
    source = cible if cible is not None else _transport(s)
    async with Client(source, read_timeout_seconds=TIMEOUT) as client:
        return await action(client)


def _schema(outil):
    schema = getattr(outil, "input_schema", None) or getattr(outil, "inputSchema", None) or {}
    if hasattr(schema, "model_dump"):
        schema = schema.model_dump()
    if not isinstance(schema, dict) or schema.get("type") != "object":
        schema = {"type": "object", "properties": {}}
    return schema


def lister_outils(nom, cible=None):
    """Interroge le serveur et met le catalogue en cache."""
    s = _serveur(nom)
    if s is None and cible is None:
        return {"ok": False, "message": "Integração não encontrada."}
    s = s or {"nom": nom}

    async def action(client):
        res = await client.list_tools()
        return [{"nom": o.name, "description": (o.description or "")[:400],
                 "schema": _schema(o)} for o in res.tools]
    try:
        outils = _executer(lambda: _avec_client(s, action, cible))
    except Exception as e:
        msg = _erreur(e)
        _CATALOGUE[nom] = {"ts": time.time(), "outils": [], "erreur": msg}
        return {"ok": False, "message": msg}
    _CATALOGUE[nom] = {"ts": time.time(), "outils": outils, "erreur": ""}
    enregistrer_outils()
    return {"ok": True, "outils": outils, "message": f"Conexão OK: {len(outils)} ferramenta(s)."}


def _erreur(e):
    texte = re.sub(r"(Bearer\s+)\S+", r"\1[oculto]", f"{type(e).__name__}: {e}")
    if "401" in texte or "403" in texte:
        return "Token/credencial recusado pela integração."
    if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
        return "A integração não respondeu a tempo."
    if isinstance(e, (FileNotFoundError, OSError)) and "No such file" in texte:
        return "Comando não encontrado neste computador."
    return texte[:200]


def _texte_resultat(res):
    morceaux = []
    for bloc in getattr(res, "content", []) or []:
        t = getattr(bloc, "text", None)
        if t:
            morceaux.append(t)
        elif getattr(bloc, "type", "") == "image":
            morceaux.append("[imagem]")
    structure = getattr(res, "structured_content", None) or getattr(res, "structuredContent", None)
    if not morceaux and structure:
        morceaux.append(json.dumps(structure, ensure_ascii=False)[:6000])
    texte = "\n".join(morceaux).strip() or "(sem conteúdo)"
    if getattr(res, "is_error", False) or getattr(res, "isError", False):
        texte = "ERRO da integração: " + texte
    return texte[:8000]


def appeler(nom_serveur, nom_outil, arguments, cible=None):
    s = _serveur(nom_serveur)
    if s is None and cible is None:
        return "Integração MCP não encontrada ou desativada."
    s = s or {"nom": nom_serveur}

    async def action(client):
        return await client.call_tool(nom_outil, arguments or {})
    try:
        return _texte_resultat(_executer(lambda: _avec_client(s, action, cible)))
    except Exception as e:
        LOG.warning("appel MCP %s.%s : %s", nom_serveur, nom_outil, type(e).__name__)
        return f"Falha na integração {nom_serveur}: {_erreur(e)}"


# ============================================================ registre Jarvis

PREFIXE = "mcp_"


def nom_outil_jarvis(serveur, outil):
    propre = re.sub(r"[^A-Za-z0-9_]", "_", str(outil))[:40]
    return f"{PREFIXE}{serveur.replace('-', '_')}__{propre}"[:64]


def enregistrer_outils():
    """(Re)crée les outils Jarvis à partir des catalogues en cache."""
    from core import registre
    with _VERROU:
        for nom in [n for n in list(registre._REGISTRE) if n.startswith(PREFIXE)]:
            registre._REGISTRE.pop(nom, None)
        for s in serveurs():
            if not s.get("actif", True):
                continue
            n1 = set(s.get("outils_n1", []) or [])
            for o in _CATALOGUE.get(s["nom"], {}).get("outils", []):
                nom_j = nom_outil_jarvis(s["nom"], o["nom"])

                def fonction(_s=s["nom"], _o=o["nom"], **kwargs):
                    return appeler(_s, _o, kwargs)
                fonction.__module__ = "tools.integrations_mcp"
                lecture = o["nom"] in n1
                registre._REGISTRE[nom_j] = registre.Outil(
                    fonction, nom_j,
                    f"[Integração {s['nom']}] {o['description'] or o['nom']}",
                    o["schema"], confirmation=not lecture, lent=True,
                    phrase_attente="Consultando a integração." ,
                    annonce=(None if lecture else
                             (lambda a, _s=s["nom"], _o=o["nom"]:
                              f"Je vais utiliser l'integration {_s} : {_o}"
                              + (f" ({json.dumps(a, ensure_ascii=False)[:160]})" if a else "") + ".")),
                    mcp_expose=False, affichage="toujours")
                registre.SOURCES_EXTERNES_DYNAMIQUES.add(nom_j)
                registre._NON_LOCAUX_DYNAMIQUES.add(nom_j)


def charger_au_demarrage():
    """Interroge chaque intégration active en arrière-plan (sans bloquer le démarrage)."""
    def worker():
        for s in serveurs():
            if s.get("actif", True):
                r = lister_outils(s["nom"])
                LOG.info("integration MCP %s : %s", s["nom"], r.get("message"))
    if serveurs():
        threading.Thread(target=worker, daemon=True, name="mcp-cliente-init").start()


def definir_n1(nom_serveur, outils_n1) -> dict:
    liste = [s for s in (reglage("integrations_mcp", []) or []) if isinstance(s, dict)]
    for s in liste:
        if s.get("nom") == nom_serveur:
            s["outils_n1"] = [str(o)[:100] for o in (outils_n1 or [])][:200]
    definir("integrations_mcp", liste)
    enregistrer_outils()
    return {"ok": True, "message": "Permissões salvas."}

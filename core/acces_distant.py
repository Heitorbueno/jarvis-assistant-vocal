"""Accès distant authentifié au panneau (Tailscale Serve, Cloudflare Tunnel, proxy HTTPS).

Par défaut RIEN ne change : le panneau et le cockpit restent strictement locaux
(voir core/http_local). L'accès distant ne s'ouvre que si l'utilisateur, depuis le
poste local, l'active ET déclare les noms d'hôte publics autorisés, puis génère un
code d'accès. Une requête distante est alors acceptée uniquement si :

  1. ``acces_distant.actif`` est vrai ;
  2. la socket vient du poste (le proxy Tailscale/cloudflared tourne en local) ou
     d'un réseau explicitement listé dans ``acces_distant.reseaux`` ;
  3. l'en-tête Host figure dans ``acces_distant.hotes`` (anti DNS rebinding : un
     domaine quelconque pointant vers le proxy est refusé) ;
  4. le navigateur présente un cookie de session signé (HMAC-SHA256), obtenu en
     saisissant le code d'accès sur /acesso.

Le code n'est jamais stocké en clair (PBKDF2-SHA256 salé) ; régénérer le code
change aussi le secret de signature, ce qui déconnecte toutes les sessions.
La configuration de l'accès distant elle-même reste modifiable en LOCAL uniquement.
"""

import base64
import hashlib
import hmac
import ipaddress
import logging
import secrets
import threading
import time

from core.config import definir, reglage
from core.http_local import _nom_hote, requete_locale

LOG = logging.getLogger("jarvis.acces")

COOKIE = "jarvis_sessao"
_ITERATIONS = 200_000
_MAX_ECHECS_IP = 5
_MAX_ECHECS_GLOBAL = 30
_FENETRE_ECHECS = 600  # secondes
_ECHECS: dict[str, list[float]] = {}
_VERROU = threading.Lock()
_NOM_HOTE_VALIDE = set("abcdefghijklmnopqrstuvwxyz0123456789-.")


# ============================================================ configuration

def actif() -> bool:
    return bool(reglage("acces_distant.actif", False))


def hotes() -> list[str]:
    valeurs = reglage("acces_distant.hotes", []) or []
    if isinstance(valeurs, str):
        valeurs = [valeurs]
    return [normaliser_hote(h) for h in valeurs if normaliser_hote(h)]


def reseaux() -> list[str]:
    valeurs = reglage("acces_distant.reseaux", []) or []
    if isinstance(valeurs, str):
        valeurs = [valeurs]
    return [str(v).strip() for v in valeurs if str(v).strip()]


def cockpit_autorise() -> bool:
    return bool(reglage("acces_distant.cockpit", False))


def duree_session() -> int:
    try:
        jours = int(reglage("acces_distant.duree_session_jours", 30))
    except (TypeError, ValueError):
        jours = 30
    return max(1, min(jours, 365)) * 86400


def code_defini() -> bool:
    return bool(reglage("acces_distant.code_hash", ""))


def normaliser_hote(valeur) -> str:
    """'https://Jarvis.ts.net:443/x' -> 'jarvis.ts.net' ; '' si invalide."""
    v = str(valeur or "").strip().lower()
    if "://" in v:
        v = v.split("://", 1)[1]
    v = v.split("/", 1)[0]
    v = _nom_hote(v)
    if not v or len(v) > 253 or not set(v) <= _NOM_HOTE_VALIDE or ".." in v:
        return ""
    if v in {"localhost", "127.0.0.1"} or v.startswith((".", "-")):
        return ""
    return v


def reseau_valide(valeur) -> bool:
    try:
        ipaddress.ip_network(str(valeur).strip(), strict=False)
        return True
    except ValueError:
        return False


def etat_public() -> dict:
    """Ce que le panneau local affiche (jamais le hash ni le secret)."""
    return {
        "actif": actif(),
        "hotes": hotes(),
        "reseaux": reseaux(),
        "cockpit": cockpit_autorise(),
        "code_defini": code_defini(),
        "duree_session_jours": duree_session() // 86400,
    }


def configurer(actif_=None, hotes_=None, reseaux_=None, cockpit=None, duree_jours=None) -> dict:
    """Écrit la configuration (appelé depuis le panneau LOCAL uniquement)."""
    if hotes_ is not None:
        propres, invalides = [], []
        for h in (hotes_ if isinstance(hotes_, list) else str(hotes_).split(",")):
            n = normaliser_hote(h)
            if n and n not in propres:
                propres.append(n)
            elif str(h).strip() and not n:
                invalides.append(str(h).strip()[:60])
        if invalides:
            return {"ok": False, "message": f"Host inválido : {', '.join(invalides)}"}
        definir("acces_distant.hotes", propres)
    if reseaux_ is not None:
        liste = reseaux_ if isinstance(reseaux_, list) else str(reseaux_).split(",")
        liste = [str(r).strip() for r in liste if str(r).strip()]
        mauvais = [r for r in liste if not reseau_valide(r)]
        if mauvais:
            return {"ok": False, "message": f"Rede (CIDR) inválida : {', '.join(mauvais)}"}
        definir("acces_distant.reseaux", liste)
    if cockpit is not None:
        definir("acces_distant.cockpit", bool(cockpit))
    if duree_jours is not None:
        try:
            definir("acces_distant.duree_session_jours", max(1, min(int(duree_jours), 365)))
        except (TypeError, ValueError):
            return {"ok": False, "message": "Duração inválida."}
    if actif_ is not None:
        if actif_ and not hotes():
            return {"ok": False, "message": "Adicione pelo menos um host antes de ativar."}
        if actif_ and not code_defini():
            return {"ok": False, "message": "Gere um código de acesso antes de ativar."}
        definir("acces_distant.actif", bool(actif_))
    return {"ok": True, "message": "Configuração de acesso remoto salva.", **etat_public()}


# ============================================================ code d'accès

def _hacher(code: str, sel: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), sel, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${sel.hex()}${dk.hex()}"


def generer_code() -> str:
    """Crée un nouveau code (renvoyé UNE fois) et invalide toutes les sessions."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    brut = "".join(secrets.choice(alphabet) for _ in range(16))
    code = "-".join(brut[i:i + 4] for i in range(0, 16, 4))
    definir("acces_distant.code_hash", _hacher(code, secrets.token_bytes(16)))
    definir("acces_distant.secret", secrets.token_hex(32))
    LOG.info("nouveau code d'acces distant genere (sessions precedentes invalidees)")
    return code


def _normaliser_code(code) -> str:
    return "".join(c for c in str(code or "").upper() if c.isalnum())


def verifier_code(code) -> bool:
    stocke = str(reglage("acces_distant.code_hash", "") or "")
    try:
        algo, iterations, sel_hex, attendu = stocke.split("$")
        if algo != "pbkdf2_sha256":
            return False
        propre = _normaliser_code(code)
        if len(propre) != 16:
            return False
        formate = "-".join(propre[i:i + 4] for i in range(0, 16, 4))
        dk = hashlib.pbkdf2_hmac("sha256", formate.encode("utf-8"),
                                 bytes.fromhex(sel_hex), int(iterations))
        return hmac.compare_digest(dk.hex(), attendu)
    except (ValueError, TypeError):
        return False


# ============================================================ limitation des essais

def _purger(maintenant: float) -> None:
    for cle in list(_ECHECS):
        _ECHECS[cle] = [t for t in _ECHECS[cle] if maintenant - t < _FENETRE_ECHECS]
        if not _ECHECS[cle]:
            del _ECHECS[cle]


def bloque(ip: str) -> bool:
    with _VERROU:
        maintenant = time.time()
        _purger(maintenant)
        return (len(_ECHECS.get(ip, [])) >= _MAX_ECHECS_IP
                or len(_ECHECS.get("*", [])) >= _MAX_ECHECS_GLOBAL)


def noter_echec(ip: str) -> None:
    with _VERROU:
        maintenant = time.time()
        _ECHECS.setdefault(ip, []).append(maintenant)
        _ECHECS.setdefault("*", []).append(maintenant)


def reinitialiser_echecs() -> None:
    with _VERROU:
        _ECHECS.clear()


# ============================================================ sessions

def _secret() -> bytes:
    s = str(reglage("acces_distant.secret", "") or "")
    return bytes.fromhex(s) if len(s) >= 32 else b""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def creer_session() -> str:
    secret = _secret()
    if not secret:
        raise RuntimeError("secret de session absent : genere un code d'acces")
    charge = f"{int(time.time()) + duree_session()}.{secrets.token_hex(8)}"
    sig = _b64(hmac.new(secret, charge.encode("ascii"), hashlib.sha256).digest())
    return f"{charge}.{sig}"


def session_valide(jeton) -> bool:
    secret = _secret()
    if not secret or not jeton:
        return False
    try:
        expiration, nonce, sig = str(jeton).split(".")
        charge = f"{expiration}.{nonce}"
        attendu = _b64(hmac.new(secret, charge.encode("ascii"), hashlib.sha256).digest())
        return hmac.compare_digest(sig, attendu) and int(expiration) > time.time()
    except (ValueError, TypeError):
        return False


# ============================================================ décision

def socket_autorisee(adresse) -> bool:
    adresse = str(adresse or "").strip().lower()
    if adresse in {"127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    for r in reseaux():
        try:
            if ip in ipaddress.ip_network(r, strict=False):
                return True
        except ValueError:
            continue
    return False


def hote_distant_autorise(valeur_host) -> bool:
    return actif() and _nom_hote(valeur_host) in set(hotes())


def contexte_distant(adresse_client, entetes) -> bool:
    """La requête arrive-t-elle par un chemin distant DÉCLARÉ (sans juger la session) ?"""
    return hote_distant_autorise(entetes.get("host")) and socket_autorisee(adresse_client)


def mode_acces(adresse_client, entetes, cookies, perimetre="panneau") -> str:
    """'local', 'distant' (session valide) ou '' (refus)."""
    if requete_locale(adresse_client, entetes):
        return "local"
    if perimetre == "cockpit" and not cockpit_autorise():
        return ""
    if perimetre not in {"panneau", "cockpit"}:
        return ""
    if contexte_distant(adresse_client, entetes) and session_valide((cookies or {}).get(COOKIE)):
        return "distant"
    return ""


def origine_distante_ok(valeur_origin, valeur_host) -> bool:
    """Écritures distantes : Origin absente refusée, sinon même hôte autorisé que Host."""
    from urllib.parse import urlsplit
    if not valeur_origin:
        return False
    try:
        morceaux = urlsplit(str(valeur_origin))
    except ValueError:
        return False
    hote = (morceaux.hostname or "").lower()
    return (morceaux.scheme == "https" and hote == _nom_hote(valeur_host)
            and hote in set(hotes()))


def ip_client(request) -> str:
    """IP pour la limitation d'essais (en-têtes du proxy local, sinon socket)."""
    for en_tete in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        v = request.headers.get(en_tete)
        if v:
            return v.split(",")[0].strip()[:64]
    return str(getattr(request.client, "host", "") or "")


# ============================================================ routes

_PAGE_LOGIN = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0f1115">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Jarvis">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/pwa/apple-touch-icon.png">
<title>Jarvis — Acesso</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--bord:#2a2f3a;--txt:#e6e8ec;--dim:#9aa2b1;--acc:#5b8cff;--ko:#ff6b6b}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
display:flex;align-items:center;justify-content:center;padding:16px}
form{width:100%;max-width:360px;background:var(--card);border:1px solid var(--bord);border-radius:16px;padding:24px}
h1{font-size:18px;margin:0 0 4px}p{color:var(--dim);margin:0 0 18px;font-size:13px}
input{width:100%;background:#1d222b;border:1px solid var(--bord);color:var(--txt);border-radius:10px;
padding:12px;font:16px ui-monospace,Consolas,monospace;letter-spacing:.08em;text-transform:uppercase}
button{width:100%;margin-top:12px;background:var(--acc);color:#fff;border:0;border-radius:10px;padding:12px;font-size:15px;cursor:pointer}
button:disabled{opacity:.6}#m{color:var(--ko);min-height:20px;margin-top:10px;font-size:13px}
</style></head><body>
<form id="f" autocomplete="off">
<h1>Jarvis</h1><p>Digite o código de acesso gerado no painel local.</p>
<input id="c" placeholder="XXXX-XXXX-XXXX-XXXX" autocapitalize="characters" spellcheck="false" required>
<button id="b">Entrar</button><div id="m"></div>
</form>
<script>
document.getElementById('f').addEventListener('submit',async e=>{
  e.preventDefault();const b=document.getElementById('b'),m=document.getElementById('m');b.disabled=true;m.textContent='';
  try{const r=await fetch('/api/acesso/entrar',{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-Jarvis-Panneau':'1'},
      body:JSON.stringify({codigo:document.getElementById('c').value})});
    const j=await r.json();if(j.ok){location.replace('/panneau');return}m.textContent=j.message||'Código inválido.';
  }catch(_){m.textContent='Falha de rede.'}b.disabled=false;});
if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});}
</script></body></html>"""


def monter_routes(app):
    """/ (accueil), /acesso (connexion distante), /api/acesso/*."""
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

    def adresse(request):
        return getattr(request.client, "host", "")

    def introuvable():
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    @app.get("/")
    def accueil(request: Request):
        mode = mode_acces(adresse(request), request.headers, request.cookies)
        if mode:
            return RedirectResponse("/panneau", status_code=302)
        if contexte_distant(adresse(request), request.headers):
            return RedirectResponse("/acesso", status_code=302)
        return introuvable()

    @app.get("/acesso")
    def page_acces(request: Request):
        if requete_locale(adresse(request), request.headers):
            return RedirectResponse("/panneau", status_code=302)
        if not contexte_distant(adresse(request), request.headers):
            return introuvable()
        return HTMLResponse(_PAGE_LOGIN, headers={
            "X-Frame-Options": "DENY", "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer"})

    @app.post("/api/acesso/entrar")
    async def entrer(request: Request):
        if not contexte_distant(adresse(request), request.headers):
            return introuvable()
        ct = (request.headers.get("content-type", "") or "").split(";")[0].strip().lower()
        if (ct != "application/json" or request.headers.get("x-jarvis-panneau") != "1"
                or not origine_distante_ok(request.headers.get("origin"), request.headers.get("host"))):
            return JSONResponse({"ok": False, "message": "Requisição recusada."}, status_code=403)
        ip = ip_client(request)
        if bloque(ip):
            return JSONResponse({"ok": False,
                                 "message": "Muitas tentativas. Aguarde 10 minutos."},
                                status_code=429)
        try:
            corps = await request.json()
        except Exception:
            corps = {}
        if not verifier_code((corps or {}).get("codigo")):
            noter_echec(ip)
            LOG.warning("acces distant : code refuse (%s)", ip)
            return JSONResponse({"ok": False, "message": "Código inválido."}, status_code=401)
        rep = JSONResponse({"ok": True})
        rep.set_cookie(COOKIE, creer_session(), max_age=duree_session(), httponly=True,
                       secure=True, samesite="strict", path="/")
        LOG.info("acces distant : session ouverte (%s)", ip)
        return rep

    @app.post("/api/acesso/sair")
    def sortir(request: Request):
        rep = JSONResponse({"ok": True})
        rep.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        return rep

    LOG.info("acces distant monte : / et /acesso (actif=%s)", actif())

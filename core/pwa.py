"""PWA du panneau Jarvis (installation desktop, Android et iOS).

Fichiers statiques publics et sans donnée personnelle : manifeste, service worker
et icônes. Ils ne sont servis qu'au poste local ou aux hôtes distants déclarés
(acces_distant.hotes), jamais sur un domaine inconnu (tunnel ngrok du pont iPhone).

Le service worker ne met en cache que l'enveloppe statique ; les pages et les
/api/* passent toujours par le réseau (aucune donnée de Jarvis n'est stockée sur
l'appareil). Installation iOS : Safari > Partager > « Sur l'écran d'accueil »,
uniquement en HTTPS (Tailscale Serve et Cloudflare Tunnel le fournissent).
"""
import json
from pathlib import Path

_DOSSIER = Path(__file__).resolve().parent.parent / "web" / "pwa"
VERSION = "jarvis-pwa-v1"

MANIFESTE = {
    "id": "/panneau",
    "name": "Jarvis — Painel",
    "short_name": "Jarvis",
    "description": "Configuração e controle do assistente Jarvis",
    "start_url": "/panneau?origem=pwa",
    "scope": "/",
    "display": "standalone",
    "display_override": ["standalone", "minimal-ui"],
    "orientation": "any",
    "background_color": "#0f1115",
    "theme_color": "#0f1115",
    "lang": "pt-BR",
    "icons": [
        {"src": "/pwa/icone-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/pwa/icone-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/pwa/icone-maskable-512.png", "sizes": "512x512", "type": "image/png",
         "purpose": "maskable"},
    ],
}

SERVICE_WORKER = """/* Service worker Jarvis : enveloppe statique uniquement, jamais /api ni les pages. */
const CACHE = '%s';
const STATIQUES = ['/manifest.webmanifest', '/pwa/icone-192.png', '/pwa/icone-512.png',
  '/pwa/apple-touch-icon.png', '/pwa/hors-ligne.html'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIQUES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('/pwa/hors-ligne.html')));
    return;
  }
  if (STATIQUES.includes(url.pathname)) {
    e.respondWith(caches.match(req).then(r => r || fetch(req)));
  }
});
""" % VERSION

_FICHIERS = {
    "icone-192.png": "image/png",
    "icone-512.png": "image/png",
    "icone-maskable-512.png": "image/png",
    "apple-touch-icon.png": "image/png",
    "favicon.png": "image/png",
    "hors-ligne.html": "text/html; charset=utf-8",
    "i18n.js": "application/javascript; charset=utf-8",
}


def balises_tete() -> str:
    """Balises à injecter dans le <head> des pages servies (panneau, cockpit)."""
    return (
        '<link rel="manifest" href="/manifest.webmanifest">'
        '<meta name="theme-color" content="#0f1115">'
        '<meta name="mobile-web-app-capable" content="yes">'
        '<meta name="apple-mobile-web-app-capable" content="yes">'
        '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">'
        '<meta name="apple-mobile-web-app-title" content="Jarvis">'
        '<link rel="apple-touch-icon" href="/pwa/apple-touch-icon.png">'
        '<link rel="icon" type="image/png" href="/pwa/favicon.png">'
        "<script>if('serviceWorker' in navigator){addEventListener('load',()=>"
        "navigator.serviceWorker.register('/sw.js').catch(()=>{}))}</script>"
    )


def injecter(html: str) -> str:
    """Ajoute les balises PWA et la traduction d'interface (assistant.langue)."""
    import re
    from core import langue
    code = langue.code()
    attr = f'lang="{"pt-BR" if code == "pt" else "fr"}" data-langue="{code}"'
    if re.search(r"<html\b", html):
        html = re.sub(r"<html\b[^>]*>", f"<html {attr}>", html, count=1)
    if "manifest.webmanifest" not in html:
        html = html.replace("</head>", balises_tete() + "</head>", 1)
    if "/pwa/i18n.js" not in html:
        html = html.replace("</head>", '<script src="/pwa/i18n.js" defer></script></head>', 1)
    return html


def _hote_permis(request) -> bool:
    from core import acces_distant
    from core.http_local import hote_local
    host = request.headers.get("host")
    return hote_local(host) or acces_distant.hote_distant_autorise(host)


def monter_routes(app):
    from fastapi import Request
    from fastapi.responses import JSONResponse, Response

    def introuvable():
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    @app.get("/manifest.webmanifest")
    def manifeste(request: Request):
        if not _hote_permis(request):
            return introuvable()
        return Response(json.dumps(MANIFESTE, ensure_ascii=False),
                        media_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js")
    def service_worker(request: Request):
        if not _hote_permis(request):
            return introuvable()
        return Response(SERVICE_WORKER, media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

    @app.get("/pwa/{nom}")
    def fichier(nom: str, request: Request):
        if not _hote_permis(request) or nom not in _FICHIERS:
            return introuvable()
        chemin = _DOSSIER / nom
        if not chemin.is_file():
            return introuvable()
        return Response(chemin.read_bytes(), media_type=_FICHIERS[nom],
                        headers={"Cache-Control": "public, max-age=86400"})

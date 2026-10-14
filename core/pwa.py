"""Interface PWA pública do Jarvis.

Somente arquivos estáticos, sem credenciais nem APIs administrativas.
A autorização para APIs remotas permanece em core.pont_iphone.
"""
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

_PUBLIC = Path(__file__).resolve().parent.parent / "web" / "pwa"
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'none'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'none'; connect-src 'self'; "
        "img-src 'self' data:; script-src 'self'; style-src 'self'; "
        "worker-src 'self'; manifest-src 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
}
_STATIC = {
    "app.css": "text/css",
    "app.js": "application/javascript",
    "icon.svg": "image/svg+xml",
}


def _arquivo(nome, tipo, *, html=False):
    cabecalhos = {
        **_SECURITY_HEADERS,
        "Cache-Control": "no-store, private" if html else "no-cache",
    }
    return FileResponse(_PUBLIC / nome, media_type=tipo, headers=cabecalhos)


def monter_routes(app):
    """Adiciona somente GET / e os arquivos estáticos do PWA."""

    @app.get("/", include_in_schema=False)
    def pagina_inicial():
        return _arquivo("index.html", "text/html; charset=utf-8", html=True)

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return _arquivo("manifest.webmanifest", "application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        resposta = _arquivo("sw.js", "application/javascript")
        resposta.headers["Service-Worker-Allowed"] = "/"
        return resposta

    @app.get("/pwa/{nome}", include_in_schema=False)
    def recurso_pwa(nome: str):
        tipo = _STATIC.get(nome)
        if tipo is None:
            raise HTTPException(status_code=404)
        return _arquivo(nome, tipo)

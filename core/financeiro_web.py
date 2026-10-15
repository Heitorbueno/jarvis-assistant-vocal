"""Rotas web do módulo financeiro (/financeiro + /api/financeiro/*).

Mesma proteção do cockpit : poste local, ou sessão remota autenticada SOMENTE se
``acces_distant.cockpit`` estiver ativo (dados financeiros = opt-in separado).
Escritas : JSON exato + X-Jarvis-Panneau + Origin (local ou mesmo host HTTPS).
Exclusão definitiva e credenciais Open Finance : somente no poste local.
"""
import base64
import logging
from pathlib import Path

from core import financeiro as fin
from core.config import definir, reglage

LOG = logging.getLogger("jarvis.financeiro")
_HTML = Path(__file__).resolve().parent.parent / "web" / "financeiro.html"


def monter_routes(app):
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    def _mode(request):
        from core.panneau import _mode as mode_panneau
        return mode_panneau(request, "cockpit")

    def garde(request, local=False):
        mode = _mode(request)
        if not mode or (local and mode != "local"):
            return JSONResponse({"ok": False, "message": "Financeiro acessível somente localmente."
                                 if local or not mode else "Acesso não autorizado."}, status_code=403)
        if request.method not in ("GET", "HEAD"):
            ct = (request.headers.get("content-type", "") or "").split(";")[0].strip().lower()
            if ct != "application/json":
                return JSONResponse({"ok": False, "message": "Content-Type invalide."}, status_code=415)
            if mode == "local":
                from core.http_local import origine_locale
                origem_ok = origine_locale(request.headers.get("origin"))
            else:
                from core.acces_distant import origine_distante_ok
                origem_ok = origine_distante_ok(request.headers.get("origin"), request.headers.get("host"))
            if request.headers.get("x-jarvis-panneau") != "1" or not origem_ok:
                return JSONResponse({"ok": False, "message": "Requete refusee."}, status_code=403)
        return None

    async def corpo(request):
        try:
            d = await request.json()
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def protegido(fn):
        try:
            return fn()
        except ValueError as e:
            return JSONResponse({"ok": False, "message": str(e)[:200]}, status_code=400)

    @app.get("/financeiro")
    def pagina(request: Request):
        if (r := garde(request)):
            return r
        from core.pwa import injecter
        return HTMLResponse(injecter(_HTML.read_text(encoding="utf-8")),
                            headers={"X-Frame-Options": "DENY", "Cache-Control": "no-store",
                                     "Referrer-Policy": "no-referrer"})

    @app.get("/api/financeiro/resumo")
    def api_resumo(request: Request, dias: int = 30):
        if (r := garde(request)):
            return r
        return {"resumo": fin.resumo(), "fluxo": fin.fluxo_caixa(dias), "contas": fin.contas(),
                "modo": _mode(request), "pluggy": fin.pluggy_configurado()}

    @app.get("/api/financeiro/lancamentos")
    def api_listar(request: Request, tipo: str = "", status: str = "aberto", de: str = "",
                   ate: str = "", busca: str = "", conta_id: int = 0):
        if (r := garde(request)):
            return r
        return protegido(lambda: {"itens": fin.listar(tipo or None, status or None, de or None,
                                                      ate or None, conta_id or None, busca[:60])})

    @app.get("/api/financeiro/categorias")
    def api_categorias(request: Request):
        return garde(request) or fin.categorias()

    @app.post("/api/financeiro/lancar")
    async def api_lancar(request: Request):
        if (r := garde(request)):
            return r
        d = await corpo(request)
        return fin.lancar(d.get("tipo"), d.get("descricao"), d.get("valor"), d.get("vencimento"),
                          d.get("conta_id") or None, d.get("categoria"), d.get("recorrencia", "nenhuma"),
                          d.get("parcelas", 1), d.get("contraparte", ""), d.get("observacao", ""))

    @app.post("/api/financeiro/editar")
    async def api_editar(request: Request):
        if (r := garde(request)):
            return r
        d = await corpo(request)
        return fin.editar(int(d.get("id", 0)), {k: v for k, v in d.items() if k != "id"})

    @app.post("/api/financeiro/baixar")
    async def api_baixar(request: Request):
        if (r := garde(request)):
            return r
        d = await corpo(request)
        return fin.baixar(int(d.get("id", 0)), d.get("data") or None, d.get("valor") or None,
                          d.get("conta_id") or None)

    @app.post("/api/financeiro/estornar")
    async def api_estornar(request: Request):
        if (r := garde(request)):
            return r
        return fin.estornar(int((await corpo(request)).get("id", 0)))

    @app.post("/api/financeiro/cancelar")
    async def api_cancelar(request: Request):
        if (r := garde(request)):
            return r
        return fin.cancelar(int((await corpo(request)).get("id", 0)))

    @app.post("/api/financeiro/excluir")
    async def api_excluir(request: Request):
        if (r := garde(request, local=True)):
            return r
        return fin.excluir(int((await corpo(request)).get("id", 0)))

    @app.get("/api/financeiro/contas")
    def api_contas(request: Request):
        return garde(request) or {"contas": fin.contas(incluir_inativas=True), "tipos": fin.TIPOS_CONTA,
                                  "padrao": reglage("financeiro.conta_padrao", "")}

    @app.post("/api/financeiro/contas")
    async def api_conta_salvar(request: Request):
        if (r := garde(request)):
            return r
        d = await corpo(request)
        res = fin.conta_salvar(d)
        if res.get("ok") and d.get("padrao"):
            definir("financeiro.conta_padrao", str(d.get("nome", "")))
        return res

    @app.post("/api/financeiro/importar-ofx")
    async def api_ofx(request: Request):
        if (r := garde(request)):
            return r
        d = await corpo(request)
        try:
            brut = base64.b64decode(str(d.get("conteudo", "")), validate=True)
        except Exception:
            return {"ok": False, "message": "Arquivo OFX inválido."}
        if len(brut) > 10 * 1024 * 1024:
            return {"ok": False, "message": "Arquivo maior que 10 MB."}
        return fin.importar_ofx(brut, d.get("conta_id"))

    @app.get("/api/financeiro/extrato")
    def api_extrato(request: Request, conta_id: int = 0, pendentes: int = 1):
        if (r := garde(request)):
            return r
        return {"itens": fin.extrato(conta_id or None, bool(pendentes)),
                "sugestoes": fin.conciliar_sugestoes(conta_id or None)}

    @app.post("/api/financeiro/conciliar")
    async def api_conciliar(request: Request):
        if (r := garde(request)):
            return r
        d = await corpo(request)
        return fin.conciliar(int(d.get("extrato_id", 0)), d.get("lancamento_id") or None)

    @app.get("/api/financeiro/openfinance")
    def api_of(request: Request):
        if (r := garde(request)):
            return r
        return {"configurado": fin.pluggy_configurado(),
                "client_id": reglage("financeiro.pluggy.client_id", "") and "••••" + str(
                    reglage("financeiro.pluggy.client_id", ""))[-4:],
                "itens": list(reglage("financeiro.pluggy.itens", []) or [])}

    @app.post("/api/financeiro/openfinance")
    async def api_of_salvar(request: Request):
        if (r := garde(request, local=True)):
            return r
        d = await corpo(request)
        import re
        for chave in ("client_id", "client_secret"):
            v = str(d.get(chave, "") or "").strip()
            if v and not v.startswith("••••"):
                if not re.match(r"^[A-Za-z0-9-]{8,100}$", v):
                    return {"ok": False, "message": f"{chave} inválido."}
                definir(f"financeiro.pluggy.{chave}", v)
        if "itens" in d:
            itens = [str(i).strip() for i in (d.get("itens") or []) if str(i).strip()][:20]
            if any(not re.match(r"^[A-Za-z0-9-]{8,64}$", i) for i in itens):
                return {"ok": False, "message": "itemId inválido."}
            definir("financeiro.pluggy.itens", itens)
        return {"ok": True, "message": "Open Finance salvo."}

    @app.post("/api/financeiro/sincronizar")
    async def api_sync(request: Request):
        if (r := garde(request)):
            return r
        return fin.pluggy_sincronizar(int((await corpo(request)).get("dias", 30) or 30))

    @app.get("/api/financeiro/exportar.csv")
    def api_csv(request: Request):
        if (r := garde(request)):
            return r
        return Response("﻿" + fin.exportar_csv(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=jarvis-financeiro.csv"})

    LOG.info("financeiro monte : /financeiro (local ; distant si acces_distant.cockpit)")

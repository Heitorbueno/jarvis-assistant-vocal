"""Widgets do HUD : clima, câmbio, bolsa, notícias e mídia (YouTube, Spotify,
Netflix, Prime Video).

- Catálogo (« loja ») : o usuário instala/remove cada widget e escolhe a coluna
  (esquerda/direita) no painel, aba « Widgets ». Configuração em ``widgets`` no
  config.yaml ; sem configuração, nenhum widget aparece (HUD original).
- Fontes gratuitas e sem chave :
    clima   -> Open-Meteo (forecast + geocoding) ;
    câmbio  -> AwesomeAPI (economia.awesomeapi.com.br) ;
    bolsa   -> Yahoo Finance (chart v8, não oficial) ; brapi.dev se ``widgets.brapi_token`` ;
    notícias-> feeds RSS configuráveis (padrão : g1).
- Cada fonte tem cache (TTL) e falha isolada : um widget com erro não derruba os
  outros. Os dados ficam no servidor local ; o HUD só lê /api/widgets.
- Netflix e Prime Video bloqueiam incorporação (DRM / X-Frame-Options) : o widget
  é um atalho que abre o serviço. YouTube e Spotify são incorporados (players
  oficiais youtube-nocookie.com e open.spotify.com/embed).
"""
import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from core.config import definir, reglage

LOG = logging.getLogger("jarvis.widgets")
_UA = "Mozilla/5.0 (Jarvis assistant; +https://github.com/Heitorbueno/jarvis-assistant-vocal)"
_CACHE = {}
_VERROU = threading.Lock()

CATALOGO = [
    {"id": "clima", "nome": "Clima", "coluna": "direita", "tipo": "dados",
     "descricao": "Temperatura agora, sensação, umidade, vento e previsão de 3 dias.",
     "fonte": "Open-Meteo (gratuito, sem chave)", "ttl": 600},
    {"id": "cambio", "nome": "Câmbio", "coluna": "direita", "tipo": "dados",
     "descricao": "Dólar, euro e bitcoin em reais, com variação do dia.",
     "fonte": "AwesomeAPI (gratuito, sem chave)", "ttl": 120},
    {"id": "bolsa", "nome": "Bolsa", "coluna": "direita", "tipo": "dados",
     "descricao": "Ibovespa e ações escolhidas (ex.: PETR4, VALE3, ITUB4).",
     "fonte": "Yahoo Finance (não oficial) ou brapi.dev com token", "ttl": 300},
    {"id": "noticias", "nome": "Notícias", "coluna": "esquerda", "tipo": "dados",
     "descricao": "Últimas manchetes dos feeds RSS escolhidos.",
     "fonte": "RSS (padrão: g1)", "ttl": 900},
    {"id": "youtube", "nome": "YouTube", "coluna": "esquerda", "tipo": "midia",
     "descricao": "Player de um vídeo ou playlist do YouTube.",
     "fonte": "youtube-nocookie.com/embed (oficial)", "ttl": 0},
    {"id": "spotify", "nome": "Spotify", "coluna": "esquerda", "tipo": "midia",
     "descricao": "Player de uma playlist, álbum, faixa ou podcast do Spotify.",
     "fonte": "open.spotify.com/embed (oficial)", "ttl": 0},
    {"id": "netflix", "nome": "Netflix", "coluna": "esquerda", "tipo": "atalho",
     "descricao": "Atalho para a Netflix (não permite player incorporado).",
     "fonte": "netflix.com", "ttl": 0},
    {"id": "primevideo", "nome": "Prime Video", "coluna": "esquerda", "tipo": "atalho",
     "descricao": "Atalho para o Prime Video (não permite player incorporado).",
     "fonte": "primevideo.com", "ttl": 0},
]
_IDS = {w["id"]: w for w in CATALOGO}

_FEEDS_PADRAO = ["https://g1.globo.com/rss/g1/"]
_MOEDAS_PADRAO = ["USD-BRL", "EUR-BRL", "BTC-BRL"]
_ACOES_PADRAO = ["^BVSP", "PETR4.SA", "VALE3.SA", "ITUB4.SA"]

_WMO_PT = {
    0: "céu limpo", 1: "predomínio de sol", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina com geada", 51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 66: "chuva congelante",
    67: "chuva congelante forte", 71: "neve fraca", 73: "neve", 75: "neve forte",
    77: "grãos de neve", 80: "pancadas fracas", 81: "pancadas de chuva",
    82: "pancadas fortes", 85: "pancadas de neve", 86: "pancadas fortes de neve",
    95: "trovoada", 96: "trovoada com granizo", 99: "trovoada forte com granizo",
}
_ICONES = {0: "☀", 1: "🌤", 2: "⛅", 3: "☁", 45: "🌫", 48: "🌫", 51: "🌦", 53: "🌦", 55: "🌧",
           61: "🌧", 63: "🌧", 65: "🌧", 80: "🌦", 81: "🌧", 82: "⛈", 95: "⛈", 96: "⛈", 99: "⛈"}


# ============================================================ configuração

def instalados():
    valores = reglage("widgets.instalados", []) or []
    out = []
    for w in valores:
        if isinstance(w, str):
            w = {"id": w}
        if isinstance(w, dict) and w.get("id") in _IDS:
            coluna = "esquerda" if w.get("coluna") == "esquerda" else (
                "direita" if w.get("coluna") == "direita" else _IDS[w["id"]]["coluna"])
            out.append({"id": w["id"], "coluna": coluna})
    return out


def parametros():
    return {
        "cidade": str(reglage("widgets.cidade", "") or reglage("meteo.ville", "") or ""),
        "moedas": list(reglage("widgets.moedas", _MOEDAS_PADRAO) or _MOEDAS_PADRAO),
        "acoes": list(reglage("widgets.acoes", _ACOES_PADRAO) or _ACOES_PADRAO),
        "feeds": list(reglage("widgets.feeds", _FEEDS_PADRAO) or _FEEDS_PADRAO),
        "youtube": str(reglage("widgets.youtube", "") or ""),
        "spotify": str(reglage("widgets.spotify", "") or ""),
        "visivel": bool(reglage("widgets.visivel", True)),
        "brapi_token_definido": bool(reglage("widgets.brapi_token", "")),
    }


def catalogo():
    ins = {w["id"]: w for w in instalados()}
    return {"catalogo": [{**w, "instalado": w["id"] in ins,
                          "coluna_atual": ins.get(w["id"], {}).get("coluna", w["coluna"])}
                         for w in CATALOGO],
            "parametros": parametros()}


def instalar(wid, coluna=None):
    if wid not in _IDS:
        return {"ok": False, "message": "Widget desconhecido."}
    lista = [w for w in instalados() if w["id"] != wid]
    lista.append({"id": wid, "coluna": coluna if coluna in ("esquerda", "direita")
                  else _IDS[wid]["coluna"]})
    definir("widgets.instalados", lista)
    return {"ok": True, "message": f"Widget {_IDS[wid]['nome']} instalado."}


def remover(wid):
    definir("widgets.instalados", [w for w in instalados() if w["id"] != wid])
    return {"ok": True, "message": "Widget removido."}


def mover(wid, direcao):
    lista = instalados()
    i = next((k for k, w in enumerate(lista) if w["id"] == wid), None)
    if i is None:
        return {"ok": False, "message": "Widget não instalado."}
    j = i + (1 if direcao == "baixo" else -1)
    if 0 <= j < len(lista):
        lista[i], lista[j] = lista[j], lista[i]
        definir("widgets.instalados", lista)
    return {"ok": True, "message": "Ordem salva."}


_URL = re.compile(r"^https://[^\s<>\"']{4,500}$")
_TICKER = re.compile(r"^\^?[A-Z0-9.=\-]{1,15}$")
_PAR = re.compile(r"^[A-Z]{3,4}-[A-Z]{3,4}$")


def definir_parametros(d: dict) -> dict:
    d = d or {}
    if "cidade" in d:
        cidade = " ".join(str(d["cidade"] or "").split())[:80]
        definir("widgets.cidade", cidade)
        _CACHE.pop("clima", None)
        _CACHE.pop("geo", None)
    if "moedas" in d:
        moedas = [str(m).strip().upper() for m in (d["moedas"] or []) if str(m).strip()][:8]
        if any(not _PAR.match(m) for m in moedas):
            return {"ok": False, "message": "Moeda inválida (formato USD-BRL)."}
        definir("widgets.moedas", moedas)
        _CACHE.pop("cambio", None)
    if "acoes" in d:
        acoes = [str(a).strip().upper() for a in (d["acoes"] or []) if str(a).strip()][:10]
        acoes = [a if (a.startswith("^") or "." in a or not re.match(r"^[A-Z]{4}\d{1,2}$", a))
                 else a + ".SA" for a in acoes]
        if any(not _TICKER.match(a) for a in acoes):
            return {"ok": False, "message": "Código de ação inválido."}
        definir("widgets.acoes", acoes)
        _CACHE.pop("bolsa", None)
    if "feeds" in d:
        feeds = [str(f).strip() for f in (d["feeds"] or []) if str(f).strip()][:6]
        if any(not _URL.match(f) for f in feeds):
            return {"ok": False, "message": "Feed RSS inválido (use https://)."}
        definir("widgets.feeds", feeds)
        _CACHE.pop("noticias", None)
    for chave in ("youtube", "spotify"):
        if chave in d:
            url = str(d[chave] or "").strip()
            if url and not _URL.match(url):
                return {"ok": False, "message": f"Link do {chave} inválido."}
            if url and (chave == "youtube" and not embed_youtube(url)
                        or chave == "spotify" and not embed_spotify(url)):
                return {"ok": False, "message": f"Não reconheci o link do {chave}."}
            definir(f"widgets.{chave}", url)
    if "visivel" in d:
        definir("widgets.visivel", bool(d["visivel"]))
    if "brapi_token" in d:
        tok = str(d["brapi_token"] or "").strip()
        if tok and not re.match(r"^[A-Za-z0-9_-]{8,100}$", tok):
            return {"ok": False, "message": "Token brapi inválido."}
        definir("widgets.brapi_token", tok)
        _CACHE.pop("bolsa", None)
    return {"ok": True, "message": "Configuração dos widgets salva."}


# ============================================================ mídia

def embed_youtube(url):
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    hote = (u.hostname or "").lower()
    q = urllib.parse.parse_qs(u.query)
    if hote.endswith("youtube.com") or hote.endswith("youtube-nocookie.com"):
        if q.get("list"):
            lista = q["list"][0]
            if re.match(r"^[A-Za-z0-9_-]{10,64}$", lista):
                return f"https://www.youtube-nocookie.com/embed/videoseries?list={lista}"
        vid = (q.get("v") or [""])[0]
        if not vid:
            m = re.match(r"^/(?:embed|shorts|live)/([A-Za-z0-9_-]{11})", u.path)
            vid = m.group(1) if m else ""
    elif hote == "youtu.be":
        vid = u.path.strip("/")[:11]
    else:
        return ""
    return f"https://www.youtube-nocookie.com/embed/{vid}" if re.match(r"^[A-Za-z0-9_-]{11}$", vid) else ""


def embed_spotify(url):
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    if (u.hostname or "").lower() != "open.spotify.com":
        return ""
    m = re.match(r"^/(?:intl-[a-z-]+/)?(?:embed/)?(playlist|album|track|artist|show|episode)/([A-Za-z0-9]{22})", u.path)
    return f"https://open.spotify.com/embed/{m.group(1)}/{m.group(2)}" if m else ""


# ============================================================ fontes

def _json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _cache(chave, ttl, fabrique):
    with _VERROU:
        c = _CACHE.get(chave)
        if c and time.time() - c["ts"] < ttl:
            return c["v"]
    try:
        v = fabrique()
        v = {"ok": True, **v}
    except Exception as e:
        LOG.warning("widget %s : %s", chave, e)
        anterior = (_CACHE.get(chave) or {}).get("v")
        if anterior and anterior.get("ok"):
            return {**anterior, "desatualizado": True}
        v = {"ok": False, "erro": f"Fonte indisponível ({type(e).__name__})."}
    with _VERROU:
        _CACHE[chave] = {"ts": time.time(), "v": v}
    return v


def _local():
    cidade = parametros()["cidade"]

    def fab():
        if cidade:
            q = urllib.parse.quote(cidade)
            res = _json(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=pt")
            r = (res.get("results") or [None])[0]
            if r:
                return {"lat": r["latitude"], "lon": r["longitude"],
                        "cidade": r.get("name", cidade), "uf": r.get("admin1", "")}
        d = _json("http://ip-api.com/json/?fields=status,lat,lon,city,regionName")
        if d.get("status") == "success":
            return {"lat": d["lat"], "lon": d["lon"], "cidade": d.get("city", ""),
                    "uf": d.get("regionName", "")}
        raise RuntimeError("localização indisponível")
    v = _cache("geo", 86400, fab)
    if not v.get("ok"):
        raise RuntimeError(v.get("erro", "localização indisponível"))
    return v


def clima():
    def fab():
        lugar = _local()
        d = _json("https://api.open-meteo.com/v1/forecast?"
                  f"latitude={lugar['lat']}&longitude={lugar['lon']}&timezone=auto"
                  "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
                  "weather_code,wind_speed_10m,is_day"
                  "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
                  "precipitation_probability_max&forecast_days=4")
        c, dia = d["current"], d["daily"]
        prev = []
        for i in range(1, min(4, len(dia["time"]))):
            prev.append({"data": dia["time"][i], "max": round(dia["temperature_2m_max"][i]),
                         "min": round(dia["temperature_2m_min"][i]),
                         "chuva": (dia.get("precipitation_probability_max") or [None] * 4)[i],
                         "icone": _ICONES.get(dia["weather_code"][i], "·")})
        codigo = c.get("weather_code", 0)
        return {"cidade": lugar["cidade"], "uf": lugar.get("uf", ""),
                "temp": round(c["temperature_2m"]), "sensacao": round(c.get("apparent_temperature", c["temperature_2m"])),
                "umidade": c.get("relative_humidity_2m"), "vento": round(c.get("wind_speed_10m", 0)),
                "descricao": _WMO_PT.get(codigo, "tempo variável"),
                "icone": ("🌙" if codigo in (0, 1) and not c.get("is_day", 1) else _ICONES.get(codigo, "·")),
                "max": round(dia["temperature_2m_max"][0]), "min": round(dia["temperature_2m_min"][0]),
                "previsao": prev}
    return _cache("clima", _IDS["clima"]["ttl"], fab)


def cambio():
    def fab():
        pares = parametros()["moedas"]
        d = _json("https://economia.awesomeapi.com.br/json/last/" + ",".join(pares))
        out = []
        for par in pares:
            v = d.get(par.replace("-", ""))
            if not v:
                continue
            out.append({"par": par, "nome": v.get("name", par).split("/")[0],
                        "valor": float(v["bid"]), "variacao": float(v.get("pctChange") or 0),
                        "hora": v.get("create_date", "")})
        if not out:
            raise RuntimeError("sem cotações")
        return {"cotacoes": out}
    return _cache("cambio", _IDS["cambio"]["ttl"], fab)


def _yahoo(simbolo):
    d = _json("https://query1.finance.yahoo.com/v8/finance/chart/"
              + urllib.parse.quote(simbolo) + "?range=1d&interval=1d")
    meta = d["chart"]["result"][0]["meta"]
    preco = float(meta["regularMarketPrice"])
    anterior = float(meta.get("chartPreviousClose") or meta.get("previousClose") or preco)
    return {"simbolo": simbolo, "nome": "Ibovespa" if simbolo == "^BVSP" else simbolo.replace(".SA", ""),
            "valor": preco, "variacao": (preco / anterior - 1) * 100 if anterior else 0.0,
            "moeda": meta.get("currency", "BRL")}


def _brapi(simbolos, token):
    lista = ",".join(s.replace(".SA", "") for s in simbolos)
    d = _json(f"https://brapi.dev/api/quote/{urllib.parse.quote(lista, safe=',^')}?token={token}")
    out = []
    for r in d.get("results", []):
        s = r.get("symbol", "")
        out.append({"simbolo": s, "nome": "Ibovespa" if s == "^BVSP" else s,
                    "valor": float(r.get("regularMarketPrice") or 0),
                    "variacao": float(r.get("regularMarketChangePercent") or 0),
                    "moeda": r.get("currency", "BRL")})
    return out


def bolsa():
    def fab():
        simbolos = parametros()["acoes"]
        token = str(reglage("widgets.brapi_token", "") or "")
        if token:
            try:
                ativos = _brapi(simbolos, token)
                if ativos:
                    return {"ativos": ativos, "fonte": "brapi.dev"}
            except Exception as e:
                LOG.info("brapi indisponivel (%s), repli Yahoo", type(e).__name__)
        ativos = []
        for s in simbolos:
            try:
                ativos.append(_yahoo(s))
            except Exception as e:
                LOG.info("yahoo %s : %s", s, type(e).__name__)
        if not ativos:
            raise RuntimeError("sem cotações da bolsa")
        return {"ativos": ativos, "fonte": "Yahoo Finance"}
    return _cache("bolsa", _IDS["bolsa"]["ttl"], fab)


def _rss(url, limite=8):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=8) as r:
        brut = r.read(2_000_000)
    racine = ET.fromstring(brut)
    itens = []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for item in racine.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if titulo:
            itens.append({"titulo": titulo[:200], "link": link if link.startswith("https://") else ""})
        if len(itens) >= limite:
            break
    if not itens:
        for e in racine.findall("a:entry", ns):
            titulo = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
            l = e.find("a:link", ns)
            link = l.get("href", "") if l is not None else ""
            if titulo:
                itens.append({"titulo": titulo[:200], "link": link if link.startswith("https://") else ""})
            if len(itens) >= limite:
                break
    fonte = (racine.findtext("channel/title") or urllib.parse.urlsplit(url).hostname or "").strip()
    return fonte[:40], itens


def noticias():
    def fab():
        manchetes = []
        for url in parametros()["feeds"]:
            try:
                fonte, itens = _rss(url)
                manchetes += [{**i, "fonte": fonte} for i in itens]
            except Exception as e:
                LOG.info("rss %s : %s", url, type(e).__name__)
        if not manchetes:
            raise RuntimeError("nenhum feed respondeu")
        return {"manchetes": manchetes[:10]}
    return _cache("noticias", _IDS["noticias"]["ttl"], fab)


_FONTES = {"clima": clima, "cambio": cambio, "bolsa": bolsa, "noticias": noticias}


def dados_hud():
    """Layout + dados de cada widget instalado (lido pelo HUD a cada minuto)."""
    p = parametros()
    saida = []
    for w in instalados():
        item = {"id": w["id"], "coluna": w["coluna"], "nome": _IDS[w["id"]]["nome"],
                "tipo": _IDS[w["id"]]["tipo"]}
        if w["id"] in _FONTES:
            item["dados"] = _FONTES[w["id"]]()
        elif w["id"] == "youtube":
            item["dados"] = {"ok": bool(embed_youtube(p["youtube"])), "embed": embed_youtube(p["youtube"]),
                             "erro": "" if p["youtube"] else "Defina o link no painel › Widgets."}
        elif w["id"] == "spotify":
            item["dados"] = {"ok": bool(embed_spotify(p["spotify"])), "embed": embed_spotify(p["spotify"]),
                             "erro": "" if p["spotify"] else "Defina o link no painel › Widgets."}
        elif w["id"] == "netflix":
            item["dados"] = {"ok": True, "url": "https://www.netflix.com/browse"}
        elif w["id"] == "primevideo":
            item["dados"] = {"ok": True, "url": "https://www.primevideo.com/"}
        saida.append(item)
    return {"visivel": p["visivel"], "widgets": saida, "ts": int(time.time())}


def aquecer():
    """Pré-carrega as fontes em segundo plano (início do HUD)."""
    def worker():
        for w in instalados():
            f = _FONTES.get(w["id"])
            if f:
                f()
    threading.Thread(target=worker, daemon=True, name="widgets").start()

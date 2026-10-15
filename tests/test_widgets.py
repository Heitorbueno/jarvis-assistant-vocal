"""Widgets do HUD : catalogo, fontes (formatos reais simulados), midia e ferramentas de voz."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import config, widgets

OPEN_METEO = {"current": {"temperature_2m": 33.4, "apparent_temperature": 36.1,
                          "relative_humidity_2m": 41, "weather_code": 2, "wind_speed_10m": 9.6, "is_day": 1},
              "daily": {"time": ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17"],
                        "weather_code": [2, 61, 3, 0], "temperature_2m_max": [35, 31, 33, 36],
                        "temperature_2m_min": [23, 22, 22, 24],
                        "precipitation_probability_max": [10, 80, 20, 0]}}
GEO = {"results": [{"latitude": -15.6, "longitude": -56.1, "name": "Cuiabá", "admin1": "Mato Grosso"}]}
AWESOME = {"USDBRL": {"name": "Dólar Americano/Real Brasileiro", "bid": "5.4321", "pctChange": "-0.42",
                      "create_date": "2026-10-14 17:00:00"},
           "EURBRL": {"name": "Euro/Real Brasileiro", "bid": "6.10", "pctChange": "0.10"},
           "BTCBRL": {"name": "Bitcoin/Real Brasileiro", "bid": "350000", "pctChange": "1.5"}}


def _yahoo(simb, preco, ant):
    return {"chart": {"result": [{"meta": {"symbol": simb, "currency": "BRL",
                                           "regularMarketPrice": preco, "chartPreviousClose": ant}}]}}


def faux_json(url, timeout=8):
    if "geocoding" in url:
        return GEO
    if "open-meteo.com/v1/forecast" in url:
        return OPEN_METEO
    if "awesomeapi" in url:
        return AWESOME
    if "yahoo" in url:
        return _yahoo("^BVSP", 130500.0, 129000.0) if "BVSP" in url else _yahoo("PETR4.SA", 38.5, 39.0)
    raise OSError("bloqueado")


RSS = b"""<?xml version="1.0"?><rss><channel><title>g1</title>
<item><title>Manchete 1</title><link>https://g1.globo.com/a</link></item>
<item><title>Manchete 2 &lt;script&gt;</title><link>javascript:alert(1)</link></item>
</channel></rss>"""


class _Conf:
    def __init__(self, d=None):
        self.d = d or {}

    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        self._p = [patch.object(config, "_CONFIG", self.d),
                   patch.object(config, "FICHIER", Path(self._t.name) / "c.yaml"),
                   patch.object(widgets, "_json", side_effect=faux_json)]
        for p in self._p:
            p.start()
        widgets._CACHE.clear()
        return self.d

    def __exit__(self, *a):
        for p in reversed(self._p):
            p.stop()
        self._t.cleanup()
        widgets._CACHE.clear()


class WidgetsTest(unittest.TestCase):
    def test_sem_configuracao_nenhum_widget(self):
        with _Conf():
            self.assertEqual(widgets.dados_hud()["widgets"], [])

    def test_loja_instalar_mover_remover(self):
        with _Conf():
            self.assertFalse(widgets.instalar("inexistente")["ok"])
            widgets.instalar("clima")
            widgets.instalar("cambio", "esquerda")
            self.assertEqual([w["id"] for w in widgets.instalados()], ["clima", "cambio"])
            self.assertEqual(widgets.instalados()[1]["coluna"], "esquerda")
            widgets.mover("cambio", "cima")
            self.assertEqual(widgets.instalados()[0]["id"], "cambio")
            widgets.remover("clima")
            self.assertEqual([w["id"] for w in widgets.instalados()], ["cambio"])

    def test_fontes(self):
        with _Conf({"widgets": {"cidade": "Cuiabá", "acoes": ["^BVSP", "PETR4.SA"]}}):
            c = widgets.clima()
            self.assertTrue(c["ok"])
            self.assertEqual((c["cidade"], c["temp"], c["descricao"]), ("Cuiabá", 33, "parcialmente nublado"))
            self.assertEqual(len(c["previsao"]), 3)
            m = widgets.cambio()
            self.assertAlmostEqual(m["cotacoes"][0]["valor"], 5.4321)
            b = widgets.bolsa()
            self.assertEqual(b["ativos"][0]["nome"], "Ibovespa")
            self.assertGreater(b["ativos"][0]["variacao"], 1.0)

    def test_noticias_rss_e_links_seguros(self):
        class R:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self, n=-1): return RSS
        with _Conf(), patch.object(widgets.urllib.request, "urlopen", return_value=R()):
            n = widgets.noticias()
        self.assertTrue(n["ok"])
        self.assertEqual(n["manchetes"][0]["link"], "https://g1.globo.com/a")
        self.assertEqual(n["manchetes"][1]["link"], "")          # javascript: descartado

    def test_falha_isolada_e_cache_desatualizado(self):
        with _Conf():
            widgets.instalar("cambio")
            widgets.instalar("noticias")
            self.assertTrue(widgets.cambio()["ok"])
            widgets._CACHE["cambio"]["ts"] = 0
            with patch.object(widgets, "_json", side_effect=OSError("rede")):
                v = widgets.cambio()
            self.assertTrue(v["ok"] and v["desatualizado"])
            d = {w["id"]: w for w in widgets.dados_hud()["widgets"]}
            self.assertFalse(d["noticias"]["dados"]["ok"])           # RSS bloqueado, o resto segue

    def test_midia(self):
        self.assertEqual(widgets.embed_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
                         "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ")
        self.assertIn("videoseries?list=PL", widgets.embed_youtube(
            "https://www.youtube.com/playlist?list=PL1234567890abcdef"))
        self.assertEqual(widgets.embed_youtube("https://youtu.be/dQw4w9WgXcQ?t=3"),
                         "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ")
        self.assertEqual(widgets.embed_youtube("https://evil.com/watch?v=dQw4w9WgXcQ"), "")
        self.assertEqual(widgets.embed_spotify("https://open.spotify.com/intl-pt/playlist/37i9dQZF1DXcBWIGoYBM5M?si=1"),
                         "https://open.spotify.com/embed/playlist/37i9dQZF1DXcBWIGoYBM5M")
        self.assertEqual(widgets.embed_spotify("https://spotify.evil.com/playlist/37i9dQZF1DXcBWIGoYBM5M"), "")

    def test_validacao_parametros(self):
        with _Conf() as d:
            self.assertFalse(widgets.definir_parametros({"moedas": ["dolar"]})["ok"])
            self.assertFalse(widgets.definir_parametros({"feeds": ["http://inseguro/rss"]})["ok"])
            self.assertFalse(widgets.definir_parametros({"youtube": "https://exemplo.com/x"})["ok"])
            self.assertTrue(widgets.definir_parametros({"acoes": ["petr4", "^BVSP"]})["ok"])
            self.assertEqual(d["widgets"]["acoes"], ["PETR4.SA", "^BVSP"])

    def test_ferramentas_de_voz(self):
        from core import registre
        from tools.widgets_hud import cotacoes
        with _Conf({"widgets": {"acoes": ["^BVSP"]}}):
            txt = cotacoes("tudo")
        self.assertIn("USD R$ 5,43", txt)
        self.assertIn("Ibovespa 130.500", txt)
        self.assertIn("CONTENU EXTERNE", registre.baliser_externe("noticias", "x"))


if __name__ == "__main__":
    unittest.main()

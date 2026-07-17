# -*- coding: utf-8 -*-
"""Adaptadores de fuentes de datos gratuitas.

Cada adaptador es independiente: si una fuente falla, devuelve None o una
lista vacia y el resto del sistema sigue funcionando. Para sustituir una
fuente basta con cambiar el adaptador correspondiente.
"""
import json
import time
import email.utils
from datetime import datetime, timezone

import requests
import feedparser

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 briefing-personal/1.0"}
TIMEOUT = 20


def _get_json(url, params=None, headers=None):
    try:
        r = requests.get(url, params=params, headers=headers or UA, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[aviso] fallo al pedir {url}: {e}")
        return None


# ---------------------------------------------------------------- Yahoo Finance
def yahoo_series(symbol):
    """Serie diaria de ~1 anio para un simbolo de Yahoo Finance.

    Devuelve dict con precio actual, variaciones a 1 dia / 1 semana / 1 mes /
    1 anio, una serie corta para el sparkline y los cierres del anio completo
    ("cierres", uso interno del modulo de senales; generate.py los retira
    antes de publicar markets.json). Datos con retraso, suficientes para un
    briefing diario.
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    data = _get_json(url, params={"range": "1y", "interval": "1d"})
    if not data:
        return None
    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
        closes = result["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) < 2:
            return None
        price = meta.get("regularMarketPrice") or closes[-1]

        def pct(back):
            if len(closes) > back and closes[-1 - back]:
                return round((price / closes[-1 - back] - 1) * 100, 2)
            return None

        return {
            "symbol": symbol,
            "precio": round(price, 4),
            "moneda": meta.get("currency"),
            "d1": pct(1),
            "w1": pct(5),
            "m1": pct(21),
            "y1": round((price / closes[0] - 1) * 100, 2) if len(closes) > 200 else None,
            "spark": [round(c, 4) for c in closes[-30:]],
            "cierres": [round(c, 4) for c in closes],
        }
    except Exception as e:
        print(f"[aviso] datos inesperados de Yahoo para {symbol}: {e}")
        return None


def yahoo_watchlist(watchlist):
    """Recorre la watchlist y devuelve los datos de mercado por grupo."""
    grupos = []
    for grupo in watchlist.get("grupos", []):
        activos = []
        for a in grupo.get("activos", []):
            serie = yahoo_series(a["symbol"])
            if serie:
                serie["nombre"] = a.get("nombre", a["symbol"])
                activos.append(serie)
            time.sleep(0.4)  # respeto a la fuente gratuita
        grupos.append({"id": grupo["id"], "nombre": grupo["nombre"], "activos": activos})
    return grupos


def yahoo_historico(symbol, desde_iso):
    """Cierres diarios de un simbolo desde una fecha (AAAA-MM-DD) hasta hoy.

    Devuelve {"moneda": ..., "serie": [(fecha_iso, cierre), ...]} ordenado por
    fecha, o None si la fuente falla. Sirve para valorar posiciones de la
    cartera compradas en el pasado y para comparar con un indice en el mismo
    periodo.
    """
    try:
        desde = datetime.strptime(desde_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        print(f"[aviso] fecha invalida '{desde_iso}' para {symbol} (formato AAAA-MM-DD)")
        return None
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    data = _get_json(url, params={
        "period1": int(desde.timestamp()),
        "period2": int(datetime.now(timezone.utc).timestamp()),
        "interval": "1d",
    })
    if not data:
        return None
    try:
        result = data["chart"]["result"][0]
        tiempos = result["timestamp"]
        cierres = result["indicators"]["quote"][0]["close"]
        serie = []
        for t, c in zip(tiempos, cierres):
            if c is not None:
                fecha = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
                serie.append((fecha, round(c, 4)))
        if not serie:
            return None
        return {"moneda": result["meta"].get("currency"), "serie": serie}
    except Exception as e:
        print(f"[aviso] historico inesperado de Yahoo para {symbol}: {e}")
        return None


def yahoo_cambio_divisa(de, a, desde_iso):
    """Serie del tipo de cambio de la moneda 'de' a la moneda 'a' desde una fecha.

    Usa el par de Yahoo (p. ej. USDEUR=X). Si ambas monedas coinciden devuelve
    una serie constante de 1 para simplificar al que llama.
    """
    if de == a:
        hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return {"moneda": a, "serie": [(desde_iso, 1.0), (hoy, 1.0)]}
    return yahoo_historico(f"{de}{a}=X", desde_iso)


# ------------------------------------------------------------------- CoinGecko
def coingecko_global():
    """Dominancia de BTC y capitalizacion total del mercado cripto."""
    data = _get_json("https://api.coingecko.com/api/v3/global")
    if not data:
        return None
    try:
        d = data["data"]
        return {
            "dominancia_btc": round(d["market_cap_percentage"]["btc"], 1),
            "cap_total_usd": int(d["total_market_cap"]["usd"]),
            "variacion_cap_24h": round(d.get("market_cap_change_percentage_24h_usd", 0), 2),
        }
    except Exception:
        return None


# ------------------------------------------------------------- Fear and Greed
def fear_and_greed():
    """Indice Fear & Greed del mercado cripto (alternative.me, gratuito)."""
    data = _get_json("https://api.alternative.me/fng/?limit=1")
    try:
        item = data["data"][0]
        return {"valor": int(item["value"]), "texto": item["value_classification"]}
    except Exception:
        return None


# ------------------------------------------------------------------------ FRED
def fred_serie(serie_id, intentos=2):
    """Ultimo valor de una serie de FRED via CSV publico (sin clave).

    FRED responde a veces lento desde los servidores de GitHub Actions, asi que
    se usa un timeout holgado y un reintento antes de rendirse.
    """
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    for intento in range(1, intentos + 1):
        try:
            r = requests.get(url, params={"id": serie_id}, headers=UA, timeout=40)
            r.raise_for_status()
            filas = [f for f in r.text.strip().splitlines()[1:] if "," in f]
            for fila in reversed(filas):
                fecha, valor = fila.split(",", 1)
                if valor not in (".", ""):
                    return {"serie": serie_id, "fecha": fecha, "valor": float(valor)}
            return None
        except Exception as e:
            print(f"[aviso] FRED {serie_id} (intento {intento}/{intentos}): {e}")
            if intento < intentos:
                time.sleep(2)
    return None


def indicadores_macro():
    """Indicadores macro de referencia desde FRED."""
    series = {
        "T10Y2Y": "Curva de tipos USA (10a - 2a)",
        "DGS2": "Bono USA 2 años",
        "DGS10": "Bono USA 10 años",
        "BAMLH0A0HYM2": "High yield spread",
    }
    out = []
    for sid, nombre in series.items():
        dato = fred_serie(sid)
        if dato:
            dato["nombre"] = nombre
            out.append(dato)
    return out


# ------------------------------------------------------------------- Noticias
def _fecha_entrada(entry):
    for campo in ("published", "updated"):
        valor = entry.get(campo)
        if valor:
            try:
                return email.utils.parsedate_to_datetime(valor).astimezone(timezone.utc)
            except Exception:
                pass
    return None


def leer_feeds(feeds_config, max_por_feed=8, max_total=60):
    """Lee todos los feeds RSS y devuelve titulares recientes deduplicados."""
    items = []
    vistos = set()
    for feed in feeds_config.get("feeds", []):
        try:
            parsed = feedparser.parse(feed["url"], request_headers=UA)
            for entry in parsed.entries[:max_por_feed]:
                titulo = (entry.get("title") or "").strip()
                if not titulo:
                    continue
                clave = titulo.lower()[:80]
                if clave in vistos:
                    continue
                vistos.add(clave)
                fecha = _fecha_entrada(entry)
                items.append({
                    "titulo": titulo,
                    "resumen": (entry.get("summary") or "")[:400],
                    "fuente": feed["fuente"],
                    "url": entry.get("link", ""),
                    "fecha": fecha.isoformat() if fecha else None,
                })
        except Exception as e:
            print(f"[aviso] feed {feed['fuente']}: {e}")
    items.sort(key=lambda i: i["fecha"] or "", reverse=True)
    return items[:max_total]

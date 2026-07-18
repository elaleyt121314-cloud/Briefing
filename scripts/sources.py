# -*- coding: utf-8 -*-
"""Adaptadores de fuentes de datos gratuitas.

Cada adaptador es independiente: si una fuente falla, devuelve None o una
lista vacia y el resto del sistema sigue funcionando. Para sustituir una
fuente basta con cambiar el adaptador correspondiente.
"""
import csv
import io
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


# Bolsas europeas que cotizan en euros: se prefieren al resolver un ISIN para
# que los datos cuadren con Trade Republic (que muestra todo en euros).
_BOLSAS_EUR = (".DE", ".F", ".SG", ".MU", ".BE", ".DU", ".HM", ".AS", ".MI", ".PA", ".MC", ".VI")
_isin_cache = {}


def yahoo_resolver_isin(isin):
    """Traduce un ISIN (el que muestra Trade Republic) al mejor simbolo de Yahoo.

    Prefiere una cotizacion europea en euros y valida que tenga datos antes de
    devolverla. Devuelve {"symbol": ..., "nombre": ...} o None. Se cachea por
    ejecucion para no repetir busquedas.
    """
    isin = isin.strip().upper()
    if isin in _isin_cache:
        return _isin_cache[isin]
    resultado = None
    data = _get_json("https://query1.finance.yahoo.com/v1/finance/search",
                     params={"q": isin, "quotesCount": 10})
    if data:
        quotes = [q for q in data.get("quotes", []) if q.get("symbol")]
        # Euro primero; dentro de cada grupo, se respeta el orden de Yahoo.
        quotes.sort(key=lambda q: 0 if any(q["symbol"].endswith(s) for s in _BOLSAS_EUR) else 1)
        for q in quotes:
            if yahoo_series(q["symbol"]):  # nos aseguramos de que hay datos reales
                resultado = {"symbol": q["symbol"],
                             "nombre": q.get("longname") or q.get("shortname") or q["symbol"]}
                break
    if not resultado:
        print(f"[aviso] no se pudo resolver el ISIN {isin} a un activo con datos")
    _isin_cache[isin] = resultado
    return resultado


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


# ------------------------------------------------------------- Tesoro EE. UU.
def _treasury_filas(anio):
    """Filas de la curva de tipos diaria del Tesoro para un anio (mas recientes
    primero). Fuente oficial sin clave, accesible desde GitHub Actions (a
    diferencia de FRED, que limita las IPs de centros de datos)."""
    url = (f"https://home.treasury.gov/resource-center/data-chart-center/"
           f"interest-rates/daily-treasury-rates.csv/{anio}/all")
    r = requests.get(url, params={"type": "daily_treasury_yield_curve", "_format": "csv"},
                     headers=UA, timeout=30)
    r.raise_for_status()
    filas = list(csv.reader(io.StringIO(r.text)))
    return filas[0], filas[1:]  # cabecera, datos


def treasury_curva():
    """Bono a 2 y 10 anios y la pendiente 10a-2a, del Tesoro de EE. UU."""
    try:
        anio = datetime.now(timezone.utc).year
        cabecera, filas = _treasury_filas(anio)
        if not filas:  # a primeros de enero el anio nuevo aun no tiene datos
            cabecera, filas = _treasury_filas(anio - 1)
        idx = {c.strip(): i for i, c in enumerate(cabecera)}
        fila = filas[0]  # la mas reciente
        fecha = datetime.strptime(fila[idx["Date"]], "%m/%d/%Y").strftime("%Y-%m-%d")
        dos = float(fila[idx["2 Yr"]])
        diez = float(fila[idx["10 Yr"]])
    except Exception as e:
        print(f"[aviso] Tesoro EE.UU. (curva de tipos): {e}")
        return []
    return [
        {"serie": "US2Y", "nombre": "Bono USA 2 años", "valor": round(dos, 2),
         "fecha": fecha, "unidad": "%", "fuente": "Tesoro EE. UU."},
        {"serie": "US10Y", "nombre": "Bono USA 10 años", "valor": round(diez, 2),
         "fecha": fecha, "unidad": "%", "fuente": "Tesoro EE. UU."},
        {"serie": "US10Y2Y", "nombre": "Curva de tipos USA (10a - 2a)",
         "valor": round(diez - dos, 2), "fecha": fecha, "unidad": " pp",
         "fuente": "Tesoro EE. UU."},
    ]


# ------------------------------------------------------------------------ FRED
def fred_serie(serie_id, timeout=8):
    """Ultimo valor de una serie de FRED via CSV publico (sin clave).

    FRED limita las IPs de centros de datos, asi que desde GitHub Actions
    suele dar timeout. Se usa solo para datos que no hay en otra fuente
    (high yield spread), en modo "mejor esfuerzo": si responde, se usa; si no,
    el resto del bloque macro (curva del Tesoro) se publica igualmente.
    """
    try:
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                         params={"id": serie_id}, headers=UA, timeout=timeout)
        r.raise_for_status()
        filas = [f for f in r.text.strip().splitlines()[1:] if "," in f]
        for fila in reversed(filas):
            fecha, valor = fila.split(",", 1)
            if valor not in (".", ""):
                return {"serie": serie_id, "fecha": fecha, "valor": float(valor)}
    except Exception as e:
        print(f"[aviso] FRED {serie_id}: {e}")
    return None


def indicadores_macro():
    """Bloque macro: curva de tipos del Tesoro (fiable) + high yield de FRED
    (mejor esfuerzo, solo disponible ahi)."""
    out = treasury_curva()
    hy = fred_serie("BAMLH0A0HYM2")
    if hy:
        out.append({"serie": "HY", "nombre": "High yield spread", "valor": round(hy["valor"], 2),
                    "fecha": hy["fecha"], "unidad": "%", "fuente": "FRED"})
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


def noticias_de_activo(symbol, max_items=6):
    """Titulares recientes de un activo concreto (feed por simbolo de Yahoo).

    Sirve para el apartado de impacto personal: noticias de las posiciones de
    la cartera. Funciona incluso con el simbolo europeo (TKE.F devuelve las
    noticias de Take-Two). Titulares en ingles; la IA los resume en espanol.
    """
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
    items = []
    try:
        parsed = feedparser.parse(url, request_headers=UA)
        for entry in parsed.entries[:max_items]:
            titulo = (entry.get("title") or "").strip()
            if not titulo:
                continue
            fecha = _fecha_entrada(entry)
            items.append({
                "titulo": titulo,
                "fuente": (entry.get("source", {}) or {}).get("title") or "Yahoo Finanzas",
                "url": entry.get("link", ""),
                "fecha": fecha.isoformat() if fecha else None,
            })
    except Exception as e:
        print(f"[aviso] noticias de {symbol}: {e}")
    return items


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

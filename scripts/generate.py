# -*- coding: utf-8 -*-
"""Proceso diario del briefing.

1. Lee la configuracion (watchlist y feeds).
2. Recupera datos de mercado, cripto, macro y noticias de fuentes gratuitas.
3. Pide a la IA que redacte el briefing usando SOLO esos datos.
4. Escribe los JSON que consume la web estatica.

Se ejecuta desde GitHub Actions cada manana o manualmente.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import sources
import cartera
import senales
import llm

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RAIZ, "data")
CONFIG = os.path.join(RAIZ, "config")


def leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def escribir_json(nombre, contenido):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, nombre), "w", encoding="utf-8") as f:
        json.dump(contenido, f, ensure_ascii=False, indent=1)
    print(f"[ok] data/{nombre}")


def movimientos_destacados(grupos, umbral=2.0):
    """Activos con movimiento diario superior al umbral, para que la IA los explique."""
    out = []
    for g in grupos:
        for a in g["activos"]:
            if a.get("d1") is not None and abs(a["d1"]) >= umbral:
                out.append({"nombre": a["nombre"], "variacion_dia_pct": a["d1"], "grupo": g["nombre"]})
    return out


def main():
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    watchlist = leer_json(os.path.join(CONFIG, "watchlist.json"))
    feeds = leer_json(os.path.join(CONFIG, "feeds.json"))

    print("== 1/5 datos de mercado (Yahoo Finance, con retraso) ==")
    grupos = sources.yahoo_watchlist(watchlist)

    print("== 2/5 cripto y sentimiento ==")
    cripto_global = sources.coingecko_global()
    fng = sources.fear_and_greed()

    print("== 3/5 indicadores macro (FRED) ==")
    macro = sources.indicadores_macro()

    print("== 4/5 noticias (RSS) ==")
    noticias = sources.leer_feeds(feeds)

    print("== 5/5 cartera personal ==")
    ruta_cartera = os.path.join(CONFIG, "cartera.json")
    config_cartera = leer_json(ruta_cartera) if os.path.exists(ruta_cartera) else {}
    datos_cartera = cartera.calcular(config_cartera)

    # El contexto tecnico de las senales se construye antes de publicar
    # markets.json, porque usa los cierres del anio que luego se retiran
    # (la web no los necesita y abultarian el archivo).
    activos_senales, sentimiento = senales.construir(grupos, {"fear_and_greed": fng})
    for g in grupos:
        for a in g["activos"]:
            a.pop("cierres", None)

    escribir_json("markets.json", {"actualizado": ahora, "grupos": grupos})
    escribir_json("extras.json", {
        "actualizado": ahora,
        "cripto_global": cripto_global,
        "fear_and_greed": fng,
        "macro": macro,
    })
    escribir_json("news.json", {"actualizado": ahora, "items": noticias[:30]})
    datos_cartera["actualizado"] = ahora
    escribir_json("cartera.json", datos_cartera)

    contexto = {
        "fecha_utc": ahora,
        "mercados": [
            {
                "grupo": g["nombre"],
                "activos": [
                    {"nombre": a["nombre"], "precio": a["precio"], "dia_pct": a["d1"],
                     "semana_pct": a["w1"], "mes_pct": a["m1"]}
                    for a in g["activos"]
                ],
            }
            for g in grupos
        ],
        "movimientos_destacados_mas_de_2pct": movimientos_destacados(grupos),
        "cripto_global": cripto_global,
        "fear_and_greed_cripto": fng,
        "indicadores_macro_fred": macro,
        # Contexto compacto: 20 titulares con resumen corto bastan para el briefing
        # y mantienen la peticion ligera para el nivel gratuito de la IA.
        "titulares_recientes": [
            {"titulo": n["titulo"], "fuente": n["fuente"], "resumen": n["resumen"][:140]}
            for n in noticias[:20]
        ],
    }

    briefing = llm.generar_briefing(contexto)
    escribir_json("briefing.json", {
        "actualizado": ahora,
        "generado_con_ia": briefing is not None,
        "contenido": briefing,
    })

    print("== señales (técnico calculado + veredicto IA) ==")
    # A la IA solo van los activos invertibles (los instrumentos de contexto,
    # como el VIX, se publican con su tecnico pero sin veredicto).
    contexto_senales = {
        "fecha_utc": ahora,
        "sentimiento": sentimiento,
        "activos": [
            {"symbol": a["symbol"], "nombre": a["nombre"], "grupo": a["grupo"],
             "d1": a["d1"], "m1": a["m1"], "y1": a["y1"], "tecnico": a["tecnico"]}
            for a in activos_senales if a["con_veredicto"]
        ],
    }
    respuesta = llm.generar_senales(contexto_senales)
    por_symbol = {}
    if respuesta:
        for s in respuesta.get("activos", []):
            if s.get("symbol") and s.get("veredicto"):
                por_symbol[s["symbol"]] = {
                    "veredicto": s["veredicto"],
                    "confianza": s.get("confianza"),
                    "resumen": s.get("resumen"),
                    "a_favor": s.get("a_favor") or [],
                    "en_contra": s.get("en_contra") or [],
                }
    for a in activos_senales:
        a["senal"] = por_symbol.get(a["symbol"]) if a["con_veredicto"] else None
    escribir_json("senales.json", {
        "actualizado": ahora,
        "generado_con_ia": bool(por_symbol),
        "sentimiento": sentimiento,
        "activos": activos_senales,
    })

    escribir_json("meta.json", {"actualizado": ahora, "version": 1})
    print("== proceso completado ==")


if __name__ == "__main__":
    main()

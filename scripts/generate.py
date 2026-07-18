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


def resolver_isins(entradas):
    """Rellena 'symbol' (y 'nombre' si falta) en las entradas que solo traen
    'isin'. Asi el usuario puede pegar el ISIN que ve en Trade Republic y el
    sistema encuentra el activo. Las entradas con 'symbol' explicito no se tocan.
    """
    salida = []
    for e in entradas:
        if not e.get("symbol") and e.get("isin"):
            r = sources.yahoo_resolver_isin(e["isin"])
            if not r:
                print(f"[aviso] se omite {e.get('nombre') or e['isin']}: ISIN sin activo con datos")
                continue
            e = dict(e)
            e["symbol"] = r["symbol"]
            e.setdefault("nombre", r["nombre"])
        salida.append(e)
    return salida


def impacto_cartera(datos_cartera):
    """Para cada posicion real, recoge sus noticias del dia y pide a la IA un
    resumen que relacione su marcha con esas noticias. Devuelve la lista lista
    para pintar en la carta (o [] si no hay posiciones). Las noticias se
    muestran aunque la IA falle; el resumen es un extra."""
    posiciones = datos_cartera.get("posiciones") or []
    if not posiciones:
        return []
    salida = []
    for p in posiciones:
        noticias = sources.noticias_de_activo(p["symbol"])
        salida.append({
            "symbol": p["symbol"], "nombre": p["nombre"], "pl_pct": p["pl_pct"],
            "resumen": None, "noticias": noticias,
        })

    contexto = {"posiciones": [
        {"symbol": s["symbol"], "nombre": s["nombre"], "rentabilidad_pct": s["pl_pct"],
         "titulares": [n["titulo"] for n in s["noticias"][:6]]}
        for s in salida
    ]}
    respuesta = llm.generar_impacto(contexto)
    if respuesta:
        resumenes = {r["symbol"]: r.get("resumen") for r in respuesta.get("posiciones", [])}
        for s in salida:
            s["resumen"] = resumenes.get(s["symbol"])
    return salida


def main():
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    watchlist = leer_json(os.path.join(CONFIG, "watchlist.json"))
    feeds = leer_json(os.path.join(CONFIG, "feeds.json"))

    # Los activos indicados por ISIN (copiados de Trade Republic) se traducen
    # a su simbolo de Yahoo antes de pedir datos.
    for grupo in watchlist.get("grupos", []):
        grupo["activos"] = resolver_isins(grupo.get("activos", []))

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
    if config_cartera.get("posiciones"):
        config_cartera["posiciones"] = resolver_isins(config_cartera["posiciones"])
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

    # Impacto personal: noticias de cada posicion real + resumen de la IA.
    # Solo si el usuario tiene cartera real (no en modo simulacion vacio).
    posiciones_carta = impacto_cartera(datos_cartera)

    escribir_json("briefing.json", {
        "actualizado": ahora,
        "generado_con_ia": briefing is not None,
        "contenido": briefing,
        "posiciones": posiciones_carta,
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

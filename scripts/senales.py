# -*- coding: utf-8 -*-
"""Contexto tecnico objetivo para el modulo de senales (Fase 2c).

Calcula, con el anio de cierres que ya trae la watchlist, la posicion de
cada activo respecto a sus maximos de 52 semanas y sus medias moviles
(SMA 20/50/200), y una etiqueta de tendencia derivada de reglas fijas.

Todo lo de este modulo es DATO CALCULADO, no opinion: la interpretacion
(argumentos y veredicto) la redacta despues la IA sobre estos numeros, y
la web los muestra siempre juntos: nunca un veredicto sin su porque.
"""

# Instrumentos de contexto (miden riesgo o cambio, no se "compran"): se les
# calcula el tecnico pero no reciben veredicto de inversion.
SIN_VEREDICTO = {"^VIX", "^TNX", "EURUSD=X"}


def _sma(cierres, n):
    """Media movil simple de los ultimos n cierres, o None si no hay datos."""
    if len(cierres) < n:
        return None
    return sum(cierres[-n:]) / n


def _pct(a, b):
    """Variacion porcentual de a respecto a b, redondeada."""
    if not a or not b:
        return None
    return round((a / b - 1) * 100, 2)


def tecnico_activo(activo):
    """Contexto tecnico de un activo de la watchlist (con 'cierres' de 1 anio)."""
    cierres = activo.get("cierres") or []
    precio = activo.get("precio")
    if not precio or len(cierres) < 20:
        return None
    maximo = max(cierres)
    minimo = min(cierres)
    sma20, sma50, sma200 = _sma(cierres, 20), _sma(cierres, 50), _sma(cierres, 200)

    # Tendencia por reglas fijas y transparentes (no es una opinion):
    # alcista = precio y SMA50 por encima de la SMA200; bajista = lo contrario.
    tendencia = None
    if sma200 and sma50:
        if precio > sma200 and sma50 > sma200:
            tendencia = "alcista"
        elif precio < sma200 and sma50 < sma200:
            tendencia = "bajista"
        else:
            tendencia = "mixta"

    return {
        "pct_desde_max_52s": _pct(precio, maximo),
        "pct_sobre_min_52s": _pct(precio, minimo),
        "pct_vs_sma20": _pct(precio, sma20),
        "pct_vs_sma50": _pct(precio, sma50),
        "pct_vs_sma200": _pct(precio, sma200),
        "tendencia": tendencia,
    }


def construir(grupos, extras):
    """Contexto tecnico de toda la watchlist + sentimiento global.

    Devuelve (activos, contexto_global): los datos que se publican en
    data/senales.json y que se entregan a la IA para argumentar.
    """
    activos = []
    for g in grupos:
        for a in g["activos"]:
            tec = tecnico_activo(a)
            if not tec:
                continue
            activos.append({
                "symbol": a["symbol"],
                "nombre": a["nombre"],
                "grupo": g["nombre"],
                "precio": a["precio"],
                "moneda": a.get("moneda"),
                "d1": a.get("d1"),
                "m1": a.get("m1"),
                "y1": a.get("y1"),
                "tecnico": tec,
                "con_veredicto": a["symbol"] not in SIN_VEREDICTO,
            })

    contexto_global = {}
    for g in grupos:
        for a in g["activos"]:
            if a["symbol"] == "^VIX":
                contexto_global["vix"] = {"valor": a["precio"], "d1": a.get("d1")}
    fng = (extras or {}).get("fear_and_greed")
    if fng:
        contexto_global["fear_and_greed_cripto"] = fng
    return activos, contexto_global

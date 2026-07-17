# -*- coding: utf-8 -*-
"""Calculos de la cartera personal (Fase 2a).

Lee config/cartera.json (posiciones introducidas a mano por el usuario) y
calcula, con datos de mercado reales: valor actual, coste, rentabilidad desde
la fecha de compra, peso de cada posicion, distribucion por sector y
geografia, y la comparacion honesta con el S&P 500 en el mismo periodo.

Principios:
- Todo son datos objetivos calculados aqui; la IA no interviene en esta capa.
- Las monedas se convierten a la moneda base con el tipo de cambio de la
  fecha de compra (coste) y el actual (valor), para que la rentabilidad
  refleje tambien el efecto divisa.
- La comparacion con el S&P 500 simula haber invertido el mismo importe en
  el indice el mismo dia, pasando por dolares y volviendo a la moneda base
  (el indice cotiza en USD; ignorar la divisa seria enganarse).
- Si una posicion falla al obtener datos, se omite con aviso y el resto de
  la cartera se publica igualmente.
"""
import time

import sources

SIMBOLO_SP500 = "^GSPC"
PAUSA = 0.4  # segundos entre llamadas a Yahoo, respeto a la fuente gratuita


def _valor_en(serie, fecha_iso):
    """Primer cierre de la serie en o despues de una fecha (AAAA-MM-DD).

    Si la fecha es anterior al inicio de la serie devuelve el primer valor;
    si es posterior al final, el ultimo. Las series son cortas: busqueda lineal.
    """
    for fecha, valor in serie:
        if fecha >= fecha_iso:
            return valor
    return serie[-1][1]


def _redondear(v, dec=2):
    return None if v is None else round(v, dec)


def _agrupar(posiciones, campo, valor_total):
    """Distribucion del valor actual por un campo (sector o geografia)."""
    grupos = {}
    for p in posiciones:
        clave = p.get(campo) or "Sin clasificar"
        grupos[clave] = grupos.get(clave, 0.0) + p["valor"]
    salida = [
        {"nombre": k, "valor": _redondear(v), "pct": _redondear(v / valor_total * 100, 1)}
        for k, v in grupos.items()
    ]
    salida.sort(key=lambda g: -g["valor"])
    return salida


def calcular(config):
    """Calcula la cartera completa. Devuelve el dict que se publica en data/.

    Si no hay posiciones, devuelve {"activada": False} y la web no muestra
    la seccion.
    """
    posiciones_cfg = config.get("posiciones") or []
    base = config.get("moneda_base", "EUR")
    if not posiciones_cfg:
        return {"activada": False}

    # Series compartidas: S&P 500 y tipo de cambio USD->base, desde la compra
    # mas antigua. Se piden una sola vez y cada posicion toma su tramo.
    fecha_mas_antigua = min(p["fecha_compra"] for p in posiciones_cfg)
    sp = sources.yahoo_historico(SIMBOLO_SP500, fecha_mas_antigua)
    time.sleep(PAUSA)
    fx_usd = sources.yahoo_cambio_divisa("USD", base, fecha_mas_antigua)
    time.sleep(PAUSA)

    # Cache de tipos de cambio por moneda del activo, para no repetir peticiones.
    fx_cache = {"USD": fx_usd}

    posiciones, omitidas = [], []
    for p in posiciones_cfg:
        symbol = p["symbol"]
        hist = sources.yahoo_historico(symbol, p["fecha_compra"])
        time.sleep(PAUSA)
        if not hist:
            print(f"[aviso] cartera: sin datos para {symbol}; se omite")
            omitidas.append(symbol)
            continue
        moneda = hist["moneda"] or "USD"
        if moneda not in fx_cache:
            fx_cache[moneda] = sources.yahoo_cambio_divisa(moneda, base, fecha_mas_antigua)
            time.sleep(PAUSA)
        fx = fx_cache[moneda]
        if not fx:
            print(f"[aviso] cartera: sin tipo de cambio {moneda}->{base} para {symbol}; se omite")
            omitidas.append(symbol)
            continue

        fx_ini = _valor_en(fx["serie"], p["fecha_compra"])
        fx_hoy = fx["serie"][-1][1]
        precio_hoy = hist["serie"][-1][1]

        coste = p["participaciones"] * p["precio_medio"] * fx_ini
        valor = p["participaciones"] * precio_hoy * fx_hoy
        pl = valor - coste

        # S&P 500 en el mismo periodo: mismo importe, pasando por USD.
        sp_pct = None
        if sp and fx_usd:
            sp_ini = _valor_en(sp["serie"], p["fecha_compra"])
            sp_hoy = sp["serie"][-1][1]
            usd_ini = _valor_en(fx_usd["serie"], p["fecha_compra"])
            usd_hoy = fx_usd["serie"][-1][1]
            factor_sp = (sp_hoy / sp_ini) * (usd_hoy / usd_ini)
            sp_pct = _redondear((factor_sp - 1) * 100)

        posiciones.append({
            "symbol": symbol,
            "nombre": p.get("nombre", symbol),
            "sector": p.get("sector"),
            "geografia": p.get("geografia"),
            "fecha_compra": p["fecha_compra"],
            "participaciones": p["participaciones"],
            "moneda": moneda,
            "precio_actual": precio_hoy,
            "coste": _redondear(coste),
            "valor": _redondear(valor),
            "pl": _redondear(pl),
            "pl_pct": _redondear(pl / coste * 100),
            "sp500_pct_mismo_periodo": sp_pct,
        })

    if not posiciones:
        return {"activada": False, "omitidas": omitidas}

    coste_total = sum(p["coste"] for p in posiciones)
    valor_total = sum(p["valor"] for p in posiciones)
    for p in posiciones:
        p["peso_pct"] = _redondear(p["valor"] / valor_total * 100, 1)
    posiciones.sort(key=lambda p: -p["valor"])

    # Total de la simulacion S&P: cada coste invertido en el indice en su fecha.
    sp_valor_total = None
    con_sp = [p for p in posiciones if p["sp500_pct_mismo_periodo"] is not None]
    if con_sp and len(con_sp) == len(posiciones):
        sp_valor_total = _redondear(sum(
            p["coste"] * (1 + p["sp500_pct_mismo_periodo"] / 100) for p in posiciones))

    totales = {
        "coste": _redondear(coste_total),
        "valor": _redondear(valor_total),
        "pl": _redondear(valor_total - coste_total),
        "pl_pct": _redondear((valor_total / coste_total - 1) * 100),
        "sp500_valor_equivalente": sp_valor_total,
        "sp500_pl_pct": _redondear((sp_valor_total / coste_total - 1) * 100) if sp_valor_total else None,
    }

    return {
        "activada": True,
        # Cartera de practica con dinero ficticio: la web lo etiqueta visiblemente
        # para no confundir nunca simulacion con inversion real.
        "simulada": bool(config.get("simulada")),
        "moneda_base": base,
        "totales": totales,
        "posiciones": posiciones,
        "por_sector": _agrupar(posiciones, "sector", valor_total),
        "por_geografia": _agrupar(posiciones, "geografia", valor_total),
        "omitidas": omitidas,
    }

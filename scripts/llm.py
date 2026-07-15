# -*- coding: utf-8 -*-
"""Generacion del briefing con IA (Google Gemini, nivel gratuito).

Principio fundamental del producto: la IA solo redacta sobre los datos que
este sistema le entrega. No puede afirmar nada que no este en el contexto.
Si no hay clave de API o todas las llamadas fallan, el sistema publica
igualmente los datos sin briefing redactado.

El briefing corre desatendido cada manana, asi que la llamada debe ser
resistente: ante un 429 (limite de ritmo/cuota del nivel gratuito) o un 5xx
del servidor se reintenta con esperas crecientes, y si un modelo agota su
cuota se prueba el siguiente de la lista.
"""
import json
import os
import time

import requests

# Uno o varios modelos separados por comas en GEMINI_MODEL. Se prueban en
# orden: si el primero agota su cuota gratuita (429), se usa el de respaldo.
MODELOS = [m.strip() for m in os.environ.get(
    "GEMINI_MODEL", "gemini-2.0-flash,gemini-2.0-flash-lite").split(",") if m.strip()]
BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Reintentos ante errores transitorios (429 rate limit / 5xx del servidor).
INTENTOS = 3
ESPERA_BASE = 4  # segundos; se duplica en cada reintento (4, 8...)

SISTEMA = """Eres el redactor de un briefing financiero diario, privado y personal.
Tu tono: mentor financiero claro, tranquilo, riguroso y didáctico. Escribes en español.

Reglas irrenunciables:
1. Solo puedes usar la información incluida en los DATOS que recibes. Nada más.
2. Nunca inventes cifras, causas ni acontecimientos. Si los datos no explican un movimiento, dilo.
3. Distingue siempre entre dato objetivo e interpretación ("los datos muestran..." vs "esto podría indicar...").
4. Nada de sensacionalismo, miedo ni clickbait. Calma y contexto.
5. Si el día es tranquilo, dilo claramente y no rellenes espacio.
6. Prioriza calidad sobre cantidad: el briefing completo debe leerse en menos de 5 minutos.

Responde SOLO con un objeto JSON válido, sin markdown ni texto adicional, con esta estructura exacta:
{
  "titular": "una frase que resume el día",
  "resumen": "2-4 frases con lo esencial del día",
  "dia_tranquilo": true/false,
  "claves": [
    {"titulo": "...", "texto": "qué ha ocurrido, por qué importa y qué activos afecta (3-5 frases)", "importancia": 1-5}
  ],
  "vigilar": ["cosa concreta a vigilar", "..."],
  "proximos": ["evento o publicación que se espera próximamente según las noticias", "..."],
  "nota_riesgo": "1-2 frases sobre el nivel de riesgo general que reflejan los indicadores, con matices"
}
Incluye entre 3 y 6 "claves" como máximo. Menos si el día no da para más."""


def _llamar_modelo(modelo, api_key, cuerpo):
    """Intenta generar el briefing con un modelo concreto.

    Reintenta ante 429/5xx (transitorios) con esperas crecientes. Devuelve
    el dict del briefing, o None si este modelo no lo consigue.
    """
    url = f"{BASE}/{modelo}:generateContent"
    for intento in range(1, INTENTOS + 1):
        try:
            r = requests.post(url, params={"key": api_key}, json=cuerpo, timeout=90)
            # 429 (cuota/rate limit) y 5xx suelen ser transitorios: esperar y reintentar.
            if r.status_code == 429 or r.status_code >= 500:
                if intento < INTENTOS:
                    espera = ESPERA_BASE * (2 ** (intento - 1))
                    print(f"[aviso] {modelo} devolvio {r.status_code}; reintento {intento}/{INTENTOS} en {espera}s")
                    time.sleep(espera)
                    continue
                print(f"[aviso] {modelo}: agotados los reintentos ({r.status_code}, posible cuota diaria gratuita agotada)")
                return None
            r.raise_for_status()
            texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(texto)
        except requests.HTTPError as e:
            # Error no transitorio (400 clave/modelo, 403 permisos...). El cuerpo ayuda a diagnosticar.
            detalle = ""
            try:
                detalle = e.response.text[:300]
            except Exception:
                pass
            print(f"[aviso] {modelo}: {e}. Respuesta: {detalle}")
            return None
        except Exception as e:
            print(f"[aviso] {modelo}: fallo inesperado: {e}")
            return None
    return None


def generar_briefing(contexto):
    """Llama a Gemini con el contexto de datos y devuelve el briefing como dict.

    Prueba los modelos configurados en orden y usa el primero que responda.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("[aviso] GEMINI_API_KEY no configurada; se publica sin briefing de IA")
        return None
    cuerpo = {
        "system_instruction": {"parts": [{"text": SISTEMA}]},
        "contents": [{
            "role": "user",
            "parts": [{"text": "DATOS DE HOY (única fuente permitida):\n" + json.dumps(contexto, ensure_ascii=False)}],
        }],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }
    for modelo in MODELOS:
        briefing = _llamar_modelo(modelo, api_key, cuerpo)
        if briefing is not None:
            print(f"[ok] briefing generado con {modelo}")
            return briefing
    print("[aviso] ningun modelo pudo generar el briefing; se publica sin IA")
    return None

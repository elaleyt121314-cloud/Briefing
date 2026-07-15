# -*- coding: utf-8 -*-
"""Generacion del briefing con IA (Google Gemini, nivel gratuito).

Principio fundamental del producto: la IA solo redacta sobre los datos que
este sistema le entrega. No puede afirmar nada que no este en el contexto.
Si no hay clave de API o la llamada falla, el sistema publica igualmente
los datos sin briefing redactado.
"""
import json
import os

import requests

MODELO = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent"

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


def generar_briefing(contexto):
    """Llama a Gemini con el contexto de datos y devuelve el briefing como dict."""
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
    try:
        r = requests.post(URL, params={"key": api_key}, json=cuerpo, timeout=90)
        r.raise_for_status()
        texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(texto)
    except Exception as e:
        print(f"[aviso] fallo en la llamada a la IA: {e}")
        return None

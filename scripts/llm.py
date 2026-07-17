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
# En el nivel gratuito de Gemini, la familia 2.0 ya no tiene cuota (limit 0);
# los modelos con free tier son los 2.5-flash. Se prioriza 2.5-flash (mas
# capaz) y se deja 2.5-flash-lite como respaldo (mas margen de peticiones).
MODELOS = [m.strip() for m in os.environ.get(
    "GEMINI_MODEL", "gemini-2.5-flash,gemini-2.5-flash-lite").split(",") if m.strip()]
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

    Solo reintenta ante errores 5xx (fallos transitorios del servidor). Un 429
    del nivel gratuito es un limite de cuota: reintentar en segundos no lo
    resuelve y ademas gasta mas cuota de tokens, asi que se registra y se pasa
    al siguiente modelo. Devuelve el dict del briefing, o None si no lo consigue.
    """
    url = f"{BASE}/{modelo}:generateContent"
    for intento in range(1, INTENTOS + 1):
        try:
            r = requests.post(url, params={"key": api_key}, json=cuerpo, timeout=90)
            if r.status_code >= 500:
                # Error de servidor: transitorio, merece la pena reintentar con espera.
                if intento < INTENTOS:
                    espera = ESPERA_BASE * (2 ** (intento - 1))
                    print(f"[aviso] {modelo} devolvio {r.status_code}; reintento {intento}/{INTENTOS} en {espera}s")
                    time.sleep(espera)
                    continue
                print(f"[aviso] {modelo}: {r.status_code} tras reintentos. Respuesta: {r.text[:400]}")
                return None
            if r.status_code == 429:
                # Cuota/limite del nivel gratuito. NO reintentar: se registra el motivo
                # literal de Google y se deja paso al siguiente modelo.
                print(f"[aviso] {modelo}: 429 (limite del nivel gratuito). Respuesta: {r.text[:400]}")
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


def _modelos_disponibles(api_key):
    """Pregunta a la API que modelos puede usar ESTA clave y devuelve los aptos
    para redactar (generateContent), priorizando la familia 'flash' (rapida y con
    free tier). Asi el sistema se adapta solo aunque Google jubile modelos.
    """
    try:
        r = requests.get(BASE, params={"key": api_key, "pageSize": 200}, timeout=30)
        r.raise_for_status()
        modelos_api = r.json().get("models", [])
    except Exception as e:
        print(f"[aviso] no se pudo consultar la lista de modelos: {e}")
        return []
    # Nos quedan solo los que generan texto y descartamos los especializados
    # (imagen, voz, incrustaciones...), que no sirven para el briefing.
    excluir = ("embedding", "aqa", "tts", "image", "imagen", "audio", "vision", "live")
    aptos = []
    for m in modelos_api:
        nombre = m.get("name", "").replace("models/", "")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if any(x in nombre.lower() for x in excluir):
            continue
        aptos.append(nombre)

    def prioridad(n):
        n = n.lower()
        if "flash-lite" in n:
            return 0  # el mas ligero: mas margen de peticiones gratuitas
        if "flash" in n:
            return 1
        if "pro" in n:
            return 3  # potente pero suele no tener free tier
        return 2
    aptos.sort(key=prioridad)
    if aptos:
        print(f"[info] modelos aptos para esta clave: {', '.join(aptos[:8])}")
    return aptos


# Lista de modelos resuelta una vez por ejecucion (la carta y las senales
# comparten el descubrimiento para no repetir la consulta).
_cache_modelos = None


def _resolver_modelos(api_key):
    global _cache_modelos
    if _cache_modelos is None:
        # Con GEMINI_MODEL se puede forzar la lista; por defecto, autodescubrimiento
        # (con los modelos por defecto como ultimo recurso si la consulta falla).
        if os.environ.get("GEMINI_MODEL"):
            _cache_modelos = MODELOS
        else:
            _cache_modelos = _modelos_disponibles(api_key) or MODELOS
    return _cache_modelos


def _generar(sistema, texto_usuario, etiqueta, max_tokens=2048, temperatura=0.4):
    """Nucleo compartido: llama a Gemini y devuelve el JSON de respuesta.

    'etiqueta' solo se usa en los mensajes de log (carta, senales...).
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print(f"[aviso] GEMINI_API_KEY no configurada; se publica sin {etiqueta}")
        return None
    cuerpo = {
        "system_instruction": {"parts": [{"text": sistema}]},
        "contents": [{"role": "user", "parts": [{"text": texto_usuario}]}],
        "generationConfig": {
            "temperature": temperatura,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    for modelo in _resolver_modelos(api_key):
        resultado = _llamar_modelo(modelo, api_key, cuerpo)
        if resultado is not None:
            print(f"[ok] {etiqueta}: generado con {modelo}")
            return resultado
    print(f"[aviso] ningun modelo pudo generar {etiqueta}; se publica sin IA")
    return None


def generar_briefing(contexto):
    """Redacta la carta del dia usando SOLO el contexto de datos recuperados."""
    return _generar(
        SISTEMA,
        "DATOS DE HOY (única fuente permitida):\n" + json.dumps(contexto, ensure_ascii=False),
        "la carta",
    )


SISTEMA_SENALES = """Eres el analista de un briefing financiero diario, privado y personal.
Tu tono: mentor claro, tranquilo y riguroso. Escribes en español.

Recibes el contexto técnico calculado de una lista de activos (posición respecto a máximos
de 52 semanas y medias móviles, tendencia por reglas fijas, variaciones) y el sentimiento
de mercado (VIX, Fear & Greed cripto). Para CADA activo recibido debes emitir una señal.

Reglas irrenunciables:
1. Solo puedes usar los datos incluidos. Nada de noticias, fundamentales ni datos externos.
2. El veredicto SIEMPRE va acompañado de argumentos a favor y en contra: nunca un veredicto solo.
3. La confianza refleja la coherencia de las señales: si el técnico y el sentimiento se
   contradicen, la confianza es baja y lo dices.
4. Si los datos no bastan para opinar, veredicto "mantener" con confianza "baja" y explica por qué.
5. Esto es interpretación educativa para uso personal, no asesoramiento profesional. Sé prudente:
   ante la duda, "mantener".
6. Sé breve: resumen de 1-2 frases; cada argumento, una frase corta.

Responde SOLO con un objeto JSON válido, sin markdown, con esta estructura exacta:
{
  "activos": [
    {
      "symbol": "el mismo symbol recibido",
      "veredicto": "comprar" | "mantener" | "vender",
      "confianza": "alta" | "media" | "baja",
      "resumen": "la idea principal en 1-2 frases",
      "a_favor": ["argumento breve", "..."],
      "en_contra": ["argumento breve", "..."]
    }
  ]
}
Incluye entre 1 y 3 argumentos por lado. Todos los activos recibidos deben aparecer."""


def generar_senales(contexto):
    """Argumenta y emite el veredicto por activo sobre el contexto tecnico dado.

    Llamada separada de la carta: mas presupuesto de salida (una lista de
    ~25 activos no cabe en el de la carta) sin arriesgar su calidad.
    """
    return _generar(
        SISTEMA_SENALES,
        "CONTEXTO TÉCNICO Y SENTIMIENTO DE HOY (única fuente permitida):\n"
        + json.dumps(contexto, ensure_ascii=False),
        "las senales",
        max_tokens=8192,
        temperatura=0.3,
    )

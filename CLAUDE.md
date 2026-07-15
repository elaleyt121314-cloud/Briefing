# CLAUDE.md — memoria del proyecto

Este archivo es el registro de decisiones del proyecto. Claude Code debe leerlo
al empezar cada sesión y respetarlo. Si una nueva petición contradice algo de
aquí, señalarlo antes de implementar.

## Qué es este proyecto

Centro personal de inteligencia financiera. Herramienta **personal y privada de un
solo usuario** (Ale). No es un producto comercial, no habrá más usuarios, no hay
métricas de negocio. Nació de un PRD ambicioso de 15 secciones que se analizó
críticamente y se redujo a su núcleo: **un briefing diario inteligente, claro y
sin ruido**, sobre los activos que el usuario elige.

## Decisiones tomadas (y su porqué)

1. **Uso personal, no comercial.** Se valoró publicarlo; se descartó por los
   riesgos legales (MiFID II: las recomendaciones personalizadas de inversión son
   actividad regulada en la UE). Al ser privado, ese riesgo desaparece.
2. **Coste cero absoluto.** Decisión firme del usuario. Solo fuentes gratuitas,
   GitHub Actions (cron diario), GitHub Pages y el tier gratuito de Gemini.
   Nada de servidores 24/7 ni APIs de pago. Renuncias aceptadas conscientemente:
   sin chat instantáneo con la IA (se sustituye por "Run workflow" manual),
   fuentes no oficiales que pueden romperse (por eso existe la capa de
   adaptadores en scripts/sources.py), briefing 1-2 veces al día y no continuo.
3. **Datos con retraso (15 min o cierre).** El usuario se informa a diario, no
   tradea en 10 minutos. Esta decisión es la que hace viable el coste cero.
4. **Web PWA, no app nativa.** Un solo desarrollo para móvil y PC, instalable
   desde el navegador, sin tiendas de aplicaciones. Usará ambos por igual.
5. **Arquitectura "briefing estático":** GitHub Actions cada mañana → adaptadores
   recopilan datos → normalización → Gemini redacta usando SOLO esos datos →
   JSON estáticos en /data → web estática los pinta. Aprobada explícitamente.
6. **Jerarquía de información:** la carta de la mañana (briefing IA) es la
   pantalla principal; mercados, noticias y riesgo son profundización. Nunca
   15 secciones con el mismo peso.
7. **Noticias:** solo fuentes con RSS gratuito (CNBC, MarketWatch, Investing,
   Yahoo, NYT, The Economist, BBC, CoinDesk, Expansión, El Economista...).
   Bloomberg, FT y WSJ quedan fuera: son de pago y no se puede scrapear su
   contenido. De NYT y Economist solo titulares/resúmenes del RSS, no texto
   completo.
8. **Recomendaciones:** el usuario pidió explícitamente veredictos literales
   Comprar / Mantener / Vender, asumiendo el riesgo. Se acordó: el veredicto
   existe, pero SIEMPRE acompañado del razonamiento (contexto técnico,
   sentimiento, argumentos a favor y en contra) y un nivel de confianza.
   Nunca un veredicto sin su porqué. Etiquetar siempre como interpretación.
9. **La IA nunca inventa.** Es requisito de arquitectura, no una instrucción:
   el modelo solo recibe y solo puede usar los datos recuperados esa mañana.
   Si los datos no explican un movimiento, la carta lo dice honestamente.
   Si el día es tranquilo, lo dice y no rellena.
10. **Diseño para la calma** (ya implementado, respetar): estilo Apple/Notion,
    serif editorial (Newsreader) para la carta, verdes/rojos apagados (nunca
    rojo alarma), sin tickers ni animaciones ansiógenas, tema claro/oscuro.
    Se descartó Bloomberg como referencia por ser la antítesis del producto.
    Gráficos: sobriedad tipo TradingView solo dentro de los gráficos.
11. **Personalización básica, no total.** Watchlist editable (config/watchlist.json)
    con símbolos de Yahoo Finance. Se descartaron para v1: perfiles de inversión,
    prioridades por estrellas, importar/exportar, watchlists ilimitadas.
    Se añadirán solo si el usuario los echa de menos.
12. **"IA autoevolutiva" del PRD original → reinterpretada** como regeneración
    diaria del contenido. El sistema no se auto-modifica.

## Principios irrenunciables (heredados del PRD y vigentes)

- Claridad antes que cantidad. Contexto antes que datos sueltos.
- Distinguir siempre dato objetivo / interpretación / escenario / confianza.
- Nada de sensacionalismo, FOMO, clickbait ni relleno.
- Tono: mentor financiero tranquilo, riguroso y didáctico. Todo en español.
- Calidad antes que velocidad de desarrollo. Modular: cada fuente sustituible
  sin tocar el resto.

## Estado y hoja de ruta

- **Fase 0 — cerrada.** Todas las decisiones de arriba.
- **Fase 1 — construida, pendiente de verificación con red real.** Carta diaria,
  mercados con sparklines, noticias, fichas de riesgo, PWA, workflow diario.
  Probada en seco (fuentes simuladas); las llamadas reales a Yahoo/CoinGecko/RSS
  aún no se han ejecutado. Primer paso de cualquier sesión: verificarlas.
- **Fase 2 — siguiente.** (a) Cartera en config/cartera.json: rentabilidad,
  distribución sectorial y geográfica, comparación con S&P 500. (b) Impacto
  personal: el briefing relaciona noticias con las posiciones. (c) Módulo de
  señales y escenarios con veredicto Comprar/Mantener/Vender razonado.
- **Fase 3 — después.** Alertas (ntfy o email desde el workflow), contenido
  educativo curado, asistente con grounding si algún día se acepta coste >0.

## Reglas de trabajo

- Claves solo en GitHub Secrets, jamás en el código.
- Código y comentarios en español. Commits pequeños y descriptivos.
- Ante una decisión de producto no cubierta aquí: preguntar al usuario, no asumir.

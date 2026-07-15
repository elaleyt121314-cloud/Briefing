# Briefing — tu centro personal de inteligencia financiera

Herramienta personal y privada. Cada mañana, un proceso automático recopila datos de mercado,
noticias e indicadores de fuentes públicas gratuitas, pide a la IA que redacte tu briefing
usando **solo** esos datos, y publica el resultado como una web que puedes abrir desde el
móvil o el PC. Coste: 0 €.

## Cómo ponerla en marcha (unos 20 minutos, sin programar)

### 1. Crea una cuenta en GitHub (si no la tienes)
Ve a [github.com](https://github.com) y regístrate. Es gratis.

### 2. Sube este proyecto a un repositorio
1. En GitHub, pulsa **New repository**. Nombre: `briefing`. Elige **Public**
   (necesario para publicar gratis con GitHub Pages; aquí no hay datos sensibles,
   solo tu lista de activos). Pulsa **Create repository**.
2. En la página del repositorio, pulsa **uploading an existing file**.
3. Arrastra **todo el contenido** de esta carpeta (incluida la carpeta `.github`;
   si al arrastrar no se sube, usa "Add file → Upload files" y arrastra las carpetas
   una a una). Pulsa **Commit changes**.

### 3. Consigue tu clave gratuita de IA (Google Gemini)
1. Ve a [aistudio.google.com](https://aistudio.google.com) y entra con una cuenta de Google.
2. Pulsa **Get API key → Create API key** y copia la clave.
3. En tu repositorio de GitHub: **Settings → Secrets and variables → Actions →
   New repository secret**. Nombre: `GEMINI_API_KEY`. Valor: pega la clave. Guarda.

El nivel gratuito de Gemini sobra para un briefing diario. Nunca pegues la clave
en ningún archivo del repositorio: solo en Secrets.

### 4. Activa la web (GitHub Pages)
En el repositorio: **Settings → Pages → Source: Deploy from a branch →
Branch: `main`, carpeta `/ (root)` → Save**. En un par de minutos tu web estará en
`https://TU-USUARIO.github.io/briefing/`.

### 5. Lanza el primer briefing
En el repositorio: pestaña **Actions → Briefing diario → Run workflow**.
Tarda 2-3 minutos. Cuando termine, recarga tu web: verás tu primera carta real.
A partir de ahí se ejecuta solo cada mañana (~7:30 hora española).

### 6. Instálala en el móvil
Abre la web en el navegador del móvil y elige **Añadir a pantalla de inicio**
(Safari: botón compartir; Chrome: menú ⋮). Se comportará como una app.

## Cómo cambiar los activos que sigues
Edita `config/watchlist.json` desde la propia web de GitHub (icono del lápiz).
Añade o quita activos con su símbolo de Yahoo Finance (búscalo en
[finance.yahoo.com](https://finance.yahoo.com); por ejemplo, Inditex es `ITX.MC`).
Al guardar, el siguiente briefing ya los incluirá. Para verlo al momento,
lanza el workflow manualmente (paso 5).

Las fuentes de noticias se cambian igual, en `config/feeds.json`.

## Cómo regenerar el briefing a cualquier hora
Pestaña **Actions → Briefing diario → Run workflow**. Útil si quieres un
repaso al cierre de mercado además del de la mañana.

## Qué hace cada pieza
- `scripts/` — recopila los datos y llama a la IA (Python).
- `config/` — tu watchlist y tus fuentes de noticias.
- `data/` — los JSON que genera el proceso cada día (no los edites a mano).
- `.github/workflows/briefing.yml` — el despertador que lo ejecuta cada mañana.
- El resto de archivos son la web (HTML, CSS y JavaScript, sin frameworks).

## Límites conocidos (decisiones de coste cero)
- Datos con retraso, no en tiempo real. Suficiente para informarse, no para tradear.
- Yahoo Finance es una fuente no oficial: si algún día falla, se sustituye el
  adaptador en `scripts/sources.py` sin tocar nada más.
- Sin chat instantáneo con la IA (requeriría un servidor de pago). El botón
  "Run workflow" hace de "regenerar análisis".

## Hoja de ruta
- **Fase 2**: tu cartera con posiciones, impacto personalizado de las noticias,
  y el módulo de señales y escenarios con veredicto comprar/mantener/vender.
- **Fase 3**: alertas por notificación, contenido educativo, asistente con grounding.

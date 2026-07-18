/* Briefing — lógica de la web estática.
   Lee los JSON de /data generados cada mañana por GitHub Actions. */

const $ = (sel) => document.querySelector(sel);

/* ---------------------------------------------------------- tema */
(function tema() {
  const guardado = localStorage.getItem("tema");
  if (guardado) document.documentElement.dataset.tema = guardado;
  else if (matchMedia("(prefers-color-scheme: dark)").matches)
    document.documentElement.dataset.tema = "oscuro";
  $("#tema").addEventListener("click", () => {
    const nuevo = document.documentElement.dataset.tema === "oscuro" ? "claro" : "oscuro";
    document.documentElement.dataset.tema = nuevo;
    localStorage.setItem("tema", nuevo);
  });
})();

/* ---------------------------------------------------------- utilidades */
async function cargar(nombre) {
  try {
    const r = await fetch(`data/${nombre}?v=${Date.now()}`);
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) {
    console.warn(`No se pudo cargar data/${nombre}`, e);
    return null;
  }
}

function fmtFecha(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("es-ES", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
}

function fmtHora(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("es-ES", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function fmtPrecio(v, moneda) {
  if (v == null) return "—";
  const dec = v >= 1000 ? 0 : v >= 10 ? 2 : 4;
  const n = v.toLocaleString("es-ES", { minimumFractionDigits: dec, maximumFractionDigits: dec });
  const simbolos = { USD: "$", EUR: "€", GBP: "£", JPY: "¥" };
  return simbolos[moneda] ? `${n} ${simbolos[moneda]}` : n;
}

function celdaVar(v, clase = "") {
  if (v == null) return `<span class="var plano ${clase}">—</span>`;
  const tipo = v > 0.05 ? "pos" : v < -0.05 ? "neg" : "plano";
  const signo = v > 0 ? "+" : "";
  return `<span class="var ${tipo} ${clase}">${signo}${v.toFixed(2)}%</span>`;
}

function sparkline(serie) {
  if (!serie || serie.length < 2) return "<span></span>";
  const min = Math.min(...serie), max = Math.max(...serie);
  const rango = max - min || 1;
  const W = 80, H = 26;
  const pts = serie
    .map((v, i) => `${((i / (serie.length - 1)) * W).toFixed(1)},${(H - 3 - ((v - min) / rango) * (H - 6)).toFixed(1)}`)
    .join(" ");
  const sube = serie[serie.length - 1] >= serie[0];
  const color = sube ? "var(--positivo)" : "var(--negativo)";
  return `<svg class="spark" width="${W}" height="${H}" aria-hidden="true"><polyline points="${pts}" stroke="${color}"/></svg>`;
}

const esc = (t) => (t || "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------------------------------------------------------- carta */
function pintarCarta(briefing) {
  $("#carta-fecha").textContent = fmtFecha(briefing?.actualizado) || fmtFecha(new Date().toISOString());
  const c = briefing?.contenido;
  if (!c) {
    $("#carta-titular").textContent = "Los mercados, en datos";
    $("#carta-resumen").textContent =
      "Aquí abajo tienes el estado actualizado de tus activos, las noticias del día y los indicadores de riesgo.";
    if (briefing && !briefing.generado_con_ia) $("#carta-sin-ia").hidden = false;
    return;
  }
  $("#carta-titular").textContent = c.titular || "Briefing del día";
  $("#carta-resumen").textContent = c.resumen || "";
  if (c.dia_tranquilo) $("#carta-tranquilo").hidden = false;

  $("#carta-claves").innerHTML = (c.claves || [])
    .map((k) => `
      <article class="clave">
        <h3>${esc(k.titulo)}${k.importancia ? `<span class="imp">${"●".repeat(k.importancia)}${"○".repeat(5 - k.importancia)}</span>` : ""}</h3>
        <p>${esc(k.texto)}</p>
      </article>`)
    .join("");

  if (c.vigilar?.length) {
    $("#bloque-vigilar").hidden = false;
    $("#lista-vigilar").innerHTML = c.vigilar.map((v) => `<li>${esc(v)}</li>`).join("");
  }
  if (c.proximos?.length) {
    $("#bloque-proximos").hidden = false;
    $("#lista-proximos").innerHTML = c.proximos.map((v) => `<li>${esc(v)}</li>`).join("");
  }
}

/* Impacto personal: tus posiciones y sus noticias (independiente de la carta IA). */
function pintarPosicionesCarta(briefing) {
  const pos = briefing?.posiciones;
  if (!pos?.length) return;
  $("#carta-posiciones").hidden = false;
  $("#carta-posiciones-lista").innerHTML = pos
    .map((p) => `
      <article class="pos">
        <div class="pos-cab">
          <h3>${esc(p.nombre)}</h3>
          ${p.pl_pct != null ? celdaVar(p.pl_pct) : ""}
        </div>
        ${p.resumen ? `<p class="pos-resumen">${esc(p.resumen)}</p>` : ""}
        ${p.noticias?.length ? `<ul class="pos-noticias">${p.noticias.slice(0, 4)
          .map((n) => `<li><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.titulo)}</a>${n.fecha ? `<span class="meta"> · ${fmtHora(n.fecha)}</span>` : ""}</li>`)
          .join("")}</ul>` : `<p class="pos-resumen">Sin noticias específicas hoy.</p>`}
      </article>`)
    .join("");
}

/* ---------------------------------------------------------- cartera */
function fmtDinero(v, moneda) {
  if (v == null) return "—";
  const n = v.toLocaleString("es-ES", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  const simbolos = { USD: "$", EUR: "€", GBP: "£", JPY: "¥" };
  return `${n} ${simbolos[moneda] || moneda}`;
}

function pintarCartera(c) {
  if (!c?.activada) return;
  $("#cartera").hidden = false;
  $("#nav-cartera").hidden = false;
  $("#cartera-fecha").textContent = `Actualizado: ${fmtHora(c.actualizado)}`;
  if (c.simulada) {
    $("#cartera-simulada").hidden = false;
    $("#cartera-aviso-simulacion").hidden = false;
  }

  const t = c.totales, m = c.moneda_base;
  const signo = (v) => (v > 0 ? "+" : "");
  const fichas = [
    { etq: "Valor actual", val: fmtDinero(t.valor, m), sub: `coste ${fmtDinero(t.coste, m)}` },
    { etq: "Resultado", val: `${signo(t.pl)}${fmtDinero(t.pl, m)}`, sub: `${signo(t.pl_pct)}${t.pl_pct}% desde la compra` },
  ];
  if (t.sp500_pl_pct != null) {
    fichas.push({
      etq: "S&P 500 mismo periodo",
      val: `${signo(t.sp500_pl_pct)}${t.sp500_pl_pct}%`,
      sub: `habría sido ${fmtDinero(t.sp500_valor_equivalente, m)}`,
    });
  }
  $("#cartera-resumen").innerHTML = fichas
    .map((f) => `<div class="ficha"><div class="etq">${esc(f.etq)}</div><div class="val">${esc(f.val)}</div><div class="sub">${esc(f.sub)}</div></div>`)
    .join("");

  $("#cartera-posiciones").innerHTML = `
    <div class="fila fila-c cabecera">
      <span>Activo</span><span class="precio">Valor</span>
      <span class="var plano">Rentab.</span><span class="var plano w1">Resultado</span>
      <span class="var plano m1">Peso</span><span class="var plano m1">S&amp;P periodo</span>
    </div>
    ${c.posiciones.map((p) => `
      <div class="fila fila-c">
        <span class="nombre">${esc(p.nombre)}</span>
        <span class="precio">${fmtDinero(p.valor, m)}</span>
        ${celdaVar(p.pl_pct)}
        <span class="var plano w1">${p.pl > 0 ? "+" : ""}${fmtDinero(p.pl, m)}</span>
        <span class="var plano m1">${p.peso_pct}%</span>
        ${celdaVar(p.sp500_pct_mismo_periodo, "m1")}
      </div>`).join("")}`;

  const barras = (lista) => lista
    .map((g) => `
      <div class="distro">
        <span class="etq">${esc(g.nombre)}</span>
        <div class="barra"><div style="width:${Math.min(g.pct, 100)}%"></div></div>
        <span class="pct">${g.pct}%</span>
      </div>`)
    .join("");
  $("#cartera-sector").innerHTML = barras(c.por_sector || []);
  $("#cartera-geo").innerHTML = barras(c.por_geografia || []);
}

/* ---------------------------------------------------------- señales */
function pintarSenales(s) {
  if (!s?.activos?.length) return;
  $("#senales").hidden = false;
  $("#nav-senales").hidden = false;
  $("#senales-fecha").textContent = `Actualizado: ${fmtHora(s.actualizado)}`;
  if (!s.generado_con_ia) $("#senales-sin-ia").hidden = false;

  const chipVeredicto = (a) => {
    if (!a.con_veredicto) return `<span class="chip-veredicto contexto">contexto</span>`;
    const v = a.senal?.veredicto;
    if (!v) return `<span class="chip-veredicto contexto">sin veredicto</span>`;
    return `<span class="chip-veredicto ${esc(v)}">${esc(v)}</span>`;
  };
  const conf = { alta: "●●●", media: "●●○", baja: "●○○" };
  const fmtp = (v, dec = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(dec)}%`);

  const tecnicoLinea = (a) => {
    const t = a.tecnico;
    const partes = [
      `Máx. 52 sem.: ${fmtp(t.pct_desde_max_52s)}`,
      `SMA 50: ${fmtp(t.pct_vs_sma50)}`,
      `SMA 200: ${fmtp(t.pct_vs_sma200)}`,
      t.tendencia ? `tendencia ${t.tendencia}` : null,
      a.y1 != null ? `1 año: ${fmtp(a.y1, 2)}` : null,
    ].filter(Boolean);
    return partes.join(" · ");
  };

  const carta = (a) => `
    <details class="senal">
      <summary>
        <span class="senal-nombre">${esc(a.nombre)}</span>
        ${a.senal?.confianza ? `<span class="senal-conf" title="Confianza ${esc(a.senal.confianza)}">${conf[a.senal.confianza] || ""}</span>` : ""}
        ${chipVeredicto(a)}
      </summary>
      <div class="senal-cuerpo">
        ${a.senal?.resumen ? `<p class="senal-resumen">${esc(a.senal.resumen)}</p>` : ""}
        ${a.senal ? `
          <div class="senal-args">
            <div><h4>A favor</h4><ul>${a.senal.a_favor.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
            <div><h4>En contra</h4><ul>${a.senal.en_contra.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
          </div>` : ""}
        ${!a.con_veredicto ? `<p class="senal-resumen">Instrumento de contexto: mide riesgo o condiciones de mercado; no recibe veredicto de inversión.</p>` : ""}
        <p class="senal-tecnico">${tecnicoLinea(a)}</p>
      </div>
    </details>`;

  const grupos = [];
  for (const a of s.activos) {
    let g = grupos.find((x) => x.nombre === a.grupo);
    if (!g) grupos.push((g = { nombre: a.grupo, activos: [] }));
    g.activos.push(a);
  }
  $("#senales-grupos").innerHTML = grupos
    .map((g) => `<div class="grupo"><h3>${esc(g.nombre)}</h3>${g.activos.map(carta).join("")}</div>`)
    .join("");
}

/* ---------------------------------------------------------- mercados */
function pintarMercados(markets) {
  if (!markets) return;
  $("#mercados-fecha").textContent = `Actualizado: ${fmtHora(markets.actualizado)}`;
  $("#mercados-grupos").innerHTML = markets.grupos
    .filter((g) => g.activos.length)
    .map((g) => `
      <div class="grupo">
        <h3>${esc(g.nombre)}</h3>
        <div class="tabla">
          <div class="fila cabecera">
            <span>Activo</span><span class="precio">Precio</span>
            <span class="var plano">Día</span><span class="var plano w1">Semana</span>
            <span class="var plano m1">Mes</span><span class="spark">30 días</span>
          </div>
          ${g.activos.map((a) => `
            <div class="fila">
              <span class="nombre">${esc(a.nombre)}</span>
              <span class="precio">${fmtPrecio(a.precio, a.moneda)}</span>
              ${celdaVar(a.d1)}${celdaVar(a.w1, "w1")}${celdaVar(a.m1, "m1")}
              ${sparkline(a.spark)}
            </div>`).join("")}
        </div>
      </div>`)
    .join("");
}

/* ---------------------------------------------------------- noticias */
function pintarNoticias(news) {
  if (!news?.items?.length) return;
  $("#lista-noticias").innerHTML = news.items.slice(0, 18)
    .map((n) => `
      <li>
        <a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.titulo)}</a>
        <span class="meta">${esc(n.fuente)}${n.fecha ? " · " + fmtHora(n.fecha) : ""}</span>
      </li>`)
    .join("");
}

/* ---------------------------------------------------------- riesgo */
function pintarRiesgo(extras, briefing) {
  const nota = briefing?.contenido?.nota_riesgo;
  if (nota) $("#riesgo-nota").textContent = nota;

  const fichas = [];
  const fng = extras?.fear_and_greed;
  if (fng) fichas.push({ etq: "Fear & Greed (cripto)", val: fng.valor, sub: fng.texto });
  const cg = extras?.cripto_global;
  if (cg) {
    fichas.push({ etq: "Dominancia de Bitcoin", val: `${cg.dominancia_btc}%`, sub: "del mercado cripto" });
    fichas.push({
      etq: "Capitalización cripto",
      val: `${(cg.cap_total_usd / 1e12).toFixed(2)} B$`,
      sub: `${cg.variacion_cap_24h > 0 ? "+" : ""}${cg.variacion_cap_24h}% en 24 h`,
    });
  }
  for (const m of extras?.macro || []) {
    fichas.push({ etq: m.nombre, val: `${m.valor}${m.unidad || ""}`, sub: `${m.fuente || "FRED"} · ${m.fecha}` });
  }
  $("#riesgo-fichas").innerHTML = fichas
    .map((f) => `<div class="ficha"><div class="etq">${esc(f.etq)}</div><div class="val">${esc(String(f.val))}</div><div class="sub">${esc(f.sub)}</div></div>`)
    .join("");
}

/* ---------------------------------------------------------- arranque */
(async function init() {
  const [briefing, markets, news, extras, carteraDatos, senalesDatos] = await Promise.all([
    cargar("briefing.json"), cargar("markets.json"), cargar("news.json"), cargar("extras.json"),
    cargar("cartera.json"), cargar("senales.json"),
  ]);
  pintarCarta(briefing);
  pintarPosicionesCarta(briefing);
  pintarCartera(carteraDatos);
  pintarSenales(senalesDatos);
  pintarMercados(markets);
  pintarNoticias(news);
  pintarRiesgo(extras, briefing);
})();

/* ---------------------------------------------------------- PWA */
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");

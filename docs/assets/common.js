// B3 Radar: what every page shares. Data comes straight from the repo (raw
// GitHub, CORS-open, cached ~5 min); locally, from ../data/.
"use strict";
const LOCAL = ["localhost", "127.0.0.1"].includes(location.hostname);
const DATA = LOCAL ? "../data/" : "https://raw.githubusercontent.com/mbottoni/b3-radar/main/data/";
const REPO = "https://github.com/mbottoni/b3-radar";

const $ = (s, root = document) => root.querySelector(s);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const el = (tag, props = {}, ...kids) => { const e = document.createElement(tag); Object.assign(e, props); e.append(...kids.filter((k) => k != null)); return e; };
const svg = (tag, attrs = {}) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
const num = (x) => (x === "" || x == null ? NaN : +x);
// Numbers in the page's language (i18n.js): 12,6% and R$ 1,2 bi in Portuguese, 12.6% and R$ 1.2bn in English.
const f1 = (x, d = 1) => fmtNum(x, d);
const pct = (x, d = 0, sign = false) => (Number.isFinite(x) ? `${sign && x > 0 ? "+" : ""}${fmtNum(x * 100, d)}%` : "–");
const pts = (x, d = 1) => (Number.isFinite(x) ? `${x > 0 ? "+" : ""}${fmtNum(x * 100, d)} ${L("p.p.", "pts")}` : "–");
const brl = fmtBRL;
const signed = (x, d = 1) => el("span", { className: x > 0 ? "pos" : x < 0 ? "neg" : "", textContent: pct(x, d, true) });
// Up/down with a glyph, so the direction never rests on color alone.
const change = (x, d = 1) => el("span", { className: x > 0 ? "pos" : x < 0 ? "neg" : "muted", textContent: Number.isFinite(x) ? `${x > 0 ? "▲" : x < 0 ? "▼" : ""} ${pct(Math.abs(x), d)}` : "–" });
const median = (xs) => { const v = xs.filter(Number.isFinite).sort((a, b) => a - b); return v.length ? v[Math.floor(v.length / 2)] : NaN; };

function parseCSV(text) {
  const rows = []; let row = [], field = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; } else field += c; }
    else if (c === '"') q = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const [h, ...b] = rows;
  return h ? b.map((r) => Object.fromEntries(h.map((k, j) => [k, r[j] ?? ""]))) : [];
}
async function get(path, parse = parseCSV) {
  try {
    const r = await fetch(DATA + path);
    return r.ok ? parse(await r.text()) : null;
  } catch { return null; }
}
const getJSON = (path) => get(path, JSON.parse);

// ---------------------------------------------------------------- theme
const THEME_KEY = "b3radar-theme";
const REDRAW = new Set();       // functions that redraw charts (colors are read at draw time)
const redrawAll = () => REDRAW.forEach((f) => f());
function setTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
}
try { setTheme(localStorage.getItem(THEME_KEY)); } catch { /* storage blocked: follow the OS */ }
const isDark = () => (document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";
function toggleTheme() {
  const next = isDark() ? "light" : "dark";
  setTheme(next);
  try { localStorage.setItem(THEME_KEY, next); } catch { /* fine */ }
  syncThemeButton(); redrawAll();
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { syncThemeButton(); redrawAll(); });
const SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
const MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
function syncThemeButton() {
  const b = $("#themeBtn"); if (!b) return;
  b.innerHTML = isDark() ? SUN : MOON;
  b.setAttribute("aria-label", isDark() ? L("Mudar para o tema claro", "Switch to light mode") : L("Mudar para o tema escuro", "Switch to dark mode"));
  b.title = b.getAttribute("aria-label");
}

// --------------------------------------------------------------- header
const TABS = [["overview", L("Visão geral", "Overview")], ["screener", L("Filtro de ações", "Screener")], ["financials", "Financials"],
  ["backtest", "Backtest"], ["record", L("Histórico ao vivo", "Track record")]];
const GH = '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.22 1.87.87 2.33.66.07-.52.28-.87.5-1.07-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>';
const LOGO = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8" opacity=".55"/><circle cx="12" cy="12" r="3.5"/><path d="M12 12l6-6"/></svg>';
// ``active``: a tab key (index page) or null (other pages link back to the tabs).
function shell(active, status) {
  applyStatic();
  const home = active ? "#/" : "./";
  const head = el("div", { className: "top-in" });
  const brand = el("a", { className: "brand", href: home, innerHTML: `<span class="logo">${LOGO}</span><span class="brand-name">B3 Radar</span>`, ariaLabel: "B3 Radar" });
  const asof = el("span", { className: "pill live", id: "asofPill", textContent: status ? `${L("Dados", "Data")} · ${fmtDate(status.asof)}` : L("Carregando…", "Loading…") });
  const rules = el("a", { className: "pill rules", id: "rulesPill", href: `${REPO}/blob/main/METHODOLOGY.md#scores`, style: "text-decoration:none",
    title: L("Impressão digital de todas as regras que decidem a elegibilidade e o ranking. Uma mudança começa um novo histórico ao vivo.",
      "Fingerprint of every rule that decides eligibility and ranking. A change starts a new track record."),
    textContent: status?.rules ? `${L("regras", "rules")} ${status.rules}` : "" });
  const tabs = el("nav", { className: "tabs", ariaLabel: L("Seções", "Sections") }, ...TABS.map(([k, label]) => {
    const a = el("a", { href: `${active ? "" : "./"}#/${k === "overview" ? "" : k}`, textContent: label });
    a.dataset.tab = k;
    if (k === active) a.setAttribute("aria-current", "page");
    return a;
  }));
  const gh = el("a", { className: "icon-btn", href: REPO, innerHTML: `${GH}<span class="gh-label">GitHub</span>`, ariaLabel: L("Código e dados no GitHub", "Code and data on GitHub") });
  const lng = langSwitch(); lng.classList.add("spacer");
  const theme = el("button", { className: "icon-btn", id: "themeBtn", type: "button" });
  theme.addEventListener("click", toggleTheme);
  head.append(brand, asof, rules, tabs, gh, lng, theme);
  const top = $("#top"); top.className = "top"; top.replaceChildren(head);
  syncThemeButton();
}
function setStatus(status) {
  if (!status) return;
  const d = fmtDate(status.asof);
  const a = $("#asofPill"); if (a) { a.textContent = `${L("Dados", "Data")} · ${d}`; a.title = L(`Cotações até o pregão de ${d}; atualizado todo dia útil`, `Quotes through the ${d} session; updated every weekday`); }
  const r = $("#rulesPill"); if (r && status.rules) r.textContent = `${L("regras", "rules")} ${status.rules}`;
}

// The reasons the Python screen writes to `excluded` (b3radar/screen.py), as the reader's language says them.
const EXCLUDED = {
  "financial sector": "setor financeiro",
  "special trading segment (sanctioned or in recovery)": "segmento especial de negociação (sancionada ou em recuperação)",
  "registration not active": "registro na CVM não ativo",
  "not operating normally": "não opera normalmente",
  "illiquid": "baixa liquidez",
  "under a year of quotes": "menos de um ano de cotações",
  "no fundamentals": "sem demonstrações financeiras",
  "negative equity": "patrimônio líquido negativo",
  "non-positive EV": "valor da firma (EV) zero ou negativo",
};
const excludedText = (x) => (x ? L(EXCLUDED[x] || x, x) : "");

// -------------------------------------------------------------- tooltip
function showTip(ev, kids) {
  const t = $("#tip"); t.replaceChildren(...kids); t.style.display = "block";
  const r = t.getBoundingClientRect();
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
  t.style.left = `${Math.max(4, x)}px`; t.style.top = `${Math.max(4, y)}px`;
}
const hideTip = () => { const t = $("#tip"); if (t) t.style.display = "none"; };
const tipRow = (color, value, label) => el("div", { className: "row" }, el("span", { className: "key", style: `background:${color}` }), el("strong", { textContent: value }), label);

// ----------------------------------------------------------- heat cells
// Percentile scores (0-100): blue above the median, red below, gray at 50.
// Text keeps its ink color; only the cell tint carries the magnitude.
function heatBg(t) {
  if (!Number.isFinite(t)) return "";
  const a = Math.round(Math.min(1, Math.abs(t)) * 46);
  return `background:color-mix(in srgb, var(${t >= 0 ? "--heat-hi" : "--heat-lo"}) ${a}%, transparent)`;
}
const scoreCell = (v, extra = "") => el("td", { className: `heat ${extra}`, style: heatBg((v - 50) / 50), textContent: f1(v, 0) });
// Returns: saturates at +/-``cap``.
const retCell = (r, cap = 0.5, d = 0) => el("td", { className: "heat", style: heatBg(r / cap), textContent: Number.isFinite(r) ? pct(r, d, true) : "–" });

// ------------------------------------------------------------ sparkline
function sparkline(values, { w = 96, h = 28, color = "--s1", area = true, ref } = {}) {
  const v = values.map((x) => (x == null ? NaN : +x));
  const ok = v.map((x, i) => [x, i]).filter(([x]) => Number.isFinite(x));
  const s = svg("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}`, "aria-hidden": "true", class: "spark" });
  if (ok.length < 2) return s;
  const lo = Math.min(...ok.map(([x]) => x), ref ?? Infinity), hi = Math.max(...ok.map(([x]) => x), ref ?? -Infinity);
  const X = (i) => 1 + (i / (v.length - 1)) * (w - 2), Y = (x) => 2 + (1 - (x - lo) / (hi - lo || 1)) * (h - 4);
  const d = ok.map(([x, i], j) => `${j ? "L" : "M"}${X(i).toFixed(1)},${Y(x).toFixed(1)}`).join("");
  // Colors as CSS variables, so a theme switch restyles tables without a redraw.
  if (area) s.append(svg("path", { d: `${d}L${X(ok.at(-1)[1]).toFixed(1)},${h}L${X(ok[0][1]).toFixed(1)},${h}Z`, style: `fill:var(${color});opacity:.13` }));
  if (Number.isFinite(ref)) s.append(svg("line", { x1: 0, x2: w, y1: Y(ref), y2: Y(ref), style: "stroke:var(--axis)", "stroke-dasharray": "2 2" }));
  s.append(svg("path", { d, fill: "none", style: `stroke:var(${color})`, "stroke-width": 1.6, "stroke-linejoin": "round", "stroke-linecap": "round" }));
  s.append(svg("circle", { cx: X(ok.at(-1)[1]), cy: Y(ok.at(-1)[0]), r: 2.2, style: `fill:var(${color})` }));
  return s;
}
function fillSpark(box, values, opts = {}) {     // full width of its box
  box.replaceChildren(sparkline(values, { ...opts, w: Math.max(80, box.clientWidth || 200) }));
}

// ---------------------------------------------------------------- gauge
// A half-circle meter for one 0-100 number (a hero number, not a chart).
function gauge(value, { size = 200, label = "" } = {}) {
  const w = size, h = size * 0.56, cx = w / 2, cy = h - 4, r = w / 2 - 12, sw = 16;
  const pt = (f) => [cx - r * Math.cos(Math.PI * f), cy - r * Math.sin(Math.PI * f)];
  const arc = (f0, f1) => { const [x0, y0] = pt(f0), [x1, y1] = pt(f1); return `M${x0},${y0} A${r},${r} 0 0 1 ${x1},${y1}`; };
  const s = svg("svg", { width: w, height: h + 18, viewBox: `0 0 ${w} ${h + 18}`, role: "img", "aria-label": label, style: "margin:0 auto" });
  s.append(svg("path", { d: arc(0, 1), fill: "none", stroke: css("--grid"), "stroke-width": sw, "stroke-linecap": "round" }));
  const f = Math.max(0.001, Math.min(1, value / 100));
  if (Number.isFinite(value)) s.append(svg("path", { d: arc(0, f), fill: "none", stroke: css("--s1"), "stroke-width": sw, "stroke-linecap": "round" }));
  for (const [t, x] of [[0, cx - r], [100, cx + r]]) {     // under the arc's ends
    const tx = svg("text", { x, y: cy + 18, "text-anchor": "middle", "font-size": 10, fill: css("--muted") });
    tx.textContent = t; s.append(tx);
  }
  const big = svg("text", { x: cx, y: cy - 10, "text-anchor": "middle", "font-size": 40, "font-weight": 700, fill: css("--ink") });
  big.textContent = Number.isFinite(value) ? Math.round(value) : "–"; s.append(big);
  return s;
}

// ---------------------------------------------------------------- ticks
// Decimals that tell ticks ``step`` apart: 0.5 -> 1, 5 -> 0.
const stepDigits = (step) => Math.max(0, Math.ceil(-Math.log10(step) - 1e-9));
// Round ticks inside [lo, hi], 1, 2 or 5 x 10^k apart, about ``count`` steps:
// at least three when a finer step allows, coarser while ``fmt(tick, step)``
// would print two ticks the same.
function niceTicks(lo, hi, count, fmt = (v) => String(v)) {
  const raw = (hi - lo) / Math.max(1, count);
  if (!(raw > 0) || !Number.isFinite(raw)) return { ticks: [lo], step: undefined };
  const p = 10 ** Math.floor(Math.log10(raw)), e = raw / p;
  let step = +(p * (e >= 7.07 ? 10 : e >= 3.16 ? 5 : e >= 1.41 ? 2 : 1)).toPrecision(12);
  const at = (st) => {
    const out = [];
    for (let k = Math.ceil(lo / st - 1e-9); k * st <= hi + st * 1e-9; k++) out.push(+(k * st).toPrecision(12));
    return out;
  };
  const lead = (st) => Math.round(st / 10 ** Math.floor(Math.log10(st)));          // 1, 2 or 5
  const unique = (ts, st) => new Set(ts.map((t) => fmt(t, st))).size === ts.length;
  let ticks = at(step);
  if (ticks.length < 3) {
    const st = +(step / (lead(step) === 5 ? 2.5 : 2)).toPrecision(12), ts = at(st);   // 5 -> 2 -> 1 -> 0.5
    if (unique(ts, st)) { step = st; ticks = ts; }
  }
  for (let i = 0; i < 6 && !unique(ticks, step); i++) {
    step = +(step * (lead(step) === 2 ? 2.5 : 2)).toPrecision(12);                    // 1 -> 2 -> 5 -> 10
    ticks = at(step);
  }
  return { ticks, step };
}

// ----------------------------------------------------------- line chart
// series: [{values, color (a token), label, width, dash, endLabel(v)}];
// opts: {h, log, fmt (axis: fmt(v, step), step only on automatic ticks), tipFmt,
//        ticks, ref, refLabel, yMin (a floor the padding does not cross), yMax,
//        fixed, clipHi, ml, labels (direct end labels), legend, legendNote, aria, tipExtra(i)}
function lineChart(box, dates, series, opts = {}) {
  box.replaceChildren();
  const vals = series.flatMap((s) => s.values).filter(Number.isFinite).filter((v) => !opts.log || v > 0);
  if (dates.length < 2 || !vals.length) { box.append(el("p", { className: "muted", textContent: L("Histórico insuficiente.", "Not enough history.") })); return; }
  const fmt = opts.fmt || ((z, st) => fmtNum(z, st ? stepDigits(st) : 0)), tipFmt = opts.tipFmt || opts.fmt || ((z) => fmtNum(z, 1));
  const w = box.clientWidth || 600, h = opts.h || 200, ml = opts.ml || 46, mt = 10, mb = 20;
  // On a phone, end labels would eat a third of the plot: the legend names the lines instead.
  opts = { ...opts, labels: opts.labels && w >= 520, legend: opts.legend || (opts.labels && w < 520 && series.length > 1) };
  const mr = opts.labels ? (opts.mr || 118) : 8;
  const T = (v) => (opts.log ? Math.log(v) : v);
  let lo = Math.min(...vals, opts.ref ?? Infinity), hi = Math.max(...vals, opts.ref ?? -Infinity);
  if (opts.yMin !== undefined) lo = Math.min(lo, opts.yMin);
  if (opts.yMax !== undefined) hi = Math.max(hi, opts.yMax);
  if (Number.isFinite(opts.clipHi)) hi = Math.min(hi, opts.clipHi);
  const pad = opts.fixed ? 0 : (T(hi) - T(lo)) * 0.08 || 1;
  let a = opts.fixed ? T(opts.yMin) : T(lo) - pad, b = opts.fixed ? T(opts.yMax) : T(hi) + pad;
  // Padding never takes the axis past a floor the data respects (yMin, else zero):
  // a dividend yield's axis does not go to -6%. Likewise a series that is never positive stops at 0.
  if (!opts.fixed && !opts.log) {
    const floor = opts.yMin ?? 0;
    if (lo >= floor && a < floor) a = floor;
    if (hi <= 0 && b > 0) b = 0;
  }
  const clip = (v) => (Number.isFinite(opts.clipHi) && v > opts.clipHi ? opts.clipHi : v);
  const x = (i) => ml + (i / (dates.length - 1)) * (w - ml - mr), y = (v) => mt + (1 - (T(v) - a) / (b - a)) * (h - mt - mb);
  const s = svg("svg", { width: w, height: h, role: "img", "aria-label": opts.aria || series.map((z) => z.label).join(", ") });
  let ticks = opts.ticks, step;
  if (!ticks && opts.log) ticks = [25, 50, 100, 200, 400, 800, 1600, 3200, 6400].filter((v) => T(v) >= a && T(v) <= b);
  if (!ticks) ({ ticks, step } = niceTicks(a, b, Math.max(3, Math.round((h - mt - mb) / 50)), fmt));
  for (const t of ticks.filter((v) => T(v) >= a - 1e-9 && T(v) <= b + 1e-9)) {
    const yy = y(t);
    s.append(svg("line", { x1: ml, x2: w - mr, y1: yy, y2: yy, stroke: Math.abs(t) < 1e-12 && !opts.log ? css("--axis") : css("--grid") }));
    const tx = svg("text", { x: ml - 6, y: yy + 4, "text-anchor": "end", "font-size": 10, fill: css("--muted") });
    tx.textContent = fmt(t, step); s.append(tx);
  }
  if (Number.isFinite(opts.ref)) s.append(svg("line", { x1: ml, x2: w - mr, y1: y(opts.ref), y2: y(opts.ref), stroke: css("--other"), "stroke-width": 1.5 }));
  const yrs = dates.map((d, i) => [d, i]).filter(([d], i, arr) => i === 0 || d.slice(0, 4) !== arr[i - 1][0].slice(0, 4));
  const every = Math.max(1, Math.ceil(yrs.length / Math.max(2, Math.floor((w - ml - mr) / 56))));
  yrs.forEach(([d, i], j) => {
    if (j % every || (i === 0 && yrs.length > 1 && x(yrs[1]?.[1] ?? 0) - x(0) < 30)) return;
    const t = svg("text", { x: x(i), y: h - 4, "text-anchor": "middle", "font-size": 10, fill: css("--muted") }); t.textContent = d.slice(0, 4); s.append(t);
  });
  const ends = [];
  for (const se of [...series].reverse()) {
    let d = "", pen = false;
    se.values.forEach((v, i) => {
      if (!Number.isFinite(v) || (opts.log && v <= 0)) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(clip(v)).toFixed(1)}`; pen = true;
      const solo = (i === 0 || !Number.isFinite(se.values[i - 1])) && (i === se.values.length - 1 || !Number.isFinite(se.values[i + 1]));
      if (solo) s.append(svg("circle", { cx: x(i), cy: y(clip(v)), r: 2.5, fill: css(se.color) }));
    });
    s.append(svg("path", { d, fill: "none", stroke: css(se.color), "stroke-width": se.width || 2, "stroke-linejoin": "round",
      ...(se.dash ? { "stroke-dasharray": "5 4" } : {}) }));
    const last = se.values.map((v, i) => [v, i]).filter(([v]) => Number.isFinite(v)).at(-1);
    if (opts.labels && last) ends.push({ y: y(clip(last[0])), x: x(last[1]), text: se.endLabel ? se.endLabel(last[0]) : se.label });
  }
  ends.sort((p, q) => p.y - q.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  for (const e of ends) { const t = svg("text", { x: e.x + 7, y: e.y + 4, "font-size": 11, fill: css("--ink") }); t.textContent = e.text; s.append(t); }
  const hair = svg("line", { y1: mt, y2: h - mb, stroke: css("--ink2"), opacity: 0 }); s.append(hair);
  const hit = svg("rect", { x: ml, y: 0, width: Math.max(0, w - ml - mr), height: h, fill: "transparent" });
  const move = (ev) => {
    const r = s.getBoundingClientRect(), i = Math.max(0, Math.min(dates.length - 1, Math.round(((ev.clientX - r.left - ml) / (w - ml - mr)) * (dates.length - 1))));
    hair.setAttribute("x1", x(i)); hair.setAttribute("x2", x(i)); hair.setAttribute("opacity", 1);
    showTip(ev, [el("b", { textContent: fmtDate(dates[i]) }), ...series.map((se) => tipRow(css(se.color), Number.isFinite(se.values[i]) ? tipFmt(se.values[i]) : "–", se.label)),
      ...(Number.isFinite(opts.ref) ? [tipRow(css("--other"), tipFmt(opts.ref), opts.refLabel || L("mediana", "median"))] : []), ...(opts.tipExtra ? opts.tipExtra(i) : [])]);
  };
  hit.addEventListener("pointermove", move); hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", () => { hair.setAttribute("opacity", 0); hideTip(); });
  s.append(hit); box.append(s);
  if (opts.legend) box.append(el("div", { className: "legend" }, ...series.map((se) => el("span", {}, el("i", { className: se.dash ? "dash" : "", style: se.dash ? `color:${css(se.color)}` : `background:${css(se.color)}` }), se.label)),
    ...(opts.legendNote ? [el("span", { className: "muted", textContent: opts.legendNote })] : [])));
}

// Columns from a zero baseline, one slot per label: a missing or zero value
// leaves its slot empty (still hoverable), so a gap reads as a gap. Values sit
// on the caps when every column has room; otherwise round y ticks carry them.
// ``fmt(v, step)``: step is given for axis ticks only. Year labels are thinned
// to round years (every 2, 5, 10...).
function barChart(box, labels, values, fmt, { h = 170, aria = "", unit = L("por ação", "per share"), none = "no payments on file" } = {}) {
  box.replaceChildren();
  if (!values.some((v) => v > 0)) { box.append(el("p", { className: "muted", textContent: L("Nenhum pagamento registrado.", "No payments on file.") })); return; }
  const w = box.clientWidth || 600, mr = 8, mt = 16, mb = 18;
  const widest = Math.max(...values.filter((v) => v > 0).map((v) => fmt(v).length)) * 6 + 8;   // ~6px a character at 10px
  const capped = (w - 8 - mr) / labels.length >= widest, ml = capped ? 8 : 46, bw = (w - ml - mr) / labels.length;
  const top = Math.max(...values.filter((v) => v > 0));
  const hi = top * (capped ? 1.12 : 1.06);
  const y = (v) => mt + (1 - v / hi) * (h - mt - mb);
  const s = svg("svg", { width: w, height: h, role: "img", "aria-label": aria });
  if (!capped) {
    const { ticks, step } = niceTicks(0, hi, 3, fmt);
    for (const t of ticks.filter((t) => t > 0)) {
      s.append(svg("line", { x1: ml, x2: w - mr, y1: y(t), y2: y(t), stroke: css("--grid") }));
      const tx = svg("text", { x: ml - 6, y: y(t) + 4, "text-anchor": "end", "font-size": 10, fill: css("--muted") }); tx.textContent = fmt(t, step); s.append(tx);
    }
  }
  s.append(svg("line", { x1: ml, x2: w - mr, y1: y(0), y2: y(0), stroke: css("--axis") }));
  const years = labels.every((l) => /^\d{4}$/.test(l)), every = [1, 2, 5, 10, 20, 50].find((k) => k * bw >= 40) || 100;
  const hover = svg("rect", { y: mt, width: bw, height: y(0) - mt, fill: css("--grid"), opacity: 0 });
  s.append(hover);
  labels.forEach((lab, i) => {
    const v = values[i], cx = ml + (i + 0.5) * bw, bwid = Math.max(2, Math.min(24, bw - 2 * Math.min(4, bw * 0.15)));
    if (v > 0) {
      // Rounded at the data end, square at the baseline.
      const x0 = cx - bwid / 2, x1 = cx + bwid / 2, y0 = y(v), y1 = y(0), r = Math.min(bwid >= 8 ? 4 : 2, bwid / 2, y1 - y0);
      s.append(svg("path", { d: `M${x0},${y1}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x1 - r}Q${x1},${y0} ${x1},${y0 + r}V${y1}Z`, fill: css("--s1") }));
      if (capped) { const t = svg("text", { x: cx, y: y0 - 4, "text-anchor": "middle", "font-size": 10, fill: css("--ink") }); t.textContent = fmt(v); s.append(t); }
    }
    if ((years ? +lab : i) % every === 0) { const t = svg("text", { x: cx, y: h - 4, "text-anchor": "middle", "font-size": 10, fill: css("--muted") }); t.textContent = lab; s.append(t); }
  });
  // One hit area per slot (bar or not), the full plot height.
  const hit = svg("rect", { x: ml, y: 0, width: Math.max(0, w - ml - mr), height: h, fill: "transparent" });
  const move = (ev) => {
    const i = Math.max(0, Math.min(labels.length - 1, Math.floor((ev.clientX - s.getBoundingClientRect().left - ml) / bw))), v = values[i];
    hover.setAttribute("x", ml + i * bw); hover.setAttribute("opacity", 0.5);
    showTip(ev, [el("b", { textContent: labels[i] }), v > 0 ? el("div", { className: "row" }, el("strong", { textContent: fmt(v) }), unit) : el("div", { className: "row muted", textContent: none })]);
  };
  hit.addEventListener("pointermove", move); hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", () => { hover.setAttribute("opacity", 0); hideTip(); });
  s.append(hit);
  box.append(s);
}

// ------------------------------------------------------ why this score
const METRICS = {
  value: [["earnings_yield", L("Earnings yield (EBIT / valor da firma)", "Earnings yield (EBIT / EV)"), (x) => pct(x, 1)],
          ["book_to_market", L("Patrimônio / valor de mercado", "Book / market value"), (x) => f1(x, 2)]],
  quality: [["roic", L("Retorno sobre o capital investido (ROIC)", "Return on invested capital"), (x) => pct(x)],
            ["roe", L("Retorno sobre o patrimônio (ROE)", "Return on equity"), (x) => pct(x)],
            ["net_debt_ebit", L("Dívida líquida / EBIT (menor é melhor)", "Net debt / EBIT (lower is better)"), (x) => f1(x)]],
  momentum: [["momentum", L("Retorno em 12 meses, sem o último mês", "12-month return, last month left out"), (x) => pct(x, 0, true)]],
  income: [["dividend_yield", L("Dividendos dos últimos 12 meses / preço", "Dividends of the last 12 months / price"), (x) => pct(x, 1)]],
  growth: [["revenue_growth", L("Crescimento da receita ao ano, 3 anos", "Revenue growth per year, 3 years"), (x) => pct(x, 1, true)],
           ["earnings_growth", L("Crescimento do lucro líquido ao ano, 3 anos", "Net income growth per year, 3 years"),
            (x, p) => (Number.isFinite(x) ? pct(x, 1, true) : Number.isFinite(p) ? L("prejuízo hoje", "loss now") : "–")],
           ["growth_consistency", L("Trimestres com receita acima de um ano antes", "Quarters with revenue above a year before"), (x) => pct(x, 0)]],
};
const PILLAR = { value: L("Valor", "Value"), quality: L("Qualidade", "Quality"), momentum: L("Momento", "Momentum"), income: L("Dividendos", "Income"),
  growth: L("Crescimento", "Growth") };
const PILLAR_KEYS = ["value", "quality", "momentum", "income"];   // the scored ones
// Shown for information: a pillar with no weight in the score (METHODOLOGY.md: why growth is out).
const UNSCORED = { growth: L("Fora da nota: no backtest, as que mais cresciam foram as piores.", "Not in the score: in the backtest the fastest growers did worst.") };
function breakdown(r, { meta = true, among = L(" entre as empresas elegíveis", " among eligible companies") } = {}) {
  const box = el("div", { className: "bd" });
  for (const [k, ms] of Object.entries(METRICS)) {
    const col = el("div", {}, el("h4", { textContent: `${PILLAR[k]}: ${f1(num(r[k + "_score"]), 0)} / 100` }));
    if (UNSCORED[k]) col.append(el("div", { className: "off", textContent: UNSCORED[k] }));
    for (const [m, label, fmt] of ms) {
      const p = num(r["p_" + m]);
      col.append(el("div", { className: "m" },
        el("span", { textContent: label }), el("strong", { textContent: fmt(num(r[m]), p) }),
        el("div", { className: "bar", role: "img", ariaLabel: `${L("percentil", "percentile")} ${f1(p, 0)}` }, el("i", { style: `width:${Number.isFinite(p) ? p : 0}%` })),
        el("span", { className: "pctl", textContent: Number.isFinite(p) ? `${L("percentil", "percentile")} ${f1(p, 0)}${among}` : L("sem nota", "not scored") })));
    }
    box.append(col);
  }
  if (meta) box.append(el("div", { className: "meta", textContent:
    L(`Demonstrações até ${fmtDate(r.fundamentals_date)}, entregues à CVM em ${fmtDate(r.filed)}`, `Statements up to ${fmtDate(r.fundamentals_date)}, filed with CVM on ${fmtDate(r.filed)}`) +
    (r.growth_base ? L(` · crescimento medido desde ${fmtDate(r.growth_base)}`, ` · growth measured from ${fmtDate(r.growth_base)}`) : "") +
    L(` · número de ações: ${(r.shares_source || "–").toUpperCase()}`, ` · share count from ${(r.shares_source || "–").toUpperCase()}`) + ` · tickers: ${r.tickers || r.ticker}` +
    (r.excluded ? L(` · fora do ranking: ${excludedText(r.excluded)}`, ` · not ranked: ${r.excluded}`) : "") }));
  return box;
}

// Ticker -> its company page; the click must not also expand the row.
function companyLink(ticker, title) {
  const a = el("a", { className: "tk", href: `company.html?t=${encodeURIComponent(ticker)}`, textContent: ticker,
    title: title || L(`${ticker}: histórico, valuation, dividendos`, `${ticker}: history, valuation, dividends`) });
  a.addEventListener("click", (e) => e.stopPropagation());
  a.addEventListener("keydown", (e) => e.stopPropagation());
  return a;
}
// Two-line company cell: ticker (link) over the company name.
function nameCell(r, extra = []) {
  return el("td", { className: "l name sticky" }, companyLink(r.ticker, r.tickers), ...extra, el("span", { className: "co", textContent: r.company || "", title: r.company || "" }));
}
// 1-year trend: weekly total-return sparkline and the 1-year return.
function trendCell(sp) {
  if (!sp) return el("td", { className: "trend muted", textContent: "–" });
  return el("td", { className: "trend" }, el("div", { className: "tw" }, sparkline(sp.w, { w: 76, h: 24 }), el("span", { className: "num" }, signed(sp.r1y, 0))));
}

// Redraw a set of charts when their box changes width.
function onResize(node, fn) {
  let lastW = 0;
  new ResizeObserver(([e]) => { const w = Math.round(e.contentRect.width); if (w && w !== lastW) { lastW = w; fn(); } }).observe(node);
}
const INFO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>';
const callout = (text) => el("div", { className: "callout", innerHTML: INFO }, el("div", { textContent: text }));

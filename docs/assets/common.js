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
const f1 = (x, d = 1) => (Number.isFinite(x) ? x.toFixed(d) : "–");
const pct = (x, d = 0, sign = false) => (Number.isFinite(x) ? `${sign && x > 0 ? "+" : ""}${(x * 100).toFixed(d)}%` : "–");
const pts = (x, d = 1) => (Number.isFinite(x) ? `${x > 0 ? "+" : ""}${(x * 100).toFixed(d)} pts` : "–");
const brl = (x) => !Number.isFinite(x) ? "–" : Math.abs(x) >= 1e9 ? `R$ ${(x / 1e9).toFixed(1)}bn` : `R$ ${(x / 1e6).toFixed(0)}m`;
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
  b.setAttribute("aria-label", isDark() ? "Switch to light mode" : "Switch to dark mode");
  b.title = b.getAttribute("aria-label");
}

// --------------------------------------------------------------- header
const TABS = [["overview", "Overview"], ["screener", "Screener"], ["backtest", "Backtest"], ["record", "Track record"]];
const GH = '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.22 1.87.87 2.33.66.07-.52.28-.87.5-1.07-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>';
const LOGO = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8" opacity=".55"/><circle cx="12" cy="12" r="3.5"/><path d="M12 12l6-6"/></svg>';
// ``active``: a tab key (index page) or null (other pages link back to the tabs).
function shell(active, status) {
  const home = active ? "#/" : "./";
  const head = el("div", { className: "top-in" });
  const brand = el("a", { className: "brand", href: home, innerHTML: `<span class="logo">${LOGO}</span>B3 Radar` });
  const asof = el("span", { className: "pill live", id: "asofPill", textContent: status ? `Data · ${status.asof}` : "Loading…" });
  const rules = el("a", { className: "pill rules", id: "rulesPill", href: `${REPO}/blob/main/METHODOLOGY.md#scores`, style: "text-decoration:none",
    title: "Fingerprint of every rule that decides eligibility and ranking. A change starts a new track record.",
    textContent: status?.rules ? `rules ${status.rules}` : "" });
  const tabs = el("nav", { className: "tabs", ariaLabel: "Sections" }, ...TABS.map(([k, label]) => {
    const a = el("a", { href: `${active ? "" : "./"}#/${k === "overview" ? "" : k}`, textContent: label });
    a.dataset.tab = k;
    if (k === active) a.setAttribute("aria-current", "page");
    return a;
  }));
  const gh = el("a", { className: "icon-btn", href: REPO, innerHTML: `${GH}<span class="gh-label">GitHub</span>`, ariaLabel: "Code and data on GitHub" });
  const theme = el("button", { className: "icon-btn spacer", id: "themeBtn", type: "button" });
  theme.addEventListener("click", toggleTheme);
  head.append(brand, asof, rules, tabs, gh, theme);
  const top = $("#top"); top.className = "top"; top.replaceChildren(head);
  syncThemeButton();
}
function setStatus(status) {
  if (!status) return;
  const a = $("#asofPill"); if (a) { a.textContent = `Data · ${status.asof}`; a.title = `Quotes through the ${status.asof} session; updated every weekday`; }
  const r = $("#rulesPill"); if (r && status.rules) r.textContent = `rules ${status.rules}`;
}

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

// ----------------------------------------------------------- line chart
// series: [{values, color (a token), label, width, dash, endLabel(v)}];
// opts: {h, log, fmt (axis), tipFmt, ticks, ref, refLabel, yMin, yMax, fixed,
//        clipHi, ml, labels (direct end labels), legend, legendNote, aria, tipExtra(i)}
function lineChart(box, dates, series, opts = {}) {
  box.replaceChildren();
  const vals = series.flatMap((s) => s.values).filter(Number.isFinite).filter((v) => !opts.log || v > 0);
  if (dates.length < 2 || !vals.length) { box.append(el("p", { className: "muted", textContent: "Not enough history." })); return; }
  const fmt = opts.fmt || ((z) => z.toFixed(0)), tipFmt = opts.tipFmt || opts.fmt || ((z) => z.toFixed(1));
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
  const a = opts.fixed ? T(opts.yMin) : T(lo) - pad, b = opts.fixed ? T(opts.yMax) : T(hi) + pad;
  const clip = (v) => (Number.isFinite(opts.clipHi) && v > opts.clipHi ? opts.clipHi : v);
  const x = (i) => ml + (i / (dates.length - 1)) * (w - ml - mr), y = (v) => mt + (1 - (T(v) - a) / (b - a)) * (h - mt - mb);
  const s = svg("svg", { width: w, height: h, role: "img", "aria-label": opts.aria || series.map((z) => z.label).join(", ") });
  let ticks = opts.ticks;
  if (!ticks) ticks = opts.log ? [25, 50, 100, 200, 400, 800, 1600, 3200, 6400].filter((v) => T(v) >= a && T(v) <= b) : [0, 0.5, 1].map((f) => a + f * (b - a));
  for (const t of ticks.filter((v) => T(v) >= a - 1e-9 && T(v) <= b + 1e-9)) {
    const yy = y(t);
    s.append(svg("line", { x1: ml, x2: w - mr, y1: yy, y2: yy, stroke: Math.abs(t) < 1e-12 && !opts.log ? css("--axis") : css("--grid") }));
    const tx = svg("text", { x: ml - 6, y: yy + 4, "text-anchor": "end", "font-size": 10, fill: css("--muted") });
    tx.textContent = fmt(t); s.append(tx);
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
    showTip(ev, [el("b", { textContent: dates[i] }), ...series.map((se) => tipRow(css(se.color), Number.isFinite(se.values[i]) ? tipFmt(se.values[i]) : "–", se.label)),
      ...(Number.isFinite(opts.ref) ? [tipRow(css("--other"), tipFmt(opts.ref), opts.refLabel || "median")] : []), ...(opts.tipExtra ? opts.tipExtra(i) : [])]);
  };
  hit.addEventListener("pointermove", move); hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", () => { hair.setAttribute("opacity", 0); hideTip(); });
  s.append(hit); box.append(s);
  if (opts.legend) box.append(el("div", { className: "legend" }, ...series.map((se) => el("span", {}, el("i", { className: se.dash ? "dash" : "", style: se.dash ? `color:${css(se.color)}` : `background:${css(se.color)}` }), se.label)),
    ...(opts.legendNote ? [el("span", { className: "muted", textContent: opts.legendNote })] : [])));
}

function barChart(box, labels, values, fmt, { h = 170, aria = "" } = {}) {
  box.replaceChildren();
  if (!values.some(Number.isFinite)) { box.append(el("p", { className: "muted", textContent: "No payments on file." })); return; }
  const w = box.clientWidth || 600, ml = 8, mr = 8, mt = 16, mb = 18;
  const hi = Math.max(...values.filter(Number.isFinite)) * 1.12, bw = (w - ml - mr) / labels.length;
  const y = (v) => mt + (1 - v / hi) * (h - mt - mb);
  const s = svg("svg", { width: w, height: h, role: "img", "aria-label": aria });
  s.append(svg("line", { x1: ml, x2: w - mr, y1: y(0), y2: y(0), stroke: css("--axis") }));
  labels.forEach((lab, i) => {
    const v = values[i], bx = ml + i * bw + Math.min(4, bw * 0.15), bwid = Math.max(bw - 2 * Math.min(4, bw * 0.15), 2);
    if (Number.isFinite(v) && v > 0) {
      const r = svg("rect", { x: bx, y: y(v), width: bwid, height: y(0) - y(v), rx: 3, fill: css("--s1") });
      r.addEventListener("pointermove", (ev) => showTip(ev, [el("b", { textContent: lab }), el("div", { className: "row" }, el("strong", { textContent: fmt(v) }), "per share")]));
      r.addEventListener("pointerleave", hideTip); s.append(r);
      if (bw > 30) { const t = svg("text", { x: bx + bwid / 2, y: y(v) - 4, "text-anchor": "middle", "font-size": 10, fill: css("--ink") }); t.textContent = fmt(v); s.append(t); }
    }
    if (bw > 22 || i % 2 === 0) { const t = svg("text", { x: bx + bwid / 2, y: h - 4, "text-anchor": "middle", "font-size": 10, fill: css("--muted") }); t.textContent = lab.slice(2); s.append(t); }
  });
  box.append(s);
}

// ------------------------------------------------------ why this score
const METRICS = {
  value: [["earnings_yield", "Earnings yield (EBIT / EV)", (x) => pct(x, 1)], ["book_to_market", "Book / market value", (x) => f1(x, 2)]],
  quality: [["roic", "Return on invested capital", (x) => pct(x)], ["roe", "Return on equity", (x) => pct(x)],
            ["net_debt_ebit", "Net debt / EBIT (lower is better)", (x) => f1(x)]],
  momentum: [["momentum", "12-month return, last month left out", (x) => pct(x, 0, true)]],
  income: [["dividend_yield", "Dividends of the last 12 months / price", (x) => pct(x, 1)]],
  growth: [["revenue_growth", "Revenue growth per year, 3 years", (x) => pct(x, 1, true)],
           ["earnings_growth", "Net income growth per year, 3 years", (x, p) => (Number.isFinite(x) ? pct(x, 1, true) : Number.isFinite(p) ? "loss now" : "–")],
           ["growth_consistency", "Quarters with revenue above a year before", (x) => pct(x, 0)]],
};
const PILLAR = { value: "Value", quality: "Quality", momentum: "Momentum", income: "Income", growth: "Growth" };
const PILLAR_KEYS = ["value", "quality", "momentum", "income"];   // the scored ones
// Shown for information: a pillar with no weight in the score (METHODOLOGY.md: why growth is out).
const UNSCORED = { growth: "Not in the score: in the backtest the fastest growers did worst." };
function breakdown(r, { meta = true, among = " among eligible companies" } = {}) {
  const box = el("div", { className: "bd" });
  for (const [k, ms] of Object.entries(METRICS)) {
    const col = el("div", {}, el("h4", { textContent: `${PILLAR[k]}: ${f1(num(r[k + "_score"]), 0)} / 100` }));
    if (UNSCORED[k]) col.append(el("div", { className: "off", textContent: UNSCORED[k] }));
    for (const [m, label, fmt] of ms) {
      const p = num(r["p_" + m]);
      col.append(el("div", { className: "m" },
        el("span", { textContent: label }), el("strong", { textContent: fmt(num(r[m]), p) }),
        el("div", { className: "bar", role: "img", ariaLabel: `percentile ${f1(p, 0)}` }, el("i", { style: `width:${Number.isFinite(p) ? p : 0}%` })),
        el("span", { className: "pctl", textContent: Number.isFinite(p) ? `percentile ${f1(p, 0)}${among}` : "not scored" })));
    }
    box.append(col);
  }
  if (meta) box.append(el("div", { className: "meta", textContent:
    `Statements up to ${r.fundamentals_date || "–"}, filed with CVM on ${r.filed || "–"}` +
    (r.growth_base ? ` · growth measured from ${r.growth_base}` : "") + ` · share count from ${(r.shares_source || "–").toUpperCase()} · tickers: ${r.tickers || r.ticker}` +
    (r.excluded ? ` · not ranked: ${r.excluded}` : "") }));
  return box;
}

// Ticker -> its company page; the click must not also expand the row.
function companyLink(ticker, title) {
  const a = el("a", { className: "tk", href: `company.html?t=${encodeURIComponent(ticker)}`, textContent: ticker, title: title || `${ticker}: history, valuation, dividends` });
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

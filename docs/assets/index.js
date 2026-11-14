// B3 Radar index: four tabs (overview, screener, backtest, track record) over
// the files in data/. Each tab renders once, then redraws its charts on
// resize and on theme changes.
"use strict";
const S = {};                 // everything loaded
const SPARK = () => S.sparks?.tickers || {};

// ------------------------------------------------------------------ router
const tabFromHash = () => { const t = location.hash.replace(/^#\/?/, "").split(/[?/]/)[0] || "overview"; return TABS.some(([k]) => k === t) ? t : "overview"; };
const BUILT = new Set();
let current = null;
function show() {
  const tab = tabFromHash();
  for (const s of document.querySelectorAll("main > section[data-tab]")) s.hidden = s.dataset.tab !== tab;
  for (const a of document.querySelectorAll(".tabs a")) a.dataset.tab === tab ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current");
  if (current && current !== tab) window.scrollTo(0, 0);
  current = tab;
  document.title = tab === "overview" ? "B3 Radar" : `${TABS.find(([k]) => k === tab)[1]} · B3 Radar`;
  if (!S.ready) return;
  if (!BUILT.has(tab)) { BUILD[tab](); BUILT.add(tab); }
  REDRAW.clear(); if (DRAW[tab]) { REDRAW.add(DRAW[tab]); DRAW[tab](); }
}
addEventListener("hashchange", show);

// ================================================================ OVERVIEW
function scard({ k, sub, value, d, spark, ref, foot = [] }) {
  const box = el("div", { className: "spark" });
  const c = el("div", { className: "scard" },
    el("div", { className: "row1" }, el("span", { className: "k", textContent: k }), d ? el("span", { className: "d" }, ...[].concat(d)) : null),
    el("div", { className: "sub", textContent: sub }),
    el("div", { className: "card-v", textContent: value }), box,
    el("div", { className: "foot" }, ...foot.map((f) => el("span", {}, ...[].concat(f)))));
  c._spark = () => fillSpark(box, spark || [], { h: 42, ref });
  return c;
}
function buildCards() {
  const H = S.mkHist || [], T = S.mkToday || {}, b = S.sparks?.bova11;
  const series = (k) => [...H.map((r) => num(r[k])), T[k] ?? NaN];
  const cards = [];
  if (b) cards.push(scard({ k: "BOVA11", sub: L("ETF do Ibovespa · últimos 12 meses", "Ibovespa ETF · last 12 months"), value: `R$ ${f1(b.close.filter((x) => x != null).at(-1), 2)}`,
    d: ["1D ", change(b.r1d)], spark: b.close, foot: [["1M ", change(b.r1m)], [L("12M ", "1Y "), change(b.r1y)]] }));
  cards.push(scard({ k: "Earnings yield", sub: L("ação típica, EBIT / valor da firma", "typical eligible stock, EBIT / EV"), value: pct(T.earnings_yield, 1),
    d: `${L("mediana", "median")} ${pct(T.history_median, 1)}`, spark: series("earnings_yield"), ref: T.history_median,
    foot: [L(`acima de ${pct(T.cheaper_than)} dos meses desde ${(T.history_from || "").slice(0, 4)}`, `above ${pct(T.cheaper_than)} of months since ${(T.history_from || "").slice(0, 4)}`)] }));
  cards.push(scard({ k: "CDI", sub: L("o que o caixa rende, ao ano", "what cash pays, per year"), value: pct(T.cdi, 1), spark: series("cdi"),
    foot: [`${L("real", "after inflation")} ${pct(T.real_cdi, 1)}`] }));
  cards.push(scard({ k: L("Inflação", "Inflation"), sub: L("IPCA, últimos 12 meses", "IPCA, last 12 months"), value: pct(T.ipca_12m, 1), spark: series("ipca_12m"),
    foot: [L("Banco Central, série 433", "Banco Central, series 433")] }));
  cards.push(scard({ k: L("Universo", "Universe"), sub: L("empresas que passam nos filtros", "companies passing the filters"), value: String(S.status?.eligible ?? "–"),
    spark: series("eligible"), foot: [L(`de ${S.status?.companies ?? "–"} listadas`, `of ${S.status?.companies ?? "–"} listed`), L("mensal desde 2011", "monthly since 2011")] }));
  $("#cards").replaceChildren(...cards);
}

const MK = [["earnings_yield", "--s1", L("Earnings yield, ação típica", "Earnings yield, typical stock"), "Earnings yield"], ["cdi", "--s2", "CDI", "CDI"],
            ["real_cdi", "--s3", L("CDI real (descontado o IPCA de 12 meses)", "CDI after inflation (last 12 months)"), "CDI real"]];
function mkRows() {
  const rows = (S.mkHist || []).map((r) => ({ date: r.date, ...Object.fromEntries(MK.map(([k]) => [k, num(r[k])])) }));
  const t = S.mkToday;
  if (t && t.date > (rows.at(-1)?.date || "")) rows.push({ date: t.date, ...Object.fromEntries(MK.map(([k]) => [k, t[k] ?? NaN])), today: true });
  return rows;
}
function drawMkChart() {
  const rows = mkRows(), box = $("#mkChart");
  if (rows.length < 2) { box.replaceChildren(el("p", { className: "muted", textContent: L("O histórico do mercado ainda não foi montado.", "The market history has not been built yet.") })); return; }
  const all = rows.flatMap((r) => MK.map(([k]) => r[k])).filter(Number.isFinite);
  const lo = Math.min(0, Math.floor(Math.min(...all) * 20) / 20), hi = Math.ceil(Math.max(...all) * 20) / 20;
  const ticks = []; for (let v = lo; v <= hi + 1e-9; v += 0.05) ticks.push(+v.toFixed(2));
  lineChart(box, rows.map((r) => (r.today ? `${r.date} (${L("hoje", "today")})` : r.date)), MK.map(([k, c, label, short]) => ({
    values: rows.map((r) => r[k]), color: c, label, width: k === "earnings_yield" ? 2.5 : 2, endLabel: (v) => `${short} ${pct(v, 1)}` })),
  { h: 260, ml: 38, ticks, yMin: lo, yMax: hi, fixed: true, fmt: (v) => `${Math.round(v * 100)}%`, tipFmt: (v) => pct(v, 1), labels: true, mr: 128,
    legend: true, legendNote: L("· % ao ano, fim de cada mês, último ponto hoje", "· % per year, month ends, last point today"),
    aria: L("Earnings yield da ação típica contra o CDI, mensal desde 2011", "Earnings yield of the typical stock against the CDI, monthly since 2011"),
    tipExtra: (i) => [el("div", { className: "row muted", textContent: `${L("earnings yield − CDI real", "earnings yield − CDI after inflation")}: ${pts(rows[i].earnings_yield - rows[i].real_cdi)}` })] });
}
function buildWhy() {
  const T = S.mkToday || {}, H = S.mkHist || [];
  const gaps = H.map((r) => num(r.earnings_yield) - num(r.real_cdi)).filter(Number.isFinite);
  const kv = (k, v) => [el("span", { textContent: k }), el("strong", { textContent: v })];
  $("#mkWhy").replaceChildren(
    ...kv(L("Earnings yield, ação típica", "Earnings yield, typical stock"), pct(T.earnings_yield, 1)),
    ...kv(L(`Sua mediana desde ${(T.history_from || "").slice(0, 4)}`, `Its median since ${(T.history_from || "").slice(0, 4)}`), pct(T.history_median, 1)),
    ...kv(L("P/L agregado (as grandes pesam mais)", "Aggregate P/E (big caps weigh more)"), f1(T.pe_agg)),
    ...kv(L("Dividend yield, ação típica", "Dividend yield, typical stock"), pct(T.dividend_yield, 1)),
    el("div", { className: "sep" }),
    ...kv("CDI", pct(T.cdi, 1)), ...kv(L("CDI real", "CDI after inflation"), pct(T.real_cdi, 1)),
    ...kv(L("Earnings yield − CDI real", "Earnings yield − real CDI"), pts(T.earnings_yield - T.real_cdi)),
    ...kv(L("A mesma diferença, mediana desde 2011", "Same gap, median since 2011"), pts(median(gaps))));
  const v = Number.isFinite(T.cheaper_than) ? T.cheaper_than * 100 : NaN;
  const zone = !Number.isFinite(v) ? "" : v >= 67 ? L("Barata frente ao próprio histórico", "Cheap against its own history")
    : v >= 33 ? L("Perto do nível de costume", "Near its usual level") : L("Cara frente ao próprio histórico", "Expensive against its own history");
  $("#gauge").replaceChildren(gauge(v, { size: 220, label: L(`Mais barata que em ${f1(v, 0)}% dos meses passados`, `Cheaper than ${f1(v, 0)}% of past months`) }),
    el("div", { className: "lbl", textContent: Number.isFinite(v)
      ? L(`Mais barata que em ${f1(v, 0)}% dos fechamentos de mês desde ${(T.history_from || "").slice(0, 4)}`, `Cheaper than ${f1(v, 0)}% of month ends since ${(T.history_from || "").slice(0, 4)}`)
      : L("Ainda sem histórico", "No history yet") }),
    zone ? el("div", { className: "badge", textContent: zone }) : null,
    el("p", { className: "note", style: "margin:10px 0 0", textContent: L("Pelo earnings yield da ação típica: yield maior = mais barata.", "By the typical stock's earnings yield: higher yield = cheaper.") }));
  $("#mkNote").textContent = L("Todas as empresas elegíveis (não financeiras, líquidas, em operação) como o filtro estava em cada fim de mês, só com o que era público na data. " +
    "Earnings yield é EBIT / valor da firma, a métrica de valor do filtro; sua mediana é a ação típica. O lucro cresce com os preços, por isso a comparação justa é com o CDI real. Estar barata não diz nada sobre o momento certo: veja abaixo.",
  "Every eligible company (non-financial, liquid, operating) as the screen stood at each month end, point in time. " +
    "Earnings yield is EBIT / enterprise value, the screen's value metric; its median is the typical stock. Earnings grow with prices, so the fair comparison is cash after inflation. Cheapness says nothing about timing: see below.");
}

function mkPoints() {
  return (S.mkHist || []).map((r) => ({ date: r.date, gap: num(r.earnings_yield) - num(r.real_cdi), out: num(r.fwd_stocks) - num(r.fwd_cdi),
    stocks: num(r.fwd_stocks), cdi: num(r.fwd_cdi) })).filter((p) => Number.isFinite(p.gap) && Number.isFinite(p.out));
}
function drawMkScatter() {
  const box = $("#mkScatter"); box.replaceChildren();
  const P = mkPoints(), t = S.mkToday;
  if (!P.length) return;
  const nowGap = t && t.earnings_yield != null && t.real_cdi != null ? t.earnings_yield - t.real_cdi : NaN;
  const w = box.clientWidth || 480, h = 300, ml = 40, mr = 10, mt = 18, mb = 34;
  const xs = [...P.map((p) => p.gap), ...(Number.isFinite(nowGap) ? [nowGap] : [])], ys = P.map((p) => p.out);
  const x0 = Math.floor(Math.min(0, ...xs) * 20) / 20, x1 = Math.ceil(Math.max(0, ...xs) * 20) / 20;
  const y0 = Math.floor(Math.min(0, ...ys) * 20) / 20, y1 = Math.ceil(Math.max(0, ...ys) * 20) / 20;
  const X = (v) => ml + ((v - x0) / (x1 - x0)) * (w - ml - mr), Y = (v) => mt + (1 - (v - y0) / (y1 - y0)) * (h - mt - mb);
  const s = svg("svg", { width: w, height: h, role: "img", "aria-label": L("Diferença entre earnings yield e CDI real no início contra ações menos CDI nos três anos seguintes", "Gap between earnings yield and real CDI at the start against stocks minus CDI over the next three years") });
  const lab = (x, y, t, a = "middle") => { const e = svg("text", { x, y, "text-anchor": a, "font-size": 10, fill: css("--muted") }); e.textContent = t; s.append(e); };
  for (let v = y0; v <= y1 + 1e-9; v += 0.05) {
    s.append(svg("line", { x1: ml, x2: w - mr, y1: Y(v), y2: Y(v), stroke: Math.abs(v) < 1e-9 ? css("--axis") : css("--grid") }));
    lab(ml - 6, Y(v) + 4, `${v > 1e-9 ? "+" : ""}${Math.round(v * 100)}`, "end");
  }
  for (let v = x0; v <= x1 + 1e-9; v += 0.05) {
    if (Math.abs(v) < 1e-9) s.append(svg("line", { x1: X(0), x2: X(0), y1: mt, y2: h - mb, stroke: css("--axis") }));
    lab(X(v), h - mb + 14, `${v > 1e-9 ? "+" : ""}${Math.round(v * 100)}`);
  }
  const xl = svg("text", { x: ml + (w - ml - mr) / 2, y: h - 4, "text-anchor": "middle", "font-size": 11, fill: css("--ink2") });
  xl.textContent = L("earnings yield − CDI real, no início (p.p.)", "earnings yield − CDI after inflation, at the start (pts)"); s.append(xl);
  const yl = svg("text", { x: ml - 34, y: mt - 8, "font-size": 11, fill: css("--ink2") }); yl.textContent = L("ações − CDI ao ano, 3 anos seguintes (p.p.)", "stocks − CDI per year, next 3 years (pts)"); s.append(yl);
  if (Number.isFinite(nowGap)) {
    s.append(svg("line", { x1: X(nowGap), x2: X(nowGap), y1: mt, y2: h - mb, stroke: css("--ink2"), "stroke-dasharray": "4 3" }));
    const tt = svg("text", { x: X(nowGap) + 4, y: mt + 10, "font-size": 11, "font-weight": 600, fill: css("--ink") }); tt.textContent = L("diferença de hoje", "today's gap"); s.append(tt);
  }
  for (const p of P) {
    const c = svg("circle", { cx: X(p.gap), cy: Y(p.out), r: 4, fill: css("--s1"), stroke: css("--surface"), "stroke-width": 1.5 });
    const tip = (ev) => showTip(ev, [el("b", { textContent: L(`A partir de ${fmtDate(p.date)}`, `From ${p.date}`) }),
      el("div", { className: "row", textContent: L(`earnings yield ${pts(p.gap)} acima do CDI real`, `earnings yield ${pts(p.gap)} over cash after inflation`) }),
      tipRow(css("--s1"), pct(p.stocks, 1, true), L("ações ao ano, 3 anos seguintes", "stocks per year, next 3 years")), tipRow(css("--s2"), pct(p.cdi, 1), L("CDI ao ano", "CDI per year"))]);
    c.addEventListener("pointermove", tip); c.addEventListener("pointerdown", tip);
    c.addEventListener("pointerleave", hideTip); s.append(c);
  }
  box.append(s);
}
function buildThirds() {
  const P = mkPoints().sort((a, b) => a.gap - b.gap), t = $("#mkThirds");
  t.replaceChildren(el("tr", {}, ...[[L("Diferença no início", "Gap at the start")], [L("Meses", "Months")],
    [L("Ações − CDI", "Stocks − CDI"), L("Ações menos CDI, ao ano, 3 anos seguintes", "Stocks minus CDI, per year, next 3 years")],
    [L("Bateu o CDI", "Beat CDI"), L("Fração dos meses em que as ações bateram o CDI nos 3 anos seguintes", "Share of months in which stocks beat the CDI over the next 3 years")]]
    .map(([h, title], i) => el("th", { className: i ? "" : "l", textContent: h, title: title || "" }))));
  const n = P.length;
  for (const [label, a, b] of [[L("Terço menor", "Smallest third"), 0, Math.round(n / 3)], [L("Terço do meio", "Middle third"), Math.round(n / 3), Math.round((2 * n) / 3)],
    [L("Terço maior", "Largest third"), Math.round((2 * n) / 3), n]]) {
    const g = P.slice(a, b);
    if (!g.length) continue;
    const avg = g.reduce((s, p) => s + p.out, 0) / g.length, wins = g.filter((p) => p.out > 0).length / g.length;
    t.append(el("tr", {}, el("td", { className: "l" }, el("div", { textContent: label }), el("span", { className: "muted", style: "font-size:12px", textContent: `${pts(g[0].gap, 0)} ${L("a", "to")} ${pts(g.at(-1).gap, 0)}` })),
      el("td", { textContent: g.length }), retCell(avg, 0.15, 1), el("td", { textContent: pct(wins) })));
  }
  const dates = P.map((p) => p.date).sort();
  $("#mkCaveat").textContent = !n ? "" : L(`${n} inícios mensais, de ${fmtDate(dates[0].slice(0, 7))} a ${fmtDate(dates.at(-1).slice(0, 7))}. Eles se sobrepõem: meses seguidos compartilham quase todos os seus três anos, então isto está mais perto de quatro ou cinco períodos independentes do que de ${n}. Descreve o passado, não é uma previsão.`,
    `${n} monthly starts, ${dates[0].slice(0, 7)} to ${dates.at(-1).slice(0, 7)}. They overlap: consecutive months share almost all of their three years, so this is closer to four or five independent periods than to ${n}. It describes the past, not a forecast.`);
}

// Expandable row (click / Enter) showing the score breakdown.
const OPEN = { list: new Set(), screen: new Set() };
function expandable(table, open, key, cells, row, span, rerender) {
  const tr = el("tr", { className: "clickable", tabIndex: 0 }, ...cells);
  tr.setAttribute("aria-expanded", String(open.has(key)));
  const toggle = () => { open.has(key) ? open.delete(key) : open.add(key); rerender(); };
  tr.addEventListener("click", toggle);
  tr.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), toggle()));
  table.append(tr);
  if (open.has(key)) table.append(el("tr", { className: "detail" }, el("td", { colSpan: span }, breakdown(row))));
}
function buildList() {
  const by = new Map(S.screen.map((r) => [r.ticker, r])), picks = S.picks || [];
  const dates = [...new Set(picks.map((p) => p.date))].sort();
  const cur = dates.at(-1), prev = dates.at(-2);
  const now = picks.filter((p) => p.date === cur && p.strategy === "composite").sort((a, b) => a.rank - b.rank);
  const before = new Set(picks.filter((p) => p.date === prev && p.strategy === "composite").map((p) => p.ticker));
  $("#listNote").textContent = cur
    ? L(`Lista de ${fmtDate(cur)} (preços de fechamento), as 10 primeiras pela nota. Células de nota: percentil no universo elegível. Clique numa linha para ver a nota em detalhe.`,
      `List of ${cur} (closing prices), the top 10 by score. Score cells: percentile in the eligible universe. Click a row for the full breakdown.`)
    : L("Ainda sem lista: a primeira sai na segunda-feira.", "No list yet: the first one is made on Monday.");
  const head = [["#"], [L("Empresa", "Company"), "l sticky"], [L("12M", "1Y")], [L("Nota", "Score")], ["V", "c", PILLAR.value], ["Q", "c", PILLAR.quality],
    ["M", "c", PILLAR.momentum], [L("D", "I"), "c", PILLAR.income], [L("P/L", "P/E")], ["EV/EBIT"], ["ROE"], [L("DY", "Div. yield")], [L("Preço", "Price")]];
  const t = $("#list");
  const render = () => {
    t.replaceChildren(el("tr", {}, ...head.map(([h, c = "", title = ""]) => el("th", { className: c, textContent: h, title }))));
    for (const p of now) {
      const s = by.get(p.ticker) || { ticker: p.ticker, company: p.company };
      expandable(t, OPEN.list, p.ticker, [
        el("td", { textContent: p.rank }),
        nameCell({ ...s, company: p.company }, prev && !before.has(p.ticker) ? [el("span", { className: "new", textContent: L("NOVA", "NEW") })] : []),
        trendCell(SPARK()[p.ticker]), scoreCell(num(p.score)),
        ...PILLAR_KEYS.map((k) => scoreCell(num(s[k + "_score"]))),
        el("td", { textContent: f1(num(s.pe)) }), el("td", { textContent: f1(num(s.ev_ebit)) }),
        el("td", { textContent: pct(num(s.roe)) }), el("td", { textContent: pct(num(s.dividend_yield), 1) }),
        el("td", { textContent: `R$ ${f1(num(p.price), 2)}` })], s, head.length, render);
    }
  };
  render();
  const magic = picks.filter((p) => p.date === cur && p.strategy === "magic").sort((a, b) => a.rank - b.rank);
  $("#magic").replaceChildren(...magic.map((m) => el("a", { className: "chip", href: `company.html?t=${m.ticker}`, style: "text-decoration:none", textContent: `${m.rank}. ${m.ticker}`, title: m.company })));
}

function buildOverview() {
  const st = S.status;
  $("#status").textContent = !st ? "" : L(`Fechamento de ${fmtDate(st.asof)} · ${st.eligible} de ${st.companies} empresas listadas passam nos filtros · atualizado todo dia útil`,
    `Closing prices of ${st.asof} · ${st.eligible} of ${st.companies} listed companies pass the filters · updated every weekday`);
  buildCards(); buildWhy(); buildThirds(); buildList();
}
function drawOverview() {
  for (const c of $("#cards").children) c._spark?.();
  drawMkChart(); drawMkScatter();
  const g = $("#gauge svg"); if (g) { const v = S.mkToday?.cheaper_than; g.replaceWith(gauge(Number.isFinite(v) ? v * 100 : NaN, { size: 220 })); }
}

// ================================================================ SCREENER
const PRESETS = [
  ["all", L("Todas as elegíveis", "All eligible"), (r) => !r.excluded],
  ["top", L("20 maiores notas", "Top 20 score"), (r) => !r.excluded && num(r.rank) <= 20],
  ["magic", L("Fórmula Mágica 20", "Magic Formula 20"), (r) => !r.excluded && num(r.magic_rank) <= 20],
  ["value", `${PILLAR.value} ≥ 80`, (r) => !r.excluded && num(r.value_score) >= 80],
  ["quality", `${PILLAR.quality} ≥ 80`, (r) => !r.excluded && num(r.quality_score) >= 80],
  ["momentum", `${PILLAR.momentum} ≥ 80`, (r) => !r.excluded && num(r.momentum_score) >= 80],
  ["income", `${PILLAR.income} ≥ 80`, (r) => !r.excluded && num(r.income_score) >= 80],
  ["growth", `${PILLAR.growth} ≥ 80`, (r) => !r.excluded && num(r.growth_score) >= 80],
  ["excluded", L("Excluídas", "Excluded"), (r) => !!r.excluded],
];
const COLS = [
  ["rank", "#", "n"], ["ticker", L("Empresa", "Company"), "s", "l sticky"], ["r1y", L("12M", "1Y"), "n", "", L("Retorno total, últimos 12 meses", "Total return, last 12 months")],
  ["score", L("Nota", "Score"), "n", "c"],
  ["value_score", "V", "n", "c", PILLAR.value], ["quality_score", "Q", "n", "c", PILLAR.quality], ["momentum_score", "M", "n", "c", PILLAR.momentum],
  ["income_score", L("D", "I"), "n", "c", PILLAR.income], ["growth_score", L("C", "G"), "n", "c", L("Crescimento (aparece, fora da nota)", "Growth (shown, not scored)")],
  ["pe", L("P/L", "P/E"), "n"], ["ev_ebit", "EV/EBIT", "n"], ["roe", "ROE", "n"], ["dividend_yield", L("DY", "Div. yield"), "n", "", "Dividend yield"],
  ["momentum", "12–1m", "n", "", L("Retorno de 12 meses atrás até 1 mês atrás", "Return from 12 months to 1 month ago")],
  ["market_cap", L("Valor de mercado", "Mkt cap"), "n"],
  ["liquidity", L("Vol. diário", "Daily vol."), "n", "", L("Volume médio diário negociado, 3 meses", "Average daily traded volume, 3 months")],
  ["sector", L("Setor", "Sector"), "s", "l"], ["excluded", L("Excluída por", "Excluded because"), "s", "l"],
];
const FMT = { pe: f1, ev_ebit: f1, roe: (x) => pct(x), dividend_yield: (x) => pct(x, 1), market_cap: brl, liquidity: brl };
const SCR = { preset: "all", sortKey: "rank", sortAsc: true };
const val = (r, k) => (k === "r1y" ? num(SPARK()[r.ticker]?.r1y) : r[k]);
function buildScreener() {
  const st = S.status;
  $("#scrMeta").textContent = !st ? "" : L(`${st.companies} empresas · ${st.eligible} elegíveis · fechamento de ${fmtDate(st.asof)}`,
    `${st.companies} companies · ${st.eligible} eligible · closing prices of ${st.asof}`);
  const sectors = [...new Set(S.screen.filter((r) => !r.excluded).map((r) => r.sector))].filter(Boolean).sort();
  $("#sector").append(...sectors.map((s) => el("option", { value: s, textContent: s })));
  for (const id of ["#q", "#sector", "#liq"]) $(id).addEventListener("input", renderScreen);
  $("#presets").replaceChildren(...PRESETS.map(([k, label, f]) => {
    const b = el("button", { className: "preset", type: "button" }, label, el("span", { className: "n", textContent: S.screen.filter(f).length }));
    b.dataset.k = k;
    b.addEventListener("click", () => { SCR.preset = k; renderScreen(); });
    return b;
  }));
  renderScreen();
}
function renderScreen() {
  for (const b of $("#presets").children) b.setAttribute("aria-pressed", String(b.dataset.k === SCR.preset));
  const q = $("#q").value.trim().toLowerCase(), sec = $("#sector").value, liq = +$("#liq").value;
  const pf = PRESETS.find(([k]) => k === SCR.preset)[2];
  const cols = COLS.filter(([k]) => SCR.preset === "excluded" || k !== "excluded");
  const rows = S.screen.filter((r) => pf(r) && (!sec || r.sector === sec) && num(r.liquidity) >= liq &&
    (!q || r.ticker.toLowerCase().includes(q) || r.company.toLowerCase().includes(q) || r.tickers.toLowerCase().includes(q)));
  const type = Object.fromEntries(COLS.map(([k, , t]) => [k, t]));
  const { sortKey, sortAsc } = SCR;
  rows.sort((a, b) => {
    const [x, y] = [val(a, sortKey), val(b, sortKey)];
    if (type[sortKey] === "n") { const [u, v] = [num(x), num(y)]; if (!Number.isFinite(u)) return 1; if (!Number.isFinite(v)) return -1; return sortAsc ? u - v : v - u; }
    return sortAsc ? String(x).localeCompare(String(y)) : String(y).localeCompare(String(x));
  });
  $("#scrCount").textContent = L(`${rows.length} na tela`, `${rows.length} shown`);
  const t = $("#screen");
  t.replaceChildren(el("tr", {}, ...cols.map(([k, label, ty, cls = "", title = ""]) => {
    const th = el("th", { className: `sortable ${cls} ${k === sortKey ? "sorted" : ""}`, textContent: label + (k === sortKey ? (sortAsc ? " ▲" : " ▼") : ""), tabIndex: 0, title });
    th.setAttribute("aria-sort", k === sortKey ? (sortAsc ? "ascending" : "descending") : "none");
    const go = () => { if (SCR.sortKey === k) SCR.sortAsc = !SCR.sortAsc; else { SCR.sortKey = k; SCR.sortAsc = ty === "s" || k === "rank"; } renderScreen(); };
    th.addEventListener("click", go); th.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), go()));
    return th;
  })));
  if (!rows.length) { t.append(el("tr", {}, el("td", { className: "l muted", colSpan: cols.length, textContent: L("Nenhuma empresa encontrada.", "No company matches.") }))); return; }
  for (const r of rows) {
    expandable(t, OPEN.screen, r.ticker, cols.map(([k, , ty]) => {
      const v = r[k];
      if (k === "ticker") return nameCell(r);
      if (k === "r1y") return trendCell(SPARK()[r.ticker]);
      if (k.endsWith("_score") || k === "score") return scoreCell(num(v));
      if (k === "momentum") return el("td", {}, signed(num(v), 0));
      if (k === "rank") return el("td", { className: "muted", textContent: v || "–" });
      if (ty === "s") { const tx = k === "excluded" ? excludedText(v) : v; return el("td", { className: `l ${k === "excluded" ? "muted" : ""}`, textContent: tx, title: tx, style: "max-width:220px;overflow:hidden;text-overflow:ellipsis" }); }
      return el("td", { textContent: (FMT[k] || ((x) => (Number.isFinite(x) ? x : "–")))(num(v)) });
    }), r, cols.length, renderScreen);
  }
}

// ================================================================ BACKTEST
const BT_LABEL = { composite: L("Nota (10 primeiras)", "Score (top 10)"), magic: L("Fórmula Mágica (10 primeiras)", "Magic Formula (top 10)"),
  value: L("Só valor", "Value only"), quality: L("Só qualidade", "Quality only"), momentum: L("Só momento", "Momentum only"), income: L("Só dividendos", "Income only"),
  eligible: L("Todas as ações elegíveis", "All eligible stocks"), bova11: "BOVA11 (Ibovespa)", cdi: L("CDI (caixa)", "CDI (cash)") };
const BT_SHORT = { composite: L("Nota", "Score"), magic: L("Mágica", "Magic"), value: PILLAR.value, quality: PILLAR.quality, momentum: L("Mom.", "Mom."),
  income: L("Divid.", "Income"), eligible: L("Elegíveis", "All elig."), bova11: "BOVA11", cdi: "CDI" };
const BT_CHART = [["composite", "--s1"], ["bova11", "--s2"], ["cdi", "--s3"], ["eligible", "--other"]];
const BT_ORDER = ["composite", "magic", "value", "quality", "momentum", "income", "eligible", "bova11", "cdi"];

function buildBacktest() {
  const { meta, summary } = S.bt;
  if (!summary) { $("#btNote").textContent = L("O backtest ainda não foi rodado.", "The backtest has not been run yet."); return; }
  const by = Object.fromEntries(summary.map((r) => [r.series, r]));
  $("#btMeta").textContent = L(`${fmtDate(meta.first)} a ${fmtDate(meta.last)} · ${meta.rebalances} listas anuais · regras ${meta.rules}`,
    `${meta.first} to ${meta.last} · ${meta.rebalances} yearly lists · rules ${meta.rules}`);
  $("#btNote").textContent = L(`Todo mês de maio, as ${meta.top_n} primeiras pela nota como o filtro estava naquele dia, compradas em pesos iguais e mantidas por um ano com dividendos reinvestidos; sem custos nem impostos. ` +
    "Comparadas com o BOVA11, com o CDI (caixa) e com a compra de todas as ações elegíveis, o que isola o que a seleção acrescenta.",
  `Every May, the top ${meta.top_n} by score as the screen stood that day, bought in equal weights and held a year with dividends reinvested; no costs or taxes. ` +
    "Compared with BOVA11, with the CDI (cash) and with owning every eligible stock, which isolates what the picking adds.");
  $("#btTiles").replaceChildren(...["composite", "bova11", "cdi", "eligible"].filter((k) => by[k]).map((k) => {
    const r = by[k];
    return el("div", { className: `tile ${k === "composite" ? "lead" : ""}` }, el("div", { className: "k", textContent: BT_LABEL[k] }),
      el("div", { className: "v", textContent: `R$ ${f1(100 * (1 + num(r.total_return)), 0)}` }),
      el("div", { className: "s", textContent: L(`${pct(num(r.cagr), 1)} ao ano · maior queda ${pct(num(r.max_drawdown), 0)}`, `${pct(num(r.cagr), 1)} a year · worst fall ${pct(num(r.max_drawdown), 0)}`) }));
  }));
  const t = $("#btSummary");
  const head = ["", L("R$ 100 viraram", "R$100 became"), L("Ao ano", "Per year"), L("Volatilidade", "Volatility"), L("Maior queda", "Worst fall"),
    L("Melhor ano", "Best year"), L("Pior ano", "Worst year"), L("Anos acima do BOVA11", "Years beating BOVA11"), L("Ao ano vs CDI", "Per year vs CDI")];
  t.replaceChildren(el("tr", {}, ...head.map((h, i) => el("th", { className: i ? "" : "l", textContent: h }))));
  for (const k of BT_ORDER) {
    const r = by[k]; if (!r) continue;
    t.append(el("tr", {},
      el("td", { className: "l" }, k === "composite" ? el("b", { textContent: BT_LABEL[k] }) : BT_LABEL[k]),
      el("td", { textContent: `R$ ${f1(100 * (1 + num(r.total_return)), 0)}` }),
      el("td", {}, signed(num(r.cagr))), el("td", { textContent: pct(num(r.volatility)) }),
      el("td", {}, signed(num(r.max_drawdown), 0)), el("td", {}, signed(num(r.best_year), 0)), el("td", {}, signed(num(r.worst_year), 0)),
      el("td", { textContent: r.years_beating_bova11 || "–" }), el("td", {}, signed(num(r.excess_over_cdi)))));
  }
  buildBtYears(); buildBtCohorts(); buildBtHoldings();
}
function drawBtChart() {
  const curve = S.bt.curve; if (!curve) return;
  const dates = [...new Set(curve.map((r) => r.date))].sort();
  const by = {}; for (const r of curve) (by[r.series] ||= new Map()).set(r.date, +r.value);
  lineChart($("#btChart"), dates, BT_CHART.map(([k, c]) => ({ values: dates.map((d) => by[k]?.get(d) ?? NaN), color: c, label: BT_LABEL[k],
    width: k === "composite" ? 2.5 : 2, endLabel: (v) => `${BT_SHORT[k]} R$${f1(v, 0)}` })),
  { log: true, h: 330, ml: 48, labels: true, mr: 120, legend: true, legendNote: L("· escala logarítmica", "· log scale"), fmt: (v) => `R$${f1(v, 0)}`, tipFmt: (v) => `R$ ${f1(v, 0)}`,
    aria: L("Evolução de R$ 100, escala logarítmica", "Growth of R$100, log scale") });
}
function drawQuintiles() {
  const q = S.bt.quintiles, box = $("#quintiles"); box.replaceChildren();
  if (!q || !q.length) return;
  const elig = num((S.bt.summary.find((r) => r.series === "eligible") || {}).cagr);
  const names = { score: L("Nota", "Score"), value: PILLAR.value, quality: PILLAR.quality, momentum: PILLAR.momentum, income: PILLAR.income,
    growth: L("Crescimento (fora da nota)", "Growth (not scored)") };
  const start = q.map((r) => r.first).filter(Boolean).sort()[0];
  const all = q.map((r) => num(r.cagr));
  const lo = Math.min(0, ...all, elig) - 0.02, hi = Math.max(...all, elig) + 0.03;
  for (const f of Object.keys(names)) {
    const rows = q.filter((r) => r.factor === f).sort((a, b) => a.quintile - b.quintile);
    if (!rows.length) continue;
    const w = 220, h = 170, ml = 4, mr = 4, mt = 14, mb = 18;
    const y = (v) => mt + (1 - (v - lo) / (hi - lo)) * (h - mt - mb);
    const bw = (w - ml - mr) / 5;
    const s = svg("svg", { viewBox: `0 0 ${w} ${h}`, width: "100%", role: "img", "aria-label": L(`${names[f]}: retorno ao ano por quinto`, `${names[f]}: return per year by fifth`) });
    s.append(svg("line", { x1: ml, x2: w - mr, y1: y(0), y2: y(0), stroke: css("--axis") }));
    rows.forEach((r, i) => {
      const v = num(r.cagr), x = ml + i * bw + 4, top = Math.min(y(v), y(0)), hgt = Math.abs(y(v) - y(0));
      const bar = svg("rect", { x, y: top, width: bw - 8, height: Math.max(hgt, 1), rx: 3, fill: css("--s1") });
      bar.addEventListener("pointermove", (ev) => showTip(ev, [el("b", { textContent: `${names[f]} · Q${r.quintile}` }), el("div", { className: "row" }, el("strong", { textContent: pct(v, 1) }), L("ao ano", "a year"))]));
      bar.addEventListener("pointerleave", hideTip); s.append(bar);
      const t = svg("text", { x: x + (bw - 8) / 2, y: v >= 0 ? top - 4 : top + hgt + 11, "text-anchor": "middle", "font-size": 10, fill: css("--ink") });
      t.textContent = pct(v, 1); s.append(t);
      const lab = svg("text", { x: x + (bw - 8) / 2, y: h - 4, "text-anchor": "middle", "font-size": 10, fill: css("--muted") });
      lab.textContent = `Q${r.quintile}`; s.append(lab);
    });
    if (Number.isFinite(elig)) s.append(svg("line", { x1: ml, x2: w - mr, y1: y(elig), y2: y(elig), stroke: css("--other"), "stroke-width": 1.5 }));
    const spread = num(rows[0].cagr) - num(rows[4].cagr);
    box.append(el("div", {}, el("h4", { textContent: names[f] }),
      el("div", { className: "sub", textContent: L(`Q1 − Q5: ${pts(spread)} ao ano · Q1 bateu Q5 em ${rows[0].top_beat_bottom} anos`, `Q1 − Q5: ${pts(spread)}/yr · Q1 beat Q5 in ${rows[0].top_beat_bottom} years`) +
        (rows[0].first && rows[0].first !== start ? ` · ${L("desde", "from")} ${rows[0].first.slice(0, 4)}` : "") }), s));
  }
}
function buildBtYears() {
  const periods = S.bt.periods; if (!periods) return;
  const starts = [...new Set(periods.map((p) => p.start))].sort().reverse();
  const t = $("#btYears");
  t.replaceChildren(el("tr", {}, el("th", { className: "l", textContent: L("Comprada em", "Held from") }), ...BT_ORDER.map((c) => el("th", { className: "c", textContent: BT_SHORT[c] }))));
  for (const d of starts) {
    const row = Object.fromEntries(periods.filter((p) => p.start === d).map((p) => [p.series, num(p.return)]));
    const end = periods.find((p) => p.start === d).end;
    t.append(el("tr", {}, el("td", { className: "l", textContent: fmtDate(d.slice(0, 7)), title: `${fmtDate(d)} → ${fmtDate(end)}` }), ...BT_ORDER.map((c) => retCell(row[c]))));
  }
}
function buildBtCohorts() {
  const cohorts = S.bt.cohorts; if (!cohorts) return;
  const t = $("#btCohorts"), hs = [1, 3, 5];
  t.replaceChildren(
    el("tr", {}, el("th", {}), ...hs.map((h) => el("th", { colSpan: 3, textContent: L(`${h} ano${h > 1 ? "s" : ""}`, `${h} year${h > 1 ? "s" : ""}`), className: "c" }))),
    el("tr", {}, el("th", { className: "l", textContent: L("Comprada em", "Bought") }), ...hs.flatMap(() => [L("Lista", "List"), "BOVA11", "CDI"].map((x) => el("th", { className: "c", textContent: x })))));
  const starts = [...new Set(cohorts.map((c) => c.start))].sort().reverse();
  for (const d of starts) {
    const cells = hs.flatMap((h) => {
      const c = cohorts.find((r) => r.start === d && +r.horizon === h);
      if (!c) return [el("td"), el("td"), el("td")];
      const partial = c.complete === "False";
      const mk = (v) => { const td = retCell(num(v), 0.5 * h ** 0.5); if (partial) { td.classList.add("muted"); td.textContent += "*"; } return td; };
      return [mk(c.composite), mk(c.bova11), mk(c.cdi)];
    });
    t.append(el("tr", {}, el("td", { className: "l", textContent: fmtDate(d.slice(0, 7)) }), ...cells));
  }
}
function buildBtHoldings() {
  const holdings = S.bt.holdings, box = $("#btHoldings"); box.replaceChildren();
  if (!holdings) return;
  const dates = [...new Set(holdings.map((h) => h.date))].sort().reverse();
  dates.forEach((d, i) => {
    const rows = holdings.filter((h) => h.date === d && h.strategy === "composite").sort((a, b) => a.rank - b.rank);
    const avg = rows.map((r) => num(r.period_return)).filter(Number.isFinite);
    const det = el("details", { open: i === 0 });
    det.append(el("summary", { textContent: `${fmtDate(d)}: ${rows.map((r) => r.ticker).join(", ")} (${L("média", "average")} ${pct(avg.reduce((a, b) => a + b, 0) / (avg.length || 1), 0, true)})` }));
    const t = el("table", { className: "dense" });
    t.append(el("tr", {}, ...["#", L("Empresa", "Company"), L("Setor", "Sector"), L("Nota", "Score"), L("Retorno no ano", "Return over the year")]
      .map((h, j) => el("th", { className: j === 1 || j === 2 ? "l" : "", textContent: h }))));
    for (const r of rows) t.append(el("tr", {}, el("td", { textContent: r.rank }), nameCell(r),
      el("td", { className: "l muted", textContent: r.sector }), scoreCell(num(r.metric)), retCell(num(r.period_return))));
    det.append(el("div", { className: "scroll" }, t)); box.append(det);
  });
}
function drawBacktest() { drawBtChart(); drawQuintiles(); }

// ============================================================ TRACK RECORD
function liveCurve() {
  const R = S.status?.rules || "";
  return (S.perf || []).filter((r) => r.strategy === "composite" && (!R || !r.rules || r.rules === R)).map((r) => ({ date: r.date, p: +r.portfolio, b: +r.benchmark }));
}
function buildRecord() {
  const R = S.status?.rules || "";
  const lists = [...new Set((S.picks || []).filter((p) => p.strategy === "composite" && (!R || !p.rules || p.rules === R)).map((p) => p.date))].sort();
  const n = lists.length, s = (k) => (k > 1 ? "s" : "");
  $("#recMeta").textContent = !n ? "" : L(`Registrando desde ${fmtDate(lists[0])} · ${n} lista${s(n)} semana${n > 1 ? "is" : "l"} · regras ${R}`,
    `Recording since ${lists[0]} · ${n} weekly list${s(n)} · rules ${R}`);
  const c = liveCurve();
  $("#recCallout").replaceChildren(...(n < 8 ? [callout(!n ? L("A primeira lista sai na segunda-feira.", "The first list is made on Monday.")
    : L(`Só ${n} lista${s(n)} semana${n > 1 ? "is" : "l"} até agora, ${c.length ? `${c.length} pregão${c.length > 1 ? "es" : ""} de carteira` : "nenhum pregão de carteira ainda"}: nada aqui é resultado ainda. O backtest é a visão longa; esta é a checagem honesta ao vivo, e ela precisa de anos.`,
      `Only ${n} weekly list${s(n)} so far, ${c.length ? `${c.length} session${s(c.length)} held` : "none held yet"}: nothing here is a result yet. The backtest is the long view; this is the honest live check, and it needs years.`))] : []));
  const t = $("#cohorts");
  const rows = (S.cohorts || []).filter((r) => r.strategy === "composite" && (!R || !r.rules || r.rules === R)).sort((a, b) => b.date.localeCompare(a.date));
  t.replaceChildren(el("tr", {}, ...[L("Lista", "List"), L("Retorno", "Return"), "BOVA11", L("Diferença", "Difference"), L("Subiram", "Picks up")]
    .map((h, i) => el("th", { className: i ? "" : "l", textContent: h }))));
  if (!rows.length) { t.append(el("tr", {}, el("td", { className: "l muted", colSpan: 5, textContent: L("Ainda sem listas.", "No lists yet.") }))); return; }
  for (const r of rows) {
    const ret = num(r.return), b = num(r.benchmark);
    t.append(el("tr", {}, el("td", { className: "l", textContent: fmtDate(r.date) }), el("td", {}, signed(ret)), el("td", {}, signed(b)), retCell(ret - b, 0.1, 1), el("td", { textContent: pct(num(r.hit_rate)) })));
  }
}
function drawRecord() {
  const c = liveCurve(), box = $("#chart");
  if (c.length < 2) { box.replaceChildren(el("p", { className: "muted", textContent: L("O histórico começa depois que uma lista é mantida por alguns pregões; volte depois da próxima segunda-feira.",
    "The track record starts once a list has been held for a few sessions; check back after the next Monday.") })); return; }
  lineChart(box, c.map((r) => r.date), [{ values: c.map((r) => r.p), color: "--s1", label: L("Lista da semana (nota)", "Shortlist (composite)"), width: 2.5, endLabel: (v) => `${L("Lista", "List")} ${f1(v, 1)}` },
    { values: c.map((r) => r.b), color: "--s2", label: "BOVA11", endLabel: (v) => `BOVA11 ${f1(v, 1)}` }],
  { h: 260, labels: true, mr: 96, legend: true, fmt: (v) => f1(v, 0), tipFmt: (v) => f1(v, 1), aria: L("Carteira da lista da semana contra o BOVA11", "Shortlist portfolio vs BOVA11") });
}

const BUILD = { overview: buildOverview, screener: buildScreener, backtest: buildBacktest, record: buildRecord };
const DRAW = { overview: drawOverview, backtest: drawBacktest, record: drawRecord };

// ------------------------------------------------------------------- load
(async () => {
  shell(tabFromHash(), null);
  show();
  const [status, screen, picks, perf, cohorts, sparks, mkHist, mkToday, meta, summary, curve, periods, btCohorts, holdings, quintiles] = await Promise.all([
    getJSON("status.json"), get("screen/latest.csv"), get("picks/picks.csv"), get("picks/performance.csv"), get("picks/cohorts.csv"),
    getJSON("screen/sparks.json"), get("market/history.csv"), getJSON("market/today.json"),
    getJSON("backtest/meta.json"), get("backtest/summary.csv"), get("backtest/curve.csv"), get("backtest/periods.csv"),
    get("backtest/cohorts.csv"), get("backtest/holdings.csv"), get("backtest/quintiles.csv")]);
  if (!screen) { $("#status").textContent = L("Não foi possível carregar os dados.", "Could not load the data."); return; }
  Object.assign(S, { status, screen, picks, perf, cohorts, sparks, mkHist, mkToday, bt: { meta: meta || {}, summary, curve, periods, cohorts: btCohorts, holdings, quintiles }, ready: true });
  setStatus(status);
  show();
  onResize($("main"), () => current && DRAW[current]?.());
})();

// B3 Radar: the financials screen (banks, insurers and their holdings), a
// separate ranking. Used by the index page (its own tab) and by the company
// pages of those companies. Loaded after common.js (and index.js).
"use strict";

const PB = L("P/VP", "P/B");
const FIN_METRICS = {
  value: [["book_to_market", L("Patrimônio / valor de mercado", "Book / market value"), (x, r) => `${f1(x, 2)} · ${PB} ${f1(num(r.pb), 2)}`]],
  quality: [["roe", L("Retorno sobre o patrimônio (ROE), últimos 12 meses", "Return on equity, last 12 months"), (x) => pct(x, 1)],
            ["roe_stability", L("Oscilação desse ROE em 3 anos (menor é mais estável)", "Spread of that ROE over 3 years (lower is steadier)"),
              (x) => (Number.isFinite(x) ? `${f1(x * 100, 1)} ${L("p.p.", "pts")}` : "–")]],
  momentum: [["momentum", L("Retorno em 12 meses, sem o último mês", "12-month return, last month left out"), (x) => pct(x, 0, true)]],
  income: [["dividend_yield", L("Dividendos dos últimos 12 meses / preço", "Dividends of the last 12 months / price"), (x) => pct(x, 1)]],
};
const FIN_PILLAR = { value: PILLAR.value, quality: PILLAR.quality, momentum: PILLAR.momentum, income: PILLAR.income };
const FIN_GROUP = { bank: L("Banco", "Bank"), insurance: L("Seguradora", "Insurance"), holding: "Holding", other: L("Outro", "Other") };
const FIN_BASIS = { con: L("consolidadas", "consolidated"), ind: L("individuais", "individual") };
const FIN_SEPARATE = L("Um ranking à parte: percentis só entre bancos, seguradoras e suas holdings. Não é comparável com a nota principal.",
  "A separate ranking: percentiles among banks, insurers and their holdings only. Not comparable with the main score.");

function finBreakdown(r, { among = L(" entre as financeiras elegíveis", " among eligible financials"), meta = true } = {}) {
  const box = el("div", { className: "bd" });
  for (const [k, ms] of Object.entries(FIN_METRICS)) {
    const col = el("div", {}, el("h4", { textContent: `${FIN_PILLAR[k]}: ${f1(num(r[k + "_score"]), 0)} / 100` }));
    for (const [m, label, fmt] of ms) {
      const p = num(r["p_" + m]);
      col.append(el("div", { className: "m" },
        el("span", { textContent: label }), el("strong", { textContent: fmt(num(r[m]), r) }),
        el("div", { className: "bar", role: "img", ariaLabel: `${L("percentil", "percentile")} ${f1(p, 0)}` }, el("i", { style: `width:${Number.isFinite(p) ? p : 0}%` })),
        el("span", { className: "pctl", textContent: Number.isFinite(p) ? `${L("percentil", "percentile")} ${f1(p, 0)}${among}` : L("sem nota", "not scored") })));
    }
    box.append(col);
  }
  const shown = el("div", {}, el("h4", { textContent: L("Aparecem, mas fora da nota", "Shown, not scored") }));
  for (const [label, v] of [[L("P/L", "P/E"), f1(num(r.pe))], [L("Earnings yield (lucro líquido / valor de mercado)", "Earnings yield (net income / market cap)"), pct(num(r.earnings_yield), 1)],
    [L("Payout (dividendos / lucro líquido)", "Payout (dividends / net income)"), pct(num(r.payout))], [L("Lucro líquido, últimos 12 meses", "Net income, last 12 months"), brl(num(r.net_income))],
    [L("Patrimônio líquido", "Equity"), brl(num(r.equity))]]) {
    shown.append(el("div", { className: "m" }, el("span", { textContent: label }), el("strong", { textContent: v })));
  }
  box.append(shown);
  if (meta) box.append(el("div", { className: "meta", textContent: L(
    `Demonstrações até ${fmtDate(r.fundamentals_date)} (${FIN_BASIS[r.basis] || "–"}), entregues à CVM em ${fmtDate(r.filed)} · ` +
    `lucro líquido e patrimônio são a parte dos controladores · número de ações: ${(r.shares_source || "–").toUpperCase()} · tickers: ${r.tickers || r.ticker}` +
    (r.excluded ? ` · fora do ranking: ${excludedText(r.excluded)}` : ""),
    `Statements up to ${r.fundamentals_date || "–"} (${FIN_BASIS[r.basis] || "–"}), filed with CVM on ${r.filed || "–"} · ` +
    `net income and equity are the controlling shareholders' share · share count from ${(r.shares_source || "–").toUpperCase()} · tickers: ${r.tickers || r.ticker}` +
    (r.excluded ? ` · not ranked: ${r.excluded}` : "")) }));
  return box;
}

// ================================================================ INDEX TAB
const FIN = { rows: null, preset: "ranked", sortKey: "rank", sortAsc: true, open: new Set(), ready: false };
const FIN_COLS = [
  ["rank", "#", "n"], ["ticker", L("Empresa", "Company"), "s", "l sticky"], ["r1y", L("12M", "1Y"), "n", "", L("Retorno total, últimos 12 meses", "Total return, last 12 months")],
  ["score", L("Nota", "Score"), "n", "c", L("Nota das financeiras: percentis só entre as financeiras", "Financials score: percentiles among financials only")],
  ["value_score", "V", "n", "c", L("Valor: patrimônio / valor de mercado", "Value: book / market")],
  ["quality_score", "Q", "n", "c", L("Qualidade: o ROE e a sua estabilidade", "Quality: ROE and its stability")],
  ["momentum_score", "M", "n", "c", PILLAR.momentum], ["income_score", L("D", "I"), "n", "c", PILLAR.income],
  ["pb", PB, "n", "", L("Preço / valor patrimonial (o patrimônio dos controladores)", "Price / book (the controlling shareholders' equity)")], ["pe", L("P/L", "P/E"), "n"],
  ["roe", "ROE", "n", "", L("Lucro líquido dos últimos 12 meses / patrimônio líquido", "Net income of the last 12 months / equity")],
  ["roe_stability", L("Oscilação do ROE", "ROE spread"), "n", "", L("Desvio padrão do ROE nos últimos 3 anos de demonstrações (menor é mais estável)",
    "Standard deviation of the ROE over the last 3 years of statements (lower is steadier)")],
  ["payout", "Payout", "n", "", L("Dividendos dos últimos 12 meses / lucro líquido", "Dividends of the last 12 months / net income")],
  ["dividend_yield", L("DY", "Div. yield"), "n", "", "Dividend yield"],
  ["momentum", "12–1m", "n", "", L("Retorno de 12 meses atrás até 1 mês atrás", "Return from 12 months to 1 month ago")], ["market_cap", L("Valor de mercado", "Mkt cap"), "n"],
  ["group", L("Tipo", "Type"), "s", "l"], ["excluded", L("Fora do ranking por", "Not ranked because"), "s", "l"],
];
const FIN_FMT = { pb: (x) => f1(x, 2), pe: f1, roe: (x) => pct(x, 1), roe_stability: (x) => f1(x * 100, 1),
  payout: (x) => pct(x), dividend_yield: (x) => pct(x, 1), market_cap: brl };
const FIN_PRESETS = [["ranked", L("Ranqueadas", "Ranked"), (r) => !r.excluded], ["excluded", L("Fora do ranking", "Not ranked"), (r) => !!r.excluded]];

async function buildFinTab() {
  const [rows, meta, q, per, btMeta] = await Promise.all([get("screen/financials.csv"), getJSON("screen/financials.json"),
    get("backtest/financials_quintiles.csv"), get("backtest/financials_periods.csv"), getJSON("backtest/financials_meta.json")]);
  Object.assign(FIN, { rows: rows || [], meta: meta || {}, q, per, btMeta, ready: true });
  const n = FIN.rows.filter((r) => !r.excluded).length;
  $("#finMeta").textContent = !meta ? "" : L(`${FIN.rows.length} empresas · ${n} ranqueadas · fechamento de ${fmtDate(meta.asof)} · regras próprias ${meta.rules}`,
    `${FIN.rows.length} companies · ${n} ranked · closing prices of ${meta.asof} · own rules ${meta.rules}`);
  $("#finCallout").replaceChildren(callout(L(`${FIN_SEPARATE} O filtro principal deixa essas empresas de fora, porque EBIT, valor da firma e dívida líquida não significam nada para um banco. ` +
    `Aqui elas são comparadas só entre si (${n} hoje), então um 70 aqui e um 70 no filtro de ações dizem coisas diferentes. Só aparecem aqui: nunca entram na lista da semana, no histórico ao vivo nem no backtest principal.`,
  `${FIN_SEPARATE} The main screen leaves these companies out, because EBIT, enterprise value and net debt mean nothing for a bank. ` +
    `Here they are ranked only against each other (${n} today), so a 70 here and a 70 in the screener say different things. Shown only: never in the weekly list, the track record or the main backtest.`)));
  $("#finPresets").replaceChildren(...FIN_PRESETS.map(([k, label, f]) => {
    const b = el("button", { className: "preset", type: "button" }, label, el("span", { className: "n", textContent: FIN.rows.filter(f).length }));
    b.dataset.k = k;
    b.addEventListener("click", () => { FIN.preset = k; renderFinTable(); });
    return b;
  }));
  renderFinTable();
  buildFinBacktest();
  drawFinTab();
}

function renderFinTable() {
  for (const b of $("#finPresets").children) b.setAttribute("aria-pressed", String(b.dataset.k === FIN.preset));
  const pf = FIN_PRESETS.find(([k]) => k === FIN.preset)[2];
  const cols = FIN_COLS.filter(([k]) => FIN.preset === "excluded" || k !== "excluded");
  const sp = (typeof SPARK === "function" ? SPARK() : {}) || {};
  const val = (r, k) => (k === "r1y" ? num(sp[r.ticker]?.r1y) : r[k]);
  const type = Object.fromEntries(FIN_COLS.map(([k, , t]) => [k, t]));
  const { sortKey, sortAsc } = FIN;
  const rows = FIN.rows.filter(pf).sort((a, b) => {
    const [x, y] = [val(a, sortKey), val(b, sortKey)];
    if (type[sortKey] === "n") { const [u, v] = [num(x), num(y)]; if (!Number.isFinite(u)) return 1; if (!Number.isFinite(v)) return -1; return sortAsc ? u - v : v - u; }
    return sortAsc ? String(x).localeCompare(String(y)) : String(y).localeCompare(String(x));
  });
  const t = $("#finTable");
  t.replaceChildren(el("tr", {}, ...cols.map(([k, label, ty, cls = "", title = ""]) => {
    const th = el("th", { className: `sortable ${cls} ${k === sortKey ? "sorted" : ""}`, textContent: label + (k === sortKey ? (sortAsc ? " ▲" : " ▼") : ""), tabIndex: 0, title });
    th.setAttribute("aria-sort", k === sortKey ? (sortAsc ? "ascending" : "descending") : "none");
    const go = () => { if (FIN.sortKey === k) FIN.sortAsc = !FIN.sortAsc; else { FIN.sortKey = k; FIN.sortAsc = ty === "s" || k === "rank" || k === "roe_stability" || k === "pb" || k === "pe"; } renderFinTable(); };
    th.addEventListener("click", go); th.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), go()));
    return th;
  })));
  if (!rows.length) { t.append(el("tr", {}, el("td", { className: "l muted", colSpan: cols.length, textContent: L("Nenhuma empresa aqui.", "No company here.") }))); return; }
  for (const r of rows) {
    const cells = cols.map(([k, , ty]) => {
      const v = r[k];
      if (k === "ticker") return nameCell(r);
      if (k === "r1y") return trendCell(sp[r.ticker]);
      if (k.endsWith("_score") || k === "score") return scoreCell(num(v));
      if (k === "momentum") return el("td", {}, signed(num(v), 0));
      if (k === "rank") return el("td", { className: "muted", textContent: v || "–" });
      if (k === "group") return el("td", { className: "l muted", textContent: FIN_GROUP[v] || v });
      if (ty === "s") { const tx = k === "excluded" ? excludedText(v) : v; return el("td", { className: "l muted", textContent: tx, title: tx, style: "max-width:220px;overflow:hidden;text-overflow:ellipsis" }); }
      return el("td", { textContent: (FIN_FMT[k] || ((x) => (Number.isFinite(x) ? x : "–")))(num(v)) });
    });
    const tr = el("tr", { className: "clickable", tabIndex: 0 }, ...cells);
    tr.setAttribute("aria-expanded", String(FIN.open.has(r.ticker)));
    const toggle = () => { FIN.open.has(r.ticker) ? FIN.open.delete(r.ticker) : FIN.open.add(r.ticker); renderFinTable(); };
    tr.addEventListener("click", toggle);
    tr.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), toggle()));
    t.append(tr);
    if (FIN.open.has(r.ticker)) t.append(el("tr", { className: "detail" }, el("td", { colSpan: cols.length }, finBreakdown(r))));
  }
}

const FIN_FACTORS = { score: L("Nota", "Score"), value: `${PILLAR.value} (${PB})`, quality: `${PILLAR.quality} (ROE)`, momentum: PILLAR.momentum, income: PILLAR.income };
function finCagr(f, k) { return num(((FIN.q || []).find((r) => r.factor === f && +r.quintile === k) || {}).cagr); }

function buildFinBacktest() {
  const m = FIN.btMeta, q = FIN.q;
  if (!m || !q || !q.length) {
    $("#finBtNote").textContent = L("O backtest das financeiras ainda não foi rodado (ele roda todo mês, junto com o backtest principal).",
      "The financials backtest has not been run yet (it runs monthly, with the main backtest).");
    return;
  }
  const counts = Object.values(m.eligible || {});
  const used = Object.entries(m.eligible || {}).filter(([d]) => d >= m.first).map(([, n]) => n);
  const lo = Math.floor(Math.min(...used) / 5), hi = Math.ceil(Math.max(...used) / 5);
  $("#finBtNote").textContent = L(`Todo mês de maio, as financeiras elegíveis como estavam naquele dia (só com o que era público na data), divididas em quintos pela nota das financeiras e por cada pilar (Q1 = melhor), ` +
    `e cada quinto mantido por um ano em pesos iguais, com dividendos reinvestidos. Desde ${m.first.slice(0, 4)}: o primeiro maio com pelo menos ${m.min_names} financeiras elegíveis ` +
    `(de ${Math.min(...counts)} a ${Math.max(...counts)} por ano desde 2012, ou seja, ${lo}–${hi} ações por quinto). A linha cinza é o conjunto das financeiras elegíveis.`,
  `Each May, every eligible financial as it stood that day (point in time), split into fifths by the financials score and by each pillar (Q1 = best), ` +
    `each fifth held a year in equal weights with dividends reinvested. From ${m.first.slice(0, 4)}: the first May with at least ${m.min_names} eligible financials ` +
    `(${Math.min(...counts)} to ${Math.max(...counts)} a year since 2012, so ${lo}–${hi} stocks a fifth). The gray line is all eligible financials.`);
  const all = finCagr("all", 0), bova = finCagr("bova11", 0), cdi = finCagr("cdi", 0);
  const s1 = finCagr("score", 1), s5 = finCagr("score", 5);
  const wins = (q.find((r) => r.factor === "score" && +r.quintile === 1) || {}).top_beat_bottom || "–";
  const steps = [1, 2, 3, 4, 5].map((k) => finCagr("score", k));
  const mono = steps.every((v, i) => !i || v <= steps[i - 1]);
  const worst = steps.indexOf(Math.min(...steps)) + 1;
  const pillars = ["value", "quality", "momentum", "income"].map((f) => [f, finCagr(f, 1) - finCagr(f, 5)]).sort((a, b) => b[1] - a[1]);
  const y0 = m.first.slice(0, 4), y1 = m.last.slice(0, 4), wide = FIN_FACTORS[pillars[0][0]], narrow = FIN_FACTORS[pillars[3][0]];
  $("#finBtRead").textContent = L(`O que mostra, de ${y0} a ${y1}: o quinto superior pela nota rendeu ${pct(s1, 1)} ao ano e o quinto inferior, ${pct(s5, 1)}, ` +
    `contra ${pct(all, 1)} do conjunto das financeiras elegíveis, ${pct(bova, 1)} do BOVA11 e ${pct(cdi, 1)} do CDI; o quinto superior bateu o inferior em ${wins} anos. ` +
    `${mono ? "Os quintos descem em ordem." : `Os quintos não estão em ordem: o Q${worst} foi o pior.`} ` +
    `Por pilar, a maior diferença entre o quinto superior e o inferior é a de ${wide} (${pts(pillars[0][1])} ao ano), e a menor, a de ${narrow} (${pts(pillars[3][1])}). ` +
    `Com ${m.rebalances} períodos anuais e tão poucos nomes por quinto, uma única ação move um quinto em vários pontos: isto descreve o passado e não é prova de que a nota funciona.`,
  `What it shows, ${y0} to ${y1}: the top fifth by score returned ${pct(s1, 1)} a year and the bottom fifth ${pct(s5, 1)}, ` +
    `against ${pct(all, 1)} for all eligible financials, ${pct(bova, 1)} for BOVA11 and ${pct(cdi, 1)} for the CDI; the top fifth beat the bottom in ${wins} years. ` +
    `${mono ? "The fifths step down in order." : `The fifths are not in order: Q${worst} did worst.`} ` +
    `By pillar, the widest gap between top and bottom fifths is ${wide} (${pts(pillars[0][1])} a year), the narrowest ${narrow} (${pts(pillars[3][1])}). ` +
    `With ${m.rebalances} yearly periods and so few names a fifth, one stock moves a fifth by several points: this describes the past and is not evidence that the score works.`);
}

function drawFinTab() {
  if (!FIN.ready) return;
  const q = FIN.q, box = $("#finQuint");
  box.replaceChildren();
  if (!q || !q.length) return;
  const all = finCagr("all", 0);
  const vals = q.filter((r) => +r.quintile > 0).map((r) => num(r.cagr));
  const lo = Math.min(0, ...vals, all) - 0.02, hi = Math.max(...vals, all) + 0.03;
  for (const [f, name] of Object.entries(FIN_FACTORS)) {
    const rows = q.filter((r) => r.factor === f).sort((a, b) => a.quintile - b.quintile);
    if (!rows.length) continue;
    const w = 220, h = 170, ml = 4, mr = 4, mt = 14, mb = 18, bw = (w - ml - mr) / 5;
    const y = (v) => mt + (1 - (v - lo) / (hi - lo)) * (h - mt - mb);
    const s = svg("svg", { viewBox: `0 0 ${w} ${h}`, width: "100%", role: "img", "aria-label": L(`${name}: retorno ao ano por quinto`, `${name}: return per year by fifth`) });
    s.append(svg("line", { x1: ml, x2: w - mr, y1: y(0), y2: y(0), stroke: css("--axis") }));
    rows.forEach((r, i) => {
      const v = num(r.cagr), x = ml + i * bw + 4, top = Math.min(y(v), y(0)), hgt = Math.abs(y(v) - y(0));
      const bar = svg("rect", { x, y: top, width: bw - 8, height: Math.max(hgt, 1), rx: 3, fill: css("--s1") });
      bar.addEventListener("pointermove", (ev) => showTip(ev, [el("b", { textContent: `${name} · Q${r.quintile}` }), el("div", { className: "row" }, el("strong", { textContent: pct(v, 1) }), L("ao ano", "a year"))]));
      bar.addEventListener("pointerleave", hideTip); s.append(bar);
      const t = svg("text", { x: x + (bw - 8) / 2, y: v >= 0 ? top - 4 : top + hgt + 11, "text-anchor": "middle", "font-size": 10, fill: css("--ink") });
      t.textContent = pct(v, 1); s.append(t);
      const lab = svg("text", { x: x + (bw - 8) / 2, y: h - 4, "text-anchor": "middle", "font-size": 10, fill: css("--muted") });
      lab.textContent = `Q${r.quintile}`; s.append(lab);
    });
    if (Number.isFinite(all)) s.append(svg("line", { x1: ml, x2: w - mr, y1: y(all), y2: y(all), stroke: css("--other"), "stroke-width": 1.5 }));
    const spread = num(rows[0].cagr) - num(rows[4].cagr);
    box.append(el("div", {}, el("h4", { textContent: name }),
      el("div", { className: "sub", textContent: L(`Q1 − Q5: ${pts(spread)} ao ano · Q1 bateu Q5 em ${rows[0].top_beat_bottom} anos`,
        `Q1 − Q5: ${pts(spread)}/yr · Q1 beat Q5 in ${rows[0].top_beat_bottom} years`) }), s));
  }
}

if (typeof BUILD !== "undefined" && typeof DRAW !== "undefined") { BUILD.financials = buildFinTab; DRAW.financials = drawFinTab; }

// ============================================================ COMPANY PAGE
// ``d``: the company's JSON (d.financials once the monthly rebuild has run), ``r``: today's row of
// screen/financials.csv, ``meta``: screen/financials.json. Fills the page's own boxes.
function finChips(r, meta) {
  const n = meta?.eligible;
  return [el("span", { className: "chip", textContent: r.excluded
    ? L(`Filtro das financeiras: fora do ranking (${excludedText(r.excluded)})`, `Financials screen: not ranked (${r.excluded})`)
    : L(`Filtro das financeiras: #${r.rank} de ${n ?? "–"}`, `Financials screen: #${r.rank} of ${n ?? "–"}`) }),
    el("span", { className: "chip warn", textContent: `${PB} ${f1(num(r.pb), 2)} · ROE ${pct(num(r.roe), 1)} · ${L(`negocia ${brl(num(r.liquidity))}/dia`, `trades ${brl(num(r.liquidity))}/day`)}` }),
    el("a", { className: "chip warn", href: "./#/financials", style: "text-decoration:none",
      textContent: L("Fora da nota principal: ranking só entre as financeiras →", "Out of the main score: ranked among financials only →") })];
}

function finHistory(d) { return d.financials?.history || null; }

function finCards(d, r, sp, card) {
  const H = finHistory(d), hist = (k) => (H ? [...H[k].map(num), num(r[k])] : [num(r[k])]);
  const medPB = H ? median(H.pb.map(num).filter((x) => x > 0)) : NaN, medDY = H ? median(H.dividend_yield.map(num)) : NaN;
  const cards = [];
  if (sp) cards.push(card({ k: L("Preço", "Price"), sub: L(`${d.ticker} · 12 meses, retorno total`, `${d.ticker} · last 12 months, total return`), value: `R$ ${f1(num(r.price), 2)}`,
    d: ["1D ", change(sp.r1d)], spark: sp.w, foot: [["1M ", change(sp.r1m)], [L("12M ", "1Y "), change(sp.r1y)]] }));
  cards.push(card({ k: L("Nota das financeiras", "Financials score"), sub: L("só entre as financeiras, a cada trimestre", "among financials only, each quarter"),
    value: r.excluded ? L("fora do ranking", "not ranked") : `${f1(num(r.score), 0)} · #${r.rank}`,
    spark: hist("score"), ref: 50, foot: [`V ${f1(num(r.value_score), 0)} · Q ${f1(num(r.quality_score), 0)}`, `M ${f1(num(r.momentum_score), 0)} · ${L("D", "I")} ${f1(num(r.income_score), 0)}`] }));
  cards.push(card({ k: PB, sub: L("preço / valor patrimonial", "price / book value"), value: f1(num(r.pb), 2), d: Number.isFinite(medPB) ? `${L("mediana", "median")} ${f1(medPB, 2)}` : null,
    spark: hist("pb"), ref: medPB, foot: [`${L("P/L", "P/E")} ${f1(num(r.pe))} · ROE ${pct(num(r.roe), 1)}`] }));
  cards.push(card({ k: "Dividend yield", sub: L("últimos 12 meses / preço", "last 12 months / price"), value: pct(num(r.dividend_yield), 1),
    d: Number.isFinite(medDY) ? `${L("mediana", "median")} ${pct(medDY, 1)}` : null, spark: hist("dividend_yield"), ref: medDY, foot: [`payout ${pct(num(r.payout))}`] }));
  cards.push(card({ k: L("Valor de mercado", "Market cap"), sub: L("todas as classes de ações", "all share classes"), value: brl(num(r.market_cap)), spark: H?.market_cap ? hist("market_cap") : [],
    foot: [`${L("demonstrações", "statements")} ${fmtDate(r.fundamentals_date)}`] }));
  return cards;
}

// Retitles the company page's sections for a financial company.
function finRetitle(r, meta) {
  const set = (id, eyebrow, note) => {
    const sec = $(`#${id}`)?.closest("section"); if (!sec) return;
    if (eyebrow) $(".eyebrow", sec).textContent = eyebrow;
    if (note !== undefined) { const n = $(".note", sec); if (n) n.textContent = note; }
  };
  const basis = FIN_BASIS[r.basis] || FIN_BASIS.con;
  set("why", L("De onde vem a posição entre as financeiras", "Why it ranks where it does among financials"),
    `${FIN_SEPARATE} ${L(`Percentis entre as ${meta?.eligible ?? ""} financeiras elegíveis de hoje (0–100).`, `Percentiles among today's ${meta?.eligible ?? ""} eligible financials (0–100).`)}`);
  set("score", L("A nota das financeiras ao longo do tempo", "The financials score over time"),
    L("O filtro das financeiras como estava em cada trimestre (só com o que era público na época). Lacunas: não era elegível naquele trimestre (baixa liquidez, listada há pouco tempo, sem demonstrações).",
      "The financials screen as it stood each quarter (point in time). Gaps: not eligible that quarter (illiquid, too new, no statements)."));
  set("valuation", L("Barata ou cara frente ao próprio histórico?", "Cheap or expensive against its own history?"),
    L("O valuation de cada trimestre; a linha cinza é a mediana da própria empresa.", "Each quarter's valuation; the gray line is the company's own median."));
  set("business", L("O negócio", "The business"),
    L(`Lucro líquido dos últimos doze meses a cada entrega à CVM, patrimônio líquido e retorno sobre o patrimônio: a parte dos controladores, demonstrações ${basis}. ` +
      "Receita, EBIT e dívida líquida de um banco ficam de fora: para quem empresta dinheiro, eles significam outra coisa.",
    `Trailing twelve months of net income at every filing with CVM, equity and return on equity: the controlling shareholders' share, ${basis} statements. ` +
      "A bank's revenue, EBIT and net debt are left out: they mean something else for a lender."));
  set("backtest", L("No backtest das financeiras", "In the financials backtest"),
    L("Em cada maio, o seu quinto pela nota das financeiras entre as financeiras elegíveis (Q1 = melhor), e como foi no ano seguinte.",
      "Each May, its fifth by the financials score among eligible financials (Q1 = best), and how it did over the following year."));
}

// ``what``: [Portuguese, English], e.g. ["O histórico trimestral", "The quarterly history"].
function finNoHistory(box, [pt, en]) {
  box.replaceChildren(el("p", { className: "muted", textContent: L(`${pt} é refeito todo mês com o backtest; aparece aqui depois da próxima atualização.`,
    `${en} is rebuilt monthly with the backtest; it appears here after the next rebuild.`) }));
}
const FIN_QUARTERLY = ["O histórico trimestral", "The quarterly history"];

function finDraw(d, r) {
  const H = finHistory(d), F = d.financials?.fundamentals;
  const fmtS = (v) => f1(v, 0);
  const pill = $("#pillars"); pill.replaceChildren();
  if (!H) { finNoHistory($("#score"), FIN_QUARTERLY); finNoHistory($("#valuation"), FIN_QUARTERLY); }
  else {
    lineChart($("#score"), H.dates, [{ values: H.score.map(num), color: "--s1", label: L("nota das financeiras", "financials score"), width: 2.5 }],
      { h: 200, fmt: fmtS, yMin: 0, yMax: 100, fixed: true, ticks: [0, 25, 50, 75, 100], aria: L("Nota das financeiras a cada trimestre", "Financials score each quarter") });
    for (const [k, key] of [[FIN_FACTORS.value, "value_score"], [FIN_FACTORS.quality, "quality_score"], [FIN_FACTORS.momentum, "momentum_score"], [FIN_FACTORS.income, "income_score"]]) {
      const cell = el("div", { className: "mini" }, el("h4", { textContent: k }), el("div", { className: "val", textContent: `${L("hoje", "now")} ${fmtS(num(r[key]))}` }), el("div"));
      pill.append(cell);
      lineChart(cell.lastChild, H.dates, [{ values: (H[key] || []).map(num), color: "--s1", label: k }], { h: 110, fmt: fmtS, yMin: 0, yMax: 100, fixed: true, ticks: [0, 50, 100] });
    }
    const val = $("#valuation"); val.replaceChildren();
    for (const [label, key, fmt] of [[PB, "pb", (v) => f1(v, 2)], [L("P/L", "P/E"), "pe", (v) => f1(v)], ["Dividend yield", "dividend_yield", (v) => pct(v, 1)]]) {
      const v = H[key].map(num).map((x) => (key !== "dividend_yield" && (x <= 0 || x > 100) ? NaN : x));
      const med = median(v);
      const cell = el("div", { className: "mini" }, el("h4", { textContent: label }), el("div", { className: "val",
        textContent: L(`hoje ${fmt(num(r[key]))} · mediana própria ${fmt(med)}`, `now ${fmt(num(r[key]))} · own median ${fmt(med)}`) }), el("div"));
      val.append(cell);
      lineChart(cell.lastChild, H.dates, [{ values: v, color: "--s1", label }], { h: 150, fmt, ref: med, refLabel: L("mediana própria", "own median"),
        clipHi: key === "dividend_yield" ? undefined : 4 * med, yMin: 0 });
    }
  }
  const bus = $("#business"); bus.replaceChildren();
  if (!F || !F.dates.length) { finNoHistory(bus, ["O histórico das demonstrações", "The statement history"]); return; }
  for (const [key, label, values, fmt] of [["net_income", L("Lucro líquido (12M)", "Net income (TTM)"), F.net_income.map(num), brl], ["equity", L("Patrimônio líquido", "Equity"), F.equity.map(num), brl],
    ["roe", L("Retorno sobre o patrimônio (12M)", "Return on equity (TTM)"), F.roe.map(num), (v) => pct(v)], ["payout", "Payout", H ? H.payout.map(num) : [], (v) => pct(v)]]) {
    const dates = key === "payout" ? (H ? H.dates : []) : F.dates;
    const last = values.filter(Number.isFinite).at(-1);
    const cell = el("div", { className: "mini" }, el("h4", { textContent: label }), el("div", { className: "val", textContent: `${L("último", "latest")} ${fmt(last)}` }), el("div"));
    bus.append(cell);
    if (dates.length < 2) { finNoHistory(cell.lastChild, ["Este histórico", "This history"]); continue; }
    lineChart(cell.lastChild, dates, [{ values, color: "--s1", label }], { h: 140, fmt, ref: key === "net_income" ? 0 : undefined, refLabel: L("zero", "zero"),
      ml: fmt === brl ? 70 : 46 });
  }
}

function finBacktestTable(d) {
  const B = d.financials?.backtest || [];
  if (!d.financials) return el("p", { className: "muted", textContent: L("Refeito todo mês com o backtest; aparece aqui depois da próxima atualização.", "Rebuilt monthly with the backtest; appears here after the next rebuild.") });
  if (!B.length) return el("p", { className: "muted", textContent: L("Nunca esteve entre as financeiras elegíveis numa data do backtest (desde 2015).", "Never among the eligible financials on a backtest date (from 2015).") });
  const t = el("table");
  t.append(el("tr", {}, ...[L("Comprada em", "Bought"), L("Quinto", "Fifth"), L("Posição", "Rank"), L("Retorno no ano", "Return over the year")]
    .map((h, i) => el("th", { className: i ? "" : "l", textContent: h }))));
  for (const b of B) t.append(el("tr", {}, el("td", { className: "l", textContent: fmtDate(b.date) }), el("td", { textContent: `Q${b.quintile}` }),
    el("td", { textContent: L(`#${b.rank} de ${b.of}`, `#${b.rank} of ${b.of}`) }), retCell(num(b.return))));
  return t;
}

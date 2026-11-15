// B3 Radar: language (Portuguese by default, English on request) and number and date formats per
// language. The same approach as political-eye (docs/lib/i18n.js), as a plain script loaded before
// common.js. The choice comes from ?lang=, then what the reader picked last time, then Portuguese.
// It is fixed for the life of a page: the switch reloads it, so a constant built with L() when a
// script loads (tab names, column headers) is always in the right language.
//
// Making a string bilingual
//   Static HTML is written in Portuguese and carries the English beside it:
//     <h1 data-en="Screener">Filtro de ações</h1>                               text only
//     <li data-en-html="<b>One path:</b> …"><b>Um só caminho:</b> …</li>        text with markup (same links and tags)
//     <input placeholder="Ticker ou empresa" data-en-placeholder="Ticker or company">
//                                       likewise data-en-title, data-en-aria-label, data-en-content (<meta>)
//   data-en replaces the element's whole text: put a label beside an <input> in its own <span>.
//   Text that is the same in both languages (a brand, a file name) goes in an element with translate="no".
//   In scripts: L("Nota", "Score"), and L(`${n} lista${n === 1 ? "" : "s"}`, `${n} list${n === 1 ? "" : "s"}`).
//   Numbers and dates the reader sees go through f1, pct, pts, brl (common.js) or fmtNum, fmtDate (here),
//   never toFixed. Strings written by the Python package are translated on the page: exclusion reasons
//   (EXCLUDED) and sector groups (SECTOR_GROUPS) in common.js. tests/test_site_i18n.py fails on HTML text
//   left without its English.
//
// Glossary (English -> Portuguese), so every page says the same thing:
//   score -> nota · pillar -> pilar · value, quality, momentum, income, growth -> valor, qualidade,
//     momento, dividendos, crescimento (V Q M I G -> V Q M D C)
//   screener -> filtro de ações · shortlist -> lista da semana · track record -> histórico ao vivo ·
//     backtest -> backtest · Magic Formula -> Fórmula Mágica · rules fingerprint -> impressão digital das regras
//   watchlist -> favoritas (to watch -> acompanhar) · avoid list -> lista a evitar · bottom 10 -> as 10 piores ·
//     bottom fifth -> quinto inferior · peers -> pares · rebalance -> rebalanceamento · turnover -> giro ·
//     financials (banks, insurers, holdings) -> financeiras · ranked / not ranked -> no ranking / fora do ranking
//   earnings yield -> earnings yield (EBIT / valor da firma) · dividend yield -> dividend yield (DY in tables) ·
//     EV -> valor da firma · P/E -> P/L · P/B -> P/VP · EV/EBIT, ROE, ROIC, JCP, CDI, IPCA, payout -> unchanged
//   market cap -> valor de mercado · daily volume -> volume diário · net debt -> dívida líquida ·
//     revenue -> receita · net income -> lucro líquido · equity -> patrimônio líquido · TTM -> 12M · statements -> demonstrações ·
//     filed with CVM -> entregue à CVM · eligible -> elegível · illiquid -> baixa liquidez
//   cash -> CDI · after inflation -> real · percentage points (pts) -> p.p. · per year -> ao ano ·
//     1D 1M 1Y -> 1D 1M 12M · worst fall -> maior queda · fifths -> quintos · point in time ->
//     só o que era público na data
//   Tickers, company names and CVM's sector names stay as they are (the short sector groups do not: SECTOR_GROUPS).
"use strict";

const LANGS = { pt: { label: "PT", name: "Português", tag: "pt-BR" }, en: { label: "EN", name: "English", tag: "en" } };
const LANG_KEY = "b3radar-lang";
const isLang = (l) => typeof l === "string" && Object.hasOwn(LANGS, l);

const LANG = (() => {
  if (typeof location === "undefined") return "pt";   // Node (tests/i18n_check.mjs)
  const q = new URLSearchParams(location.search).get("lang");
  if (isLang(q)) { try { localStorage.setItem(LANG_KEY, q); } catch { /* storage blocked */ } return q; }
  try { const s = localStorage.getItem(LANG_KEY); if (isLang(s)) return s; } catch { /* storage blocked */ }
  return "pt";
})();
const lang = () => LANG;

/** Inline text in both languages: L("Nota", "Score"). */
const L = (pt, en) => (LANG === "en" ? en : pt);

/** Switch language: remembered, in the URL (so a shared link keeps it), then the page reloads. */
function setLang(l) {
  if (!isLang(l) || l === LANG) return;
  try { localStorage.setItem(LANG_KEY, l); } catch { /* storage blocked: the URL carries it */ }
  const p = new URLSearchParams(location.search);
  if (l === "pt") p.delete("lang"); else p.set("lang", l);
  const q = p.toString();
  history.replaceState(null, "", (q ? `?${q}` : location.pathname) + location.hash);
  location.reload();
}

// ------------------------------------------------------------ numbers and dates
// pt-BR: 1.234,5 · 12,6% · R$ 1,2 bi · 13/11/2026. en: 1,234.5 · 12.6% · R$ 1.2bn · 2026-11-13.
const NUMBER_FORMATS = {};
/** A number with exactly d decimals in the page's language; "–" when missing. */
function fmtNum(x, d = 0) {
  if (!Number.isFinite(x)) return "–";
  const f = (NUMBER_FORMATS[d] ||= new Intl.NumberFormat(LANGS[LANG].tag, { minimumFractionDigits: d, maximumFractionDigits: d }));
  const r = f.format(x);
  return /^-[0.,]+$/.test(r) ? r.slice(1) : r;   // -0,0 rounds to zero: no minus sign
}
/** Reais with a scale word: R$ 1,2 bi / R$ 120 mi (pt), R$ 1.2bn / R$ 120m (en). */
function fmtBRL(x) {
  if (!Number.isFinite(x)) return "–";
  return Math.abs(x) >= 1e9 ? `R$ ${fmtNum(x / 1e9, 1)}${L(" bi", "bn")}` : `R$ ${fmtNum(x / 1e6, 0)}${L(" mi", "m")}`;
}
/** An ISO date at the start of a string, as the language writes it: "2026-11-13" -> "13/11/2026", "2012-05" -> "05/2012". English keeps ISO. */
function fmtDate(s) {
  if (s == null || s === "") return "–";
  if (LANG === "en") return String(s);
  return String(s).replace(/^(\d{4})-(\d{2})(?:-(\d{2}))?/, (_, y, m, d) => (d ? `${d}/${m}/${y}` : `${m}/${y}`));
}

// ------------------------------------------------------------ pages

/** Swap the static Portuguese for the English beside it (see the top of this file). */
function applyStatic(root = document) {
  document.documentElement.lang = LANGS[LANG].tag;
  if (LANG !== "en") return;
  for (const e of root.querySelectorAll("[data-en]")) e.textContent = e.dataset.en;
  for (const e of root.querySelectorAll("[data-en-html]")) e.innerHTML = e.dataset.enHtml;
  for (const a of ["placeholder", "title", "aria-label", "content"]) {
    const k = `en${a.split("-").map((w) => w[0].toUpperCase() + w.slice(1)).join("")}`;
    for (const e of root.querySelectorAll(`[data-en-${a}]`)) e.setAttribute(a, e.dataset[k]);
  }
}

/** The PT | EN switch for the header. */
function langSwitch() {
  const box = document.createElement("div");
  box.className = "lang";
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "Idioma / Language");
  for (const [k, v] of Object.entries(LANGS)) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = v.label; b.lang = v.tag; b.title = v.name;
    b.setAttribute("aria-pressed", String(k === LANG));
    b.addEventListener("click", () => setLang(k));
    box.append(b);
  }
  return box;
}

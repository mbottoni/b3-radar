// The page's language code (docs/assets/i18n.js) run as the browser runs it, with a fake location
// and localStorage: Portuguese by default, ?lang=en, the remembered choice, blocked storage, and the
// number and date formats of each language. Run by tests/test_site_i18n.py, or alone:
//   node tests/i18n_check.mjs
import { readFileSync } from "node:fs";
import vm from "node:vm";

const code = readFileSync(new URL("../docs/assets/i18n.js", import.meta.url), "utf8");
const KEY = "b3radar-lang";

function load({ search = "", stored = null, blocked = false } = {}) {
  const store = new Map(stored ? [[KEY, stored]] : []);
  const no = () => { throw new Error("storage blocked"); };
  const localStorage = blocked ? { getItem: no, setItem: no } : { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)) };
  const ctx = vm.createContext({ location: { search }, localStorage, URLSearchParams });
  vm.runInContext(`${code}\n;globalThis.api = { lang, L, fmtNum, fmtBRL, fmtDate };`, ctx);
  return { ...ctx.api, store };
}

let bad = 0;
const eq = (what, got, want) => { if (got !== want) { bad++; console.error(`${what}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); } };

// Which language
let p = load();
eq("default", p.lang(), "pt");
eq("L() in Portuguese", p.L("Nota", "Score"), "Nota");
p = load({ search: "?lang=en" });
eq("?lang=en", p.lang(), "en");
eq("L() in English", p.L("Nota", "Score"), "Score");
eq("?lang=en is remembered", p.store.get(KEY), "en");
eq("remembered choice", load({ stored: "en" }).lang(), "en");
p = load({ search: "?lang=pt", stored: "en" });
eq("the URL wins over the remembered choice", p.lang(), "pt");
eq("and replaces it", p.store.get(KEY), "pt");
eq("unknown ?lang=", load({ search: "?lang=fr" }).lang(), "pt");
eq("?lang=toString", load({ search: "?lang=toString" }).lang(), "pt");
eq("unknown remembered value", load({ stored: "xx" }).lang(), "pt");
eq("storage blocked, ?lang=en", load({ search: "?lang=en", blocked: true }).lang(), "en");
eq("storage blocked", load({ blocked: true }).lang(), "pt");

// Formats
p = load();
eq("pt number", p.fmtNum(1234.5, 1), "1.234,5");
eq("pt integer", p.fmtNum(1234), "1.234");
eq("pt negative", p.fmtNum(-0.25, 2), "-0,25");
eq("pt missing", p.fmtNum(NaN), "–");
eq("pt billions", p.fmtBRL(1.234e9), "R$ 1,2 bi");
eq("pt millions", p.fmtBRL(1.2e8), "R$ 120 mi");
eq("pt trillion in billions", p.fmtBRL(1234.5e9), "R$ 1.234,5 bi");
eq("pt day", p.fmtDate("2026-11-13"), "13/11/2026");
eq("pt month", p.fmtDate("2012-05"), "05/2012");
eq("pt date with a suffix", p.fmtDate("2026-11-13 (hoje)"), "13/11/2026 (hoje)");
eq("pt no date", p.fmtDate(""), "–");
p = load({ search: "?lang=en" });
eq("en number", p.fmtNum(1234.5, 1), "1,234.5");
eq("en billions", p.fmtBRL(1.234e9), "R$ 1.2bn");
eq("en millions", p.fmtBRL(1.2e8), "R$ 120m");
eq("en day", p.fmtDate("2026-11-13"), "2026-11-13");

if (bad) { console.error(`i18n: ${bad} failures`); process.exit(1); }
console.log("i18n: ok");

"""A separate screen for banks, insurers and their holdings.

The main screen leaves them out (``screen.FINANCIAL``): EBIT, enterprise
value and net debt mean nothing for a bank, whose debt is its raw material.
Here they are ranked among themselves only, on metrics that fit them:

- value: book / market (the parent's equity / market cap; price / book is
  its inverse, shown);
- quality: return on equity (the parent's trailing net income / its
  equity), and how steady that ROE was over three years;
- momentum and income: the main screen's own 12-1 return and 365-day
  dividend yield, unchanged.

Each metric is a percentile within the eligible financials, 25% per pillar.
P/E, earnings yield and payout are shown, not scored. The score is never
mixed with the main one: it is not in the main fingerprint, the weekly list
or the main backtest, and it has a fingerprint of its own (``rules_hash``).

Net income and equity come from ``cvm.financial_filings``, point in time by
the day CVM received each filing; market cap, momentum and dividend yield
from ``screen.compute``, which already covers every listed company.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest, cotahist, screen

WEIGHTS = {"value": 0.25, "quality": 0.25, "momentum": 0.25, "income": 0.25}
PILLARS = {               # metric percentiles averaged into each pillar
    "value": ("book_to_market",),
    "quality": ("roe", "roe_stability"),   # ROE stability: the spread of ROE, lower is better
    "momentum": ("momentum",),
    "income": ("dividend_yield",),
}
STABILITY_YEARS = 3       # ROE stability: TTM ROE at every statement of the last 3 years...
STABILITY_MIN = 4         # ...at least 4 of them
QUINTILE_MIN = 10         # eligible financials needed to split a date into fifths (2 a fifth)
CAP_JUMP = 10             # a market cap this far from B3's count carried back is a units or dating error: B3's is used
INCOME = ("net_income", "net_income_parent")
COLUMNS = ["asof", "rank", "ticker", "company", "group", "sector", "score", "value_score", "quality_score",
           "momentum_score", "income_score", "price", "market_cap", "liquidity", "pb", "book_to_market", "pe",
           "earnings_yield", "roe", "roe_stability", "roe_readings", "payout", "momentum", "dividend_yield",
           "net_income", "equity", "minority_share", "basis", "fundamentals_date", "filed", "shares_source", "tickers",
           "cnpj", "excluded", "p_book_to_market", "p_roe", "p_roe_stability", "p_momentum", "p_dividend_yield"]


def rules() -> dict:
    """What decides who is ranked and how, hashed into this screen's own fingerprint."""
    return {"universe": list(screen.FINANCIAL), "liquidity_min": screen.LIQUIDITY_MIN,
            "liquidity_window": screen.LIQUIDITY_WINDOW, "history_min": screen.HISTORY_MIN,
            "stale": screen.STALE_SESSIONS, "operating": screen.OPERATING,
            "momentum": [screen.MOMENTUM_LONG, screen.MOMENTUM_SKIP], "capital_returns": list(screen.CAPITAL_RETURNS),
            "weights": WEIGHTS, "pillars": {k: list(v) for k, v in PILLARS.items()},
            "stability": [STABILITY_YEARS, STABILITY_MIN],
            "metrics": "bm=equity_parent/mcap; roe=ni_parent_ttm/equity_parent; roe_stability=std of ttm roe at the "
                       "statements of 3y (>=4, lower better); mom=adj(t-21)/adj(t-252)-1; dy=cash 365d ex capital returns",
            "accounts": "ni=last top-level income line before 3.99, parent share; equity=top-level 'Patrimonio Liquido' "
                        "less non-controlling; ttm within one basis (con/ind)",
            "formula_version": 1}


def rules_hash() -> str:
    import hashlib
    return hashlib.sha1(json.dumps(rules(), sort_keys=True).encode()).hexdigest()[:8]


def is_financial(sector: pd.Series) -> pd.Series:
    """The main screen's own test (``screen._metrics``: "financial sector")."""
    return sector.fillna("").str.contains("|".join(screen.FINANCIAL))


def group(sector: str) -> str:
    """Banks, insurers (and insurance brokers), holdings, other: for reading the table, not for scoring."""
    s = sector or ""
    if "Bancos" in s:
        return "bank"
    if "Seguradoras" in s:
        return "insurance"
    return "holding" if s.startswith("Emp. Adm. Part") else "other"


def cnpjs(data_dir: Path) -> set | None:
    """Listed companies (with a trading code) in a financial sector: the
    ones whose accounts are extracted. None (every company) before the
    register and the trading codes exist."""
    comp = screen._load(data_dir, "companies.csv")
    tick = screen._load(data_dir, "tickers.csv")
    if comp.empty or tick.empty:
        return None
    return set(comp.cnpj[is_financial(comp.sector)]) & set(tick.cnpj)


SCALE_JUMP = 200         # equity this many times off the company's previous filings: filed in the wrong unit
MONEY = ("net_income", "net_income_parent", "net_income_prev", "net_income_parent_prev", "equity", "equity_parent")


def clean(fin: pd.DataFrame) -> pd.DataFrame:
    """Two errors in the filings, fixed looking only backwards (so still
    point in time):

    - **A filing in the wrong unit.** Pine's ITRs of June and September 2024
      say units but hold thousands (equity R$1.1 million, against R$1.07
      billion in March). A filing whose equity is over ``SCALE_JUMP`` times
      smaller (larger) than the median of the company's previous four in
      the same basis is multiplied (divided) by 1000.
    - **No prior-year figure.** Every bank's individual (Banco Central
      accounting) ITRs of 2025 give last year's year-to-date net income as
      0: CMN Resolution 4,966 took effect on 1 January 2025 without
      restating comparatives. A zero prior-year figure next to a non-zero
      current one is taken from the prior year's own report for that
      quarter; without one, the trailing twelve months cannot be computed
      in that basis."""
    fin = fin.sort_values(["cnpj", "basis", "dt_refer"], kind="stable").reset_index(drop=True)
    ref = fin.groupby(["cnpj", "basis"]).equity.transform(lambda s: s.shift(1).rolling(4, min_periods=1).median())
    r = fin.equity / ref.where(ref > 0)
    scale = np.where(r < 1 / SCALE_JUMP, 1000.0, np.where(r > SCALE_JUMP, 1 / 1000, 1.0))
    scale = np.where(fin.equity > 0, scale, 1.0)
    for c in MONEY:
        fin[c] = fin[c] * scale
    itr = fin.kind == "ITR"
    year_before = (pd.to_datetime(fin.dt_refer) - pd.DateOffset(years=1)).dt.strftime("%Y-%m-%d")
    prior = fin[itr].set_index(["cnpj", "basis", "dt_refer"])
    idx = pd.MultiIndex.from_arrays([fin.cnpj, fin.basis, year_before])
    missing = itr & (fin.net_income_prev == 0) & (fin.net_income != 0)
    for c in ("net_income", "net_income_parent"):
        own = prior[c].reindex(idx).to_numpy()
        fin[f"{c}_prev"] = fin[f"{c}_prev"].where(~missing, own)
    return fin


def load(data_dir: Path) -> pd.DataFrame:
    p = data_dir / "cvm" / "financials.csv"
    if not p.exists():
        return pd.DataFrame(columns=["cnpj", "kind", "dt_refer", "dt_receb", "basis", *MONEY])
    return clean(pd.read_csv(p, dtype={"cnpj": str, "cd_cvm": str, "kind": str, "dt_refer": str, "dt_receb": str,
                                       "basis": str}).fillna({"dt_receb": ""}))


# ------------------------------------------------------------ fundamentals

def _ttm_basis(g: pd.DataFrame) -> dict | None:
    """Same rule as ``screen.ttm``, within one basis: last annual, plus this
    year's year-to-date, minus the same period a year before; equity from
    the latest statement."""
    dfp = g[g.kind == "DFP"].sort_values("dt_refer").tail(1)
    itr = g[g.kind == "ITR"].sort_values("dt_refer").tail(1)
    last = pd.concat([dfp, itr]).sort_values("dt_refer", kind="stable").tail(1)
    if last.empty:
        return None
    out = {"dt_refer": last.dt_refer.iloc[0], "dt_receb": last.dt_receb.iloc[0],
           "equity_total": last.equity.iloc[0], "equity": last.equity_parent.iloc[0]}
    if not dfp.empty and not itr.empty and itr.dt_refer.iloc[0] > dfp.dt_refer.iloc[0]:
        gap = (pd.Timestamp(itr.dt_refer.iloc[0]) - pd.Timestamp(dfp.dt_refer.iloc[0])).days
        inc = {c: dfp[c].iloc[0] + itr[c].iloc[0] - itr[f"{c}_prev"].iloc[0] if gap < 366 else np.nan for c in INCOME}
    elif not dfp.empty:
        inc = {c: dfp[c].iloc[0] for c in INCOME}
    else:
        inc = {c: np.nan for c in INCOME}
    out["net_income_total"], out["net_income"] = inc["net_income"], inc["net_income_parent"]
    return out


def ttm(fin: pd.DataFrame, asof: str) -> pd.DataFrame:
    """Per company, from filings CVM had received by ``asof``: trailing net
    income and the latest equity, the parent's share (``net_income``,
    ``equity``) and in total. Consolidated and individual statements are
    never mixed: of the two, the basis with a computable TTM and equity,
    then the latest statement, then consolidated."""
    f = fin[(fin.dt_receb != "") & (fin.dt_receb <= asof)]
    rows = []
    for cnpj, g in f.groupby("cnpj", sort=True):
        best = None
        for basis in ("con", "ind"):
            r = _ttm_basis(g[g.basis == basis])
            if r is None:
                continue
            key = (bool(np.isfinite(r["net_income"]) and np.isfinite(r["equity"])), r["dt_refer"], basis == "con")
            if best is None or key > best[0]:
                best = (key, {**r, "basis": basis})
        if best:
            rows.append({"cnpj": cnpj, **best[1]})
    cols = ["cnpj", "dt_refer", "dt_receb", "equity_total", "equity", "net_income_total", "net_income", "basis"]
    return pd.DataFrame(rows, columns=cols).set_index("cnpj")


def ttm_history(fin: pd.DataFrame) -> pd.DataFrame:
    """TTM net income (the parent's), its equity and ROE at every statement
    of every company and basis, with the day it became public (``avail``:
    the later of the two filings a quarter's TTM uses)."""
    f = fin[fin.dt_receb != ""].assign(t=lambda d: pd.to_datetime(d.dt_refer))
    keep = ["cnpj", "basis", "t", "dt_receb", "equity_parent", *INCOME]
    dfp = f[f.kind == "DFP"][keep]
    itr = f[f.kind == "ITR"][keep + [f"{c}_prev" for c in INCOME]]
    ann = dfp.rename(columns={"dt_receb": "avail_a", **{c: f"{c}_a" for c in INCOME}}).drop(columns="equity_parent")
    if len(itr) and len(ann):
        m = pd.merge_asof(itr.sort_values("t", kind="stable"), ann.assign(t_a=ann.t).sort_values("t", kind="stable"),
                          on="t", by=["cnpj", "basis"], allow_exact_matches=False)
        m = m[(m.t - m.t_a).dt.days < 366].copy()
        for c in INCOME:
            m[c] = m[f"{c}_a"] + m[c] - m[f"{c}_prev"]
        m["dt_receb"] = np.maximum(m.dt_receb, m.avail_a)
    else:
        m = itr.iloc[0:0]
    out = pd.concat([dfp, m[keep]], ignore_index=True).rename(columns={"dt_receb": "avail"})
    out["roe"] = out.net_income_parent / out.equity_parent.where(out.equity_parent > 0)
    return out.sort_values(["cnpj", "basis", "t"], kind="stable").drop_duplicates(["cnpj", "basis", "t"]).reset_index(drop=True)


def stability(hist: pd.DataFrame, basis: pd.Series, asof: str) -> pd.DataFrame:
    """Per company: the standard deviation of TTM ROE across its statements
    public by ``asof`` from the ``STABILITY_YEARS`` before its latest one
    (in the basis ``ttm`` chose), with how many there were; under
    ``STABILITY_MIN`` readings it is not measured."""
    h = hist[(hist.avail <= asof) & hist.roe.notna()]
    h = h[h.basis.to_numpy() == h.cnpj.map(basis).to_numpy()]
    if h.empty:
        return pd.DataFrame(columns=["roe_stability", "roe_readings"], index=pd.Index([], name="cnpj"))
    last = h.groupby("cnpj").t.transform("max")
    w = h[h.t > last - pd.DateOffset(years=STABILITY_YEARS)]
    s = w.groupby("cnpj").roe.agg(["std", "size"])
    return pd.DataFrame({"roe_stability": s["std"].where(s["size"] >= STABILITY_MIN), "roe_readings": s["size"]})


# ------------------------------------------------------------------ screen

def compute(snap: pd.DataFrame, fin: pd.DataFrame, hist: pd.DataFrame, asof: str, pit: bool = False) -> pd.DataFrame:
    """The financials screen as of ``asof``, from the main screen's snapshot
    of that session (``screen.compute``: price, market cap, liquidity,
    momentum, dividend yield) and the financial statements."""
    cols = ["ticker", "company", "sector", "cnpj", "tickers", "price", "market_cap", "market_cap_b3", "liquidity",
            "sessions", "bdi", "situation", "issuer_status", "momentum", "dividend_yield", "shares_source"]
    df = snap[is_financial(snap.sector)][[c for c in cols if c in snap]].copy().reset_index(drop=True)
    df["asof"] = asof
    if "market_cap_b3" in df:
        # Itaú, Bradesco and Itaúsa file share counts in thousands (4,958,290 for 4.96 billion), above the
        # 2 million under which screen.outstanding reads thousands, and in the backtest B3's count settles
        # nothing once a later bonus issue exists: their market caps came out 1000 times too small. IRB's
        # 2022 annual report gives the count after its 30:1 reverse split of January 2023, which was then
        # applied again. Issuance and the bonus issues B3's events service misses (Bradesco) keep the two
        # counts within 3x; over CAP_JUMP times apart, B3's carried-back count is used.
        ratio = df.market_cap / df.market_cap_b3
        off = (ratio > CAP_JUMP) | (ratio < 1 / CAP_JUMP)
        df.loc[off, "market_cap"] = df.market_cap_b3[off]
        df.loc[off, "shares_source"] = "b3"
    df["group"] = df.sector.map(group)
    f = ttm(fin, asof)
    df = df.join(f.rename(columns={"dt_refer": "fundamentals_date", "dt_receb": "filed"}), on="cnpj")
    df = df.join(stability(hist, f.basis, asof), on="cnpj")
    pos = lambda s: s.where(s > 0)  # noqa: E731
    df["book_to_market"] = df.equity / df.market_cap
    df["pb"] = df.market_cap / pos(df.equity)
    df["pe"] = df.market_cap / pos(df.net_income)
    df["earnings_yield"] = df.net_income / df.market_cap
    df["roe"] = df.net_income / pos(df.equity)
    df["payout"] = df.dividend_yield * df.market_cap / pos(df.net_income)
    df["minority_share"] = 1 - df.equity / pos(df.equity_total)

    reason = pd.Series("", index=df.index)

    def flag(mask, why):
        reason[mask & (reason == "")] = why
    flag(df.bdi.fillna("02") != "02", "special trading segment (sanctioned or in recovery)")
    if not pit:   # today's status; unknown for past dates
        flag(df.situation.fillna("") != "ATIVO", "registration not active")
        flag(df.issuer_status.fillna("") != screen.OPERATING, "not operating normally")
    flag(df.liquidity < screen.LIQUIDITY_MIN, "illiquid")
    flag(df.sessions < screen.HISTORY_MIN, "under a year of quotes")
    flag(df.net_income.isna() | df.equity.isna() | df.market_cap.isna(), "no fundamentals")
    flag(df.equity <= 0, "negative equity")
    df["excluded"] = reason

    ok = reason == ""
    pct = lambda s, asc=True: s[ok].rank(pct=True, ascending=asc)  # noqa: E731
    metric_pct = {"book_to_market": pct(df.book_to_market), "roe": pct(df.roe),
                  "roe_stability": pct(df.roe_stability, asc=False), "momentum": pct(df.momentum),
                  "dividend_yield": pct(df.dividend_yield.fillna(0))}
    for m, v in metric_pct.items():
        df[f"p_{m}"] = (v * 100).reindex(df.index)
    for k, metrics in PILLARS.items():
        df[f"{k}_score"] = df[[f"p_{m}" for m in metrics]].mean(axis=1, skipna=True).where(ok)
    df["score"] = sum(df[f"{k}_score"].fillna(50) * w for k, w in WEIGHTS.items()).where(ok)
    df["rank"] = df.score.rank(ascending=False, method="first").astype("Int64")
    for c in COLUMNS:
        if c not in df:
            df[c] = np.nan
    return df.sort_values(["rank", "ticker"], na_position="last", kind="stable").reset_index(drop=True)


def build(snap: pd.DataFrame, data_dir: Path) -> pd.DataFrame:
    """Today's financials screen, from the main screen's snapshot (``screen.build``)."""
    fin = load(data_dir)
    return compute(snap, fin, ttm_history(fin), snap["asof"].iloc[0])


def save(df: pd.DataFrame, data_dir: Path) -> Path:
    path = data_dir / "screen" / "financials.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_csv(path, index=False, lineterminator="\n", float_format="%.6g")
    meta = {"asof": df["asof"].iloc[0], "rules": rules_hash(), "companies": int(len(df)),
            "eligible": int((df.excluded == "").sum())}
    (data_dir / "screen" / "financials.json").write_text(json.dumps(meta, indent=2) + "\n")
    return path


# ----------------------------------------------------------- company pages

HISTORY_FIELDS = ("score", "value_score", "quality_score", "momentum_score", "income_score", "rank", "pb", "pe", "roe",
                  "dividend_yield", "payout", "market_cap")


def company_fundamentals(hist: pd.DataFrame, cnpj: str, basis: str | None) -> dict:
    """TTM net income, equity and ROE (the parent's) at every statement of one
    company, in the basis today's screen uses (else consolidated, if any)."""
    h = hist[hist.cnpj == cnpj]
    if basis not in set(h.basis):
        basis = "con" if "con" in set(h.basis) else "ind"
    h = h[h.basis == basis].sort_values("t")
    r = lambda x, d=0: None if pd.isna(x) or not np.isfinite(x) else round(float(x), d)  # noqa: E731
    return {"basis": basis, "dates": list(h.t.dt.strftime("%Y-%m-%d")), "net_income": [r(x) for x in h.net_income_parent],
            "equity": [r(x) for x in h.equity_parent], "roe": [r(x, 4) for x in h.roe]}


# ---------------------------------------------------------------- backtest

FACTORS = {"score": "score", "value": "value_score", "quality": "quality_score", "momentum": "momentum_score",
           "income": "income_score"}


def run_backtest(data_dir: Path, first_year: int = backtest.FIRST_YEAR, log=print) -> dict:
    """Does the financials score separate winners from losers? Each May
    (``backtest.rebalance_dates``), the eligible financials as they stood
    that day, point in time, cut into fifths by the score and by each
    pillar (Q1 = best), each fifth held a year in equal weights with
    dividends reinvested; against all eligible financials, BOVA11 and the
    CDI. A date with under ``QUINTILE_MIN`` eligible names is skipped."""
    inp = screen.load_inputs(data_dir)
    fin = load(data_dir)
    hist = ttm_history(fin)
    sessions = np.sort(inp.px.date.unique())
    end = sessions[-1]
    dates = backtest.rebalance_dates(sessions, first_year)
    prices = backtest.Prices(inp.px, inp.cash, inp.stock)
    cdi = backtest.cdi_index(data_dir)
    nxt = {d: (dates[i + 1] if i + 1 < len(dates) else end) for i, d in enumerate(dates)}

    buckets, names, used, holdings = {}, {}, [], []
    for d in dates:
        snap = compute(screen.compute(inp, d, pit=True), fin, hist, d, pit=True)
        e = snap[snap.excluded == ""]
        names[d] = list(e.ticker)
        log(f"[financials] {d}: {len(e)} eligible financials")
        if len(e) < QUINTILE_MIN:
            continue
        used.append(d)
        for f, col in FACTORS.items():
            x = e[e[col].notna()]
            q = pd.qcut(x[col].rank(method="first", ascending=False), 5, labels=[1, 2, 3, 4, 5])
            for k in range(1, 6):
                buckets[(d, f, k)] = list(x.ticker[q == k])
        fifth = {t: k for (dd, f, k), ts in buckets.items() if dd == d and f == "score" for t in ts}
        for r in e.itertuples():
            holdings.append({"date": d, "rank": int(r.rank), "of": len(e), "quintile": fifth[r.ticker], "ticker": r.ticker,
                             "company": r.company, "group": r.group, "score": round(float(r.score), 2),
                             "period_return": prices.ret([r.ticker], d, nxt[d])})
    if not used:
        return {}
    years = (pd.Timestamp(end) - pd.Timestamp(used[0])).days / 365.25
    per, rows = [], []
    for d in used:
        for k, r in (("all", prices.ret(names[d], d, nxt[d])), ("bova11", prices.ret([cotahist.BENCHMARK], d, nxt[d])),
                     ("cdi", backtest._cdi_ret(cdi, d, nxt[d]))):
            per.append({"start": d, "end": nxt[d], "factor": k, "quintile": 0, "return": r,
                        "names": len(names[d]) if k == "all" else 1})
        for f in FACTORS:
            for k in range(1, 6):
                per.append({"start": d, "end": nxt[d], "factor": f, "quintile": k,
                            "return": prices.ret(buckets[(d, f, k)], d, nxt[d]), "names": len(buckets[(d, f, k)])})
    per = pd.DataFrame(per)
    ret = per.set_index(["factor", "quintile", "start"])["return"].sort_index()
    wins = {f: f"{int((ret.loc[(f, 1)] > ret.loc[(f, 5)]).sum())}/{len(used)}" for f in FACTORS}
    for (f, k), g in per.groupby(["factor", "quintile"], sort=False):
        v = float(np.prod(1 + g["return"].fillna(0.0)))
        rows.append({"factor": f, "quintile": k, "first": used[0], "total_return": v - 1, "cagr": v ** (1 / years) - 1,
                     "top_beat_bottom": wins.get(f, "")})
    quint = pd.DataFrame(rows)
    meta = {"first": used[0], "last": end, "rebalances": len(used), "skipped": [d for d in dates if d not in used],
            "rules": rules_hash(), "min_names": QUINTILE_MIN,
            "eligible": {d: len(names[d]) for d in dates}, "costs": "none"}
    return {"quintiles": quint, "periods": per, "holdings": pd.DataFrame(holdings), "meta": meta}


def save_backtest(res: dict, data_dir: Path) -> None:
    if not res:
        return
    out = data_dir / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("quintiles", "periods", "holdings"):
        res[name].to_csv(out / f"financials_{name}.csv", index=False, lineterminator="\n", float_format="%.6g")
    (out / "financials_meta.json").write_text(json.dumps(res["meta"], indent=2) + "\n")

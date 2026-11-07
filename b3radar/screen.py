"""The daily snapshot: point-in-time fundamentals + prices -> metrics -> scores.

Everything is computed "as of" a date using only what was public then:
statements count from the day CVM received them, prices up to that session.
METHODOLOGY.md documents every rule; the constants below are its numbers.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import cotahist, events

LIQUIDITY_MIN = 5e6          # R$ average daily traded volume, main ticker
LIQUIDITY_WINDOW = 63        # sessions (~3 months)
MOMENTUM_LONG, MOMENTUM_SKIP = 252, 21   # 12-month return, skipping the last month
HISTORY_MIN = 252            # sessions of quotes needed (excludes recent IPOs)
STALE_SESSIONS = 5           # a ticker must have traded in the last N sessions
FINANCIAL = ("Bancos", "Intermediação Financeira", "Seguradoras", "Arrendamento Mercantil",
             "Securitização", "Crédito Imobiliário")
OPERATING = "FASE OPERACIONAL"
CAPITAL_RETURNS = ("REST CAP DIN",)   # cash, but not a dividend: kept out of dividend yield
PN_KINDS = ("PN", "PNA", "PNB", "PNC", "PND", "PNE", "PNF", "PNG")
WEIGHTS = {"value": 0.25, "quality": 0.25, "momentum": 0.25, "income": 0.25}
PILLARS = {               # metric percentiles averaged into each pillar
    "value": ("earnings_yield", "book_to_market"),
    "quality": ("roic", "roe", "net_debt_ebit"),   # net debt / EBIT: lower is better
    "momentum": ("momentum",),
    "income": ("dividend_yield",),
}


def rules() -> dict:
    """Everything that decides who is eligible and how they rank. Its hash
    stamps every published list and backtest, so results made under
    different rules are never pooled (and cannot be rewritten later)."""
    return {"liquidity_min": LIQUIDITY_MIN, "liquidity_window": LIQUIDITY_WINDOW,
            "momentum": [MOMENTUM_LONG, MOMENTUM_SKIP], "history_min": HISTORY_MIN, "stale": STALE_SESSIONS,
            "financial": list(FINANCIAL), "operating": OPERATING, "capital_returns": list(CAPITAL_RETURNS),
            "weights": WEIGHTS, "pillars": {k: list(v) for k, v in PILLARS.items()},
            "metrics": "ey=ebit/ev; bm=equity/mcap; roe=ni/equity; roic=ebit/(equity+net_debt); "
                       "lev=net_debt/ebit (ebit<=0 worst); mom=adj(t-21)/adj(t-252)-1; dy=cash 365d ex capital returns",
            "formula_version": 1}


def rules_hash() -> str:
    import hashlib
    import json
    return hashlib.sha1(json.dumps(rules(), sort_keys=True).encode()).hexdigest()[:8]

S = {"dtype": {"cnpj": str, "cd_cvm": str, "ticker": str, "dt_refer": str, "dt_receb": str, "kind": str}}


# ------------------------------------------------------------ fundamentals

def ttm(filings: pd.DataFrame, asof: str) -> pd.DataFrame:
    """Trailing-twelve-month income and latest balance sheet per company,
    from filings CVM had received on or before ``asof``."""
    f = filings[(filings.dt_receb <= asof) & (filings.dt_receb != "")]
    income = ["revenue", "gross_profit", "ebit", "net_income"]
    balance = ["total_assets", "cash", "short_investments", "st_debt", "lt_debt", "equity",
               "shares_on", "shares_pn", "treasury_on", "treasury_pn"]
    rows = []
    for cnpj, g in f.groupby("cnpj", sort=True):
        dfp = g[g.kind == "DFP"].sort_values("dt_refer").tail(1)
        itr = g[g.kind == "ITR"].sort_values("dt_refer").tail(1)
        last = pd.concat([dfp, itr]).sort_values("dt_refer").tail(1)
        if last.empty:
            continue
        out = {"cnpj": cnpj, "dt_refer": last.dt_refer.iloc[0], "dt_receb": last.dt_receb.iloc[0]}
        out.update({c: last[c].iloc[0] for c in balance})
        if not dfp.empty and not itr.empty and itr.dt_refer.iloc[0] > dfp.dt_refer.iloc[0]:
            gap = (pd.Timestamp(itr.dt_refer.iloc[0]) - pd.Timestamp(dfp.dt_refer.iloc[0])).days
            if gap < 366:   # ITR in the fiscal year right after the DFP: annual + YTD - prior YTD
                out.update({c: dfp[c].iloc[0] + itr[c].iloc[0] - itr[f"{c}_prev"].iloc[0] for c in income})
            else:
                out.update({c: np.nan for c in income})
        elif not dfp.empty:
            out.update({c: dfp[c].iloc[0] for c in income})
        else:
            out.update({c: np.nan for c in income})
        rows.append(out)
    return pd.DataFrame(rows)


def outstanding(total: float, treasury: float, b3_total: float | None = None,
                tol: tuple[float, float] = (0.8, 1.25)) -> tuple[float, str]:
    """Shares outstanding for one class, and where the number came from.

    ``total``/``treasury`` are CVM's raw capital-composition counts, already
    carried through any splits since the filing. That file has no unit
    column: many companies file thousands, PETR files units, and some rows
    mix the two (Tenda 2026-06-30: total in thousands, treasury in units).
    B3's current count per class settles it:

    - CVM within ``tol`` (0.8-1.25x) of B3: CVM, in units;
    - B3 within 1000 x ``tol`` of CVM: CVM, in thousands;
    - anything else (LAVV filed an extra digit; OPCT issued shares since its
      filing): B3's count.

    Without a B3 count, under 2 million shares is read as thousands (no
    listed company is that small). A treasury over 25% of the total is read
    as a units mix-up and ignored.
    """
    if not np.isfinite(total) or total <= 0:
        return (b3_total, "b3") if b3_total else (np.nan, "")
    source = "cvm"
    if b3_total:
        r = b3_total / total
        if tol[0] <= r <= tol[1]:
            scale = 1.0
        elif 1000 * tol[0] <= r <= 1000 * tol[1]:
            scale = 1000.0
        else:
            return b3_total, "b3"
    else:
        scale = 1000.0 if total < 2e6 else 1.0
    tot = total * scale
    tr = treasury * scale if np.isfinite(treasury) and treasury > 0 else 0.0
    return tot - (tr if tr <= 0.25 * tot else 0.0), source


# ----------------------------------------------------------------- mapping

def ticker_map(prices: pd.DataFrame, tickers: pd.DataFrame, companies: pd.DataFrame, issuers: pd.DataFrame) -> dict:
    """ticker -> cnpj, via the FCA trading codes, then the issuer prefix,
    then B3's issuer -> CVM code."""
    out = dict(zip(tickers.ticker, tickers.cnpj))
    by_prefix = {}
    for t, c in out.items():
        by_prefix.setdefault(t[:4], set()).add(c)
    cvm_to_cnpj = dict(zip(companies.cd_cvm, companies.cnpj))
    issuer_cvm = dict(zip(issuers.issuer, issuers.cd_cvm)) if len(issuers) else {}
    for t in prices.ticker.unique():
        if t in out:
            continue
        cands = by_prefix.get(t[:4], set())
        if len(cands) == 1:
            out[t] = next(iter(cands))
        elif issuer_cvm.get(t[:4]) in cvm_to_cnpj:
            out[t] = cvm_to_cnpj[issuer_cvm[t[:4]]]
    return out


# -------------------------------------------------------------------- build

def _load(data_dir: Path, name: str) -> pd.DataFrame:
    p = data_dir / "cvm" / name
    return pd.read_csv(p, keep_default_na=False, **S) if p.exists() else pd.DataFrame()


@dataclass
class Inputs:
    """Everything the screen reads, loaded once (the backtest reuses it for
    every rebalance date)."""
    px: pd.DataFrame
    filings: pd.DataFrame
    capital: pd.DataFrame
    companies: pd.DataFrame
    tmap: dict
    cash: pd.DataFrame
    stock: pd.DataFrame
    b3_shares: dict
    isins: dict          # ticker -> every ISIN it has traded under


def load_inputs(data_dir: Path, since: str | None = None) -> Inputs:
    px = cotahist.load(data_dir, since=since)
    companies = _load(data_dir, "companies.csv")
    filings = pd.read_csv(data_dir / "cvm" / "filings.csv", **S).fillna({"dt_receb": ""})
    cap_path = data_dir / "cvm" / "capital.csv"
    capital = pd.read_csv(cap_path, dtype={"cnpj": str, "date": str, "form": str}) if cap_path.exists() \
        else pd.DataFrame(columns=["cnpj", "date", "shares_on", "shares_pn"])
    issuers_path = data_dir / "events" / "issuers.csv"
    issuers = pd.read_csv(issuers_path, dtype=str, keep_default_na=False) if issuers_path.exists() else pd.DataFrame()
    cash, stock = events.load(data_dir)
    b3_shares = {r.issuer: (float(r.shares_on or "nan"), float(r.shares_pn or "nan"))
                 for r in issuers.itertuples()} if len(issuers) else {}
    isins = {t: set(g) for t, g in px.groupby("ticker")["isin"]}
    return Inputs(px, filings, capital, companies, ticker_map(px, _load(data_dir, "tickers.csv"), companies, issuers),
                  cash, stock, b3_shares, isins)


def _shares_filed(f, capital: pd.DataFrame, cnpj: str, asof: str):
    """(on, pn, treasury_on, treasury_pn, as-of date) of the latest share
    count public by ``asof``: the filing's own (DFP/ITR, 2020 on), else the
    FRE capital timeline (2010-2019)."""
    if np.isfinite(f.shares_on) or np.isfinite(f.shares_pn):
        return f.shares_on, f.shares_pn, f.treasury_on, f.treasury_pn, f.dt_refer
    c = capital[(capital.cnpj == cnpj) & (capital.date <= asof)]
    if c.empty:
        return np.nan, np.nan, np.nan, np.nan, ""
    last = c.sort_values("date").iloc[-1]
    return last.shares_on, last.shares_pn, np.nan, np.nan, last.date


def compute(inp: Inputs, asof: str, pit: bool = False) -> pd.DataFrame:
    """The screen as of a session. ``pit`` (the backtest): skip filters only
    known today (registration and issuer status) and resolve historical share
    counts against B3's current count carried back through later splits,
    with a wider band since issuance and buybacks since then are unknown."""
    since = (dt.date.fromisoformat(asof) - dt.timedelta(days=420)).isoformat()
    px = inp.px[(inp.px.date >= since) & (inp.px.date <= asof)]
    sessions = np.sort(px.date.unique())
    recent = set(sessions[-STALE_SESSIONS:])
    window = set(sessions[-LIQUIDITY_WINDOW:])

    stocks = px[px.kind != "ETF"]
    last = stocks.sort_values("date").groupby("ticker").tail(1).set_index("ticker")
    liq = stocks[stocks.date.isin(window)].groupby("ticker").volume.sum() / LIQUIDITY_WINDOW
    hist = stocks.groupby("ticker").date.nunique()
    tk = pd.DataFrame({"close": last.close, "date": last.date, "isin": last["isin"], "kind": last.kind,
                       "bdi": last.bdi.fillna("02"), "liquidity": liq, "sessions": hist}).fillna({"liquidity": 0.0})
    tk = tk[tk.date.isin(recent)]
    tk["cnpj"] = tk.index.map(inp.tmap)
    tk = tk[tk.cnpj.notna()]

    stock = inp.stock
    isins = inp.isins
    fund = ttm(inp.filings, asof).set_index("cnpj")
    comp = inp.companies.set_index("cnpj")
    tol = (0.6, 1.6) if pit else (0.8, 1.25)

    def mult(isins, after: str, before: str) -> float:
        m = stock[stock["isin"].isin(isins) & (stock.last_date_prior >= after) & (stock.last_date_prior < before)]
        return float(np.prod(m.drop_duplicates(["label", "last_date_prior"]).mult))

    rows = []
    for cnpj, g in tk.groupby("cnpj"):
        g = g.sort_values(["liquidity", "kind"], ascending=[False, True], kind="stable")   # ties: ON before PN
        main = g.index[0]
        on = g[g.kind == "ON"]
        pn = g[g.kind.isin(PN_KINDS)]
        on_px = on.close.iloc[0] if len(on) else np.nan
        pn_px = pn.close.iloc[0] if len(pn) else np.nan
        on_px, pn_px = (pn_px if np.isnan(on_px) else on_px), (on_px if np.isnan(pn_px) else pn_px)
        info = comp.loc[cnpj] if cnpj in comp.index else None
        r = {"ticker": main, "cnpj": cnpj, "tickers": " ".join(g.index),
             "company": info["name"] if info is not None else "", "sector": info["sector"] if info is not None else "",
             "situation": info["situation"] if info is not None else "",
             "issuer_status": info["issuer_status"] if info is not None else "",
             "price": g.close.iloc[0], "liquidity": g.liquidity.iloc[0], "sessions": g.sessions.iloc[0],
             "isin": g["isin"].iloc[0], "bdi": g.bdi.iloc[0]}
        if cnpj in fund.index:
            f = fund.loc[cnpj]
            s_on, s_pn, t_on, t_pn, when = _shares_filed(f, inp.capital, cnpj, asof)
            # Filed counts carried through any split / reverse split / bonus
            # since they were filed; B3's current count carried back through
            # any since ``asof``: both are then counts at ``asof`` (ORVR: a
            # 1:4 split after its June filing; history: decades of splits).
            on_isins = set().union(*(isins.get(t, set()) for t in on.index)) if len(on) else set()
            pn_isins = set().union(*(isins.get(t, set()) for t in pn.index)) if len(pn) else set()
            m_on = mult(on_isins, when, asof) if len(on) and when else 1.0
            m_pn = mult(pn_isins, when, asof) if len(pn) and when else 1.0
            b3_on, b3_pn = inp.b3_shares.get(main[:4], (np.nan, np.nan))
            ref_on = b3_on / mult(on_isins, asof, "9999") if b3_on > 0 and len(on) else (b3_on if b3_on > 0 else None)
            ref_pn = b3_pn / mult(pn_isins, asof, "9999") if b3_pn > 0 and len(pn) else (b3_pn if b3_pn > 0 else None)
            sh_on, src_on = outstanding(s_on * m_on, t_on * m_on, ref_on, tol)
            sh_pn, src_pn = outstanding(s_pn * m_pn, t_pn * m_pn, ref_pn, tol)
            r["shares_source"] = "/".join(x for x in (src_on, src_pn) if x)
            mcap = np.nansum([sh_on * on_px if sh_on > 0 else np.nan, sh_pn * pn_px if sh_pn > 0 else np.nan])
            debt = np.nansum([f.st_debt, f.lt_debt])
            liquid = np.nansum([f.cash, f.short_investments])
            r.update({"fundamentals_date": f.dt_refer, "filed": f.dt_receb, "revenue": f.revenue, "ebit": f.ebit,
                      "net_income": f.net_income, "equity": f.equity, "net_debt": debt - liquid,
                      "market_cap": mcap if mcap > 0 else np.nan})
        rows.append(r)
    df = pd.DataFrame(rows)
    df["asof"] = asof
    return _metrics(df, px, inp.cash, stock, asof, pit, isins)


def build(data_dir: Path, asof: str | None = None) -> pd.DataFrame:
    asof = asof or cotahist.last_date(data_dir)
    since = (dt.date.fromisoformat(asof) - dt.timedelta(days=430)).isoformat()
    return compute(load_inputs(data_dir, since=since), asof)


def _momentum_and_yield(df, px, cash, stock, asof, isins):
    mom, dy = [], []
    by = {t: g for t, g in px.groupby("ticker")}
    for t, isin, price in zip(df.ticker, df["isin"], df.price):
        g = by.get(t)
        all_isins = isins.get(t) or {isin}
        adj = events.adjusted_close(g[["date", "close"]], all_isins, cash, stock) if g is not None else pd.Series(dtype=float)
        mom.append(adj.iloc[-1 - MOMENTUM_SKIP] / adj.iloc[-1 - MOMENTUM_LONG] - 1
                   if len(adj) > MOMENTUM_LONG and adj.iloc[-1 - MOMENTUM_LONG] > 0 else np.nan)
        start = (dt.date.fromisoformat(asof) - dt.timedelta(days=365)).isoformat()
        c = cash[(cash["isin"].isin(all_isins)) & (cash.last_date_prior >= start) & (cash.last_date_prior < asof)
                 & ~cash.label.isin(CAPITAL_RETURNS)].drop_duplicates(["label", "last_date_prior", "rate"])
        s = stock[stock["isin"].isin(all_isins)].drop_duplicates(["label", "last_date_prior"])
        total = 0.0
        for e in c.itertuples():
            later = s[(s.last_date_prior >= e.last_date_prior) & (s.last_date_prior < asof)].drop_duplicates(
                ["label", "last_date_prior"])
            total += e.rate / float(np.prod(later.mult))   # per share as the stock trades today
        dy.append(total / price if price > 0 else np.nan)
    return mom, dy


def _metrics(df: pd.DataFrame, px, cash, stock, asof, pit: bool = False, isins: dict | None = None) -> pd.DataFrame:
    for c in ("market_cap", "ebit", "net_income", "revenue", "equity", "net_debt"):
        if c not in df:
            df[c] = np.nan
    df["ev"] = df.market_cap + df.net_debt
    pos = lambda s: s.where(s > 0)  # noqa: E731
    df["earnings_yield"] = df.ebit / pos(df.ev)
    df["ev_ebit"] = pos(df.ev) / pos(df.ebit)
    df["pe"] = df.market_cap / pos(df.net_income)
    df["book_to_market"] = df.equity / df.market_cap
    df["roe"] = df.net_income / pos(df.equity)
    df["roic"] = df.ebit / pos(df.equity + df.net_debt)
    df["net_debt_ebit"] = df.net_debt / pos(df.ebit)
    df["net_margin"] = df.net_income / pos(df.revenue)
    df["momentum"], df["dividend_yield"] = _momentum_and_yield(df, px, cash, stock, asof, isins or {})

    reason = pd.Series("", index=df.index)
    def flag(mask, why):
        reason[mask & (reason == "")] = why
    flag(df.sector.fillna("").str.contains("|".join(FINANCIAL)), "financial sector")
    flag(df.bdi.fillna("02") != "02", "special trading segment (sanctioned or in recovery)")
    if not pit:   # today's status; unknown for past dates
        flag(df.situation.fillna("") != "ATIVO", "registration not active")
        flag(df.issuer_status.fillna("") != OPERATING, "not operating normally")
    flag(df.liquidity < LIQUIDITY_MIN, "illiquid")
    flag(df.sessions < HISTORY_MIN, "under a year of quotes")
    flag(df.ebit.isna() | df.market_cap.isna(), "no fundamentals")
    flag(df.equity <= 0, "negative equity")
    flag(df.ev <= 0, "non-positive EV")
    df["excluded"] = reason

    ok = reason == ""
    pct = lambda s, asc=True: s[ok].rank(pct=True, ascending=asc)  # noqa: E731
    lev = df.net_debt_ebit.where(df.ebit > 0, np.inf)
    # Each metric's percentile is kept ("p_*" columns) so the page can show
    # why a company scores what it does, not only the pillar averages.
    metric_pct = {
        "earnings_yield": pct(df.earnings_yield), "book_to_market": pct(df.book_to_market),
        "roic": pct(df.roic), "roe": pct(df.roe), "net_debt_ebit": pct(lev, asc=False),
        "momentum": pct(df.momentum), "dividend_yield": pct(df.dividend_yield.fillna(0)),
    }
    for m, v in metric_pct.items():
        df[f"p_{m}"] = (v * 100).reindex(df.index)
    for k, metrics in PILLARS.items():
        df[f"{k}_score"] = df[[f"p_{m}" for m in metrics]].mean(axis=1, skipna=True).where(ok)
    df["score"] = sum(df[f"{k}_score"].fillna(50) * w for k, w in WEIGHTS.items()).where(ok)
    df["rank"] = df.score.rank(ascending=False, method="first").astype("Int64")
    mf = ok & (df.ebit > 0)
    df["magic_rank"] = (df.earnings_yield[mf].rank(ascending=False) + df.roic[mf].rank(ascending=False)) \
        .rank(method="first").astype("Int64").reindex(df.index)
    return df.sort_values(["rank", "ticker"], na_position="last").reset_index(drop=True)


COLUMNS = ["asof", "rank", "ticker", "company", "sector", "score", "value_score", "quality_score", "momentum_score",
           "income_score", "magic_rank", "price", "market_cap", "ev", "liquidity", "pe", "ev_ebit", "earnings_yield",
           "book_to_market", "roe", "roic", "net_debt_ebit", "net_margin", "momentum", "dividend_yield",
           "fundamentals_date", "filed", "shares_source", "tickers", "cnpj", "excluded",
           "p_earnings_yield", "p_book_to_market", "p_roic", "p_roe", "p_net_debt_ebit", "p_momentum",
           "p_dividend_yield"]


def save(df: pd.DataFrame, data_dir: Path) -> Path:
    path = data_dir / "screen" / "latest.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_csv(path, index=False, lineterminator="\n", float_format="%.6g")
    return path

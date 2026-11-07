"""One JSON per company for its page: long history a buy-and-hold investor
reads before owning a stock for years.

- total-return price (dividends reinvested) since 2010, monthly, with BOVA11;
- the screen as it stood each quarter since 2011 (point in time): score,
  pillars, rank, valuation (P/E, EV/EBIT, dividend yield), ROE, ROIC;
- trailing-twelve-month revenue, EBIT and net income at every filing;
- dividends per share by year (per share as the stock trades today);
- the years it made the backtest's top 10, and how that year went.

Written to data/companies/<TICKER>.json by ``python -m b3radar companies``
(monthly, with the backtest). Quarterly snapshots are taken on the first
session of April, June, September and December, after the annual report
and each quarterly report are due.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest, cotahist, events, screen

SNAPSHOT_MONTHS = (4, 6, 9, 12)
FIRST_YEAR = 2011
HISTORY_FIELDS = ("score", "value_score", "quality_score", "momentum_score", "income_score", "rank", "pe", "ev_ebit",
                  "dividend_yield", "roe", "roic", "net_margin", "market_cap")


def _r(x, digits=4):
    """Rounded float, or None for any kind of missing (NaN, pd.NA, inf)."""
    if x is None or pd.isna(x):
        return None
    x = float(x)
    return round(x, digits) if np.isfinite(x) else None


def snapshot_dates(sessions: np.ndarray, first_year: int = FIRST_YEAR) -> list[str]:
    out = []
    for y in range(first_year, int(sessions[-1][:4]) + 1):
        for m in SNAPSHOT_MONTHS:
            later = sessions[sessions >= f"{y}-{m:02d}-01"]
            if len(later):
                out.append(later[0])
    return sorted(set(out))


def ttm_series(filings: pd.DataFrame) -> pd.DataFrame:
    """TTM income at every filing of one company (same rule as the screen:
    annual + this year's YTD - last year's YTD), with the balance sheet."""
    f = filings.sort_values(["dt_refer", "kind"])
    dfps = f[f.kind == "DFP"].set_index("dt_refer")
    rows = []
    for r in f.itertuples():
        out = {"dt_refer": r.dt_refer, "equity": r.equity,
               "net_debt": np.nansum([r.st_debt, r.lt_debt]) - np.nansum([r.cash, r.short_investments])}
        if r.kind == "DFP":
            out.update({c: getattr(r, c) for c in ("revenue", "ebit", "net_income")})
        else:
            prior = dfps[(dfps.index < r.dt_refer)]
            if len(prior) and (pd.Timestamp(r.dt_refer) - pd.Timestamp(prior.index[-1])).days < 366:
                d = prior.iloc[-1]
                out.update({c: d[c] + getattr(r, c) - getattr(r, f"{c}_prev") for c in ("revenue", "ebit", "net_income")})
            else:
                continue
        rows.append(out)
    return pd.DataFrame(rows).drop_duplicates("dt_refer", keep="last") if rows else pd.DataFrame()


def build(data_dir: Path, log=print) -> int:
    inp = screen.load_inputs(data_dir)
    latest = pd.read_csv(data_dir / "screen" / "latest.csv", dtype={"ticker": str, "cnpj": str}, keep_default_na=False)
    sessions = np.sort(inp.px.date.unique())
    dates = snapshot_dates(sessions)
    snaps = []
    for d in dates:
        s = screen.compute(inp, d, pit=True)
        s["eligible"] = s.excluded.fillna("") == ""
        snaps.append(s[["cnpj", "ticker", "eligible", *HISTORY_FIELDS]].assign(date=d))
        log(f"[companies] snapshot {d}: {int(s.eligible.sum())} eligible")
    hist = pd.concat(snaps, ignore_index=True)

    prices = backtest.Prices(inp.px, inp.cash, inp.stock)
    month_ends = sorted(set(pd.Series(sessions).groupby(pd.Series(sessions).str[:7]).max()))
    bova = prices.series(cotahist.BENCHMARK)
    bova_m = [_r(prices.at(cotahist.BENCHMARK, d), 3) for d in month_ends]
    bt_path = data_dir / "backtest" / "holdings.csv"
    bt = pd.read_csv(bt_path, dtype={"ticker": str}) if bt_path.exists() else pd.DataFrame(columns=["ticker"])
    bt = bt[bt.strategy == "composite"] if len(bt) else bt

    out_dir = data_dir / "companies"
    out_dir.mkdir(parents=True, exist_ok=True)
    keep = set()
    for r in latest.itertuples():
        t, cnpj = r.ticker, r.cnpj
        h = hist[hist.cnpj == cnpj].sort_values("date")
        adj = prices.series(t)
        first = adj.index[0] if len(adj) else None
        months = [d for d in month_ends if first and d >= first]
        f = inp.filings[inp.filings.cnpj == cnpj]
        fund = ttm_series(f) if len(f) else pd.DataFrame()
        isins = inp.isins.get(t, {r.isin} if hasattr(r, "isin") else set())
        cash = inp.cash[inp.cash["isin"].isin(isins) & ~inp.cash.label.isin(screen.CAPITAL_RETURNS)] \
            .drop_duplicates(["label", "last_date_prior", "rate"])
        stock = inp.stock[inp.stock["isin"].isin(isins)].drop_duplicates(["label", "last_date_prior"])
        per_year = {}
        for e in cash.itertuples():
            later = stock[stock.last_date_prior >= e.last_date_prior]
            per_year[e.last_date_prior[:4]] = per_year.get(e.last_date_prior[:4], 0.0) + e.rate / float(np.prod(later.mult))
        doc = {
            "ticker": t, "company": r.company, "sector": r.sector, "tickers": r.tickers, "cnpj": cnpj,
            "now": {k: getattr(r, k) for k in latest.columns if k not in ("cnpj",)},
            "price": {"dates": months, "adj": [_r(prices.at(t, d), 4) for d in months],
                      "bova": [b for d, b in zip(month_ends, bova_m) if d in set(months)]},
            "history": {"dates": list(h.date), "eligible": [bool(x) for x in h.eligible],
                        **{k: [_r(x) for x in h[k]] for k in HISTORY_FIELDS}},
            "fundamentals": {"dates": list(fund.dt_refer) if len(fund) else [],
                             **{k: [_r(x, 0) for x in fund[k]] if len(fund) else [] for k in
                                ("revenue", "ebit", "net_income", "equity", "net_debt")}},
            "dividends": {"years": sorted(per_year), "per_share": [_r(per_year[y], 4) for y in sorted(per_year)]},
            "backtest": [{"date": b.date, "rank": int(b.rank), "return": _r(b.period_return)}
                         for b in bt[bt.ticker == t].itertuples()] if len(bt) else [],
        }
        name = f"{t}.json"
        (out_dir / name).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
        keep.add(name)
    for old in out_dir.glob("*.json"):
        if old.name not in keep:
            old.unlink()
    return len(keep)

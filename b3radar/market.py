"""Is the market cheap? The whole eligible universe against cash.

At the end of every month since 2011, the screen as it stood that day
(point in time, the same code as the backtest) is summed up:

- **earnings yield of the typical stock**: the median EBIT / EV of the
  eligible companies, the screen's own value metric;
- aggregate P/E and dividend yield (market-cap weighted: what the big
  companies say), and the median dividend yield;
- the **CDI** (what cash pays, annualized from the day's rate) and the CDI
  after the last twelve months of inflation (IPCA): earnings grow with
  prices, so a stock's earnings yield is closer to a real return than to a
  nominal one;
- what came next: the eligible universe bought in equal weights and held
  three years, against the CDI over the same three years.

Written to data/market/history.csv by ``python -m b3radar market``
(monthly, with the backtest). Today's figures, from the daily screen, go
to data/market/today.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest, screen

FIRST_MONTH = "2011-05"     # the 2010 annual reports are public and a year of quotes exists
FORWARD_YEARS = 3
IPCA_LAG_DAYS = 15          # IPCA for a month is published around the 10th of the next


def cdi_annual(cdi: pd.DataFrame, asof: str) -> float:
    """The CDI rate in force on ``asof``, annualized over 252 sessions."""
    r = cdi[cdi.date <= asof]
    return float((1 + r.rate.iloc[-1] / 100) ** 252 - 1) if len(r) else np.nan


def ipca_12m(ipca: pd.DataFrame, asof: str) -> float:
    """Inflation over the last twelve months published by ``asof``."""
    cut = (pd.Timestamp(asof) - pd.Timedelta(days=IPCA_LAG_DAYS)).to_period("M") - 1
    known = ipca[pd.to_datetime(ipca.date).dt.to_period("M") <= cut].tail(12)
    return float(np.prod(1 + known.rate / 100) - 1) if len(known) == 12 else np.nan


def snapshot(df: pd.DataFrame, asof: str, cdi: pd.DataFrame, ipca: pd.DataFrame) -> dict:
    e = df[df.excluded.fillna("") == ""]
    mcap = e.market_cap.sum()
    c, i = cdi_annual(cdi, asof), ipca_12m(ipca, asof)
    ni = e.net_income.sum()
    return {
        "date": asof, "eligible": int(len(e)),
        "earnings_yield": float(e.earnings_yield.median()) if len(e) else np.nan,
        "earnings_yield_agg": float(e.ebit.sum() / e.ev.sum()) if len(e) else np.nan,
        "pe_agg": float(mcap / ni) if ni > 0 else np.nan,
        "dividend_yield": float(e.dividend_yield.fillna(0).median()) if len(e) else np.nan,
        "dividend_yield_agg": float((e.dividend_yield.fillna(0) * e.market_cap).sum() / mcap) if mcap > 0 else np.nan,
        "cdi": c, "ipca_12m": i, "real_cdi": (1 + c) / (1 + i) - 1,
    }


def _macro(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    def read(name):
        p = data_dir / "macro" / name
        return pd.read_csv(p, dtype={"date": str}) if p.exists() else pd.DataFrame(columns=["date", "rate"])
    return read("cdi.csv"), read("ipca.csv")


def month_ends(sessions: np.ndarray, first: str = FIRST_MONTH) -> list[str]:
    s = pd.Series(sessions)
    ends = s.groupby(s.str[:7]).max()
    return [d for m, d in ends.items() if m >= first and d != sessions[-1]]   # the current month is not over


def build(data_dir: Path, log=print) -> pd.DataFrame:
    inp = screen.load_inputs(data_dir)
    sessions = np.sort(inp.px.date.unique())
    cdi, ipca = _macro(data_dir)
    cdi_idx = backtest.cdi_index(data_dir)
    prices = backtest.Prices(inp.px, inp.cash, inp.stock)
    rows = []
    for d in month_ends(sessions):
        s = screen.compute(inp, d, pit=True)
        row = snapshot(s, d, cdi, ipca)
        # What came next: the universe held FORWARD_YEARS, against cash.
        target = (pd.Timestamp(d) + pd.DateOffset(years=FORWARD_YEARS)).strftime("%Y-%m-%d")
        later = sessions[sessions >= target]
        if len(later):
            names = list(s.ticker[s.excluded.fillna("") == ""])
            stocks, cash = prices.ret(names, d, later[0]), backtest._cdi_ret(cdi_idx, d, later[0])
            span = (pd.Timestamp(later[0]) - pd.Timestamp(d)).days / 365.25
            row["fwd_stocks"] = (1 + stocks) ** (1 / span) - 1
            row["fwd_cdi"] = (1 + cash) ** (1 / span) - 1
        rows.append(row)
        log(f"[market] {d}: {row['eligible']} eligible, earnings yield {row['earnings_yield']:.1%}, CDI {row['cdi']:.1%}")
    return pd.DataFrame(rows)


def save(hist: pd.DataFrame, data_dir: Path) -> Path:
    path = data_dir / "market" / "history.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["date", "eligible", "earnings_yield", "earnings_yield_agg", "pe_agg", "dividend_yield", "dividend_yield_agg",
            "cdi", "ipca_12m", "real_cdi", "fwd_stocks", "fwd_cdi"]
    hist.reindex(columns=cols).to_csv(path, index=False, lineterminator="\n", float_format="%.6g")
    return path


def today(df: pd.DataFrame, data_dir: Path) -> dict:
    """Today's figures from the daily screen, with where today's earnings
    yield stands in the monthly history (share of months it beats)."""
    cdi, ipca = _macro(data_dir)
    asof = df["asof"].iloc[0]
    out = snapshot(df, asof, cdi, ipca)
    hp = data_dir / "market" / "history.csv"
    if hp.exists():
        h = pd.read_csv(hp, dtype={"date": str})
        ey = h.earnings_yield.dropna()
        out["cheaper_than"] = float((ey < out["earnings_yield"]).mean()) if len(ey) else np.nan
        out["history_from"] = h.date.iloc[0] if len(h) else ""
        out["history_median"] = float(ey.median()) if len(ey) else np.nan
    clean = {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in out.items()}
    path = data_dir / "market" / "today.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2) + "\n")
    return clean

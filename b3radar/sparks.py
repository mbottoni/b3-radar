"""Small price series for the page: every screened ticker's last year of
total-return prices (weekly, for the sparklines in the tables) and
BOVA11's last year (daily, for the snapshot card), each with its 1-day,
1-month and 1-year returns.

Written to data/screen/sparks.json with every screen rebuild.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest, cotahist, events

YEAR, MONTH, WEEK = 252, 21, 5


def _r(x, digits=4):
    return round(float(x), digits) if x is not None and np.isfinite(x) else None


def _sig(x):
    """Four significant digits: enough for a 60-pixel line."""
    return float(f"{x:.4g}") if x is not None and np.isfinite(x) else None


def build(df: pd.DataFrame, data_dir: Path) -> dict:
    asof = df["asof"].iloc[0]
    since = (dt.date.fromisoformat(asof) - dt.timedelta(days=400)).isoformat()
    px = cotahist.load(data_dir, since=since)
    px = px[px.date <= asof]
    cash, stock = events.load(data_dir)
    prices = backtest.Prices(px, cash, stock)
    sessions = np.sort(px.date.unique())
    year = sessions[-(YEAR + 1):]
    weekly = list(year[::-WEEK][::-1])           # every fifth session, ending on the last

    def returns(t):
        at = lambda i: prices.at(t, sessions[-1 - i]) if len(sessions) > i else np.nan  # noqa: E731
        now = at(0)
        return {k: _r(now / at(i) - 1) if at(i) > 0 else None for k, i in (("r1d", 1), ("r1m", MONTH), ("r1y", YEAR))}

    out = {"asof": str(sessions[-1]), "weekly": weekly, "tickers": {}}
    for t in sorted(df.ticker):
        s = prices.series(t)
        first = s.index[0] if len(s) else "9999"
        out["tickers"][t] = {"w": [_sig(prices.at(t, d)) if d >= first else None for d in weekly], **returns(t)}
    b = cotahist.BENCHMARK
    raw = px[px.ticker == b].set_index("date").close
    out["bova11"] = {"dates": [str(d) for d in year], "close": [_sig(raw.get(d, np.nan)) for d in year], **returns(b)}
    path = data_dir / "screen" / "sparks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    return out

"""The weekly shortlist and its track record.

Each Monday's top N (by the composite score, and by Greenblatt's Magic
Formula as a baseline) is appended to data/picks/picks.csv with that day's
price. The track record follows every list as an equal-weight portfolio held
until the next list, on dividend- and split-adjusted prices, against BOVA11.
Nothing is ever removed from the log: losers stay visible.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import cotahist, events

TOP_N = 10
STRATEGIES = {"composite": "rank", "magic": "magic_rank"}
BENCHMARK = cotahist.BENCHMARK
PICK_COLUMNS = ["date", "strategy", "rank", "ticker", "company", "sector", "score", "price"]


def select(screen: pd.DataFrame, n: int = TOP_N) -> pd.DataFrame:
    out = []
    for strategy, col in STRATEGIES.items():
        top = screen[screen[col].notna()].sort_values(col).head(n)
        out.append(pd.DataFrame({
            "date": top["asof"], "strategy": strategy, "rank": top[col].astype(int), "ticker": top.ticker,
            "company": top.company, "sector": top.sector, "score": top.score.round(2), "price": top.price,
        }))
    return pd.concat(out, ignore_index=True)[PICK_COLUMNS]


def _path(data_dir: Path, name: str) -> Path:
    return data_dir / "picks" / name


def load(data_dir: Path) -> pd.DataFrame:
    p = _path(data_dir, "picks.csv")
    return pd.read_csv(p, dtype={"date": str, "ticker": str}) if p.exists() else pd.DataFrame(columns=PICK_COLUMNS)


def record(new: pd.DataFrame, data_dir: Path) -> pd.DataFrame:
    """Append a list; re-running on the same date replaces that date's list."""
    log = load(data_dir)
    log = pd.concat([log[~log.date.isin(new.date)], new], ignore_index=True)
    log = log.sort_values(["date", "strategy", "rank"])
    p = _path(data_dir, "picks.csv")
    p.parent.mkdir(parents=True, exist_ok=True)
    log.to_csv(p, index=False, lineterminator="\n")
    return log


def changes(log: pd.DataFrame, strategy: str = "composite") -> tuple[list[str], list[str]]:
    """Tickers that entered / left the list since the previous one."""
    dates = sorted(log[log.strategy == strategy].date.unique())
    if len(dates) < 2:
        return [], []
    cur = set(log[(log.strategy == strategy) & (log.date == dates[-1])].ticker)
    prev = set(log[(log.strategy == strategy) & (log.date == dates[-2])].ticker)
    return sorted(cur - prev), sorted(prev - cur)


def _adjusted(px: pd.DataFrame, cash, stock) -> dict[str, pd.Series]:
    out = {}
    for t, g in px.groupby("ticker"):
        out[t] = events.adjusted_close(g[["date", "close"]], g["isin"].iloc[-1], cash, stock)
    return out


def _ret(adj: dict, ticker: str, d0: str, d1: str) -> float:
    s = adj.get(ticker)
    if s is None:
        return np.nan
    a, b = s[s.index <= d0], s[s.index <= d1]
    if a.empty or b.empty or a.iloc[-1] <= 0:
        return np.nan
    return b.iloc[-1] / a.iloc[-1] - 1   # a ticker that stopped trading keeps its last price


def performance(data_dir: Path, asof: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(curve, cohorts). ``curve``: portfolio and benchmark value (start 100)
    at each list date and ``asof``; ``cohorts``: each list's return to date."""
    log = load(data_dir)
    if log.empty:
        return pd.DataFrame(columns=["date", "strategy", "portfolio", "benchmark"]), pd.DataFrame()
    asof = asof or cotahist.last_date(data_dir)
    px = cotahist.load(data_dir, since=log.date.min()[:7] + "-01")
    px = px[px.date <= asof]
    cash, stock = events.load(data_dir)
    adj = _adjusted(px[px.ticker.isin(set(log.ticker) | {BENCHMARK})], cash, stock)

    curve, cohorts = [], []
    for strategy in STRATEGIES:
        lg = log[log.strategy == strategy]
        dates = sorted(lg.date.unique())
        if not dates:
            continue
        value = bench = 100.0
        curve.append({"date": dates[0], "strategy": strategy, "portfolio": value, "benchmark": bench})
        for i, d0 in enumerate(dates):
            d1 = dates[i + 1] if i + 1 < len(dates) else asof
            names = lg[lg.date == d0].ticker
            rets = [r for r in (_ret(adj, t, d0, d1) for t in names) if np.isfinite(r)]
            period = float(np.mean(rets)) if rets else 0.0
            b = _ret(adj, BENCHMARK, d0, d1)
            value *= 1 + period
            bench *= 1 + (b if np.isfinite(b) else 0.0)
            if d1 != d0:
                curve.append({"date": d1, "strategy": strategy, "portfolio": value, "benchmark": bench})
            to_date = [r for r in (_ret(adj, t, d0, asof) for t in names) if np.isfinite(r)]
            cohorts.append({"date": d0, "strategy": strategy, "names": len(names),
                            "return": float(np.mean(to_date)) if to_date else np.nan,
                            "benchmark": _ret(adj, BENCHMARK, d0, asof),
                            "hit_rate": float(np.mean([r > 0 for r in to_date])) if to_date else np.nan})
    curve = pd.DataFrame(curve).drop_duplicates(["date", "strategy"], keep="last")
    return curve, pd.DataFrame(cohorts)


def save_performance(curve: pd.DataFrame, cohorts: pd.DataFrame, data_dir: Path) -> None:
    curve.round(4).to_csv(_path(data_dir, "performance.csv"), index=False, lineterminator="\n")
    cohorts.round(4).to_csv(_path(data_dir, "cohorts.csv"), index=False, lineterminator="\n")

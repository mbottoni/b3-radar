"""Backtest the screen the way a long-term, buy-and-hold investor would use it.

Once a year, on the first session of May (annual reports, due at the end of
March, are public by then), take the top 10 of the screen as it stood that
day, buy them in equal weights and hold for a year with dividends
reinvested; then repeat. Each yearly list is also followed untouched for
one, three and five years. Every list is made point in time
(``screen.compute(..., pit=True)``): only quotes, filings and events public
on that date.

Compared against BOVA11 (Ibovespa, a total-return index), the CDI (what
cash earns in Brazil) and every eligible stock in equal weights (does the
picking add anything over owning the whole universe?).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import cotahist, events, screen

REBALANCE_MONTH = 5
FIRST_YEAR = 2012          # needs a year of quotes and TTM statements, which start in 2010-2011
TOP_N = 10
HORIZONS = (1, 3, 5)
STRATEGIES = {             # column, ascending
    "composite": ("score", False),
    "magic": ("magic_rank", True),
    "value": ("value_score", False),
    "quality": ("quality_score", False),
    "momentum": ("momentum_score", False),
    "income": ("income_score", False),
    "composite_bottom": ("score", True),       # the avoid list: the 10 lowest scores
}
# The avoid list, as fifths: the score's bottom fifth, and every eligible stock but those.
AVOID = ("score_q5", "eligible_ex_q5")
BENCHMARKS = ("eligible", "bova11", "cdi")
QUINTILE_FACTORS = {"score": "score", "value": "value_score", "quality": "quality_score",
                    "momentum": "momentum_score", "income": "income_score", "growth": "growth_score"}
QUINTILE_MIN = 25          # scored names needed to split a date into fifths (growth: none in 2012)
# How often the score's top 10 is set back to the current list (months between rebalances, from May).
# The live record holds each weekly list one week; "weekly" (the last session of each week, as the
# weekly job uses) needs a screen per week, about 40 minutes, so it runs only on request (--weekly).
CADENCES = {"yearly": 12, "quarterly": 3, "monthly": 1}
CADENCE_SERIES = {"yearly": "composite", "quarterly": "composite_q", "monthly": "composite_m", "weekly": "composite_w"}
COST_PER_SIDE = 0.001      # brokerage, exchange fees and half the spread, per side of every trade (--cost, in %)


def rebalance_dates(sessions: np.ndarray, first_year: int = FIRST_YEAR) -> list[str]:
    out = []
    for y in range(first_year, int(sessions[-1][:4]) + 1):
        later = sessions[sessions >= f"{y}-{REBALANCE_MONTH:02d}-01"]
        if len(later):
            out.append(later[0])
    return sorted(set(out))


def pick(snap: pd.DataFrame, col: str, ascending: bool, n: int = TOP_N) -> pd.DataFrame:
    ok = snap[(snap.excluded.fillna("") == "") & snap[col].notna()]
    # Pillar scores are means of percentiles, so exact ties are common. An
    # unstable sort orders them differently on x86 and ARM (numpy uses
    # different SIMD sorts): break ties explicitly, with a stable sort.
    return ok.sort_values([col, "score", "ticker"], ascending=[ascending, False, True], kind="stable").head(n)


def cadence_dates(sessions: np.ndarray, months: int, first_year: int = FIRST_YEAR) -> list[str]:
    """First session of every ``months``-th month, counted from May of ``first_year``."""
    out = []
    for y in range(first_year, int(sessions[-1][:4]) + 1):
        for m in range(1, 13):
            if (y == first_year and m < REBALANCE_MONTH) or (m - REBALANCE_MONTH) % months:
                continue
            later = sessions[sessions >= f"{y}-{m:02d}-01"]
            if len(later):
                out.append(later[0])
    return sorted(set(out))


def week_ends(sessions: np.ndarray, first: str) -> list[str]:
    """``first``, then the last session of every later week (the session the weekly list uses)."""
    s = pd.Series(sessions[sessions > first])
    ends = s.groupby(pd.to_datetime(s).dt.strftime("%G-%V")).max()
    return [first] + sorted(ends)


class Prices:
    """Adjusted closes, looked up as of any date (a ticker that stopped
    trading keeps its last price)."""

    def __init__(self, px: pd.DataFrame, cash: pd.DataFrame, stock: pd.DataFrame):
        self.px, self.cash, self.stock, self.cache = px, cash, stock, {}

    def series(self, ticker: str) -> pd.Series:
        if ticker not in self.cache:
            g = self.px[self.px.ticker == ticker]
            self.cache[ticker] = events.adjusted_close(g[["date", "close"]], set(g["isin"]), self.cash, self.stock) \
                if len(g) else pd.Series(dtype=float)
        return self.cache[ticker]

    def at(self, ticker: str, date: str) -> float:
        s = self.series(ticker)
        i = s.index.searchsorted(date, side="right")
        return float(s.iloc[i - 1]) if i else np.nan

    def ret(self, tickers, d0: str, d1: str) -> float:
        """Equal-weight buy-and-hold return of ``tickers`` from d0 to d1."""
        r = [self.at(t, d1) / self.at(t, d0) for t in tickers]
        r = [x for x in r if np.isfinite(x) and x > 0]
        return float(np.mean(r)) - 1 if r else np.nan


def follow(lists: dict[str, list[str]], dates: list[str], end: str, checkpoints: list[str], prices: Prices,
           cost: float = COST_PER_SIDE) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(values, trades) of a portfolio bought in equal weights on ``dates[0]``
    and set back to equal weights on each later date's list.

    ``values``: gross and net of ``cost`` per side of every trade, at every
    checkpoint; the value on a rebalance date is before that day's trades.
    ``trades``: per rebalance, the share of the portfolio bought and sold.
    Between rebalances the holdings drift with their returns; a rebalance
    trades the gap between those weights and equal weights on the new list
    (selling a third of the portfolio to buy new names is a turnover of a
    third). Names with no price at either end are left out, as ``Prices.ret``
    does."""
    gross = net = 100.0
    held: dict[str, float] = {}
    rows, trades = [{"date": dates[0], "gross": gross, "net": net}], []
    for i, d0 in enumerate(dates):
        d1 = dates[i + 1] if i + 1 < len(dates) else end
        names = lists[d0]
        target = {t: 1 / len(names) for t in names} if names else {}
        bought = sum(max(target.get(t, 0.0) - held.get(t, 0.0), 0.0) for t in set(target) | set(held))
        sold = sum(max(held.get(t, 0.0) - target.get(t, 0.0), 0.0) for t in set(target) | set(held))
        trades.append({"date": d0, "bought": bought, "sold": sold})
        net *= 1 - cost * (bought + sold)
        g0, n0 = gross, net
        for c in (c for c in checkpoints if d0 < c <= d1):
            x = prices.ret(names, d0, c)
            x = x if np.isfinite(x) else 0.0
            rows.append({"date": c, "gross": g0 * (1 + x), "net": n0 * (1 + x)})
        ratio = {t: prices.at(t, d1) / prices.at(t, d0) for t in names}
        ratio = {t: r for t, r in ratio.items() if np.isfinite(r) and r > 0}
        x = float(np.mean(list(ratio.values()))) - 1 if ratio else 0.0
        gross, net = g0 * (1 + x), n0 * (1 + x)
        total = sum(ratio.values())
        held = {t: r / total for t, r in ratio.items()} if total else {}
    return pd.DataFrame(rows).drop_duplicates("date", keep="last"), pd.DataFrame(trades)


def cdi_index(data_dir: Path) -> pd.Series:
    c = pd.read_csv(data_dir / "macro" / "cdi.csv", dtype={"date": str})
    return (1 + c.set_index("date").rate / 100).cumprod()


def _cdi_ret(idx: pd.Series, d0: str, d1: str) -> float:
    a, b = idx[idx.index <= d0], idx[idx.index <= d1]
    return float(b.iloc[-1] / a.iloc[-1] - 1) if len(a) and len(b) else np.nan


def run(data_dir: Path, first_year: int = FIRST_YEAR, log=print, cost: float = COST_PER_SIDE,
        cadences: tuple[str, ...] = tuple(CADENCES)) -> dict[str, pd.DataFrame]:
    inp = screen.load_inputs(data_dir)
    sessions = np.sort(inp.px.date.unique())
    end = sessions[-1]
    dates = rebalance_dates(sessions, first_year)
    prices = Prices(inp.px, inp.cash, inp.stock)
    cdi = cdi_index(data_dir)

    lists, holdings, buckets = {}, [], {}
    for d in dates:
        snap = screen.compute(inp, d, pit=True)
        eligible = snap[snap.excluded.fillna("") == ""]
        lists[d] = {"eligible": list(eligible.ticker)}
        # Fifths of the eligible universe by each factor (Q1 = best).
        for f, col in QUINTILE_FACTORS.items():
            e = eligible[eligible[col].notna()]
            if len(e) < QUINTILE_MIN:
                continue
            q = pd.qcut(e[col].rank(method="first", ascending=False), 5, labels=[1, 2, 3, 4, 5])
            for k in range(1, 6):
                buckets[(d, f, k)] = list(e.ticker[q == k])
        q5 = set(buckets.get((d, "score", 5), ()))
        lists[d]["score_q5"] = sorted(q5)
        lists[d]["eligible_ex_q5"] = [t for t in lists[d]["eligible"] if t not in q5]
        for name, (col, asc) in STRATEGIES.items():
            top = pick(snap, col, asc)
            lists[d][name] = list(top.ticker)
            for rank, r in enumerate(top.itertuples(), 1):
                holdings.append({"date": d, "strategy": name, "rank": rank, "ticker": r.ticker, "company": r.company,
                                 "sector": r.sector, "metric": round(float(getattr(r, col)), 4)})
        log(f"[backtest] {d}: {len(eligible)} eligible; composite {', '.join(lists[d]['composite'])}")

    # Monthly checkpoints (last session of each month) plus rebalance dates.
    s = pd.Series(sessions)
    checkpoints = sorted(set(s.groupby(s.str[:7]).max()) | set(dates) | {end})
    checkpoints = [c for c in checkpoints if c >= dates[0]]
    series = list(STRATEGIES) + list(AVOID) + list(BENCHMARKS)
    value = {k: 100.0 for k in series}
    curve, periods = [], []
    for k in series:
        curve.append({"date": dates[0], "series": k, "value": 100.0})
    for i, d0 in enumerate(dates):
        d1 = dates[i + 1] if i + 1 < len(dates) else end
        for k in series:
            def r(c):
                if k == "bova11":
                    return prices.ret([cotahist.BENCHMARK], d0, c)
                if k == "cdi":
                    return _cdi_ret(cdi, d0, c)
                return prices.ret(lists[d0][k], d0, c)
            for c in (c for c in checkpoints if d0 < c <= d1):
                x = r(c)
                curve.append({"date": c, "series": k, "value": value[k] * (1 + (x if np.isfinite(x) else 0.0))})
            x = r(d1)
            periods.append({"start": d0, "end": d1, "series": k, "return": x})
            value[k] *= 1 + (x if np.isfinite(x) else 0.0)
    curve = pd.DataFrame(curve).drop_duplicates(["date", "series"], keep="last")
    periods = pd.DataFrame(periods)

    # The score's top 10 rebalanced yearly, quarterly, monthly (or weekly), gross and net of costs.
    cad_dates = {c: week_ends(sessions, dates[0]) if c == "weekly" else cadence_dates(sessions, CADENCES[c], first_year)
                 for c in cadences}
    cad_dates = {c: [d for d in ds if d < end or d == dates[0]] for c, ds in cad_dates.items()}
    tops = {d: lists[d]["composite"] for d in dates}
    todo = sorted(set().union(*cad_dates.values()) - set(tops)) if cad_dates else []
    for j, d in enumerate(todo):
        tops[d] = list(pick(screen.compute(inp, d, pit=True), *STRATEGIES["composite"]).ticker)
        if j % 24 == 0 or j == len(todo) - 1:
            log(f"[backtest] rebalance lists: {d} ({j + 1}/{len(todo)})")
    years = (pd.Timestamp(end) - pd.Timestamp(dates[0])).days / 365.25
    cad_rows, extra_curve, extra_periods = [], [], []
    for c, ds in cad_dates.items():
        pts = sorted(set(checkpoints) | set(ds))
        vals, trades = follow(tops, ds, end, pts, prices, cost)
        vals = vals.set_index("date")
        name = CADENCE_SERIES[c]
        for col, k in (("gross", name), ("net", f"{name}_net")):
            if k == "composite":          # the yearly gross series is the backtest's own
                continue
            v = vals[col]
            extra_curve += [{"date": d, "series": k, "value": float(x)} for d, x in v[v.index.isin(checkpoints)].items()]
            for i, d0 in enumerate(dates):
                d1 = dates[i + 1] if i + 1 < len(dates) else end
                extra_periods.append({"start": d0, "end": d1, "series": k, "return": float(v[d1] / v[d0] - 1)})
        g, n = vals.gross.iloc[-1] / 100, vals.net.iloc[-1] / 100
        cad_rows.append({"cadence": c, "series": name, "rebalances": len(ds), "cost_per_side": cost,
                         "turnover_per_rebalance": float(trades.sold.iloc[1:].mean()) if len(trades) > 1 else 0.0,
                         "turnover_per_year": float(trades.sold.sum() / years),
                         "gross_cagr": g ** (1 / years) - 1, "net_cagr": n ** (1 / years) - 1})
    cadence = pd.DataFrame(cad_rows)
    if len(cadence):
        cadence["cost_per_year"] = cadence.gross_cagr - cadence.net_cagr
    curve = pd.concat([curve, pd.DataFrame(extra_curve)], ignore_index=True)
    periods = pd.concat([periods, pd.DataFrame(extra_periods)], ignore_index=True)

    # Ticker returns within each holding period (for the holdings table).
    hold = pd.DataFrame(holdings)
    nxt = {d: (dates[i + 1] if i + 1 < len(dates) else end) for i, d in enumerate(dates)}
    hold["period_return"] = [prices.ret([t], d, nxt[d]) for t, d in zip(hold.ticker, hold.date)]

    # Each list bought once and held untouched.
    cohorts = []
    for d0 in dates:
        for h in HORIZONS:
            target = (pd.Timestamp(d0) + pd.DateOffset(years=h)).strftime("%Y-%m-%d")
            later = sessions[sessions >= target]
            d1, complete = (later[0], True) if len(later) else (end, False)
            row = {"start": d0, "horizon": h, "end": d1, "complete": complete,
                   "bova11": prices.ret([cotahist.BENCHMARK], d0, d1), "cdi": _cdi_ret(cdi, d0, d1),
                   "eligible": prices.ret(lists[d0]["eligible"], d0, d1)}
            for k in ("composite", "magic"):
                row[k] = prices.ret(lists[d0][k], d0, d1)
            cohorts.append(row)
    cohorts = pd.DataFrame(cohorts)
    summary = _summary(curve, periods, dates[0], end)
    qrows, qper, qdates = [], [], {}
    for f in QUINTILE_FACTORS:
        # Only the years a factor could be measured (growth needs 3 years of statements: from 2013).
        qdates[f] = [d for d in dates if (d, f, 1) in buckets]
        years = (pd.Timestamp(end) - pd.Timestamp(qdates[f][0])).days / 365.25
        for k in range(1, 6):
            v = 1.0
            for d0 in qdates[f]:
                r = prices.ret(buckets[(d0, f, k)], d0, nxt[d0])
                qper.append({"start": d0, "factor": f, "quintile": k, "return": r,
                             "names": len(buckets[(d0, f, k)])})
                v *= 1 + (r if np.isfinite(r) else 0.0)
            qrows.append({"factor": f, "quintile": k, "first": qdates[f][0], "total_return": v - 1,
                          "cagr": v ** (1 / years) - 1})
    quintiles = pd.DataFrame(qrows)
    qper = pd.DataFrame(qper)
    # How often the top fifth beat the bottom fifth, period by period.
    wins = {f: int(sum(qper[(qper.factor == f) & (qper.quintile == 1) & (qper.start == d)]["return"].iloc[0]
                       > qper[(qper.factor == f) & (qper.quintile == 5) & (qper.start == d)]["return"].iloc[0]
                       for d in qdates[f])) for f in QUINTILE_FACTORS}
    quintiles["top_beat_bottom"] = quintiles.factor.map(lambda f: f"{wins[f]}/{len(qdates[f])}")
    meta = {"first": dates[0], "last": end, "rebalances": len(dates), "top_n": TOP_N, "rules": screen.rules_hash(),
            "rebalance": f"first session of month {REBALANCE_MONTH}", "costs": "none",
            "cost_per_side": cost, "cadences": list(cad_dates)}
    return {"curve": curve, "periods": periods, "holdings": hold, "cohorts": cohorts, "summary": summary, "meta": meta,
            "quintiles": quintiles, "quintile_periods": qper, "cadence": cadence}


def _summary(curve: pd.DataFrame, periods: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    years = (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25
    bova = periods[periods.series == "bova11"].set_index("start")["return"]
    cdi_cagr = None
    rows = []
    for k, g in curve.groupby("series", sort=False):
        v = g.sort_values("date").set_index("date").value
        monthly = v.pct_change().dropna()
        cagr = (v.iloc[-1] / 100) ** (1 / years) - 1
        if k == "cdi":
            cdi_cagr = cagr
        p = periods[periods.series == k].set_index("start")["return"]
        rows.append({"series": k, "total_return": v.iloc[-1] / 100 - 1, "cagr": cagr,
                     "volatility": float(monthly.std() * np.sqrt(12)) if len(monthly) > 2 else np.nan,
                     "max_drawdown": float((v / v.cummax() - 1).min()),
                     "best_year": float(p.max()), "worst_year": float(p.min()),
                     "years_beating_bova11": f"{int((p > bova.reindex(p.index)).sum())}/{len(p)}" if k != "bova11" else ""})
    out = pd.DataFrame(rows)
    out["excess_over_cdi"] = out.cagr - cdi_cagr
    return out


def save(res: dict, data_dir: Path) -> None:
    out = data_dir / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("curve", "periods", "holdings", "cohorts", "summary", "quintiles", "quintile_periods", "cadence"):
        res[name].to_csv(out / f"{name}.csv", index=False, lineterminator="\n", float_format="%.6g")
    (out / "meta.json").write_text(json.dumps(res["meta"], indent=2) + "\n")

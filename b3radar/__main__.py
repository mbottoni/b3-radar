"""Command line: ``python -m b3radar {daily,weekly,backfill,screen}``."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

from . import backtest, cotahist, cvm, events, history, picks, report, screen

REPO = Path(__file__).resolve().parent.parent


def _today(a) -> dt.date:
    return dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(dt.UTC).date()


def refresh_cvm(data_dir: Path, cache: Path, year: int) -> None:
    """Register, trading codes, and the statements the screen can use:
    annual reports filed in the last three calendar years, quarterlies for this and last."""
    out = data_dir / "cvm"
    out.mkdir(parents=True, exist_ok=True)
    cvm.companies(cvm.fetch_register(cache)).to_csv(out / "companies.csv", index=False, lineterminator="\n")
    for y in (year - 1, year):        # this year's FCA may not exist yet in January
        fca = cvm.fetch_doc("FCA", y, cache)
        if fca is not None:
            cvm.merge_tickers(cvm.tickers(fca), data_dir)
    # This year's DFP file too: companies with fiscal years ending in
    # February or March (CAML, SMTO) file their latest annual report there.
    for kind, years in (("DFP", (year - 2, year - 1, year)), ("ITR", (year - 1, year))):
        for y in years:
            z = cvm.fetch_doc(kind, y, cache)
            if z is not None:
                cvm.store_filings(cvm.filings(kind, z), data_dir)


def backfill_cvm(data_dir: Path, cache: Path, first: int = 2010, last: int | None = None) -> None:
    """Statements, trading codes and the FRE capital timeline since ``first``
    (for the backtest; the daily job keeps the recent years fresh)."""
    last = last or dt.datetime.now(dt.UTC).year
    for y in range(first, last + 1):
        for kind in ("DFP", "ITR"):
            z = cvm.fetch_doc(kind, y, cache)
            if z is not None:
                cvm.store_filings(cvm.filings(kind, z), data_dir)
        fca = cvm.fetch_doc("FCA", y, cache)
        if fca is not None:
            cvm.merge_tickers(cvm.tickers(fca), data_dir)
        if y <= 2021:      # DFP/ITR carry share capital from 2020 on
            fre = cvm.fetch_doc("FRE", y, cache)
            if fre is not None:
                cvm.store_capital(cvm.capital_history(fre), data_dir)
        print(f"[cvm] {y} done", file=sys.stderr)


def candidate_issuers(data_dir: Path, min_volume: float = 1e6) -> list[str]:
    """Issuer codes worth fetching events for: a wider net than the screen's
    liquidity cut, so a stock drifting into the universe already has history."""
    last = cotahist.last_date(data_dir)
    px = cotahist.load(data_dir, since=(dt.date.fromisoformat(last) - dt.timedelta(days=120)).isoformat())
    px = px[px.kind != "ETF"]
    sessions = sorted(px.date.unique())[-screen.LIQUIDITY_WINDOW:]
    liq = px[px.date.isin(sessions)].groupby("ticker").volume.sum() / screen.LIQUIDITY_WINDOW
    return sorted({t[:4] for t in liq[liq >= min_volume].index})


def refresh_inferred(data_dir: Path) -> None:
    """Re-derive splits missing from B3's events service from B3's ex-markers
    (see events.infer_stock_events)."""
    px = cotahist.load(data_dir)
    _, stock = events.load(data_dir)
    events.save_inferred(events.infer_stock_events(px, stock[~stock.label.str.contains("INFERIDO")]), data_dir)


def write_status(data_dir: Path, df: pd.DataFrame) -> None:
    status = {"asof": df["asof"].iloc[0], "rules": screen.rules_hash(), "companies": int(len(df)),
              "eligible": int((df.excluded.fillna("") == "").sum()),
              "first_quote": sorted((data_dir / "prices").glob("*.csv"))[0].stem}
    (data_dir / "status.json").write_text(json.dumps(status, indent=2) + "\n")


def cmd_daily(a) -> int:
    today = _today(a)
    if cotahist.last_date(a.data) is None:
        cotahist.backfill([today.year - 1, today.year], a.data, a.cache)
    cotahist.update_daily(a.data, a.cache, today)
    refresh_cvm(a.data, a.cache, today.year)
    print(f"[events] {events.refresh(candidate_issuers(a.data), a.data)}", file=sys.stderr)
    history.update_cdi(a.data)
    refresh_inferred(a.data)
    df = screen.build(a.data)
    screen.save(df, a.data)
    write_status(a.data, df)
    print(f"screen as of {df['asof'].iloc[0]}: {len(df)} companies, {(df.excluded == '').sum()} eligible", file=sys.stderr)
    return 0


def cmd_weekly(a) -> int:
    today = _today(a)
    # Reconcile with B3's authoritative yearly file: fills any session a
    # daily run missed (B3 sometimes 404s a daily file for a while).
    years = [today.year - 1, today.year] if today.month == 1 else [today.year]
    cotahist.backfill(years, a.data, a.cache)
    refresh_inferred(a.data)
    df = screen.build(a.data)
    screen.save(df, a.data)
    write_status(a.data, df)
    asof = df["asof"].iloc[0]
    hist = a.data / "screen" / "history" / f"{asof}.csv"
    hist.parent.mkdir(parents=True, exist_ok=True)
    df[df.excluded == ""][screen.COLUMNS].to_csv(hist, index=False, lineterminator="\n", float_format="%.6g")

    new = picks.select(df)
    log = picks.record(new, a.data)
    entered, left = picks.changes(log)
    curve, cohorts = picks.performance(a.data, asof)
    picks.save_performance(curve, cohorts, a.data)
    subject, html_body, text = report.build(df, new, entered, left, cohorts, curve)
    report.send(subject, html_body, text, a.out)
    return 0


def cmd_backtest(a) -> int:
    res = backtest.run(a.data, a.first_year, log=lambda m: print(m, file=sys.stderr))
    backtest.save(res, a.data)
    print(res["summary"].round(3).to_string(index=False), file=sys.stderr)
    return 0


def cmd_history(a) -> int:
    """One-time backfill of everything the backtest needs since 2010."""
    today = _today(a)
    cotahist.backfill(list(range(a.first_year, today.year + 1)), a.data, a.cache)
    backfill_cvm(a.data, a.cache, a.first_year, today.year)
    px = cotahist.load(a.data)
    codes = sorted({t[:4] for t in px[px.kind != "ETF"].ticker.unique()})
    print(f"[events] {events.refresh(codes, a.data)}", file=sys.stderr)
    iss = pd.read_csv(a.data / "events" / "issuers.csv", dtype=str, keep_default_na=False)
    print(f"[history] {history.backfill_dividends({r.issuer: r.name for r in iss.itertuples() if r.name}, px, a.data)}",
          file=sys.stderr)
    history.update_cdi(a.data)
    refresh_inferred(a.data)
    return 0


def cmd_backfill(a) -> int:
    cotahist.backfill(a.years, a.data, a.cache)
    return 0


def cmd_screen(a) -> int:
    df = screen.build(a.data, a.asof)
    screen.save(df, a.data)
    write_status(a.data, df)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b3radar", description=__doc__)
    p.add_argument("--data", type=Path, default=REPO / "data")
    p.add_argument("--cache", type=Path, default=REPO / ".cache" / "raw")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("daily", help="fetch quotes, filings and events; rebuild the screen")
    d.add_argument("--today", help="YYYY-MM-DD (default: today, UTC)")
    d.set_defaults(fn=cmd_daily)

    w = sub.add_parser("weekly", help="reconcile quotes, record the shortlist, update the track record, email")
    w.add_argument("--today")
    w.add_argument("--out", type=Path, default=REPO / "out")
    w.set_defaults(fn=cmd_weekly)

    t = sub.add_parser("backtest", help="yearly buy-and-hold backtest of the screen, point in time")
    t.add_argument("--first-year", type=int, default=backtest.FIRST_YEAR)
    t.set_defaults(fn=cmd_backtest)

    h = sub.add_parser("history", help="one-time backfill of quotes, filings, events and dividends since 2010")
    h.add_argument("--first-year", type=int, default=2010)
    h.add_argument("--today")
    h.set_defaults(fn=cmd_history)

    b = sub.add_parser("backfill", help="load whole years of quotes from B3's yearly files")
    b.add_argument("years", nargs="+", type=int)
    b.set_defaults(fn=cmd_backfill)

    s = sub.add_parser("screen", help="rebuild the screen from data/ only")
    s.add_argument("--asof")
    s.set_defaults(fn=cmd_screen)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())

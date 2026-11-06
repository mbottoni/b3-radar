"""Command line: ``python -m b3radar {daily,weekly,backfill,screen}``."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

from . import cotahist, cvm, events, picks, report, screen

REPO = Path(__file__).resolve().parent.parent


def _today(a) -> dt.date:
    return dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(dt.UTC).date()


def refresh_cvm(data_dir: Path, cache: Path, year: int) -> None:
    """Register, trading codes, and the statements the screen can use:
    annual reports for the last two years, quarterlies for this and last."""
    out = data_dir / "cvm"
    out.mkdir(parents=True, exist_ok=True)
    cvm.companies(cvm.fetch_register(cache)).to_csv(out / "companies.csv", index=False, lineterminator="\n")
    for y in (year, year - 1):        # this year's FCA may not exist yet in January
        fca = cvm.fetch_doc("FCA", y, cache)
        if fca is not None:
            cvm.tickers(fca).to_csv(out / "tickers.csv", index=False, lineterminator="\n")
            break
    for kind, years in (("DFP", (year - 2, year - 1)), ("ITR", (year - 1, year))):
        for y in years:
            z = cvm.fetch_doc(kind, y, cache)
            if z is not None:
                cvm.store_filings(cvm.filings(kind, z), data_dir)


def candidate_issuers(data_dir: Path, min_volume: float = 1e6) -> list[str]:
    """Issuer codes worth fetching events for: a wider net than the screen's
    liquidity cut, so a stock drifting into the universe already has history."""
    last = cotahist.last_date(data_dir)
    px = cotahist.load(data_dir, since=(dt.date.fromisoformat(last) - dt.timedelta(days=120)).isoformat())
    px = px[px.kind != "ETF"]
    sessions = sorted(px.date.unique())[-screen.LIQUIDITY_WINDOW:]
    liq = px[px.date.isin(sessions)].groupby("ticker").volume.sum() / screen.LIQUIDITY_WINDOW
    return sorted({t[:4] for t in liq[liq >= min_volume].index})


def write_status(data_dir: Path, df: pd.DataFrame) -> None:
    status = {"asof": df["asof"].iloc[0], "companies": int(len(df)),
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

"""B3 daily quotes (COTAHIST): parse the fixed-width files, keep stocks and the benchmark.

Layout (B3, "Séries Históricas"): one 245-character record per instrument
per day. We keep the cash market (TPMERC 010), standard lots (CODBDI 02) of
shares and units, plus BOVA11 as the benchmark. Prices are stored per share
(divided by the quotation factor FATCOT), in reais.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from pathlib import Path

import pandas as pd

from .fetch import download_zip, log

BASE = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist"
STOCK_KINDS = {"ON", "PN", "PNA", "PNB", "PNC", "PND", "PNE", "PNF", "PNG", "UNT"}
BENCHMARK = "BOVA11"
COLUMNS = ["date", "ticker", "isin", "kind", "open", "high", "low", "close", "volume", "trades"]


def parse_lines(lines) -> pd.DataFrame:
    rows = []
    for r in lines:
        if r[:2] != "01" or r[24:27] != "010":
            continue
        ticker = r[12:24].strip()
        spec = r[39:49].split()
        kind = spec[0] if spec else ""
        if ticker == BENCHMARK:
            kind = "ETF"
        elif r[10:12] != "02" or kind not in STOCK_KINDS:
            continue
        fat = int(r[210:217]) or 1

        def px(a: int, b: int) -> float:
            return round(int(r[a:b]) / 100 / fat, 6)

        d = r[2:10]
        rows.append((f"{d[:4]}-{d[4:6]}-{d[6:]}", ticker, r[230:242].strip(), "UNIT" if kind == "UNT" else kind,
                     px(56, 69), px(69, 82), px(82, 95), px(108, 121), round(int(r[170:188]) / 100, 2), int(r[147:152])))
    return pd.DataFrame(rows, columns=COLUMNS)


def parse_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            return parse_lines(io.TextIOWrapper(f, encoding="latin-1"))


def _month_path(data_dir: Path, month: str) -> Path:
    return data_dir / "prices" / f"{month}.csv"


def store(df: pd.DataFrame, data_dir: Path) -> list[str]:
    """Merge quotes into data/prices/YYYY-MM.csv (a date present in ``df``
    replaces that date). Returns the months written."""
    if df.empty:
        return []
    months = sorted(df.date.str[:7].unique())
    for m in months:
        path = _month_path(data_dir, m)
        new = df[df.date.str[:7] == m]
        if path.exists():
            old = pd.read_csv(path, dtype={"date": str, "ticker": str, "isin": str, "kind": str})
            new = pd.concat([old[~old.date.isin(new.date)], new])
        path.parent.mkdir(parents=True, exist_ok=True)
        new.sort_values(["date", "ticker"]).to_csv(path, index=False, lineterminator="\n")
    return months


def load(data_dir: Path, since: str | None = None) -> pd.DataFrame:
    files = sorted((data_dir / "prices").glob("*.csv"))
    if since:
        files = [f for f in files if f.stem >= since[:7]]
    if not files:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.concat(pd.read_csv(f, dtype={"date": str, "ticker": str, "isin": str, "kind": str}) for f in files)
    return df[df.date >= since] if since else df


def last_date(data_dir: Path) -> str | None:
    files = sorted((data_dir / "prices").glob("*.csv"))
    return pd.read_csv(files[-1], usecols=["date"]).date.max() if files else None


def backfill(years: list[int], data_dir: Path, cache: Path) -> list[str]:
    written = []
    for y in years:
        path = download_zip(f"{BASE}/COTAHIST_A{y}.ZIP", cache / f"COTAHIST_A{y}.ZIP")
        if path is None:
            log(f"COTAHIST_A{y}: not published")
            continue
        written += store(parse_zip(path), data_dir)
    return written


def update_daily(data_dir: Path, cache: Path, today: dt.date | None = None, max_days: int = 20) -> list[str]:
    """Fetch every daily file after the last stored date (404 = no session)."""
    today = today or dt.date.today()
    last = last_date(data_dir)
    start = dt.date.fromisoformat(last) + dt.timedelta(days=1) if last else today - dt.timedelta(days=max_days)
    if (today - start).days > max_days:
        raise RuntimeError(f"last stored quote is {last}; run a backfill for the gap instead of {max_days}+ daily files")
    written, missing, day = [], [], start
    while day <= today:
        # Weekdays: a 404 may be a server that has not got the file yet;
        # weekends: 404 is the expected answer, so do not wait for it.
        weekday = day.weekday() < 5
        path = download_zip(f"{BASE}/COTAHIST_D{day:%d%m%Y}.ZIP", cache / f"COTAHIST_D{day:%d%m%Y}.ZIP",
                            retry_404=2 if weekday else 0)
        if path is None and weekday:
            missing.append(day.isoformat())
        if path is not None:
            df = parse_zip(path)
            log(f"{day}: {len(df)} quotes")
            written += store(df, data_dir)
        day += dt.timedelta(days=1)
    if missing:
        log(f"no quote file for weekday(s) {', '.join(missing)}: holidays, or B3 lagging; "
            f"the weekly reconcile (yearly file) fills real gaps")
    return sorted(set(written))

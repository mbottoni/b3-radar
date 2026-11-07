"""Long history for the backtest: dividend history per share class (B3) and
the CDI (Banco Central). Both are merged into data/ once and then kept up
to date by the daily job.

B3's ``GetListedCashDividends`` lists every cash event since the 1990s, per
share class (ON, PN, PNA...), paged 120 at a time, keyed by trading name.
Companies that have left the exchange are not served, so delisted companies
lose their dividends in the backtest (their quotes remain): a small,
documented understatement of returns.
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import pandas as pd

from . import events
from .fetch import get_json

DIVIDENDS = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedCashDividends/"
CDI = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={}&dataFinal={}"
CLASS_KIND = {"ON": "ON", "PN": "PN", "PNA": "PNA", "PNB": "PNB", "PNC": "PNC", "PND": "PND", "UNT": "UNIT",
              "UNIT": "UNIT"}


def _q(payload: dict) -> str:
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def dividend_history(trading_name: str, pause: float = 0.25) -> list[dict]:
    rows, page = [], 1
    while True:
        d = get_json(DIVIDENDS + _q({"language": "pt-br", "pageNumber": page, "pageSize": 120,
                                     "tradingName": trading_name}))
        res = (d or {}).get("results") or []
        rows += res
        total = ((d or {}).get("page") or {}).get("totalPages") or 1
        if page >= total or not res:
            return rows
        page += 1
        time.sleep(pause)


def class_isins(prices: pd.DataFrame) -> dict[tuple[str, str], str]:
    """(issuer, kind) -> ISIN, from the quotes (latest ISIN per ticker)."""
    last = prices.sort_values("date").groupby("ticker").tail(1)
    out = {}
    for r in last.itertuples():
        out.setdefault((r.ticker[:4], r.kind), r.isin)
    return out


def backfill_dividends(issuers: dict[str, str], prices: pd.DataFrame, data_dir: Path, pause: float = 0.25) -> dict:
    """``issuers``: issuer code -> B3 trading name. Merges into data/events/cash.csv."""
    isin = class_isins(prices)
    rows, unmapped = [], 0
    for i, (code, name) in enumerate(sorted(issuers.items())):
        try:
            hist = dividend_history(name.strip(), pause)
        except RuntimeError as e:
            print(f"[history] {code}: {e}", file=sys.stderr)
            continue
        for h in hist:
            kind = CLASS_KIND.get((h.get("typeStock") or "").strip().upper())
            key = isin.get((code, kind))
            if key is None:
                unmapped += 1
                continue
            per = events._num(h.get("quotedPerShares")) or 1.0
            rows.append([code, key, (h.get("corporateAction") or "").strip(), events._num(h.get("valueCash")) / per,
                         events._date(h.get("lastDatePriorEx")), "", events._date(h.get("dateApproval")), "history"])
        time.sleep(pause)
        if (i + 1) % 50 == 0:
            print(f"[history] {i + 1}/{len(issuers)} issuers, {len(rows)} events", file=sys.stderr)
    events._merge(data_dir / "events" / "cash.csv", rows, events.CASH_COLUMNS,
                  ["isin", "label", "last_date_prior", "approved_on", "rate"])
    return {"issuers": len(issuers), "events": len(rows), "unmapped": unmapped}


def update_cdi(data_dir: Path, start: str = "2010-01-01") -> int:
    """Daily CDI (% per day) into data/macro/cdi.csv. BCB serves at most
    ten years of a daily series per request."""
    path = data_dir / "macro" / "cdi.csv"
    old = pd.read_csv(path, dtype={"date": str}) if path.exists() else pd.DataFrame(columns=["date", "rate"])
    begin = pd.Timestamp(old.date.max()) + pd.Timedelta(days=1) if len(old) else pd.Timestamp(start)
    end = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    rows = []
    while begin <= end:
        stop = min(begin + pd.DateOffset(years=9), end)
        data = get_json(CDI.format(begin.strftime("%d/%m/%Y"), stop.strftime("%d/%m/%Y"))) or []
        rows += [(f"{x['data'][6:]}-{x['data'][3:5]}-{x['data'][:2]}", float(x["valor"])) for x in data]
        begin = stop + pd.Timedelta(days=1)
    new = pd.concat([old, pd.DataFrame(rows, columns=["date", "rate"])]).drop_duplicates("date", keep="last")
    path.parent.mkdir(parents=True, exist_ok=True)
    new.sort_values("date").to_csv(path, index=False, lineterminator="\n")
    return len(rows)

"""Corporate events from B3's listed-companies service: dividends, JCP,
splits, reverse splits and bonus shares, per security (ISIN).

B3 only lists roughly the last year of cash events, so every fetch is
merged into data/events/*.csv: the repo accumulates the full history.

Stock-event factors as B3 publishes them (checked against PETR's 2008 1:2
split and MGLU's 2020 1:4 split, 2024 10:1 reverse split, 2025 5% bonus):
DESDOBRAMENTO and BONIFICACAO give the percentage of new shares (300 ->
x4), GRUPAMENTO gives the multiplier itself (0.1 -> /10).
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .fetch import get_json

API = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/"
CASH_COLUMNS = ["issuer", "isin", "label", "rate", "last_date_prior", "payment_date", "approved_on", "related_to"]
STOCK_COLUMNS = ["issuer", "isin", "label", "factor", "last_date_prior", "approved_on"]
ISSUER_COLUMNS = ["issuer", "cd_cvm", "name", "shares_on", "shares_pn"]


def _num(s: str) -> float:
    s = (s or "").strip()
    return float(s.replace(".", "").replace(",", ".")) if s else np.nan


def _date(s: str) -> str:
    s = (s or "").strip()
    return f"{s[6:10]}-{s[3:5]}-{s[0:2]}" if len(s) == 10 else ""


def share_multiplier(label: str, factor: float) -> float:
    """How many shares one old share becomes (1.0 for unknown labels)."""
    label = label.upper()
    if label in ("DESDOBRAMENTO", "BONIFICACAO"):
        return 1 + factor / 100
    if label == "GRUPAMENTO":
        return factor
    return 1.0


def fetch_issuer(code: str) -> dict | None:
    params = base64.b64encode(json.dumps({"issuingCompany": code, "language": "pt-br"}, separators=(",", ":")).encode())
    data = get_json(API + params.decode())
    return data[0] if isinstance(data, list) and data else None


def parse(code: str, d: dict) -> tuple[list, list, list]:
    cash = [[code, e.get("isinCode", ""), e.get("label", ""), _num(e.get("rate")), _date(e.get("lastDatePrior")),
             _date(e.get("paymentDate")), _date(e.get("approvedOn")), e.get("relatedTo", "")]
            for e in d.get("cashDividends") or []]
    stock = [[code, e.get("isinCode", ""), e.get("label", ""), _num(e.get("factor")), _date(e.get("lastDatePrior")),
              _date(e.get("approvedOn"))] for e in d.get("stockDividends") or []]
    info = [[code, str(d.get("codeCVM", "")).lstrip("0"), (d.get("tradingName") or "").strip(),
             _num(d.get("numberCommonShares")), _num(d.get("numberPreferredShares"))]]
    return cash, stock, info


def _merge(path: Path, rows: list, columns: list, key: list) -> pd.DataFrame:
    new = pd.DataFrame(rows, columns=columns)
    if path.exists():
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        for c in columns:
            if c not in old:
                old[c] = ""
        new = pd.concat([old[columns], new.astype({c: str for c in columns})], ignore_index=True)
    new = new.astype(str).replace("nan", "")
    new = new.drop_duplicates(key, keep="last").sort_values(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, index=False, lineterminator="\n")
    return new


def refresh(codes: list[str], data_dir: Path, pause: float = 0.25) -> dict:
    """Fetch events for each 4-letter issuer code and merge them into data/."""
    cash, stock, info, missing = [], [], [], []
    for i, code in enumerate(sorted(set(codes))):
        try:
            d = fetch_issuer(code)
        except RuntimeError as e:
            print(f"[events] {code}: {e}", file=sys.stderr)
            d = None
        if d is None:
            missing.append(code)
        else:
            c, s, inf = parse(code, d)
            cash += c; stock += s; info += inf
        time.sleep(pause)
    ev = data_dir / "events"
    _merge(ev / "cash.csv", cash, CASH_COLUMNS, ["isin", "label", "last_date_prior", "approved_on", "rate"])
    _merge(ev / "stock.csv", stock, STOCK_COLUMNS, ["isin", "label", "last_date_prior", "approved_on"])
    _merge(ev / "issuers.csv", info, ISSUER_COLUMNS, ["issuer"])
    return {"issuers": len(set(codes)), "missing": missing, "cash": len(cash), "stock": len(stock)}


def load(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    ev = data_dir / "events"
    cash = pd.read_csv(ev / "cash.csv", dtype=str, keep_default_na=False) if (ev / "cash.csv").exists() \
        else pd.DataFrame(columns=CASH_COLUMNS)
    stock = pd.read_csv(ev / "stock.csv", dtype=str, keep_default_na=False) if (ev / "stock.csv").exists() \
        else pd.DataFrame(columns=STOCK_COLUMNS)
    cash["rate"] = pd.to_numeric(cash.rate, errors="coerce")
    stock["factor"] = pd.to_numeric(stock.factor, errors="coerce")
    stock["mult"] = [share_multiplier(lbl, f) for lbl, f in zip(stock.label, stock.factor)]
    return cash, stock


# ---------------------------------------------------------------- adjustment

def adjusted_close(px: pd.DataFrame, isin: str, cash: pd.DataFrame, stock: pd.DataFrame) -> pd.Series:
    """Total-return adjusted closes for one ticker (latest close unchanged).

    ``px``: that ticker's rows (date, close), any order. Each event takes
    effect on the first session after its last 'com' date: a cash event
    scales earlier prices by 1 - rate / close(last com date), a stock event
    by 1 / multiplier.
    """
    s = px.sort_values("date").set_index("date").close.astype(float)
    if s.empty:
        return s
    dates = s.index.to_numpy()
    factor = pd.Series(1.0, index=s.index)
    evs = [("cash", r.last_date_prior, r.rate) for r in cash[cash["isin"] == isin].itertuples()]
    evs += [("stock", r.last_date_prior, r.mult) for r in stock[stock["isin"] == isin].itertuples()]
    for kind, last_com, val in evs:
        if not last_com or not np.isfinite(val):
            continue
        pos = np.searchsorted(dates, last_com, side="right")   # first session after the com date
        if pos == 0 or pos >= len(dates):
            continue                                           # event outside our price history
        if kind == "cash":
            base = s.iloc[pos - 1]
            f = 1 - val / base if base > 0 else 1.0
        else:
            f = 1 / val if val > 0 else 1.0
        if 0 < f <= 10:
            factor.iloc[:pos] *= f
    return s * factor

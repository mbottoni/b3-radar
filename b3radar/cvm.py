"""CVM open data: company register, tickers, and the financial statements we use.

Sources (dados.cvm.gov.br, CIA_ABERTA): ``cad_cia_aberta.csv`` (register),
FCA ``valor_mobiliario`` (trading codes), DFP (annual) and ITR (quarterly)
statements. All CVM files are ';'-separated latin-1.

Only standard (non-financial) account codes are extracted; banks and
insurers use a different chart of accounts and are screened out by sector.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .fetch import download, download_zip

BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA"

INCOME = {"3.01": "revenue", "3.03": "gross_profit", "3.05": "ebit", "3.11": "net_income"}
ASSETS = {"1": "total_assets", "1.01.01": "cash", "1.01.02": "short_investments"}
LIABILITIES = {"2.01.04": "st_debt", "2.02.01": "lt_debt", "2.03": "equity"}
FIELDS = (list(INCOME.values()) + [f"{v}_prev" for v in INCOME.values()]
          + list(ASSETS.values()) + list(LIABILITIES.values())
          + ["shares_on", "shares_pn", "treasury_on", "treasury_pn"])
FILING_COLUMNS = ["cnpj", "cd_cvm", "kind", "dt_refer", "versao", "dt_receb", "basis", *FIELDS]


def fetch_register(cache: Path) -> Path:
    return download(f"{BASE}/CAD/DADOS/cad_cia_aberta.csv", cache / "cad_cia_aberta.csv")


def fetch_doc(kind: str, year: int, cache: Path) -> Path | None:
    k = kind.lower()
    return download_zip(f"{BASE}/DOC/{kind}/DADOS/{k}_cia_aberta_{year}.zip", cache / f"{k}_cia_aberta_{year}.zip")


def _csv(src, **kw) -> pd.DataFrame:
    return pd.read_csv(src, sep=";", encoding="latin-1", dtype=str, keep_default_na=False, **kw)


def _member(z: zipfile.ZipFile, suffix: str):
    names = [n for n in z.namelist() if n.endswith(suffix)]
    return z.open(names[0]) if names else None


# --------------------------------------------------------------- register

def companies(cad_path: Path) -> pd.DataFrame:
    df = _csv(cad_path, usecols=["CNPJ_CIA", "DENOM_SOCIAL", "DENOM_COMERC", "SIT", "DT_INI_SIT", "CD_CVM",
                                 "SETOR_ATIV", "SIT_EMISSOR"])
    # A CNPJ can appear more than once (old cancelled registrations): keep
    # the active one, else the most recent.
    df["_active"] = df.SIT == "ATIVO"
    df = df.sort_values(["CNPJ_CIA", "_active", "DT_INI_SIT"]).drop_duplicates("CNPJ_CIA", keep="last")
    out = pd.DataFrame({
        "cnpj": df.CNPJ_CIA, "cd_cvm": df.CD_CVM.str.lstrip("0"),
        "name": df.DENOM_COMERC.where(df.DENOM_COMERC != "", df.DENOM_SOCIAL),
        "sector": df.SETOR_ATIV, "situation": df.SIT, "issuer_status": df.SIT_EMISSOR,
    })
    return out.sort_values("cnpj").reset_index(drop=True)


def tickers(fca_zip: Path) -> pd.DataFrame:
    """Trading codes per company from the latest FCA of each company."""
    with zipfile.ZipFile(fca_zip) as z:
        df = _csv(_member(z, "_valor_mobiliario_" + fca_zip.stem.split("_")[-1] + ".csv"))
    df = df[(df.Mercado == "Bolsa") & (df.Codigo_Negociacao.str.strip() != "")]
    df["Versao"] = df.Versao.astype(int)
    latest = df.groupby("CNPJ_Companhia")[["Data_Referencia", "Versao"]].max().reset_index()
    df = df.merge(latest, on=["CNPJ_Companhia", "Data_Referencia", "Versao"])
    kind = df.Valor_Mobiliario.map({"Ações Ordinárias": "ON", "Ações Preferenciais": "PN", "Units": "UNIT"})
    out = pd.DataFrame({"cnpj": df.CNPJ_Companhia, "ticker": df.Codigo_Negociacao.str.strip().str.upper(),
                        "security": kind.fillna(df.Valor_Mobiliario)})
    return out.drop_duplicates(["cnpj", "ticker"]).sort_values(["cnpj", "ticker"]).reset_index(drop=True)


# ------------------------------------------------------------- statements

def _scaled(df: pd.DataFrame) -> pd.Series:
    v = pd.to_numeric(df.VL_CONTA, errors="coerce")
    return v * np.where(df.ESCALA_MOEDA == "MIL", 1000.0, 1.0)


def _extract(z: zipfile.ZipFile, kind: str, year: int, basis: str) -> pd.DataFrame:
    """One row per filing (cnpj, dt_refer, versao) with the selected accounts."""
    k = kind.lower()
    parts = []
    for stmt, accounts in (("DRE", INCOME), ("BPA", ASSETS), ("BPP", LIABILITIES)):
        f = _member(z, f"_{stmt}_{basis}_{year}.csv")
        if f is None:
            continue
        df = _csv(io.TextIOWrapper(f, encoding="latin-1"),
                  usecols=lambda c: c in {"CNPJ_CIA", "DT_REFER", "VERSAO", "CD_CVM", "ORDEM_EXERC", "DT_INI_EXERC",
                                          "DT_FIM_EXERC", "CD_CONTA", "VL_CONTA", "ESCALA_MOEDA"})
        df = df[df.CD_CONTA.isin(accounts.keys())].copy()
        df["value"] = _scaled(df)
        df["field"] = df.CD_CONTA.map(accounts)
        if stmt == "DRE":
            # Year-to-date rows: the earliest period start within each filing.
            first = df.groupby(["CNPJ_CIA", "DT_REFER", "VERSAO", "ORDEM_EXERC", "CD_CONTA"]).DT_INI_EXERC.transform("min")
            df = df[df.DT_INI_EXERC == first]
            df.loc[df.ORDEM_EXERC != "ÚLTIMO", "field"] = df.field + "_prev"
        else:
            df = df[df.ORDEM_EXERC == "ÚLTIMO"]
        parts.append(df[["CNPJ_CIA", "DT_REFER", "VERSAO", "CD_CVM", "field", "value"]])
    if not parts:
        return pd.DataFrame()
    long = pd.concat(parts)
    wide = long.pivot_table(index=["CNPJ_CIA", "DT_REFER", "VERSAO", "CD_CVM"], columns="field", values="value",
                            aggfunc="first").reset_index()
    wide["basis"] = basis
    return wide


def filings(kind: str, zip_path: Path) -> pd.DataFrame:
    """Every filing of one DFP/ITR year file, latest version, consolidated
    statements when the company files them, individual otherwise."""
    year = int(zip_path.stem.split("_")[-1])
    k = kind.lower()
    with zipfile.ZipFile(zip_path) as z:
        idx = _csv(_member(z, f"{k}_cia_aberta_{year}.csv"), usecols=["CNPJ_CIA", "DT_REFER", "VERSAO", "CD_CVM", "DT_RECEB"])
        con, ind = _extract(z, kind, year, "con"), _extract(z, kind, year, "ind")
        cap = _csv(_member(z, f"_composicao_capital_{year}.csv"))
    key = ["CNPJ_CIA", "DT_REFER", "VERSAO"]
    if not ind.empty and not con.empty:
        ind = ind.merge(con[key], on=key, how="left", indicator=True)
        ind = ind[ind._merge == "left_only"].drop(columns="_merge")
    st = pd.concat([x for x in (con, ind) if not x.empty], ignore_index=True)
    num = lambda s: pd.to_numeric(s, errors="coerce")  # noqa: E731
    # Raw counts, as filed. Many companies file these in thousands (the file
    # has no unit column) and some mix units within a row; screen.shares()
    # resolves the scale against B3's own share count.
    cap = pd.DataFrame({
        "CNPJ_CIA": cap.CNPJ_CIA, "DT_REFER": cap.DT_REFER, "VERSAO": cap.VERSAO,
        "shares_on": num(cap.QT_ACAO_ORDIN_CAP_INTEGR), "shares_pn": num(cap.QT_ACAO_PREF_CAP_INTEGR),
        "treasury_on": num(cap.QT_ACAO_ORDIN_TESOURO), "treasury_pn": num(cap.QT_ACAO_PREF_TESOURO),
    })
    df = st.merge(cap, on=key, how="left").merge(idx.drop(columns="CD_CVM"), on=key, how="left")
    df["VERSAO"] = df.VERSAO.astype(int)
    df = df.sort_values("VERSAO").drop_duplicates(["CNPJ_CIA", "DT_REFER"], keep="last")
    out = df.rename(columns={"CNPJ_CIA": "cnpj", "DT_REFER": "dt_refer", "VERSAO": "versao",
                             "CD_CVM": "cd_cvm", "DT_RECEB": "dt_receb"})
    out["cd_cvm"] = out.cd_cvm.str.lstrip("0")
    out["kind"] = kind
    for c in FIELDS:
        if c not in out:
            out[c] = np.nan
    return out[FILING_COLUMNS].sort_values(["cnpj", "dt_refer"]).reset_index(drop=True)


def store_filings(new: pd.DataFrame, data_dir: Path) -> None:
    """Merge into data/cvm/filings.csv, replacing the (kind, year) blocks rebuilt."""
    path = data_dir / "cvm" / "filings.csv"
    if path.exists() and not new.empty:
        old = pd.read_csv(path, dtype={"cnpj": str, "cd_cvm": str, "kind": str, "dt_refer": str, "dt_receb": str,
                                       "basis": str})
        rebuilt = set(zip(new.kind, new.dt_refer.str[:4]))
        old = old[[(k, d[:4]) not in rebuilt for k, d in zip(old.kind, old.dt_refer)]]
        new = pd.concat([old, new], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    new.sort_values(["cnpj", "kind", "dt_refer"]).to_csv(path, index=False, lineterminator="\n", float_format="%.0f")

"""CVM open data: company register, tickers, and the financial statements we use.

Sources (dados.cvm.gov.br, CIA_ABERTA): ``cad_cia_aberta.csv`` (register),
FCA ``valor_mobiliario`` (trading codes), DFP (annual) and ITR (quarterly)
statements. All CVM files are ';'-separated latin-1.

``filings`` extracts the standard (non-financial) account codes; banks and
insurers use a different chart of accounts and are screened out by sector.
``financial_filings`` finds their net income and equity by their place in
the statement, for the financials screen (``financials.py``).
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
    df = df.sort_values(["CNPJ_CIA", "_active", "DT_INI_SIT", "CD_CVM"], kind="stable").drop_duplicates("CNPJ_CIA", keep="last")
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
        # Share capital is in DFP/ITR files only from 2020; earlier years
        # take it from the FRE capital timeline (capital_history below).
        member = _member(z, f"_composicao_capital_{year}.csv")
        cap = _csv(member) if member is not None else pd.DataFrame(columns=[
            "CNPJ_CIA", "DT_REFER", "VERSAO", "QT_ACAO_ORDIN_CAP_INTEGR", "QT_ACAO_PREF_CAP_INTEGR",
            "QT_ACAO_ORDIN_TESOURO", "QT_ACAO_PREF_TESOURO"])
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
    df = df.sort_values(["VERSAO", "DT_RECEB"], kind="stable").drop_duplicates(["CNPJ_CIA", "DT_REFER"], keep="last")
    out = df.rename(columns={"CNPJ_CIA": "cnpj", "DT_REFER": "dt_refer", "VERSAO": "versao",
                             "CD_CVM": "cd_cvm", "DT_RECEB": "dt_receb"})
    out["cd_cvm"] = out.cd_cvm.str.lstrip("0")
    out["kind"] = kind
    for c in FIELDS:
        if c not in out:
            out[c] = np.nan
    return out[FILING_COLUMNS].sort_values(["cnpj", "dt_refer"]).reset_index(drop=True)


def store_filings(new: pd.DataFrame, data_dir: Path, name: str = "filings.csv",
                  order: tuple[str, ...] = ("cnpj", "kind", "dt_refer")) -> None:
    """Merge into data/cvm/filings.csv, replacing the (kind, year) blocks rebuilt.
    A file with nothing in it (this year's DFP for the financials) changes nothing."""
    path = data_dir / "cvm" / name
    if new.empty and path.exists():
        return
    if path.exists():
        old = pd.read_csv(path, dtype={"cnpj": str, "cd_cvm": str, "kind": str, "dt_refer": str, "dt_receb": str,
                                       "basis": str})
        rebuilt = set(zip(new.kind, new.dt_refer.str[:4]))
        old = old[[(k, d[:4]) not in rebuilt for k, d in zip(old.kind, old.dt_refer)]]
        new = pd.concat([old, new], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    new.sort_values(list(order)).to_csv(path, index=False, lineterminator="\n", float_format="%.0f")


# ------------------------------------------------- financial statements

# Banks, insurers and their holdings file other charts of accounts, and the
# codes differ between them: net income is 3.09 (Itaú, and Banco do Brasil
# until 2019), 3.11 (BB since 2020, Itaúsa, Porto Seguro) or 3.13 (BB
# Seguridade, IRB, and most banks' individual statements); equity is 2.03
# (insurers, holdings), 2.05, 2.07 or 2.08 (banks), while a bank's
# consolidated 2.03 is a liability (Itaú: financial liabilities at
# amortized cost). What does not
# move, in every financial company's DFP and ITR since 2010: net income is
# the last top-level income line before 3.99 (earnings per share), named
# "Lucro/Prejuízo ... do Período"; equity is the top-level liability line
# named "Patrimônio Líquido". Both are found that way here, with the
# parent's share: the net income line's child "Atribuído a Sócios da
# Empresa Controladora", and equity less its child "... Não Controladores".
FIN_FIELDS = ["net_income", "net_income_parent", "net_income_prev", "net_income_parent_prev", "equity", "equity_parent"]
FIN_COLUMNS = ["cnpj", "cd_cvm", "kind", "dt_refer", "versao", "dt_receb", "basis", *FIN_FIELDS]


def _level(code: pd.Series) -> pd.Series:
    return code.str.count(r"\.")


def _fin_extract(z: zipfile.ZipFile, year: int, basis: str, cnpjs: set | None) -> pd.DataFrame:
    """Net income (year to date, this year and the same period a year
    before) and equity of each filing in one basis (con/ind)."""
    cols = {"CNPJ_CIA", "DT_REFER", "VERSAO", "ORDEM_EXERC", "DT_INI_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA",
            "ESCALA_MOEDA"}
    key = ["CNPJ_CIA", "DT_REFER", "VERSAO"]
    out = []
    for stmt in ("DRE", "BPP"):
        f = _member(z, f"_{stmt}_{basis}_{year}.csv")
        if f is None:
            return pd.DataFrame()
        df = _csv(io.TextIOWrapper(f, encoding="latin-1"), usecols=lambda c: c in cols)
        if cnpjs is not None:
            df = df[df.CNPJ_CIA.isin(cnpjs)]
        df = df[_level(df.CD_CONTA) <= 2].copy()
        df["value"] = _scaled(df)
        out.append(df)
    dre, bpp = out
    # Income: the year-to-date rows (earliest period start in each filing).
    dre = dre[dre.DT_INI_EXERC == dre.groupby(key + ["ORDEM_EXERC", "CD_CONTA"]).DT_INI_EXERC.transform("min")]
    top = dre[(_level(dre.CD_CONTA) == 1) & (dre.CD_CONTA != "3.99")]
    top = top.assign(n=top.CD_CONTA.str.split(".").str[1].astype(int)).sort_values("n", kind="stable")
    ni = top.groupby(key + ["ORDEM_EXERC"]).tail(1)
    ni = ni[ni.DS_CONTA.str.contains("lucro|preju", case=False)]
    sub = dre[_level(dre.CD_CONTA) == 2].assign(parent=lambda d: d.CD_CONTA.str.rsplit(".", n=1).str[0])
    nci_line = sub.DS_CONTA.str.contains(r"(?i)n[ãa]o controlador")
    for name, mask in (("parent_value", ~nci_line & sub.DS_CONTA.str.contains("controladora", case=False)),
                       ("nci_value", nci_line)):
        part = sub[mask].drop_duplicates(key + ["ORDEM_EXERC", "parent"])
        ni = ni.merge(part[key + ["ORDEM_EXERC", "parent", "value"]].rename(columns={"parent": "CD_CONTA", "value": name}),
                      on=key + ["ORDEM_EXERC", "CD_CONTA"], how="left")
    # The split is used only when its two lines add up to the total: IRB
    # files zeros in both. Individual statements are the parent's own.
    adds_up = (ni.parent_value + ni.nci_value.fillna(0) - ni.value).abs() <= np.maximum(0.01 * ni.value.abs(), 1e3)
    ni["parent_value"] = ni.parent_value.where(adds_up, ni.value)
    cur, prev = ni[ni.ORDEM_EXERC == "ÚLTIMO"], ni[ni.ORDEM_EXERC != "ÚLTIMO"]
    inc = cur[key + ["value", "parent_value"]].rename(columns={"value": "net_income", "parent_value": "net_income_parent"}).merge(
        prev[key + ["value", "parent_value"]].rename(columns={"value": "net_income_prev", "parent_value": "net_income_parent_prev"}),
        on=key, how="left")
    # Balance: the top-level "Patrimônio Líquido" line, less non-controlling interests.
    bpp = bpp[bpp.ORDEM_EXERC == "ÚLTIMO"]
    eq = bpp[(_level(bpp.CD_CONTA) == 1) & bpp.DS_CONTA.str.match(r"(?i)patrim[oô]nio l[ií]quido")]
    eq = eq.drop_duplicates(key)
    nci = bpp[(_level(bpp.CD_CONTA) == 2) & bpp.DS_CONTA.str.contains(r"(?i)n[ãa]o controlador")]
    nci = nci.assign(parent=nci.CD_CONTA.str.rsplit(".", n=1).str[0])
    eq = eq.merge(nci[key + ["parent", "value"]].rename(columns={"parent": "CD_CONTA", "value": "nci"}).drop_duplicates(key),
                  on=key + ["CD_CONTA"], how="left")
    # Zero equity is a blank (Santander's individual annual reports of 2020 and 2021), not a bank with no capital.
    total = eq.value.where(eq.value != 0)
    eq = pd.DataFrame({**{k: eq[k] for k in key}, "equity": total, "equity_parent": total - eq.nci.fillna(0.0)})
    df = inc.merge(eq, on=key, how="outer")
    df["basis"] = basis
    return df


def financial_filings(kind: str, zip_path: Path, cnpjs: set | None = None) -> pd.DataFrame:
    """Net income and equity of the financial companies (``cnpjs``) in one
    DFP/ITR year file, latest version of each filing. Unlike ``filings``,
    both bases are kept, one row each: banks' individual statements follow
    the Banco Central's accounting and their consolidated ones IFRS, so a
    trailing twelve months must not mix them (ABC Brasil files
    consolidated statements until 2023, individual ones after)."""
    year = int(zip_path.stem.split("_")[-1])
    k = kind.lower()
    with zipfile.ZipFile(zip_path) as z:
        idx = _csv(_member(z, f"{k}_cia_aberta_{year}.csv"), usecols=["CNPJ_CIA", "DT_REFER", "VERSAO", "CD_CVM", "DT_RECEB"])
        parts = [x for x in (_fin_extract(z, year, b, cnpjs) for b in ("con", "ind")) if not x.empty]
    if not parts:
        return pd.DataFrame(columns=FIN_COLUMNS)
    key = ["CNPJ_CIA", "DT_REFER", "VERSAO"]
    df = pd.concat(parts, ignore_index=True).merge(idx, on=key, how="left")
    df["VERSAO"] = df.VERSAO.astype(int)
    df = df.sort_values(["VERSAO", "DT_RECEB"], kind="stable").drop_duplicates(["CNPJ_CIA", "DT_REFER", "basis"], keep="last")
    out = df.rename(columns={"CNPJ_CIA": "cnpj", "DT_REFER": "dt_refer", "VERSAO": "versao", "CD_CVM": "cd_cvm",
                             "DT_RECEB": "dt_receb"})
    out["cd_cvm"] = out.cd_cvm.fillna("").str.lstrip("0")
    out["kind"] = kind
    return out[FIN_COLUMNS].sort_values(["cnpj", "dt_refer", "basis"]).reset_index(drop=True)


def store_financial_filings(new: pd.DataFrame, data_dir: Path) -> None:
    """Merge into data/cvm/financials.csv, replacing the (kind, year) blocks rebuilt."""
    store_filings(new, data_dir, "financials.csv", ("cnpj", "kind", "dt_refer", "basis"))


# -------------------------------------------------------- capital timeline

def capital_history(fre_zip: Path) -> pd.DataFrame:
    """Paid-in share counts per company with the date each was approved,
    from one year's Reference Forms (FRE): the whole capital history each
    company reported, latest form version."""
    year = fre_zip.stem.split("_")[-1]
    with zipfile.ZipFile(fre_zip) as z:
        df = _csv(_member(z, f"_capital_social_{year}.csv"))
    df = df[df.Tipo_Capital == "Capital Integralizado"]
    df["Versao"] = df.Versao.astype(int)
    df = df[df.Versao == df.groupby("CNPJ_Companhia").Versao.transform("max")]
    num = lambda s: pd.to_numeric(s, errors="coerce")  # noqa: E731
    out = pd.DataFrame({"cnpj": df.CNPJ_Companhia, "date": df.Data_Autorizacao_Aprovacao,
                        "shares_on": num(df.Quantidade_Acoes_Ordinarias), "shares_pn": num(df.Quantidade_Acoes_Preferenciais),
                        "form": year})
    out = out[(out.date != "") & (out.shares_on.fillna(0) + out.shares_pn.fillna(0) > 0)]
    return out.drop_duplicates(["cnpj", "date"], keep="last")


FLOAT_MIN_PCT = 1.0   # a class with under 1% in free float gives too imprecise a total


def share_counts(fre_zip: Path) -> pd.DataFrame:
    """Shares per class from one year's Reference Forms: shares in free
    float divided by the free float's percentage of the class (item 15.3).
    ``date``: the day CVM received the version they come from (when it was
    public); ``meeting``: the shareholders' meeting the position refers to.
    Most forms give the count as of their receipt, some (Sabesp, received
    after its 2013 3:1 split) still the one of the meeting: see
    ``screen.date_share_counts``.

    Unlike the capital timeline, each count carries its own date, so a
    later form cannot rewrite an earlier count: Odontoprev's 2021 form lists
    its 2010 capital entry with 2021's share count (after a 3:1 split in
    2012), while its 2011 form gives the 2011 count. A class with no free
    float (or under ``FLOAT_MIN_PCT``) has no count here."""
    year = fre_zip.stem.split("_")[-1]
    with zipfile.ZipFile(fre_zip) as z:
        member = _member(z, f"_distribuicao_capital_{year}.csv")
        if member is None:
            return pd.DataFrame(columns=["cnpj", "date", "meeting", "shares_on", "shares_pn", "form"])
        df = _csv(member)
        received = _csv(_member(z, f"fre_cia_aberta_{year}.csv"), usecols=["ID_DOC", "DT_RECEB"])
    # The detail tables keep only each company's latest version of the form,
    # and its counts are as of that version: date them by its receipt.
    df = df.merge(received.drop_duplicates("ID_DOC"), left_on="ID_Documento", right_on="ID_DOC", how="left")
    num = lambda s: pd.to_numeric(s, errors="coerce")  # noqa: E731

    def total(q, p):
        q, p = num(q), num(p)
        return (q / (p / 100)).where((q > 0) & (p >= FLOAT_MIN_PCT)).round()
    received = df.DT_RECEB.fillna("")
    meeting = df.Data_Ultima_Assembleia.fillna("")
    out = pd.DataFrame({"cnpj": df.CNPJ_Companhia, "date": received,
                        "meeting": meeting.where((meeting != "") & (meeting < received), received),
                        "shares_on": total(df.Quantidade_Acoes_Ordinarias_Circulacao, df.Percentual_Acoes_Ordinarias_Circulacao),
                        "shares_pn": total(df.Quantidade_Acoes_Preferenciais_Circulacao,
                                           df.Percentual_Acoes_Preferenciais_Circulacao),
                        "form": year})
    out = out[(out.date != "") & (out.shares_on.notna() | out.shares_pn.notna())]
    return out.drop_duplicates(["cnpj", "date"], keep="last")


def store_share_counts(new: pd.DataFrame, data_dir: Path) -> None:
    """Merge into data/cvm/shares_fre.csv; the same (company, meeting date)
    reported by two forms keeps the later form's figures."""
    path = data_dir / "cvm" / "shares_fre.csv"
    if path.exists():
        new = pd.concat([pd.read_csv(path, dtype={"cnpj": str, "date": str, "form": str}), new], ignore_index=True)
    new = new.sort_values(["cnpj", "date", "form"], kind="stable").drop_duplicates(["cnpj", "date"], keep="last")
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, index=False, lineterminator="\n", float_format="%.0f")


def store_capital(new: pd.DataFrame, data_dir: Path) -> None:
    """Merge into data/cvm/capital.csv; for the same (company, date) the
    most recent form wins (later forms correct earlier ones)."""
    path = data_dir / "cvm" / "capital.csv"
    if path.exists():
        new = pd.concat([pd.read_csv(path, dtype={"cnpj": str, "date": str, "form": str}), new], ignore_index=True)
    new = new.sort_values(["cnpj", "date", "form"]).drop_duplicates(["cnpj", "date"], keep="last")
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, index=False, lineterminator="\n", float_format="%.0f")


def merge_tickers(new: pd.DataFrame, data_dir: Path) -> None:
    """Union of trading codes across years, so delisted companies keep their
    mapping; the newest form wins for a code that moved."""
    path = data_dir / "cvm" / "tickers.csv"
    if path.exists():
        new = pd.concat([pd.read_csv(path, dtype=str, keep_default_na=False), new], ignore_index=True)
    new.drop_duplicates("ticker", keep="last").sort_values(["cnpj", "ticker"]).to_csv(
        path, index=False, lineterminator="\n")

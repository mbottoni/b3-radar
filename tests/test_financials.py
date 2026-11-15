"""The financials screen: banks, insurers and holdings ranked among themselves.
Each case here was met in CVM's filings; the docstrings say where."""

import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from b3radar import cvm, events, financials, screen

DRE_COLS = ["CNPJ_CIA", "DT_REFER", "VERSAO", "DENOM_CIA", "CD_CVM", "GRUPO_DFP", "MOEDA", "ESCALA_MOEDA", "ORDEM_EXERC",
            "DT_INI_EXERC", "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA", "ST_CONTA_FIXA"]


def _rows(cnpj, lines, prev=None, start="2025-01-01", end="2025-12-31"):
    """DRE/BPP rows for one filing: ``lines`` [(code, description, value)], and the prior year's values."""
    out = []
    for order, values in (("ÚLTIMO", lines), ("PENÚLTIMO", prev or [])):
        y = -1 if order == "PENÚLTIMO" else 0
        for code, desc, v in values:
            out.append([cnpj, end, "1", "X", "1", "", "REAL", "MIL", order, f"{int(start[:4]) + y}{start[4:]}",
                        f"{int(end[:4]) + y}{end[4:]}", code, desc, f"{v:.10f}", "S"])
    return out


def _zip(path, kind, year, dre, bpp, received):
    k = kind.lower()
    with zipfile.ZipFile(path, "w") as z:
        def put(name, rows, cols):
            buf = io.StringIO()
            pd.DataFrame(rows, columns=cols).to_csv(buf, sep=";", index=False)
            z.writestr(name, buf.getvalue().encode("latin-1"))
        put(f"{k}_cia_aberta_{year}.csv", [[c, f"{year}-12-31", "1", "1", d] for c, d in received.items()],
            ["CNPJ_CIA", "DT_REFER", "VERSAO", "CD_CVM", "DT_RECEB"])
        for basis in ("con", "ind"):
            put(f"{k}_cia_aberta_DRE_{basis}_{year}.csv", dre.get(basis, []), DRE_COLS)
            put(f"{k}_cia_aberta_BPP_{basis}_{year}.csv", bpp.get(basis, []), DRE_COLS)
    return path


def test_net_income_and_equity_are_found_by_their_place_not_their_code(tmp_path):
    """Itaú: net income at 3.09, equity at 2.08 (its 2.03 is a liability). BB Seguridade: net income at 3.13.
    IRB files zeros in both lines of the parent / minority split: the total is used. Santander's individual
    2020 and 2021 annual reports have equity 0: a blank, not a bank with no capital."""
    bank, insurer, irb = "60.872.504/0001-23", "17.344.597/0001-94", "33.376.989/0001-91"
    bank_dre = [("3.01", "Receitas da Intermediação Financeira", 387e6), ("3.08", "Resultado Líquido das Operações Descontinuadas", 0),
                ("3.09", "Lucro/Prejuízo Consolidado do Período", 45849e3),
                ("3.09.01", "Atribuído a Sócios da Empresa Controladora", 45000e3), ("3.09.02", "Atribuído a Sócios Não Controladores", 849e3),
                ("3.99", "Lucro por Ação - (R$ / Ação)", 4.2)]
    bank_bpp = [("2.03", "Passivos Financeiros ao Custo Amortizado", 2.35e9), ("2.08", "Patrimônio Líquido Consolidado", 215076e3),
                ("2.08.01", "Capital Social Realizado", 136910e3), ("2.08.09", "Participação dos Acionistas Não Controladores", 10575e3)]
    ins_dre = [("3.11", "Resultado Líquido das Operações Continuadas", 9017e3), ("3.13", "Lucro/Prejuízo Consolidado do Período", 9017e3),
               ("3.13.01", "Atribuído a Sócios da Empresa Controladora", 9017e3), ("3.13.02", "Atribuído a Sócios Não Controladores", 0)]
    irb_dre = [("3.13", "Lucro/Prejuízo Consolidado do Período", 390e3), ("3.13.01", "Atribuído a Sócios da Empresa Controladora", 0),
               ("3.13.02", "Atribuído a Sócios Não Controladores", 0)]
    eq = lambda v: [("2.03", "Patrimônio Líquido Consolidado", v)]  # noqa: E731
    dre = {"con": _rows(bank, bank_dre, prev=[("3.09", "Lucro/Prejuízo Consolidado do Período", 41e6)]) + _rows(insurer, ins_dre)
           + _rows(irb, irb_dre),
           "ind": _rows(bank, [("3.13", "Lucro/Prejuízo do Período", 44e6), ("3.99", "Lucro por Ação", 4.1)])}
    bpp = {"con": _rows(bank, bank_bpp) + _rows(insurer, eq(10384e3)) + _rows(irb, eq(5e6)),
           "ind": _rows(bank, [("2.05", "Patrimônio Líquido", 0)])}
    z = _zip(tmp_path / "dfp_cia_aberta_2025.zip", "DFP", 2025, dre, bpp, {bank: "2026-02-05", insurer: "2026-02-10", irb: "2026-03-20"})
    f = cvm.financial_filings("DFP", z).set_index(["cnpj", "basis"])
    b = f.loc[(bank, "con")]
    assert b.net_income == 45849e6 and b.net_income_parent == 45000e6 and b.net_income_prev == 41e9
    assert b.equity == 215076e6 and b.equity_parent == 215076e6 - 10575e6
    assert f.loc[(bank, "ind")].net_income_parent == 44e9 and np.isnan(f.loc[(bank, "ind")].equity)
    assert f.loc[(insurer, "con")].net_income_parent == 9017e6 and f.loc[(insurer, "con")].equity == 10384e6
    assert f.loc[(irb, "con")].net_income_parent == 390e6                      # the split does not add up: the total
    assert f.loc[(bank, "con")].dt_receb == "2026-02-05"
    # Only the companies asked for, when a list is given.
    assert set(cvm.financial_filings("DFP", z, {insurer}).cnpj) == {insurer}


def test_an_empty_extraction_leaves_the_stored_filings_alone(tmp_path):
    row = {c: 1.0 for c in cvm.FIN_FIELDS} | {"cnpj": "C", "cd_cvm": "1", "kind": "ITR", "dt_refer": "2025-09-30",
                                              "versao": 1, "dt_receb": "2025-11-01", "basis": "con"}
    cvm.store_financial_filings(pd.DataFrame([row])[cvm.FIN_COLUMNS], tmp_path)
    cvm.store_financial_filings(pd.DataFrame(columns=cvm.FIN_COLUMNS), tmp_path)   # this year's DFP: nothing yet
    assert len(pd.read_csv(tmp_path / "cvm" / "financials.csv")) == 1


def fin(kind, dt_refer, dt_receb, basis="con", ni=10.0, prev=8.0, equity=100.0, cnpj="B"):
    return {"cnpj": cnpj, "kind": kind, "dt_refer": dt_refer, "dt_receb": dt_receb, "basis": basis, "net_income": ni,
            "net_income_parent": ni, "net_income_prev": prev, "net_income_parent_prev": prev, "equity": equity,
            "equity_parent": equity}


def test_ttm_never_mixes_consolidated_and_individual_statements():
    """ABC Brasil files consolidated statements until 2023 and individual ones after: the TTM of 2024 is
    individual annual + individual YTD - individual prior YTD, never a consolidated annual + individual YTD."""
    f = pd.DataFrame([fin("DFP", "2023-12-31", "2024-02-01", "con", ni=100.0), fin("DFP", "2023-12-31", "2024-02-01", "ind", ni=90.0),
                      fin("ITR", "2024-06-30", "2024-08-01", "ind", ni=60.0, prev=40.0, equity=120.0)])
    t = financials.ttm(f, "2024-09-01").loc["B"]
    assert t.basis == "ind" and t.net_income == 110.0 and t.equity == 120.0   # 90 + 60 - 40
    assert financials.ttm(f, "2024-03-01").loc["B"].basis == "con"           # both annual only: consolidated
    assert financials.ttm(f, "2024-01-01").empty


def test_cleaning_fixes_a_filing_in_the_wrong_unit_and_a_missing_prior_year():
    """Pine's June 2024 ITR says units but holds thousands. In 2025 the banks' individual ITRs give last year's
    figure as 0 (CMN Resolution 4,966 did not restate comparatives): it comes from the prior year's own report."""
    rows = [fin("ITR", "2024-03-31", "2024-05-01", ni=50e6, equity=1.0e9), fin("ITR", "2024-06-30", "2024-08-01", ni=100e3, prev=60e3, equity=1.1e6),
            fin("ITR", "2025-06-30", "2025-08-01", ni=120e6, prev=0.0, equity=1.2e9)]
    c = financials.clean(pd.DataFrame(rows)).set_index("dt_refer")
    assert c.loc["2024-06-30", "equity"] == pytest.approx(1.1e9) and c.loc["2024-06-30", "net_income"] == pytest.approx(100e6)
    assert c.loc["2025-06-30", "net_income_prev"] == pytest.approx(100e6)   # from June 2024's own (fixed) report
    assert c.loc["2024-03-31", "equity"] == 1.0e9                           # the first filing has nothing to compare with


def snapshot(n=6, financial=True):
    sector = "Bancos" if financial else "Energia Elétrica"
    return pd.DataFrame({"ticker": [f"B{i}4" for i in range(n)], "company": "", "sector": sector, "cnpj": list("ABCDEF")[:n],
                         "tickers": "", "price": 10.0, "market_cap": 1000.0, "market_cap_b3": 1000.0, "liquidity": 1e8,
                         "sessions": 500, "bdi": "02", "situation": "ATIVO", "issuer_status": screen.OPERATING,
                         "momentum": np.linspace(-0.2, 0.3, n), "dividend_yield": 0.05, "shares_source": "cvm"})


def test_scores_are_percentiles_among_the_financials_only():
    snap = pd.concat([snapshot(), snapshot(financial=False).assign(cnpj=list("UVWXYZ"), ticker=[f"E{i}3" for i in range(6)])])
    before = snap.copy()
    rows = [fin("DFP", "2025-12-31", "2026-02-01", ni=10.0 * (i + 1), equity=100.0 + 50 * i, cnpj=c) for i, c in enumerate("ABCDEF")]
    f = pd.DataFrame(rows)
    out = financials.compute(snap, f, financials.ttm_history(f), "2026-05-04").set_index("cnpj")
    assert set(out.index) == set("ABCDEF")                         # only financial sectors
    assert out.score.notna().all() and sorted(out["rank"]) == [1, 2, 3, 4, 5, 6]
    assert out.book_to_market.idxmax() == "F" and out.p_book_to_market["F"] == 100
    assert out.roe["A"] == pytest.approx(0.1) and out.pb["A"] == pytest.approx(10.0)
    pd.testing.assert_frame_equal(snap, before)                    # the main snapshot is left as it was


def test_a_market_cap_off_by_a_thousand_takes_b3s_count():
    """Itaú files 4,958,290 (thousand) ON shares; read as units in the backtest, its market cap came out
    R$ 0.2 billion instead of R$ 230 billion."""
    snap = snapshot().assign(market_cap=[0.23, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0], market_cap_b3=[230.0, 1000.0, 1000.0, 1000.0, 1000.0, 2500.0])
    f = pd.DataFrame([fin("DFP", "2025-12-31", "2026-02-01", cnpj=c) for c in "ABCDEF"])
    out = financials.compute(snap, f, financials.ttm_history(f), "2026-05-04").set_index("cnpj")
    assert out.market_cap["A"] == 230.0 and out.shares_source["A"] == "b3"
    assert out.market_cap["F"] == 1000.0                           # 2.5x apart: issuance or a missed bonus, the filing stands


def test_roe_stability_needs_four_readings_and_lower_is_better():
    rows = []
    for c, swing in (("A", 0.0), ("B", 5.0), ("C", 0.0)):
        for i, q in enumerate(("2025-03-31", "2025-06-30", "2025-09-30")):
            rows.append(fin("ITR", q, f"{q[:4]}-{int(q[5:7]) + 1:02d}-28", ni=5.0 + swing * (i % 2), prev=5.0, cnpj=c))
        rows.append(fin("DFP", "2024-12-31", "2025-02-01", ni=20.0, cnpj=c))
    rows = [r for r in rows if not (r["cnpj"] == "C" and r["dt_refer"] > "2025-03-31")]    # C: 2 readings only
    f = pd.DataFrame(rows)
    s = financials.stability(financials.ttm_history(f), pd.Series({"A": "con", "B": "con", "C": "con"}), "2026-01-01")
    assert s.roe_stability["A"] == pytest.approx(0.0) and s.roe_stability["B"] > 0
    assert np.isnan(s.roe_stability["C"]) and s.roe_readings["C"] == 2


def test_the_financials_screen_has_its_own_fingerprint(monkeypatch):
    main = screen.rules_hash()
    before = financials.rules_hash()
    monkeypatch.setitem(financials.WEIGHTS, "quality", 0.5)
    assert financials.rules_hash() != before and screen.rules_hash() == main


def test_a_corrected_event_completes_itaus_2011_reverse_split_and_split(tmp_path):
    """B3 lists Itaú's 100:1 reverse split of 2011-10-31 but not the 1:100 split of the same day: its
    price did not move, yet the adjusted series showed a 99% fall."""
    ev = tmp_path / "events"
    ev.mkdir()
    pd.DataFrame([["ITUB", "BRITUBACNPR1", "GRUPAMENTO", 0.01, "2011-10-31", "2011-04-25"]], columns=events.STOCK_COLUMNS) \
        .to_csv(ev / "stock.csv", index=False)
    pd.DataFrame([["ITUB", "BRITUBACNPR1", "DESDOBRAMENTO (CORRIGIDO)", 9900.0, "2011-10-31", "2011-04-25"]],
                 columns=events.STOCK_COLUMNS).to_csv(ev / "stock_fixes.csv", index=False)
    _, stock = events.load(tmp_path)
    assert np.prod(stock.mult) == pytest.approx(1.0)
    px = pd.DataFrame({"date": ["2011-10-31", "2011-11-01"], "close": [32.73, 32.13]})
    adj = events.adjusted_close(px, "BRITUBACNPR1", pd.DataFrame(columns=["isin", "label", "last_date_prior", "rate"]), stock)
    assert adj.iloc[0] == pytest.approx(32.73)

"""Unit tests for the pieces that turn raw files into numbers. Each edge case
here was met in the real data; the docstrings say where."""

import numpy as np
import pandas as pd
import pytest

from b3radar import cotahist, events, screen


# ---------------------------------------------------------------- COTAHIST

def record(date="20261105", bdi="02", ticker="PETR4", tpmerc="010", spec="PN      N2", close=4595, volume=100000,
           fatcot=1, isin="BRPETRACNPR6", trades=10):
    r = [" "] * 245
    def put(a, b, v, num=False):
        s = str(v).rjust(b - a + 1, "0") if num else str(v).ljust(b - a + 1)
        r[a - 1:b] = list(s[: b - a + 1])
    put(1, 2, "01"); put(3, 10, date); put(11, 12, bdi); put(13, 24, ticker); put(25, 27, tpmerc)
    put(40, 49, spec)
    for a, b in ((57, 69), (70, 82), (83, 95), (109, 121)):
        put(a, b, close, num=True)
    put(148, 152, trades, num=True); put(171, 188, volume, num=True); put(211, 217, fatcot, num=True)
    put(231, 242, isin)
    return "".join(r)


def test_cotahist_keeps_stocks_and_benchmark_only():
    lines = [
        "00COTAHIST.2026BOVESPA 20261105".ljust(245),
        record(),                                                        # PN share
        record(ticker="TAEE11", spec="UNT     N2", isin="BRTAEECDAM10"), # unit
        record(ticker="BOVA11", bdi="14", spec="CI  ATZ", isin="BRBOVACTF003"),
        record(ticker="PETR4F", tpmerc="020"),                           # odd lot: dropped
        record(ticker="AAPL34", bdi="34", spec="DRN"),                   # BDR: dropped
        record(ticker="XPML11", bdi="12", spec="CI"),                    # FII: dropped
        record(ticker="OLD3", close=123400, fatcot=1000),                # quoted per 1000 shares
    ]
    df = cotahist.parse_lines(lines).set_index("ticker")
    assert sorted(df.index) == ["BOVA11", "OLD3", "PETR4", "TAEE11"]
    assert df.loc["PETR4", "close"] == 45.95 and df.loc["PETR4", "date"] == "2026-11-05"
    assert df.loc["TAEE11", "kind"] == "UNIT" and df.loc["BOVA11", "kind"] == "ETF"
    assert df.loc["OLD3", "close"] == pytest.approx(1.234)


def test_store_replaces_a_date_and_is_deterministic(tmp_path):
    a = cotahist.parse_lines([record(), record(ticker="VALE3", spec="ON NM", isin="BRVALEACNOR0")])
    cotahist.store(a, tmp_path)
    b = cotahist.parse_lines([record(close=5000)])
    cotahist.store(b, tmp_path)
    df = cotahist.load(tmp_path)
    assert len(df) == 1 and df.close.iloc[0] == 50.0        # the date was replaced wholesale
    first = (tmp_path / "prices" / "2026-11.csv").read_bytes()
    cotahist.store(b, tmp_path)
    assert (tmp_path / "prices" / "2026-11.csv").read_bytes() == first


# ------------------------------------------------------------------ events

def test_share_multipliers_match_b3_semantics():
    # PETR 2008 1:2 split (100), MGLU 2020 1:4 (300), MGLU 2024 10:1 reverse (0.1), MGLU 2025 5% bonus (5)
    assert events.share_multiplier("DESDOBRAMENTO", 100) == 2
    assert events.share_multiplier("DESDOBRAMENTO", 300) == 4
    assert events.share_multiplier("GRUPAMENTO", 0.1) == 0.1
    assert events.share_multiplier("BONIFICACAO", 5) == pytest.approx(1.05)
    assert events.share_multiplier("CIS RED CAP", 100) == 1.0


def test_adjusted_close_removes_dividend_and_split_gaps():
    px = pd.DataFrame({"date": ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"],
                       "close": [10.0, 10.0, 9.0, 4.5]})
    cash = pd.DataFrame({"isin": ["X"], "rate": [1.0], "last_date_prior": ["2026-01-05"], "label": ["DIVIDENDO"]})
    stock = pd.DataFrame({"isin": ["X"], "mult": [2.0], "last_date_prior": ["2026-01-06"], "label": ["DESDOBRAMENTO"]})
    adj = events.adjusted_close(px, "X", cash, stock)
    # ex-dividend drop 10 -> 9 (R$1 paid) and the 1:2 split 9 -> 4.5 are not losses
    assert np.allclose(adj.pct_change().dropna(), [0.0, 0.0, 0.0])
    assert adj.iloc[-1] == 4.5                                   # latest price unchanged


def test_events_filed_under_an_old_isin_still_apply():
    # HAPV-style: 15:1 reverse split filed under the old ISIN, quotes continue under a new one
    px = pd.DataFrame({"date": ["2025-06-04", "2025-06-05", "2025-06-06"], "close": [2.70, 2.70, 40.5]})
    stock = pd.DataFrame({"isin": ["OLD"], "mult": [1 / 15], "last_date_prior": ["2025-06-05"], "label": ["GRUPAMENTO"]})
    cash = pd.DataFrame({"isin": ["OLD", "NEW"], "rate": [0.27, 0.27], "last_date_prior": ["2025-06-04"] * 2,
                         "label": ["DIVIDENDO"] * 2})            # the same payment on file twice
    adj = events.adjusted_close(px, {"OLD", "NEW"}, cash, stock)
    assert adj.pct_change().iloc[-1] == pytest.approx(0.0)       # the reverse split is no jump
    assert adj.iloc[0] / adj.iloc[1] == pytest.approx(0.9)       # one 10% dividend, not two


def test_missing_splits_are_inferred_from_b3_ex_markers():
    # MGLU3 2017: 8:1 bonus split, marked EB by B3, absent from B3's events service
    px = pd.DataFrame({"date": ["2017-09-01", "2017-09-04", "2017-09-05", "2017-09-08"], "ticker": "MGLU3",
                       "isin": "BRMGLUACNOR2", "kind": "ON", "open": [579.0, 566.0, 79.76, 86.26],
                       "close": [564.14, 621.79, 82.0, 78.92], "ex": ["", "", "EB", "EB"]})
    crash = px.assign(ticker="XXXX3", isin="X", close=[10.0, 10.0, 3.1, 3.0], open=[10.0, 10.0, 3.5, 3.0],
                      ex=["", "", "", ""])                      # a 70% fall with no marker: left alone
    none = pd.DataFrame(columns=["isin", "last_date_prior", "label"])
    inf = events.infer_stock_events(pd.concat([px, crash]), none)
    assert list(inf.issuer) == ["MGLU"] and inf.last_date_prior.iloc[0] == "2017-09-04"
    assert events.share_multiplier("DESDOBRAMENTO", inf.factor.iloc[0]) == 8
    known = pd.DataFrame({"isin": ["BRMGLUACNOR2"], "last_date_prior": ["2017-09-04"], "label": ["BONIFICACAO"]})
    assert events.infer_stock_events(px, known).empty           # already on file: nothing inferred


# ------------------------------------------------------------------ shares

@pytest.mark.parametrize("total,treasury,b3,expected,source", [
    (7_442_231_382, 0, 7_442_231_382, 7_442_231_382, "cvm"),     # PETR files units
    (1_198_563, 2_350, 1_198_563_531, 1_196_213_000, "cvm"),     # VBBR files thousands
    (122_578, 65_148, 122_578_152, 122_578_000, "cvm"),          # TEND: treasury in units -> ignored
    (1_954_343_520, 0, 195_434_352, 195_434_352, "b3"),          # LAVV: extra digit -> B3
    (137_324 * 4, 0, 549_296_404, 549_296_000, "cvm"),           # ORVR, already carried through a 1:4 split
    (57_000, 0, None, 57_000_000, "cvm"),                        # no B3 count, tiny -> thousands
])
def test_outstanding_resolves_units(total, treasury, b3, expected, source):
    n, src = screen.outstanding(total, treasury, b3)
    assert src == source and n == pytest.approx(expected)


# --------------------------------------------------------------------- TTM

def filing(kind, dt_refer, dt_receb, **v):
    base = {c: np.nan for c in ["revenue", "gross_profit", "ebit", "net_income", "revenue_prev", "gross_profit_prev",
                                "ebit_prev", "net_income_prev", "total_assets", "cash", "short_investments", "st_debt",
                                "lt_debt", "equity", "shares_on", "shares_pn", "treasury_on", "treasury_pn"]}
    return {"cnpj": "C", "kind": kind, "dt_refer": dt_refer, "dt_receb": dt_receb, **base, **v}


def test_ttm_is_annual_plus_ytd_minus_prior_ytd_and_point_in_time():
    f = pd.DataFrame([
        filing("DFP", "2025-12-31", "2026-03-05", ebit=100.0, equity=500.0),
        filing("ITR", "2026-06-30", "2026-08-06", ebit=70.0, ebit_prev=40.0, equity=520.0),
    ])
    before = screen.ttm(f, "2026-08-05").iloc[0]              # the ITR was not public yet
    assert before.ebit == 100.0 and before.equity == 500.0 and before.dt_refer == "2025-12-31"
    after = screen.ttm(f, "2026-08-06").iloc[0]
    assert after.ebit == 130.0 and after.equity == 520.0        # 100 + 70 - 40
    assert screen.ttm(f, "2026-03-04").empty                     # nothing filed yet


def test_ttm_refuses_a_quarter_not_following_the_annual():
    f = pd.DataFrame([filing("DFP", "2024-12-31", "2025-03-01", ebit=100.0),
                      filing("ITR", "2026-06-30", "2026-08-06", ebit=70.0, ebit_prev=40.0)])
    assert np.isnan(screen.ttm(f, "2026-09-01").iloc[0].ebit)


# ------------------------------------------------------------------ growth

def test_growth_is_point_in_time_and_uses_the_prior_year_of_the_first_report():
    rows = [filing("DFP", "2010-12-31", "2011-03-30", revenue=110.0, net_income=11.0,
                   revenue_prev=100.0, net_income_prev=10.0)]          # also states 2009
    for y, rev, ni in ((2011, 121.0, 12.0), (2012, 133.1, -5.0)):
        rows.append(filing("DFP", f"{y}-12-31", f"{y + 1}-03-30", revenue=rev, net_income=ni,
                           revenue_prev=np.nan, net_income_prev=np.nan))
    rows.append(filing("ITR", "2013-03-31", "2013-05-10", revenue=40.0, net_income=1.0,
                       revenue_prev=30.0, net_income_prev=2.0))          # TTM 143.1, published after May 2
    h = screen.ttm_history(pd.DataFrame(rows))
    assert list(h.t.dt.year) == [2009, 2010, 2011, 2012, 2013]
    g = screen.growth(h, "2013-05-02").loc["C"]                          # 2012 vs 2009, the ITR not public yet
    assert g.revenue_growth == pytest.approx(1.331 ** (365.25 / 1096) - 1) and g.growth_base == "2009-12-31"   # ~10%/yr
    assert np.isnan(g.earnings_growth)                                   # a loss now has no CAGR...
    assert g.growth_consistency == 1.0                                   # 2010, 2011, 2012 each above the year before
    assert screen.growth(h, "2012-05-02").loc["C"].growth_base == ""     # under 3 years of history: not measured
    later = screen.growth(h, "2013-05-10").loc["C"]                      # Q1 2013 vs 2009: 3.25 years, exact span
    assert later.revenue_growth == pytest.approx((143.1 / 100) ** (1 / (1186 / 365.25)) - 1)


def test_a_loss_ranks_last_on_earnings_growth_and_growth_does_not_move_the_score():
    n = 6
    df = pd.DataFrame({"ticker": [f"T{i}" for i in range(n)], "cnpj": list("ABCDEF"), "isin": "", "price": 10.0,
                       "sector": "", "bdi": "02", "liquidity": 1e8, "sessions": 500, "market_cap": 1000.0,
                       "ebit": 100.0, "net_income": [50.0] * (n - 1) + [-10.0], "revenue": 1000.0,
                       "equity": 500.0, "net_debt": 100.0, "revenue_growth": np.linspace(0.0, 0.5, n),
                       "earnings_growth": [0.1, 0.2, 0.3, np.nan, 0.4, np.nan], "growth_consistency": 1.0,
                       "growth_base": ["2023-06-30"] * (n - 2) + ["", "2023-06-30"]})
    empty = pd.DataFrame(columns=["date", "ticker", "close"])
    cash = pd.DataFrame(columns=["isin", "rate", "last_date_prior", "label"])
    stock = pd.DataFrame(columns=["isin", "mult", "last_date_prior", "label"])
    out = screen._metrics(df.copy(), empty, cash, stock, "2026-11-06", pit=True).set_index("cnpj")
    assert out.p_earnings_growth.idxmin() == "F"           # losing money now: last
    assert np.isnan(out.loc["D", "p_earnings_growth"])     # no measurable start: not scored
    flat = df.assign(revenue_growth=0.0, earnings_growth=0.0, growth_consistency=0.0)
    again = screen._metrics(flat, empty, cash, stock, "2026-11-06", pit=True).set_index("cnpj")
    assert (out.score == again.score).all()                 # weight 0: shown, not scored

import numpy as np
import pandas as pd
import pytest

from b3radar import backtest


def test_rebalance_is_first_session_of_may_each_year():
    sessions = np.array(["2012-04-30", "2012-05-02", "2012-05-03", "2013-04-30", "2013-05-06", "2014-03-01"])
    assert backtest.rebalance_dates(sessions, 2012) == ["2012-05-02", "2013-05-06"]


def prices():
    px = pd.DataFrame({
        "date": ["2020-05-04", "2020-06-01", "2021-05-03"] * 2 + ["2020-05-04", "2020-06-01"],
        "ticker": ["AAA3"] * 3 + ["BBB3"] * 3 + ["DEAD3"] * 2,
        "isin": ["A"] * 3 + ["B"] * 3 + ["D"] * 2,
        "close": [10, 11, 12, 20, 20, 10, 5, 2],
    })
    cash = pd.DataFrame({"isin": ["B"], "rate": [10.0], "last_date_prior": ["2020-06-01"], "label": ["DIVIDENDO"]})
    stock = pd.DataFrame(columns=["isin", "mult", "last_date_prior", "label"])
    return backtest.Prices(px, cash, stock)


def test_buy_and_hold_return_includes_dividends_and_keeps_dead_stocks():
    p = prices()
    # AAA3 +20%; BBB3 paid R$10 on a R$20 price then fell to 10: total return 0%
    assert p.ret(["AAA3"], "2020-05-04", "2021-05-03") == pytest.approx(0.2)
    assert p.ret(["BBB3"], "2020-05-04", "2021-05-03") == pytest.approx(0.0)
    # DEAD3 stopped trading at 2 (from 5): it keeps its last price, -60%, not dropped
    assert p.ret(["DEAD3"], "2020-05-04", "2021-05-03") == pytest.approx(-0.6)
    assert p.ret(["AAA3", "DEAD3"], "2020-05-04", "2021-05-03") == pytest.approx(-0.2)
    assert np.isnan(p.ret(["NOPE3"], "2020-05-04", "2021-05-03"))


def test_cdi_return_compounds_daily_rates():
    idx = (1 + pd.Series([0.05, 0.05, 0.05], index=["2020-01-02", "2020-01-03", "2020-01-06"]) / 100).cumprod()
    assert backtest._cdi_ret(idx, "2020-01-02", "2020-01-06") == pytest.approx(1.0005 ** 2 - 1)


def test_company_ttm_series_follows_the_screen_rule():
    from b3radar import companies
    f = pd.DataFrame([
        {"kind": "DFP", "dt_refer": "2024-12-31", "revenue": 100.0, "ebit": 20.0, "net_income": 10.0,
         "revenue_prev": np.nan, "ebit_prev": np.nan, "net_income_prev": np.nan,
         "equity": 50.0, "st_debt": 5.0, "lt_debt": 15.0, "cash": 8.0, "short_investments": 2.0},
        {"kind": "ITR", "dt_refer": "2025-06-30", "revenue": 60.0, "ebit": 14.0, "net_income": 7.0,
         "revenue_prev": 50.0, "ebit_prev": 10.0, "net_income_prev": 5.0,
         "equity": 55.0, "st_debt": 5.0, "lt_debt": 15.0, "cash": 10.0, "short_investments": 0.0},
        {"kind": "ITR", "dt_refer": "2026-09-30", "revenue": 1.0, "ebit": 1.0, "net_income": 1.0,   # no annual right before it
         "revenue_prev": 1.0, "ebit_prev": 1.0, "net_income_prev": 1.0,
         "equity": 1.0, "st_debt": 0.0, "lt_debt": 0.0, "cash": 0.0, "short_investments": 0.0},
    ])
    s = companies.ttm_series(f).set_index("dt_refer")
    assert list(s.index) == ["2024-12-31", "2025-06-30"]
    assert s.loc["2025-06-30", "revenue"] == 110.0 and s.loc["2025-06-30", "ebit"] == 24.0
    assert s.loc["2024-12-31", "net_debt"] == 10.0


def test_company_snapshots_follow_the_filing_calendar():
    from b3radar import companies
    sessions = np.array(["2011-04-01", "2011-06-01", "2011-09-01", "2011-12-01", "2012-04-02", "2012-05-02"])
    assert companies.snapshot_dates(sessions, 2011) == ["2011-04-01", "2011-06-01", "2011-09-01", "2011-12-01", "2012-04-02"]

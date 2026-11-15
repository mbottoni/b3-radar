import numpy as np
import pandas as pd
import pytest

from b3radar import backtest


def test_rebalance_is_first_session_of_may_each_year():
    sessions = np.array(["2012-04-30", "2012-05-02", "2012-05-03", "2013-04-30", "2013-05-06", "2014-03-01"])
    assert backtest.rebalance_dates(sessions, 2012) == ["2012-05-02", "2013-05-06"]


def test_the_avoid_list_is_the_bottom_of_the_same_ranking():
    snap = pd.DataFrame({"ticker": ["A3", "B3", "C3", "D3"], "excluded": ["", "", "", "illiquid"],
                         "score": [90.0, 20.0, 50.0, 1.0], "sector_group": "Retail"})
    assert list(backtest.pick(snap, *backtest.STRATEGIES["composite_bottom"], n=2).ticker) == ["B3", "C3"]


def test_the_pages_bottom_fifth_cut_matches_the_backtests_fifths():
    # docs/assets/index.js: rank > 1 + 0.8 (n - 1) is the bottom fifth, as pandas.qcut cuts it
    for n in (25, 124, 129, 130, 131, 180):
        rank = pd.Series(range(1, n + 1))
        q = pd.qcut(rank, 5, labels=[1, 2, 3, 4, 5])
        assert list(rank[q == 5]) == list(rank[rank > 1 + 0.8 * (n - 1)])


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


def test_cadences_count_months_from_may_and_weeks_end_on_their_last_session():
    sessions = np.array(["2012-05-02", "2012-05-04", "2012-06-01", "2012-07-02", "2012-08-01", "2012-11-01",
                         "2013-02-01", "2013-05-02"])
    assert backtest.cadence_dates(sessions, 3, 2012) == ["2012-05-02", "2012-08-01", "2012-11-01", "2013-02-01", "2013-05-02"]
    assert backtest.cadence_dates(sessions, 12, 2012) == backtest.rebalance_dates(sessions, 2012)
    week = np.array(["2026-11-03", "2026-11-04", "2026-11-06", "2026-11-09", "2026-11-13", "2026-11-16"])
    assert backtest.week_ends(week, "2026-11-04") == ["2026-11-04", "2026-11-06", "2026-11-13", "2026-11-16"]


def test_rebalancing_trades_the_drift_and_costs_both_sides():
    px = pd.DataFrame({"date": ["2020-05-04", "2020-06-01", "2020-07-01"] * 3,
                       "ticker": ["AAA3"] * 3 + ["BBB3"] * 3 + ["CCC3"] * 3, "isin": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
                       "close": [10, 20, 20, 10, 10, 10, 10, 10, 15]})
    p = backtest.Prices(px, pd.DataFrame(columns=["isin", "rate", "last_date_prior", "label"]),
                        pd.DataFrame(columns=["isin", "mult", "last_date_prior", "label"]))
    lists = {"2020-05-04": ["AAA3", "BBB3"], "2020-06-01": ["AAA3", "CCC3"]}
    dates, end = list(lists), "2020-07-01"
    vals, trades = backtest.follow(lists, dates, end, ["2020-06-01", end], p, cost=0.01)
    v = vals.set_index("date")
    # AAA3 doubled: the holdings drift to 2/3 AAA3, 1/3 BBB3; equal weights on the new list sell
    # 1/6 of AAA3 and all of BBB3 (1/3 + 1/6 = 1/2 of the portfolio) to buy half in CCC3.
    assert trades.sold.tolist() == pytest.approx([0.0, 0.5]) and trades.bought.tolist() == pytest.approx([1.0, 0.5])
    assert v.gross["2020-06-01"] == pytest.approx(150.0) and v.gross[end] == pytest.approx(150 * 1.25)
    assert v.net["2020-06-01"] == pytest.approx(100 * 0.99 * 1.5)                  # buying it all: 1% once
    assert v.net[end] == pytest.approx(100 * 0.99 * 1.5 * (1 - 0.01 * 1.0) * 1.25)  # half sold + half bought: 1%
    # Without costs it is the plain chain of equal-weight returns.
    same, _ = backtest.follow(lists, dates, end, [end], p, cost=0.0)
    assert same.set_index("date").net[end] == pytest.approx(100 * (1 + p.ret(lists[dates[0]], dates[0], "2020-06-01"))
                                                            * (1 + p.ret(lists[dates[1]], "2020-06-01", end)))


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


def test_market_rates_use_only_what_was_published():
    from b3radar import market
    cdi = pd.DataFrame({"date": ["2026-10-30", "2026-11-03"], "rate": [0.05, 0.06]})
    assert market.cdi_annual(cdi, "2026-11-02") == pytest.approx(1.0005 ** 252 - 1)    # the rate in force that day
    months = pd.date_range("2025-09-01", "2026-09-01", freq="MS").strftime("%Y-%m-%d")
    ipca = pd.DataFrame({"date": months, "rate": [1.0] + [0.5] * 12})
    # Sep 2026's IPCA comes out around Oct 10: on Oct 5 the last twelve are Sep 2025 - Aug 2026
    assert market.ipca_12m(ipca, "2026-10-05") == pytest.approx(1.01 * 1.005 ** 11 - 1)
    assert market.ipca_12m(ipca, "2026-10-20") == pytest.approx(1.005 ** 12 - 1)
    assert np.isnan(market.ipca_12m(ipca.tail(5), "2026-10-20"))                         # under a year known


def test_market_snapshot_sums_the_eligible_universe_only():
    from b3radar import market
    df = pd.DataFrame({"excluded": ["", "", "", "illiquid"], "earnings_yield": [0.10, 0.20, 0.05, 0.90],
                       "ebit": [10.0, 40.0, 5.0, 900.0], "ev": [100.0, 200.0, 100.0, 1000.0],
                       "market_cap": [80.0, 150.0, 100.0, 1000.0], "net_income": [8.0, 30.0, -3.0, 500.0],
                       "dividend_yield": [0.04, np.nan, 0.02, 0.5]})
    cdi = pd.DataFrame({"date": ["2026-11-06"], "rate": [0.05]})
    s = market.snapshot(df, "2026-11-06", cdi, pd.DataFrame(columns=["date", "rate"]))
    assert s["eligible"] == 3 and s["earnings_yield"] == pytest.approx(0.10)              # median, not the outlier
    assert s["earnings_yield_agg"] == pytest.approx(55 / 400) and s["pe_agg"] == pytest.approx(330 / 35)
    assert s["dividend_yield_agg"] == pytest.approx((0.04 * 80 + 0.02 * 100) / 330)      # no dividend counts as 0
    assert np.isnan(s["real_cdi"])                                                       # no inflation known


def test_market_history_skips_the_month_in_progress():
    from b3radar import market
    sessions = np.array(["2011-04-29", "2011-05-30", "2011-05-31", "2011-06-01", "2011-06-02"])
    assert market.month_ends(sessions) == ["2011-05-31"]

# Methodology

Every number on the page and in the email comes from the rules below. The
constants live at the top of `b3radar/screen.py` and `b3radar/picks.py`.

## Data

| what | source | refreshed |
|---|---|---|
| Quotes (open, high, low, close, volume) per ticker and session | B3, "Séries Históricas" (COTAHIST daily and yearly files) | every session |
| Statements: income, balance sheet, share capital, with the date CVM received each filing | CVM open data: DFP (annual), ITR (quarterly) | daily check |
| Company register: sector, registration status, issuer status | CVM `cad_cia_aberta` | daily check |
| Trading codes per company | CVM FCA `valor_mobiliario` | daily check |
| Dividends, JCP, capital returns, splits, reverse splits, bonus shares, current share counts | B3 listed-companies service | every weekday |

Kept from the quote files: the cash market, standard lots, shares and units
(`ON`, `PN`, `PNA`…, `UNT`), and BOVA11 as the benchmark. BDRs, funds, odd
lots and the separate judicial-recovery segment are dropped. Prices are per
share (divided by B3's quotation factor).

### Problems met in the data, and what is done about them

- **B3 rewrites its yearly quote file every evening**, and during the rewrite
  it serves a truncated zip whose size header matches the truncated body.
  Every downloaded zip is CRC-checked; a corrupt one is fetched again a
  minute later.
- **B3 sometimes answers 404 for a daily file that exists.** A weekday 404 is
  retried, and the weekly job re-applies the authoritative yearly file, so a
  missed session is filled within a week.
- **B3 answers 404 to daily files unless the User-Agent starts with
  `Mozilla/5.0`.** The scraper uses the usual bot convention
  (`Mozilla/5.0 (compatible; b3-radar/0.1; +repo URL)`): it names itself and
  links here, it does not pose as a browser.
- **CVM's share-capital file has no unit column.** Many companies file
  thousands, Petrobras files units, and some rows mix both (Tenda's
  2026-06-30 filing: total in thousands, treasury in units). Each class's
  count is checked against B3's current count, after carrying the filed
  count through any split since the filing date: within 0.8–1.25× it is
  units, 800–1250× it is thousands, anything else (Lavvi filed an extra
  digit; OceanPact issued shares since its filing) uses B3's count. The
  screen records which source each count came from.
- **B3's corporate-events service lists about a year of cash events**; the
  full history (since the 1990s) comes from its `GetListedCashDividends`
  service, per share class, and every later fetch is merged into
  `data/events/`.
- **B3 often issues a new ISIN after a reverse split** and files the event
  under the old one (Hapvida 2025, Azevedo & Travassos 2026). Events are
  matched against every ISIN a ticker has traded under, and a payment on
  file under both is counted once.
- **B3's events service misses some splits** (Magazine Luiza's 2017 and
  2019 8:1 bonus splits). B3 marks the session an event takes effect in the
  quote file (`EB` ex-bonus/split, `EG` ex-reverse split): a marked session
  with no recorded event gets an inferred one, the multiplier being the
  previous close over that session's open snapped to a clean ratio (2, 3,
  8, 10, 3:2, 1:10...). Moves under 30% are not inferred. These live in
  `data/events/stock_inferred.csv`, labelled `(INFERIDO)`. 156 were found
  for 2010–2026. After this, the price moves over 2.5x in a session that
  remain in stocks the screen could hold are real: crashes (Americanas 2023,
  Ambipar 2025, the market-wide fall of 2026-10-26), spin-offs (below) and
  tickers returning after years without trades.

## Point in time

The screen for a session uses only what was public by then: a filing counts
from the day CVM received it, quotes up to that session. CVM's data files
hold the latest version of each filing, so a restatement is used from its
own receipt date.

**Trailing twelve months (TTM)**, income items: last annual report, plus the
current year-to-date quarterly figure, minus the same period of the prior
year (taken from that same quarterly filing). If the latest quarterly is not
in the fiscal year right after the latest annual, TTM is left empty rather
than guessed. Balance-sheet items come from the latest filing.

## Universe

A company is eligible if all of these hold:

- its most-traded ticker averaged at least **R$ 5 million a day** over the
  last 63 sessions and traded in the last 5;
- it has **a year of quotes** (252 sessions), so recent IPOs wait a year;
- CVM registration **active** and issuer status **"fase operacional"**:
  judicial or extrajudicial recovery, liquidation, bankruptcy,
  pre-operational and halted companies are out;
- **not a financial**: banks, insurers, financial intermediation, leasing,
  securitization and real-estate credit, plus holding companies in those
  sectors, use a different chart of accounts;
- TTM EBIT and a market cap can be computed, equity is positive and
  enterprise value is positive.

Each excluded company is still listed on the page with its reason.

## Metrics

- **Market cap:** shares outstanding per class (ON, PN) times that class's
  most-traded price; a class with no recent trade uses the other class's
  price. Units are not counted separately (they are bundles of ON and PN).
- **Net debt** = short- and long-term loans and financing − cash − short-term
  investments. **EV** = market cap + net debt.
- **Earnings yield** = EBIT / EV · **Book/market** = equity / market cap ·
  **ROE** = net income / equity · **ROIC** = EBIT / (equity + net debt) ·
  **Net debt / EBIT** (EBIT ≤ 0 counts as the worst) · P/E, EV/EBIT and net
  margin are shown but not scored.
- **Momentum (12–1)**: total return from 252 to 21 sessions ago, on prices
  adjusted for every dividend, JCP, capital return, split, reverse split and
  bonus. An event takes effect on the first session after its last "com"
  date: a cash event scales earlier prices by 1 − amount / close, a stock
  event by 1 / share multiplier. **Spin-offs and rights issues are not
  adjusted**: when GPA spun off Assaí (2021) and Éxito (2023), or Lojas
  Americanas reorganized (2021), the value that moved to the new shares
  shows as a loss in the old ticker.
- **Dividend yield**: dividends, JCP and other income paid in the last 365
  days (per share as the stock trades today) / price. Capital returns are
  excluded: they are cash, but not a recurring dividend.
- **Growth** (shown, not scored: see below), from the TTM revenue and net
  income at every statement (`screen.ttm_history`), each public from the
  later of the two filings it uses:
  - **Revenue growth** and **net income growth**: compound annual growth
    from the statement three years before the latest one to the latest
    (the start may be up to a quarter older; the rate uses the exact span).
    Both ends must be positive. A company losing money now, against a
    measurable start, ranks last on net income growth; one that went from
    a loss to a profit has no rate and is not scored on it.
  - **Consistency**: of the statements in those three years (up to 12
    quarters), the share whose TTM revenue was above the one a year
    earlier; at least 3 readings.
  - CVM's open data starts with the 2010 annual reports (which also state
    2009), so three-year growth exists from 2013. Totals, not per share:
    share counts before 2020 are too approximate to measure dilution.

## Scores

Within the eligible universe, each metric becomes a percentile (0–100,
higher is better; for net debt / EBIT lower is better):

| category | metrics | weight |
|---|---|---|
| Value | earnings yield, book/market | 25% |
| Quality | ROIC, ROE, low net debt / EBIT | 25% |
| Momentum | 12–1 return | 25% |
| Income | dividend yield | 25% |
| Growth | revenue growth, net income growth, consistency | 0% (shown) |

The **score** is the weighted mean of the four scored category means. Percentiles
make the score robust to outliers: a company with a one-off 33% yield gets
the top income percentile, not 33 points more.

Each company's row on the page expands into **why it scores what it
does**: every metric's raw value and its percentile, the statements used
(period and the date CVM received them) and where its share count came from.

**Why growth is not in the score.** It was added to answer a blind spot:
WEG turned R$100 into about R$2,460 from 2010 while never being cheap, and
the score never picked it. Before testing, the rule was fixed: growth
joins the score at an equal one-fifth weight only if, on its own, its top
fifth beats its bottom fifth over the backtest and in at least half the
years. It did neither. From 2013 the fastest-growing fifth returned 2.8% a
year and the slowest 6.3%; the top beat the bottom in 5 of 14 years. Fast
growers were already priced for it (median P/E around 20–30 against
13–17 for the slowest), and the slowest included the beaten-down companies
that rebounded hardest, as in 2016. Added anyway at one fifth, the score's
backtest would have fallen from 8.4% to 3.7% a year. Growth stays on the
page and on the company pages, for reading a company, with no weight.

**Rules fingerprint.** Everything above that decides eligibility and
ranking (thresholds, sector exclusions, weighted pillars, weights, metric
definitions) is hashed (`screen.rules()`, shown on the page as "scoring
rules xxxxxxxx"). Every weekly list and every backtest is stamped with it.
Lists made under different rules are tracked as separate records, never
pooled, and a list is held until the strategy's next list whatever its
rules, so changing the rules ends one record and starts another instead of
rewriting the past. A pillar with no weight is left out of the
fingerprint: it cannot change a rank.

**Magic Formula** (Greenblatt), the baseline: rank by earnings yield plus
rank by ROIC, among eligible companies with positive EBIT.

## The weekly list and the track record

Every Monday (closing prices of the previous session) the top 10 by score,
and the top 10 by the Magic Formula, are appended to `data/picks/picks.csv`
with their prices. Nothing is ever removed.

The track record holds each list as an **equal-weight portfolio until the
next list**, on adjusted prices (dividends reinvested), and compares it with
BOVA11 over the same sessions. A ticker that stops trading keeps its last
price. The return is measured from the close used to make the list, so it
assumes you could buy at that close; buying at Monday's open will differ.

## Backtest

`python -m b3radar backtest` (monthly in CI, results in `data/backtest/`)
replays the screen as a long-term investor would use it:

- **Once a year**, on the first session of May (annual reports, due at the
  end of March, are public), the screen is computed **as it stood that
  day** (the same code, point in time) and the top 10 are bought in equal
  weights, held twelve months with dividends reinvested, then replaced.
  First list: May 2012 (quotes and statements start in 2010–2011).
- **Buy once and hold**: each yearly list is also followed untouched for
  one, three and five years.
- Six strategies (the score, the Magic Formula, and each category alone)
  against **BOVA11** (the Ibovespa is a total-return index), the **CDI**
  (Banco Central series 12, compounded daily: what cash earns) and **every
  eligible stock in equal weights**, which isolates what the picking adds
  over simply owning the universe.

**Does each score separate winners from losers?** At every yearly date the
eligible universe is cut into fifths by the composite and by each pillar
(Q1 = best), each fifth held for the year in equal weights. A factor that
works steps down from Q1 to Q5. Through 2026 the clearest effects were the
bottom fifth of the score and of value doing much worse than the rest, and
momentum's top fifth doing best; the top fifth of quality did not beat the
middle, and growth's top fifth did worst of all (from 2013, when growth
can first be measured). Fifteen yearly periods are a small sample: these results describe
the past, and re-weighting the score to fit them would overfit it.

History behind it:

- Quotes since 2010 from B3's yearly files, **including the sanctioned and
  recovery segments** (CODBDI 05–09), so a stock that goes into judicial
  recovery keeps its falling quotes instead of freezing at its last normal
  price. The screen never picks from those segments.
- Dividends and JCP since the 1990s from B3's `GetListedCashDividends`, per
  share class; splits from the corporate-events service.
- Share counts: DFP/ITR from 2020; before that the capital timeline of
  CVM's Reference Form (FRE). A historical count is checked against B3's
  current count carried back through every later split, with a wider band
  (0.6–1.6x) since later issuance and buybacks are unknown; outside it, the
  carried-back count is used.
- Registration and issuer status are only known as of today, so they are
  not applied to past dates (the special trading segments still are).

What it does not include: brokerage, taxes, slippage; dividends of
companies that have since delisted (B3 only serves listed companies'
history), which understates returns slightly; the fact that a May close is
not always where you would have bought.

## Known limits

- Trailing yields and earnings include one-offs (special dividends, asset
  sales). Percentiles cap their effect on the score but not on the display.
- Units' market caps use their ON and PN prices; spin-offs and rights
  issues leave a small gap in momentum.
- No transaction costs, taxes or slippage in the track record.
- The scores know nothing about news, governance or guidance.

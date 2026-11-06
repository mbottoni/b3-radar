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
- **B3 lists only about a year of cash events.** Every fetch is merged into
  `data/events/`, so the repo accumulates the full history from now on.

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
  event by 1 / share multiplier. Spin-offs and rights issues are not adjusted.
- **Dividend yield**: dividends, JCP and other income paid in the last 365
  days (per share as the stock trades today) / price. Capital returns are
  excluded: they are cash, but not a recurring dividend.

## Scores

Within the eligible universe, each metric becomes a percentile (0–100,
higher is better; for net debt / EBIT lower is better):

| category | metrics | weight |
|---|---|---|
| Value | earnings yield, book/market | 25% |
| Quality | ROIC, ROE, low net debt / EBIT | 25% |
| Momentum | 12–1 return | 25% |
| Income | dividend yield | 25% |

The **score** is the weighted mean of the four category means. Percentiles
make the score robust to outliers: a company with a one-off 33% yield gets
the top income percentile, not 33 points more.

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

## Known limits

- Trailing yields and earnings include one-offs (special dividends, asset
  sales). Percentiles cap their effect on the score but not on the display.
- Units' market caps use their ON and PN prices; spin-offs and rights
  issues leave a small gap in momentum.
- No transaction costs, taxes or slippage in the track record.
- The scores know nothing about news, governance or guidance.

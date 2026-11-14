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
  screen records which source each count came from. A count is read as
  thousands only if it is under 100 million (no company has 100 billion
  shares).
- **Share counts before 2020 are not in the statements.** CVM's Reference
  Form (FRE) gives them two ways. Its capital timeline is not point in
  time: later forms rewrite earlier entries in later share terms
  (Odontoprev's 2021 form lists its 2010 capital with 2021's share count,
  three times the 2010 one after a 2012 split), and the data keeps only
  the latest. Its free-float table (item 15.3) is used instead: shares in
  free float divided by their percentage of the class gives the class
  total (CCR 2013: 861.3 million / 48.78% = 1,765.6 million), dated by the
  day CVM received the form version (`data/cvm/shares_fre.csv`). Most
  forms give the count at receipt; some, received after a split, still
  give the one of their last shareholders' meeting before it (Sabesp
  2013, Totvs 2011). When a split falls between the two dates, the next
  form decides: if it is about the split larger, the count predates it.
  A class with no free float (Gol's voting shares, all held by its
  controller) falls back to the capital timeline.
- **In the backtest, B3's count is no reference.** It is today's count
  carried back through every later split, which knows nothing of shares
  issued since: PDG went from 1.3 billion shares in 2012 to 27 million
  after five reverse splits and a restructuring, so its carried-back count
  gave a market cap of R$63 quadrillion. Past dates keep the count filed
  at the time. Until this was fixed (November 2026) the backtest held 14
  company-years with market caps over R$1 trillion, and CCR, Marisa and
  Odontoprev at 3–15x their size; they now match history (Ambev R$285
  billion, Petrobras R$237 billion, CCR R$36 billion in January 2013).
  Across the yearly backtest dates, 47 of 1,361 year-on-year steps in a
  company's share count (in today's terms) exceed 1.6x; most are real
  issuance (Hapvida's merger, Minerva's and Cosan's offerings).
- **B3's corporate-events service lists about a year of cash events**; the
  full history (since the 1990s) comes from its `GetListedCashDividends`
  service, per share class, and every later fetch is merged into
  `data/events/`.
- **B3's dividend history matches the company's trading name exactly**, and
  answers nothing for a name written with "S/A" ("AMBEV S/A": none; "AMBEV
  SA": 2014 on). Such names are also asked for with "SA"; before 2026-11-14,
  13 companies (Ambev, Klabin, Cury, Light, TIM among them) had only the
  last year of dividends on file. B3's history for **Fras-le stops in
  2002** under every spelling, and the daily events feed starts in late
  2025, so FRAS3's dividends for 2003–2024 are missing: its dividend yield
  and total return in those years are understated.
- **B3 often issues a new ISIN after a reverse split** and files the event
  under the old one (Hapvida 2025, Azevedo & Travassos 2026). Events are
  matched against every ISIN a ticker has traded under, and a payment on
  file under both is counted once.
- **A company that changes its name gets a new ticker, and usually a new
  ISIN** (Eletrobras ELET3 → AXIA3 and Embraer EMBR3 → EMBJ3 in Nov 2025,
  Guararapes GUAR3 → RIAA3 in Feb 2026, CTEEP TRPL4 → ISAE4 in 2024; 49 such
  switches since 2010). On its own the new ticker looks like a new listing:
  under a year of quotes, no momentum, no history, and the old one is often
  missing from CVM's current list of trading codes, so it never meets its
  filings (CTEEP was absent from every backtest year for that reason). A
  ticker that stops and one of the same company (CNPJ) and class (the
  digits) with a different root that starts within 10 days, with the
  adjusted price moving less than 25% across the switch, are taken as one
  share: its whole history is read under the ticker it trades under now, in
  the screen, the backtest, the company pages and the track record. The
  price test keeps out a merger priced at an exchange ratio; a rename that
  comes with a split on file passes it. Past lists in the backtest therefore
  show today's ticker (CTEEP as ISAE4 in 2012). Since 2026-11-14.
- **B3's events service lists half of Itaú's 2011 operation**: the 100:1
  reverse split of 2011-10-31, not the 1:100 split approved with it, which
  left the share count and the price where they were (R$32.73 before,
  R$32.13 after). Alone, the reverse split showed Itaú's total return
  falling 99% in November 2011 and its dividend yield at 100–300% through
  2012. `data/events/stock_fixes.csv` adds the missing half, labelled
  `(CORRIGIDO)`. Two other recorded events disagree with the price on
  their session by over 3x (Banestes 2012, General Shopping 2019); neither
  is liquid enough to be screened, and they are left as filed.
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
  sectors, use a different chart of accounts (they are ranked apart: see
  [the financials screen](#the-financials-screen-a-separate-ranking));
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
years. It did neither. From 2013 the fastest-growing fifth returned 2.7% a
year and the slowest 6.7%; the top beat the bottom in 5 of 14 years. Fast
growers were already priced for it (median P/E around 20–30 against
13–17 for the slowest), and the slowest included the beaten-down companies
that rebounded hardest, as in 2016. Added anyway at one fifth, the score's
backtest would have fallen from 8.9% to 4.8% a year. Growth stays on the
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

## The financials screen (a separate ranking)

The companies the main screen leaves out as "financial sector" (banks,
insurers and insurance brokers, their holdings, card acquirers) are ranked
among themselves in `b3radar/financials.py`, on metrics that fit a lender:
EBIT, enterprise value and net debt mean nothing for a bank, whose debt is
its raw material. It is shown only: it never enters the main score, the
weekly list, the track record or the main backtest, and it has a
fingerprint of its own (`financials.rules_hash()`, on the page as "own
rules xxxxxxxx"), so changing it never touches the main one.

**Who is ranked.** The main screen's own filters, applied the same way:
R$ 5 million a day, a year of quotes, a recent trade, registration active
and operating normally (today only), outside the special segments; plus a
trailing net income, a market cap and positive equity. Few pass: 7 in
2012, 10 in 2015, 14–18 since 2019 (16 today).

**Metrics**, point in time like the main screen:

| pillar | metric | weight |
|---|---|---|
| Value | book / market (the parent's equity / market cap); P/B is its inverse | 25% |
| Quality | ROE (the parent's net income, trailing twelve months / its equity); ROE stability (standard deviation of that ROE at every statement of the last 3 years, at least 4, lower is better) | 25% |
| Momentum | 12–1 return, the main screen's | 25% |
| Income | dividend yield, the main screen's 365-day rule | 25% |

Each metric is a percentile among the eligible financials (0–100), each
pillar the mean of its metrics, the score the weighted mean of the pillars.
P/E, earnings yield (net income / market cap) and payout (dividend yield ×
market cap / net income) are shown, not scored. These rules were set
before the backtest below was run, and not changed after.

**Where net income and equity are.** Banks, insurers and holdings file
other charts of accounts than industrial companies, and the codes move
between them: net income is `3.09` (Itaú; Banco do Brasil until 2019),
`3.11` (Banco do Brasil since 2020, Itaúsa, Porto Seguro) or `3.13` (BB
Seguridade, IRB, and most banks' individual statements); equity is
`2.03` (insurers, holdings), `2.05`, `2.07` or `2.08` (banks), while a
bank's consolidated `2.03` is a liability (Itaú's "Passivos Financeiros
ao Custo Amortizado", R$ 2.35 trillion; Banco do Brasil's provisions). Read with the industrial codes, Bradesco
showed a book / market of 3.2 and Itaú no P/E at all. What does not move,
in every DFP and ITR the 48 listed financial companies filed since 2010
(3,845 balance sheets, consolidated and individual, and their income
statements; `cvm.financial_filings`):

- **net income** is the last top-level income line before `3.99`
  (earnings per share), always named "Lucro/Prejuízo ... do Período";
  the controlling shareholders' share is its child "Atribuído a Sócios da
  Empresa Controladora";
- **equity** is the top-level liability line named "Patrimônio Líquido";
  the controlling shareholders' share is that less its child "...
  Não Controladores".

Problems met in these filings, and what is done:

- **The split between parent and minorities does not always add up.** IRB,
  Caixa Seguridade, Banco Pan, Banestes and Santander (in several
  quarters) file zeros in both lines; Santander's June 2026 ITR gives the
  parent R$ 6.1 billion of a R$ 8.1 billion total with no minorities to
  speak of. The split is used only when its two lines add up to the total
  (within 1%); otherwise the total is the parent's (in 101 of 3,862
  filings).
- **Consolidated and individual statements differ.** A bank's individual
  statements follow the Banco Central's accounting, its consolidated ones
  IFRS, and some companies switch (ABC Brasil files consolidated statements
  until 2023, individual ones after). Both are kept
  (`data/cvm/financials.csv`, one row per filing and basis) and a trailing
  twelve months is computed within one basis: the one with a computable
  TTM and equity, then the latest statement, then consolidated.
- **No prior-year figure in 2025.** Every bank's individual ITRs of 2025
  give last year's year-to-date net income as 0: CMN Resolution 4,966
  took effect on 1 January 2025 without restating comparatives. A zero
  prior-year figure next to a non-zero current one is taken from the prior
  year's own report for that quarter.
- **A filing in the wrong unit.** Pine's ITRs of June and September 2024
  say units but hold thousands (equity R$ 1.1 million, against R$ 1.07
  billion in March). A filing whose equity is over 200 times smaller (or
  larger) than the median of the company's previous four, same basis, is
  multiplied (divided) by 1000. Only earlier filings are compared, so this
  stays point in time.
- **Equity of exactly 0** (Santander's individual annual reports of 2020
  and 2021, an empty Banco Inter ITR) is a blank, not a bank with no
  capital.
- **Market caps 1000 times too small.** Itaú, Bradesco and Itaúsa file
  share counts in thousands (4,958,290 for 4.96 billion), above the 2
  million under which `screen.outstanding` reads thousands. Live, B3's
  current count settles it; in the backtest it is dropped after any later
  bonus issue, and these banks issue bonus shares most years, so their
  market caps came out at R$ 0.2 billion from 2020. IRB's 2022 annual
  report gives its share count after the 30:1 reverse split of January
  2023, which was then applied again (1/30 of its size in May 2023). A
  market cap over 10 times away from the one B3's count carried back
  gives is a units or dating error, not issuance, and B3's is used. Smaller
  gaps keep the filed count, as in the main screen: B3's events service
  misses some of Bradesco's and Itaúsa's yearly bonus issues, which puts
  its carried-back count 1.3–2.7 times too high before 2020. The same
  thousands reading affects one class of Eletrobras in the main backtest
  (from 2023 its market cap is about a seventh of its size; it ranked
  81st, 61st and 20th in 2023–2025, never in the top 10); the main screen
  is not changed here.
- **Before 2020, share counts come from the Reference Form** (see above)
  and stay approximate: Banco do Brasil's May 2012 market cap comes out at
  R$ 20 billion, about a third of its size.
- **A refiled report counts from its refiling.** Itaú filed new versions
  of its 2011 and 2012 annual reports in March 2020; CVM keeps only the
  latest version, which counts from the day it was received (as everywhere
  here), so Itaú has no trailing net income, and no score, from mid-2012
  to the end of 2013.

Insurance brokers (Qualicorp, Wiz) file ordinary accounts and are in this
screen only because CVM files them under "Seguradoras e Corretoras"; their
book value, mostly goodwill, means less than a bank's.

**Does the score separate winners from losers?** The backtest (`python -m
b3radar backtest`, monthly; `data/backtest/financials_*`) cuts the eligible
financials into fifths each May, as they stood that day, by the score and by
each pillar, and holds each fifth a year in equal weights with dividends
reinvested. It starts in 2015, the first May with 10 eligible financials, so
each fifth holds 2–4 stocks. Through November 2026 (12 periods):

| fifth by score | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|
| per year | 13.7% | 9.4% | 8.0% | −0.7% | 8.2% |

against 9.2% for all eligible financials, 10.1% for BOVA11 and 10.0% for
the CDI. The top fifth beat the bottom in 7 of 12 years, and the fifths are
not in order: Q4 did worst. By pillar, only value steps down roughly in
order (13.7%, 15.2%, 10.4%, 4.5%, −3.1%); quality (ROE and its stability)
shows no order at all (10.5% for Q1, 9.6% for Q5); momentum and income
are mixed. With 2–4 names a fifth, one bank's year moves a fifth by
several points: this describes the past and is not evidence that the score
works.

## The market against cash

`python -m b3radar market` (monthly, with the backtest; `data/market/`)
sums up the screen at every month end since May 2011, point in time:

- **Earnings yield of the typical stock**: the median EBIT / EV of the
  eligible companies, the screen's own value metric. Also the aggregate
  (sum of EBIT over sum of EV), the aggregate P/E and dividend yields.
- **The CDI**, annualized from the day's rate (Banco Central series 12),
  and **the CDI after inflation**: deflated by the IPCA of the last twelve
  months published by then (series 433; a month's IPCA counts from the 15th
  of the next). Earnings rise with prices, so an earnings yield compares
  with a real rate more than with a nominal one.
- **Cheaper than X% of months**: where today's earnings yield stands in
  that history (higher yield = cheaper).
- **What came next**: every eligible stock, equal weights, dividends
  reinvested, held three years from each month end, against the CDI over
  the same three years. Consecutive months share most of their three
  years, so 150 monthly starts are closer to four or five independent
  periods: this describes the past, it is not a forecast.

Today's figures come from the daily screen (`data/market/today.json`) and
the weekly email carries them in one line.

## The weekly list and the track record

Every Monday (closing prices of the previous session) the top 10 by score,
and the top 10 by the Magic Formula, are appended to `data/picks/picks.csv`
with their prices. Nothing is ever removed, and a session's list, once
recorded, is never replaced: a re-run of the weekly job on the same session
keeps (and emails) the first one.

The track record holds each list as an **equal-weight portfolio until the
next list**, on adjusted prices (dividends reinvested), and compares it with
BOVA11 over the same sessions. A ticker that stops trading keeps its last
price. The return is measured from the close used to make the list, so it
assumes you could buy at that close; buying at Monday's open will differ.
The record is marked to the latest close by every daily run; only the
weekly job adds lists.

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
works steps down from Q1 to Q5. Through 2026: value's top two fifths
returned about 9% a year against 2–4% for the bottom three; momentum's top
fifth did best; the top fifth of quality did not beat the middle; growth's
top fifth did worst of all (from 2013, when growth can first be measured).
An earlier version showed the bottom fifths of value and of the score
losing 4–6% a year; much of that came from the market-cap errors fixed in
November 2026 (distressed companies with absurd market caps looked
extremely expensive), and with correct counts the bottom fifth of the score
returns about 0%. Fifteen yearly periods are a small sample: these results describe
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

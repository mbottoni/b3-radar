# b3-radar

**[Open the page →](https://mbottoni.github.io/b3-radar/)**

A daily screen of Brazilian stocks built only from official open data (B3,
CVM, Banco Central), a shortlist emailed every Monday, and a public track
record of every shortlist against BOVA11, losers included.

- **Daily** (Tue–Sat, 07:00 Brasília): new quotes, filings and corporate events
  are committed to `data/`; the screen is rebuilt.
- **Weekly** (Mon, 07:30 Brasília): the top 10 is logged, the track record
  updated, and the email sent.
- **Backtest** (monthly): the yearly list since 2012, bought each May and
  held, point in time, against BOVA11, the CDI and all eligible stocks; also
  each list held untouched for 1, 3 and 5 years.
- **[METHODOLOGY.md](METHODOLOGY.md)**: every rule, and every problem found in
  the data with how it is handled.

## Email setup

The weekly job emails only when three repository secrets exist (Settings →
Secrets and variables → Actions); until then it is a dry run and the
rendered email is kept as a workflow artifact.

| secret | value |
|---|---|
| `SMTP_USER` | the Gmail address that sends |
| `SMTP_PASSWORD` | a Google [App Password](https://myaccount.google.com/apppasswords) for it (needs 2-Step Verification) |
| `EMAIL_TO` | where the report goes |

## Run it locally

```bash
uv sync
uv run python -m b3radar daily     # fetch and rebuild data/
uv run python -m b3radar weekly    # list, track record, email (dry run without the env vars)
uv run python -m b3radar backtest  # yearly buy-and-hold backtest from data/
uv run pytest -q
```

## Data

```
data/prices/YYYY-MM.csv       daily quotes per ticker
data/cvm/                     companies, trading codes, extracted filings
data/events/                  dividends, JCP, splits; B3 share counts
data/screen/latest.csv        today's metrics, scores and exclusions
data/screen/history/          the screen behind each weekly list
data/picks/                   every list, the track record, per-list returns
data/backtest/                yearly buy-and-hold backtest since 2012
data/macro/cdi.csv            daily CDI since 2010
```

A rules-based screen of public data, not investment advice. Code: MIT.

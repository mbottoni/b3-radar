"""The weekly email: this week's shortlist, what changed, the market against
cash, the track record and the backtest's long view.

Charts are PNGs (b3radar.charts) embedded in the message (multipart/related,
``cid:`` links), since email clients run no scripts and Gmail strips SVG;
everything else is table HTML with inline styles, 640px wide.

Sent over SMTP (Gmail with an App Password by default). Credentials and the
recipient come only from environment variables (repo secrets in CI), never
from the repo. Without them it is a dry run: the email is written to out/
(with its images as files), which CI keeps as an artifact.
"""

from __future__ import annotations

import html
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import numpy as np
import pandas as pd

PAGE = "https://mbottoni.github.io/b3-radar/"
DISCLAIMER = ("A rules-based screen of public data (B3, CVM, Banco Central). It is not investment advice: "
              "the scores know nothing about news, governance or your situation. Do your own research.")

INK, INK2, MUTED, LINE, ACCENT, PAGE_BG, SURFACE = "#0b0b0b", "#52514e", "#6b6a65", "#e1e0d9", "#2a78d6", "#f4f4f1", "#ffffff"
GOOD, BAD = "#006300", "#d03b3b"
HI, LO = (42, 120, 214), (227, 73, 72)      # heat poles: the page's blue and red
FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and np.isnan(x)) and np.isfinite(float(x))


def _pct(x, digits=0, sign=False):
    if not _ok(x):
        return "–"
    return f"{x * 100:+.{digits}f}%" if sign else f"{x * 100:.{digits}f}%"


def _num(x, digits=1):
    return "–" if not _ok(x) else f"{x:.{digits}f}"


def _signed(x, digits=0):
    color = GOOD if _ok(x) and x > 0 else BAD if _ok(x) and x < 0 else MUTED
    arrow = "▲ " if _ok(x) and x > 0 else "▼ " if _ok(x) and x < 0 else ""
    return f'<span style="color:{color}">{arrow}{_pct(abs(x) if _ok(x) else x, digits)}</span>'


def _heat(v: float) -> str:
    """Background for a 0-100 percentile: blue above 50, red below (the page's
    tint, mixed with white here: email clients lack color-mix)."""
    if not _ok(v):
        return SURFACE
    t = max(-1.0, min(1.0, (v - 50) / 50))
    a = abs(t) * 0.46
    c = HI if t >= 0 else LO
    return "#" + "".join(f"{round(255 * (1 - a) + ch * a):02x}" for ch in c)


def _td(v, align="right", bold=False, bg=None, extra=""):
    w = "font-weight:600;" if bold else ""
    b = f"background:{bg};" if bg else ""
    return f'<td style="padding:7px 6px;border-bottom:1px solid {LINE};text-align:{align};{w}{b}{extra}">{v}</td>'


def _th(v, align="right"):
    return (f'<th style="padding:6px 6px;border-bottom:1px solid {LINE};text-align:{align};font-weight:600;'
            f'color:{MUTED};font-size:10px;letter-spacing:.06em;text-transform:uppercase">{v}</th>')


def _h(text):
    return (f'<p style="margin:26px 0 8px;font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;'
            f'color:{INK2}">{html.escape(text)}</p>')


def market_line(m: dict | None) -> str:
    """The market against cash, in one sentence (market.today's figures)."""
    if not m or m.get("earnings_yield") is None:
        return ""
    f = lambda k, d=1: _pct(m[k] if m.get(k) is not None else np.nan, d)  # noqa: E731
    out = f"The typical eligible stock earns {f('earnings_yield')} of its value a year (EBIT / EV)"
    if m.get("cheaper_than") is not None:
        out += (f", cheaper than {f('cheaper_than', 0)} of months since {m['history_from'][:4]}"
                f" (median {f('history_median')})")
    out += f". Cash: CDI {f('cdi')}"
    if m.get("real_cdi") is not None:
        out += f", {f('real_cdi')} after the last 12 months' inflation"
    return out + "."


def load_extras(data_dir: Path) -> dict:
    """Context the email shows beyond the list: market history, sparklines, backtest."""
    def csv(p):
        p = data_dir / p
        return pd.read_csv(p, dtype={"date": str}) if p.exists() else None

    def js(p):
        p = data_dir / p
        return json.loads(p.read_text()) if p.exists() else None
    return {"market_hist": csv("market/history.csv"), "sparks": js("screen/sparks.json"),
            "bt_summary": csv("backtest/summary.csv"), "bt_curve": csv("backtest/curve.csv"), "bt_meta": js("backtest/meta.json")}


def _market_reading(m: dict, hist: pd.DataFrame | None) -> str:
    gap = m["earnings_yield"] - m["real_cdi"] if m.get("real_cdi") is not None else np.nan
    out = html.escape(market_line(m))
    if hist is None or not _ok(gap):
        return out
    g = (hist.earnings_yield - hist.real_cdi).dropna()
    med = float(g.median())
    level = "above its usual level" if gap > med + 0.01 else "below its usual level" if gap < med - 0.01 else "around its usual level"
    out += (f" Against cash after inflation the gap is <b>{gap * 100:+.1f} pts</b>, {level} "
            f"(median {med * 100:+.1f} pts since {hist.date.iloc[0][:4]}).")
    f = hist.dropna(subset=["fwd_stocks", "fwd_cdi"]).assign(gap=lambda d: d.earnings_yield - d.real_cdi,
                                                              out=lambda d: d.fwd_stocks - d.fwd_cdi)
    if len(f) >= 30:
        f = f.sort_values("gap")
        lo, hi = f.out.iloc[: len(f) // 3].mean(), f.out.iloc[-(len(f) // 3):].mean()
        out += (f" So far a bigger gap has {'meant' if hi > lo else 'not meant'} better three years ahead: the largest third of "
                f"gaps was followed by stocks {_pct(hi, 1, True)} a year against the CDI, the smallest third by "
                f"{_pct(lo, 1, True)}. Context, not a timing signal.")
    return out


def build(screen: pd.DataFrame, picks: pd.DataFrame, entered: list[str], left: list[str],
          cohorts: pd.DataFrame, curve: pd.DataFrame, market: dict | None = None,
          data_dir: Path | None = None) -> tuple[str, str, str, dict[str, bytes]]:
    """(subject, html, text, images): images are PNG bytes by content id."""
    ex = load_extras(data_dir) if data_dir else {}
    images: dict[str, bytes] = {}
    try:
        from . import charts
    except ImportError:          # matplotlib missing: the email goes without charts
        charts = None

    def img(cid, png, w, h, alt):
        if not png:
            return ""
        images[cid] = png
        return (f'<img src="cid:{cid}" width="{w}" height="{h}" alt="{html.escape(alt)}" '
                f'style="display:block;width:{w}px;max-width:100%;height:auto;border:0">')

    asof = screen["asof"].iloc[0]
    eligible = int((screen.excluded.fillna("") == "").sum())
    top = picks[picks.strategy == "composite"].merge(
        screen[["ticker", "value_score", "quality_score", "momentum_score", "income_score", "pe", "ev_ebit", "roe",
                "momentum", "dividend_yield"]], on="ticker", how="left").sort_values("rank")
    magic = picks[picks.strategy == "magic"].sort_values("rank")
    sp = (ex.get("sparks") or {}).get("tickers", {})
    subject = f"B3 Radar · shortlist of {asof}: {', '.join(top.ticker.head(3))}…"

    # ---------------------------------------------------------- headline figures
    kpis = []
    b = (ex.get("sparks") or {}).get("bova11")
    if b:
        closes = [c for c in b["close"] if c is not None]
        week = closes[-1] / closes[-6] - 1 if len(closes) > 6 else np.nan
        kpis.append(("BOVA11", f"R$ {closes[-1]:.2f}", f"week {_signed(week, 1)} · 1Y {_signed(b.get('r1y'), 0)}"))
    if market and market.get("earnings_yield") is not None:
        kpis.append(("Earnings yield", _pct(market["earnings_yield"], 1),
                     f"typical stock · median {_pct(market.get('history_median'), 1)}"))
        kpis.append(("CDI", _pct(market.get("cdi"), 1), f"{_pct(market.get('real_cdi'), 1)} after inflation"))
    s = ex.get("bt_summary")
    if s is not None and len(s):
        by = s.set_index("series")
        kpis.append(("Backtest", f"{_pct(by.cagr.get('composite'), 1)} a year",
                     f"score since 2012 · BOVA11 {_pct(by.cagr.get('bova11'), 1)}"))
    kpi_html = ""
    if kpis:
        cells = "".join(
            f'<td width="{100 // len(kpis)}%" valign="top" style="padding:10px 12px;background:{SURFACE};border:1px solid {LINE};border-radius:8px">'
            f'<div style="font-size:11px;font-weight:700;color:{INK2}">{k}</div>'
            f'<div style="font-size:20px;font-weight:700;margin:2px 0;color:{INK}">{v}</div>'
            f'<div style="font-size:11px;color:{MUTED}">{sub}</div></td>' for k, v, sub in kpis)
        kpi_html = f'<table role="presentation" width="100%" cellspacing="6" cellpadding="0" style="border-collapse:separate;margin:0 -6px">{"".join(["<tr>", cells, "</tr>"])}</table>'

    # ------------------------------------------------------------ the shortlist
    rows = []
    for r in top.itertuples():
        t = html.escape(r.ticker)
        new = (f' <span style="background:#e8eef8;color:#1c5cab;font-size:9px;font-weight:700;padding:1px 4px;'
               f'border-radius:3px">NEW</span>' if r.ticker in entered else "")
        s_t = sp.get(r.ticker)
        trend = "–"
        if s_t and charts:
            trend = (img(f"spark-{t}@b3radar", charts.spark(s_t["w"]), 64, 18, f"{t} last 12 months")
                     .replace("display:block;", "display:inline-block;vertical-align:middle;")
                     + f'&nbsp;<span style="font-size:11px">{_signed(s_t.get("r1y"), 0)}</span>')
        name = (f'<a href="{PAGE}company.html?t={t}" style="color:{INK};font-weight:700;text-decoration:none">{t}</a>{new}'
                f'<div style="font-size:11px;color:{MUTED};max-width:150px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">'
                f'{html.escape(str(r.company))[:26]}</div>')
        rows.append("<tr>" + _td(r.rank, "center", extra=f"color:{MUTED}") + _td(name, "left")
                    + _td(trend, "left", extra="white-space:nowrap")
                    + _td(_num(r.score, 0), "center", True, _heat(r.score))
                    + "".join(_td(_num(v, 0), "center", bg=_heat(v)) for v in
                              (r.value_score, r.quality_score, r.momentum_score, r.income_score))
                    + _td(_num(r.pe)) + _td(_pct(r.dividend_yield, 1)) + _td(f"R$&nbsp;{r.price:.2f}") + "</tr>")
    table = (f"<table role='presentation' style='border-collapse:collapse;font-size:12px;width:100%;background:{SURFACE}'><tr>"
             + _th("#", "center") + _th("Company", "left") + _th("1 year", "left") + _th("Score", "center")
             + "".join(_th(x, "center") for x in "VQMI") + _th("P/E") + _th("Div. yld") + _th("Price")
             + "</tr>" + "".join(rows) + "</table>")
    changes = ""
    if entered or left:
        changes = (f"<p style='margin:10px 0 0;font-size:13px'><b>Entered:</b> {html.escape(', '.join(entered) or '—')}"
                   f" &nbsp;·&nbsp; <b>Left:</b> {html.escape(', '.join(left) or '—')}</p>")

    # ------------------------------------------------------------- the market
    market_html = ""
    if market and market.get("earnings_yield") is not None:
        hist = ex.get("market_hist")
        chart = img("market@b3radar", charts.market(hist, market), 600, 230,
                    "Earnings yield of the typical stock against the CDI since 2011") if charts and hist is not None and len(hist) > 2 else ""
        market_html = (_h("The market against cash") + chart
                       + f'<p style="margin:8px 0 0;font-size:13px;line-height:1.5;color:{INK}">{_market_reading(market, hist)}</p>')

    # ----------------------------------------------------------- track record
    c = curve[curve.strategy == "composite"] if len(curve) else curve
    if len(c) > 1:
        lines = []
        for strategy in ("composite", "magic"):
            cs = curve[curve.strategy == strategy]
            if len(cs) > 1:
                p_, b_ = cs.portfolio.iloc[-1] / 100 - 1, cs.benchmark.iloc[-1] / 100 - 1
                lines.append(f"<li><b>{strategy}</b> since {cs.date.iloc[0]}: {_signed(p_, 1)} vs BOVA11 "
                             f"{_signed(b_, 1)}</li>")
        recent = cohorts[cohorts.strategy == "composite"].sort_values("date").tail(4)
        cl = "".join(f"<li>{r.date}: {_signed(r['return'], 1)} vs {_signed(r.benchmark, 1)}, "
                     f"{_pct(r.hit_rate)} of picks up</li>" for _, r in recent.iterrows())
        live = img("record@b3radar", charts.record(curve), 600, 170, "The live lists against BOVA11") if charts else ""
        record = (live + f"<ul style='padding-left:18px;margin:8px 0;font-size:13px'>{''.join(lines)}</ul>"
                  f"<p style='margin:8px 0 2px;color:{MUTED};font-size:12px'>Recent lists, return to date:</p>"
                  f"<ul style='padding-left:18px;margin:4px 0;font-size:13px'>{cl}</ul>")
    else:
        first = picks.date.min() if len(picks) else asof
        record = (f"<p style='margin:0;font-size:13px;color:{INK2}'>Recording since {first}: the live record needs a few "
                  "weeks before it shows anything, and years before it means much.</p>")
    long_view = ""
    bc = ex.get("bt_curve")
    if bc is not None and len(bc) and s is not None:
        by = s.set_index("series")
        r100 = lambda k: f"R${100 * (1 + by.total_return.get(k)):.0f}"  # noqa: E731
        long_view = (_h("The long view: the backtest since 2012")
                     + (img("growth@b3radar", charts.growth(bc), 600, 230, "R$100 in the backtest's yearly list since 2012") if charts else "")
                     + f"<p style='margin:8px 0 0;font-size:13px;line-height:1.5'>R$100 in May 2012 became <b>{r100('composite')}</b> "
                       f"with the score's yearly top 10 ({_pct(by.cagr.get('composite'), 1)} a year), {r100('bova11')} in BOVA11 and "
                       f"{r100('cdi')} in the CDI; it beat BOVA11 in {by.years_beating_bova11.get('composite')} years. "
                       "Point in time, dividends reinvested, no costs or taxes.</p>")

    magic_links = ", ".join(f'<a href="{PAGE}company.html?t={html.escape(t)}" style="color:{ACCENT};text-decoration:none">{html.escape(t)}</a>'
                            for t in magic.ticker)
    button = (f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin:26px 0 0"><tr>'
              f'<td style="background:{ACCENT};border-radius:8px"><a href="{PAGE}" style="display:inline-block;padding:10px 18px;'
              f'color:#ffffff;font-weight:700;font-size:14px;text-decoration:none">Open the screener, the backtest and every company →</a></td></tr></table>')
    body = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(subject)}</title></head><body style="margin:0;padding:0;background:{PAGE_BG}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{PAGE_BG}"><tr><td align="center" style="padding:20px 10px">
<table role="presentation" width="640" cellspacing="0" cellpadding="0" style="width:640px;max-width:100%;font-family:{FONT};color:{INK}">
<tr><td style="padding:0 0 14px">
  <table role="presentation" cellspacing="0" cellpadding="0"><tr>
    <td style="background:{ACCENT};border-radius:7px;width:26px;height:26px;text-align:center;color:#fff;font-weight:700;font-size:14px">◎</td>
    <td style="padding-left:8px;font-size:16px;font-weight:700">B3 Radar <span style="font-weight:400;color:{MUTED}">· weekly shortlist</span></td>
  </tr></table>
  <h1 style="margin:14px 0 2px;font-size:22px">This week's shortlist</h1>
  <p style="margin:0;color:{MUTED};font-size:13px">Closing prices of {asof} · {eligible} companies passed the filters
  (liquidity, operating status, non-financial, a year of quotes, positive equity).</p>
</td></tr>
<tr><td>{kpi_html}</td></tr>
<tr><td style="padding-top:16px">{table}{changes}
<p style="margin:10px 0 0;color:{MUTED};font-size:11px;line-height:1.5">Score: equal mix of four percentiles in the eligible universe,
Value (EBIT/EV, book/price), Quality (ROIC, ROE, low leverage), Momentum (12-month return without the last month) and Income
(dividend yield). Cells blue above the median, red below. Tickers link to each company's page.</p></td></tr>
<tr><td>{market_html}</td></tr>
<tr><td>{_h("The live track record")}{record}</td></tr>
<tr><td>{long_view}</td></tr>
<tr><td>{_h("Magic Formula baseline")}<p style="margin:0;font-size:13px">{magic_links}</p></td></tr>
<tr><td>{button}</td></tr>
<tr><td style="padding-top:22px;color:{MUTED};font-size:11px;line-height:1.5">{html.escape(DISCLAIMER)}</td></tr>
</table></td></tr></table></body></html>"""

    text = [f"B3 Radar weekly shortlist, closing prices of {asof}", ""]
    for r in top.itertuples():
        s_t = sp.get(r.ticker) or {}
        text.append(f"{r.rank:>2}. {r.ticker:<7} {str(r.company)[:28]:<28} score {_num(r.score, 0):>3}  "
                    f"1Y {_pct(s_t.get('r1y'), 0, True):>5}  P/E {_num(r.pe)}  DY {_pct(r.dividend_yield, 1)}")
    if entered or left:
        text += ["", f"Entered: {', '.join(entered) or '-'}   Left: {', '.join(left) or '-'}"]
    if market_line(market):
        text += ["", market_line(market)]
    text += ["", f"Magic Formula baseline: {', '.join(magic.ticker)}", "", PAGE, "", DISCLAIMER]
    return subject, body, "\n".join(text), images


def send(subject: str, html_body: str, text: str, out_dir: Path, images: dict[str, bytes] | None = None) -> bool:
    """Send if SMTP_USER, SMTP_PASSWORD and EMAIL_TO are set; else dry run.
    The rendered email is always written to out/ (CI keeps it as an artifact),
    with its images as files so the HTML opens in a browser."""
    images = images or {}
    out_dir.mkdir(parents=True, exist_ok=True)
    preview = html_body
    for cid, png in images.items():
        name = cid.split("@")[0] + ".png"
        (out_dir / name).write_bytes(png)
        preview = preview.replace(f"cid:{cid}", name)
    (out_dir / "email.html").write_text(preview)
    (out_dir / "email.txt").write_text(text)
    user, password, to = (os.environ.get(k, "").strip() for k in ("SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"))
    if not (user and password and to):
        print("[email] dry run: SMTP_USER / SMTP_PASSWORD / EMAIL_TO not set; wrote out/email.html")
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    html_part = msg.get_payload()[1]
    for cid, png in images.items():   # inline: multipart/related, referenced as cid:...
        html_part.add_related(png, maintype="image", subtype="png", cid=f"<{cid}>", filename=cid.split("@")[0] + ".png")
    host, port = os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=60) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(user, password)
        s.send_message(msg)
    print(f"[email] sent to {len(to.split(','))} recipient(s), {len(images)} images, {len(msg.as_bytes()) // 1024} KB")
    return True

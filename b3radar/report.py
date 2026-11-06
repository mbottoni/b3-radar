"""The weekly email: this week's shortlist, what changed, the track record.

Sent over SMTP (Gmail with an App Password by default). Credentials and the
recipient come only from environment variables (repo secrets in CI), never
from the repo. Without them it is a dry run: the email is written to out/.
"""

from __future__ import annotations

import html
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

INK, MUTED, LINE, ACCENT = "#0b0b0b", "#6b6a65", "#e1e0d9", "#2a78d6"


def _pct(x, digits=0, sign=False):
    if x is None or not np.isfinite(x):
        return "–"
    return f"{x * 100:+.{digits}f}%" if sign else f"{x * 100:.{digits}f}%"


def _num(x, digits=1):
    return "–" if x is None or not np.isfinite(x) else f"{x:.{digits}f}"


def _td(v, align="right", bold=False):
    w = "font-weight:600;" if bold else ""
    return f'<td style="padding:6px 8px;border-bottom:1px solid {LINE};text-align:{align};{w}">{v}</td>'


def _th(v, align="right"):
    return (f'<th style="padding:6px 8px;border-bottom:2px solid {LINE};text-align:{align};font-weight:600;'
            f'color:{MUTED};font-size:12px">{v}</th>')


def build(screen: pd.DataFrame, picks: pd.DataFrame, entered: list[str], left: list[str],
          cohorts: pd.DataFrame, curve: pd.DataFrame) -> tuple[str, str, str]:
    """(subject, html, text)."""
    asof = screen["asof"].iloc[0]
    eligible = int((screen.excluded.fillna("") == "").sum())
    top = picks[picks.strategy == "composite"].merge(
        screen[["ticker", "value_score", "quality_score", "momentum_score", "income_score", "pe", "ev_ebit", "roe",
                "momentum", "dividend_yield"]], on="ticker", how="left").sort_values("rank")
    magic = picks[picks.strategy == "magic"].sort_values("rank")
    subject = f"b3-radar · weekly shortlist · {asof}"

    rows = []
    for r in top.itertuples():
        new = (f' <span style="color:{ACCENT};font-size:11px;font-weight:600">NEW</span>' if r.ticker in entered else "")
        why = " · ".join(f"{k} {int(round(v))}" for k, v in (("V", r.value_score), ("Q", r.quality_score),
                                                               ("M", r.momentum_score), ("I", r.income_score))
                         if np.isfinite(v))
        rows.append("<tr>" + _td(r.rank) + _td(f"<b>{html.escape(r.ticker)}</b>{new}", "left")
                    + _td(html.escape(str(r.company))[:34], "left") + _td(_num(r.score, 0), bold=True)
                    + _td(f'<span style="color:{MUTED}">{why}</span>', "left") + _td(_num(r.pe)) + _td(_num(r.ev_ebit))
                    + _td(_pct(r.roe)) + _td(_pct(r.momentum, sign=True)) + _td(_pct(r.dividend_yield, 1))
                    + _td(f"R$ {r.price:.2f}") + "</tr>")
    table = ("<table style='border-collapse:collapse;font-size:13px;width:100%'><tr>"
             + _th("#") + _th("Ticker", "left") + _th("Company", "left") + _th("Score") + _th("Why (0–100)", "left")
             + _th("P/E") + _th("EV/EBIT") + _th("ROE") + _th("12–1m") + _th("Div. yield") + _th("Price")
             + "</tr>" + "".join(rows) + "</table>")

    changes = ""
    if entered or left:
        changes = (f"<p style='margin:12px 0 0'><b>Entered:</b> {html.escape(', '.join(entered) or '—')}"
                   f" &nbsp;·&nbsp; <b>Left:</b> {html.escape(', '.join(left) or '—')}</p>")

    record = "<p style='color:%s'>First list: the track record starts next week.</p>" % MUTED
    c = curve[curve.strategy == "composite"]
    if len(c) > 1:
        lines = []
        for strategy in ("composite", "magic"):
            cs = curve[curve.strategy == strategy]
            if len(cs) > 1:
                p, b = cs.portfolio.iloc[-1] / 100 - 1, cs.benchmark.iloc[-1] / 100 - 1
                lines.append(f"<li><b>{strategy}</b> since {cs.date.iloc[0]}: {_pct(p, 1, True)} vs BOVA11 "
                             f"{_pct(b, 1, True)} ({_pct(p - b, 1, True)})</li>")
        recent = cohorts[cohorts.strategy == "composite"].sort_values("date").tail(4)
        cl = "".join(f"<li>{r.date}: {_pct(r['return'], 1, True)} vs {_pct(r.benchmark, 1, True)}, "
                     f"{_pct(r.hit_rate)} of picks up</li>" for _, r in recent.iterrows())
        record = f"<ul style='padding-left:18px;margin:6px 0'>{''.join(lines)}</ul>" \
                 f"<p style='margin:8px 0 2px;color:{MUTED}'>Recent lists, return to date:</p>" \
                 f"<ul style='padding-left:18px;margin:4px 0'>{cl}</ul>"

    magic_line = ", ".join(magic.ticker)
    body = f"""<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:{INK};max-width:880px">
<h2 style="margin:0 0 4px">This week's shortlist</h2>
<p style="margin:0 0 14px;color:{MUTED}">Closing prices of {asof} · {eligible} companies passed the filters
(liquidity, operating status, non-financial, a year of quotes, positive equity).</p>
{table}
{changes}
<p style="margin:10px 0 0;color:{MUTED};font-size:12px">Score: equal-weight mix of Value (EBIT/EV, book/price),
Quality (ROIC, ROE, low leverage), Momentum (12-month return excluding the last month) and Income (dividend yield),
each a percentile within the eligible universe.</p>
<h3 style="margin:22px 0 4px">Magic Formula baseline</h3>
<p style="margin:0">{html.escape(magic_line)}</p>
<h3 style="margin:22px 0 4px">Track record</h3>
{record}
<p style="margin:22px 0 0"><a href="{PAGE}" style="color:{ACCENT}">Full screener, every past list and the methodology →</a></p>
<p style="margin:18px 0 0;color:{MUTED};font-size:12px">{html.escape(DISCLAIMER)}</p>
</div>"""

    text = [f"b3-radar weekly shortlist, closing prices of {asof}", ""]
    for r in top.itertuples():
        text.append(f"{r.rank:>2}. {r.ticker:<7} {str(r.company)[:30]:<30} score {_num(r.score, 0):>3}  "
                    f"P/E {_num(r.pe)}  ROE {_pct(r.roe)}  12-1m {_pct(r.momentum, sign=True)}  DY {_pct(r.dividend_yield, 1)}")
    if entered or left:
        text += ["", f"Entered: {', '.join(entered) or '-'}   Left: {', '.join(left) or '-'}"]
    text += ["", f"Magic Formula baseline: {magic_line}", "", PAGE, "", DISCLAIMER]
    return subject, body, "\n".join(text)


def send(subject: str, html_body: str, text: str, out_dir: Path) -> bool:
    """Send if SMTP_USER, SMTP_PASSWORD and EMAIL_TO are set; else dry run.
    The rendered email is always written to out/ (CI keeps it as an artifact)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "email.html").write_text(html_body)
    (out_dir / "email.txt").write_text(text)
    user, password, to = (os.environ.get(k, "").strip() for k in ("SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"))
    if not (user and password and to):
        print("[email] dry run: SMTP_USER / SMTP_PASSWORD / EMAIL_TO not set; wrote out/email.html")
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    host, port = os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=60) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(user, password)
        s.send_message(msg)
    print(f"[email] sent to {len(to.split(','))} recipient(s)")
    return True

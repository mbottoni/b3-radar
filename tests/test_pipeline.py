"""Picks, track record, email, and the downloader against a misbehaving server."""

import io
import os
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pandas as pd
import pytest

from b3radar import fetch, picks, report


def write_prices(data_dir, rows):
    df = pd.DataFrame(rows, columns=["date", "ticker", "close"])
    df["isin"] = df.ticker + "ISIN"
    df["kind"] = np.where(df.ticker == "BOVA11", "ETF", "ON")
    df["open"] = df["high"] = df["low"] = df.close
    df["volume"], df["trades"] = 1e7, 100
    (data_dir / "prices").mkdir(parents=True, exist_ok=True)
    df[["date", "ticker", "isin", "kind", "open", "high", "low", "close", "volume", "trades"]] \
        .to_csv(data_dir / "prices" / "2026-11.csv", index=False)


def test_track_record_chains_lists_against_the_benchmark(tmp_path):
    write_prices(tmp_path, [
        ("2026-11-02", "AAA3", 10), ("2026-11-02", "BBB3", 10), ("2026-11-02", "BOVA11", 100),
        ("2026-11-09", "AAA3", 12), ("2026-11-09", "BBB3", 9), ("2026-11-09", "BOVA11", 101),
        ("2026-11-16", "AAA3", 12), ("2026-11-16", "BBB3", 9), ("2026-11-16", "BOVA11", 99.99),
    ])
    for d, names in (("2026-11-02", ["AAA3", "BBB3"]), ("2026-11-09", ["AAA3"])):
        picks.record(pd.DataFrame({"date": d, "strategy": "composite", "rank": range(1, len(names) + 1),
                                   "ticker": names, "company": "", "sector": "", "score": 1.0, "price": 0.0}), tmp_path)
    curve, cohorts = picks.performance(tmp_path, "2026-11-16")
    c = curve[curve.strategy == "composite"].set_index("date")
    assert c.portfolio.loc["2026-11-09"] == pytest.approx(105.0)      # (+20% - 10%) / 2
    assert c.portfolio.loc["2026-11-16"] == pytest.approx(105.0)      # AAA3 flat
    assert c.benchmark.loc["2026-11-16"] == pytest.approx(99.99)
    first = cohorts[(cohorts.strategy == "composite") & (cohorts.date == "2026-11-02")].iloc[0]
    assert first["return"] == pytest.approx(0.05) and first.hit_rate == 0.5
    assert picks.changes(picks.load(tmp_path)) == ([], ["BBB3"])


def test_email_dry_run_without_secrets(tmp_path, monkeypatch):
    for k in ("SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"):
        monkeypatch.delenv(k, raising=False)
    screen = pd.DataFrame({"asof": ["2026-11-06"] * 2, "ticker": ["AAA3", "BBB3"], "excluded": ["", "illiquid"],
                           "value_score": [80, 1], "quality_score": [70, 1], "momentum_score": [60, 1],
                           "income_score": [50, 1], "pe": [5.0, 1], "ev_ebit": [4.0, 1], "roe": [0.2, 0],
                           "momentum": [0.3, 0], "dividend_yield": [0.05, 0]})
    new = pd.DataFrame({"date": "2026-11-06", "strategy": ["composite", "magic"], "rank": [1, 1],
                        "ticker": ["AAA3", "AAA3"], "company": ["A <&> Co"] * 2, "sector": "", "score": [65.0, 65.0],
                        "price": [10.0, 10.0]})
    subject, body, text = report.build(screen, new, ["AAA3"], [], pd.DataFrame(), pd.DataFrame(columns=["strategy"]))
    assert "2026-11-06" in subject and "A &lt;&amp;&gt; Co" in body and "NEW" in body
    assert report.send(subject, body, text, tmp_path) is False
    assert (tmp_path / "email.html").exists() and "AAA3" in (tmp_path / "email.txt").read_text()
    m = {"earnings_yield": 0.129, "cheaper_than": 0.8, "history_from": "2011-05-31", "history_median": 0.105,
         "cdi": 0.136, "real_cdi": None}
    assert report.market_line(m) == ("The typical eligible stock earns 12.9% of its value a year (EBIT / EV), cheaper "
                                      "than 80% of months since 2011 (median 10.5%). Cash: CDI 13.6%.")
    assert "cheaper than 80%" in report.build(screen, new, ["AAA3"], [], pd.DataFrame(),
                                              pd.DataFrame(columns=["strategy"]), m)[1]


# ------------------------------------------------------------------ fetch

def zip_bytes(payload=b"x" * 5000):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.txt", payload)
    return buf.getvalue()


class Server(BaseHTTPRequestHandler):
    bodies: list = []      # served in order, one per GET; then the last one forever
    misses = 0             # leading 404s (HEAD and GET)

    def log_message(self, *a):
        pass

    def _send(self, head_only):
        if Server.misses > 0:
            Server.misses -= 1
            self.send_error(404)
            return
        body = Server.bodies[0]
        if not head_only and len(Server.bodies) > 1:
            Server.bodies.pop(0)
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", f'"{hash(body)}"')
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def do_HEAD(self):
        self._send(True)

    def do_GET(self):
        self._send(False)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Server)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/f.zip"
    srv.shutdown()


def test_truncated_zip_is_downloaded_again(server, tmp_path):
    good = zip_bytes()
    Server.bodies, Server.misses = [good[: len(good) // 2], good], 0   # B3 mid-rewrite, then the real file
    path = fetch.download_zip(server, tmp_path / "f.zip", wait=0, backoff=0)
    assert path.read_bytes() == good and fetch.zip_ok(path)


def test_transient_404_on_an_existing_file_is_retried(server, tmp_path):
    Server.bodies, Server.misses = [zip_bytes()], 2
    assert fetch.download(server, tmp_path / "f.zip", retry_404=2, wait_404=0, backoff=0) is not None
    Server.bodies, Server.misses = [zip_bytes()], 5
    assert fetch.download(server, tmp_path / "g.zip", retry_404=1, wait_404=0, backoff=0) is None


def test_rules_fingerprint_separates_track_records(tmp_path, monkeypatch):
    from b3radar import screen
    before = screen.rules_hash()
    monkeypatch.setitem(screen.WEIGHTS, "income", 0.0)
    assert screen.rules_hash() != before                      # any rule change -> new fingerprint
    monkeypatch.setitem(screen.WEIGHTS, "income", 0.25)
    assert screen.rules_hash() == before

    write_prices(tmp_path, [("2026-11-02", "AAA3", 10), ("2026-11-02", "BOVA11", 100),
                            ("2026-11-09", "AAA3", 12), ("2026-11-09", "BOVA11", 100),
                            ("2026-11-16", "AAA3", 6), ("2026-11-16", "BOVA11", 100)])
    for d, rules in (("2026-11-02", "old00000"), ("2026-11-09", "new11111")):
        picks.record(pd.DataFrame({"date": [d], "strategy": "composite", "rank": [1], "ticker": ["AAA3"], "company": "",
                                   "sector": "", "score": 1.0, "price": 0.0, "rules": rules}), tmp_path)
    curve, _ = picks.performance(tmp_path, "2026-11-16")
    old = curve[curve.rules == "old00000"].set_index("date").portfolio
    new = curve[curve.rules == "new11111"].set_index("date").portfolio
    assert list(old.index) == ["2026-11-02", "2026-11-09"]        # the old record ends when the new rules start
    assert old.iloc[-1] == pytest.approx(120.0)
    assert list(new.index) == ["2026-11-09", "2026-11-16"]        # the new one starts fresh at 100
    assert new.iloc[-1] == pytest.approx(50.0)


def test_an_unweighted_pillar_leaves_the_fingerprint_alone(monkeypatch):
    from b3radar import screen
    before = screen.rules_hash()
    assert screen.WEIGHTS["growth"] == 0
    monkeypatch.setattr(screen, "GROWTH_YEARS", 5)          # growth rules don't rank anything at weight 0
    assert screen.rules_hash() == before
    monkeypatch.setitem(screen.WEIGHTS, "growth", 0.2)
    assert screen.rules_hash() != before

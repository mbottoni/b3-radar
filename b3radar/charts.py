"""PNG charts for the weekly email (email clients run no scripts and Gmail
strips SVG, so charts travel as inline images). Same palette and rules as
the page: one axis, thin lines, direct labels, recessive grid; drawn at 2x
for sharp screens, on a light surface (clients do not follow the page's
theme)."""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.ticker  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

S1, S2, S3, OTHER = "#2a78d6", "#eb6834", "#1baf7a", "#b5b4ad"
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff"
WIDTH_PX = 600      # as displayed in the email
DPI = 200


def _fig(h_px: int):
    fig, ax = plt.subplots(figsize=(WIDTH_PX / 100, h_px / 100), dpi=DPI)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=7, length=0, pad=4)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    return fig, ax


def _years(ax, first, last, step=2):
    """Year ticks within the data only (the right margin holds the end labels)."""
    years = [y for y in range(pd.Timestamp(first).year + 1, pd.Timestamp(last).year + 1) if y % step == 0]
    ax.set_xticks([pd.Timestamp(f"{y}-01-01") for y in years], [str(y) for y in years])


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor=SURFACE, bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    return buf.getvalue()


def _end_labels(ax, items):
    """Direct labels at the right end of each line, nudged apart."""
    items = sorted(items, key=lambda t: t[1])
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * 0.07
    placed = []
    for x, y, text, color in items:
        if placed and y - placed[-1] < gap:
            y = placed[-1] + gap
        placed.append(y)
        ax.annotate(text, (x, y), xytext=(4, 0), textcoords="offset points", va="center", fontsize=7, color=INK)


def market(hist: pd.DataFrame, today: dict | None) -> bytes:
    """Earnings yield of the typical stock against the CDI, before and after inflation."""
    h = hist.copy()
    if today and today.get("date", "") > h.date.max():
        h = pd.concat([h, pd.DataFrame([{k: today.get(k) for k in ("date", "earnings_yield", "cdi", "real_cdi")}])])
    d = pd.to_datetime(h.date)
    fig, ax = _fig(230)
    lines = [("earnings_yield", S1, 1.8, "Earnings yield"), ("cdi", S2, 1.3, "CDI"), ("real_cdi", S3, 1.3, "CDI real")]
    ends = []
    for k, c, w, label in lines:
        v = pd.to_numeric(h[k], errors="coerce") * 100
        ax.plot(d, v, color=c, linewidth=w, solid_joinstyle="round")
        ends.append((d.iloc[-1], v.iloc[-1], f"{label} {v.iloc[-1]:.1f}%", c))
    ax.axhline(0, color=AXIS, linewidth=0.8)
    ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(5))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    _years(ax, d.iloc[0], d.iloc[-1])
    ax.set_xlim(d.iloc[0], d.iloc[-1] + pd.Timedelta(days=900))
    _end_labels(ax, ends)
    return _png(fig)


def growth(curve: pd.DataFrame) -> bytes:
    """R$100 in the backtest's first May: the score's yearly list against BOVA11 and the CDI (log scale)."""
    fig, ax = _fig(230)
    ends = []
    for k, c, w, label in (("composite", S1, 1.8, "Score"), ("bova11", S2, 1.3, "BOVA11"), ("cdi", S3, 1.3, "CDI")):
        g = curve[curve.series == k].sort_values("date")
        d, v = pd.to_datetime(g.date), g.value.astype(float)
        ax.plot(d, v, color=c, linewidth=w)
        ends.append((d.iloc[-1], v.iloc[-1], f"{label} R${v.iloc[-1]:.0f}", c))
    ax.set_yscale("log")
    ticks = [t for t in (50, 100, 200, 400, 800) if ax.get_ylim()[0] <= t <= ax.get_ylim()[1]]
    ax.set_yticks(ticks, [f"R${t}" for t in ticks])
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    _years(ax, curve.date.min(), curve.date.max())
    ax.set_xlim(right=pd.to_datetime(curve.date.max()) + pd.Timedelta(days=900))
    _end_labels(ax, ends)
    return _png(fig)


def record(perf: pd.DataFrame) -> bytes | None:
    """The live lists against BOVA11 (start = 100), once there are two points."""
    c = perf[perf.strategy == "composite"].sort_values("date")
    if len(c) < 2:
        return None
    d = pd.to_datetime(c.date)
    fig, ax = _fig(170)
    ax.plot(d, c.portfolio, color=S1, linewidth=1.8)
    ax.plot(d, c.benchmark, color=S2, linewidth=1.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.set_xlim(right=d.iloc[-1] + (d.iloc[-1] - d.iloc[0]) * 0.22)
    _end_labels(ax, [(d.iloc[-1], c.portfolio.iloc[-1], f"Lists {c.portfolio.iloc[-1]:.1f}", S1),
                     (d.iloc[-1], c.benchmark.iloc[-1], f"BOVA11 {c.benchmark.iloc[-1]:.1f}", S2)])
    return _png(fig)


def spark(values) -> bytes | None:
    """A 1-year price line for a table row (shown at 84x24)."""
    v = np.array([np.nan if x is None else float(x) for x in values])
    if np.isfinite(v).sum() < 2:
        return None
    fig = plt.figure(figsize=(0.84, 0.24), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    x = np.arange(len(v))
    ok = np.isfinite(v)
    ax.fill_between(x[ok], v[ok], np.nanmin(v), color=S1, alpha=0.13, linewidth=0)
    ax.plot(x[ok], v[ok], color=S1, linewidth=1.1)
    ax.plot(x[ok][-1], v[ok][-1], "o", color=S1, markersize=2)
    ax.set_xlim(-0.5, len(v) - 0.5)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()

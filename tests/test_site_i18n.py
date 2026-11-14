"""The site in two languages (docs/assets/i18n.js): the static HTML is Portuguese and carries its English.

Every text in docs/*.html must sit in an element with its English beside it (data-en, data-en-html) or
marked translate="no"; data-en must not wipe out child elements; data-en-html must keep the same tags and
links. The language code itself runs under Node (tests/i18n_check.mjs) when Node is installed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted((ROOT / "docs").glob("*.html"))
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
ATTRS = ("placeholder", "title", "aria-label")   # attributes a reader sees; each needs data-en-<attr>
LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)


class Tags(HTMLParser):
    """The tags and links in a fragment, to compare the two languages of a data-en-html."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs).get("href") or ""))


class Check(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, dict]] = []
        self.problems: list[str] = []
        self.inner: list[list[tuple[str, str]]] = []   # tags inside each open data-en-html element

    def where(self) -> str:
        return f"line {self.getpos()[0]}"

    def covered(self) -> bool:
        return any("data-en" in a or "data-en-html" in a or a.get("translate") == "no" for _, a in self.stack)

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        for _, parent in self.stack:
            if "data-en" in parent:
                self.problems.append(f"{self.where()}: <{tag}> inside a data-en element is lost in English; use data-en-html")
        for inner in self.inner:
            inner.append((tag, a.get("href", "")))
        for k in ("data-en", "data-en-html"):
            if k in a and not a[k].strip():
                self.problems.append(f"{self.where()}: empty {k}")
        for k in ATTRS + ("content",):
            if f"data-en-{k}" in a and k not in a:
                self.problems.append(f"{self.where()}: data-en-{k} without {k}")
        free = a.get("translate") == "no" or self.covered()
        for k in ATTRS:
            if a.get(k, "").strip() and LETTERS.search(a[k]) and f"data-en-{k}" not in a and not free:
                self.problems.append(f"{self.where()}: {k}={a[k]!r} has no data-en-{k}")
        if tag == "meta" and a.get("name") == "description" and "data-en-content" not in a:
            self.problems.append(f"{self.where()}: meta description has no data-en-content")
        if tag in VOID:
            return
        self.stack.append((tag, a))
        if "data-en-html" in a:
            self.inner.append([])

    def handle_endtag(self, tag):
        if tag in VOID or not self.stack:
            return
        while self.stack:
            t, a = self.stack.pop()
            if "data-en-html" in a:
                pt = self.inner.pop()
                en = Tags()
                en.feed(a["data-en-html"])
                if pt != en.tags:
                    self.problems.append(f"{self.where()}: data-en-html has tags {en.tags}, the Portuguese {pt}")
            if t == tag:
                break

    def handle_data(self, data):
        if any(t in ("script", "style") for t, _ in self.stack):
            return
        text = data.strip()
        if not text or not LETTERS.search(text):
            return
        if not any(t in ("body", "title") for t, _ in self.stack):
            return
        if not self.covered():
            self.problems.append(f"{self.where()}: {text[:60]!r} has no English (data-en, data-en-html or translate=\"no\")")


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_static_text_has_english(page):
    html = page.read_text(encoding="utf-8")
    assert '<html lang="pt-BR">' in html, "pages are written in Portuguese"
    assert re.search(r'<script src="assets/i18n\.js"></script>\s*<script src="assets/common\.js">', html), "i18n.js loads before common.js"
    c = Check()
    c.feed(html)
    c.close()
    assert not c.problems, "\n".join(c.problems)


def test_data_en_elements_have_text():
    """Both languages present on every marked element."""
    for page in PAGES:
        html = page.read_text(encoding="utf-8")
        for m in re.finditer(r'<(\w+)[^>]*\sdata-en="([^"]*)"[^>]*>([^<]*)</\1>', html):
            assert m.group(2).strip() and m.group(3).strip(), f"{page.name}: {m.group(0)[:80]}"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_language_code_under_node():
    r = subprocess.run(["node", str(ROOT / "tests" / "i18n_check.mjs")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout

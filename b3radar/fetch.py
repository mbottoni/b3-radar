"""Downloads that survive flaky government servers.

Large files resume with ``Range`` requests guarded by ``If-Range`` (so a
resumed transfer never splices two versions of a file), and a file whose
ETag and size have not changed is not downloaded again. Adapted from
camara-graphs, where the Câmara's server dropped long transfers routinely.
"""

from __future__ import annotations

import http.client
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# The usual bot convention: names us and links the repo. B3 answers 404 to
# daily quote files unless the agent starts with "Mozilla/5.0", so the
# prefix is required, but nothing here pretends to be a browser.
USER_AGENT = "Mozilla/5.0 (compatible; b3-radar/0.1; +https://github.com/mbottoni/b3-radar)"
CHUNK = 1 << 20


def log(msg: str) -> None:
    print(f"[fetch] {msg}", file=sys.stderr)


def _req(url: str, method: str = "GET", headers: dict | None = None) -> urllib.request.Request:
    return urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})


def get_json(url: str, *, attempts: int = 4, timeout: float = 30, backoff: float = 2.0):
    """GET a small JSON document with retries. Returns None on 404."""
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(_req(url), timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err: Exception = e
        except (urllib.error.URLError, http.client.HTTPException, OSError, json.JSONDecodeError) as e:
            err = e
        if attempt < attempts:
            time.sleep(min(backoff**attempt, 20))
    raise RuntimeError(f"GET {url} failed {attempts} times: {err}")


def zip_ok(path: Path) -> bool:
    """A complete, CRC-clean zip. Servers that regenerate a file in place
    (B3 rewrites its yearly quote file every evening) can serve a truncated
    copy whose Content-Length matches, so size checks alone are not enough."""
    import zipfile

    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None
    except (zipfile.BadZipFile, OSError, EOFError):
        return False


def download_zip(url: str, dest: Path, *, tries: int = 4, wait: float = 60, **kw) -> Path | None:
    """``download`` plus an integrity check; a corrupt zip is discarded and
    fetched again after ``wait`` seconds."""
    for attempt in range(1, tries + 1):
        path = download(url, dest, **kw)
        if path is None or zip_ok(path):
            return path
        log(f"{dest.name}: corrupt zip (server mid-update?); retry {attempt}/{tries} in {wait:.0f}s")
        for p in (dest, dest.with_name(dest.name + ".json")):
            p.unlink(missing_ok=True)
        if attempt < tries:
            time.sleep(wait)
    raise RuntimeError(f"{url}: still corrupt after {tries} downloads")


def download(url: str, dest: Path, *, attempts: int = 8, timeout: float = 60, backoff: float = 2.0,
             retry_404: int = 0, wait_404: float = 20) -> Path | None:
    """Download ``url`` to ``dest``; ``None`` if the server says 404.

    Skips the transfer when a sidecar records the same ETag and size. B3's
    servers intermittently answer 404 for a file that exists (seen on a
    fresh daily file), so ``retry_404`` re-asks before believing it, and a
    previously verified local copy is used if the server still says 404.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta, part, pmeta = dest.with_name(dest.name + ".json"), dest.with_name(dest.name + ".part"), \
        dest.with_name(dest.name + ".part.json")

    head, misses = None, 0
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(_req(url, "HEAD"), timeout=timeout) as r:
                head = {"size": int(r.headers.get("Content-Length") or -1), "etag": r.headers.get("ETag", ""),
                        "last_modified": r.headers.get("Last-Modified", "")}
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                if dest.exists() and meta.exists():
                    return dest
                if misses < retry_404:
                    misses += 1
                    log(f"{dest.name}: 404, asking again ({misses}/{retry_404}) in {wait_404:.0f}s")
                    time.sleep(wait_404)
                    continue
                return None
            err: Exception = e
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            err = e
        log(f"{dest.name}: HEAD failed ({err}); retry {attempt}/{attempts}")
        time.sleep(min(backoff**attempt, 30))
    if head is None:
        raise RuntimeError(f"HEAD {url} failed {attempts} times")

    if dest.exists() and meta.exists() and head["size"] >= 0 and dest.stat().st_size == head["size"]:
        if json.loads(meta.read_text()) == head:
            return dest

    src = head
    if part.exists() and pmeta.exists():
        src = json.loads(pmeta.read_text())
    else:
        part.write_bytes(b"")
    for attempt in range(1, attempts + 1):
        have = part.stat().st_size
        if src["size"] >= 0 and have == src["size"]:
            break
        if src["size"] >= 0 and have > src["size"]:
            part.write_bytes(b"")
            have = 0
        headers = {"Range": f"bytes={have}-", "If-Range": src["etag"] or src["last_modified"]} if have else {}
        try:
            with urllib.request.urlopen(_req(url, headers=headers), timeout=timeout) as r:
                if r.status == 200:
                    src = {"size": int(r.headers.get("Content-Length") or -1), "etag": r.headers.get("ETag", ""),
                           "last_modified": r.headers.get("Last-Modified", "")}
                    pmeta.write_text(json.dumps(src))
                    mode = "wb"
                elif r.status == 206:
                    mode = "ab"
                else:
                    raise RuntimeError(f"unexpected HTTP {r.status} for {url}")
                with part.open(mode) as f:
                    while chunk := r.read(CHUNK):
                        f.write(chunk)
            if src["size"] < 0:      # no Content-Length: a clean EOF is the end
                break
        except urllib.error.HTTPError as e:
            if e.code == 416 and part.stat().st_size == src["size"]:
                break
            log(f"{dest.name}: HTTP {e.code}; restarting in a moment")
            part.write_bytes(b"")
            time.sleep(min(backoff**attempt, 30))
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            log(f"{dest.name}: dropped at {part.stat().st_size:,} bytes ({e.__class__.__name__}); retry {attempt}/{attempts}")
            time.sleep(min(backoff**attempt, 30))
    else:
        raise RuntimeError(f"GET {url} did not complete after {attempts} attempts")
    if src["size"] >= 0 and part.stat().st_size != src["size"]:
        raise RuntimeError(f"{url}: got {part.stat().st_size} bytes, expected {src['size']}")
    part.replace(dest)
    pmeta.unlink(missing_ok=True)
    meta.write_text(json.dumps(src))
    log(f"{dest.name}: {dest.stat().st_size:,} bytes")
    return dest

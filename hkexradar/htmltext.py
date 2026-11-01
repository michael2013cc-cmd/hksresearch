from __future__ import annotations

import html as html_lib
import re

import httpx

_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def html_to_text(html_text: str) -> str:
    text = _SCRIPT.sub(" ", html_text)
    text = _TAG.sub(" ", text)
    return _SPACE.sub(" ", html_lib.unescape(text)).strip()


def fetch_html_text(url: str, *, timeout: float = 60.0,
                    client: httpx.Client | None = None) -> str:
    owns_client = client is None
    client = client or httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; hkexradar/0.1)"},
    )
    try:
        response = client.get(url)
        response.raise_for_status()
        return html_to_text(response.text)
    finally:
        if owns_client:
            client.close()

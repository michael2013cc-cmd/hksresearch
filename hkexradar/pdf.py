from __future__ import annotations

import re
import subprocess
from pathlib import Path

import httpx

_DISCLAIMER_START = "對本公告的內容概不負責"
_DISCLAIMER_END = "承擔任何責任。"
_CJK_GAP = re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])")


def pdf_filename(news_id: str) -> str:
    return f"{news_id}.pdf"


def download_pdf(url: str, dest: Path, *, timeout: float = 60,
                 client: httpx.Client | None = None) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return True
    owns_client = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        response = client.get(url)
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"):
            return False
        dest.write_bytes(response.content)
        return True
    except Exception:  # noqa: BLE001 - a single download failure only degrades that row
        return False
    finally:
        if owns_client:
            client.close()


def _tighten_cjk(text: str) -> str:
    return _CJK_GAP.sub("", text)


def _strip_disclaimer(text: str) -> str:
    start = text.find(_DISCLAIMER_START)
    if start == -1 or start > 400:
        return text
    end = text.find(_DISCLAIMER_END, start)
    if end == -1:
        return text
    return text[end + len(_DISCLAIMER_END):].lstrip()


def extract_text(path: Path, max_chars: int = 6000) -> tuple[str, str]:
    if not path.exists():
        return "", "unavailable"
    try:
        process = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", "-f", "1", "-l", "5", str(path), "-"],
            capture_output=True,
            timeout=60,
        )
    except Exception:  # noqa: BLE001
        return "", "unavailable"
    if process.returncode != 0:
        return "", "unavailable"
    text = process.stdout.decode("utf-8", errors="ignore").strip()
    text = _strip_disclaimer(_tighten_cjk(" ".join(text.split())))
    if not text:
        return "", "unavailable"
    return text[:max_chars], "ok"

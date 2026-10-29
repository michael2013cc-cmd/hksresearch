from pathlib import Path

import httpx

from hkexradar.pdf import (
    _strip_disclaimer,
    _tighten_cjk,
    download_pdf,
    extract_text,
    pdf_filename,
)

FIXTURE_PDF = Path(__file__).resolve().parent / "fixtures" / "sample.pdf"


def test_tighten_cjk_removes_spacing_artifacts():
    assert _tighten_cjk("香 港 交 易 所 2026 年") == "香港交易所 2026 年"


def test_strip_disclaimer_drops_header_block():
    text = (
        "香港交易及結算所有限公司對本公告的內容概不負責，對其準確性亦不發表任何聲明，"
        "概不會就因本公告而引致的任何損失承擔任何責任。茲提述本公司日期為九月一日的公告。"
    )
    assert _strip_disclaimer(text).startswith("茲提述")


def test_extract_text_from_real_pdf():
    text, status = extract_text(FIXTURE_PDF)
    assert status == "ok"
    assert len(text) > 100


def test_extract_text_missing_file_degrades():
    assert extract_text(Path("does-not-exist.pdf")) == ("", "unavailable")


def test_extract_text_respects_max_chars():
    text, status = extract_text(FIXTURE_PDF, max_chars=50)
    assert status == "ok"
    assert len(text) <= 50


def test_pdf_filename_is_news_id():
    assert pdf_filename("12325368") == "12325368.pdf"


def test_download_pdf_skips_existing(tmp_path: Path):
    dest = tmp_path / "1.pdf"
    dest.write_bytes(b"%PDF-1.4 existing")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=b"%PDF-1.4 new")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert download_pdf("https://example.com/a.pdf", dest, client=client) is True
    assert calls["n"] == 0
    assert dest.read_bytes().startswith(b"%PDF-1.4 existing")


def test_download_pdf_rejects_non_pdf(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not a pdf</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dest = tmp_path / "2.pdf"
    assert download_pdf("https://example.com/a.pdf", dest, client=client) is False
    assert not dest.exists()


def test_download_pdf_writes_body(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4 hello")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dest = tmp_path / "3.pdf"
    assert download_pdf("https://example.com/a.pdf", dest, client=client) is True
    assert dest.read_bytes() == b"%PDF-1.4 hello"

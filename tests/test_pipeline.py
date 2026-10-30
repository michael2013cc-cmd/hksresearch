from datetime import time
from pathlib import Path

from hkexradar.models import Announcement
from hkexradar.pipeline import _attach_pdf, run_day

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "2026-09-08.json"


def test_non_pdf_link_is_skipped_without_download(tmp_path: Path):
    ann = Announcement(
        news_id="1",
        primary_code="00001",
        stock_name="示例",
        published_at="2026-10-29T09:00:00",
        title="交易所通告 - 短暫停牌",
        doc_group="公告及通告",
        category_label="公告及通告",
        file_url="https://example.com/a.htm",
    )
    _attach_pdf(ann, tmp_path)
    assert ann.text_status == "skipped"


def test_full_chain_offline_produces_report(tmp_path: Path):
    report = run_day(
        "2026-09-08",
        root=ROOT,
        raw_path=FIXTURE,
        download_pdf=False,
        out_dir=tmp_path,
        read_top_n=0,
    )
    assert report.total == 590
    assert 80 <= report.candidate_count <= 150
    assert len(report.top) == 20
    assert report.top[0].final_score >= report.top[-1].final_score
    assert report.grade_counts
    assert report.overview
    assert (tmp_path / "2026-09-08-hkex-daily.md").exists()
    assert (tmp_path / "2026-09-08-hkex-daily.json").exists()


def test_from_time_keeps_only_the_window(tmp_path: Path):
    report = run_day(
        "2026-09-08", root=ROOT, raw_path=FIXTURE,
        download_pdf=False, out_dir=tmp_path, read_top_n=0,
        from_time=time(21, 0),
    )
    assert 0 < report.total < 590
    assert report.window_from == "21:00"
    assert all(item.announcement.published_at.time() >= time(21, 0)
               for item in report.ranked)
    text = (tmp_path / "2026-09-08-hkex-daily.md").read_text(encoding="utf-8")
    assert "統計窗口：21:00 起" in text


def test_scores_are_sorted_descending(tmp_path: Path):
    report = run_day(
        "2026-09-08", root=ROOT, raw_path=FIXTURE,
        download_pdf=False, out_dir=tmp_path, read_top_n=0,
    )
    scores = [item.final_score for item in report.top]
    assert scores == sorted(scores, reverse=True)

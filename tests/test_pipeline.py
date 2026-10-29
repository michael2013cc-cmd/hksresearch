from pathlib import Path

from hkexradar.pipeline import run_day

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "2026-09-08.json"


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


def test_scores_are_sorted_descending(tmp_path: Path):
    report = run_day(
        "2026-09-08", root=ROOT, raw_path=FIXTURE,
        download_pdf=False, out_dir=tmp_path, read_top_n=0,
    )
    scores = [item.final_score for item in report.top]
    assert scores == sorted(scores, reverse=True)

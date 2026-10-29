from __future__ import annotations

import argparse
from pathlib import Path

from .config import api_key, load_settings
from .llm import LLMClient
from .pipeline import run_day


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HKEX daily announcement radar")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--offline", type=Path, default=None, help="replay a saved snapshot")
    parser.add_argument("--no-llm", action="store_true", help="use rule summaries only")
    parser.add_argument("--limit", type=int, default=None, help="max announcements to read")
    parser.add_argument("--no-pdf", action="store_true", help="skip pdf download")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root)
    llm = None
    if not args.no_llm:
        key = api_key(settings)
        if key:
            llm = LLMClient(
                base_url=settings["llm"]["base_url"],
                api_key=key,
                model=settings["llm"]["model"],
                cache_dir=root / "data" / "cache" / "insights",
                timeout=settings["llm"]["timeout_seconds"],
            )
        else:
            print("warning: no API key, falling back to rule summaries")

    report = run_day(
        args.date,
        root=root,
        llm=llm,
        raw_path=args.offline,
        download_pdf=not args.no_pdf,
        read_top_n=args.limit,
    )
    print(f"total={report.total} candidates={report.candidate_count} "
          f"read={report.read_count} top={len(report.top)}")
    print(f"report: {root / 'reports' / (args.date + '-hkex-daily.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

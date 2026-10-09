import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.screener import build_batch_report, screen_directory


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Screen and rank resumes from a folder.")
    parser.add_argument("--input", default="resumes", help="Directory containing PDF/DOCX/TXT resumes")
    parser.add_argument("--output", default="output/results.json", help="Path to output JSON")
    parser.add_argument("--no-github", action="store_true", help="Skip GitHub API enrichment (useful for offline runs)")
    args = parser.parse_args()

    try:
        result = screen_directory(args.input, use_github=not args.no_github)
    except (NotADirectoryError, OSError) as exc:
        parser.error(str(exc))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    report = build_batch_report(result, args.input)
    report_path = output_path.with_name("screening_report.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Processed: {report['batch_summary']['total_processed']}")
    print(f"Eligible: {report['batch_summary']['eligible_count']}")
    print(f"Rejected: {report['batch_summary']['rejected_count']}")
    print(f"Results array: {output_path.resolve()}")
    print(f"Batch report: {report_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

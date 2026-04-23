"""Run resume compatibility regression tests and export machine/human readable reports."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = BACKEND_ROOT / "tests"
ARTIFACT_DIR = TEST_ROOT / "artifacts"

# Keep this suite focused on resume compatibility and extraction regressions.
TEST_PATTERNS = [
    "test_resume_text_extraction.py",
    "test_resume_compatibility_tracking.py",
]


def _collect_suite() -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    for pattern in TEST_PATTERNS:
        suite.addTests(loader.discover(str(TEST_ROOT), pattern=pattern))
    return suite


def _build_failure_items(label: str, entries: list[tuple[unittest.case.TestCase, str]]) -> list[dict]:
    return [{"type": label, "test": test.id(), "traceback": traceback_text} for test, traceback_text in entries]


def _write_reports(result: unittest.result.TestResult, started_at: datetime, finished_at: datetime) -> tuple[Path, Path]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    failures = _build_failure_items("failure", result.failures)
    errors = _build_failure_items("error", result.errors)

    report_payload = {
        "suite": "resume_compatibility",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "patterns": TEST_PATTERNS,
        "counts": {
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "expected_failures": len(result.expectedFailures),
            "unexpected_successes": len(result.unexpectedSuccesses),
        },
        "failed_items": failures + errors,
        "skipped_items": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        "success": result.wasSuccessful(),
    }

    json_path = ARTIFACT_DIR / "resume-compat-results.json"
    json_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_lines = [
        "# Resume Compatibility Test Report",
        "",
        f"- Started: `{report_payload['started_at']}`",
        f"- Finished: `{report_payload['finished_at']}`",
        f"- Duration: `{report_payload['duration_seconds']}s`",
        f"- Tests: `{result.testsRun}`",
        f"- Failures: `{len(result.failures)}`",
        f"- Errors: `{len(result.errors)}`",
        f"- Skipped: `{len(result.skipped)}`",
        f"- Result: `{'PASS' if report_payload['success'] else 'FAIL'}`",
        "",
        "## Included Test Files",
        "",
    ]

    markdown_lines.extend([f"- `{pattern}`" for pattern in TEST_PATTERNS])
    markdown_lines.append("")

    if report_payload["failed_items"]:
        markdown_lines.extend(["## Failures", ""])
        for item in report_payload["failed_items"]:
            markdown_lines.extend(
                [
                    f"### {item['test']}",
                    "",
                    f"- Type: `{item['type']}`",
                    "- Traceback:",
                    "```text",
                    item["traceback"].rstrip(),
                    "```",
                    "",
                ]
            )
    else:
        markdown_lines.extend(["## Failures", "", "No failures.", ""])

    md_path = ARTIFACT_DIR / "resume-compat-report.md"
    md_path.write_text("\n".join(markdown_lines), encoding="utf-8")

    return json_path, md_path


def main() -> int:
    started_at = datetime.now()
    suite = _collect_suite()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    finished_at = datetime.now()

    json_path, md_path = _write_reports(result, started_at, finished_at)
    print(f"[compat-suite] JSON report: {json_path}")
    print(f"[compat-suite] Markdown report: {md_path}")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())


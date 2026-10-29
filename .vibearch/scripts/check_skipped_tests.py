#!/usr/bin/env python3
"""check_skipped_tests.py — Stage 6 gate: no silent gaps in the suite.

A skipped test is an untested requirement wearing a green badge. The most common cause
is the one this pipeline is built to prevent: "Postgres/RabbitMQ isn't available in CI,
so skip the integration tests" — which is precisely how a system reaches 95% coverage
and still fails every user journey.

This script finds skips two ways:
  1. Statically, by scanning test sources for skip/pending/ignore markers.
  2. Dynamically, by scanning a test-run log for a non-zero skipped count, if given.

It writes `release_evidence/skipped_tests_report.txt`. Empty file = release may proceed.
Non-empty = the report lists every skip and the script exits 1.

Usage:
  python3 scripts/check_skipped_tests.py --tests tests
  python3 scripts/check_skipped_tests.py --tests tests --log release_evidence/smoke_test_transcript.log
  python3 scripts/check_skipped_tests.py --tests tests --out release_evidence/skipped_tests_report.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import Report, is_test_file, read_text, repo_root, strip_comments, test_files_in  # noqa: E402

SKIP_MARKERS = [
    ("pytest.mark.skip", r"@pytest\.mark\.skip\b"),
    ("pytest.mark.skipif", r"@pytest\.mark\.skipif\b"),
    ("pytest.mark.xfail", r"@pytest\.mark\.xfail\b"),
    ("pytest.skip()", r"\bpytest\.skip\s*\("),
    ("pytest.importorskip", r"\bpytest\.importorskip\s*\("),
    ("unittest.skip", r"@unittest\.skip(?:If|Unless)?\b|\bself\.skipTest\s*\("),
    ("jest/vitest skip", r"\b(?:describe|it|test|context)\s*\.\s*(?:skip|todo|failing)\s*\("),
    ("xit/xdescribe", r"\bx(?:it|describe|test|context)\s*\("),
    ("mocha pending", r"\bit\s*\(\s*['\"][^'\"]*['\"]\s*\)\s*;", ),
    ("go t.Skip", r"\bt\s*\.\s*Skip(?:Now|f)?\s*\("),
    ("JUnit @Ignore/@Disabled", r"@Ignore\b|@Disabled\b"),
    ("rspec pending/skip", r"\b(?:pending|skip)\s+['\"]"),
    ("phpunit markTestSkipped", r"\bmarkTestSkipped\s*\(|\bmarkTestIncomplete\s*\("),
    ("commented-out test", r"^\s*(?://|#)\s*(?:def\s+test_|it\s*\(|test\s*\(|func\s+Test)"),
]

LOG_SKIP_COUNTS = [
    r"(\d+)\s+skipped",
    r"skipped[:=]\s*(\d+)",
    r"(\d+)\s+pending",
    r"(\d+)\s+ignored",
    r"(\d+)\s+xfailed",
]

_MARKERS = [(name, re.compile(pattern, re.M)) for name, pattern in SKIP_MARKERS]


def rel(path: Path, root: Path) -> str:
    """Relative path when possible — `Path.is_relative_to` is 3.9+, this is 3.8-safe."""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Stage 6 skipped-test gate.")
    parser.add_argument("--tests", nargs="+", default=["tests"], help="test roots to scan")
    parser.add_argument("--log", action="append", default=[],
                        help="test-run log(s) to scan for skipped counts (repeatable)")
    parser.add_argument("--out", default="release_evidence/skipped_tests_report.txt")
    args = parser.parse_args(argv)

    root = repo_root()
    report = Report("skipped tests")
    findings: list[str] = []

    existing = []
    for raw in args.tests:
        path = Path(raw) if Path(raw).is_absolute() else root / raw
        if path.exists():
            existing.append(path)
        else:
            report.warn(f"{raw} does not exist — skipped")

    files = [p for p in test_files_in(existing) if is_test_file(p)] or test_files_in(existing)
    for path in files:
        text = read_text(path)
        body = strip_comments(text, path.suffix)
        lines = text.splitlines()
        for name, rx in _MARKERS:
            # commented-out tests must be found in the raw text, not the stripped body
            haystack = text if name == "commented-out test" else body
            for match in rx.finditer(haystack):
                lineno = haystack.count("\n", 0, match.start()) + 1
                snippet = (lines[lineno - 1].strip() if lineno - 1 < len(lines) else match.group(0))
                findings.append(f"{rel(path, root)}:{lineno}: {name} — {snippet[:100]}")

    for raw_log in args.log:
        log_path = Path(raw_log) if Path(raw_log).is_absolute() else root / raw_log
        if not log_path.exists():
            report.warn(f"{raw_log} does not exist — not scanned")
            continue
        text = read_text(log_path)
        for pattern in LOG_SKIP_COUNTS:
            for match in re.finditer(pattern, text, re.I):
                if int(match.group(1)) > 0:
                    line_start = text.rfind("\n", 0, match.start()) + 1
                    line_end = text.find("\n", match.end())
                    line = text[line_start:line_end if line_end > 0 else len(text)].strip()
                    findings.append(f"{raw_log}: run reported skips — {line[:120]}")

    findings = sorted(set(findings))

    out_path = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(("\n".join(findings) + "\n") if findings else "", encoding="utf-8")
    report.note(f"wrote {args.out} ({len(findings)} entr{'y' if len(findings) == 1 else 'ies'})")

    for finding in findings:
        report.fail(finding)
    if findings:
        report.fail(
            f"{len(findings)} skipped/pending test(s) — a release cannot ship with silent gaps. "
            "Either make the test run for real (containers for DB/broker) or delete it and "
            "record the gap as a spec amendment."
        )

    return report.finish(f"{len(files)} test file(s) scanned, no skips")


if __name__ == "__main__":
    sys.exit(main())

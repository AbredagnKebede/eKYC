#!/usr/bin/env python3
"""check_journey_coverage.py — the journey loop's real coverage gate.

Component loops are gated on 85% line coverage. Journey loops are gated on something
stricter and more honest: **100% of the assertion points** written down in the journey
file must be verified by a test.

The link is an id. `journey_mapper` numbers every assertion point `AP-<n>` inside the
journey's `## Assertion Points` section; the journey loop's tests must cite that id in
a test name, docstring, or comment. Anything uncited is an unverified claim.

Usage:
  python3 scripts/check_journey_coverage.py \
      --journey journeys/journey_01_book-a-session.md \
      --tests tests/journey

Exit 0 = every assertion point cited. Exit 1 = the uncited ones are listed.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import Report, find_section, read_text, test_files_in  # noqa: E402

AP_ID = re.compile(r"\bAP-(\d{1,3})\b")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Journey assertion-point coverage gate.")
    parser.add_argument("--journey", required=True, help="path to journeys/journey_<nn>_<slug>.md")
    parser.add_argument("--tests", nargs="+", required=True, help="the loop's journey test dirs")
    args = parser.parse_args(argv)

    report = Report("journey assertion-point coverage")

    journey_path = Path(args.journey)
    if not journey_path.exists():
        report.fail(f"{journey_path} does not exist")
        return report.finish()

    text = read_text(journey_path)
    _, body = find_section(text, title_contains="assertion points")
    if body is None:
        report.fail(f"{journey_path} has no `## Assertion Points` section")
        return report.finish()

    points: dict[str, str] = {}
    for line in body.splitlines():
        match = AP_ID.search(line)
        if match and re.match(r"^\s*(?:[-*+]|\d+\.)\s", line):
            points[match.group(1).lstrip("0") or "0"] = line.strip(" -*+\t")

    unnumbered = [
        ln.strip(" -*+\t") for ln in body.splitlines()
        if re.match(r"^\s*(?:[-*+]|\d+\.)\s+\S", ln) and not AP_ID.search(ln)
    ]
    for line in unnumbered:
        report.fail(
            f"{journey_path}: assertion point has no `AP-<n>` id — {line[:80]!r}. "
            "Every assertion point needs an id so a test can cite it."
        )

    if not points:
        report.fail(f"{journey_path}: `## Assertion Points` declares no `AP-<n>` items")
        return report.finish()

    existing = [Path(p) for p in args.tests if Path(p).exists()]
    for raw in args.tests:
        if not Path(raw).exists():
            report.warn(f"{raw} does not exist — skipped")
    files = test_files_in(existing)
    if not files:
        report.fail(f"no journey tests found under: {', '.join(args.tests)}")
        return report.finish()

    cited: dict[str, list[str]] = {}
    for path in files:
        for match in AP_ID.finditer(read_text(path)):
            cited.setdefault(match.group(1).lstrip("0") or "0", []).append(path.name)

    for num in sorted(points, key=int):
        if num not in cited:
            report.fail(
                f"AP-{num} is not verified by any test — {points[num][:90]!r}"
            )

    stray = sorted(set(cited) - set(points), key=int)
    for num in stray:
        report.warn(
            f"tests cite AP-{num}, which {journey_path.name} does not define "
            f"(in {', '.join(sorted(set(cited[num])))})"
        )

    return report.finish(
        f"{len(points)} assertion point(s), all cited across {len(files)} journey test file(s)"
    )


if __name__ == "__main__":
    sys.exit(main())

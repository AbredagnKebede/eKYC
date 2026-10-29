#!/usr/bin/env python3
"""check_assertions.py — assertion-density gate, called from every loop's verify.sh.

Stops a loop from padding its test count with tests that assert nothing meaningful.
Per test file:

  * fail when strong assertions < code_lines / RATIO           (default 1 per 10 lines)
  * fail when weak assertions > WEAK_MAX x total assertions    (default 30%)

"Strong" means the assertion pins a value, shape, error, or status code. "Weak" means
`assert True`, `assert x is not None`, `expect(x).toBeDefined()` — true of almost any
run, so it proves almost nothing.

Usage:
  python3 scripts/check_assertions.py tests/unit tests/integration
  python3 scripts/check_assertions.py --ratio 10 --weak-max 0.3 tests/
  python3 scripts/check_assertions.py --min-lines 15 tests/journey

Exits 0 when every file passes (and at least one test file was found), 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import Report, is_test_file, read_text, score_assertions, test_files_in  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Assertion-density gate.")
    parser.add_argument("paths", nargs="+", help="test files or directories to score")
    parser.add_argument("--ratio", type=float, default=10.0,
                        help="one strong assertion per N code lines (default 10)")
    parser.add_argument("--weak-max", type=float, default=0.3,
                        help="max fraction of assertions allowed to be weak (default 0.3)")
    parser.add_argument("--min-lines", type=int, default=8,
                        help="skip density scoring for files below this many code lines")
    parser.add_argument("--allow-empty", action="store_true",
                        help="pass when no test files are found (default: fail)")
    args = parser.parse_args(argv)

    report = Report("assertion density")

    existing = [Path(p) for p in args.paths if Path(p).exists()]
    missing = [p for p in args.paths if not Path(p).exists()]
    for path in missing:
        report.warn(f"{path} does not exist — skipped")

    candidates = test_files_in(existing)
    files = [p for p in candidates if is_test_file(p)] or [
        p for p in candidates if p.parent.name in {"unit", "component", "integration",
                                                   "contract", "journey", "chaos"}
    ]

    if not files:
        if args.allow_empty:
            return report.finish("no test files found (--allow-empty)")
        report.fail(f"no test files found under: {', '.join(str(p) for p in args.paths)}")
        return report.finish()

    total_strong = total_weak = total_lines = 0
    for path in files:
        lines, strong, weak = score_assertions(read_text(path), path.suffix)
        total_lines += lines
        total_strong += strong
        total_weak += weak
        assertions = strong + weak

        if assertions == 0:
            report.fail(f"{path}: no assertions found in {lines} code lines")
            continue

        if lines >= args.min_lines:
            required = lines / args.ratio
            if strong < required:
                report.fail(
                    f"{path}: only {strong} strong assertion(s) in {lines} code lines "
                    f"(need >= {required:.1f}); {weak} weak"
                )

        if weak > assertions * args.weak_max:
            report.fail(
                f"{path}: {weak}/{assertions} assertions are weak "
                f"(max {args.weak_max:.0%}) — replace `is not None`/`toBeDefined`-style "
                "checks with assertions that pin the value"
            )

    return report.finish(
        f"{len(files)} test file(s), {total_strong} strong / {total_weak} weak "
        f"assertions over {total_lines} code lines"
    )


if __name__ == "__main__":
    sys.exit(main())

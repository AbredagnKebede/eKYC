#!/usr/bin/env python3
"""check_mocks.py — the "no silent mocks" gate, called from every loop's verify.sh.

Three modes, one per loop type:

  --mode component   A loop that touches a real boundary (db / queue / external_api /
                     worker) must prove at least one test crosses it for real.
                     Mocks stay legal in tests/unit and tests/component.

  --mode journey     A journey loop is black-box or it is nothing. At least one test
                     must carry a `black_box` marker, and NO test under tests/journey
                     may mock the database, broker, worker process, or external API.

  --mode chaos       Failure injection is legal (that is the point), but the
                     boundaries under test must still be real, so the same no-mock rules
                     apply to everything except the fault-injection seam. The `black_box`
                     marker is not required here — that is a journey-loop rule.

Boundaries come from `--boundaries db,queue,external_api,worker`, which the roadmap
agent derives from the loop's `system_graph.json` edges (`stores`/`publishes`/
`consumes`/`calls`).

Escape hatch: a `vibearch: allow-mock(<boundary>)` comment in a test file exempts that
file for that boundary. It is deliberately visible in the diff — an argued exception,
not a silent one.

Usage:
  python3 scripts/check_mocks.py --mode journey  --boundaries db,queue --tests tests/journey
  python3 scripts/check_mocks.py --mode component --boundaries db --tests tests/unit tests/integration

Exit 0 = pass. Exit 1 = failures printed to stderr.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import (  # noqa: E402
    BLACK_BOX_MARKER, Report, detect_mocks, detect_real_boundary, is_test_file,
    read_text, test_files_in,
)

VALID_BOUNDARIES = ("db", "queue", "external_api", "worker")


def collect(paths, report) -> list[Path]:
    existing = []
    for raw in paths:
        path = Path(raw)
        if path.exists():
            existing.append(path)
        else:
            report.warn(f"{raw} does not exist — skipped")
    candidates = test_files_in(existing)
    files = [p for p in candidates if is_test_file(p)]
    return files or candidates


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="No-silent-mocks gate.")
    parser.add_argument("--mode", required=True, choices=("component", "journey", "chaos"))
    parser.add_argument("--tests", nargs="+", required=True,
                        help="test dirs/files to inspect")
    parser.add_argument("--boundaries", default="",
                        help="comma-separated: db,queue,external_api,worker")
    parser.add_argument("--real-tests", nargs="*", default=None,
                        help="component mode: dirs that must contain the real-boundary "
                             "test (default: the --tests paths named integration/journey)")
    args = parser.parse_args(argv)

    report = Report(f"no-silent-mocks ({args.mode})")

    boundaries = [b.strip() for b in args.boundaries.split(",") if b.strip()]
    for boundary in boundaries:
        if boundary not in VALID_BOUNDARIES:
            report.fail(f"unknown boundary {boundary!r} — expected one of {', '.join(VALID_BOUNDARIES)}")
    boundaries = [b for b in boundaries if b in VALID_BOUNDARIES]

    files = collect(args.tests, report)
    if not files:
        report.fail(f"no test files found under: {', '.join(args.tests)}")
        return report.finish()

    if args.mode == "component":
        if not boundaries:
            return report.finish("loop touches no critical boundary — nothing to prove")

        real_roots = args.real_tests if args.real_tests is not None else [
            p for p in args.tests
            if Path(p).name in {"integration", "contract", "journey"}
        ]
        real_files = collect(real_roots, report) if real_roots else []
        pool = real_files or files
        if not real_files:
            report.warn(
                "no tests/integration or tests/contract directory given — scanning all "
                "supplied tests for real-boundary evidence instead"
            )

        proven = set()
        for path in pool:
            text = read_text(path)
            crossed = detect_real_boundary(text, boundaries)
            if not crossed:
                continue
            # Evidence only counts if this file is not faking the same boundary.
            faked = {
                f.split(" boundary faked")[0]
                for f in detect_mocks(text, path.suffix, crossed)
                if " boundary faked" in f
            }
            proven |= (crossed - faked)

        # See the note in journey mode: worker liveness comes from verify.sh's
        # `require_services`, not from text in a test file.
        for boundary in [b for b in boundaries if b != "worker"]:
            if boundary not in proven:
                report.fail(
                    f"loop touches the {boundary} boundary but no test exercises it for real "
                    f"— every test mocks or fakes it. Add a tests/integration test that uses a "
                    f"real {boundary} (container, sandbox, or live dependency)."
                )
        return report.finish(
            f"real boundary proven for: {', '.join(sorted(proven)) or 'none required'}"
        )

    # ---- journey / chaos: real boundaries throughout
    black_box_files = [p for p in files if BLACK_BOX_MARKER.search(read_text(p))]
    if args.mode == "journey" and not black_box_files:
        report.fail(
            "no test carries a `black_box` marker — a journey loop needs at least one "
            "test declared black-box (pytest: `@pytest.mark.black_box`; jest: a "
            "`black_box` tag in the test name; go: `// black_box`)"
        )

    enforced = boundaries or list(VALID_BOUNDARIES)
    for path in files:
        text = read_text(path)
        findings = detect_mocks(text, path.suffix, enforced)
        for finding in findings:
            report.fail(
                f"{path}: {finding} — {args.mode} tests must run against real boundaries. "
                "Use a container/sandbox, or justify the exception with a "
                "`vibearch: allow-mock(<boundary>)` comment."
            )

    # A test file can only show textual evidence of boundaries it addresses directly —
    # a connection string, a sandbox URL. Worker liveness is established by verify.sh
    # calling `require_services`, not by anything written in the test, so requiring
    # textual proof of it here would fail correct tests. Worker MOCKS are still caught
    # above; only the positive-evidence requirement is skipped.
    evidence_required = [b for b in boundaries if b != "worker"]
    crossed = set()
    for path in files:
        crossed |= detect_real_boundary(read_text(path), enforced)
    for boundary in evidence_required:
        if boundary not in crossed:
            report.fail(
                f"no {args.mode} test shows evidence of reaching the real {boundary} "
                f"(no connection string, container, or sandbox reference found)"
            )

    return report.finish(
        f"{len(files)} test file(s), {len(black_box_files)} black-box, "
        f"real boundaries reached: {', '.join(sorted(crossed)) or 'none'}"
    )


if __name__ == "__main__":
    sys.exit(main())

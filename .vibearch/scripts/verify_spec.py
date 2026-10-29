#!/usr/bin/env python3
"""verify_spec.py — Stage-3 freeze gate.

Checks, in order:
  1. `dependency_list.md` exists.
  2. Every `ArchitecturalDecisions/ADR-*.md` is `status: accepted` with a real Decision
     and Rationale.
  3. `system_guide.md` header carries `spec_version` and an `amendments:` pointer.
     (`frozen: true` is NOT checked here — the architect sets it *after* this gate passes.)
  4. All ten required sections are present and substantive.
  5. §8 Acceptance Scenarios gives every scenario a stable `AS-<nn>` id — the anchor the
     journey_mapper stage builds on.
  6. §9 Resilience and Failure Modes has non-empty §9.1–§9.4. A spec that never says what
     happens when a token expires or a worker crashes cannot be tested for it.
  7. §10 Deployment names its artifacts in backticks, so Stage 6 knows what to build.
  8. `system_graph.json` parses, every node maps to a guide section, and topology nodes
     carry the fields the Stage 4 topology validator needs.

Exit 0 = pass. Exit 1 = failures printed to stderr.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import (  # noqa: E402
    Report, deployment_artifacts, find_section, is_substantive, load_json, read_text, repo_root,
)

REQUIRED_SECTIONS = [
    ("1", "Overview"),
    ("2", "Data Model"),
    ("3", "APIs"),
    ("4", "State Machines"),
    ("5", "Event Contracts"),
    ("6", "Security"),
    ("7", "SLOs"),
    ("8", "Acceptance Scenarios"),
    ("9", "Resilience and Failure Modes"),
    ("10", "Deployment"),
]

RESILIENCE_SUBSECTIONS = [
    ("9.1", "Time-Dependent Behavior", "credential TTL, refresh strategy, expiry behavior"),
    ("9.2", "Timeout and Retry Policy", "timeout ms, retry count, backoff, circuit breaker"),
    ("9.3", "Idempotency and Concurrency", "idempotency key, duplicate window, concurrent behavior"),
    ("9.4", "Partial Failure Scenarios", "compensation strategy, dead-letter policy"),
]

NODE_TYPES = {"service", "model", "job", "ui", "queue", "event", "external_api", "worker"}
EDGE_TYPES = {"calls", "stores", "publishes", "consumes", "depends"}

SCENARIO_ID = re.compile(r"\bAS-(\d{1,3})\b")


def main() -> int:
    root = repo_root()
    report = Report("spec")

    # ---- 1. dependency_list.md
    if not (root / "dependency_list.md").exists():
        report.fail("dependency_list.md does not exist")

    # ---- 2. ADRs
    adr_dir = root / "ArchitecturalDecisions"
    adrs = []
    if not adr_dir.is_dir():
        report.fail("ArchitecturalDecisions/ directory does not exist")
    else:
        adrs = sorted(adr_dir.glob("ADR-*.md"))
        if not adrs:
            report.fail("ArchitecturalDecisions/ contains no ADR-*.md files")
        for adr in adrs:
            text = read_text(adr)
            if re.search(r"^status:\s*superseded-by\b", text, re.M):
                continue
            if not re.search(r"^status:\s*accepted\s*$", text, re.M):
                report.fail(f"{adr.name} — not 'status: accepted'")
            for section in ("Decision", "Rationale"):
                _, body = find_section(text, title_contains=section)
                if body is None:
                    report.fail(f"{adr.name} — missing ## {section} section")
                elif not is_substantive(body, min_chars=20):
                    report.fail(f"{adr.name} — ## {section} is empty or a placeholder")

    # ---- 3./4. system_guide.md
    guide_path = root / "system_guide.md"
    guide = read_text(guide_path)
    if not guide:
        report.fail("system_guide.md does not exist or is empty")
        return report.finish()

    if not re.search(r"^spec_version:\s*\d+", guide, re.M):
        report.fail("system_guide.md header has no `spec_version: <n>`")
    if not re.search(r"^amendments:\s*\S", guide, re.M):
        report.fail("system_guide.md header has no `amendments:` pointer to spec_amendments/INDEX.md")

    bodies = {}
    for number, title in REQUIRED_SECTIONS:
        heading, body = find_section(guide, number=number)
        if body is None:
            heading, body = find_section(guide, title_contains=title)
        if body is None:
            report.fail(f"system_guide.md is missing `## {number} {title}`")
            continue
        bodies[number] = body
        if not is_substantive(body, min_chars=60):
            report.fail(f"system_guide.md §{number} {title} is empty or a placeholder")

    # ---- 5. acceptance scenario ids
    scenarios = bodies.get("8", "")
    scenario_ids = sorted(set(SCENARIO_ID.findall(scenarios)), key=int)
    if scenarios and not scenario_ids:
        report.fail(
            "system_guide.md §8 declares no `AS-<nn>` scenario ids — give every acceptance "
            "scenario a stable id (e.g. `### 8.1 AS-01: Book a session`) so Stage 4.5 can map "
            "each one to a journey"
        )
    duplicates = [i for i in scenario_ids if scenarios.count(f"AS-{int(i):02d}:") > 1]
    for dup in sorted(set(duplicates)):
        report.fail(f"system_guide.md §8 defines AS-{int(dup):02d} more than once")

    # ---- 6. resilience subsections
    resilience = bodies.get("9")
    if resilience:
        for number, title, expects in RESILIENCE_SUBSECTIONS:
            _, sub = find_section(resilience, number=number, level=3)
            if sub is None:
                _, sub = find_section(resilience, title_contains=title, level=3)
            if sub is None:
                report.fail(f"system_guide.md is missing `### {number} {title}`")
            elif not is_substantive(sub, min_chars=40):
                report.fail(
                    f"system_guide.md §{number} {title} is empty — it must specify {expects}"
                )

    # ---- 7. deployment artifacts named
    deployment = bodies.get("10")
    if deployment:
        if not deployment_artifacts(deployment):
            report.fail(
                "system_guide.md §10 Deployment names no artifact paths in backticks — Stage 6 "
                "needs to know which Dockerfile/compose/k8s manifests to build"
            )

    # ---- 8. system_graph.json
    graph, err = load_json(root / "system_graph.json", default={})
    if err:
        report.fail(err)
        return report.finish()

    nodes = graph.get("nodes", [])
    if not nodes:
        report.fail("system_graph.json declares no nodes")

    seen_ids = set()
    for node in nodes:
        nid = node.get("id", "")
        if not nid:
            report.fail(f"system_graph.json node {node!r} has no id")
            continue
        if nid in seen_ids:
            report.fail(f"system_graph.json defines node {nid!r} twice")
        seen_ids.add(nid)

        ntype = node.get("type", "")
        if ntype not in NODE_TYPES:
            report.fail(
                f"node {nid!r} has type {ntype!r} — expected one of {', '.join(sorted(NODE_TYPES))}"
            )

        section = node.get("spec_section", "")
        if not section:
            report.fail(f"node {nid!r} has no spec_section")
        elif section.lstrip("§") not in guide and section not in guide:
            report.fail(f"node {nid!r} references {section!r}, which is not in system_guide.md")

        # Topology nodes carry the extra fields Stage 4 and Stage 6 depend on.
        if ntype == "queue" and not (node.get("queue_name") or node.get("label")):
            report.fail(f"queue node {nid!r} has no `queue_name` (or label) to match against code")
        if ntype == "event" and not (node.get("event_name") or node.get("label")):
            report.fail(f"event node {nid!r} has no `event_name` (or label)")
        if ntype == "external_api":
            if not node.get("credential_env"):
                report.fail(f"external_api node {nid!r} has no `credential_env`")
            if not (node.get("sandbox_env") or node.get("sandbox_base_url")):
                report.fail(
                    f"external_api node {nid!r} has no `sandbox_env`/`sandbox_base_url` — journey "
                    "tests must have a real sandbox to call instead of a mock"
                )
        if ntype == "worker" and not node.get("process_entrypoint"):
            report.fail(
                f"worker node {nid!r} has no `process_entrypoint` — a worker that is not a "
                "runnable process can only be tested by direct function call, which proves "
                "nothing about the queue"
            )

    for edge in graph.get("edges", []):
        src, dst, etype = edge.get("from"), edge.get("to"), edge.get("type")
        if src not in seen_ids:
            report.fail(f"edge {src!r} -> {dst!r}: 'from' is not a known node")
        if dst not in seen_ids:
            report.fail(f"edge {src!r} -> {dst!r}: 'to' is not a known node")
        if etype not in EDGE_TYPES:
            report.fail(
                f"edge {src!r} -> {dst!r} has type {etype!r} — expected one of "
                f"{', '.join(sorted(EDGE_TYPES))}"
            )

    accepted = len([a for a in adrs if re.search(r"^status:\s*accepted\s*$", read_text(a), re.M)])
    return report.finish(
        f"{len(nodes)} graph nodes, {len(scenario_ids)} acceptance scenarios, {accepted} ADRs accepted"
    )


if __name__ == "__main__":
    sys.exit(main())

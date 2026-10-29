#!/usr/bin/env python3
"""check_journeys.py — Stage 4.5 (journey_mapper) gate.

Proves the journey map is complete and machine-usable before any loop is scaffolded:

  1. Every acceptance scenario in `system_guide.md §8` has exactly one journey file.
  2. Every journey file carries the required frontmatter and the four required sections.
  3. Every journey declares at least one assertion point and one failure mode.
  4. Every `graph_nodes` entry resolves to a real node in `system_graph.json`.
  5. `journeys/INDEX.md` lists every journey file, and nothing that does not exist.

Exit 0 = pass. Exit 1 = failures printed to stderr.

Usage: python3 scripts/check_journeys.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import (  # noqa: E402
    Report, find_section, is_substantive, load_json, read_text, repo_root, split_sections,
)

REQUIRED_SECTIONS = (
    ("User Steps", r"user\s+steps"),
    ("Required System Components", r"required\s+system\s+components"),
    ("Assertion Points", r"assertion\s+points"),
    ("Failure Modes to Test", r"failure\s+modes"),
)

SCENARIO_ID = re.compile(r"\bAS-(\d{1,3})\b")
JOURNEY_FILE = re.compile(r"^journey_(\d{2,3})_[a-z0-9][a-z0-9-]*\.md$")
PRIORITIES = {"critical", "high", "normal"}


def frontmatter(text: str) -> dict:
    """Parse the `key: value` block between the `# Journey:` title and the first `##`."""
    head = re.split(r"^##\s", text, maxsplit=1, flags=re.M)[0]
    fields = {}
    for line in head.splitlines():
        match = re.match(r"^([a-z_]+)\s*:\s*(.+?)\s*$", line.strip())
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def parse_list(value: str) -> list[str]:
    return [item.strip().strip("`\"'") for item in value.strip("[] ").split(",") if item.strip(" []")]


def bullet_count(body: str) -> int:
    return len([
        ln for ln in (body or "").splitlines()
        if re.match(r"^\s*(?:[-*+]|\d+\.)\s+\S", ln)
    ])


def main() -> int:
    root = repo_root()
    report = Report("journey map")

    guide = read_text(root / "system_guide.md")
    if not guide:
        report.fail("system_guide.md does not exist or is empty — run the architect stage first")
        return report.finish()

    graph, graph_err = load_json(root / "system_graph.json", default={})
    if graph_err:
        report.fail(graph_err)
    node_ids = {n.get("id") for n in (graph or {}).get("nodes", [])}

    # ---- 1. acceptance scenarios must be identified as AS-<nn>
    heading, scenarios_body = find_section(guide, number="8")
    if scenarios_body is None:
        heading, scenarios_body = find_section(guide, title_contains="acceptance scenario")
    if scenarios_body is None:
        report.fail("system_guide.md has no `## 8 Acceptance Scenarios` section")
        return report.finish()

    scenario_ids = sorted({str(int(n)) for n in SCENARIO_ID.findall(scenarios_body)}, key=int)
    if not scenario_ids:
        report.fail(
            "system_guide.md §8 declares no `AS-<nn>` scenario ids — the architect must "
            "give every acceptance scenario a stable id (e.g. `### 8.1 AS-01: ...`)"
        )
        return report.finish()

    # ---- 2. journey files
    journeys_dir = root / "journeys"
    if not journeys_dir.is_dir():
        report.fail("journeys/ directory does not exist — run the journey_mapper stage")
        return report.finish()

    journey_files = sorted(
        p for p in journeys_dir.glob("journey_*.md") if JOURNEY_FILE.match(p.name)
    )
    malformed = sorted(
        p.name for p in journeys_dir.glob("*.md")
        if p.name != "INDEX.md" and not JOURNEY_FILE.match(p.name)
    )
    for name in malformed:
        report.fail(f"journeys/{name} — filename must match journey_<nn>_<slug>.md")

    if not journey_files:
        report.fail("journeys/ contains no journey_<nn>_<slug>.md files")
        return report.finish()

    covered: dict[str, list[str]] = {}
    journey_ids: dict[str, str] = {}

    for path in journey_files:
        text = read_text(path)
        rel = f"journeys/{path.name}"

        if not re.search(r"^#\s+Journey:\s*\S", text, re.M):
            report.fail(f"{rel} — missing `# Journey: <name>` title line")

        meta = frontmatter(text)

        jid = meta.get("journey_id", "")
        if not re.match(r"^J-\d{2,3}$", jid):
            report.fail(f"{rel} — `journey_id:` must be `J-<nn>` (got {jid or 'nothing'!r})")
        elif jid in journey_ids:
            report.fail(f"{rel} — journey_id {jid} already used by {journey_ids[jid]}")
        else:
            journey_ids[jid] = rel

        priority = meta.get("priority", "").lower()
        if priority not in PRIORITIES:
            report.fail(
                f"{rel} — `priority:` must be one of {'/'.join(sorted(PRIORITIES))} "
                f"(got {meta.get('priority', '') or 'nothing'!r})"
            )

        covers = parse_list(meta.get("covers", ""))
        if not covers:
            report.fail(f"{rel} — `covers:` must list at least one `AS-<nn>` scenario id")
        for scenario in covers:
            match = SCENARIO_ID.search(scenario)
            if not match:
                report.fail(f"{rel} — `covers:` entry {scenario!r} is not an `AS-<nn>` id")
                continue
            num = str(int(match.group(1)))
            if num not in scenario_ids:
                report.fail(
                    f"{rel} — covers AS-{int(match.group(1)):02d}, which does not appear in "
                    "system_guide.md §8"
                )
            covered.setdefault(num, []).append(rel)

        nodes = parse_list(meta.get("graph_nodes", ""))
        if not nodes:
            report.fail(
                f"{rel} — `graph_nodes:` must list the system_graph.json nodes this journey "
                "touches (this is the coverage anchor)"
            )
        for node in nodes:
            if node_ids and node not in node_ids:
                report.fail(f"{rel} — graph_nodes entry {node!r} is not a node in system_graph.json")

        # required sections
        found = {title.lower(): body for title, body in split_sections(text, level=2)}
        for label, pattern in REQUIRED_SECTIONS:
            match_body = next(
                (body for title, body in found.items() if re.search(pattern, title)), None
            )
            if match_body is None:
                report.fail(f"{rel} — missing `## {label}` section")
            elif not is_substantive(match_body, min_chars=20):
                report.fail(f"{rel} — `## {label}` is empty or a placeholder")
            elif label in {"Assertion Points", "Failure Modes to Test", "User Steps"}:
                count = bullet_count(match_body)
                minimum = 2 if label == "User Steps" else 1
                if count < minimum:
                    report.fail(
                        f"{rel} — `## {label}` needs at least {minimum} enumerated item(s), found {count}"
                    )

    # ---- 3. every scenario covered exactly once
    for num in scenario_ids:
        owners = covered.get(num, [])
        if not owners:
            report.fail(
                f"acceptance scenario AS-{int(num):02d} has no journey file — "
                "every §8 scenario must map to exactly one journey"
            )
        elif len(owners) > 1:
            report.fail(
                f"acceptance scenario AS-{int(num):02d} is claimed by {len(owners)} journeys: "
                + ", ".join(owners)
            )

    # ---- 4. INDEX.md parity
    index_path = journeys_dir / "INDEX.md"
    if not index_path.exists():
        report.fail("journeys/INDEX.md does not exist")
    else:
        index_text = read_text(index_path)
        for path in journey_files:
            if path.name not in index_text:
                report.fail(f"journeys/INDEX.md does not list {path.name}")
        for name in re.findall(r"journey_\d{2,3}_[a-z0-9-]+\.md", index_text):
            if not (journeys_dir / name).exists():
                report.fail(f"journeys/INDEX.md references {name}, which does not exist")

    return report.finish(
        f"{len(journey_files)} journeys covering {len(scenario_ids)} acceptance scenarios"
    )


if __name__ == "__main__":
    sys.exit(main())

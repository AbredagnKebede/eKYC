#!/usr/bin/env python3
"""check_dag.py — Stage-4 loop DAG gate.

The pipeline now has three loop types, and their ordering is the whole point:

    loop_unit_<nn>_<slug>      component loops   (DB, auth, domain logic)
              |
              v
    loop_journey_<nn>_<slug>   journey loops     (one per user journey, real boundaries)
              |
              v
    loop_chaos                 chaos loop        (time-dependent + failure modes)

Checks:
  1. Every `system_graph.json` node is covered by exactly one COMPONENT loop.
  2. Every `journeys/journey_*.md` file has exactly one journey loop, and that loop's
     `status.json.journey_file` points back at it.
  3. `loop_chaos` exists, and no loop is named after an in-process end-to-end suite —
     that shape goes green on direct function calls and proves nothing about real
     boundaries, so the name is rejected with an explanation.
  4. Every journey loop depends on at least one component loop, and depends only on
     component loops.
  5. `loop_chaos` depends on every journey loop.
  6. Every loop declares `loop_type`, and journey/chaos loops declare `boundaries`.
  7. `depends_on` across all loops forms a DAG (no cycles, no dangling references).

Exit 0 = pass. Exit 1 = failures printed to stderr.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import Report, load_json, read_text, repo_root  # noqa: E402

COMPONENT_RE = re.compile(r"^loop_unit_(\d{2,3})_[a-z0-9][a-z0-9-]*$")
JOURNEY_RE = re.compile(r"^loop_journey_(\d{2,3})_[a-z0-9][a-z0-9-]*$")
CHAOS_NAME = "loop_chaos"

# Any spelling of a single catch-all end-to-end loop, so the explanation below is not tied
# to one name.
E2E_NAME_RE = re.compile(
    r"^loop_(?:unit_)?(?:e2e|end[_-]?to[_-]?end|endtoend|system|smoke)\b", re.I
)

VALID_BOUNDARIES = {"db", "queue", "external_api", "worker"}


def main() -> int:
    root = repo_root()
    loops_dir = root / "loops"
    report = Report("loop DAG")

    if not loops_dir.is_dir():
        report.fail("loops/ does not exist — run the roadmap agent")
        return report.finish()

    loop_dirs = sorted(p for p in loops_dir.iterdir() if p.is_dir())
    if not loop_dirs:
        report.fail("loops/ contains no loop directories")
        return report.finish()

    component, journey, chaos, unknown = [], [], [], []
    for path in loop_dirs:
        if COMPONENT_RE.match(path.name):
            component.append(path)
        elif JOURNEY_RE.match(path.name):
            journey.append(path)
        elif path.name == CHAOS_NAME:
            chaos.append(path)
        else:
            unknown.append(path)

    for path in unknown:
        if E2E_NAME_RE.match(path.name):
            report.fail(
                f"loops/{path.name}/ is not a valid loop. There is no general-purpose "
                "end-to-end loop: a single suite covering 'everything end to end' goes green "
                "by calling functions directly and proves nothing about the boundaries a real "
                "user crosses. Split it up — one loop_journey_<nn>_<slug> per user flow, each "
                f"black box against the running stack, and {CHAOS_NAME} for failure modes."
            )
        else:
            report.fail(
                f"loops/{path.name}/ does not match loop_unit_<nn>_<slug>, "
                f"loop_journey_<nn>_<slug>, or {CHAOS_NAME}"
            )

    if not chaos:
        report.fail(f"loops/{CHAOS_NAME}/ does not exist")
    if not component:
        report.fail("no component loops (loop_unit_<nn>_<slug>) scaffolded")

    # ---- read every loop's declared state
    statuses: dict[str, dict] = {}
    for path in loop_dirs:
        status, err = load_json(path / "status.json", default=None)
        if err:
            report.fail(f"{path.name}/status.json — {err}")
            statuses[path.name] = {}
            continue
        statuses[path.name] = status

        loop_type = status.get("loop_type")
        expected = ("component" if COMPONENT_RE.match(path.name)
                    else "journey" if JOURNEY_RE.match(path.name)
                    else "chaos" if path.name == CHAOS_NAME else None)
        if expected and loop_type != expected:
            report.fail(
                f"{path.name}/status.json has loop_type {loop_type!r}, expected {expected!r}"
            )

        if expected in {"journey", "chaos"}:
            boundaries = status.get("boundaries")
            if boundaries is None:
                report.fail(
                    f"{path.name}/status.json has no `boundaries` list — verify.sh needs it to "
                    "know which real boundaries the no-silent-mocks gate must enforce"
                )
            else:
                for boundary in boundaries:
                    if boundary not in VALID_BOUNDARIES:
                        report.fail(
                            f"{path.name}/status.json boundary {boundary!r} is not one of "
                            f"{', '.join(sorted(VALID_BOUNDARIES))}"
                        )

        verify = path / "verify.sh"
        if not verify.exists():
            report.fail(f"{path.name}/verify.sh does not exist")
        else:
            body = read_text(verify)
            if expected in {"journey", "chaos"} and "check_mocks.py" not in body:
                report.fail(
                    f"{path.name}/verify.sh does not call scripts/check_mocks.py — a "
                    f"{expected} loop without the no-silent-mocks gate can go green on mocks"
                )
            if expected == "journey" and "check_journey_coverage.py" not in body:
                report.fail(
                    f"{path.name}/verify.sh does not call scripts/check_journey_coverage.py — "
                    "journey loops are gated on 100% of their assertion points, not line coverage"
                )
            if "check_assertions.py" not in body:
                report.fail(f"{path.name}/verify.sh does not call scripts/check_assertions.py")

    # ---- 1. component loops cover every graph node exactly once
    covered: dict[str, str] = {}
    for path in component:
        gstatus, err = load_json(path / "graph_status.json", default=None)
        if err:
            report.fail(f"{path.name}/graph_status.json — {err}")
            continue
        ids = gstatus.get("node_ids") or ([gstatus["node_id"]] if gstatus.get("node_id") else [])
        if not ids:
            report.fail(f"{path.name}/graph_status.json declares no node_id/node_ids")
        for node_id in ids:
            if node_id in covered:
                report.fail(
                    f"graph node {node_id!r} is claimed by both {covered[node_id]} and {path.name}"
                )
            covered[node_id] = path.name

    graph, err = load_json(root / "system_graph.json", default={})
    if err:
        report.fail(err)
    for node in (graph or {}).get("nodes", []):
        nid = node.get("id", "?")
        if nid not in covered:
            report.fail(
                f"graph node {nid!r} is not covered by any component loop — every node in "
                "system_graph.json needs exactly one loop_unit that builds it"
            )

    # ---- 2. journey loops match journey files 1:1
    journeys_dir = root / "journeys"
    journey_files = sorted(journeys_dir.glob("journey_*.md")) if journeys_dir.is_dir() else []
    if not journey_files:
        report.fail(
            "journeys/ has no journey_*.md files — run the journey_mapper stage before roadmap"
        )

    claimed: dict[str, list[str]] = defaultdict(list)
    for path in journey:
        declared = (statuses.get(path.name) or {}).get("journey_file")
        if not declared:
            report.fail(
                f"{path.name}/status.json has no `journey_file` — a journey loop must name the "
                "journeys/journey_<nn>_<slug>.md file it proves"
            )
            continue
        target = root / declared
        if not target.exists():
            report.fail(f"{path.name}/status.json journey_file {declared!r} does not exist")
        else:
            claimed[Path(declared).name].append(path.name)

    for path in journey_files:
        owners = claimed.get(path.name, [])
        if not owners:
            report.fail(
                f"journeys/{path.name} has no loop_journey_* — every mapped journey needs a "
                "journey loop that proves it end to end"
            )
        elif len(owners) > 1:
            report.fail(f"journeys/{path.name} is claimed by {len(owners)} loops: {', '.join(owners)}")

    # ---- 4./5. dependency direction between loop types
    component_names = {p.name for p in component}
    journey_names = {p.name for p in journey}
    all_names = {p.name for p in loop_dirs}

    for path in journey:
        deps = set((statuses.get(path.name) or {}).get("depends_on", []))
        if not deps:
            report.fail(
                f"{path.name} depends on nothing — a journey loop is built AFTER the component "
                "loops it exercises"
            )
        wrong = deps - component_names
        for dep in sorted(wrong):
            report.fail(
                f"{path.name} depends on {dep!r}, which is not a component loop — journey loops "
                "depend only on loop_unit_* loops"
            )

    for path in chaos:
        deps = set((statuses.get(path.name) or {}).get("depends_on", []))
        missing = journey_names - deps
        for dep in sorted(missing):
            report.fail(
                f"{CHAOS_NAME} does not depend on {dep!r} — chaos runs only after every journey "
                "loop is green"
            )

    # ---- 7. DAG over all loops
    adj = defaultdict(list)
    in_degree = {name: 0 for name in all_names}
    for name in all_names:
        for dep in (statuses.get(name) or {}).get("depends_on", []):
            if dep not in all_names:
                report.fail(f"{name}/status.json depends_on {dep!r}, which is not a loop directory")
                continue
            adj[dep].append(name)
            in_degree[name] += 1

    queue = deque(name for name, degree in in_degree.items() if degree == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for neighbor in adj[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != len(all_names):
        stuck = sorted(name for name, degree in in_degree.items() if degree > 0)
        report.fail(f"cycle detected in loop depends_on graph — involves: {', '.join(stuck)}")

    return report.finish(
        f"{len(component)} component + {len(journey)} journey + {len(chaos)} chaos loop(s), "
        f"{len(covered)} nodes covered, no cycles"
    )


if __name__ == "__main__":
    sys.exit(main())

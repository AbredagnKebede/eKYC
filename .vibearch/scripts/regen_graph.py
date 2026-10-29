#!/usr/bin/env python3
"""regen_graph.py — rebuild system_graph.json node states from per-loop graph_status.json.

Merges loop progress into the master graph without clobbering structure or edges.
Component loops own graph nodes (via `node_id` or `node_ids`); journey and chaos loops
own journeys and failure modes rather than nodes, so their state is recorded on the
graph's `coverage` block instead.

Exit 0 on success, 1 only if system_graph.json is missing or unreadable.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import load_json, repo_root  # noqa: E402


def main() -> int:
    root = repo_root()
    graph_path = root / "system_graph.json"

    graph, err = load_json(graph_path, default=None)
    if err:
        print(f"ERROR: {err} — run the architect stage first", file=sys.stderr)
        return 1

    node_map = {n["id"]: n for n in graph.get("nodes", []) if n.get("id")}
    updated = 0
    journeys: dict[str, dict] = {}
    chaos_state = None

    loops_dir = root / "loops"
    if not loops_dir.is_dir():
        print("ERROR: loops/ does not exist — run the roadmap stage first", file=sys.stderr)
        return 1

    for loop_dir in sorted(p for p in loops_dir.iterdir() if p.is_dir()):
        gstatus, gs_err = load_json(loop_dir / "graph_status.json", default=None)
        if gs_err:
            print(f"WARN: {gs_err}", file=sys.stderr)
            continue
        status, _ = load_json(loop_dir / "status.json", default={})
        loop_type = (status or {}).get("loop_type") or gstatus.get("loop_type") or "component"
        state = gstatus.get("state", "unknown")
        verified = gstatus.get("last_verified_at")

        if loop_type == "journey":
            journey_file = (status or {}).get("journey_file") or gstatus.get("journey_file")
            journeys[journey_file or loop_dir.name] = {
                "loop": loop_dir.name, "state": state, "last_verified_at": verified,
                "assertion_points_verified": gstatus.get("assertion_points_verified"),
            }
            continue

        if loop_type == "chaos":
            chaos_state = {
                "loop": loop_dir.name, "state": state, "last_verified_at": verified,
                "scenarios_verified": gstatus.get("scenarios_verified"),
            }
            continue

        node_ids = gstatus.get("node_ids") or (
            [gstatus["node_id"]] if gstatus.get("node_id") else []
        )
        if not node_ids:
            print(f"WARN: {loop_dir.name}/graph_status.json has no node_id/node_ids",
                  file=sys.stderr)
            continue
        for node_id in node_ids:
            if node_id not in node_map:
                print(f"WARN: node_id '{node_id}' in {loop_dir.name} is not in system_graph.json",
                      file=sys.stderr)
                continue
            node_map[node_id].update({
                "state": state, "loop": loop_dir.name, "last_verified_at": verified,
            })
            updated += 1

    graph["nodes"] = list(node_map.values())
    coverage = graph.setdefault("coverage", {})
    if journeys:
        coverage["journeys"] = journeys
    if chaos_state:
        coverage["chaos"] = chaos_state
    graph["last_regenerated"] = datetime.now(timezone.utc).isoformat()
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")

    done = len([n for n in graph["nodes"] if n.get("state") == "done"])
    journeys_done = len([j for j in journeys.values() if j.get("state") == "done"])
    print(
        f"OK: system_graph.json updated — {updated} node state(s) merged "
        f"({done}/{len(graph['nodes'])} nodes done, {journeys_done}/{len(journeys)} journeys done)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""topology_validator.py — Stage 4 substage: turn the documented topology into a
machine-checkable manifest, then verify nothing is documented-but-unowned.

Inputs
  system_graph.json          nodes/edges, including type `queue`, `event`, `external_api`,
                             `worker` and edge types `publishes`, `consumes`, `calls`
  system_guide.md            §3 APIs, §5 Event Contracts, § Deployment (cross-checked)
  dependency_list.md         credential placeholders
  loops/*/status.json        `boundaries`, `target_paths` declared by the roadmap agent
  loops/*/graph_status.json  node -> owning loop
  loops/*/checklist.md       publisher/consumer test scaffolds

Output
  topology_manifest.json     the contract Stage 6 re-checks against real code

Structural checks performed here
  1. Every queue node has at least one publisher AND at least one consumer edge.
  2. Every queue/event name in the graph appears in `system_guide.md §5` (graph and prose agree).
  3. Every external_api node appears in §3 and its credential is in dependency_list.md.
  4. Every event has a publisher-test and a consumer-test scaffold in some loop's checklist.
  5. Every topology node is owned by exactly one loop.
Then it shells out to `check_parity.py --mode scaffold` unless `--no-parity` is passed.

Usage: python3 scripts/topology_validator.py
Exit 0 = pass (manifest written). Exit 1 = failures printed to stderr.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import (  # noqa: E402
    Report, deployment_artifacts, find_section, load_json, read_text, repo_root,
)

TOPOLOGY_TYPES = {"queue", "event", "external_api", "worker"}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Stage 4 topology validator.")
    parser.add_argument("--no-parity", action="store_true",
                        help="write the manifest without running check_parity.py")
    parser.add_argument("--out", default="topology_manifest.json")
    args = parser.parse_args(argv)

    root = repo_root()
    report = Report("topology")

    graph, err = load_json(root / "system_graph.json", default={})
    if err:
        report.fail(err)
        return report.finish()

    guide = read_text(root / "system_guide.md")
    deps_text = read_text(root / "dependency_list.md")
    if not guide:
        report.fail("system_guide.md is missing or empty")
        return report.finish()

    nodes = {n.get("id"): n for n in graph.get("nodes", []) if n.get("id")}
    edges = graph.get("edges", [])

    # ---- loop ownership + declarations
    owner_of: dict[str, str] = {}
    loop_status: dict[str, dict] = {}
    loop_checklists: dict[str, str] = {}
    loops_dir = root / "loops"
    if loops_dir.is_dir():
        for loop in sorted(p for p in loops_dir.iterdir() if p.is_dir()):
            status, status_err = load_json(loop / "status.json", default={})
            if status_err:
                report.warn(status_err)
            loop_status[loop.name] = status or {}
            loop_checklists[loop.name] = read_text(loop / "checklist.md")
            gstatus, _ = load_json(loop / "graph_status.json", default={})
            for node_id in (gstatus or {}).get("node_ids", []) or [(gstatus or {}).get("node_id")]:
                if not node_id:
                    continue
                if node_id in owner_of:
                    report.fail(
                        f"node {node_id!r} is claimed by both {owner_of[node_id]} and {loop.name}"
                    )
                else:
                    owner_of[node_id] = loop.name
    else:
        report.fail("loops/ does not exist — run the roadmap agent's scaffolding step first")

    def targets_for(node_id: str) -> list[str]:
        loop = owner_of.get(node_id)
        node_targets = nodes.get(node_id, {}).get("target_paths") or []
        if node_targets:
            return list(node_targets)
        return list((loop_status.get(loop) or {}).get("target_paths") or [])

    # ---- spec sections used for the prose/graph cross-check
    _, apis_body = find_section(guide, number="3")
    if apis_body is None:
        _, apis_body = find_section(guide, title_contains="api")
    _, events_body = find_section(guide, number="5")
    if events_body is None:
        _, events_body = find_section(guide, title_contains="event contract")
    _, deploy_body = find_section(guide, title_contains="deployment")

    apis_body = apis_body or ""
    events_body = events_body or ""
    if not events_body:
        report.warn("system_guide.md has no §5 Event Contracts section — assuming no events/queues")

    # ---- publisher / consumer edges
    publishers: dict[str, list[str]] = {}
    consumers: dict[str, list[str]] = {}
    callers: dict[str, list[str]] = {}
    for edge in edges:
        src, dst, etype = edge.get("from"), edge.get("to"), edge.get("type")
        if not src or not dst:
            report.fail(f"edge {edge!r} is missing 'from' or 'to'")
            continue
        for endpoint in (src, dst):
            if endpoint not in nodes:
                report.fail(f"edge {src}->{dst} references unknown node {endpoint!r}")
        if etype == "publishes":
            publishers.setdefault(dst, []).append(src)
        elif etype == "consumes":
            consumers.setdefault(dst, []).append(src)
        elif etype == "calls":
            callers.setdefault(dst, []).append(src)

    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"graph": "system_graph.json", "guide": "system_guide.md"},
        "queues": [], "events": [], "consumers": [], "external_apis": [],
        "deployment_artifacts": [],
    }

    # ---- queues
    for node_id, node in nodes.items():
        if node.get("type") != "queue":
            continue
        name = node.get("queue_name") or node.get("label") or node_id
        pubs = sorted(set(publishers.get(node_id, [])))
        cons = sorted(set(consumers.get(node_id, [])))
        if not pubs:
            report.fail(f"queue {name!r} ({node_id}) has no `publishes` edge — nothing writes to it")
        if not cons:
            report.fail(
                f"queue {name!r} ({node_id}) has no `consumes` edge — a queue nobody consumes is "
                "a documented-but-dead topology, which is exactly the failure this gate exists for"
            )
        if events_body and name not in events_body:
            report.fail(
                f"queue {name!r} is in system_graph.json but its name does not appear in "
                "system_guide.md §5 Event Contracts — graph and spec disagree"
            )
        if node_id not in owner_of:
            report.fail(f"queue {name!r} ({node_id}) is not owned by any loop")
        manifest["queues"].append({
            "name": name, "node_id": node_id, "spec_ref": node.get("spec_section", ""),
            "publishers": pubs, "consumers": cons,
            "owner_loop": owner_of.get(node_id), "target_paths": targets_for(node_id),
        })

    # ---- events
    for node_id, node in nodes.items():
        if node.get("type") != "event":
            continue
        name = node.get("event_name") or node.get("label") or node_id
        pubs = sorted(set(publishers.get(node_id, [])))
        cons = sorted(set(consumers.get(node_id, [])))
        if not pubs:
            report.fail(f"event {name!r} has no publisher")
        if not cons:
            report.fail(f"event {name!r} has no consumer")
        if events_body and name not in events_body:
            report.fail(f"event {name!r} does not appear in system_guide.md §5 Event Contracts")

        pub_owner = con_owner = None
        for loop_name, checklist in loop_checklists.items():
            for line in checklist.splitlines():
                if name not in line:
                    continue
                low = line.lower()
                if pub_owner is None and re.search(r"publish", low):
                    pub_owner = loop_name
                if con_owner is None and re.search(r"consum|subscrib", low):
                    con_owner = loop_name
        if not pub_owner:
            report.fail(
                f"event {name!r} has no publisher-test scaffold — no loop checklist.md has a line "
                f"naming {name!r} together with 'publish'"
            )
        if not con_owner:
            report.fail(
                f"event {name!r} has no consumer-test scaffold — no loop checklist.md has a line "
                f"naming {name!r} together with 'consume' or 'subscribe'"
            )
        manifest["events"].append({
            "name": name, "node_id": node_id, "spec_ref": node.get("spec_section", ""),
            "schema_ref": node.get("schema_ref", ""),
            "publishers": pubs, "consumers": cons,
            "publisher_test": {"owner_loop": pub_owner,
                               "path": f"tests/contract/test_{slug(name)}_publisher"} if pub_owner else None,
            "consumer_test": {"owner_loop": con_owner,
                              "path": f"tests/contract/test_{slug(name)}_consumer"} if con_owner else None,
        })

    # ---- consumers (workers and services that consume)
    seen_consumers = set()
    for queue_id, consumer_ids in consumers.items():
        for consumer_id in consumer_ids:
            key = (consumer_id, queue_id)
            if key in seen_consumers:
                continue
            seen_consumers.add(key)
            node = nodes.get(consumer_id, {})
            entrypoint = node.get("process_entrypoint", "")
            if not entrypoint:
                report.fail(
                    f"consumer {consumer_id!r} has no `process_entrypoint` in system_graph.json — "
                    "a consumer that is not a runnable process can only ever be tested by calling "
                    "its function directly, which proves nothing about the queue"
                )
            if consumer_id not in owner_of:
                report.fail(f"consumer {consumer_id!r} is not owned by any loop")
            manifest["consumers"].append({
                "node_id": consumer_id,
                "queue": nodes.get(queue_id, {}).get("queue_name")
                         or nodes.get(queue_id, {}).get("label") or queue_id,
                "spec_ref": node.get("spec_section", ""),
                "process_entrypoint": entrypoint,
                "owner_loop": owner_of.get(consumer_id),
                "target_paths": targets_for(consumer_id),
            })

    # ---- external APIs
    for node_id, node in nodes.items():
        if node.get("type") != "external_api":
            continue
        name = node.get("label") or node_id
        if apis_body and name not in apis_body and node_id not in apis_body:
            report.fail(f"external API {name!r} does not appear in system_guide.md §3 APIs")
        env = node.get("credential_env", "")
        if not env:
            report.fail(f"external API {name!r} has no `credential_env` in system_graph.json")
        elif env not in deps_text:
            report.fail(
                f"external API {name!r} credential {env} is not in dependency_list.md — "
                "the human would never be told to supply it"
            )
        if not node.get("sandbox_env") and not node.get("sandbox_base_url"):
            report.fail(
                f"external API {name!r} has no `sandbox_env` or `sandbox_base_url` — journey "
                "tests need a real sandbox to call instead of a mock"
            )
        if node_id not in owner_of:
            report.fail(f"external API {name!r} is not owned by any loop")
        manifest["external_apis"].append({
            "name": name, "node_id": node_id, "spec_ref": node.get("spec_section", ""),
            "credential_env": env, "sandbox_env": node.get("sandbox_env", ""),
            "sandbox_base_url": node.get("sandbox_base_url", ""),
            "callers": sorted(set(callers.get(node_id, []))),
            "owner_loop": owner_of.get(node_id), "target_paths": targets_for(node_id),
        })

    # ---- deployment artifacts: every `backticked` file path named in § Deployment
    if deploy_body:
        for candidate in deployment_artifacts(deploy_body):
            manifest["deployment_artifacts"].append({
                "requirement": candidate, "spec_ref": "§ Deployment",
                "target_paths": [candidate],
            })
        if not manifest["deployment_artifacts"]:
            report.fail(
                "system_guide.md § Deployment names no artifact paths in backticks — Stage 6 "
                "would have nothing to build. Name each Dockerfile/compose/k8s manifest inline."
            )
    else:
        report.fail(
            "system_guide.md has no § Deployment section — Stage 6 (deploy_validator) cannot "
            "verify a deployment that was never specified"
        )

    out_path = root / args.out
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report.note(f"wrote {args.out}")

    summary = ", ".join(
        f"{len(manifest[k])} {k}" for k in
        ("queues", "events", "consumers", "external_apis", "deployment_artifacts")
    )
    status = report.finish(summary)
    if status != 0:
        return status

    if args.no_parity:
        return 0

    parity = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "check_parity.py"),
         "--mode", "scaffold", "--manifest", args.out],
        cwd=str(root),
    )
    return parity.returncode


if __name__ == "__main__":
    sys.exit(main())

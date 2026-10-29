#!/usr/bin/env python3
"""check_release_evidence.py — Stage 6 gate: "all tests green" is not evidence.

Verifies the `release_evidence/` bundle the deploy_validator agent produces is complete
and actually says the system worked — not merely that files exist.

Required files and what each must prove:
  manifest.json              versions + image digests + timestamps, all non-empty
  smoke_test_transcript.log  one entry per critical journey, each with a correlation id
  migration_result.log       DB schema reached the target version
  queue_inventory.json       every documented queue present, each with >=1 live consumer
  service_health.json        every service healthy
  external_api_status.json   every external API (or its sandbox) reachable
  skipped_tests_report.txt   MUST be empty
  dlq_baseline.json          dead-letter count 0 for every queue

Cross-checked against `topology_manifest.json`, so evidence cannot omit a queue, a
consumer, or an API that the spec documents.

Usage: python3 scripts/check_release_evidence.py
Exit 0 = release may be marked ready. Exit 1 = the blockers are printed.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import Report, load_json, read_text, repo_root  # noqa: E402

REQUIRED = (
    "manifest.json",
    "smoke_test_transcript.log",
    "migration_result.log",
    "queue_inventory.json",
    "service_health.json",
    "external_api_status.json",
    "skipped_tests_report.txt",
    "dlq_baseline.json",
)

HEALTHY = {"healthy", "ok", "up", "ready", "passing", "running", "200"}
REACHABLE = {"reachable", "ok", "up", "healthy", "200", "204", "sandbox-ok"}
CORRELATION = re.compile(r"correlation[_-]?id\s*[:=]\s*[\"']?([\w-]{6,})", re.I)


def status_of(value) -> str:
    """Normalise a health/status field that may be a bool, string, int, or nested dict."""
    if isinstance(value, bool):
        return "healthy" if value else "unhealthy"
    if isinstance(value, (int, float)):
        return str(int(value))
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        for key in ("status", "state", "health", "healthy", "reachable", "ok", "http_status"):
            if key in value:
                return status_of(value[key])
    return ""


def entries(payload, *keys):
    """Yield (name, value) pairs from either a dict-of-things or a list-of-objects."""
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            for name, value in payload.items():
                yield str(name), value
            return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                name = item.get("name") or item.get("queue") or item.get("service") \
                       or item.get("api") or item.get("id") or "?"
                yield str(name), item
            else:
                yield str(item), item


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Stage 6 release-evidence gate.")
    parser.add_argument("--dir", default="release_evidence")
    parser.add_argument("--manifest", default="topology_manifest.json")
    args = parser.parse_args(argv)

    root = repo_root()
    evidence = root / args.dir
    report = Report("release evidence")

    if not evidence.is_dir():
        report.fail(f"{args.dir}/ does not exist — the deploy_validator stage has not run")
        return report.finish()

    for name in REQUIRED:
        path = evidence / name
        if not path.exists():
            report.fail(f"{args.dir}/{name} is missing")
        elif name != "skipped_tests_report.txt" and not path.stat().st_size:
            report.fail(f"{args.dir}/{name} is empty")

    topology, topo_err = load_json(root / args.manifest, default={})
    if topo_err:
        report.warn(f"{topo_err} — evidence cannot be cross-checked against the documented topology")

    # ---- skipped tests: the hard stop
    skipped = evidence / "skipped_tests_report.txt"
    if skipped.exists():
        body = read_text(skipped).strip()
        if body:
            count = len([ln for ln in body.splitlines() if ln.strip()])
            report.fail(
                f"{args.dir}/skipped_tests_report.txt lists {count} skipped test(s) — release is "
                "blocked. First entry: " + body.splitlines()[0][:120]
            )

    # ---- manifest.json
    manifest, err = load_json(evidence / "manifest.json", default={})
    if err and (evidence / "manifest.json").exists():
        report.fail(err)
    elif manifest:
        for field in ("built_at", "images", "versions"):
            if not manifest.get(field):
                report.fail(f"{args.dir}/manifest.json has no non-empty {field!r}")
        for name, image in entries(manifest.get("images", {}), "images"):
            digest = image.get("digest") if isinstance(image, dict) else image
            if not digest or not re.search(r"sha256:[0-9a-f]{12,}", str(digest)):
                report.fail(
                    f"{args.dir}/manifest.json: image {name!r} has no sha256 digest — an image "
                    "without a digest is not a reproducible artifact"
                )

    # ---- service health
    health, err = load_json(evidence / "service_health.json", default={})
    if err and (evidence / "service_health.json").exists():
        report.fail(err)
    else:
        found_any = False
        for name, value in entries(health, "services"):
            found_any = True
            if status_of(value) not in HEALTHY:
                report.fail(f"service {name!r} is not healthy (status: {status_of(value) or 'unknown'})")
        if not found_any and (evidence / "service_health.json").exists():
            report.fail(f"{args.dir}/service_health.json records no services")

    # ---- queue inventory vs documented topology
    inventory, err = load_json(evidence / "queue_inventory.json", default={})
    if err and (evidence / "queue_inventory.json").exists():
        report.fail(err)
    else:
        live = {}
        for name, value in entries(inventory, "queues"):
            live[name] = value
            consumers = value.get("consumers") if isinstance(value, dict) else None
            count = (len(consumers) if isinstance(consumers, list)
                     else consumers if isinstance(consumers, int) else None)
            if count is None:
                report.fail(f"queue {name!r} in queue_inventory.json declares no consumers field")
            elif count < 1:
                report.fail(
                    f"queue {name!r} exists but has 0 connected consumers — this is the documented-"
                    "but-not-implemented consumer failure, caught before release"
                )
        for queue in topology.get("queues", []):
            qname = queue.get("name", "?")
            if qname not in live:
                report.fail(
                    f"queue {qname!r} is documented in {args.manifest} but absent from "
                    f"{args.dir}/queue_inventory.json — it was never created in the deployment"
                )

    # ---- dead letter baseline
    dlq, err = load_json(evidence / "dlq_baseline.json", default={})
    if err and (evidence / "dlq_baseline.json").exists():
        report.fail(err)
    else:
        for name, value in entries(dlq, "queues", "dlqs"):
            count = value.get("count") if isinstance(value, dict) else value
            try:
                count = int(count)
            except (TypeError, ValueError):
                report.fail(f"dlq_baseline.json: {name!r} has a non-numeric count {count!r}")
                continue
            if count != 0:
                report.fail(f"dead-letter queue {name!r} holds {count} message(s) — expected 0")

    # ---- external APIs
    apis, err = load_json(evidence / "external_api_status.json", default={})
    if err and (evidence / "external_api_status.json").exists():
        report.fail(err)
    else:
        seen = set()
        for name, value in entries(apis, "apis", "external_apis"):
            seen.add(name)
            if status_of(value) not in REACHABLE:
                report.fail(f"external API {name!r} is not reachable (status: {status_of(value) or 'unknown'})")
        for api in topology.get("external_apis", []):
            if api.get("name") not in seen:
                report.fail(
                    f"external API {api.get('name')!r} is documented but has no entry in "
                    f"{args.dir}/external_api_status.json"
                )

    # ---- migrations
    migration = read_text(evidence / "migration_result.log")
    if (evidence / "migration_result.log").exists():
        if re.search(r"\b(error|failed|failure|traceback|aborted)\b", migration, re.I):
            report.fail(f"{args.dir}/migration_result.log contains an error — schema is not at target version")
        if not re.search(r"\b(?:version|revision|head|migrated|applied|up to date)\b", migration, re.I):
            report.fail(
                f"{args.dir}/migration_result.log does not state the schema version reached — "
                "log the resulting version explicitly"
            )

    # ---- smoke transcript: one correlated entry per journey
    transcript = read_text(evidence / "smoke_test_transcript.log")
    if (evidence / "smoke_test_transcript.log").exists():
        ids = set(CORRELATION.findall(transcript))
        if not ids:
            report.fail(
                f"{args.dir}/smoke_test_transcript.log has no correlation ids — without them the "
                "transcript cannot be tied to real requests"
            )
        journeys_dir = root / "journeys"
        journey_files = sorted(journeys_dir.glob("journey_*.md")) if journeys_dir.is_dir() else []
        for path in journey_files:
            match = re.search(r"^journey_id\s*:\s*(J-\d+)", read_text(path), re.M)
            jid = match.group(1) if match else path.stem
            if jid not in transcript and path.stem not in transcript:
                report.fail(
                    f"smoke_test_transcript.log has no entry for {jid} ({path.name}) — every "
                    "critical journey needs one smoke test in the deployed system"
                )
        if re.search(r"\b(FAIL|FAILED|ERROR|Traceback|assertion ?error)\b", transcript):
            report.fail(f"{args.dir}/smoke_test_transcript.log contains a failure")

    return report.finish(f"{len(REQUIRED)} evidence artifacts verified")


if __name__ == "__main__":
    sys.exit(main())

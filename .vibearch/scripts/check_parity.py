#!/usr/bin/env python3
"""check_parity.py — "implementation matches documentation" gate.

Documentation must never outrun implementation. This script compares
`topology_manifest.json` (what the spec says exists) against the repo (what actually
exists), in one of two modes:

  --mode scaffold        Stage 4, before any code exists. Proves every documented
                         queue, consumer, external API, and deployment requirement is
                         OWNED: a loop is responsible for it, a target path is named,
                         and its credential placeholder is in dependency_list.md.
                         Nothing on disk is required yet.

  --mode implementation  Stage 6, after execution. Proves every one of those target
                         paths now exists, holds a real implementation rather than a
                         TODO stub, every queue name appears in code or config, and
                         every documented consumer has a process declared in a
                         deployment artifact.

Splitting the modes is deliberate. A single "parity check" at the end of Stage 4 cannot
inspect code that Stage 5 has not written yet; pretending otherwise is exactly the kind
of green-but-untrue gate this pipeline exists to prevent.

Usage:
  python3 scripts/check_parity.py --mode scaffold
  python3 scripts/check_parity.py --mode implementation

Exit 0 = pass. Exit 1 = failures printed to stderr.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vibelib import (  # noqa: E402
    CONFIG_EXTS, PIPELINE_ARTIFACTS, Report, code_and_config_files, is_test_file, load_json,
    read_text, repo_root, strip_comments,
)

STUB_MARKERS = re.compile(
    r"NotImplementedError|not\s+implemented|NotImplementedException|"
    r"panic\s*\(\s*[\"'](?:TODO|unimplemented|not implemented)|"
    r"todo!\s*\(|TODO:\s*implement|FIXME:\s*implement|@abstractmethod\s*$",
    re.I | re.M,
)

DEPLOY_FILE_HINT = re.compile(
    r"(?:docker-compose|compose)\.ya?ml$|Dockerfile|Procfile|\.k8s\.ya?ml$|"
    r"(?:^|/)(?:k8s|kubernetes|deploy|helm|charts|manifests)/",
    re.I,
)


def looks_like_stub(path: Path) -> str | None:
    """Return a reason string when `path` is a placeholder rather than an implementation."""
    text = read_text(path)
    if not text.strip():
        return "file is empty"
    body = strip_comments(text, path.suffix)
    code_lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(code_lines) < 3:
        return f"only {len(code_lines)} code line(s)"
    if STUB_MARKERS.search(body) and len(code_lines) < 20:
        marker = STUB_MARKERS.search(body)
        return f"unimplemented marker {marker.group(0).strip()!r} in a {len(code_lines)}-line file"
    return None


def repo_haystack(root: Path) -> list[tuple[Path, str]]:
    """Production code and config paired with its text — searched for literal names.

    Two exclusions, both load-bearing:
      * Pipeline bookkeeping files (`topology_manifest.json`, `system_graph.json`, ...) are
        the documentation side of this comparison, so a hit inside them would let the
        manifest prove itself.
      * Test files are excluded because a test asserting `queue == "booking.requests"` does
        not make the queue exist. Parity is about the code that runs in production.
    """
    out = []
    for path in code_and_config_files(root, skip_docs=True):
        if path.name in PIPELINE_ARTIFACTS or is_test_file(path):
            continue
        out.append((path, read_text(path)))
    return out


def find_literal(haystack, needle: str) -> list[Path]:
    return [path for path, text in haystack if needle and needle in text]


def check_scaffold(manifest: dict, root: Path, report: Report) -> None:
    loop_names = {p.name for p in (root / "loops").iterdir() if p.is_dir()} \
        if (root / "loops").is_dir() else set()
    deps_text = read_text(root / "dependency_list.md")

    def require_owner(kind: str, name: str, entry: dict) -> None:
        owner = entry.get("owner_loop")
        if not owner:
            report.fail(f"{kind} {name!r} has no owner_loop — no loop is responsible for building it")
        elif loop_names and owner not in loop_names:
            report.fail(f"{kind} {name!r} names owner_loop {owner!r}, which is not a directory in loops/")
        if not entry.get("target_paths"):
            report.fail(
                f"{kind} {name!r} declares no target_paths — name the file(s) that will "
                "implement it so Stage 6 can verify they exist"
            )

    for queue in manifest.get("queues", []):
        name = queue.get("name", "?")
        require_owner("queue", name, queue)
        if not queue.get("publishers"):
            report.fail(f"queue {name!r} has no declared publisher")
        if not queue.get("consumers"):
            report.fail(
                f"queue {name!r} has no declared consumer — a queue nobody consumes is a "
                "documented-but-dead topology"
            )

    for event in manifest.get("events", []):
        name = event.get("name", "?")
        if not event.get("publishers"):
            report.fail(f"event {name!r} has no declared publisher")
        if not event.get("consumers"):
            report.fail(f"event {name!r} has no declared consumer")
        if not event.get("publisher_test"):
            report.fail(f"event {name!r} has no publisher_test scaffold declared")
        if not event.get("consumer_test"):
            report.fail(f"event {name!r} has no consumer_test scaffold declared")

    for consumer in manifest.get("consumers", []):
        name = consumer.get("node_id", "?")
        require_owner("consumer", name, consumer)
        if not consumer.get("process_entrypoint"):
            report.fail(
                f"consumer {name!r} declares no process_entrypoint — a consumer that is not "
                "a runnable process cannot be observed consuming anything"
            )

    for api in manifest.get("external_apis", []):
        name = api.get("name", "?")
        require_owner("external API", name, api)
        env = api.get("credential_env")
        if not env:
            report.fail(f"external API {name!r} declares no credential_env")
        elif env not in deps_text:
            report.fail(
                f"external API {name!r} credential {env} is not listed in dependency_list.md "
                "— the human will not know to supply it"
            )
        if not api.get("sandbox_env") and not api.get("sandbox_base_url"):
            report.fail(
                f"external API {name!r} declares no sandbox_env or sandbox_base_url — journey "
                "tests would have nothing real to call"
            )

    for artifact in manifest.get("deployment_artifacts", []):
        name = artifact.get("requirement", "?")
        if not artifact.get("target_paths"):
            report.fail(f"deployment requirement {name!r} declares no target_paths")


def check_implementation(manifest: dict, root: Path, report: Report) -> None:
    haystack = repo_haystack(root)
    deploy_texts = [
        text for path, text in haystack
        if DEPLOY_FILE_HINT.search(str(path.relative_to(root)))
        or path.suffix in CONFIG_EXTS
    ]

    def require_paths(kind: str, name: str, entry: dict) -> list[Path]:
        found = []
        for rel in entry.get("target_paths", []):
            path = root / rel
            if not path.exists():
                report.fail(f"{kind} {name!r}: declared target {rel} does not exist")
                continue
            if path.is_file():
                reason = looks_like_stub(path)
                if reason:
                    report.fail(f"{kind} {name!r}: {rel} is a stub, not an implementation ({reason})")
                else:
                    found.append(path)
            else:
                found.append(path)
        return found

    for queue in manifest.get("queues", []):
        name = queue.get("name", "?")
        require_paths("queue", name, queue)
        literal = queue.get("name", "")
        if literal and not find_literal(haystack, literal):
            report.fail(
                f"queue {name!r} is documented but its name appears nowhere in code or config "
                "— the queue does not actually exist"
            )

    for consumer in manifest.get("consumers", []):
        name = consumer.get("node_id", "?")
        require_paths("consumer", name, consumer)
        entrypoint = consumer.get("process_entrypoint", "")
        token = (entrypoint.split()[-1] if entrypoint else "")
        if entrypoint and not any(entrypoint in t or (token and token in t) for t in deploy_texts):
            report.fail(
                f"consumer {name!r} entrypoint {entrypoint!r} is not launched by any deployment "
                "artifact (compose/k8s/Procfile) — it would never run in a real deploy"
            )

    for event in manifest.get("events", []):
        name = event.get("name", "?")
        for role in ("publisher_test", "consumer_test"):
            scaffold = event.get(role)
            stem = scaffold.get("path") if isinstance(scaffold, dict) else scaffold
            if not stem:
                report.fail(f"event {name!r}: no {role} declared in topology_manifest.json")
                continue
            base = root / stem
            matches = [
                p for p in base.parent.glob(base.name + "*")
                if p.is_file() and not p.name.endswith((".pyc", ".map"))
            ] if base.parent.is_dir() else []
            if not matches:
                report.fail(
                    f"event {name!r}: {role} {stem}.* does not exist — the event's "
                    f"{role.split('_')[0]} side was never contract-tested"
                )
                continue
            for path in matches:
                reason = looks_like_stub(path)
                if reason:
                    report.fail(f"event {name!r}: {role} {path.relative_to(root)} is a stub ({reason})")

    for api in manifest.get("external_apis", []):
        name = api.get("name", "?")
        require_paths("external API", name, api)
        env = api.get("credential_env", "")
        if env and not find_literal(haystack, env):
            report.fail(
                f"external API {name!r}: credential env {env} is referenced nowhere in code or "
                "config — the client cannot be reading it"
            )

    for artifact in manifest.get("deployment_artifacts", []):
        require_paths("deployment requirement", artifact.get("requirement", "?"), artifact)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Documentation/implementation parity gate.")
    parser.add_argument("--mode", required=True, choices=("scaffold", "implementation"))
    parser.add_argument("--manifest", default="topology_manifest.json")
    args = parser.parse_args(argv)

    root = repo_root()
    report = Report(f"doc/code parity ({args.mode})")

    manifest, err = load_json(root / args.manifest, default={})
    if err:
        report.fail(f"{err} — run scripts/topology_validator.py first")
        return report.finish()

    counts = {k: len(manifest.get(k, [])) for k in
              ("queues", "events", "consumers", "external_apis", "deployment_artifacts")}
    if not any(counts.values()):
        report.warn(
            "topology_manifest.json declares no queues, events, consumers, external APIs, or "
            "deployment artifacts — correct only for a system with none of those"
        )

    if args.mode == "scaffold":
        check_scaffold(manifest, root, report)
    else:
        check_implementation(manifest, root, report)

    return report.finish(", ".join(f"{v} {k}" for k, v in counts.items() if v))


if __name__ == "__main__":
    sys.exit(main())

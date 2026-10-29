#!/usr/bin/env python3
"""
check_skills.py — VibeArch Gate Script: Verify that all required domain skills
are installed into the project before Stage 5 Execution.

Invariants:
- developerStrategies/required_skills.json must exist and declare required skills.
- Every declared skill must be physically installed in .agents/skills/<name>/SKILL.md
  with valid YAML frontmatter (name, description) and substantive content (> 30 lines).
- Architectural boundaries in system_graph.json (ui, api, security) must have
  corresponding skill coverage.

Exit 0: All required skills are installed and verified.
Exit 1: Required skills are missing or non-compliant.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Verify domain skill installation.")
    parser.add_argument(
        "--target",
        default=".",
        help="Project root directory (default: current directory)",
    )
    return parser.parse_args()


def parse_frontmatter(content: str):
    """Extract YAML frontmatter fields from markdown."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return None
    frontmatter_text = match.group(1)
    fields = {}
    for line in frontmatter_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            fields[key.strip()] = val.strip().strip("\"'")
    return fields


def check_skill_file(skill_path: Path, expected_name: str):
    """Verify that a skill file exists, has valid frontmatter, and substantive content."""
    if not skill_path.exists():
        return False, f"File not found: {skill_path}"

    try:
        content = skill_path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Could not read {skill_path}: {e}"

    lines = content.splitlines()
    if len(lines) < 25:
        return (
            False,
            f"{skill_path} is too short ({len(lines)} lines). Must be a comprehensive, substantive skill.",
        )

    fm = parse_frontmatter(content)
    if not fm:
        return False, f"{skill_path} is missing valid YAML frontmatter (--- ... ---)"

    if "name" not in fm or not fm["name"]:
        return False, f"{skill_path} frontmatter missing 'name' field"

    if "description" not in fm or not fm["description"]:
        return False, f"{skill_path} frontmatter missing 'description' field"

    if fm["name"] != expected_name:
        return (
            False,
            f"{skill_path} frontmatter name '{fm['name']}' does not match expected '{expected_name}'",
        )

    return True, None


def main():
    args = parse_args()
    root = Path(args.target).resolve()
    manifest_path = root / "developerStrategies" / "required_skills.json"

    errors = []
    warnings = []

    if not manifest_path.exists():
        print(
            f"ERROR: Skills manifest missing: {manifest_path.relative_to(root)}",
            file=sys.stderr,
        )
        print(
            "The architect stage must declare required skills in developerStrategies/required_skills.json before execution.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"ERROR: Could not parse {manifest_path}: {e}", file=sys.stderr)
        sys.exit(1)

    skills_list = manifest.get("skills", [])
    if not isinstance(skills_list, list) or len(skills_list) == 0:
        print(
            f"ERROR: {manifest_path} contains no declared skills in 'skills' array.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"vibearch: verifying {len(skills_list)} declared skill(s) against project...")

    verified_count = 0
    declared_domains = set()

    for item in skills_list:
        if isinstance(item, str):
            skill_name = item
            domain = "general"
        elif isinstance(item, dict):
            skill_name = item.get("name")
            domain = item.get("domain", "general")
        else:
            errors.append(f"Invalid entry in required_skills.json: {item}")
            continue

        if not skill_name:
            errors.append("Skill entry missing 'name' attribute.")
            continue

        declared_domains.add(domain.lower())

        # Check candidate locations:
        # 1. Project-specific: .agents/skills/<name>/SKILL.md
        # 2. Plugin bundled: .agents/plugins/vibearch/skills/<name>/SKILL.md or VibeArch/skills/<name>/SKILL.md
        candidates = [
            root / ".agents" / "skills" / skill_name / "SKILL.md",
            root / ".agents" / "plugins" / "vibearch" / "skills" / skill_name / "SKILL.md",
            root / "VibeArch" / "skills" / skill_name / "SKILL.md",
        ]

        found = False
        last_err = None
        for candidate in candidates:
            if candidate.exists():
                ok, err = check_skill_file(candidate, skill_name)
                if ok:
                    try:
                        rel_path = candidate.relative_to(root)
                    except ValueError:
                        rel_path = candidate
                    print(f"  [OK] {skill_name: <32} -> {rel_path}")
                    verified_count += 1
                    found = True
                    break
                else:
                    last_err = err

        if not found:
            if last_err:
                errors.append(f"Skill '{skill_name}' invalid: {last_err}")
            else:
                errors.append(
                    f"Skill '{skill_name}' not found in .agents/skills/{skill_name}/SKILL.md"
                )

    # Cross-check system_graph.json if available
    graph_path = root / "system_graph.json"
    if graph_path.exists():
        try:
            with open(graph_path, "r", encoding="utf-8") as f:
                graph = json.load(f)
            nodes = graph.get("nodes", {})
            has_frontend = any(
                n.get("type") in ("ui", "frontend", "web", "mobile") or "ui" in k.lower()
                for k, n in nodes.items()
            )
            has_security = any(
                n.get("type") in ("auth", "security", "vault") or "auth" in k.lower()
                for k, n in nodes.items()
            )

            if has_frontend and "frontend" not in declared_domains:
                warnings.append(
                    "system_graph.json contains UI/frontend nodes, but no 'frontend' domain skill is declared in required_skills.json"
                )
            if has_security and "security" not in declared_domains:
                warnings.append(
                    "system_graph.json contains Auth/Security nodes, but no 'security' domain skill is declared in required_skills.json"
                )
        except Exception:
            pass

    for w in warnings:
        print(f"  [WARN] {w}", file=sys.stderr)

    if errors:
        print(f"\nFAILED: {len(errors)} skill verification error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("\nInstall or generate the missing skills before starting execution.", file=sys.stderr)
        sys.exit(1)

    print(f"\nOK: All {verified_count} required skill(s) verified and ready for execution.")
    sys.exit(0)


if __name__ == "__main__":
    main()

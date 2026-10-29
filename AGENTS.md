# Antigravity Agent Guidelines for VibeArch

This workspace integrates **VibeArch** — a seven-stage, spec-driven, deploy-verified pipeline where every stage is strictly gated by verification scripts.

## The 7-Stage Pipeline

| Stage | Agent / Role | Sentinel File | Gate Verification |
| ----- | ------------ | ------------- | ----------------- |
| **1** | `brainstorm` | `.pipeline/01_brainstorm.done` | Bullet list of confirmed intent approved by user |
| **2** | `consulting` | `.pipeline/02_consulting.done` | Stack/ADRs accepted with rationale citing requirements/prior art |
| **3** | `architect` | `.pipeline/03_architect.done` | `python3 .vibearch/scripts/verify_spec.py` passes + `developerStrategies/required_skills.json` written |
| **4.5**| `journey_mapper` | `.pipeline/04_journey_mapper.done` | `python3 .vibearch/scripts/check_journeys.py` passes |
| **4** | `roadmap` | `.pipeline/04_roadmap.done` | `topology_validator.py`, `check_dag.py`, and `check_skills.py` pass |
| **5** | `execute` | `.pipeline/05_execute.done` | Pre-condition `check_skills.py` + every component, journey, and chaos loop's `verify.sh` passes |
| **6** | `deploy_validator` | `.pipeline/06_deploy_validator.done` | `python3 .vibearch/scripts/check_release_evidence.py` passes |

*Note: `journey_mapper` is numbered 4.5 because it belongs to Stage 4 planning, but runs BEFORE `roadmap` so loops anchor to real user flows.*

## Core Invariants

1. **Source of Truth**: `system_guide.md` is the single source of truth. Once `frozen: true`, never edit directly. All changes require an amendment in `spec_amendments/INDEX.md`.
2. **Mandatory Gate Verification**: Never write a sentinel or mark a loop/stage complete unless its gate script exits 0. Never weaken a gate.
3. **No Silent Mocks at Critical Boundaries**: Mocks are permitted only in `tests/unit/` and `tests/component/`. Journey and chaos loops must exercise live running processes, databases, brokers, and external endpoints.
4. **Senior Domain Skills Required**: Before Stage 5 Execution starts, all architectural domains (frontend, backend, security) must have specialized senior-caliber skills installed into `.agents/skills/<name>/SKILL.md` and verified by `python3 .vibearch/scripts/check_skills.py`. No generic or boilerplate implementations allowed.
5. **Mandatory Human Checkpoints**:
   - (a) Idea approval during brainstorm.
   - (b) Review prompt ("continue or stop for review?") after each closed loop in execute.
   - (c) Production-readiness sign-off before marking deployment complete.
6. **Disk State Over Conversation**: Always read state from `.pipeline/` sentinels, `run_state.json`, and `status.json` on disk. Sentinels win if there is a conflict.
7. **Local Commits**: Git commits are local only. One atomic commit per completed loop. Never git push automatically.

## Available Skills & Workflows

### Pipeline Workflows
- `vibearch-rules`: Core invariants, test categories, no-silent-mocks rules, and gate policies.
- `vibe-init`: Install/verify project gate scripts in `.vibearch/scripts/`.
- `vibe-new`: Interactive intake to scaffold `Idea_scaff.md`.
- `vibe-run`: Run or advance the 7-stage pipeline.
- `vibe-skills`: Analyze architecture, populate `developerStrategies/required_skills.json`, and install senior skills into `.agents/skills/`.
- `vibe-status`: Read-only pipeline status inspection.
- `vibe-resume`: Cleanly resume from the earliest incomplete stage.

### Bundled Senior Domain Skills
- `frontend-design-engineering`: Senior frontend standards — modern typography, HSL palettes, glassmorphism, responsive micro-interactions, avoiding generic dashboards.
- `backend-service-engineering`: Principal backend standards — async service architecture, repository patterns, transactional integrity, and connection pooling.
- `security-hardened-engineering`: Lead AppSec standards — OWASP Top 10 mitigation, PII/KYC data encryption, zero-trust token flows, and rate limiting.

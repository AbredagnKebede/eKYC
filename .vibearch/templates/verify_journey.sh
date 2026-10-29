#!/usr/bin/env bash
# verify.sh — JOURNEY loop gate for __LOOP_NAME__
#
# Generated from .vibearch/templates/verify_journey.sh by the roadmap agent.
# Placeholders the agent must replace:
#   __LOOP_NAME__       e.g. loop_journey_02_book-a-session
#   __JOURNEY_FILE__    journeys/journey_<nn>_<slug>.md
#   __JOURNEY_TESTS__   test paths under tests/journey/
#   __BOUNDARIES__      comma-separated: db,queue,external_api,worker
#   __SERVICES__        every compose service this journey needs RUNNING (incl. workers)
#   __REQUIRED_ENV__    sandbox credential env vars from dependency_list.md
#   __MIGRATE_CMD__     command that brings the real DB to head (or "" if none)
#
# This is the REAL end-to-end gate. It is black-box on purpose:
#   * real database        (not in-memory, not sqlite swapped in)
#   * real message broker  (not a fake or eager-mode)
#   * real worker PROCESSES consuming the real queue (not direct function calls)
#   * real external sandbox APIs (not recorded cassettes or mocks)
#
# The coverage target is NOT line coverage. It is 100% of the assertion points written
# in __JOURNEY_FILE__ — every AP-<n> must be cited by a test.

set -euo pipefail

LOOP_NAME="__LOOP_NAME__"
JOURNEY_FILE="__JOURNEY_FILE__"
JOURNEY_TESTS="__JOURNEY_TESTS__"
BOUNDARIES="__BOUNDARIES__"
SERVICES="__SERVICES__"
REQUIRED_ENV="__REQUIRED_ENV__"
MIGRATE_CMD="__MIGRATE_CMD__"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$(cd "$SELF_DIR/../.." && pwd)/.vibearch/scripts/verify_lib.sh"
ROOT="$(repo_root "$SELF_DIR")"
cd "$ROOT"

printf 'verify: %s (journey loop — black box, real boundaries)\n' "$LOOP_NAME"
[[ -f "$JOURNEY_FILE" ]] || fail "journey file $JOURNEY_FILE does not exist"

# ---- 1. credentials for the real sandbox — never silently swap in a mock
if [[ -n "$REQUIRED_ENV" ]]; then
  step "required credentials"
  # shellcheck disable=SC2086
  require_env $REQUIRED_ENV
fi

# ---- 2. the whole system must actually be RUNNING, workers included
trap compose_down EXIT
[[ -n "$SERVICES" ]] || fail \
  "$LOOP_NAME declares no services — a journey loop must run against a real running system"
# shellcheck disable=SC2086
require_services $SERVICES

# ---- 3. real schema at target version
if [[ -n "$MIGRATE_CMD" ]]; then
  step "migrating the real database"
  eval "$MIGRATE_CMD"
fi

# ---- 4. the journey itself, end to end
# shellcheck disable=SC2086
run_tests $JOURNEY_TESTS

# ---- 5. 100% of the journey's assertion points must be verified by a test
step "assertion-point coverage (must be 100%)"
# shellcheck disable=SC2086
python3 .vibearch/scripts/check_journey_coverage.py --journey "$JOURNEY_FILE" --tests $JOURNEY_TESTS

# ---- 6. black-box or bust: no mocks at any critical boundary
step "no silent mocks (journey)"
# shellcheck disable=SC2086
python3 .vibearch/scripts/check_mocks.py --mode journey \
  --boundaries "$BOUNDARIES" \
  --tests $JOURNEY_TESTS

# ---- 7. assertions must be meaningful, not padding
step "assertion density"
# shellcheck disable=SC2086
python3 .vibearch/scripts/check_assertions.py $JOURNEY_TESTS

printf '\nPASS: %s\n' "$LOOP_NAME"

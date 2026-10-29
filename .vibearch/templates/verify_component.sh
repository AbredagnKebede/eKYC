#!/usr/bin/env bash
# verify.sh — COMPONENT loop gate for __LOOP_NAME__
#
# Generated from .vibearch/templates/verify_component.sh by the roadmap agent.
# Placeholders the agent must replace:
#   __LOOP_NAME__      e.g. loop_unit_03_matching
#   __SRC_PATHS__      space-separated source paths this loop owns (coverage scope)
#   __UNIT_TESTS__     space-separated unit test paths        (required)
#   __INTEGRATION_TESTS__  integration test paths            (required iff boundaries non-empty)
#   __BOUNDARIES__     comma-separated: db,queue,external_api,worker — "" if none
#   __SERVICES__       compose services needed for the integration tests — "" if none
#   __COVERAGE_MIN__   line-coverage gate, default 85
#
# Gate order: tests green -> coverage -> assertion density -> no silent mocks.
# Any non-zero exit means the loop is NOT done.

set -euo pipefail

LOOP_NAME="__LOOP_NAME__"
SRC_PATHS="__SRC_PATHS__"
UNIT_TESTS="__UNIT_TESTS__"
INTEGRATION_TESTS="__INTEGRATION_TESTS__"
BOUNDARIES="__BOUNDARIES__"
SERVICES="__SERVICES__"
COVERAGE_MIN="__COVERAGE_MIN__"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$(cd "$SELF_DIR/../.." && pwd)/.vibearch/scripts/verify_lib.sh"
ROOT="$(repo_root "$SELF_DIR")"
cd "$ROOT"

printf 'verify: %s (component loop)\n' "$LOOP_NAME"

# ---- 1. real boundaries must be up before integration tests run
if [[ -n "$BOUNDARIES" && -n "$SERVICES" ]]; then
  trap compose_down EXIT
  # shellcheck disable=SC2086
  require_services $SERVICES
fi

# ---- 2. tests + coverage
# shellcheck disable=SC2086
run_tests_with_coverage "$COVERAGE_MIN" "$SRC_PATHS" $UNIT_TESTS $INTEGRATION_TESTS

# ---- 3. assertion density: no padded test counts
step "assertion density"
# shellcheck disable=SC2086
python3 .vibearch/scripts/check_assertions.py $UNIT_TESTS $INTEGRATION_TESTS

# ---- 4. no silent mocks at a boundary this loop actually touches
step "no silent mocks (component)"
if [[ -n "$BOUNDARIES" ]]; then
  [[ -n "$INTEGRATION_TESTS" ]] || fail \
    "$LOOP_NAME touches the $BOUNDARIES boundary but declares no integration tests — mocking is legal in tests/unit only"
  # shellcheck disable=SC2086
  python3 .vibearch/scripts/check_mocks.py --mode component \
    --boundaries "$BOUNDARIES" \
    --tests $UNIT_TESTS $INTEGRATION_TESTS \
    --real-tests $INTEGRATION_TESTS
else
  printf 'loop touches no critical boundary — nothing to prove\n'
fi

printf '\nPASS: %s\n' "$LOOP_NAME"

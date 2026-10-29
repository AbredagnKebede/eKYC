#!/usr/bin/env bash
# verify.sh — COMPONENT loop gate for loop_unit_01_db-postgres
#
# Generated from .vibearch/templates/verify_component.sh by the roadmap agent.
# Placeholders the agent must replace:
#   loop_unit_01_db-postgres      e.g. loop_unit_03_matching
#   src/models/base.py src/models/application.py src/models/audit.py migrations/env.py      space-separated source paths this loop owns (coverage scope)
#   tests/unit/test_db_postgres.py     space-separated unit test paths        (required)
#   tests/integration/test_db_postgres.py  integration test paths            (required iff boundaries non-empty)
#   db     comma-separated: db,queue,external_api,worker — "" if none
#   postgres       compose services needed for the integration tests — "" if none
#   85   line-coverage gate, default 85
#
# Gate order: tests green -> coverage -> assertion density -> no silent mocks.
# Any non-zero exit means the loop is NOT done.

set -euo pipefail

LOOP_NAME="loop_unit_01_db-postgres"
SRC_PATHS="src/models"
UNIT_TESTS="tests/unit/test_db_postgres.py"
INTEGRATION_TESTS="tests/integration/test_db_postgres.py"
BOUNDARIES="db"
SERVICES="postgres"
COVERAGE_MIN="85"

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

#!/usr/bin/env bash
# verify.sh — CHAOS loop gate for loop_chaos
#
# Generated from .vibearch/templates/verify_chaos.sh by the roadmap agent.
# Placeholders the agent must replace:
#   __CHAOS_TESTS__     test paths under tests/chaos/
#   __BOUNDARIES__      comma-separated: db,queue,external_api,worker
#   __SERVICES__        every compose service, workers included
#   __REQUIRED_ENV__    sandbox credential env vars
#   __SCENARIOS__       comma-separated scenario ids from system_guide.md §9 that MUST
#                       each be covered by a test (e.g. CH-01,CH-02,...)
#
# This loop owns the failures that only appear in time and under stress:
#   token/credential expiry and refresh, timeout and retry, circuit breaking,
#   duplicate and concurrent submissions, service restart mid-operation,
#   partial failure and compensation, dead-letter routing.
#
# Not an end-to-end suite: journey loops own that, and this loop assumes they already pass.
#
# Fault INJECTION is expected here. Faking the boundary being injected into is not:
# the database, broker, workers, and sandbox APIs stay real.

set -euo pipefail

CHAOS_TESTS="__CHAOS_TESTS__"
BOUNDARIES="__BOUNDARIES__"
SERVICES="__SERVICES__"
REQUIRED_ENV="__REQUIRED_ENV__"
SCENARIOS="__SCENARIOS__"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$(cd "$SELF_DIR/../.." && pwd)/.vibearch/scripts/verify_lib.sh"
ROOT="$(repo_root "$SELF_DIR")"
cd "$ROOT"

printf 'verify: loop_chaos (failure modes and time-dependent behavior)\n'

if [[ -n "$REQUIRED_ENV" ]]; then
  step "required credentials"
  # shellcheck disable=SC2086
  require_env $REQUIRED_ENV
fi

trap compose_down EXIT
[[ -n "$SERVICES" ]] || fail "loop_chaos declares no services — chaos needs a real running system"
# shellcheck disable=SC2086
require_services $SERVICES

# ---- every §9 scenario must be covered by a test that cites its id
step "resilience scenario coverage"
if [[ -n "$SCENARIOS" ]]; then
  missing=""
  IFS=',' read -r -a _scenarios <<< "$SCENARIOS"
  for scenario in "${_scenarios[@]}"; do
    scenario="$(printf '%s' "$scenario" | tr -d '[:space:]')"
    [[ -n "$scenario" ]] || continue
    # shellcheck disable=SC2086
    if ! grep -rqF "$scenario" $CHAOS_TESTS 2>/dev/null; then
      missing="$missing $scenario"
    fi
  done
  [[ -z "$missing" ]] || fail \
    "no chaos test cites these system_guide.md §9 scenarios:$missing — every documented failure mode needs a test"
  printf 'all %d scenario(s) cited\n' "${#_scenarios[@]}"
else
  fail "loop_chaos declares no scenarios — §9 Resilience and Failure Modes must enumerate them"
fi

# ---- run the failure-injection suite
# shellcheck disable=SC2086
run_tests $CHAOS_TESTS

# ---- boundaries under test stay real
step "no silent mocks (chaos)"
# shellcheck disable=SC2086
python3 .vibearch/scripts/check_mocks.py --mode chaos \
  --boundaries "$BOUNDARIES" \
  --tests $CHAOS_TESTS

step "assertion density"
# shellcheck disable=SC2086
python3 .vibearch/scripts/check_assertions.py $CHAOS_TESTS

printf '\nPASS: loop_chaos\n'

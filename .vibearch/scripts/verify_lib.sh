#!/usr/bin/env bash
# verify_lib.sh — shared, stack-agnostic helpers sourced by every loop's verify.sh.
#
# Sourced, never executed directly. Provides:
#   repo_root                 absolute path to the pipeline root
#   detect_runner             pytest | npm | go | cargo | maven | gradle | rspec | unknown
#   run_tests <paths...>      run the test suite for the given paths
#   run_tests_with_coverage <min> <src> <paths...>
#                             run with coverage and FAIL if below <min> percent
#   require_services <svc...>  bring compose services up and wait until healthy
#   compose_down              tear the stack down (registered as an EXIT trap by callers)
#   fail <msg>                print and exit 1
#   step <msg>                print a progress banner
#
# Design rule: never pass silently. If coverage cannot be measured for the detected
# stack, this library FAILS rather than skipping the gate — an unmeasured gate that
# reports success is the exact failure mode this pipeline exists to prevent.

set -euo pipefail

VIBE_COMPOSE_FILE="${VIBE_COMPOSE_FILE:-}"
VIBE_COMPOSE_STARTED=0

repo_root() {
  local dir="${1:-$PWD}"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/system_guide.md" || -d "$dir/.pipeline" ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  printf '%s\n' "$PWD"
}

step() { printf '\n=== %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

detect_runner() {
  if [[ -n "${VIBE_TEST_RUNNER:-}" ]]; then printf '%s\n' "$VIBE_TEST_RUNNER"; return; fi
  if [[ -f go.mod ]]; then printf 'go\n'; return; fi
  if [[ -f Cargo.toml ]]; then printf 'cargo\n'; return; fi
  if [[ -f pom.xml ]]; then printf 'maven\n'; return; fi
  if [[ -f build.gradle || -f build.gradle.kts ]]; then printf 'gradle\n'; return; fi
  if [[ -f package.json ]]; then printf 'npm\n'; return; fi
  if [[ -f Gemfile ]]; then printf 'rspec\n'; return; fi
  if [[ -f pyproject.toml || -f pytest.ini || -f setup.cfg || -f tox.ini || -f requirements.txt ]]; then
    printf 'pytest\n'; return
  fi
  printf 'unknown\n'
}

_npm_script_exists() {
  [[ -f package.json ]] && grep -q "\"$1\"[[:space:]]*:" package.json
}

# _python_pkg_present <pip-name> — ask pip's metadata, not `import`.
# An uninstalled package can leave its directory behind, and Python then imports it as an
# empty namespace package, so a bare `import` reports success for a package that is gone.
_python_pkg_present() {
  python3 - "$1" <<'PY' 2>/dev/null
import sys
from importlib.metadata import PackageNotFoundError, version
try:
    version(sys.argv[1])
except PackageNotFoundError:
    sys.exit(1)
PY
}

# ensure_python_pkg <pip-name> — install a missing test dependency.
# A loop should fail because the code is wrong, not because a coverage plugin is absent.
# Set VIBE_NO_AUTO_INSTALL=1 to require the environment be prepared ahead of time.
ensure_python_pkg() {
  local pkg="$1"
  _python_pkg_present "$pkg" && return 0
  [[ -z "${VIBE_NO_AUTO_INSTALL:-}" ]] \
    || fail "$pkg is not installed and VIBE_NO_AUTO_INSTALL is set"

  step "installing missing test dependency: $pkg"
  local -a pip=(python3 -m pip install --quiet)
  [[ -n "${VIRTUAL_ENV:-}" ]] || pip+=(--user)
  if ! "${pip[@]}" "$pkg"; then
    # Distro pythons refuse --user installs (PEP 668); a virtualenv is the answer.
    [[ -n "${VIRTUAL_ENV:-}" ]] && fail "could not install $pkg into $VIRTUAL_ENV"
    fail "could not install $pkg into this Python. Create a virtualenv and re-run:
  python3 -m venv .venv && . .venv/bin/activate"
  fi
  _python_pkg_present "$pkg" || fail "$pkg reported as installed but pip cannot see it"
}

# ensure_cargo_tool <binary> <crate>
ensure_cargo_tool() {
  command -v "$1" >/dev/null && return 0
  [[ -z "${VIBE_NO_AUTO_INSTALL:-}" ]] \
    || fail "$1 is not installed and VIBE_NO_AUTO_INSTALL is set"
  step "installing missing test dependency: $2"
  cargo install --quiet "$2" || fail "could not install $2"
  command -v "$1" >/dev/null || fail "$2 installed but $1 is not on PATH"
}

run_tests() {
  local runner; runner="$(detect_runner)"
  step "running tests ($runner): $*"
  case "$runner" in
    pytest) ensure_python_pkg pytest; python3 -m pytest -q "$@" ;;
    npm)    if _npm_script_exists test; then npm test -- "$@"; else npx --yes jest "$@"; fi ;;
    go)     go test ./... ;;
    cargo)  cargo test ;;
    maven)  mvn -q test ;;
    gradle) ./gradlew test ;;
    rspec)  bundle exec rspec "$@" ;;
    *)      fail "cannot detect a test runner — set VIBE_TEST_RUNNER or add a runner case to .vibearch/scripts/verify_lib.sh" ;;
  esac
}

# run_tests_with_coverage <min_percent> <source_paths> <test_paths...>
# <source_paths> may be a space-separated list; every entry becomes its own coverage scope.
run_tests_with_coverage() {
  local min="$1"; shift
  local src="$1"; shift
  local runner; runner="$(detect_runner)"
  step "running tests with coverage >= ${min}% ($runner): $*"

  # Split the source list once; a single quoted "src/a src/b" is not a path.
  local -a src_paths=()
  read -r -a src_paths <<< "$src"
  [[ ${#src_paths[@]} -gt 0 ]] || fail "no source paths given — coverage scope would be empty"

  case "$runner" in
    pytest)
      ensure_python_pkg pytest
      ensure_python_pkg pytest-cov
      local -a cov_args=()
      local one
      for one in "${src_paths[@]}"; do cov_args+=("--cov=$one"); done
      python3 -m pytest -q "${cov_args[@]}" --cov-report=term-missing \
        "--cov-fail-under=$min" "$@"
      ;;
    npm)
      npx --yes jest --coverage \
        --coverageThreshold "{\"global\":{\"lines\":$min,\"statements\":$min}}" "$@"
      ;;
    go)
      local profile; profile="$(mktemp)"
      # -coverpkg scopes coverage to this loop's packages instead of the whole module.
      local pkgs; pkgs="$(printf '%s,' "${src_paths[@]}")"; pkgs="${pkgs%,}"
      go test ./... -coverpkg="$pkgs" -coverprofile="$profile"
      local total
      total="$(go tool cover -func="$profile" | awk '/^total:/ {gsub(/%/,"",$3); print $3}')"
      rm -f "$profile"
      [[ -n "$total" ]] || fail "could not parse go coverage total"
      awk -v got="$total" -v min="$min" 'BEGIN { exit !(got + 0 >= min + 0) }' \
        || fail "coverage ${total}% is below the ${min}% gate"
      printf 'coverage: %s%%\n' "$total"
      ;;
    cargo)
      ensure_cargo_tool cargo-llvm-cov cargo-llvm-cov
      cargo llvm-cov --fail-under-lines "$min"
      ;;
    maven)
      # jacoco wants a 0..1 ratio, so 85 becomes 0.85 and 100 becomes 1.00.
      local ratio; ratio="$(awk -v m="$min" 'BEGIN { printf "%.2f", m / 100 }')"
      mvn -q verify "-Djacoco.check.lineRatio=$ratio"
      ;;
    gradle) ./gradlew test jacocoTestCoverageVerification ;;
    rspec)
      bundle exec rspec "$@"
      [[ -f coverage/.last_run.json ]] \
        || fail "simplecov produced no coverage/.last_run.json — coverage is unmeasured"
      python3 - "$min" <<'PY'
import json, sys
covered = json.load(open("coverage/.last_run.json"))["result"]
value = covered.get("line") or covered.get("covered_percent") or 0
minimum = float(sys.argv[1])
print(f"coverage: {value}%")
sys.exit(0 if float(value) >= minimum else 1)
PY
      ;;
    *) fail "cannot detect a test runner — set VIBE_TEST_RUNNER or add a runner case to .vibearch/scripts/verify_lib.sh" ;;
  esac
}

_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then printf 'docker compose\n'
  elif command -v docker-compose >/dev/null 2>&1; then printf 'docker-compose\n'
  else return 1; fi
}

compose_down() {
  [[ "$VIBE_COMPOSE_STARTED" == "1" ]] || return 0
  local cc; cc="$(_compose_cmd)" || return 0
  step "tearing down compose stack"
  # shellcheck disable=SC2086
  $cc ${VIBE_COMPOSE_FILE:+-f "$VIBE_COMPOSE_FILE"} down -v --remove-orphans || true
  VIBE_COMPOSE_STARTED=0
}

# require_services <service...> — real infrastructure, not a fake broker.
# Journey and chaos loops call this; it FAILS rather than falling back to mocks.
require_services() {
  [[ $# -gt 0 ]] || return 0
  local cc
  cc="$(_compose_cmd)" || fail "docker compose is not available, so the real $* boundary cannot be started. A journey loop must not fall back to mocks — install Docker or run this loop where the real services exist."

  step "starting real services: $*"
  # shellcheck disable=SC2086
  $cc ${VIBE_COMPOSE_FILE:+-f "$VIBE_COMPOSE_FILE"} up -d --wait "$@" 2>/dev/null || {
    # --wait needs a recent compose; fall back to a health poll.
    # shellcheck disable=SC2086
    $cc ${VIBE_COMPOSE_FILE:+-f "$VIBE_COMPOSE_FILE"} up -d "$@" \
      || fail "could not start services: $*"
    local deadline=$((SECONDS + ${VIBE_HEALTH_TIMEOUT:-120}))
    local svc
    for svc in "$@"; do
      while :; do
        local state
        # shellcheck disable=SC2086
        state="$($cc ${VIBE_COMPOSE_FILE:+-f "$VIBE_COMPOSE_FILE"} ps --format '{{.Service}} {{.Health}} {{.State}}' 2>/dev/null \
                 | awk -v s="$svc" '$1 == s { print ($2 != "" ? $2 : $3) }' | head -n1)"
        case "$state" in
          healthy|running) break ;;
          unhealthy|exited|dead) fail "service $svc is $state — the real boundary is unavailable" ;;
        esac
        (( SECONDS < deadline )) || fail "service $svc did not become healthy within ${VIBE_HEALTH_TIMEOUT:-120}s"
        sleep 2
      done
    done
  }
  VIBE_COMPOSE_STARTED=1
}

# require_env <VAR...> — a journey loop against a real sandbox needs real credentials.
require_env() {
  local missing=()
  local var
  for var in "$@"; do
    [[ -n "${!var:-}" ]] || missing+=("$var")
  done
  if (( ${#missing[@]} )); then
    fail "missing required environment variable(s): ${missing[*]} — see dependency_list.md. Do not substitute a mock."
  fi
}

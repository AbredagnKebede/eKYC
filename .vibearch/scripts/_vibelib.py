#!/usr/bin/env python3
"""_vibelib.py — shared stdlib-only helpers for the vibearch gate scripts.

Imported by check_*.py and topology_validator.py. Every heuristic here is
stack-agnostic by design: it matches patterns, never a specific test runner, so a
Python, TypeScript, Go, Ruby, or JVM project passes through the same gates.

Not a gate itself — has no main().
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# --------------------------------------------------------------- repo layout

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "out", ".next", ".nuxt", "target", "vendor", ".gradle",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "coverage", "htmlcov",
    ".pipeline", "release_evidence", ".terraform", ".idea", ".vscode",
    # The pipeline's own installed gates: tooling, not the system under test.
    ".vibearch",
}

# Prose-only trees: excluded when we ask "does this exist in CODE?"
DOC_DIRS = {
    "research", "ArchitecturalDecisions", "developerStrategies", "spec_amendments",
    "journeys", "loops", "templates", "docs", "doc",
}

SOURCE_EXTS = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".kt", ".kts", ".rb", ".php", ".cs", ".swift", ".scala", ".ex", ".exs",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".sql", ".sh", ".bash", ".dart", ".gradle",
}

CONFIG_EXTS = {
    ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".env", ".tf", ".tfvars",
    ".hcl", ".conf", ".properties", ".xml", ".plist",
}

# Files with no extension that still count as deployment/config code.
CONFIG_NAMES = {
    "Dockerfile", "Makefile", "Procfile", "Caddyfile", "Jenkinsfile", ".env.example",
    "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
}

# Pipeline bookkeeping files. They are the DOCUMENTATION side of a parity check, so a
# code search must never count a hit inside them — otherwise `topology_manifest.json`
# listing a queue would "prove" that queue exists in code, and the gate would pass on
# its own input.
PIPELINE_ARTIFACTS = {
    "topology_manifest.json", "system_graph.json", "run_state.json",
    "execution_state.json", "smoke_test_report.md", "roadmap.md", "progress.md",
    "Lessons.md", "IMPROVEMENTS.md", "CLAUDE.md",
}

LINE_COMMENT = {
    ".py": "#", ".rb": "#", ".sh": "#", ".bash": "#", ".yml": "#", ".yaml": "#",
    ".toml": "#", ".ini": "#", ".cfg": "#", ".ex": "#", ".exs": "#", ".tf": "#",
    ".hcl": "#", ".conf": "#", ".properties": "#",
    ".js": "//", ".mjs": "//", ".cjs": "//", ".ts": "//", ".tsx": "//", ".jsx": "//",
    ".go": "//", ".rs": "//", ".java": "//", ".kt": "//", ".kts": "//", ".cs": "//",
    ".swift": "//", ".scala": "//", ".c": "//", ".cc": "//", ".cpp": "//", ".h": "//",
    ".hpp": "//", ".php": "//", ".dart": "//", ".gradle": "//",
    ".sql": "--",
}


def repo_root(start: Path | str | None = None) -> Path:
    """Walk up from `start` (default: cwd) to the directory that owns the pipeline."""
    here = Path(start or Path.cwd()).resolve()
    for cand in [here, *here.parents]:
        if (cand / "system_guide.md").exists() or (cand / ".pipeline").is_dir():
            return cand
        if (cand / "Idea_scaff.md").exists():
            return cand
        # Weakest marker, so it is checked last: present before any stage has run.
        if (cand / ".vibearch").is_dir():
            return cand
    # These scripts live in <root>/.vibearch/scripts/, so the root is two levels up.
    return Path(__file__).resolve().parent.parent.parent


def load_json(path: Path, default=None):
    """Parse JSON, returning (value, error_string). Never raises."""
    if not Path(path).exists():
        return default, f"{path} does not exist"
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return default, f"{path} is not valid JSON — {exc}"


def read_text(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def iter_files(root: Path, exts=None, skip_docs: bool = True, extra_skip=()):
    """Yield files under `root`, pruning vendor/build/doc trees as it walks."""
    root = Path(root)
    skip = set(SKIP_DIRS) | set(extra_skip)
    if skip_docs:
        skip |= DOC_DIRS
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in skip:
                    stack.append(entry)
            elif exts is None or entry.suffix in exts or entry.name in CONFIG_NAMES:
                yield entry


def code_and_config_files(root: Path, skip_docs: bool = True):
    return iter_files(root, SOURCE_EXTS | CONFIG_EXTS, skip_docs=skip_docs)


# ---------------------------------------------------- markdown section parsing

def split_sections(text: str, level: int = 2):
    """Split markdown into [(heading, body)] at exactly `level` hashes."""
    marker = "#" * level
    pattern = re.compile(rf"^{marker}[ \t]+(.+?)[ \t]*$", re.M)
    matches = list(pattern.finditer(text))
    out = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((match.group(1).strip(), text[match.end():end]))
    return out


def _heading_number(heading: str) -> str:
    token = heading.strip().split()[0] if heading.strip() else ""
    return token.lstrip("§#").rstrip(".:—-")


def find_section(text: str, number: str | None = None,
                 title_contains: str | None = None, level: int = 2):
    """Locate a section by its number (`"9"`, `"9.2"`) or a case-insensitive title
    substring. Returns (heading, body) or (None, None)."""
    needle = title_contains.lower() if title_contains else None
    for heading, body in split_sections(text, level):
        if number is not None and _heading_number(heading) == str(number):
            return heading, body
        if needle and needle in heading.lower():
            return heading, body
    return None, None


DEPLOY_ARTIFACT_EXTS = (".yml", ".yaml", ".tf", ".json", ".hcl", ".toml", ".conf", ".xml")

DEPLOY_ARTIFACT_NAME = re.compile(
    r"^(?:Dockerfile|docker-compose|compose|Procfile|Makefile|Chart|values)[\w.\-]*$"
)


def deployment_artifacts(text: str) -> list[str]:
    """Extract the `backticked` deployment artifact PATHS from a § Deployment body.

    A §Deployment section also backticks endpoints (`/healthz`), env vars (`DATABASE_URL`),
    and commands (`python -m src.workers.matching`). Only file-shaped tokens are artifacts;
    treating `/healthz` as a file makes the Stage 6 parity check demand a file that was
    never supposed to exist.
    """
    out = []
    for raw in re.findall(r"`([^`\n]+)`", text or ""):
        token = raw.strip()
        if not token or token.startswith(("/", "http://", "https://")):
            continue          # URL path or endpoint, not a file
        if not re.fullmatch(r"[\w.\-]+(?:/[\w.\-]+)*", token):
            continue          # has spaces or shell syntax — a command, not a path
        if token.isupper() and "." not in token and "/" not in token:
            continue          # ENV_VAR_NAME
        basename = token.rsplit("/", 1)[-1]
        if token.endswith(DEPLOY_ARTIFACT_EXTS) or DEPLOY_ARTIFACT_NAME.match(basename):
            if token not in out:
                out.append(token)
    return out


def is_substantive(body: str, min_chars: int = 40) -> bool:
    """True when a section body carries real content, not a placeholder."""
    stripped = re.sub(r"<!--.*?-->", " ", body or "", flags=re.S)
    stripped = re.sub(r"^\s*[-*+]\s*$", " ", stripped, flags=re.M)
    plain = stripped.strip()
    if len(plain) < min_chars:
        return False
    placeholder = re.compile(
        r"^(tbd|todo|n/?a|none|pending|fixme|xxx|\.\.\.|_?no .* yet\.?_?)$",
        re.I,
    )
    meaningful = [
        ln.strip(" \t-*+_")
        for ln in plain.splitlines()
        if ln.strip(" \t-*+_") and not placeholder.match(ln.strip(" \t-*+_.").lower())
    ]
    return bool(meaningful) and len(" ".join(meaningful)) >= min_chars


# ------------------------------------------------------- code / test text prep

def strip_comments(text: str, ext: str = "") -> str:
    """Remove comments and docstrings so counters do not score prose."""
    if ext == ".py":
        text = re.sub(r'"""(?:.|\n)*?"""', "", text)
        text = re.sub(r"'''(?:.|\n)*?'''", "", text)
    if ext in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
               ".kt", ".kts", ".cs", ".swift", ".scala", ".c", ".cc", ".cpp",
               ".h", ".hpp", ".php", ".dart", ".gradle", ".sql"}:
        text = re.sub(r"/\*(?:.|\n)*?\*/", "", text)
    marker = LINE_COMMENT.get(ext)
    if marker:
        out = []
        for line in text.splitlines():
            idx = line.find(marker)
            # Keep shebangs and avoid cutting inside an obvious string literal.
            if idx == 0 and line.startswith("#!"):
                continue
            if idx >= 0 and line.count('"', 0, idx) % 2 == 0 and line.count("'", 0, idx) % 2 == 0:
                line = line[:idx]
            out.append(line)
        text = "\n".join(out)
    return text


_CONTINUES = re.compile(r"(?:[(\[{,+\-*/%&|^~=<>:.\\]|\b(?:and|or|not|in|is)\b)\s*$")


def logical_lines(text: str, ext: str = "") -> list[str]:
    """Join wrapped expressions into single logical lines.

    Multi-line assertions (`expect(\\n  x\\n).toBe(1)`) would otherwise score zero.
    Bracket depth is a heuristic — literals containing brackets can skew it — which is
    acceptable for counting, not for parsing.
    """
    lines = strip_comments(text, ext).splitlines()
    out: list[str] = []
    buf = ""
    depth = 0
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        buf = f"{buf} {stripped}".strip() if buf else stripped
        depth += stripped.count("(") + stripped.count("[") + stripped.count("{")
        depth -= stripped.count(")") + stripped.count("]") + stripped.count("}")
        depth = max(depth, 0)
        if depth == 0 and not _CONTINUES.search(stripped):
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


# ------------------------------------------------------------ assertion scoring

STRONG_ASSERTIONS = [
    # Python / pytest
    r"\bassert\s+.+?\s*(?:==|!=|<=|>=|<|>)\s*.+",
    r"\bassert\s+.+?\s+(?:not\s+)?in\s+.+",
    r"\bassert\s+.+?\s+is\s+(?:True|False)\b",
    r"\bassert(?:Equal|Equals|NotEqual|In|NotIn|Greater|Less|AlmostEqual|Regex|"
    r"Raises|Warns|Count|ListEqual|DictEqual|SetEqual|TupleEqual|SequenceEqual|"
    r"MultiLineEqual|IsInstance)\w*\s*\(",
    r"\bpytest\.raises\s*\(",
    r"\bassert_(?:frame|series|array|allclose|almost)\w*\s*\(",
    # JS / TS
    r"\bexpect\s*\(.*?\)\s*(?:\.\s*(?:not|resolves|rejects)\s*)*\.\s*"
    r"(?:toBe|toEqual|toStrictEqual|toMatch|toMatchObject|toMatchSnapshot|toContain|"
    r"toContainEqual|toHaveLength|toHaveProperty|toHaveBeenCalledWith|"
    r"toHaveBeenCalledTimes|toThrow|toBeCloseTo|toBeGreaterThan|toBeLessThan)\b",
    r"\.should\s*\.\s*(?:equal|eql|deep|include|match|have)\b",
    r"\bassert\s*\.\s*(?:strictEqual|deepStrictEqual|deepEqual|equal|match|throws)\s*\(",
    # Go
    r"\b(?:assert|require)\s*\.\s*(?:Equal|EqualValues|NotEqual|Len|Contains|"
    r"ElementsMatch|JSONEq|Error|EqualError|NoError|Regexp|Subset)\s*\(",
    r"\bt\s*\.\s*(?:Fatalf?|Errorf?)\s*\(",
    # JVM / Ruby / PHP
    r"\bassertThat\s*\(",
    r"\bassert(?:Equals|Same|ArrayEquals|Throws|Contains)\s*\(",
    r"\bexpect\s*\(.*?\)\s*\.\s*to\s+(?:eq|eql|equal|include|match|raise_error|have)\b",
    r"\bassert(?:Same|Count|StringContainsString|JsonStringEqualsJsonString)\s*\(",
    # Boundary-flavoured assertions (HTTP status, row counts, queue depth)
    r"status(?:_code)?\s*(?:==|===|,)\s*[1-5]\d\d\b",
    r"\.status\s*(?:==|===)\s*[1-5]\d\d\b",
    r"\bassert_?(?:response|status|json|contains|matches|redirect|schema)\w*\s*\(",
]

WEAK_ASSERTIONS = [
    r"\bassert\s+True\s*$",
    r"\bassert\s+(?:1\s*==\s*1|True\s*==\s*True)\s*$",
    r"\bassertTrue\s*\(\s*True\s*\)",
    r"\bassert\s+[\w.\[\]()'\"]+\s+is\s+not\s+None\s*$",
    r"\bassert\s+[\w.\[\]()'\"]+\s*!=\s*None\s*$",
    r"\bassert\s+[\w.\[\]]+\s*$",
    r"\bassertIsNotNone\s*\(",
    r"\bassertNotNull\s*\(",
    r"\bassert\s*\.\s*(?:NotNil|Nil|True|False)\s*\(",
    r"\bexpect\s*\(.*?\)\s*(?:\.\s*not\s*)?\.\s*"
    r"(?:toBeDefined|toBeTruthy|toBeFalsy|toBeNull|toBeUndefined)\s*\(",
    r"\bassert\s+len\s*\(\s*[\w.\[\]]+\s*\)\s*>\s*0\s*$",
    r"\bassert\s+not\s+[\w.\[\]]+\s*$",
]

_STRONG_RE = [re.compile(p) for p in STRONG_ASSERTIONS]
_WEAK_RE = [re.compile(p) for p in WEAK_ASSERTIONS]


def score_assertions(text: str, ext: str = "") -> tuple[int, int, int]:
    """Return (code_lines, strong_assertions, weak_assertions) for one test file.

    A line is classified weak-first so `assert x is not None` never counts as strong.
    """
    lines = logical_lines(text, ext)
    strong = weak = 0
    for line in lines:
        if any(rx.search(line) for rx in _WEAK_RE):
            weak += 1
        elif any(rx.search(line) for rx in _STRONG_RE):
            strong += 1
    return len(lines), strong, weak


# ------------------------------------------------------------- mock detection

# Generic test-double machinery: never acceptable at a journey-loop boundary.
GENERIC_MOCK_PATTERNS = {
    "unittest.mock": r"\bfrom\s+unittest\s+import\s+mock\b|\bimport\s+unittest\.mock\b|\bfrom\s+unittest\.mock\s+import\b",
    "mock library": r"\bfrom\s+mock\s+import\b|\bimport\s+mock\b",
    "MagicMock/AsyncMock": r"\b(?:MagicMock|AsyncMock|NonCallableMock)\s*\(",
    # Only forms that unambiguously mean unittest.mock.patch: a bare `patch(...)` is as
    # likely an HTTP PATCH helper, and real use always needs one of the imports above.
    "mock.patch": r"@\s*(?:mock\.)?patch\b"
                  r"|\bwith\s+(?:mock\.)?patch\s*[.(]"
                  r"|(?:^|[^\w.])(?:mock\.)?patch\s*\.\s*(?:object|dict|multiple)\s*\("
                  r"|\bmock\s*\.\s*patch\s*\(",
    "monkeypatch": r"\bmonkeypatch\s*\.\s*(?:setattr|setitem|setenv|delattr)\b",
    "jest.mock": r"\bjest\s*\.\s*(?:mock|fn|spyOn|doMock)\s*\(",
    "vi.mock": r"\bvi\s*\.\s*(?:mock|fn|spyOn)\s*\(",
    "sinon": r"\bsinon\s*\.\s*(?:stub|mock|fake|replace|createStubInstance)\b",
    "testdouble": r"\btd\s*\.\s*(?:replace|func|object)\s*\(",
    "gomock": r"\bgomock\s*\.\s*NewController\b|\bNewMock[A-Z]\w*\s*\(",
    "Mockito": r"\bMockito\s*\.\s*(?:mock|when|spy)\b|@Mock\b|@MockBean\b",
    "rspec double": r"\b(?:instance_double|class_double|double)\s*\(",
    "proxyquire": r"\bproxyquire\s*\(",
}

BOUNDARY_MOCK_PATTERNS = {
    "db": {
        "sqlite in-memory": r":memory:|sqlite:///?:memory:",
        "mongomock": r"\bmongomock\b",
        "fakeredis": r"\bfakeredis\b|\bioredis-mock\b|\bredis-mock\b",
        "pg-mem": r"\bpg-mem\b",
        "in-memory repository": r"\bIn ?Memory(?:Db|Database|Repository|Store|Session|Adapter)\b",
        "h2 in-memory": r"jdbc:h2:mem:",
        "sqlite file swap": r"\bsqlite3?\s*\.\s*connect\s*\(\s*['\"]:memory:",
        "stubbed ORM": r"\bStubQuery|\bFakeSession\b|\bFakeRepository\b",
    },
    "queue": {
        "memory transport": r"memory://|\bin-?memory-?(?:broker|transport|queue)\b",
        "fake broker": r"\bFake(?:Broker|Producer|Consumer|Queue|Kafka|Rabbit)\w*\b",
        "mock broker": r"\bMock(?:Broker|Producer|Consumer|Queue|Kafka|Rabbit|Channel)\w*\b",
        "celery eager": r"task_always_eager|CELERY_ALWAYS_EAGER|ALWAYS_EAGER\s*=\s*True",
        "stub publish": r"\bStub(?:Publisher|Producer|Consumer|Dispatcher)\b",
        "direct handler call": r"\b(?:handle|consume|process)_\w*event\s*\(\s*(?:payload|event|msg|message)\b",
    },
    "external_api": {
        "responses": r"\bimport\s+responses\b|\bresponses\s*\.\s*(?:add|activate|RequestsMock)\b",
        "requests_mock": r"\brequests_mock\b",
        "httpretty": r"\bhttpretty\b",
        "aioresponses": r"\baioresponses\b",
        "respx": r"\brespx\b",
        "nock": r"\bnock\s*\(|\brequire\(['\"]nock['\"]\)",
        "msw": r"\bmsw\b|\bsetupServer\s*\(",
        "vcr/betamax": r"\bvcr\b|\bbetamax\b|\bvcr_cassette\b|\buse_cassette\b",
        "wiremock": r"\bWireMock\b|\bwiremock\b",
        "webmock": r"\bWebMock\b|\bstub_request\s*\(",
        "fetch stub": r"\b(?:global\.)?fetch\s*=\s*(?:jest\.fn|vi\.fn|sinon)",
        "httpx MockTransport": r"\bMockTransport\s*\(",
    },
    "worker": {
        "synchronous invoke": r"\bworker\s*\.\s*(?:run_once|process_one|handle)\s*\(",
        "fake worker": r"\b(?:Fake|Mock|Stub)Worker\b",
        "inline task run": r"\.\s*apply\s*\(\s*\)|\.\s*run\s*\(\s*\)\s*#\s*inline",
    },
}

# Evidence a test really crossed the boundary instead of faking it.
REAL_BOUNDARY_PATTERNS = {
    "db": r"\btestcontainers\b|\bpostgres(?:ql)?://|\bmysql://|\bmariadb://|\bmongodb(?:\+srv)?://|"
          r"\bDATABASE_URL\b|\bpsycopg2?\b|\basyncpg\b|\bpg8000\b|\bmysql2\b|\bpq\.|"
          r"\balembic\b|\bmigrat(?:e|ion)s?\b|\bjdbc:postgresql|\bprisma\b|\bknex\b|"
          r"\bTypeOrm\b|\bsqlalchemy\.create_engine\s*\(",
    "queue": r"\bamqp://|\bkafka://|\bredis://|\bnats://|\bsqs\b|\bpika\b|\baio_pika\b|"
             r"\bconfluent_kafka\b|\bkafkajs\b|\bamqplib\b|\bBROKER_URL\b|\bRABBITMQ\w*\b|"
             r"\bKAFKA_BROKERS?\b|\btestcontainers\b",
    "external_api": r"\bsandbox\b|\bSANDBOX\b|\b_TEST_(?:KEY|TOKEN|SECRET)\b|\btest_api_key\b|"
                    r"\bhttps?://[\w.-]*sandbox[\w.-]*|\bstaging\b",
    "worker": r"\bdocker\s+compose\b|\bsubprocess\.(?:Popen|run)\b|\bspawn(?:Sync)?\s*\(|"
              r"\bsupervisor\b|\bworker_process\b|\bcompose\s+up\b|\btestcontainers\b",
}

_GENERIC_MOCK_RE = {k: re.compile(v, re.M) for k, v in GENERIC_MOCK_PATTERNS.items()}
_BOUNDARY_MOCK_RE = {
    b: {k: re.compile(v, re.M) for k, v in pats.items()}
    for b, pats in BOUNDARY_MOCK_PATTERNS.items()
}
_REAL_RE = {k: re.compile(v, re.M) for k, v in REAL_BOUNDARY_PATTERNS.items()}

ALLOW_MOCK_MARKER = re.compile(r"vibearch:\s*allow-mock(?:\s*\(([^)]*)\))?", re.I)
BLACK_BOX_MARKER = re.compile(r"@?black_?box\b", re.I)


def detect_mocks(text: str, ext: str = "", boundaries=()) -> list[str]:
    """Return human-readable mock findings for the requested boundaries.

    Lines carrying a `vibearch: allow-mock` comment are exempt — an explicit,
    reviewable escape hatch rather than a silent one.
    """
    body = strip_comments(text, ext)
    allowed = set()
    for match in ALLOW_MOCK_MARKER.finditer(text):
        allowed.update(part.strip().lower() for part in (match.group(1) or "all").split(","))
    findings = []
    if "all" not in allowed:
        for name, rx in _GENERIC_MOCK_RE.items():
            if name.lower() in allowed:
                continue
            if rx.search(body):
                findings.append(f"generic test double: {name}")
        for boundary in boundaries:
            if boundary in allowed:
                continue
            for name, rx in _BOUNDARY_MOCK_RE.get(boundary, {}).items():
                if rx.search(body):
                    findings.append(f"{boundary} boundary faked: {name}")
    return findings


def detect_real_boundary(text: str, boundaries=()) -> set[str]:
    """Return the subset of `boundaries` this text shows real evidence of crossing."""
    return {b for b in boundaries if b in _REAL_RE and _REAL_RE[b].search(text)}


# --------------------------------------------------------------- test taxonomy

TEST_CATEGORIES = ("unit", "component", "integration", "contract", "journey", "chaos")

TEST_FILE_HINT = re.compile(
    r"(?:^|[/_.\-])(?:test|tests|spec|specs)(?:[/_.\-]|$)|_test\.|\.test\.|\.spec\.|Test\.\w+$",
    re.I,
)


def is_test_file(path: Path) -> bool:
    return bool(TEST_FILE_HINT.search(str(path))) and path.suffix in SOURCE_EXTS


def category_dirs(root: Path, category: str) -> list[Path]:
    """Find `tests/<category>/` anywhere in the tree (monorepos have several)."""
    root = Path(root)
    hits = []
    direct = root / "tests" / category
    if direct.is_dir():
        hits.append(direct)
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(p for p in current.iterdir() if p.is_dir())
        except OSError:
            continue
        for entry in entries:
            if entry.name in SKIP_DIRS or entry.name in DOC_DIRS:
                continue
            if entry.name == category and entry.parent.name in {"tests", "test", "spec", "__tests__"}:
                if entry not in hits:
                    hits.append(entry)
            stack.append(entry)
    return hits


def test_files_in(paths) -> list[Path]:
    out = []
    for base in paths:
        base = Path(base)
        if base.is_file():
            out.append(base)
            continue
        for candidate in iter_files(base, SOURCE_EXTS, skip_docs=False):
            out.append(candidate)
    return sorted(set(out))


# ------------------------------------------------------------------- reporting

class Report:
    """Collects failures and warnings, then exits with the right status code."""

    def __init__(self, name: str):
        self.name = name
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def fail(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def note(self, msg: str):
        self.notes.append(msg)

    def finish(self, summary: str = "") -> int:
        import sys
        for warning in self.warnings:
            print(f"WARN: {warning}", file=sys.stderr)
        for error in self.errors:
            print(f"FAIL: {error}", file=sys.stderr)
        if self.errors:
            print(
                f"\n{self.name}: {len(self.errors)} failure(s), {len(self.warnings)} warning(s)",
                file=sys.stderr,
            )
            return 1
        for note in self.notes:
            print(note)
        print(f"OK: {self.name}{(' — ' + summary) if summary else ''}")
        return 0

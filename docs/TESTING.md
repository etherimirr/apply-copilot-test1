# Testing Strategy

Three layers, fastest → slowest:

```
              ┌─────────────────────┐
              │   E2E (real browser, │   slow, expensive, rare
              │   live OpenAI)       │   (manual smoke test)
              ├─────────────────────┤
              │   Integration tests  │   FastAPI TestClient + SQLite tmp
              │   (route + db)       │   no browser, no network, fast
              ├─────────────────────┤
              │   Unit tests         │   pure functions; <1ms each
              │   (config, helpers,  │   majority of coverage
              │   field_classify,    │
              │   qa_memory, ...)    │
              └─────────────────────┘
```

## Layer 1 — Unit tests (`tests/unit/`)

**Goal**: Each pure function works correctly on a wide range of inputs.

Targets:

| Module                          | Why test                                                       |
|---------------------------------|----------------------------------------------------------------|
| `config.py`                     | path resolution / env-var overrides; cross-platform behavior   |
| `core.qa_memory`                | fuzzy match threshold; Jaccard scoring; stopwords              |
| `core.field_classify` (planned) | 60+ regex rules — one bad pattern = wrong field on every form  |
| `core.resume_editor` (planned)  | docx edits preserve format; page-count guard works             |
| `core.audit` (planned)          | keyword coverage math; addressable_coverage correctness        |
| `core.cl_writer` (planned)      | post-process AI-cliche filter; em-dash strip                   |
| `core.pdf_text` / `pdf_render`  | extract round-trip; multi-page detection                       |
| `platforms.handshake.preflight` | eligibility regex catches "US citizen", "no sponsorship", BS-only |
| `platforms.ats.detect`          | URL → ATS name mapping                                          |

Style:
- pytest, no class, no fixtures unless needed
- Parametrize when possible (`@pytest.mark.parametrize("label,expected", [...])`)
- Use property-based testing (`hypothesis`) for `field_classify` and `qa_memory`
- Mock OpenAI calls — return canned `dict` from `_llm_call`

## Layer 2 — Integration tests (`tests/integration/`)

**Goal**: Routes + DB + filesystem interact correctly. No browser, no real LLM.

Use FastAPI's `TestClient`:

```python
from fastapi.testclient import TestClient
from apply_copilot.server.main import app

client = TestClient(app)

def test_profile_roundtrip(tmp_data_root):
    r = client.put("/api/profile", json={"first_name": "Alice", "email": "a@x.com"})
    assert r.status_code == 200
    g = client.get("/api/profile").json()
    assert g["first_name"] == "Alice"
```

Each test uses a tmp `APPLY_COPILOT_HOME` so DB / files are isolated. Reset
before each test (via fixture).

Targets:
- Profile route: get / put / partial update
- Resume route: upload .docx → list → download → delete
- Applications: insert submission → list → filter by employment_type / status
- Settings: returns sane defaults
- Autopilot: start endpoint validates env (OPENAI_API_KEY required); status reports running PID

## Layer 3 — E2E (`tests/e2e/`)

**Goal**: Full path from dashboard → autopilot → real-or-fixture Handshake → submit.

Two flavors:

### 3a. **Recorded fixture E2E** (CI-able, deterministic)
- Save HTML/JSON snapshots of:
  - Handshake search page (filter buttons, pagination, job cards)
  - Handshake job detail page (Apply button, JD body)
  - Handshake apply modal (resume upload, transcript, submit)
  - Greenhouse / Lever / Workday / Ashby apply forms
- Test serves these via local fileserver
- Replace OpenAI with mock returning canned LLM responses
- Run autopilot against the fixture server
- Assert: SUBMITTED_LOG has expected entries

### 3b. **Live smoke test** (manual, before release)
- Real Handshake login (test account)
- Real OpenAI calls (small budget)
- Process 3 known internships
- Verify: 2 submitted, 1 left in pending_review
- Not in CI — run manually

## Continuous Integration

`.github/workflows/test.yml`:

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: ${{ matrix.python }} }
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest tests/unit tests/integration -v --cov=apply_copilot
      - run: pytest tests/e2e/recorded -v
```

Windows + macOS matrix added once Linux passes. E2E with real browser skipped
in CI.

## Coverage Goals

- Unit: **80%+** of non-IO code
- Integration: **all routes** hit at least once
- E2E (fixture-based): **happy path** for Handshake + each supported ATS

## Anti-patterns to avoid

- ❌ Real OpenAI calls in unit tests (cost + flakes)
- ❌ Real Playwright launches in unit tests (slow + brittle)
- ❌ Shared global state across tests (always fresh tmpdir)
- ❌ Assertions on log strings (fragile)
- ❌ Time-based assertions (use freezegun if necessary)

## Running

```bash
pip install -r requirements-dev.txt
pytest                              # full suite, unit + integration
pytest tests/unit -v               # just unit
pytest tests/unit/test_qa_memory.py::test_lookup_variant  # one
pytest --cov=apply_copilot --cov-report=term-missing
pytest -x --pdb                    # stop on first fail, drop to debugger
```

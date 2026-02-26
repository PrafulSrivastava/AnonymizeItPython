# Feature Brief: WhatsApp Anonymisation — Python Serverless (Vercel)
## Accuracy benchmark against TypeScript implementation

---

## Purpose

This is a Python implementation of the same anonymisation pipeline defined in `anonymisation-feature-brief.md`. It must be deployed alongside the TypeScript version on Vercel and expose an identical API contract so both implementations can be tested against the same 20 test cases and their outputs compared field-by-field.

The goal is accuracy benchmarking — not production deployment. Build for correctness, not for UI polish.

---

## Tech stack — do not deviate

- **Runtime:** Python 3.11 (Vercel Python serverless functions)
- **Web framework:** `FastAPI` (via Vercel's ASGI handler)
- **NER:** `spaCy` with `en_core_web_lg` + `de_core_news_lg`
- **Phone parsing:** `google-libphonenumber`
- **Blocklist matching:** `pyahocorasick`
- **PII framework:** `presidio-analyzer` (Microsoft) — sits on top of spaCy, adds structured entity detection
- **Hashing:** Python stdlib `hashlib`
- **Deployment:** Vercel Python runtime via `api/` directory
- **No database** — stateless, results returned in response only
- **No auth** — this is a benchmark tool, not a user-facing product

---

## Project structure — follow exactly

```
/api
  /anonymise.py              # POST handler — Vercel entry point
/lib
  /pipeline
    __init__.py
    regex_stripper.py        # Step 01
    ner_engine.py            # Step 02 — spaCy + Presidio
    blocklist.py             # Step 03 — pyahocorasick
    confidence_scorer.py     # Step 04
    validator.py             # Step 05
    index.py                 # Orchestrator
  /types.py                  # Pydantic models (shared data contract)
/tests
  /test_cases.py             # All 20 test cases as structured data
  /run_benchmark.py          # Runs all 20 cases, outputs comparison JSON
requirements.txt
vercel.json
```

---

## Shared API contract — must match TypeScript implementation exactly

Both implementations must accept identical request bodies and return identical response shapes. This is the contract. Do not add or remove fields.

### `POST /api/anonymise`

**Request:**
```json
{
  "rawText": "string, max 500 characters",
  "blocklist": "comma-separated string of names",
  "sessionId": "string"
}
```

**Response:**
```json
{
  "result": {
    "messageId": "string (SHA-256 hash of rawText + sessionId)",
    "originalLength": "integer",
    "cleanedText": "string",
    "tokens": [
      {
        "type": "PHONE | EMAIL | URL | HANDLE | AGE | DOB | PERSON | ORG | LOCATION | IBAN | BLOCKLIST | SENDER",
        "replacement": "string e.g. [PHONE_01]",
        "step": "integer 1–5",
        "confidence": "float 0–1"
      }
    ],
    "confidence": {
      "overall": "float 0–1",
      "signals": {
        "regexCoverage": "float 0–1",
        "nerConfidence": "float 0–1",
        "quasiIdentifierCount": "integer",
        "residualTokenDensity": "float 0–1"
      },
      "routingDecision": "pass | pass_flagged | review",
      "failureReasons": ["string"]
    },
    "status": "pass | pass_flagged | review"
  }
}
```

**Critical:** The `original` field (raw PII found) is intentionally excluded from the response in both implementations. Server-side only.

**Validation:** Return HTTP 400 if `rawText` exceeds 500 characters.

---

## Pydantic models — define in `/lib/types.py`

```python
from pydantic import BaseModel
from typing import Literal, Optional

class PipelineInput(BaseModel):
    rawText: str
    blocklist: str        # comma-separated, split server-side
    sessionId: str

class RedactionToken(BaseModel):
    type: Literal[
        "PHONE", "EMAIL", "URL", "HANDLE", "AGE", "DOB",
        "PERSON", "ORG", "LOCATION", "IBAN", "BLOCKLIST", "SENDER"
    ]
    replacement: str
    step: int
    confidence: float
    original: Optional[str] = None   # server-side only, never serialised to response

class ConfidenceSignals(BaseModel):
    regexCoverage: float
    nerConfidence: float
    quasiIdentifierCount: int
    residualTokenDensity: float

class ConfidenceScore(BaseModel):
    overall: float
    signals: ConfidenceSignals
    routingDecision: Literal["pass", "pass_flagged", "review"]
    failureReasons: list[str]

class ProcessedMessage(BaseModel):
    messageId: str
    originalLength: int
    cleanedText: str
    tokens: list[RedactionToken]
    confidence: ConfidenceScore
    status: Literal["pass", "pass_flagged", "review"]

    class Config:
        # Exclude 'original' field from any token when serialising response
        json_encoders = {}

class AnonymiseResponse(BaseModel):
    result: ProcessedMessage
```

---

## Pipeline implementation

### Step 01 — `regex_stripper.py`

Identical logic to the TypeScript Step 01. Use `google-libphonenumber` for phone parsing with regex fallback. Process patterns in this exact order — order matters because some patterns overlap:

1. WhatsApp header line — extract `timestamp_raw` and `sender_raw`, strip from body
2. Phone numbers — `phonenumbers.parse()` with region hints `["DE", "GB", "US"]` + fallback regex
3. Email addresses — RFC 5322 regex + obfuscated variants (`[at]`, `(at)`, ` at `)
4. URLs — `http(s)://` + bare domains with paths + Linktree
5. Social handles — `@username` (min 3 chars after @)
6. IBAN — regex + Luhn validation
7. Dates of birth — `DD.MM.YYYY`, `MM/DD/YY`, `born YYYY`, `born in YYYY`
8. Exact ages — `I'm N`, `I am N years old`, `aged N` — replace N with `[AGE_Xs]` where X is floor-to-decade

Return: `tuple[str, list[RedactionToken]]`

### Step 02 — `ner_engine.py`

Use both `spaCy` and `presidio-analyzer`. Initialise both **once at module level** — not inside the function handler. Vercel reuses the container between invocations so this is safe and critical for performance.

```python
import spacy
from presidio_analyzer import AnalyzerEngine

# Module-level initialisation — runs once per container
nlp_en = spacy.load("en_core_web_lg")
nlp_de = spacy.load("de_core_news_lg")
analyzer = AnalyzerEngine()
```

Processing order:
1. Run `presidio-analyzer` first — it returns structured `RecognizerResult` objects with entity type and score. Use for `PERSON`, `ORG`, `LOCATION`, `PHONE_NUMBER`, `EMAIL_ADDRESS`.
2. Run spaCy `en_core_web_lg` on the same text — union results with Presidio, preferring Presidio where they overlap (Presidio has higher precision on structured entities)
3. For any text detected as German (check for common German words or umlaut characters), additionally run `de_core_news_lg` and union results
4. Location granularity rule: GPE/LOC entities that are country names pass through unreplaced. City level and below → `[LOCATION_N]`. Use a hardcoded list of 50 country names for the check.
5. Flag any entity where Presidio score < 0.85 as `lowConfidence: True`

Return: `tuple[str, list[RedactionToken]]`

### Step 03 — `blocklist.py`

Use `pyahocorasick` for multi-pattern matching. Parse the comma-separated blocklist string, strip whitespace, build the automaton once per request.

```python
import ahocorasick

def build_automaton(terms: list[str]) -> ahocorasick.Automaton:
    A = ahocorasick.Automaton()
    for idx, term in enumerate(terms):
        A.add_word(term.lower(), (idx, term))
    A.make_automaton()
    return A
```

Rules:
- Case-insensitive — lowercase both text and terms before matching
- Whole-word only — check that match boundaries are not alphanumeric characters
- Replace matches with `[BLOCKLIST_N]`

Quasi-identifier detection:
- Role keywords list (hardcoded): `["manager", "developer", "designer", "founder", "engineer", "director", "analyst", "consultant", "cto", "ceo", "cpo", "vp", "lead", "head of", "freelance", "contractor", "intern", "student", "teacher", "doctor"]`
- Count surviving quasi-identifiers: role keyword matches + country-level locations that passed through + `[AGE_Xs]` tokens inserted in Step 01
- Set `quasi_identifier_risk: bool` and `quasi_identifier_count: int`

Return: `tuple[str, list[RedactionToken], bool, int]`

### Step 04 — `confidence_scorer.py`

Identical scoring logic to TypeScript Step 04. Weighted sum, same weights:

| Signal | Weight |
|---|---|
| `regexCoverage` | 30% |
| `nerConfidence` | 35% |
| `quasiIdentifierCount` | 20% |
| `residualTokenDensity` | 15% |

Routing thresholds:
- `>= 0.90` → `"pass"`
- `0.75 – 0.89` → `"pass_flagged"`
- `< 0.75` → `"review"`

`failureReasons` must be human-readable strings, not codes.

Return: `ConfidenceScore`

### Step 05 — `validator.py`

Three checks, identical to TypeScript Step 05:

1. Re-run full Step 01 regex suite on cleaned output — hard block if any fires
2. Token integrity — every token must match `r'\[[A-Z_]+(_\d+)?\]'`
3. Minimum content — if `>60%` of words redacted, tag `low_signal: True`

Return: `ProcessedMessage`

---

## Vercel configuration

### `vercel.json`
```json
{
  "functions": {
    "api/anonymise.py": {
      "runtime": "python3.11",
      "maxDuration": 30
    }
  },
  "routes": [
    {
      "src": "/api/anonymise",
      "dest": "/api/anonymise.py"
    }
  ]
}
```

### `requirements.txt`
```
fastapi==0.109.0
uvicorn==0.27.0
spacy==3.7.2
presidio-analyzer==2.2.354
google-libphonenumber==8.13.27
pyahocorasick==2.0.0
pydantic==2.5.0
mangum==0.17.0
```

Note: spaCy models (`en_core_web_lg`, `de_core_news_lg`) must be listed as direct wheel URLs in `requirements.txt` for Vercel to bundle them:

```
https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.7.1/en_core_web_lg-3.7.1-py3-none-any.whl
https://github.com/explosion/spacy-models/releases/download/de_core_news_lg-3.7.0/de_core_news_lg-3.7.0-py3-none-any.whl
```

### `api/anonymise.py` entry point
```python
from fastapi import FastAPI, HTTPException
from mangum import Mangum
from lib.types import PipelineInput, AnonymiseResponse
from lib.pipeline.index import run_pipeline

app = FastAPI()

@app.post("/api/anonymise", response_model=AnonymiseResponse)
async def anonymise(body: PipelineInput):
    if len(body.rawText) > 500:
        raise HTTPException(status_code=400, detail="rawText exceeds 500 character limit")
    result = run_pipeline(body)
    return AnonymiseResponse(result=result)

# Vercel ASGI handler
handler = Mangum(app)
```

---

## Test suite — `/tests/test_cases.py`

Define all 20 test cases as structured data. Each test case specifies the input and the minimum expected redactions — not the exact output, since token numbering may vary.

```python
TEST_CASES = [
    {
        "id": "TC01",
        "group": "structural_pii",
        "description": "Clean WhatsApp format — email and name",
        "input": {
            "rawText": "[26/02/2026, 09:14] Sarah Müller: Hi everyone! Can someone help me understand the onboarding flow? My email is sarah.mueller@gmail.com and I've been stuck for 2 days.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["EMAIL", "PERSON", "SENDER"],
        "must_not_redact": ["onboarding", "2 days"]
    },
    {
        "id": "TC02",
        "group": "structural_pii",
        "description": "Phone number and social handle",
        "input": {
            "rawText": "[26/02/2026, 11:32] James O'Brien: Just joined the group! My number is +44 7911 123456 if anyone wants to chat directly. Also follow me @jamesobrien_dev on Instagram.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["PHONE", "HANDLE", "PERSON", "SENDER"],
        "must_not_redact": ["Instagram", "group"]
    },
    {
        "id": "TC03",
        "group": "structural_pii",
        "description": "IBAN detection",
        "input": {
            "rawText": "[26/02/2026, 14:05] Priya Sharma: Quick question — does the app support IBAN payments? Mine is DE89 3704 0044 0532 0130 00 and I want to test the checkout flow.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["IBAN", "PERSON", "SENDER"],
        "must_not_redact": ["checkout", "payments"]
    },
    {
        "id": "TC04",
        "group": "age_dob",
        "description": "Multiple ages in one message",
        "input": {
            "rawText": "[26/02/2026, 10:22] Anna Klein: I'm 34 and honestly the app UX is confusing for someone my age. My mum who is 67 years old also tried it and gave up immediately.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["AGE", "PERSON", "SENDER"],
        "must_not_redact": ["UX", "app"]
    },
    {
        "id": "TC05",
        "group": "age_dob",
        "description": "Birth year in text",
        "input": {
            "rawText": "[26/02/2026, 08:45] Tom Fischer: Born in 1989 so I've seen a lot of apps come and go. This one has potential but the progress tracking feature is broken.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["DOB", "PERSON", "SENDER"],
        "must_not_redact": ["progress tracking", "broken"]
    },
    {
        "id": "TC06",
        "group": "age_dob",
        "description": "Full date of birth",
        "input": {
            "rawText": "[26/02/2026, 16:18] Lena Bauer: I signed up on my birthday — 14.03.1991 — and the welcome email never arrived. Can someone check?",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["DOB", "PERSON", "SENDER"],
        "must_not_redact": ["welcome email", "birthday"]
    },
    {
        "id": "TC07",
        "group": "ner_edge_cases",
        "description": "Short nickname — blocklist required",
        "input": {
            "rawText": "[26/02/2026, 13:01] Susi: Hey! Is the community feature live yet? My colleague Mo asked me the same thing yesterday and I didn't know what to tell him.",
            "blocklist": "Susi, Mo",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["BLOCKLIST", "SENDER"],
        "must_not_redact": ["community feature", "yesterday"]
    },
    {
        "id": "TC08",
        "group": "ner_edge_cases",
        "description": "Ambiguous name — same name as sender and in body",
        "input": {
            "rawText": "[26/02/2026, 09:55] Ali: The push notifications stopped working for me after the last update. Ali from the Berlin team had the same issue btw.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["PERSON", "SENDER"],
        "must_not_redact": ["push notifications", "update"]
    },
    {
        "id": "TC09",
        "group": "ner_edge_cases",
        "description": "Third-party name reference",
        "input": {
            "rawText": "[26/02/2026, 17:44] User: Can you tag Mei on this? She was the one who reported the bug last week and I think she has the screenshot.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["PERSON"],
        "must_not_redact": ["bug", "screenshot"]
    },
    {
        "id": "TC10",
        "group": "quasi_identifier",
        "description": "Role + location + age combination — should flag",
        "input": {
            "rawText": "[26/02/2026, 11:10] Maria Gonzalez: As a senior product manager based in Munich, aged 41, I find the dashboard completely unintuitive. This would never pass a basic usability test.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["PERSON", "LOCATION", "AGE", "SENDER"],
        "must_not_redact": ["dashboard", "usability"],
        "expected_flags": ["quasi_identifier_risk"]
    },
    {
        "id": "TC11",
        "group": "quasi_identifier",
        "description": "Role + location combination",
        "input": {
            "rawText": "[26/02/2026, 15:33] David: I'm a freelance developer in Frankfurt, been coding for 15 years. The API docs are outdated — the endpoint at /api/v1/users returns a 404.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["PERSON", "LOCATION", "SENDER"],
        "must_not_redact": ["/api/v1/users", "404", "API docs"]
    },
    {
        "id": "TC12",
        "group": "obfuscated_pii",
        "description": "Obfuscated email",
        "input": {
            "rawText": "[26/02/2026, 12:44] Jonas Weber: Reach me at jonas dot weber at protonmail dot com — I don't post my email publicly anymore after the last spam wave.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["EMAIL", "PERSON", "SENDER"],
        "must_not_redact": ["spam wave", "publicly"]
    },
    {
        "id": "TC13",
        "group": "obfuscated_pii",
        "description": "Non-standard German phone format",
        "input": {
            "rawText": "[26/02/2026, 10:08] Claire: My number is 0049 (0) 160 9876 5432 — old German format, not sure if your system recognises it. Happy to jump on a call.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["PHONE", "PERSON", "SENDER"],
        "must_not_redact": ["German format", "call"]
    },
    {
        "id": "TC14",
        "group": "obfuscated_pii",
        "description": "LinkedIn URL containing full name",
        "input": {
            "rawText": "[26/02/2026, 14:52] Fatima Al-Hassan: You can find me at linkedin.com/in/fatima-al-hassan-pm or just search my name — I'm the only one with that exact name on there.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["URL", "PERSON", "SENDER"],
        "must_not_redact": ["search", "name"]
    },
    {
        "id": "TC15",
        "group": "multilingual",
        "description": "German-English code-switched message",
        "input": {
            "rawText": "[26/02/2026, 09:30] Björn Eriksson: Das Feature funktioniert nicht auf meinem iPhone. Björn here btw, Maide hat mir die Gruppe empfohlen. Danke schon mal!",
            "blocklist": "Maide",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["PERSON", "BLOCKLIST", "SENDER"],
        "must_not_redact": ["iPhone", "Feature", "Danke"]
    },
    {
        "id": "TC16",
        "group": "multilingual",
        "description": "Japanese-English mixed — likely review queue",
        "input": {
            "rawText": "[26/02/2026, 16:05] Yuki Tanaka: すみません、I'm having trouble with the login page. Yuki from the Tokyo cohort — can someone from support help?",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["PERSON", "SENDER"],
        "must_not_redact": ["login page", "support"]
    },
    {
        "id": "TC17",
        "group": "sensitive_topic",
        "description": "Health disclosure",
        "input": {
            "rawText": "[26/02/2026, 13:28] User: I need to be honest — I've been dealing with some health issues lately and the app's reminder feature has actually been really helpful for keeping me on track with medication.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": [],
        "must_not_redact": ["reminder feature", "app"],
        "expected_flags": ["sensitive_topic"]
    },
    {
        "id": "TC18",
        "group": "sensitive_topic",
        "description": "Legal/personal disclosure with contact request",
        "input": {
            "rawText": "[26/02/2026, 11:55] Rebecca Hofer: Not sure if this is the right place but I'm going through a divorce and the shared account feature is causing me real problems. Can someone from the team contact me directly?",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["PERSON", "SENDER"],
        "must_not_redact": ["shared account feature"],
        "expected_flags": ["sensitive_topic"]
    },
    {
        "id": "TC19",
        "group": "clean_no_pii",
        "description": "Pure product feedback — no PII, must not over-redact",
        "input": {
            "rawText": "[26/02/2026, 10:00] User: The dark mode on Android is broken. When I switch from light to dark the nav bar stays white. Happens every time on version 2.4.1.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": [],
        "must_not_redact": ["Android", "dark mode", "nav bar", "version 2.4.1"]
    },
    {
        "id": "TC20",
        "group": "clean_no_pii",
        "description": "Feature suggestion — no PII, must not over-redact",
        "input": {
            "rawText": "[26/02/2026, 15:15] User: Love the new onboarding flow update! The three-step wizard is much clearer than before. One suggestion — add a progress bar so users know how far along they are.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": [],
        "must_not_redact": ["onboarding flow", "three-step wizard", "progress bar"]
    }
]
```

---

## Benchmark runner — `/tests/run_benchmark.py`

This script calls both implementations with all 20 test cases and produces a comparison report.

```python
"""
Usage:
  python tests/run_benchmark.py \
    --python-url http://localhost:8000 \
    --ts-url http://localhost:3000

Outputs: benchmark_results.json
"""
import argparse
import json
import requests
from test_cases import TEST_CASES

def run_case(url: str, case: dict) -> dict:
    try:
        response = requests.post(
            f"{url}/api/anonymise",
            json=case["input"],
            timeout=10
        )
        return {"status": response.status_code, "body": response.json()}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def evaluate(result: dict, case: dict) -> dict:
    if result["status"] != 200:
        return {"pass": False, "reason": f"HTTP {result['status']}"}

    body = result["body"]["result"]
    token_types = [t["type"] for t in body.get("tokens", [])]
    cleaned = body.get("cleanedText", "")

    failures = []

    for expected_type in case.get("must_redact", []):
        if expected_type not in token_types:
            failures.append(f"MISSED: expected {expected_type} to be redacted")

    for term in case.get("must_not_redact", []):
        if term.lower() in cleaned.lower():
            pass  # term preserved correctly
        else:
            failures.append(f"OVER-REDACTED: '{term}' was removed but should not have been")

    return {
        "pass": len(failures) == 0,
        "failures": failures,
        "confidence": body.get("confidence", {}).get("overall"),
        "routing": body.get("confidence", {}).get("routingDecision"),
        "tokenCount": len(token_types),
        "cleanedText": cleaned
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-url", required=True)
    parser.add_argument("--ts-url", required=True)
    args = parser.parse_args()

    results = []

    for case in TEST_CASES:
        py_result = run_case(args.python_url, case)
        ts_result = run_case(args.ts_url, case)

        py_eval = evaluate(py_result, case)
        ts_eval = evaluate(ts_result, case)

        results.append({
            "id": case["id"],
            "group": case["group"],
            "description": case["description"],
            "python": py_eval,
            "typescript": ts_eval,
            "agreement": py_eval.get("routing") == ts_eval.get("routing")
        })

        print(f"{case['id']} | PY: {'✓' if py_eval['pass'] else '✗'} | TS: {'✓' if ts_eval['pass'] else '✗'} | Agreement: {'✓' if results[-1]['agreement'] else '✗'}")

    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)

    passed_py = sum(1 for r in results if r["python"]["pass"])
    passed_ts = sum(1 for r in results if r["typescript"]["pass"])
    agreed = sum(1 for r in results if r["agreement"])

    print(f"\n{'─'*50}")
    print(f"Python:     {passed_py}/20 passed")
    print(f"TypeScript: {passed_ts}/20 passed")
    print(f"Agreement:  {agreed}/20 routing decisions matched")
    print(f"Results saved to benchmark_results.json")

if __name__ == "__main__":
    main()
```

---

## What done looks like

- `vercel deploy` runs without errors for the Python project
- `POST /api/anonymise` responds in under 5 seconds (spaCy models add cold start overhead vs TypeScript)
- Running `run_benchmark.py` against both live URLs produces a `benchmark_results.json` with results for all 20 test cases
- TC19 and TC20 (clean messages) return zero tokens — pipeline does not over-redact
- TC07 ("Susi", "Mo") returns `BLOCKLIST` tokens only when blocklist is provided — NER alone does not catch these short names
- TC10 and TC11 return `quasi_identifier_risk` in their confidence breakdown
- Python implementation passes at least 17/20 test cases (expected higher accuracy than TypeScript on NER due to spaCy + Presidio vs wink-nlp)
# Private Chat Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /api/chat`: anonymize the user's prompt with the existing pipeline, send only the anonymized text to an OpenAI-compatible LLM (LM Studio locally), then restore the original values into the LLM's answer before returning it.

**Architecture:** A new `lib/workflow/` package holds three focused units: `vault.py` (placeholder → original mapping and re-enrichment), `llm_client.py` (OpenAI-compatible HTTP client), and `private_chat.py` (orchestrates anonymize → LLM → re-enrich). The vault lives only in memory for the duration of one request. `api/anonymise.py` exposes the orchestrator as a FastAPI endpoint. A pre-existing pipeline bug that orphans placeholders is fixed first, because re-enrichment is impossible without a complete mapping.

**Tech Stack:** Python 3.9 (the project venv), FastAPI 0.115, Pydantic 2.10, httpx 0.27 (already installed), pytest (new dev dependency), LM Studio at `http://localhost:1234/v1`.

## Global Constraints

- Runtime is **Python 3.9** (`./venv/bin/python`). Do not use `X | Y` union syntax, `match`, or other 3.10+ features. Use `Optional[...]`, `List[...]`, `Dict[...]` from `typing`.
- The placeholder → original mapping ("vault") must **never** be returned in an API response, logged, printed, or persisted. It exists only in local variables of one request.
- Only the anonymized prompt may be sent to the LLM. The original prompt must never reach `llm_client`.
- No new runtime dependencies. Use `httpx` (already in `requirements.txt`). The only new dependency is `pytest==8.3.4` for tests.
- `POST /api/anonymise` keeps its existing 500-character limit and behavior. The new workflow limit is **8000 characters**.
- LLM configuration comes from env vars: `LLM_BASE_URL` (default `http://localhost:1234/v1`), `LLM_API_KEY` (default `lm-studio`), `LLM_MODEL` (default empty = auto-pick first non-embedding model), `LLM_TIMEOUT_SECONDS` (default `120`).
- Work on the existing branch `feature/private-chat-workflow`. Commit after each task with the message given. Never commit `.env` or `venv/` (both are git-ignored).
- Run all commands from the repo root: `/Users/prafulsrivastava/Documents/GitHub/reachy/AnonymizeItPython`.
- A dev server may already be running on port 8000 with `--reload`; it will pick up changes automatically. Do not start a second one on the same port.

## File Structure

| File | Responsibility |
|------|----------------|
| `lib/pipeline/blocklist.py` (modify) | Fix: blocklist override must not rename placeholders already embedded in the text |
| `lib/types.py` (modify) | Raise `PipelineInput.rawText` limit to 8000; add `ChatRequest` / `ChatResponse` |
| `lib/workflow/__init__.py` (create) | Package marker |
| `lib/workflow/vault.py` (create) | `build_vault`, `reenrich`, `PLACEHOLDER_RE`, `VaultIntegrityError` |
| `lib/workflow/llm_client.py` (create) | `OpenAICompatibleClient`, `LLMReply`, `LLMError` |
| `lib/workflow/private_chat.py` (create) | `run_private_chat`, `PrivateChatResult`, `PrivacyRoutingError`, `SYSTEM_PROMPT` |
| `api/anonymise.py` (modify) | `get_llm_client` dependency + `POST /api/chat` |
| `tests/conftest.py` (create) | Puts repo root on `sys.path` |
| `tests/test_placeholder_integrity.py` (create) | Every placeholder in `cleanedText` has exactly one original |
| `tests/test_vault.py` (create) | Vault + re-enrichment unit tests |
| `tests/test_input_limits.py` (create) | 8000-char workflow limit, 500-char `/api/anonymise` limit |
| `tests/test_llm_client.py` (create) | LLM client against `httpx.MockTransport` |
| `tests/test_private_chat.py` (create) | Orchestrator with a fake LLM |
| `tests/test_chat_endpoint.py` (create) | `/api/chat` via FastAPI `TestClient` |
| `requirements.txt`, `.env.example`, `README.md` (modify) | pytest, LLM env vars, docs |

---

### Task 1: Fix orphaned placeholders in the pipeline

**Background (verified bug):** For the input below with blocklist `Marcus Weber,Marcus`, `cleanedText` contains `[PERSON_02]` but no token has `value == "[PERSON_02]"`. Cause: `BlocklistMatcher.override_with_blocklist` in `lib/pipeline/blocklist.py` (around lines 200–222) renames `token.value` from `[PERSON_02]` to `[BLOCKLIST_02]` after the NER stage has already written `[PERSON_02]` into the text, so the text and token list diverge.

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_placeholder_integrity.py`
- Modify: `lib/pipeline/blocklist.py` (`override_with_blocklist`)
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `lib.pipeline.index.run_pipeline(PipelineInput) -> ProcessedMessage` (existing). `RedactionToken.original` is populated in memory and only hidden at serialization.
- Produces: guarantee that every placeholder in `ProcessedMessage.cleanedText` has a token with that exact `value` and a non-empty `original`, and all such tokens share one `original`.

- [ ] **Step 1: Add pytest and install it**

Append to `requirements.txt` under `# Testing`:

```
pytest==8.3.4
```

Run: `./venv/bin/pip install pytest==8.3.4`
Expected: `Successfully installed ... pytest-8.3.4`

- [ ] **Step 2: Create `tests/conftest.py`**

```python
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
```

- [ ] **Step 3: Write the failing integrity test** — `tests/test_placeholder_integrity.py`

```python
import re
from typing import Dict, Set

import pytest

from lib.types import PipelineInput
from lib.pipeline.index import run_pipeline

PLACEHOLDER_RE = re.compile(
    r"\[SENDER\]|\[(?:PHONE|EMAIL|URL|HANDLE|AGE|DOB|PERSON|ORG|LOCATION|IBAN|BLOCKLIST)_[0-9A-Za-z]+\]"
)

CASES = [
    (
        "[07/11/2026, 14:22] Marcus Weber: Hi team — I am Marcus Weber, product manager in Berlin. "
        "Reach me at marcus.weber@acmecorp.com or +49 170 555 0198. My DOB is 12/03/1987. "
        "Bank: DE89 3704 0044 0532 0130 00. @marcusw https://linkedin.com/in/marcus-weber-dev",
        "Marcus Weber,Marcus",
    ),
    (
        "[26/02/2026, 13:01] Susi: Hey! Is the community feature live yet? "
        "My colleague Mo asked me the same thing yesterday.",
        "Susi,Mo",
    ),
    (
        "[24.01.26, 16:40:31] Jonas Weber: Ich bin 34 Jahre alt und arbeite als Manager in Berlin",
        "",
    ),
    (
        "Please email anna.schmidt@example.org and call +44 7911 123456 about John Smith's contract.",
        "John Smith",
    ),
]


@pytest.mark.parametrize("raw_text,blocklist", CASES)
def test_every_placeholder_in_text_maps_to_one_original(raw_text, blocklist):
    result = run_pipeline(PipelineInput(rawText=raw_text, blocklist=blocklist, sessionId="integrity"))

    originals: Dict[str, Set[str]] = {}
    for token in result.tokens:
        if token.original:
            originals.setdefault(token.value, set()).add(token.original)

    in_text = set(PLACEHOLDER_RE.findall(result.cleanedText))
    missing = sorted(p for p in in_text if p not in originals)
    conflicting = sorted(p for p in in_text if len(originals.get(p, ())) > 1)

    assert not missing, f"Placeholders with no original: {missing}\nText: {result.cleanedText}"
    assert not conflicting, f"Placeholders with several originals: {conflicting}"
```

- [ ] **Step 4: Run it to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_placeholder_integrity.py -v`
Expected: the first case FAILS with `Placeholders with no original: ['[PERSON_02]']`.

- [ ] **Step 5: Fix `override_with_blocklist`**

In `lib/pipeline/blocklist.py`, replace the body of the `if token.original and token.original.lower() in blocklist_lower:` block (the type change plus the whole value-renaming `if/else`) with:

```python
            if token.original and token.original.lower() in blocklist_lower:
                # Only the type changes: token.value is already embedded in the
                # cleaned text, so renaming it would orphan that placeholder.
                token.type = "BLOCKLIST"
```

- [ ] **Step 6: Run the integrity test and the existing suite**

Run: `./venv/bin/python -m pytest tests/test_placeholder_integrity.py tests/test_sample_cases.py -v`
Expected: all integrity cases PASS. `test_sample_cases.py` must have no *new* failures compared to running it on the previous commit (`git stash` is not needed: run `git stash -- lib/pipeline/blocklist.py && ./venv/bin/python -m pytest tests/test_sample_cases.py -q; git stash pop` to get the baseline if anything fails).

If an integrity case still fails, do not weaken the test. Use superpowers:systematic-debugging: print `result.cleanedText` and every `(token.type, token.value, token.original)` and find which stage writes a placeholder into the text without a matching token (also check `lib/pipeline/validator.py`), then fix that stage.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt tests/conftest.py tests/test_placeholder_integrity.py lib/pipeline/blocklist.py
git commit -m "fix: keep blocklist-overridden placeholders consistent with cleaned text"
```

---

### Task 2: Vault and re-enrichment

**Files:**
- Create: `lib/workflow/__init__.py` (empty)
- Create: `lib/workflow/vault.py`
- Test: `tests/test_vault.py`

**Interfaces:**
- Consumes: `lib.types.ProcessedMessage`, `RedactionToken` (existing).
- Produces:
  - `PLACEHOLDER_RE: re.Pattern` (case-insensitive)
  - `class VaultIntegrityError(Exception)`
  - `build_vault(result: ProcessedMessage) -> Dict[str, str]` — keys are placeholders exactly as they appear in `cleanedText`, in first-appearance order
  - `@dataclass ReenrichResult: text: str, restored: List[str], unknown_placeholders: List[str]`
  - `reenrich(text: str, vault: Dict[str, str]) -> ReenrichResult`

- [ ] **Step 1: Write the failing tests** — `tests/test_vault.py`

```python
from typing import List

import pytest

from lib.types import ConfidenceScore, ConfidenceSignals, ProcessedMessage, RedactionToken
from lib.workflow.vault import VaultIntegrityError, build_vault, reenrich


def _token(type_: str, value: str, original: str) -> RedactionToken:
    return RedactionToken(type=type_, value=value, original=original, startIndex=0, endIndex=1)


def _message(cleaned: str, tokens: List[RedactionToken]) -> ProcessedMessage:
    return ProcessedMessage(
        messageId="m",
        cleanedText=cleaned,
        tokens=tokens,
        confidence=ConfidenceScore(
            overall=1.0,
            routing="pass",
            signals=ConfidenceSignals(
                regexCoverage=1.0, nerConfidence=1.0, quasiIdentifierCount=0, residualTokenDensity=1.0
            ),
        ),
    )


def test_build_vault_maps_placeholders_present_in_text():
    msg = _message(
        "Hi [PERSON_01], mail [EMAIL_01]",
        [
            _token("PERSON", "[PERSON_01]", "Anna"),
            _token("EMAIL", "[EMAIL_01]", "anna@x.org"),
            _token("PERSON", "[PERSON_02]", "Unused"),
        ],
    )
    assert build_vault(msg) == {"[PERSON_01]": "Anna", "[EMAIL_01]": "anna@x.org"}


def test_build_vault_ignores_brackets_that_are_not_token_types():
    msg = _message("[TODO] ask [PERSON_01]", [_token("PERSON", "[PERSON_01]", "Anna")])
    assert build_vault(msg) == {"[PERSON_01]": "Anna"}


def test_build_vault_raises_when_placeholder_has_no_original():
    msg = _message("Hi [PERSON_02]", [_token("PERSON", "[PERSON_01]", "Anna")])
    with pytest.raises(VaultIntegrityError):
        build_vault(msg)


def test_build_vault_raises_on_conflicting_originals():
    msg = _message(
        "Hi [PERSON_01]",
        [_token("PERSON", "[PERSON_01]", "Anna"), _token("BLOCKLIST", "[PERSON_01]", "Bob")],
    )
    with pytest.raises(VaultIntegrityError):
        build_vault(msg)


def test_reenrich_restores_every_occurrence():
    vault = {"[PERSON_01]": "Anna", "[EMAIL_01]": "anna@x.org"}
    result = reenrich("Dear [PERSON_01], we wrote to [EMAIL_01]. Thanks [PERSON_01]!", vault)
    assert result.text == "Dear Anna, we wrote to anna@x.org. Thanks Anna!"
    assert result.restored == ["[PERSON_01]", "[EMAIL_01]"]
    assert result.unknown_placeholders == []


def test_reenrich_is_case_insensitive():
    result = reenrich("Dear [person_01]", {"[PERSON_01]": "Anna"})
    assert result.text == "Dear Anna"


def test_reenrich_handles_age_bucket_placeholders():
    result = reenrich("You are [AGE_30s]", {"[AGE_30s]": "34"})
    assert result.text == "You are 34"


def test_reenrich_reports_unknown_placeholders_and_leaves_them():
    result = reenrich("Ask [PERSON_09] and [PERSON_01]", {"[PERSON_01]": "Anna"})
    assert result.text == "Ask [PERSON_09] and Anna"
    assert result.unknown_placeholders == ["[PERSON_09]"]


def test_reenrich_does_not_reprocess_restored_values():
    vault = {"[PERSON_01]": "literal [EMAIL_01]", "[EMAIL_01]": "anna@x.org"}
    result = reenrich("[PERSON_01]", vault)
    assert result.text == "literal [EMAIL_01]"
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_vault.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.workflow'`.

- [ ] **Step 3: Implement** — create empty `lib/workflow/__init__.py`, then `lib/workflow/vault.py`:

```python
"""
Placeholder vault: maps anonymization placeholders back to their original values
and restores them in text returned by an LLM. Never serialize, log, or persist a vault.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

from lib.types import ProcessedMessage

PLACEHOLDER_RE = re.compile(
    r"\[SENDER\]|\[(?:PHONE|EMAIL|URL|HANDLE|AGE|DOB|PERSON|ORG|LOCATION|IBAN|BLOCKLIST)_[0-9A-Za-z]+\]",
    re.IGNORECASE,
)


class VaultIntegrityError(Exception):
    """A placeholder in the anonymized text cannot be mapped to exactly one original."""


@dataclass
class ReenrichResult:
    text: str
    restored: List[str] = field(default_factory=list)
    unknown_placeholders: List[str] = field(default_factory=list)


def build_vault(result: ProcessedMessage) -> Dict[str, str]:
    originals: Dict[str, Set[str]] = {}
    for token in result.tokens:
        if token.original:
            originals.setdefault(token.value, set()).add(token.original)

    vault: Dict[str, str] = {}
    for match in PLACEHOLDER_RE.finditer(result.cleanedText):
        placeholder = match.group(0)
        if placeholder in vault:
            continue
        candidates = originals.get(placeholder)
        if not candidates:
            raise VaultIntegrityError(f"No original recorded for {placeholder}")
        if len(candidates) > 1:
            raise VaultIntegrityError(f"Several originals recorded for {placeholder}")
        vault[placeholder] = next(iter(candidates))
    return vault


def reenrich(text: str, vault: Dict[str, str]) -> ReenrichResult:
    lookup = {placeholder.upper(): original for placeholder, original in vault.items()}
    canonical = {placeholder.upper(): placeholder for placeholder in vault}
    restored: Dict[str, None] = {}
    unknown: Dict[str, None] = {}

    def _swap(match: "re.Match[str]") -> str:
        key = match.group(0).upper()
        if key in lookup:
            restored[canonical[key]] = None
            return lookup[key]
        unknown[match.group(0)] = None
        return match.group(0)

    # A single substitution pass, so restored values are never scanned again.
    new_text = PLACEHOLDER_RE.sub(_swap, text)
    return ReenrichResult(text=new_text, restored=list(restored), unknown_placeholders=list(unknown))
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/python -m pytest tests/test_vault.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add lib/workflow/__init__.py lib/workflow/vault.py tests/test_vault.py
git commit -m "feat: add placeholder vault and re-enrichment"
```

---

### Task 3: Raise the pipeline input limit for the workflow

**Files:**
- Modify: `lib/types.py` (`PipelineInput.rawText`)
- Test: `tests/test_input_limits.py`

**Interfaces:**
- Produces: `lib.types.MAX_WORKFLOW_CHARS = 8000`. `PipelineInput.rawText` accepts up to 8000 chars. `/api/anonymise` still returns HTTP 400 above 500 chars (its explicit check in `api/anonymise.py` is unchanged).

- [ ] **Step 1: Write the failing tests** — `tests/test_input_limits.py`

```python
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import api.anonymise as api_module
from lib.auth.middleware import optional_user
from lib.types import MAX_WORKFLOW_CHARS, PipelineInput


def test_pipeline_input_accepts_workflow_limit():
    PipelineInput(rawText="a" * MAX_WORKFLOW_CHARS, sessionId="s")


def test_pipeline_input_rejects_above_workflow_limit():
    with pytest.raises(ValidationError):
        PipelineInput(rawText="a" * (MAX_WORKFLOW_CHARS + 1), sessionId="s")


def test_anonymise_endpoint_keeps_500_char_limit(monkeypatch):
    monkeypatch.setattr(api_module, "check_anonymous_usage", lambda: True)
    api_module.app.dependency_overrides[optional_user] = lambda: None
    try:
        client = TestClient(api_module.app)
        response = client.post(
            "/api/anonymise", json={"rawText": "a" * 501, "blocklist": "", "sessionId": "s"}
        )
    finally:
        api_module.app.dependency_overrides.clear()
    assert response.status_code == 400
    assert "500" in response.json()["detail"]
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_input_limits.py -v`
Expected: FAIL with `ImportError: cannot import name 'MAX_WORKFLOW_CHARS'`.

- [ ] **Step 3: Implement** — in `lib/types.py`, add after the `RoutingDecision` definition:

```python
MAX_WORKFLOW_CHARS = 8000
```

and change the `rawText` field of `PipelineInput` to:

```python
    rawText: str = Field(..., max_length=MAX_WORKFLOW_CHARS, description="Raw text to anonymize")
```

- [ ] **Step 4: Run to verify pass, plus a timing sanity check**

Run: `./venv/bin/python -m pytest tests/test_input_limits.py tests/test_placeholder_integrity.py -v`
Expected: all pass.

Run:
```bash
./venv/bin/python -c "
import time
from lib.types import PipelineInput
from lib.pipeline.index import run_pipeline
text = ('Anna Schmidt from Berlin emailed anna@example.org about the invoice. ' * 110)[:8000]
t = time.time(); run_pipeline(PipelineInput(rawText=text, sessionId='t')); print(round(time.time() - t, 1), 's')
"
```
Expected: prints a duration under 30 s. If slower, report it in the task summary; do not optimize in this plan.

- [ ] **Step 5: Commit**

```bash
git add lib/types.py tests/test_input_limits.py
git commit -m "feat: allow 8000-char inputs for the private chat workflow"
```

---

### Task 4: OpenAI-compatible LLM client

**Files:**
- Create: `lib/workflow/llm_client.py`
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Produces:
  - `class LLMError(Exception)`
  - `@dataclass LLMReply: content: str, model: str`
  - `class OpenAICompatibleClient(base_url: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None, timeout: Optional[float] = None, transport: Optional[httpx.BaseTransport] = None)` with `chat(messages: List[Dict[str, str]]) -> LLMReply`

- [ ] **Step 1: Write the failing tests** — `tests/test_llm_client.py`

```python
import json

import httpx
import pytest

from lib.workflow.llm_client import LLMError, OpenAICompatibleClient


def _client(handler, model=""):
    return OpenAICompatibleClient(
        base_url="http://llm.test/v1", api_key="k", model=model, timeout=5,
        transport=httpx.MockTransport(handler),
    )


def _completion(content, model="m1"):
    return httpx.Response(200, json={"model": model, "choices": [{"message": {"content": content}}]})


def test_chat_posts_messages_with_configured_model():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _completion("hello [PERSON_01]")

    reply = _client(handler, model="my-model").chat([{"role": "user", "content": "hi"}])

    assert reply.content == "hello [PERSON_01]"
    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "my-model"
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]


def test_chat_auto_picks_first_non_embedding_model():
    def handler(request):
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "text-embedding-bge"}, {"id": "qwen/qwen3-vl-8b"}]})
        assert json.loads(request.content)["model"] == "qwen/qwen3-vl-8b"
        return _completion("ok", model="qwen/qwen3-vl-8b")

    assert _client(handler).chat([{"role": "user", "content": "hi"}]).model == "qwen/qwen3-vl-8b"


def test_chat_strips_think_blocks():
    reply = _client(lambda r: _completion("<think>secret plan</think>\nFinal answer"), model="m").chat([])
    assert reply.content == "Final answer"


def test_http_error_becomes_llm_error():
    with pytest.raises(LLMError):
        _client(lambda r: httpx.Response(500, text="boom"), model="m").chat([])


def test_connection_error_becomes_llm_error():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMError):
        _client(handler, model="m").chat([])


def test_unexpected_shape_becomes_llm_error():
    with pytest.raises(LLMError):
        _client(lambda r: httpx.Response(200, json={"oops": True}), model="m").chat([])
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_llm_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.workflow.llm_client'`.

- [ ] **Step 3: Implement** — `lib/workflow/llm_client.py`

```python
"""
Minimal client for OpenAI-compatible chat completion servers (LM Studio, vLLM, OpenAI, ...).
"""

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(Exception):
    """The LLM server could not be reached or returned an unusable response."""


@dataclass
class LLMReply:
    content: str
    model: str


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "lm-studio")
        self.model = model if model is not None else os.getenv("LLM_MODEL", "")
        self.timeout = timeout or float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
        self._transport = transport

    def chat(self, messages: List[Dict[str, str]]) -> LLMReply:
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                model = self.model or self._first_chat_model(client)
                response = client.post(
                    "/chat/completions",
                    json={"model": model, "messages": messages, "temperature": 0.2},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM response had no choices[0].message.content") from exc

        return LLMReply(content=_THINK_RE.sub("", content).strip(), model=data.get("model") or model)

    def _first_chat_model(self, client: httpx.Client) -> str:
        response = client.get("/models")
        response.raise_for_status()
        for entry in response.json().get("data", []):
            model_id = entry.get("id", "")
            if model_id and "embed" not in model_id.lower():
                return model_id
        raise LLMError("LLM server lists no chat models; set LLM_MODEL")
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/python -m pytest tests/test_llm_client.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add lib/workflow/llm_client.py tests/test_llm_client.py
git commit -m "feat: add OpenAI-compatible LLM client"
```

---

### Task 5: Private chat orchestrator

**Files:**
- Create: `lib/workflow/private_chat.py`
- Test: `tests/test_private_chat.py`

**Interfaces:**
- Consumes: `run_pipeline` (existing), `build_vault`, `reenrich`, `VaultIntegrityError` (Task 2), `LLMReply`, `LLMError` (Task 4). The `llm` argument is any object with `chat(messages: List[Dict[str, str]]) -> LLMReply`.
- Produces:
  - `SYSTEM_PROMPT: str`
  - `class PrivacyRoutingError(Exception)` with attribute `reasons: List[str]`
  - `@dataclass PrivateChatResult: answer: str, anonymized_prompt: str, anonymized_answer: str, placeholders_sent: List[str], placeholders_restored: List[str], unknown_placeholders: List[str], routing: str, flags: dict, model: str`
  - `run_private_chat(prompt: str, llm, blocklist: str = "", strict: bool = False) -> PrivateChatResult` — raises `PrivacyRoutingError` (strict and routing is `review`, LLM not called), `VaultIntegrityError` (LLM not called), or lets `LLMError` propagate.

- [ ] **Step 1: Write the failing tests** — `tests/test_private_chat.py`

```python
from typing import Dict, List

import pytest

import lib.workflow.private_chat as private_chat
from lib.types import ConfidenceScore, ConfidenceSignals, ProcessedMessage, RedactionToken
from lib.workflow.llm_client import LLMReply
from lib.workflow.private_chat import PrivacyRoutingError, run_private_chat
from lib.workflow.vault import PLACEHOLDER_RE

PROMPT = (
    "Write a short reply to Marcus Weber. His email is marcus.weber@acmecorp.com "
    "and his phone is +49 170 555 0198."
)
SECRETS = ["marcus.weber@acmecorp.com", "+49 170 555 0198", "Marcus"]


class FakeLLM:
    def __init__(self):
        self.calls: List[List[Dict[str, str]]] = []

    def chat(self, messages):
        self.calls.append(messages)
        placeholders = PLACEHOLDER_RE.findall(messages[-1]["content"])
        return LLMReply(content="Contacting " + " and ".join(placeholders), model="fake-model")


def test_llm_only_sees_anonymized_text_and_answer_is_restored():
    llm = FakeLLM()
    result = run_private_chat(PROMPT, llm)

    sent = "\n".join(m["content"] for m in llm.calls[0])
    for secret in SECRETS:
        assert secret not in sent
    assert "marcus.weber@acmecorp.com" in result.answer
    assert "+49 170 555 0198" in result.answer
    assert result.anonymized_prompt == llm.calls[0][-1]["content"]
    assert result.anonymized_answer.startswith("Contacting [")
    assert result.placeholders_sent
    assert set(result.placeholders_restored) == set(result.placeholders_sent)
    assert result.unknown_placeholders == []
    assert result.model == "fake-model"


def test_system_prompt_tells_model_to_keep_placeholders():
    llm = FakeLLM()
    run_private_chat(PROMPT, llm)
    assert llm.calls[0][0] == {"role": "system", "content": private_chat.SYSTEM_PROMPT}
    assert "placeholder" in private_chat.SYSTEM_PROMPT.lower()


def test_strict_mode_blocks_review_routing_without_calling_llm(monkeypatch):
    review = ProcessedMessage(
        messageId="m",
        cleanedText="[PERSON_01] is a manager in [LOCATION_01]",
        tokens=[
            RedactionToken(type="PERSON", value="[PERSON_01]", original="Anna", startIndex=0, endIndex=4),
            RedactionToken(type="LOCATION", value="[LOCATION_01]", original="Berlin", startIndex=5, endIndex=11),
        ],
        confidence=ConfidenceScore(
            overall=0.5,
            routing="review",
            signals=ConfidenceSignals(
                regexCoverage=0.5, nerConfidence=0.5, quasiIdentifierCount=2, residualTokenDensity=0.5
            ),
            failureReasons=["High quasi-identifier density detected"],
        ),
    )
    monkeypatch.setattr(private_chat, "run_pipeline", lambda _input: review)
    llm = FakeLLM()

    with pytest.raises(PrivacyRoutingError) as exc_info:
        run_private_chat("anything", llm, strict=True)

    assert exc_info.value.reasons == ["High quasi-identifier density detected"]
    assert llm.calls == []
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_private_chat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.workflow.private_chat'`.

- [ ] **Step 3: Implement** — `lib/workflow/private_chat.py`

```python
"""
Private chat workflow: anonymize a prompt, send only the anonymized text to an LLM,
then restore the original values in the LLM's answer.
"""

from dataclasses import dataclass, field
from typing import List

from lib.pipeline.index import run_pipeline
from lib.types import PipelineInput
from lib.workflow.vault import build_vault, reenrich

SYSTEM_PROMPT = (
    "Some details in the user's message were replaced with placeholders such as "
    "[PERSON_01], [EMAIL_01] or [LOCATION_01]. Treat each placeholder as the real value it "
    "stands for. Whenever you refer to one of these values, write the placeholder exactly as "
    "given, including the square brackets, capital letters and number. Never invent new "
    "placeholders and never guess what the hidden values are."
)


class PrivacyRoutingError(Exception):
    """Strict mode refused to send a prompt the anonymizer routed to review."""

    def __init__(self, reasons: List[str]):
        super().__init__("Anonymization confidence too low to send prompt")
        self.reasons = reasons


@dataclass
class PrivateChatResult:
    answer: str
    anonymized_prompt: str
    anonymized_answer: str
    placeholders_sent: List[str]
    placeholders_restored: List[str]
    unknown_placeholders: List[str]
    routing: str
    flags: dict = field(default_factory=dict)
    model: str = ""


def run_private_chat(prompt: str, llm, blocklist: str = "", strict: bool = False) -> PrivateChatResult:
    anonymized = run_pipeline(PipelineInput(rawText=prompt, blocklist=blocklist, sessionId="private_chat"))

    if strict and anonymized.confidence.routing == "review":
        raise PrivacyRoutingError(list(anonymized.confidence.failureReasons))

    vault = build_vault(anonymized)

    reply = llm.chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": anonymized.cleanedText},
    ])
    restored = reenrich(reply.content, vault)

    return PrivateChatResult(
        answer=restored.text,
        anonymized_prompt=anonymized.cleanedText,
        anonymized_answer=reply.content,
        placeholders_sent=list(vault),
        placeholders_restored=restored.restored,
        unknown_placeholders=restored.unknown_placeholders,
        routing=anonymized.confidence.routing,
        flags=dict(anonymized.flags),
        model=reply.model,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/python -m pytest tests/test_private_chat.py -v`
Expected: 3 passed. If `test_llm_only_sees_anonymized_text_and_answer_is_restored` fails because the pipeline leaves part of the name (e.g. `Marcus`) unredacted, that is a real privacy finding: report it in the task summary with the exact `anonymized_prompt`, and pass `blocklist="Marcus Weber,Marcus"` in that test call rather than loosening `SECRETS`.

- [ ] **Step 5: Commit**

```bash
git add lib/workflow/private_chat.py tests/test_private_chat.py
git commit -m "feat: add private chat orchestrator"
```

---

### Task 6: `POST /api/chat` endpoint

**Files:**
- Modify: `lib/types.py` (append `ChatRequest`, `ChatResponse`)
- Modify: `api/anonymise.py` (imports, `get_llm_client`, endpoint placed directly above the `# Vercel serverless handler` comment)
- Test: `tests/test_chat_endpoint.py`

**Interfaces:**
- Consumes: `run_private_chat`, `PrivacyRoutingError` (Task 5), `OpenAICompatibleClient`, `LLMError` (Task 4), `VaultIntegrityError` (Task 2), `MAX_WORKFLOW_CHARS` (Task 3), existing `optional_user`, `check_anonymous_usage`, `increment_anonymous_usage`, `check_user_usage`, `increment_user_usage` in `api/anonymise.py`.
- Produces: `api.anonymise.get_llm_client() -> OpenAICompatibleClient` (FastAPI dependency, overridable in tests). HTTP contract:
  - Request: `{"prompt": str (1..8000), "blocklist": str = "", "strict": bool = false}`
  - 200: `ChatResponse` JSON (fields below)
  - 401 / 403: same quota behavior as `/api/anonymise`
  - 422: validation error, or strict mode refused (`detail.message`, `detail.reasons`)
  - 500: vault integrity failure (prompt was not sent)
  - 502: LLM unreachable or bad response

- [ ] **Step 1: Write the failing tests** — `tests/test_chat_endpoint.py`

```python
import pytest
from fastapi.testclient import TestClient

import api.anonymise as api_module
from lib.auth.middleware import optional_user
from lib.workflow.llm_client import LLMError, LLMReply
from lib.workflow.private_chat import PrivacyRoutingError
from lib.workflow.vault import PLACEHOLDER_RE


class EchoLLM:
    def chat(self, messages):
        return LLMReply(content="Noted: " + " ".join(PLACEHOLDER_RE.findall(messages[-1]["content"])), model="echo")


class DownLLM:
    def chat(self, messages):
        raise LLMError("LLM request failed: connection refused")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api_module, "check_anonymous_usage", lambda: True)
    monkeypatch.setattr(api_module, "increment_anonymous_usage", lambda: None)
    api_module.app.dependency_overrides[optional_user] = lambda: None
    api_module.app.dependency_overrides[api_module.get_llm_client] = lambda: EchoLLM()
    yield TestClient(api_module.app)
    api_module.app.dependency_overrides.clear()


def test_chat_returns_reenriched_answer_without_vault(client):
    response = client.post("/api/chat", json={"prompt": "Email anna.schmidt@example.org today."})
    assert response.status_code == 200
    body = response.json()
    assert "anna.schmidt@example.org" in body["answer"]
    assert "anna.schmidt@example.org" not in body["anonymizedPrompt"]
    assert "anna.schmidt@example.org" not in body["anonymizedAnswer"]
    assert body["model"] == "echo"
    assert set(body) == {
        "answer", "anonymizedPrompt", "anonymizedAnswer", "placeholdersSent",
        "placeholdersRestored", "unknownPlaceholders", "routing", "flags", "model",
    }


def test_chat_rejects_prompt_over_workflow_limit(client):
    assert client.post("/api/chat", json={"prompt": "a" * 8001}).status_code == 422


def test_chat_maps_llm_failure_to_502(client):
    api_module.app.dependency_overrides[api_module.get_llm_client] = lambda: DownLLM()
    response = client.post("/api/chat", json={"prompt": "Email anna.schmidt@example.org today."})
    assert response.status_code == 502


def test_chat_strict_refusal_is_422(client, monkeypatch):
    def refuse(*args, **kwargs):
        raise PrivacyRoutingError(["High quasi-identifier density detected"])

    monkeypatch.setattr(api_module, "run_private_chat", refuse)
    response = client.post("/api/chat", json={"prompt": "x", "strict": True})
    assert response.status_code == 422
    assert response.json()["detail"]["reasons"] == ["High quasi-identifier density detected"]


def test_chat_respects_anonymous_quota(client, monkeypatch):
    monkeypatch.setattr(api_module, "check_anonymous_usage", lambda: False)
    assert client.post("/api/chat", json={"prompt": "hello"}).status_code == 401
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_chat_endpoint.py -v`
Expected: FAIL with `AttributeError: module 'api.anonymise' has no attribute 'get_llm_client'`.

- [ ] **Step 3: Add request/response models** — append to `lib/types.py`:

```python
class ChatRequest(BaseModel):
    """Request body for the private chat workflow."""
    prompt: str = Field(..., min_length=1, max_length=MAX_WORKFLOW_CHARS, description="Prompt that may contain PII")
    blocklist: str = Field(default="", description="Comma-separated list of extra terms to redact")
    strict: bool = Field(default=False, description="Refuse to call the LLM when routing is 'review'")


class ChatResponse(BaseModel):
    """Re-enriched LLM answer plus what was actually sent to the model."""
    answer: str = Field(..., description="LLM answer with original values restored")
    anonymizedPrompt: str = Field(..., description="Exact prompt text sent to the LLM")
    anonymizedAnswer: str = Field(..., description="LLM answer before re-enrichment")
    placeholdersSent: List[str] = Field(default_factory=list)
    placeholdersRestored: List[str] = Field(default_factory=list)
    unknownPlaceholders: List[str] = Field(default_factory=list, description="Placeholders the LLM emitted that were never sent")
    routing: RoutingDecision
    flags: dict = Field(default_factory=dict)
    model: str
```

- [ ] **Step 4: Add the endpoint** — in `api/anonymise.py`:

Change the existing types import line to:

```python
from lib.types import PipelineInput, AnonymiseResponse, ChatRequest, ChatResponse
```

Add after the `lib.usage.tracker` import block:

```python
from lib.workflow.llm_client import OpenAICompatibleClient, LLMError
from lib.workflow.private_chat import run_private_chat, PrivacyRoutingError
from lib.workflow.vault import VaultIntegrityError
```

Add directly above `# Vercel serverless handler (ASGI adapter)`:

```python
def get_llm_client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient()


@app.post("/api/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def private_chat(
    body: ChatRequest,
    user: Optional[User] = Depends(optional_user),
    llm: OpenAICompatibleClient = Depends(get_llm_client),
):
    """
    Anonymize the prompt, send only the anonymized text to the configured LLM,
    and return the answer with the original values restored.
    """
    if user:
        if not check_user_usage(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usage quota exceeded. Please upgrade your plan."
            )
    elif not check_anonymous_usage():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Free tier limit reached. Please login to continue."
        )

    try:
        result = run_private_chat(body.prompt, llm, blocklist=body.blocklist, strict=body.strict)
    except PrivacyRoutingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Prompt not sent: anonymization needs review", "reasons": exc.reasons}
        )
    except VaultIntegrityError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Anonymization produced a placeholder that cannot be restored; prompt was not sent"
        )
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    if user:
        increment_user_usage(user.id)
    else:
        increment_anonymous_usage()

    return ChatResponse(
        answer=result.answer,
        anonymizedPrompt=result.anonymized_prompt,
        anonymizedAnswer=result.anonymized_answer,
        placeholdersSent=result.placeholders_sent,
        placeholdersRestored=result.placeholders_restored,
        unknownPlaceholders=result.unknown_placeholders,
        routing=result.routing,
        flags=result.flags,
        model=result.model,
    )
```

Note: `VaultIntegrityError` must not include the placeholder's original in its message, and the handler above deliberately does not echo `str(exc)`.

- [ ] **Step 5: Run the new tests and the whole suite**

Run: `./venv/bin/python -m pytest tests/test_chat_endpoint.py -v`
Expected: 5 passed.

Run: `./venv/bin/python -m pytest tests/test_placeholder_integrity.py tests/test_vault.py tests/test_input_limits.py tests/test_llm_client.py tests/test_private_chat.py tests/test_chat_endpoint.py -q`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add lib/types.py api/anonymise.py tests/test_chat_endpoint.py
git commit -m "feat: add POST /api/chat private chat endpoint"
```

---

### Task 7: Configuration, docs, and live end-to-end check against LM Studio

**Files:**
- Modify: `.env.example`
- Modify: `README.md` (new section after `### Example Requests` examples, before `## Token Types`)
- Local only (git-ignored, do not commit): `.env`

**Interfaces:**
- Consumes: the running dev server on `http://localhost:8000` (uvicorn `--reload`) and LM Studio on `http://localhost:1234`.

- [ ] **Step 1: Append to `.env.example`**

```
# Private chat workflow (any OpenAI-compatible server; defaults target LM Studio)
LLM_BASE_URL=http://localhost:1234/v1
LLM_API_KEY=lm-studio
# Leave empty to auto-pick the first non-embedding model the server lists
LLM_MODEL=qwen/qwen3-vl-8b
LLM_TIMEOUT_SECONDS=120
```

- [ ] **Step 2: Configure local `.env`** — append the same five lines to `.env` (it already exists; keep its other values). Then restart the dev server so `load_dotenv()` picks them up: find the uvicorn process with `lsof -ti :8000`, kill it, and start `./venv/bin/uvicorn api.anonymise:app --reload --port 8000` in the background. Wait until `curl -s http://localhost:8000/ -o /dev/null -w '%{http_code}'` prints `200` (model loading takes ~20 s).

- [ ] **Step 3: Add README section**

```markdown
### Private Chat Workflow (anonymize → LLM → re-enrich)

**POST** `/api/chat` anonymizes the prompt, sends only the anonymized text to an
OpenAI-compatible LLM, and restores the original values in the answer. The
placeholder-to-original mapping exists only in memory for that one request.

Configure the LLM in `.env` (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`,
`LLM_TIMEOUT_SECONDS`). Defaults target LM Studio at `http://localhost:1234/v1`.

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Draft a two-sentence reply to Marcus Weber (marcus.weber@acmecorp.com) confirming our call on +49 170 555 0198.", "blocklist": "Marcus Weber,Marcus"}'
```

The response contains `answer` (re-enriched), `anonymizedPrompt` (exactly what the
LLM saw), `anonymizedAnswer`, the placeholders sent and restored, any
`unknownPlaceholders` the model invented, and the anonymizer's `routing`.
Prompts are limited to 8000 characters. Set `"strict": true` to refuse sending
prompts the anonymizer routes to `review` (HTTP 422).
```

- [ ] **Step 4: Live end-to-end run**

Run:
```bash
curl -s -m 300 -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Draft a two-sentence reply to Marcus Weber (marcus.weber@acmecorp.com) confirming our call on +49 170 555 0198.", "blocklist": "Marcus Weber,Marcus"}' \
  | ./venv/bin/python -m json.tool
```

Expected (first call may take a minute while LM Studio loads the model):
- HTTP 200 with a JSON body.
- `anonymizedPrompt` contains none of `Marcus`, `marcus.weber@acmecorp.com`, `+49 170 555 0198`.
- `answer` contains the restored email and/or phone/name wherever the model referenced them.
- `model` is `qwen/qwen3-vl-8b`.

If LM Studio returns an error because the model is not loaded and JIT loading is disabled, run `lms load qwen/qwen3-vl-8b` (if the `lms` CLI exists) and retry once; otherwise report the 502 body and stop. Do not change the code to work around LM Studio configuration.

Record the full JSON response in your final report.

- [ ] **Step 5: Commit**

```bash
git add .env.example README.md
git commit -m "docs: document private chat workflow and LLM configuration"
```

---

## Final report (required from the implementer)

1. Commits created (`git log --oneline master..HEAD`).
2. Output of the full new test run (Task 6 Step 5 command).
3. Whether `tests/test_sample_cases.py` gained any new failures versus baseline.
4. The live end-to-end JSON from Task 7 Step 4.
5. Any deviations from this plan and why, and any privacy findings (PII that reached `anonymizedPrompt`).

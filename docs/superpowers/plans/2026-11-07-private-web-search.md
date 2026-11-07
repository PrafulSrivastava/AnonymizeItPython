# Private Web Search (Exa) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the private chat an opt-in `web_search` tool backed by Exa. A guard keeps personal details and placeholders out of every query sent to Exa.

**Architecture:** The existing anonymize → vault → LLM → re-enrich flow is unchanged. When web search is on, the LLM step becomes an OpenAI-style tool-calling loop (at most 3 searches and 5 model calls). Each model-written query passes `check_query` before it reaches Exa `/search`. The endpoint returns the queries and the source links; the UI shows them.

**Tech Stack:** Python 3.9, FastAPI, Pydantic 2.10, httpx 0.27 (`httpx.MockTransport` in tests), pytest 8.3.4, vanilla JS in `public/chat.html`.

**Spec:** `docs/superpowers/specs/2026-11-07-private-web-search-design.md`

## Global Constraints

- Python 3.9 syntax only: use `Optional[...]`, `List[...]`, `Dict[...]` from `typing`; no `X | Y`, no `match`.
- Run everything with `./venv/bin/python` / `./venv/bin/pytest` from the repo root.
- No new dependencies. Call Exa over `httpx` directly; do not add `exa-py`.
- Never log, return or persist the vault (`Dict[str, str]` of placeholder → original). Never print queries or results in server logs.
- With `webSearch` false (or no search client), the model must be called exactly as today: `llm.chat(messages)` with no `tools` argument.
- Exa endpoint: `POST https://api.exa.ai/search`, header `x-api-key: <EXA_API_KEY>`, body `{"query": str, "numResults": 5, "contents": {"highlights": true}}`. Response: `{"results": [{"title": str|null, "url": str, "highlights": [str]}]}`.
- Env vars: `EXA_API_KEY` (search enabled only when set), `EXA_TIMEOUT_SECONDS` (default `20`).
- Limits: `MAX_SEARCHES = 3`, `MAX_LLM_CALLS = 5`, `MAX_SOURCES = 8`, `MAX_RESULT_CHARS = 4000`, `MAX_QUERY_CHARS = 400`.
- Never commit `.env` or `venv/`. Do not push.
- The 5 existing failures in `tests/test_sample_cases.py` predate this work; ignore them. Everything else must pass.
- `public/chat.html` is guarded by a design hook (impeccable). If a write is blocked, fix the flagged CSS pattern (no side-stripe borders, no animating layout properties, no glow box-shadows); never add ignore comments. Follow `DESIGN.md` (tokens: `--ink`, `--ink-soft`, `--line`, `--tint`, `--paper`, `--marigold`, `--alert`).

---

### Task 1: LLM client supports tools and tool calls

**Files:**
- Modify: `lib/workflow/llm_client.py`
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Produces:
  - `ToolCall(id: str, name: str, arguments: str)` (dataclass; `arguments` is the raw JSON string from the server)
  - `LLMReply(content: str, model: str, tool_calls: List[ToolCall] = [])`
  - `OpenAICompatibleClient.chat(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMReply`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_llm_client.py`, and change its import line to `from lib.workflow.llm_client import LLMError, OpenAICompatibleClient, ToolCall`:

```python
def test_chat_sends_tools_and_parses_tool_calls():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "web_search", "arguments": "{\"query\": \"x\"}"}}],
        }}]})

    tools = [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]
    reply = _client(handler, model="m").chat([{"role": "user", "content": "hi"}], tools=tools)

    assert seen["body"]["tools"] == tools
    assert reply.content == ""
    assert reply.tool_calls == [ToolCall(id="c1", name="web_search", arguments='{"query": "x"}')]


def test_chat_without_tools_omits_tools_key():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return _completion("ok")

    reply = _client(handler, model="m").chat([{"role": "user", "content": "hi"}])

    assert "tools" not in seen["body"]
    assert reply.tool_calls == []
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/pytest tests/test_llm_client.py -v`
Expected: collection error `ImportError: cannot import name 'ToolCall'`.

- [ ] **Step 3: Implement** — replace `lib/workflow/llm_client.py` from the imports through the end of `chat` with:

```python
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(Exception):
    """The LLM server could not be reached or returned an unusable response."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class LLMReply:
    content: str
    model: str
    tool_calls: List[ToolCall] = field(default_factory=list)


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

    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMReply:
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                model = self.model or self._first_chat_model(client)
                payload: Dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.2}
                if tools:
                    payload["tools"] = tools
                response = client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        try:
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            tool_calls = [
                ToolCall(
                    id=call.get("id") or "",
                    name=call["function"]["name"],
                    arguments=call["function"].get("arguments") or "{}",
                )
                for call in message.get("tool_calls") or []
            ]
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LLMError("LLM response had no usable choices[0].message") from exc

        return LLMReply(
            content=_THINK_RE.sub("", content).strip(),
            model=data.get("model") or model,
            tool_calls=tool_calls,
        )
```

Keep `_first_chat_model` unchanged below it.

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/pytest tests/test_llm_client.py tests/test_private_chat.py tests/test_chat_endpoint.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/workflow/llm_client.py tests/test_llm_client.py
git commit -m "feat: support tool calls in the OpenAI-compatible LLM client"
```

---

### Task 2: Exa search client and query guard

**Files:**
- Create: `lib/workflow/web_search.py`
- Test: `tests/test_web_search.py`

**Interfaces:**
- Consumes: `run_pipeline(PipelineInput) -> ProcessedMessage` (`lib.pipeline.index`), `PLACEHOLDER_RE` (`lib.workflow.vault`).
- Produces:
  - `WebSearchError(Exception)`
  - `SearchResult(title: str, url: str, highlights: List[str] = [])`
  - `ExaSearchClient(api_key=None, base_url="https://api.exa.ai", timeout=None, num_results=5, transport=None)` with `.search(query: str) -> List[SearchResult]`
  - `check_query(query: str, vault: Dict[str, str], strict: bool = False) -> Optional[str]`, which returns a block reason, or `None` when the query is safe to send.
  - `format_results(results: List[SearchResult]) -> str`
  - Constants `ALWAYS_BLOCKED_TYPES`, `MAX_RESULT_CHARS = 4000`, `MAX_QUERY_CHARS = 400`

- [ ] **Step 1: Write the failing tests** — create `tests/test_web_search.py`:

```python
import json

import httpx
import pytest

from lib.workflow.web_search import (
    MAX_RESULT_CHARS, ExaSearchClient, SearchResult, WebSearchError, check_query, format_results,
)


def _exa(handler):
    return ExaSearchClient(api_key="exa-key", base_url="https://exa.test", timeout=5,
                           transport=httpx.MockTransport(handler))


def test_search_posts_query_and_parses_results():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": [
            {"title": "GOLD 2025 report", "url": "https://goldcopd.org/2025", "highlights": ["Use LAMA/LABA."]},
            {"title": None, "url": "https://example.org/x"},
        ]})

    results = _exa(handler).search("COPD guidelines 2025")

    assert seen["url"] == "https://exa.test/search"
    assert seen["key"] == "exa-key"
    assert seen["body"] == {"query": "COPD guidelines 2025", "numResults": 5, "contents": {"highlights": True}}
    assert results == [
        SearchResult(title="GOLD 2025 report", url="https://goldcopd.org/2025", highlights=["Use LAMA/LABA."]),
        SearchResult(title="https://example.org/x", url="https://example.org/x", highlights=[]),
    ]


def test_http_error_becomes_web_search_error():
    with pytest.raises(WebSearchError):
        _exa(lambda r: httpx.Response(401, json={"error": "bad key"})).search("x")


def test_connection_error_becomes_web_search_error():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(WebSearchError):
        _exa(handler).search("x")


def test_unexpected_shape_becomes_web_search_error():
    with pytest.raises(WebSearchError):
        _exa(lambda r: httpx.Response(200, json={"oops": True})).search("x")


VAULT = {"[PERSON_01]": "Marcus Weber", "[EMAIL_01]": "marcus.weber@acmecorp.com"}


def test_guard_allows_generic_query():
    assert check_query("COPD exacerbation guidelines GOLD 2025", VAULT) is None


def test_guard_blocks_placeholder():
    assert check_query("[PERSON_01] cardiologist Munich", VAULT) is not None


def test_guard_blocks_vault_value_case_insensitively():
    assert check_query("MARCUS WEBER cardiologist", VAULT) is not None


def test_guard_blocks_detected_email():
    assert check_query("contact anna.schmidt@example.org", {}) is not None


def test_guard_blocks_detected_person():
    assert check_query("Dario Amodei interview", {}) is not None


def test_guard_allows_org_unless_strict():
    assert check_query("2025 ADA HbA1c targets older adults", {}) is None
    assert check_query("2025 ADA HbA1c targets older adults", {}, strict=True) is not None


def test_guard_blocks_empty_and_overlong_queries():
    assert check_query("   ", {}) is not None
    assert check_query("a " * 300, {}) is not None


def test_format_results_lists_titles_urls_highlights_and_truncates():
    text = format_results([SearchResult(title="T", url="https://u", highlights=["h1", "x" * 5000])])
    assert text.startswith("1. T\nhttps://u\n- h1")
    assert len(text) == MAX_RESULT_CHARS


def test_format_results_empty():
    assert format_results([]) == "No results found."
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/pytest tests/test_web_search.py -v`
Expected: `ModuleNotFoundError: No module named 'lib.workflow.web_search'`.

- [ ] **Step 3: Implement** — create `lib/workflow/web_search.py`:

```python
"""
Exa web search for the private chat, plus the guard that keeps personal details out of queries.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import httpx

from lib.pipeline.index import run_pipeline
from lib.types import PipelineInput
from lib.workflow.vault import PLACEHOLDER_RE

ALWAYS_BLOCKED_TYPES = {"PERSON", "EMAIL", "PHONE", "IBAN", "DOB", "HANDLE", "BLOCKLIST", "SENDER"}
MAX_RESULT_CHARS = 4000
MAX_QUERY_CHARS = 400


class WebSearchError(Exception):
    """Exa could not be reached or returned an unusable response."""


@dataclass
class SearchResult:
    title: str
    url: str
    highlights: List[str] = field(default_factory=list)


class ExaSearchClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.exa.ai",
        timeout: Optional[float] = None,
        num_results: int = 5,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.api_key = api_key if api_key is not None else os.getenv("EXA_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or float(os.getenv("EXA_TIMEOUT_SECONDS", "20"))
        self.num_results = num_results
        self._transport = transport

    def search(self, query: str) -> List[SearchResult]:
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"x-api-key": self.api_key},
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                response = client.post(
                    "/search",
                    json={"query": query, "numResults": self.num_results, "contents": {"highlights": True}},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WebSearchError(f"Exa search failed: {exc}") from exc

        try:
            return [
                SearchResult(
                    title=entry.get("title") or entry["url"],
                    url=entry["url"],
                    highlights=[h for h in entry.get("highlights") or [] if isinstance(h, str)],
                )
                for entry in data["results"]
            ]
        except (KeyError, TypeError, AttributeError) as exc:
            raise WebSearchError("Exa response had no usable results list") from exc


def check_query(query: str, vault: Dict[str, str], strict: bool = False) -> Optional[str]:
    """Return why the query must not be sent to Exa, or None when it is safe."""
    if not query.strip():
        return "empty query"
    if len(query) > MAX_QUERY_CHARS:
        return "query too long"
    if PLACEHOLDER_RE.search(query):
        return "contains a placeholder"
    lowered = query.lower()
    for original in vault.values():
        if len(original) >= 3 and original.lower() in lowered:
            return "contains a personal detail from the message"
    detected = run_pipeline(PipelineInput(rawText=query, sessionId="web_search_guard"))
    for token in detected.tokens:
        if strict or token.type in ALWAYS_BLOCKED_TYPES:
            return f"contains a possible {token.type.lower()}"
    return None


def format_results(results: List[SearchResult]) -> str:
    if not results:
        return "No results found."
    lines = []
    for number, result in enumerate(results, 1):
        lines.append(f"{number}. {result.title}\n{result.url}")
        lines.extend(f"- {highlight.strip()}" for highlight in result.highlights)
    return "\n".join(lines)[:MAX_RESULT_CHARS]
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/pytest tests/test_web_search.py -v`
Expected: all PASS. If `test_guard_blocks_detected_person` fails because spaCy misses the name, do not weaken the guard; report it.

- [ ] **Step 5: Commit**

```bash
git add lib/workflow/web_search.py tests/test_web_search.py
git commit -m "feat: add Exa search client and personal-detail query guard"
```

---

### Task 3: Tool-calling loop in the private chat workflow

**Files:**
- Modify: `lib/workflow/private_chat.py`
- Test: `tests/test_private_chat_search.py`

**Interfaces:**
- Consumes: `LLMReply`, `ToolCall` (Task 1); `WebSearchError`, `check_query`, `format_results`, `SearchResult` (Task 2). The search client is duck-typed: any object with `.search(query) -> List[SearchResult]`.
- Produces:
  - `SearchAttempt(query: str, status: str, result_count: int = 0)` where status is `"sent" | "blocked" | "failed"`
  - `Source(title: str, url: str)`
  - `PrivateChatResult.searches: List[SearchAttempt]` and `PrivateChatResult.sources: List[Source]` (both default to empty)
  - `run_private_chat(prompt, llm, blocklist="", strict=False, search=None) -> PrivateChatResult`
  - Constants `MAX_SEARCHES = 3`, `MAX_LLM_CALLS = 5`, `MAX_SOURCES = 8`, `SEARCH_PROMPT`, `WEB_SEARCH_TOOL`, `BLOCKED_MESSAGE`, `FAILED_MESSAGE`, `INVALID_MESSAGE`, `LIMIT_MESSAGE`

- [ ] **Step 1: Write the failing tests** — create `tests/test_private_chat_search.py`:

```python
import copy
import json

import lib.workflow.private_chat as private_chat
from lib.workflow.llm_client import LLMReply, ToolCall
from lib.workflow.private_chat import SearchAttempt, Source, run_private_chat
from lib.workflow.vault import PLACEHOLDER_RE
from lib.workflow.web_search import SearchResult, WebSearchError

PROMPT = (
    "Write a short reply to Marcus Weber. His email is marcus.weber@acmecorp.com "
    "and his phone is +49 170 555 0198."
)
SECRETS = ["marcus.weber@acmecorp.com", "+49 170 555 0198", "Marcus"]


class ScriptedLLM:
    """Returns scripted replies in order; a reply may be a function of the messages."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append({"messages": copy.deepcopy(messages), "tools": tools})
        reply = self.replies.pop(0)
        return reply(messages) if callable(reply) else reply


class FakeSearch:
    def __init__(self, results=None, error=False):
        self.results = results or []
        self.error = error
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        if self.error:
            raise WebSearchError("down")
        return self.results


def search_call(query, call_id="c1"):
    return LLMReply(content="", model="m", tool_calls=[
        ToolCall(id=call_id, name="web_search", arguments=json.dumps({"query": query}))])


def echo_answer(messages):
    placeholders = PLACEHOLDER_RE.findall(messages[1]["content"])
    return LLMReply(content="Contacting " + " and ".join(placeholders), model="m")


RESULTS = [
    SearchResult(title="GOLD 2025", url="https://goldcopd.org/2025", highlights=["LAMA/LABA first"]),
    SearchResult(title="GOLD 2025 again", url="https://goldcopd.org/2025"),
    SearchResult(title="NICE COPD", url="https://nice.org.uk/copd"),
]


def test_without_search_client_model_gets_no_tools():
    llm = ScriptedLLM([LLMReply(content="ok", model="m")])
    result = run_private_chat(PROMPT, llm)
    assert len(llm.calls) == 1
    assert llm.calls[0]["tools"] is None
    assert llm.calls[0]["messages"][0]["content"] == private_chat.SYSTEM_PROMPT
    assert result.searches == [] and result.sources == []


def test_allowed_search_runs_and_answer_is_restored():
    llm = ScriptedLLM([search_call("COPD guidelines 2025"), echo_answer])
    search = FakeSearch(RESULTS)

    result = run_private_chat(PROMPT, llm, search=search)

    assert search.queries == ["COPD guidelines 2025"]
    assert llm.calls[0]["tools"] == [private_chat.WEB_SEARCH_TOOL]
    assert private_chat.SEARCH_PROMPT in llm.calls[0]["messages"][0]["content"]
    second = llm.calls[1]["messages"]
    assert second[2]["role"] == "assistant" and second[2]["tool_calls"][0]["id"] == "c1"
    assert second[3]["role"] == "tool" and second[3]["tool_call_id"] == "c1"
    assert "GOLD 2025" in second[3]["content"]
    sent = json.dumps([c["messages"] for c in llm.calls]) + json.dumps(search.queries)
    for secret in SECRETS:
        assert secret not in sent
    assert result.searches == [SearchAttempt(query="COPD guidelines 2025", status="sent", result_count=3)]
    assert result.sources == [Source("GOLD 2025", "https://goldcopd.org/2025"), Source("NICE COPD", "https://nice.org.uk/copd")]
    assert "marcus.weber@acmecorp.com" in result.answer


def test_query_with_placeholder_is_blocked_and_not_sent():
    llm = ScriptedLLM([search_call("[PERSON_01] email history"), echo_answer])
    search = FakeSearch(RESULTS)

    result = run_private_chat(PROMPT, llm, search=search)

    assert search.queries == []
    assert result.searches == [SearchAttempt(query="[PERSON_01] email history", status="blocked")]
    assert llm.calls[1]["messages"][3]["content"] == private_chat.BLOCKED_MESSAGE


def test_query_with_personal_detail_is_blocked():
    llm = ScriptedLLM([search_call("marcus.weber@acmecorp.com"), echo_answer])
    search = FakeSearch(RESULTS)
    result = run_private_chat(PROMPT, llm, search=search)
    assert search.queries == []
    assert result.searches[0].status == "blocked"


def test_search_failure_falls_back_to_answer():
    llm = ScriptedLLM([search_call("COPD guidelines 2025"), echo_answer])
    result = run_private_chat(PROMPT, llm, search=FakeSearch(error=True))
    assert result.searches == [SearchAttempt(query="COPD guidelines 2025", status="failed")]
    assert llm.calls[1]["messages"][3]["content"] == private_chat.FAILED_MESSAGE
    assert result.answer.startswith("Contacting ")


def test_search_limit_then_forced_answer():
    llm = ScriptedLLM([
        search_call("q one", "c1"), search_call("q two", "c2"), search_call("q three", "c3"),
        search_call("q four", "c4"), LLMReply(content="final", model="m"),
    ])
    search = FakeSearch(RESULTS)

    result = run_private_chat(PROMPT, llm, search=search)

    assert search.queries == ["q one", "q two", "q three"]
    assert llm.calls[3]["tools"] is None
    assert llm.calls[4]["messages"][-1]["content"] == private_chat.LIMIT_MESSAGE
    assert len(llm.calls) == private_chat.MAX_LLM_CALLS
    assert result.anonymized_answer == "final"


def test_invalid_arguments_are_blocked():
    bad = LLMReply(content="", model="m", tool_calls=[ToolCall(id="c1", name="web_search", arguments="not json")])
    llm = ScriptedLLM([bad, echo_answer])
    search = FakeSearch(RESULTS)
    result = run_private_chat(PROMPT, llm, search=search)
    assert search.queries == []
    assert result.searches == [SearchAttempt(query="", status="blocked")]
    assert llm.calls[1]["messages"][3]["content"] == private_chat.INVALID_MESSAGE
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/pytest tests/test_private_chat_search.py -v`
Expected: `ImportError: cannot import name 'SearchAttempt'`.

- [ ] **Step 3: Implement** — in `lib/workflow/private_chat.py`:

Replace the imports with:

```python
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lib.pipeline.index import run_pipeline
from lib.types import PipelineInput
from lib.workflow.llm_client import LLMReply, ToolCall
from lib.workflow.vault import build_vault, reenrich
from lib.workflow.web_search import WebSearchError, check_query, format_results
```

Add after `SYSTEM_PROMPT`:

```python
SEARCH_PROMPT = (
    "You can call the web_search tool when the question needs current or factual information "
    "from the web. Search queries must be short and generic: never put placeholders or any "
    "personal details in a query. Search for the topic, not the person."
)

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information on a generic topic. "
                       "Never include placeholders or personal details in the query.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Short, generic search query"}},
            "required": ["query"],
        },
    },
}

MAX_SEARCHES = 3
MAX_LLM_CALLS = 5
MAX_SOURCES = 8

BLOCKED_MESSAGE = "Search blocked: the query contained personal details. Search only for generic topics."
FAILED_MESSAGE = "Search unavailable right now. Answer from your own knowledge and say so."
INVALID_MESSAGE = 'Search not run: arguments must be JSON like {"query": "..."}.'
LIMIT_MESSAGE = "Search limit reached. Answer with the information you already have."
```

Add these dataclasses before `PrivateChatResult`, and two fields at the end of `PrivateChatResult`:

```python
@dataclass
class SearchAttempt:
    query: str
    status: str
    result_count: int = 0


@dataclass
class Source:
    title: str
    url: str
```

```python
    searches: List[SearchAttempt] = field(default_factory=list)
    sources: List[Source] = field(default_factory=list)
```

Replace `run_private_chat` and add the helpers:

```python
def run_private_chat(
    prompt: str, llm, blocklist: str = "", strict: bool = False, search=None
) -> PrivateChatResult:
    anonymized = run_pipeline(PipelineInput(rawText=prompt, blocklist=blocklist, sessionId="private_chat"))

    if strict and anonymized.confidence.routing == "review":
        raise PrivacyRoutingError(list(anonymized.confidence.failureReasons))

    vault = build_vault(anonymized)
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": anonymized.cleanedText},
    ]
    searches: List[SearchAttempt] = []
    sources: List[Source] = []

    if search is None:
        reply = llm.chat(messages)
    else:
        messages[0] = {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + SEARCH_PROMPT}
        reply = _chat_with_search(llm, search, messages, vault, strict, searches, sources)

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
        searches=searches,
        sources=sources,
    )


def _chat_with_search(llm, search, messages, vault, strict, searches, sources) -> LLMReply:
    for _ in range(MAX_LLM_CALLS - 1):
        if len(searches) < MAX_SEARCHES:
            reply = llm.chat(messages, tools=[WEB_SEARCH_TOOL])
        else:
            reply = llm.chat(messages)
        if not reply.tool_calls:
            return reply
        messages.append({
            "role": "assistant",
            "content": reply.content,
            "tool_calls": [
                {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
                for call in reply.tool_calls
            ],
        })
        for call in reply.tool_calls:
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": _run_tool_call(call, search, vault, strict, searches, sources),
            })
    return llm.chat(messages)


def _run_tool_call(call: ToolCall, search, vault, strict, searches, sources) -> str:
    if len(searches) >= MAX_SEARCHES:
        return LIMIT_MESSAGE
    query = _parse_query(call)
    if query is None:
        searches.append(SearchAttempt(query="", status="blocked"))
        return INVALID_MESSAGE
    if check_query(query, vault, strict) is not None:
        searches.append(SearchAttempt(query=query, status="blocked"))
        return BLOCKED_MESSAGE
    try:
        results = search.search(query)
    except WebSearchError:
        searches.append(SearchAttempt(query=query, status="failed"))
        return FAILED_MESSAGE
    searches.append(SearchAttempt(query=query, status="sent", result_count=len(results)))
    known = {source.url for source in sources}
    for result in results:
        if result.url not in known and len(sources) < MAX_SOURCES:
            sources.append(Source(title=result.title, url=result.url))
            known.add(result.url)
    return format_results(results)


def _parse_query(call: ToolCall) -> Optional[str]:
    if call.name != "web_search":
        return None
    try:
        args = json.loads(call.arguments or "{}")
    except ValueError:
        return None
    query = args.get("query") if isinstance(args, dict) else None
    if not isinstance(query, str) or not query.strip():
        return None
    return query.strip()
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/pytest tests/test_private_chat_search.py tests/test_private_chat.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/workflow/private_chat.py tests/test_private_chat_search.py
git commit -m "feat: add guarded web search tool loop to private chat"
```

---

### Task 4: API contract, config endpoint and docs

**Files:**
- Modify: `lib/types.py` (near `ChatRequest` / `ChatResponse`, around lines 119-136)
- Modify: `api/anonymise.py` (around lines 38 and 314-370)
- Modify: `.env.example`, `README.md`
- Test: `tests/test_chat_endpoint.py`

**Interfaces:**
- Consumes: `run_private_chat(..., search=...)`, `PrivateChatResult.searches/.sources` (Task 3); `ExaSearchClient`, `SearchResult` (Task 2); `LLMReply`, `ToolCall` (Task 1).
- Produces:
  - `POST /api/chat` request field `webSearch: bool = False`
  - Response fields `searches: [{query, status, resultCount}]` and `sources: [{title, url}]`
  - `GET /api/chat/config` → `{"webSearch": bool}`
  - `api_module.get_search_client() -> Optional[ExaSearchClient]` (FastAPI dependency; tests override it)

- [ ] **Step 1: Write the failing tests** — edit `tests/test_chat_endpoint.py`:

Add these imports:

```python
import json

from lib.workflow.llm_client import ToolCall
from lib.workflow.web_search import SearchResult
```

In the `client` fixture, after the `get_llm_client` override line, add:

```python
    api_module.app.dependency_overrides[api_module.get_search_client] = lambda: None
```

In `test_chat_returns_reenriched_answer_without_vault`, extend the expected key set with `"searches", "sources"`.

Append:

```python
class OneResultSearch:
    def search(self, query):
        return [SearchResult(title="GOLD 2025", url="https://goldcopd.org/2025")]


class SearchingLLM:
    def __init__(self):
        self.turn = 0

    def chat(self, messages, tools=None):
        self.turn += 1
        if self.turn == 1:
            return LLMReply(content="", model="echo", tool_calls=[
                ToolCall(id="c1", name="web_search", arguments=json.dumps({"query": "COPD guidelines"}))])
        return LLMReply(content="Per GOLD 2025, see a doctor.", model="echo")


def test_chat_config_reports_search_availability(client):
    assert client.get("/api/chat/config").json() == {"webSearch": False}
    api_module.app.dependency_overrides[api_module.get_search_client] = lambda: OneResultSearch()
    assert client.get("/api/chat/config").json() == {"webSearch": True}


def test_chat_with_web_search_returns_searches_and_sources(client):
    api_module.app.dependency_overrides[api_module.get_search_client] = lambda: OneResultSearch()
    api_module.app.dependency_overrides[api_module.get_llm_client] = lambda: SearchingLLM()

    response = client.post("/api/chat", json={"prompt": "What is new in COPD care?", "webSearch": True})

    assert response.status_code == 200
    body = response.json()
    assert body["searches"] == [{"query": "COPD guidelines", "status": "sent", "resultCount": 1}]
    assert body["sources"] == [{"title": "GOLD 2025", "url": "https://goldcopd.org/2025"}]
    assert body["answer"] == "Per GOLD 2025, see a doctor."


def test_chat_ignores_web_search_flag_without_client(client):
    response = client.post("/api/chat", json={"prompt": "Email anna.schmidt@example.org today.", "webSearch": True})
    assert response.status_code == 200
    assert response.json()["searches"] == []


def test_chat_without_flag_does_not_search(client):
    api_module.app.dependency_overrides[api_module.get_search_client] = lambda: OneResultSearch()
    response = client.post("/api/chat", json={"prompt": "Email anna.schmidt@example.org today."})
    assert response.status_code == 200
    assert response.json()["searches"] == []
```

`EchoLLM.chat(messages)` has no `tools` parameter. The last two tests prove that the search-off path never passes one.

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/pytest tests/test_chat_endpoint.py -v`
Expected: FAIL with `AttributeError: module 'api.anonymise' has no attribute 'get_search_client'`.

- [ ] **Step 3: Implement types** — in `lib/types.py`, add `webSearch` to `ChatRequest`, define the new models before `ChatResponse`, and add two fields to `ChatResponse`:

```python
class ChatRequest(BaseModel):
    """Request body for the private chat workflow."""
    prompt: str = Field(..., min_length=1, max_length=MAX_WORKFLOW_CHARS, description="Prompt that may contain PII")
    blocklist: str = Field(default="", description="Comma-separated list of extra terms to redact")
    strict: bool = Field(default=False, description="Refuse to call the LLM when routing is 'review'")
    webSearch: bool = Field(default=False, description="Let the model search the web via Exa")


class SearchRecord(BaseModel):
    """One web search the model asked for."""
    query: str
    status: Literal["sent", "blocked", "failed"]
    resultCount: int = 0


class SourceLink(BaseModel):
    title: str
    url: str


class ChatConfig(BaseModel):
    webSearch: bool
```

Append to `ChatResponse`, after `model: str`:

```python
    searches: List[SearchRecord] = Field(default_factory=list)
    sources: List[SourceLink] = Field(default_factory=list)
```

- [ ] **Step 4: Implement the endpoint** — in `api/anonymise.py`:

Add `ChatConfig, SearchRecord, SourceLink` to the existing `from lib.types import ...` line. Add the import:

```python
from lib.workflow.web_search import ExaSearchClient
```

Below `get_llm_client`, add:

```python
def get_search_client() -> Optional[ExaSearchClient]:
    return ExaSearchClient() if os.getenv("EXA_API_KEY") else None


@app.get("/api/chat/config", response_model=ChatConfig)
def chat_config(search: Optional[ExaSearchClient] = Depends(get_search_client)):
    """Tell the chat UI which optional features the server has configured."""
    return ChatConfig(webSearch=search is not None)
```

In `private_chat(...)`, add the parameter `search: Optional[ExaSearchClient] = Depends(get_search_client),` after `llm`. Change the workflow call to:

```python
        result = run_private_chat(
            body.prompt, llm, blocklist=body.blocklist, strict=body.strict,
            search=search if body.webSearch else None,
        )
```

Add these to the `ChatResponse(...)` construction, after `model=result.model,`:

```python
        searches=[
            SearchRecord(query=s.query, status=s.status, resultCount=s.result_count)
            for s in result.searches
        ],
        sources=[SourceLink(title=s.title, url=s.url) for s in result.sources],
```

- [ ] **Step 5: Docs** — append to `.env.example`:

```
# Optional: enables "Search the web" in the private chat (https://dashboard.exa.ai/api-keys)
EXA_API_KEY=
EXA_TIMEOUT_SECONDS=20
```

In `README.md`, under the existing private chat section, add a short subsection called "Web search (optional)". It should cover four points:
- Setting `EXA_API_KEY` shows a "Search the web" toggle.
- The model decides when to search, up to 3 searches per message.
- Every query is checked and blocked if it contains placeholders, your original values, or detected names, emails, phones, IBANs, birth dates or handles. Strict mode blocks any detection.
- The answer lists the queries sent and the source links.

- [ ] **Step 6: Run to verify pass**

Run: `./venv/bin/pytest tests -q --deselect tests/test_sample_cases.py`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add lib/types.py api/anonymise.py tests/test_chat_endpoint.py .env.example README.md
git commit -m "feat: expose web search flag, results and config on the chat API"
```

---

### Task 5: Chat UI — toggle, searched queries, sources, notices

**Files:**
- Modify: `public/chat.html` (composer markup around line 609-613, CSS near `.receipt`/`.notice` around line 350-370 and `.check` around line 476, JS `els` around line 627, `buildExchange` ~728, `addReceipt` ~789, `send` ~839)

**Interfaces:**
- Consumes: `GET /api/chat/config` → `{webSearch}`; `POST /api/chat` with `webSearch`; response `searches`, `sources` (Task 4).

There is no automated test harness for this page. Verify manually in Step 6.

- [ ] **Step 1: Markup** — inside `.composer-options`, after the `strict` label, add:

```html
                    <label class="check" id="webSearchOption" hidden><input type="checkbox" id="webSearch"> Search the web</label>
```

- [ ] **Step 2: CSS** — after the `.check input` rule, add:

```css
        .check[hidden] { display: none; }
```

After the `.notice a` rule, add:

```css
        .searched { margin: 0.6rem 0 0; font-size: 0.85rem; color: var(--ink-soft); }
        .searched q { color: var(--ink); }

        .sources { list-style: none; margin: 0.5rem 0 0; padding: 0; display: grid; gap: 0.3rem; font-size: 0.9rem; }
        .sources a { color: var(--ink); text-decoration: underline; text-decoration-color: var(--line); text-underline-offset: 3px; }
        .sources a:hover { text-decoration-color: var(--ink); }
        .source-host { margin-left: 0.4rem; font-size: 0.8rem; color: var(--ink-soft); }
```

- [ ] **Step 3: JS state and config** — add to the `els` object:

```js
            webSearch: document.getElementById('webSearch'),
            webSearchOption: document.getElementById('webSearchOption'),
```

At the end of the script (after the existing event listeners), add:

```js
        fetch('/api/chat/config')
            .then((response) => (response.ok ? response.json() : {}))
            .then((config) => { if (config.webSearch) els.webSearchOption.hidden = false; })
            .catch(() => {});
```

- [ ] **Step 4: Request and thinking text** — in `send`, compute this before `buildExchange`:

```js
            const searching = !els.webSearchOption.hidden && els.webSearch.checked;
            const ctx = buildExchange(promptText, searching);
```

(This replaces `const ctx = buildExchange(promptText);`.) Add `webSearch: searching,` to the JSON body after `strict`.

Change `function buildExchange(promptText) {` to `function buildExchange(promptText, searching) {`. Change the thinking label line to:

```js
            thinking.append(wave, el('span', '', searching ? 'Hiding your details, asking the AI and searching the web…' : 'Hiding your details and asking the AI…'));
```

- [ ] **Step 5: Receipt, queries, sources, notices** — in `addReceipt`, insert this before `receipt.append(el('span', '', \`Answered by ${data.model}\`));`:

```js
            const searches = data.searches || [];
            const sent = searches.filter((s) => s.status === 'sent');
            if (sent.length) receipt.append(el('span', '', `Searched the web ${sent.length}×`));
```

Insert this after `ctx.exchange.append(receipt);`:

```js
            if (sent.length) {
                const searched = el('p', 'searched', 'Searched for: ');
                sent.forEach((s, i) => {
                    if (i) searched.append(document.createTextNode(', '));
                    searched.append(el('q', '', s.query));
                });
                ctx.exchange.append(searched);
            }

            const sources = data.sources || [];
            if (sources.length) {
                const list = el('ul', 'sources');
                list.setAttribute('aria-label', 'Sources');
                for (const source of sources) {
                    if (!/^https?:\/\//i.test(source.url)) continue;
                    const item = el('li');
                    const link = el('a', '', source.title);
                    link.href = source.url;
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    item.append(link);
                    try {
                        item.append(el('span', 'source-host', new URL(source.url).hostname));
                    } catch (error) {}
                    list.append(item);
                }
                ctx.exchange.append(list);
            }

            const blocked = searches.filter((s) => s.status === 'blocked').length;
            if (blocked) {
                ctx.exchange.append(el('p', 'notice', blocked === 1
                    ? 'One web search was blocked because it contained personal details, so it was not sent.'
                    : `${blocked} web searches were blocked because they contained personal details, so they were not sent.`));
            }
            if (searches.some((s) => s.status === 'failed')) {
                ctx.exchange.append(el('p', 'notice', 'Web search was unavailable, so the AI answered from its own knowledge.'));
            }
```

Only `sources` links use `href`, and only for `http:`/`https:` URLs. Every other dynamic string goes through `textContent` via `el()`. Never use `innerHTML`.

- [ ] **Step 6: Manual verification** — with uvicorn running on port 8000 and `EXA_API_KEY` set in `.env` (restart uvicorn after setting it):
  1. Open `http://localhost:8000/chat`. Check that "Search the web" appears in the composer. Without the key it must be hidden.
  2. Tick it and send: `What do the latest GOLD guidelines recommend for a COPD patient like Hans Müller (born 05.11.1948) with two exacerbations this year?`
  3. Expect three things: a "Searched the web N×" receipt entry, a "Searched for:" line with no name or date in any query, and source links that open in a new tab.
  4. Switch to "The AI" and confirm the prompt shows placeholders.
  5. Untick, send again, and confirm there's no search line.
  6. Run `node /Users/prafulsrivastava/.cursor/skills/impeccable/scripts/detect.mjs --json public/chat.html` and expect `[]`.

- [ ] **Step 7: Commit**

```bash
git add public/chat.html
git commit -m "feat: web search toggle, queries and sources in the chat UI"
```

# Private Web Search (Exa) — Design

## Goal

Let the private chat answer questions that need current information by giving the model a
web search tool backed by [Exa](https://exa.ai/docs), without letting personal details reach
Exa.

## User-facing behavior

- The composer shows a **"Search the web"** checkbox, but only when the server has
  `EXA_API_KEY` configured. Without the key, the checkbox stays hidden and chat behaves
  exactly as today.
- With the box ticked, the model may call a `web_search` tool. It decides whether and what to
  search. At most 3 searches run per message.
- Each answer that used search shows:
  - a receipt entry such as `Searched the web 2×`;
  - a "Searched for" line listing the exact queries sent to Exa;
  - a "Sources" list of result links (title + URL, deduplicated, at most 8).
- If a query was blocked by the privacy guard, a notice says so. If Exa failed, a notice says
  the answer was written without web results. Neither case stops the answer.

## Architecture

The existing flow stays the same: anonymize → vault → LLM → re-enrich. Search adds a
tool-calling loop inside the LLM step:

1. The model receives the anonymized prompt plus the `web_search` tool definition and an extra
   system instruction: queries must be generic and must never contain placeholders or
   personal details.
2. When the model returns tool calls, each query goes through the **query guard**. Allowed
   queries are sent to Exa `/search` (5 results, highlights). The results are formatted as text
   and returned to the model as `tool` messages.
3. After 3 searches, the model is called once more without tools, so it must answer.
   There is also a hard cap of 5 model calls.
4. The final answer is re-enriched as today.

### Query guard

A query is **blocked** (not sent to Exa) when any of the following is true:

- it contains a placeholder (`PLACEHOLDER_RE`), such as `[PERSON_01]`;
- it contains any original value from this request's vault (case-insensitive, values of 3+
  characters);
- running the anonymizer pipeline on the query detects a token of type `PERSON`, `EMAIL`,
  `PHONE`, `IBAN`, `DOB`, `HANDLE`, `BLOCKLIST` or `SENDER`;
- strict mode is on and the pipeline detects any token at all, including `ORG`, `LOCATION`,
  `URL` or `AGE`.

`ORG`, `LOCATION`, `URL` and `AGE` detections are allowed outside strict mode, because
everyday queries trigger them on public terms (for example "ADA", "IBAN" and "Germany").

When a query is blocked, the model receives the tool result
`"Search blocked: the query contained personal details. Search only for generic topics."`

### Components

| File | Responsibility |
|---|---|
| `lib/workflow/llm_client.py` | `chat(messages, tools=None)`; `LLMReply.tool_calls: List[ToolCall]` |
| `lib/workflow/web_search.py` (new) | `ExaSearchClient`, `SearchResult`, `WebSearchError`, `check_query`, `format_results` |
| `lib/workflow/private_chat.py` | Tool loop; `PrivateChatResult.searches` and `.sources` |
| `lib/types.py` | `ChatRequest.webSearch`; `ChatResponse.searches` and `.sources`; `SearchRecord`, `SourceLink`; `ChatConfig` |
| `api/anonymise.py` | `get_search_client()` dependency; passes the client to the workflow; `GET /api/chat/config` |
| `public/chat.html` | Checkbox, receipt entry, "Searched for" line, sources list, notices |

The Exa client uses `httpx` directly (already a dependency). No Exa SDK is added.

### Data contract

`POST /api/chat` request gains `webSearch: bool = false`.

The response gains two fields:

- `searches: [{query, status: "sent" | "blocked" | "failed", resultCount}]`
- `sources: [{title, url}]`

Blocked queries are returned with their status so the user can see them. They contain no
personal values from the vault: the guard blocks on them, and the model never saw the originals.

`GET /api/chat/config` returns `{ "webSearch": bool }`, which is true when `EXA_API_KEY` is set.

### Configuration

- `EXA_API_KEY`: required to enable search.
- `EXA_TIMEOUT_SECONDS`: default 20.

### Error handling

- An Exa HTTP error, timeout or unexpected response raises `WebSearchError`. That search is
  recorded as `failed`, and the model receives
  `"Search unavailable right now. Answer from your own knowledge and say so."`
- Malformed tool-call arguments, or a call to an unknown tool, are recorded as `blocked` with
  an empty query, and the model receives an invalid-arguments message.
- If `webSearch` is true but no search client is configured, the flag is ignored.
- LLM errors keep the existing 502 mapping.

### Privacy invariants (must be tested)

1. No vault original value ever appears in a request sent to Exa.
2. No placeholder ever appears in a request sent to Exa.
3. With `webSearch` false, the model is called with no `tools` and the request is identical to
   today's.
4. The vault is still never logged, returned or persisted.

## Testing

- `test_llm_client.py`: tools are sent in the body; tool calls are parsed; `content: null` is
  handled.
- `test_web_search.py`: the Exa request shape and auth header, result parsing, errors becoming
  `WebSearchError`, every guard rule, and result formatting with truncation.
- `test_private_chat_search.py`: the full loop with a scripted fake LLM and a fake search
  client, covering blocking, the 3-search limit, failure fallback, source dedupe, and the
  search-off path.
- `test_chat_endpoint.py`: the `webSearch` flag, the new response fields, and `/api/chat/config`.

## Out of scope

- Multi-turn memory.
- Fetching full page contents (`/contents`).
- Exa deep search or agents.
- Counting searches against the quota.

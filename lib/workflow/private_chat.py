"""
Private chat workflow: anonymize a prompt, send only the anonymized text to an LLM,
then restore the original values in the LLM's answer.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lib.pipeline.index import run_pipeline
from lib.types import PipelineInput
from lib.workflow.llm_client import LLMReply, ToolCall
from lib.workflow.vault import build_vault, reenrich
from lib.workflow.web_search import WebSearchError, check_query, format_results

SYSTEM_PROMPT = (
    "Some details in the user's message were replaced with placeholders such as "
    "[PERSON_01], [EMAIL_01] or [LOCATION_01]. Treat each placeholder as the real value it "
    "stands for. Whenever you refer to one of these values, write the placeholder exactly as "
    "given, including the square brackets, capital letters and number. Never invent new "
    "placeholders and never guess what the hidden values are."
)

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


class PrivacyRoutingError(Exception):
    """Strict mode refused to send a prompt the anonymizer routed to review."""

    def __init__(self, reasons: List[str]):
        super().__init__("Anonymization confidence too low to send prompt")
        self.reasons = reasons


@dataclass
class SearchAttempt:
    query: str
    status: str
    result_count: int = 0


@dataclass
class Source:
    title: str
    url: str


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
    searches: List[SearchAttempt] = field(default_factory=list)
    sources: List[Source] = field(default_factory=list)


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

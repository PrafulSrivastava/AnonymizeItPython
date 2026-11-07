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

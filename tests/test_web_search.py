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

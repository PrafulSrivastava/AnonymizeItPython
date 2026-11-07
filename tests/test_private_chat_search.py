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

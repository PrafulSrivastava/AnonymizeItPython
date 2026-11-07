import json

import httpx
import pytest

from lib.workflow.llm_client import LLMError, OpenAICompatibleClient, ToolCall


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

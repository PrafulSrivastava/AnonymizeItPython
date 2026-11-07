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

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

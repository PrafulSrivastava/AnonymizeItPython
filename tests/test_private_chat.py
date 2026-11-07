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

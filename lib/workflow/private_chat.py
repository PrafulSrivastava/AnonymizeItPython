"""
Private chat workflow: anonymize a prompt, send only the anonymized text to an LLM,
then restore the original values in the LLM's answer.
"""

from dataclasses import dataclass, field
from typing import List

from lib.pipeline.index import run_pipeline
from lib.types import PipelineInput
from lib.workflow.vault import build_vault, reenrich

SYSTEM_PROMPT = (
    "Some details in the user's message were replaced with placeholders such as "
    "[PERSON_01], [EMAIL_01] or [LOCATION_01]. Treat each placeholder as the real value it "
    "stands for. Whenever you refer to one of these values, write the placeholder exactly as "
    "given, including the square brackets, capital letters and number. Never invent new "
    "placeholders and never guess what the hidden values are."
)


class PrivacyRoutingError(Exception):
    """Strict mode refused to send a prompt the anonymizer routed to review."""

    def __init__(self, reasons: List[str]):
        super().__init__("Anonymization confidence too low to send prompt")
        self.reasons = reasons


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


def run_private_chat(prompt: str, llm, blocklist: str = "", strict: bool = False) -> PrivateChatResult:
    anonymized = run_pipeline(PipelineInput(rawText=prompt, blocklist=blocklist, sessionId="private_chat"))

    if strict and anonymized.confidence.routing == "review":
        raise PrivacyRoutingError(list(anonymized.confidence.failureReasons))

    vault = build_vault(anonymized)

    reply = llm.chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": anonymized.cleanedText},
    ])
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
    )

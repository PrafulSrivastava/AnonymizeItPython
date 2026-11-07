from typing import List

import pytest

from lib.types import ConfidenceScore, ConfidenceSignals, ProcessedMessage, RedactionToken
from lib.workflow.vault import VaultIntegrityError, build_vault, reenrich


def _token(type_: str, value: str, original: str) -> RedactionToken:
    return RedactionToken(type=type_, value=value, original=original, startIndex=0, endIndex=1)


def _message(cleaned: str, tokens: List[RedactionToken]) -> ProcessedMessage:
    return ProcessedMessage(
        messageId="m",
        cleanedText=cleaned,
        tokens=tokens,
        confidence=ConfidenceScore(
            overall=1.0,
            routing="pass",
            signals=ConfidenceSignals(
                regexCoverage=1.0, nerConfidence=1.0, quasiIdentifierCount=0, residualTokenDensity=1.0
            ),
        ),
    )


def test_build_vault_maps_placeholders_present_in_text():
    msg = _message(
        "Hi [PERSON_01], mail [EMAIL_01]",
        [
            _token("PERSON", "[PERSON_01]", "Anna"),
            _token("EMAIL", "[EMAIL_01]", "anna@x.org"),
            _token("PERSON", "[PERSON_02]", "Unused"),
        ],
    )
    assert build_vault(msg) == {"[PERSON_01]": "Anna", "[EMAIL_01]": "anna@x.org"}


def test_build_vault_ignores_brackets_that_are_not_token_types():
    msg = _message("[TODO] ask [PERSON_01]", [_token("PERSON", "[PERSON_01]", "Anna")])
    assert build_vault(msg) == {"[PERSON_01]": "Anna"}


def test_build_vault_raises_when_placeholder_has_no_original():
    msg = _message("Hi [PERSON_02]", [_token("PERSON", "[PERSON_01]", "Anna")])
    with pytest.raises(VaultIntegrityError):
        build_vault(msg)


def test_build_vault_raises_on_conflicting_originals():
    msg = _message(
        "Hi [PERSON_01]",
        [_token("PERSON", "[PERSON_01]", "Anna"), _token("BLOCKLIST", "[PERSON_01]", "Bob")],
    )
    with pytest.raises(VaultIntegrityError):
        build_vault(msg)


def test_reenrich_restores_every_occurrence():
    vault = {"[PERSON_01]": "Anna", "[EMAIL_01]": "anna@x.org"}
    result = reenrich("Dear [PERSON_01], we wrote to [EMAIL_01]. Thanks [PERSON_01]!", vault)
    assert result.text == "Dear Anna, we wrote to anna@x.org. Thanks Anna!"
    assert result.restored == ["[PERSON_01]", "[EMAIL_01]"]
    assert result.unknown_placeholders == []


def test_reenrich_is_case_insensitive():
    result = reenrich("Dear [person_01]", {"[PERSON_01]": "Anna"})
    assert result.text == "Dear Anna"


def test_reenrich_handles_age_bucket_placeholders():
    result = reenrich("You are [AGE_30s]", {"[AGE_30s]": "34"})
    assert result.text == "You are 34"


def test_reenrich_reports_unknown_placeholders_and_leaves_them():
    result = reenrich("Ask [PERSON_09] and [PERSON_01]", {"[PERSON_01]": "Anna"})
    assert result.text == "Ask [PERSON_09] and Anna"
    assert result.unknown_placeholders == ["[PERSON_09]"]


def test_reenrich_does_not_reprocess_restored_values():
    vault = {"[PERSON_01]": "literal [EMAIL_01]", "[EMAIL_01]": "anna@x.org"}
    result = reenrich("[PERSON_01]", vault)
    assert result.text == "literal [EMAIL_01]"

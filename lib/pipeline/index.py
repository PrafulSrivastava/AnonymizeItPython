"""
Pipeline Orchestrator: Coordinates all pipeline stages.
Main entry point for message processing.
"""

import hashlib
from lib.types import PipelineInput, ProcessedMessage
from lib.pipeline.regex_stripper import regex_stripper
from lib.pipeline.ner_engine import ner_engine
from lib.pipeline.blocklist import blocklist_matcher
from lib.pipeline.confidence_scorer import confidence_scorer
from lib.pipeline.validator import validator


def run_pipeline(input_data: PipelineInput) -> ProcessedMessage:
    """
    Main pipeline orchestration function.
    Executes all 5 stages in sequence and returns ProcessedMessage.

    Pipeline flow:
    1. Regex Stripper - Extract structural PII (phone, email, etc.)
    2. NER Engine - Extract entities (names, orgs, locations)
    3. Blocklist - Match custom blocklist terms and detect QIs
    4. Confidence Scorer - Calculate confidence and routing decision
    5. Validator - Validate output and check for PII leakage

    Args:
        input_data: PipelineInput with rawText, blocklist, sessionId

    Returns:
        ProcessedMessage with cleaned text, tokens, and confidence scores
    """
    # Generate message ID (SHA-256 hash of text + sessionId)
    message_id = hashlib.sha256(
        f"{input_data.rawText}{input_data.sessionId}".encode()
    ).hexdigest()

    # Stage 01: Regex Stripper
    text, regex_tokens = regex_stripper.process(input_data.rawText)

    # Extract sender name for NER processing (if present)
    sender_name = ""
    sender_token = next((t for t in regex_tokens if t.type == "SENDER"), None)
    if sender_token and sender_token.original:
        sender_name = sender_token.original

    # Stage 02: NER Engine (also check sender name for PERSON entity)
    text, ner_tokens = ner_engine.process(text, sender_name=sender_name)
    all_tokens = regex_tokens + ner_tokens

    # Stage 03: Blocklist Matcher
    blocklist_terms = [
        term.strip()
        for term in input_data.blocklist.split(',')
        if term.strip()
    ]
    text, blocklist_tokens, qi_risk, qi_count = blocklist_matcher.process(
        text,
        blocklist_terms,
        all_tokens
    )
    all_tokens.extend(blocklist_tokens)

    # Stage 04: Confidence Scorer
    confidence = confidence_scorer.calculate(
        tokens=all_tokens,
        qi_count=qi_count,
        qi_risk=qi_risk,
        original_text=input_data.rawText,
        cleaned_text=text
    )

    # Add QI risk to confidence flags
    if qi_risk:
        if not confidence.failureReasons:
            confidence.failureReasons = []
        if "High quasi-identifier density detected" not in confidence.failureReasons:
            confidence.failureReasons.append("High quasi-identifier density detected")

    # Stage 05: Validator
    result = validator.validate(
        cleaned_text=text,
        tokens=all_tokens,
        confidence=confidence,
        message_id=message_id,
        original_text=input_data.rawText
    )

    # Add quasi-identifier risk flag to result
    result.flags["quasi_identifier_risk"] = qi_risk
    result.flags["quasi_identifier_count"] = qi_count

    return result

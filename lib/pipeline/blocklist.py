"""
Pipeline Stage 03: Blocklist matching using Aho-Corasick automaton.
Handles custom blocklist terms and quasi-identifier detection.
"""

import re
from typing import Tuple, List, Dict
import ahocorasick
from lib.types import RedactionToken


# Role keywords for quasi-identifier detection
ROLE_KEYWORDS = {
    "manager", "developer", "designer", "founder", "engineer",
    "director", "analyst", "consultant", "cto", "ceo", "cpo",
    "vp", "lead", "head of", "freelance", "contractor", "intern",
    "student", "teacher", "doctor"
}


class BlocklistMatcher:
    """Blocklist-based PII detector with quasi-identifier risk assessment."""

    def __init__(self):
        """Initialize token counter."""
        self.counter = 0

    def reset_counter(self):
        """Reset token counter for new message."""
        self.counter = 0

    def get_next_token(self) -> str:
        """Get next blocklist token with incremented counter."""
        self.counter += 1
        return f"[BLOCKLIST_{self.counter:02d}]"

    def build_automaton(self, terms: List[str]) -> ahocorasick.Automaton:
        """
        Build Aho-Corasick automaton for efficient multi-pattern matching.
        Case-insensitive matching.
        """
        A = ahocorasick.Automaton()

        for idx, term in enumerate(terms):
            if term:  # Skip empty terms
                A.add_word(term.lower(), (idx, term))

        A.make_automaton()
        return A

    def is_word_boundary(self, text: str, start: int, end: int) -> bool:
        """
        Check if match is at word boundaries (no alphanumeric characters adjacent).
        """
        # Check character before start
        if start > 0:
            if text[start - 1].isalnum():
                return False

        # Check character after end
        if end < len(text):
            if text[end].isalnum():
                return False

        return True

    def match_blocklist(self, text: str, terms: List[str]) -> Tuple[str, List[RedactionToken]]:
        """
        Match blocklist terms in text using Aho-Corasick automaton.
        Case-insensitive, whole-word matching.
        """
        if not terms:
            return text, []

        self.reset_counter()
        tokens = []

        # Build automaton
        automaton = self.build_automaton(terms)

        # Find all matches
        matches = []
        for end_idx, (idx, original_term) in automaton.iter(text.lower()):
            start_idx = end_idx - len(original_term) + 1

            # Validate word boundaries
            if self.is_word_boundary(text, start_idx, end_idx + 1):
                matches.append({
                    "start": start_idx,
                    "end": end_idx + 1,
                    "text": text[start_idx:end_idx + 1]
                })

        # Remove overlapping matches (keep first match)
        matches.sort(key=lambda m: m["start"])
        filtered_matches = []
        last_end = -1

        for match in matches:
            if match["start"] >= last_end:
                filtered_matches.append(match)
                last_end = match["end"]

        # Create tokens and redact text (in reverse order)
        for match in reversed(filtered_matches):
            token_value = self.get_next_token()
            token = RedactionToken(
                type="BLOCKLIST",
                value=token_value,
                original=match["text"],
                startIndex=match["start"],
                endIndex=match["end"],
                confidence=1.0
            )
            tokens.append(token)

            # Redact in text
            text = text[:match["start"]] + token_value + text[match["end"]:]

        # Reverse tokens list to maintain original order
        tokens.reverse()

        return text, tokens

    def detect_quasi_identifiers(self, text: str, existing_tokens: List[RedactionToken]) -> Tuple[bool, int]:
        """
        Detect quasi-identifiers in text and existing tokens.
        Risk requires COMBINATION of different types: role + (age OR location)
        or age + location. Multiple AGE tokens alone don't trigger risk.

        Returns: (risk_flag, count)
        """
        # Track different QI categories separately
        has_role = False
        has_age = False
        has_location = False
        qi_count = 0

        # Check for role keywords in remaining text
        text_lower = text.lower()
        for role in ROLE_KEYWORDS:
            pattern = r'\b' + re.escape(role) + r'\b'
            if re.search(pattern, text_lower):
                has_role = True
                qi_count += 1
                break  # Count roles once

        # Check for AGE tokens in existing tokens
        age_tokens = [t for t in existing_tokens if t.type == "AGE"]
        if age_tokens:
            has_age = True
            qi_count += 1  # Count age once, not per token

        # Check for LOCATION tokens (cities that were redacted)
        location_tokens = [t for t in existing_tokens if t.type == "LOCATION"]
        if location_tokens:
            has_location = True
            qi_count += 1

        # Also check for country names in text (countries pass through)
        from lib.pipeline.ner_engine import COUNTRIES
        for country in COUNTRIES:
            pattern = r'\b' + re.escape(country) + r'\b'
            if re.search(pattern, text_lower, re.IGNORECASE):
                has_location = True
                if not location_tokens:  # Don't double count
                    qi_count += 1
                break

        # Risk requires COMBINATION: role+age, role+location, or age+location
        # Multiple ages alone (like family ages) don't trigger risk
        risk_flag = (has_role and has_age) or (has_role and has_location) or (has_age and has_location)

        return risk_flag, qi_count

    def override_with_blocklist(
        self,
        existing_tokens: List[RedactionToken],
        blocklist_terms: List[str]
    ) -> List[RedactionToken]:
        """
        Override existing tokens with BLOCKLIST type if their original text
        matches any blocklist term. This ensures blocklist takes priority over NER.

        IMPORTANT: Does NOT override SENDER tokens (meta-information about message structure).

        Args:
            existing_tokens: Tokens from previous pipeline stages
            blocklist_terms: List of blocklist terms to check

        Returns:
            Modified list of tokens with BLOCKLIST overrides
        """
        if not blocklist_terms:
            return existing_tokens

        # Normalize blocklist terms for comparison (case-insensitive)
        blocklist_lower = [term.lower() for term in blocklist_terms]

        # Check each existing token
        for token in existing_tokens:
            # SKIP SENDER tokens - they represent message structure, not content
            if token.type == "SENDER":
                continue

            # Check if token's original text matches any blocklist term
            if token.original and token.original.lower() in blocklist_lower:
                # Override type to BLOCKLIST
                token.type = "BLOCKLIST"
                # Update value to use BLOCKLIST format
                # Keep the existing number if it has one, otherwise use generic
                if '_' in token.value and token.value.count('_') == 1:
                    # Extract number from existing token (e.g., [PERSON_01] -> 01)
                    try:
                        num = token.value.split('_')[1].rstrip(']')
                        token.value = f"[BLOCKLIST_{num}]"
                    except:
                        token.value = f"[BLOCKLIST_01]"
                else:
                    token.value = f"[BLOCKLIST_01]"

        return existing_tokens

    def process(
        self,
        text: str,
        blocklist_terms: List[str],
        existing_tokens: List[RedactionToken]
    ) -> Tuple[str, List[RedactionToken], bool, int]:
        """
        Main blocklist processing function.
        1. Override existing tokens that match blocklist (priority)
        2. Match remaining blocklist terms in text
        3. Detect quasi-identifiers
        4. Return cleaned text, tokens, risk flag, and QI count
        """
        # Step 1: Override existing tokens with blocklist matches
        existing_tokens = self.override_with_blocklist(existing_tokens, blocklist_terms)

        # Step 2: Match blocklist in remaining text
        text, blocklist_tokens = self.match_blocklist(text, blocklist_terms)

        # Step 3: Detect quasi-identifiers
        qi_risk, qi_count = self.detect_quasi_identifiers(text, existing_tokens)

        return text, blocklist_tokens, qi_risk, qi_count


# Module-level instance for use in pipeline
blocklist_matcher = BlocklistMatcher()

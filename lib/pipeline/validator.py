"""
Pipeline Stage 05: Output validation.
Performs three validation checks: regex re-run, token integrity, and content check.
"""

import re
from typing import List
from lib.types import RedactionToken, ConfidenceScore, ProcessedMessage


class Validator:
    """Output validator with multiple validation checks."""

    def rerun_regex_suite(self, cleaned_text: str) -> tuple[bool, str]:
        """
        Re-run regex patterns on cleaned text to detect PII leakage.
        Returns: (is_valid, error_message)
        """
        # Email pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        if re.search(email_pattern, cleaned_text):
            return False, "Email pattern detected in cleaned text"

        # Phone pattern (basic)
        phone_pattern = r'\+?\d[\d\s\-\(\)]{7,}\d'
        if re.search(phone_pattern, cleaned_text):
            return False, "Phone number pattern detected in cleaned text"

        # URL pattern
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        if re.search(url_pattern, cleaned_text):
            return False, "URL pattern detected in cleaned text"

        # IBAN pattern
        iban_pattern = r'\b[A-Z]{2}[0-9]{2}[A-Z0-9]{15,30}\b'
        if re.search(iban_pattern, cleaned_text):
            return False, "IBAN pattern detected in cleaned text"

        # Handle pattern
        handle_pattern = r'@[A-Za-z0-9_]{3,}'
        if re.search(handle_pattern, cleaned_text):
            return False, "Social handle pattern detected in cleaned text"

        # Date of birth patterns
        dob_pattern = r'\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b'
        if re.search(dob_pattern, cleaned_text):
            # Check if it's not already a token
            if not re.search(r'\[DOB_\d+\]', cleaned_text):
                return False, "Date pattern detected in cleaned text"

        # ISO date pattern (YYYY-MM-DD)
        iso_date_pattern = r'\b\d{4}-\d{2}-\d{2}\b'
        if re.search(iso_date_pattern, cleaned_text):
            if not re.search(r'\[DOB_\d+\]', cleaned_text):
                return False, "ISO date pattern detected in cleaned text"

        # IPv4 address pattern
        ip_pattern = r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'
        if re.search(ip_pattern, cleaned_text):
            return False, "IP address detected in cleaned text"

        # VIN pattern (17 alphanumeric chars excluding I, O, Q)
        vin_pattern = r'\b[A-HJ-NPR-Z0-9]{17}\b'
        vin_match = re.search(vin_pattern, cleaned_text)
        if vin_match:
            vin_text = vin_match.group(0)
            if any(c.isalpha() for c in vin_text) and any(c.isdigit() for c in vin_text):
                return False, "VIN pattern detected in cleaned text"

        return True, ""

    def check_token_integrity(self, cleaned_text: str) -> tuple[bool, str]:
        """
        Validate that all tokens match expected format: [TYPE_NN] or [AGE_NNs]
        Returns: (is_valid, error_message)
        """
        # Find all tokens in cleaned text
        token_pattern = r'\[([^\]]+)\]'
        tokens = re.findall(token_pattern, cleaned_text)

        # Valid token pattern: UPPERCASE_LETTERS followed by optional _digits or _digitss
        valid_pattern = r'^[A-Z_]+(?:_\d+|_\d+s)?$'

        for token in tokens:
            if not re.match(valid_pattern, token):
                return False, f"Malformed token detected: [{token}]"

        return True, ""

    def check_minimum_content(self, original_text: str, cleaned_text: str) -> bool:
        """
        Check if >60% of words were redacted (low signal flag).
        Returns: low_signal flag
        """
        # Count words in original text
        original_words = [w for w in original_text.split() if w.strip()]

        # Count non-token words in cleaned text
        cleaned_words = [w for w in cleaned_text.split() if w.strip()]
        token_pattern = r'\[[A-Z_]+(?:_\d+|_\d+s)?\]'
        non_token_words = [w for w in cleaned_words if not re.match(token_pattern, w)]

        if not original_words:
            return False

        # Calculate percentage preserved
        preserved_ratio = len(non_token_words) / len(original_words)

        # Flag if <40% preserved (>60% redacted)
        low_signal = preserved_ratio < 0.4

        return low_signal

    def validate(
        self,
        cleaned_text: str,
        tokens: List[RedactionToken],
        confidence: ConfidenceScore,
        message_id: str,
        original_text: str
    ) -> ProcessedMessage:
        """
        Main validation function.
        Performs three validation checks and creates ProcessedMessage.
        """
        flags = {}
        additional_failure_reasons = []

        # Check 1: Re-run regex suite
        regex_valid, regex_error = self.rerun_regex_suite(cleaned_text)
        if not regex_valid:
            flags["pii_leakage_detected"] = True
            additional_failure_reasons.append(f"PII leakage: {regex_error}")
            # Force routing to review
            confidence.routing = "review"

        # Check 2: Token integrity
        token_valid, token_error = self.check_token_integrity(cleaned_text)
        if not token_valid:
            flags["malformed_tokens"] = True
            additional_failure_reasons.append(token_error)
            confidence.routing = "review"

        # Check 3: Minimum content check
        low_signal = self.check_minimum_content(original_text, cleaned_text)
        flags["low_signal"] = low_signal
        if low_signal:
            additional_failure_reasons.append("High redaction rate - minimal content preserved")

        # Add additional failure reasons to confidence object
        if additional_failure_reasons:
            confidence.failureReasons.extend(additional_failure_reasons)

        # Create ProcessedMessage
        result = ProcessedMessage(
            messageId=message_id,
            cleanedText=cleaned_text,
            tokens=tokens,
            confidence=confidence,
            flags=flags,
            metadata={
                "original_word_count": len(original_text.split()),
                "cleaned_word_count": len(cleaned_text.split()),
                "token_count": len(tokens)
            }
        )

        return result


# Module-level instance for use in pipeline
validator = Validator()

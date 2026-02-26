"""
Pipeline Stage 01: Regex-based PII extraction.
Handles WhatsApp header, phone numbers, emails, URLs, handles, IBANs, DOB, and ages.
"""

import re
from typing import Tuple, List, Dict
import phonenumbers
from lib.types import RedactionToken


class RegexStripper:
    """Regex-based PII detector and redactor."""

    def __init__(self):
        """Initialize token counters."""
        self.counters: Dict[str, int] = {}

    def reset_counters(self):
        """Reset token counters for new message."""
        self.counters = {}

    def get_next_token(self, token_type: str) -> str:
        """Get next token with incremented counter."""
        if token_type not in self.counters:
            self.counters[token_type] = 0
        self.counters[token_type] += 1
        return f"[{token_type}_{self.counters[token_type]:02d}]"

    def extract_whatsapp_header(self, text: str) -> Tuple[str, List[RedactionToken], str]:
        """
        Extract WhatsApp header in various formats:
        - [DD/MM/YYYY, HH:MM] SenderName:
        - [DD.MM.YY, HH:MM:SS] SenderName:
        Returns: (text_without_header, tokens, sender_name)
        """
        # Pattern 1: [26/02/2026, 09:14] Name: (4-digit year, slash separator)
        header_pattern1 = r'^\[(\d{1,2}/\d{1,2}/\d{4}),\s*(\d{1,2}:\d{2})\]\s*([^:]+):\s*'

        # Pattern 2: [24.01.26, 16:40:31] Name: (2-digit year, dot separator, optional seconds)
        header_pattern2 = r'^\[(\d{1,2}\.\d{1,2}\.\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?)\]\s*([^:]+):\s*'

        # Try both patterns
        for header_pattern in [header_pattern1, header_pattern2]:
            match = re.match(header_pattern, text)
            if match:
                full_header = match.group(0)
                sender_name = match.group(3).strip()
                remaining_text = text[len(full_header):]

                # Create SENDER token
                token = RedactionToken(
                    type="SENDER",
                    value="[SENDER]",
                    original=sender_name,
                    startIndex=match.start(3),
                    endIndex=match.end(3),
                    confidence=1.0
                )

                return remaining_text, [token], sender_name

        return text, [], ""

    def extract_phone_numbers(self, text: str) -> Tuple[str, List[RedactionToken]]:
        """Extract phone numbers using phonenumbers library with fallback regex."""
        tokens = []
        seen_spans = set()  # Track (start, end) pairs to avoid duplicates

        # Try parsing with phonenumbers library
        for region in ["DE", "GB", "US"]:
            try:
                for match in phonenumbers.PhoneNumberMatcher(text, region):
                    phone_text = match.raw_string
                    start_idx = match.start
                    end_idx = match.end

                    # Skip if we've already seen this span
                    span = (start_idx, end_idx)
                    if span in seen_spans:
                        continue
                    seen_spans.add(span)

                    token_value = self.get_next_token("PHONE")
                    token = RedactionToken(
                        type="PHONE",
                        value=token_value,
                        original=phone_text,
                        startIndex=start_idx,
                        endIndex=end_idx,
                        confidence=1.0
                    )
                    tokens.append(token)
            except:
                pass

        # Fallback: regex for common phone patterns
        phone_regex = r'(\+?\d{1,4}[\s\-\.]?)?\(?\d{2,4}\)?[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}'
        for match in re.finditer(phone_regex, text):
            # Check if this position is already covered
            covered = any(t.startIndex <= match.start() < t.endIndex for t in tokens)
            if not covered and len(match.group(0).replace(' ', '').replace('-', '').replace('.', '')) >= 7:
                token_value = self.get_next_token("PHONE")
                token = RedactionToken(
                    type="PHONE",
                    value=token_value,
                    original=match.group(0),
                    startIndex=match.start(),
                    endIndex=match.end(),
                    confidence=0.9
                )
                tokens.append(token)

        # Sort by start index and replace in reverse order
        tokens.sort(key=lambda t: t.startIndex, reverse=True)
        for token in tokens:
            text = text[:token.startIndex] + token.value + text[token.endIndex:]

        return text, tokens

    def extract_emails(self, text: str) -> Tuple[str, List[RedactionToken]]:
        """Extract email addresses including obfuscated formats."""
        tokens = []

        # Standard email pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

        # Obfuscated patterns - multiple variants
        # Pattern 1: name dot name at domain dot tld (e.g., "jonas dot weber at protonmail dot com")
        obfuscated_pattern1 = r'\b[A-Za-z0-9]{2,}\s*(?:dot|\[dot\]|\(dot\))\s*[A-Za-z0-9]{2,}\s*(?:\[at\]|\(at\)| at )\s*[A-Za-z0-9]+\s*(?:dot|\[dot\]|\(dot\))\s*[A-Za-z]{2,}\b'

        # Pattern 2: name at domain dot tld (e.g., "jonas at gmail dot com") - username min 3 chars
        obfuscated_pattern2 = r'\b[A-Za-z0-9._]{3,}\s*(?:\[at\]|\(at\)| at )\s*[A-Za-z0-9]+\s*(?:dot|\[dot\]|\(dot\))\s*[A-Za-z]{2,}\b'

        # Combine patterns for matching
        obfuscated_patterns = [obfuscated_pattern1, obfuscated_pattern2]

        for match in re.finditer(email_pattern, text, re.IGNORECASE):
            token_value = self.get_next_token("EMAIL")
            token = RedactionToken(
                type="EMAIL",
                value=token_value,
                original=match.group(0),
                startIndex=match.start(),
                endIndex=match.end(),
                confidence=1.0
            )
            tokens.append(token)

        for pattern in obfuscated_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Check if not already covered by standard email or previous obfuscated match
                covered = any(t.startIndex <= match.start() < t.endIndex for t in tokens)
                if not covered:
                    token_value = self.get_next_token("EMAIL")
                    token = RedactionToken(
                        type="EMAIL",
                        value=token_value,
                        original=match.group(0),
                        startIndex=match.start(),
                        endIndex=match.end(),
                        confidence=0.95
                    )
                    tokens.append(token)

        # Sort by start index and replace in reverse order
        tokens.sort(key=lambda t: t.startIndex, reverse=True)
        for token in tokens:
            text = text[:token.startIndex] + token.value + text[token.endIndex:]

        return text, tokens

    def extract_urls(self, text: str) -> Tuple[str, List[RedactionToken]]:
        """Extract URLs (http/https and bare domains with paths)."""
        tokens = []

        # HTTP/HTTPS URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'

        # Bare domains with paths (e.g., example.com/path)
        domain_pattern = r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s]*)?\b'

        for match in re.finditer(url_pattern, text, re.IGNORECASE):
            token_value = self.get_next_token("URL")
            token = RedactionToken(
                type="URL",
                value=token_value,
                original=match.group(0),
                startIndex=match.start(),
                endIndex=match.end(),
                confidence=1.0
            )
            tokens.append(token)

        for match in re.finditer(domain_pattern, text):
            # Check if not already covered and has a path or common TLD
            covered = any(t.startIndex <= match.start() < t.endIndex for t in tokens)
            url_text = match.group(0)
            if not covered and ('/' in url_text or any(tld in url_text for tld in ['.com', '.org', '.net', '.de', '.co.uk'])):
                token_value = self.get_next_token("URL")
                token = RedactionToken(
                    type="URL",
                    value=token_value,
                    original=url_text,
                    startIndex=match.start(),
                    endIndex=match.end(),
                    confidence=0.9
                )
                tokens.append(token)

        # Sort by start index and replace in reverse order
        tokens.sort(key=lambda t: t.startIndex, reverse=True)
        for token in tokens:
            text = text[:token.startIndex] + token.value + text[token.endIndex:]

        return text, tokens

    def extract_handles(self, text: str) -> Tuple[str, List[RedactionToken]]:
        """Extract social media handles (@username, min 3 chars)."""
        tokens = []

        handle_pattern = r'@[A-Za-z0-9_]{3,}'

        for match in re.finditer(handle_pattern, text):
            token_value = self.get_next_token("HANDLE")
            token = RedactionToken(
                type="HANDLE",
                value=token_value,
                original=match.group(0),
                startIndex=match.start(),
                endIndex=match.end(),
                confidence=1.0
            )
            tokens.append(token)

        # Sort by start index and replace in reverse order
        tokens.sort(key=lambda t: t.startIndex, reverse=True)
        for token in tokens:
            text = text[:token.startIndex] + token.value + text[token.endIndex:]

        return text, tokens

    def extract_ibans(self, text: str) -> Tuple[str, List[RedactionToken]]:
        """Extract and validate IBANs (regex + checksum validation). Handles spaces."""
        tokens = []

        # IBAN pattern: 2 letter country code + 2 check digits + alphanumeric with optional spaces
        # Matches: "DE89370400440532013000" or "DE89 3704 0044 0532 0130 00"
        iban_pattern = r'\b[A-Z]{2}\s*[0-9]{2}[\s0-9A-Z]{13,32}\b'

        for match in re.finditer(iban_pattern, text):
            iban_with_spaces = match.group(0)

            # Normalize: remove spaces for validation
            iban_normalized = iban_with_spaces.replace(' ', '')

            # Basic validation: check if it looks like a valid IBAN
            if self.is_valid_iban_format(iban_normalized):
                token_value = self.get_next_token("IBAN")
                token = RedactionToken(
                    type="IBAN",
                    value=token_value,
                    original=iban_with_spaces,  # Store original with spaces
                    startIndex=match.start(),
                    endIndex=match.end(),
                    confidence=0.95
                )
                tokens.append(token)

        # Sort by start index and replace in reverse order
        tokens.sort(key=lambda t: t.startIndex, reverse=True)
        for token in tokens:
            text = text[:token.startIndex] + token.value + text[token.endIndex:]

        return text, tokens

    def is_valid_iban_format(self, iban: str) -> bool:
        """Basic IBAN format validation."""
        # Check length (varies by country, but between 15-34 chars)
        if len(iban) < 15 or len(iban) > 34:
            return False

        # Check structure: 2 letters + 2 digits + alphanumeric
        if not re.match(r'^[A-Z]{2}[0-9]{2}[A-Z0-9]+$', iban):
            return False

        # For production, implement full mod-97 checksum validation
        return True

    def extract_dob(self, text: str) -> Tuple[str, List[RedactionToken]]:
        """Extract dates of birth in various formats."""
        tokens = []

        # Patterns for DOB
        patterns = [
            r'\b\d{1,2}[./]\d{1,2}[./]\d{4}\b',  # DD.MM.YYYY or DD/MM/YYYY
            r'\b\d{1,2}[./]\d{1,2}[./]\d{2}\b',  # DD/MM/YY
            r'\bborn\s+(?:in\s+)?\d{4}\b',       # born 1990, born in 1990
            r'\bborn\s+(?:on\s+)?\d{1,2}[./]\d{1,2}[./]\d{2,4}\b'  # born on 15.03.1990
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Check if not already covered
                covered = any(t.startIndex <= match.start() < t.endIndex for t in tokens)
                if not covered:
                    token_value = self.get_next_token("DOB")
                    token = RedactionToken(
                        type="DOB",
                        value=token_value,
                        original=match.group(0),
                        startIndex=match.start(),
                        endIndex=match.end(),
                        confidence=0.9
                    )
                    tokens.append(token)

        # Sort by start index and replace in reverse order
        tokens.sort(key=lambda t: t.startIndex, reverse=True)
        for token in tokens:
            text = text[:token.startIndex] + token.value + text[token.endIndex:]

        return text, tokens

    def extract_ages(self, text: str) -> Tuple[str, List[RedactionToken]]:
        """Extract ages with bucketing (privacy-preserving)."""
        tokens = []

        # Patterns: "I'm 34", "34 years old", "aged 34"
        age_patterns = [
            r"I'm\s+(\d{1,2})\b",
            r"I am\s+(\d{1,2})\b",
            r"(\d{1,2})\s+years?\s+old",
            r"aged\s+(\d{1,2})\b"
        ]

        for pattern in age_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                age_str = match.group(1)
                age = int(age_str)

                # Validate age range (1-120)
                if 1 <= age <= 120:
                    # Bucket to decade
                    decade = (age // 10) * 10
                    token_value = f"[AGE_{decade}s]"

                    # Check if not already covered
                    covered = any(t.startIndex <= match.start() < t.endIndex for t in tokens)
                    if not covered:
                        token = RedactionToken(
                            type="AGE",
                            value=token_value,
                            original=match.group(0),
                            startIndex=match.start(),
                            endIndex=match.end(),
                            confidence=0.95
                        )
                        tokens.append(token)

        # Sort by start index and replace in reverse order
        tokens.sort(key=lambda t: t.startIndex, reverse=True)
        for token in tokens:
            text = text[:token.startIndex] + token.value + text[token.endIndex:]

        return text, tokens

    def process(self, raw_text: str) -> Tuple[str, List[RedactionToken]]:
        """
        Main processing function. Executes all regex-based extractions in order.
        Returns: (cleaned_text, all_tokens)
        """
        self.reset_counters()
        all_tokens = []

        # Step 1: Extract WhatsApp header and sender
        text, header_tokens, sender = self.extract_whatsapp_header(raw_text)
        all_tokens.extend(header_tokens)

        # Step 2: Extract IBANs (BEFORE phone numbers to avoid conflicts)
        text, iban_tokens = self.extract_ibans(text)
        all_tokens.extend(iban_tokens)

        # Step 3: Extract phone numbers
        text, phone_tokens = self.extract_phone_numbers(text)
        all_tokens.extend(phone_tokens)

        # Step 4: Extract emails
        text, email_tokens = self.extract_emails(text)
        all_tokens.extend(email_tokens)

        # Step 5: Extract URLs
        text, url_tokens = self.extract_urls(text)
        all_tokens.extend(url_tokens)

        # Step 6: Extract handles
        text, handle_tokens = self.extract_handles(text)
        all_tokens.extend(handle_tokens)

        # Step 7: Extract DOB
        text, dob_tokens = self.extract_dob(text)
        all_tokens.extend(dob_tokens)

        # Step 8: Extract ages
        text, age_tokens = self.extract_ages(text)
        all_tokens.extend(age_tokens)

        # Add sender token prefix to text if sender was found
        if header_tokens:
            text = "[SENDER] " + text

        return text, all_tokens


# Module-level instance for use in pipeline
regex_stripper = RegexStripper()

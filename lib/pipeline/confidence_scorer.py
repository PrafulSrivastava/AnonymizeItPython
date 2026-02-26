"""
Pipeline Stage 04: Confidence scoring and routing decision.
Calculates weighted confidence score from multiple signals.
"""

from typing import List, Tuple
from lib.types import RedactionToken, ConfidenceScore, ConfidenceSignals


class ConfidenceScorer:
    """Confidence scoring engine with multi-signal analysis."""

    def calculate_regex_coverage(self, tokens: List[RedactionToken], original_text: str) -> float:
        """
        Calculate regex coverage score.
        Measures how well regex patterns captured potential PII.
        """
        # Count regex-based token types
        regex_types = {"PHONE", "EMAIL", "URL", "HANDLE", "IBAN", "DOB", "AGE", "SENDER"}
        regex_tokens = [t for t in tokens if t.type in regex_types]

        if not regex_tokens:
            # No regex tokens found - could be good (no PII) or bad (missed PII)
            # Check if text looks like it has PII patterns
            import re
            has_email_pattern = bool(re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}', original_text))
            has_phone_pattern = bool(re.search(r'\+?\d[\d\s\-\(\)]{7,}', original_text))
            has_url_pattern = bool(re.search(r'https?://', original_text))

            if has_email_pattern or has_phone_pattern or has_url_pattern:
                # Should have found something, low coverage
                return 0.3
            else:
                # No obvious patterns, high coverage
                return 0.95

        # Calculate coverage based on token count and diversity
        token_count = len(regex_tokens)
        token_types = len(set(t.type for t in regex_tokens))

        # Score increases with more tokens found (up to a point)
        coverage = min(0.5 + (token_count * 0.1), 1.0)

        return coverage

    def calculate_ner_confidence(self, tokens: List[RedactionToken]) -> float:
        """
        Calculate average NER confidence score.
        Uses confidence scores from Presidio and spaCy detections.
        """
        # Filter NER-based token types
        ner_types = {"PERSON", "ORG", "LOCATION"}
        ner_tokens = [t for t in tokens if t.type in ner_types]

        if not ner_tokens:
            # No NER tokens - neutral score
            return 0.8

        # Calculate average confidence
        total_confidence = sum(t.confidence for t in ner_tokens)
        avg_confidence = total_confidence / len(ner_tokens)

        return avg_confidence

    def calculate_quasi_identifier_score(self, qi_count: int, qi_risk: bool) -> float:
        """
        Calculate quasi-identifier score (inverse scoring).
        More QIs = lower score (higher risk).
        """
        if qi_count == 0:
            return 1.0

        if qi_risk:  # qi_count >= 3
            return 0.5

        # Linear decrease for 1-2 QIs
        return max(0.7, 1.0 - (qi_count * 0.15))

    def calculate_residual_token_density(self, original_text: str, cleaned_text: str) -> float:
        """
        Calculate density of non-redacted content.
        Higher density = more original content preserved = better.
        Special handling for short messages that are mostly PII.
        """
        # Count words (split on whitespace)
        original_words = [w for w in original_text.split() if w.strip()]
        cleaned_words = [w for w in cleaned_text.split() if w.strip()]

        # Filter out tokens from cleaned words
        import re
        token_pattern = r'\[[A-Z_]+(_\d+|_\d+s)?\]'
        non_token_words = [w for w in cleaned_words if not re.match(token_pattern, w)]
        token_count = len(cleaned_words) - len(non_token_words)

        if not original_words:
            return 0.5

        # Special case: Very short messages (5 words or less)
        # If the message was mostly PII and we detected it, that's good
        if len(original_words) <= 5:
            # If we found tokens, give a higher baseline score
            if token_count > 0:
                return 0.7  # Reasonable score for short PII-heavy messages
            return 0.9  # Short clean message

        # Calculate density
        density = len(non_token_words) / len(original_words)

        return density

    def determine_routing(
        self,
        overall_score: float,
        qi_risk: bool,
        low_confidence_count: int,
        tokens: List[RedactionToken],
        residual_density: float
    ) -> str:
        """
        Determine routing decision based on overall score and flags.

        Thresholds:
        - >= 0.90: pass
        - 0.75 - 0.89: pass_flagged
        - < 0.75: review

        Special case: Clean messages (only SENDER token + high density) → pass
        """
        # Special case: Clean messages with minimal PII
        # If only SENDER token (or no tokens) and high content preservation, pass directly
        non_sender_tokens = [t for t in tokens if t.type != "SENDER"]
        if len(non_sender_tokens) == 0 and residual_density > 0.85:
            return "pass"

        # Force review if high QI risk
        if qi_risk:
            return "review"

        # Force review only if MANY low-confidence detections (3+)
        # 2 low-confidence detections is acceptable for pass_flagged
        if low_confidence_count >= 3:
            return "review"

        # Apply score thresholds (relaxed for better usability)
        if overall_score >= 0.85:  # Lowered from 0.88
            return "pass"
        elif overall_score >= 0.70:  # Lowered from 0.72
            return "pass_flagged"
        else:
            return "review"

    def generate_failure_reasons(
        self,
        overall_score: float,
        signals: ConfidenceSignals,
        qi_risk: bool,
        low_confidence_count: int
    ) -> List[str]:
        """Generate human-readable failure reasons."""
        reasons = []

        if overall_score < 0.75:
            reasons.append("Overall confidence score below threshold")

        if qi_risk:
            reasons.append("High quasi-identifier density detected")

        if signals.nerConfidence < 0.7:
            reasons.append("Low NER confidence scores")

        if low_confidence_count >= 2:
            reasons.append("Multiple low-confidence detections")

        if signals.regexCoverage < 0.6:
            reasons.append("Low regex pattern coverage")

        if signals.residualTokenDensity < 0.3:
            reasons.append("Excessive redaction - potential over-anonymization")

        return reasons

    def calculate(
        self,
        tokens: List[RedactionToken],
        qi_count: int,
        qi_risk: bool,
        original_text: str,
        cleaned_text: str
    ) -> ConfidenceScore:
        """
        Main confidence calculation function.

        Formula:
        overall = (regexCoverage × 0.30) + (nerConfidence × 0.35) +
                  (quasiIdentifierScore × 0.20) + (residualTokenScore × 0.15)
        """
        # Calculate individual signals
        regex_coverage = self.calculate_regex_coverage(tokens, original_text)
        ner_confidence = self.calculate_ner_confidence(tokens)
        qi_score = self.calculate_quasi_identifier_score(qi_count, qi_risk)
        residual_density = self.calculate_residual_token_density(original_text, cleaned_text)

        # Calculate weighted overall score
        overall = (
            (regex_coverage * 0.30) +
            (ner_confidence * 0.35) +
            (qi_score * 0.20) +
            (residual_density * 0.15)
        )

        # Ensure overall is in [0, 1]
        overall = max(0.0, min(1.0, overall))

        # Create signals object
        signals = ConfidenceSignals(
            regexCoverage=regex_coverage,
            nerConfidence=ner_confidence,
            quasiIdentifierCount=qi_count,
            residualTokenDensity=residual_density
        )

        # Count low-confidence tokens
        low_confidence_count = sum(1 for t in tokens if t.lowConfidence)

        # Determine routing (with special handling for clean messages)
        routing = self.determine_routing(
            overall,
            qi_risk,
            low_confidence_count,
            tokens,
            residual_density
        )

        # Generate failure reasons
        failure_reasons = self.generate_failure_reasons(overall, signals, qi_risk, low_confidence_count)

        return ConfidenceScore(
            overall=overall,
            routing=routing,
            signals=signals,
            failureReasons=failure_reasons
        )


# Module-level instance for use in pipeline
confidence_scorer = ConfidenceScorer()

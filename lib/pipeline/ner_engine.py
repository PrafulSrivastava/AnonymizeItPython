"""
Pipeline Stage 02: NER Engine using spaCy + Microsoft Presidio.
Handles multilingual NER (English + German) with confidence scoring.
"""

import re
from typing import Tuple, List, Dict, Set
import spacy
from presidio_analyzer import AnalyzerEngine
from lib.types import RedactionToken

# Module-level model initialization (runs once per container)
# This is critical for Vercel serverless performance
try:
    nlp_en = spacy.load("en_core_web_lg")
    nlp_de = spacy.load("de_core_news_lg")
    analyzer = AnalyzerEngine()
    MODELS_LOADED = True
except Exception as e:
    print(f"Warning: Failed to load NER models: {e}")
    nlp_en = None
    nlp_de = None
    analyzer = None
    MODELS_LOADED = False


# Country list for location granularity filtering
COUNTRIES = {
    "germany", "united kingdom", "united states", "france", "spain", "italy",
    "canada", "australia", "japan", "china", "india", "brazil", "mexico",
    "russia", "south africa", "argentina", "netherlands", "belgium", "sweden",
    "norway", "denmark", "finland", "poland", "austria", "switzerland",
    "portugal", "greece", "czech republic", "hungary", "romania", "ukraine",
    "turkey", "egypt", "nigeria", "kenya", "thailand", "vietnam", "indonesia",
    "philippines", "singapore", "malaysia", "new zealand", "ireland", "scotland",
    "wales", "england", "iceland", "croatia", "serbia", "bulgaria"
}

# Tech terms whitelist - common product names that should NOT be redacted
TECH_TERMS = {
    # Operating Systems
    "android", "ios", "windows", "linux", "macos", "ubuntu",
    # Devices
    "iphone", "ipad", "macbook", "chromebook", "pixel",
    # Browsers
    "chrome", "firefox", "safari", "edge", "opera",
    # Platforms/Services
    "google", "facebook", "twitter", "instagram", "linkedin", "github",
    "youtube", "netflix", "spotify", "zoom", "slack", "teams",
    # Programming/Tech
    "javascript", "python", "java", "react", "vue", "angular",
    "docker", "kubernetes", "aws", "azure", "api", "sdk",
    # Generic tech terms
    "app", "application", "website", "platform", "software", "hardware",
    # Common false positives (words that NER mistakes for organizations)
    "dark", "light", "new", "old", "love", "user", "admin", "guest",
    # Adjectives and common words (not entities)
    "german", "english", "french", "spanish", "italian", "japanese",
    "american", "british", "european", "asian", "african",
    # Common German words that are NOT entities
    "gruppe", "das", "der", "die", "ist", "nicht", "und", "aber",
    "format", "system", "feature", "update", "version"
}


class NEREngine:
    """NER-based PII detector using spaCy and Presidio."""

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

    def is_german(self, text: str) -> bool:
        """
        Detect if text contains German language.
        Uses umlaut detection and common German word matching.
        """
        # Check for umlauts
        if re.search(r'[äöüßÄÖÜ]', text):
            return True

        # Check for common German words
        german_words = ["das", "der", "die", "ist", "nicht", "und", "aber", "von", "mit", "für"]
        words = text.lower().split()
        german_count = sum(1 for w in words if w in german_words)

        return german_count >= 2

    def is_german_text_or_names(self, text: str) -> bool:
        """
        Enhanced German detection: checks for German text OR German names.
        Returns True if German NER should be run.
        """
        # Check for umlauts (strong indicator)
        if re.search(r'[äöüßÄÖÜ]', text):
            return True

        # Check for common German words
        german_words = ["das", "der", "die", "ist", "nicht", "und", "aber", "von", "mit", "für", "auch", "wie", "auf"]
        words_lower = text.lower().split()
        german_word_count = sum(1 for w in words_lower if w in german_words)
        if german_word_count >= 2:
            return True

        # Check for common German surnames (weak indicator, use cautiously)
        german_surnames = [
            "müller", "schmidt", "schneider", "fischer", "weber", "meyer", "wagner",
            "becker", "schulz", "hoffman", "schäfer", "koch", "bauer", "klein",
            "wolf", "schröder", "neumann", "zimmermann"
        ]
        # Only trigger if we find a German surname that's capitalized (likely a name)
        words = text.split()
        for word in words:
            # Check if word is capitalized and matches a German surname
            if word and word[0].isupper():
                if word.lower() in german_surnames:
                    return True

        return False

    def is_country(self, location_text: str) -> bool:
        """Check if location text is a country name."""
        return location_text.lower() in COUNTRIES

    def is_tech_term(self, text: str) -> bool:
        """Check if text is a common tech term that should not be redacted."""
        return text.lower() in TECH_TERMS

    def run_presidio(self, text: str) -> List[Dict]:
        """
        Run Presidio analyzer on text.
        Returns list of detected entities with type, text, start, end, score.
        """
        if not MODELS_LOADED or analyzer is None:
            return []

        try:
            results = analyzer.analyze(
                text=text,
                language='en',
                entities=[
                    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
                    "LOCATION", "ORGANIZATION"
                ]
            )

            entities = []
            for result in results:
                entity = {
                    "type": result.entity_type,
                    "text": text[result.start:result.end],
                    "start": result.start,
                    "end": result.end,
                    "score": result.score
                }
                entities.append(entity)

            return entities
        except Exception as e:
            print(f"Presidio analysis error: {e}")
            return []

    def run_spacy(self, text: str, language: str = "en") -> List[Dict]:
        """
        Run spaCy NER on text.
        Returns list of detected entities with type, text, start, end, score.
        """
        if not MODELS_LOADED:
            return []

        nlp = nlp_en if language == "en" else nlp_de
        if nlp is None:
            return []

        try:
            doc = nlp(text)
            entities = []

            for ent in doc.ents:
                # Map spaCy labels to our types
                entity_type = self.map_spacy_label(ent.label_)
                if entity_type:
                    entity = {
                        "type": entity_type,
                        "text": ent.text,
                        "start": ent.start_char,
                        "end": ent.end_char,
                        "score": 0.85  # Default confidence for spaCy
                    }
                    entities.append(entity)

            return entities
        except Exception as e:
            print(f"spaCy analysis error: {e}")
            return []

    def map_spacy_label(self, label: str) -> str:
        """Map spaCy entity labels to our token types."""
        label_map = {
            "PERSON": "PERSON",
            "PER": "PERSON",
            "ORG": "ORG",
            "ORGANIZATION": "ORG",
            "GPE": "LOCATION",  # Geo-political entity
            "LOC": "LOCATION",
            "LOCATION": "LOCATION"
        }
        return label_map.get(label, None)

    def merge_entities(self, presidio_entities: List[Dict], spacy_entities: List[Dict]) -> List[Dict]:
        """
        Merge entities from Presidio and spaCy, preferring Presidio for overlaps.
        Returns unified list of entities.
        """
        merged = []

        # Add all Presidio entities first (higher precision)
        merged.extend(presidio_entities)

        # Add spaCy entities that don't overlap with Presidio
        for spacy_ent in spacy_entities:
            overlaps = False
            for presidio_ent in presidio_entities:
                # Check for overlap
                if not (spacy_ent["end"] <= presidio_ent["start"] or
                        spacy_ent["start"] >= presidio_ent["end"]):
                    overlaps = True
                    break

            if not overlaps:
                merged.append(spacy_ent)

        return merged

    def filter_locations(self, entities: List[Dict]) -> List[Dict]:
        """
        Apply filtering rules:
        1. Location granularity: countries pass through, cities redacted
        2. Tech terms: common product names pass through (Android, iOS, etc.)
        3. Low-confidence detections: filter out likely false positives
        4. Common English words: filter out obvious mistakes
        """
        # Common English words that should never be detected as entities
        common_words = {
            "hi", "hey", "hello", "everyone", "just", "joined", "love", "new",
            "the", "and", "but", "can", "will", "should", "could", "would",
            "signed", "up", "dark", "light", "mode", "update", "feature"
        }

        filtered = []

        for entity in entities:
            entity_text_lower = entity["text"].lower().strip()

            # Filter 0: Skip entities that contain brackets or are part of tokens
            if '[' in entity["text"] or ']' in entity["text"]:
                continue

            # Check for token-like patterns in entity text (our own tokens being re-detected)
            entity_text = entity["text"]
            if any(entity_text.startswith(prefix) for prefix in [
                "AGE_", "DOB_", "PHONE_", "EMAIL_", "PERSON_", "LOCATION_",
                "SENDER", "HANDLE_", "URL_", "IBAN_", "BLOCKLIST_"
            ]):
                continue

            # Also check case-insensitive (in case token format varies)
            if any(entity_text_lower.startswith(prefix.lower()) for prefix in [
                "AGE_", "DOB_", "PHONE_", "EMAIL_", "PERSON_", "LOCATION_",
                "SENDER", "HANDLE_", "URL_", "IBAN_", "BLOCKLIST_"
            ]):
                continue

            # Filter 1: Skip very short entities (likely false positives)
            if len(entity_text_lower) <= 2:
                continue

            # Filter 2: Skip common English words mistaken as entities
            if entity_text_lower in common_words:
                continue

            # Filter 3: Skip tech terms detected as ORG
            if entity["type"] == "ORG" and self.is_tech_term(entity["text"]):
                continue

            # Filter 4: Skip tech terms/adjectives detected as LOCATION (e.g., "German")
            if entity["type"] == "LOCATION" and self.is_tech_term(entity["text"]):
                continue

            # Filter 5: Apply location granularity rule with smart confidence filtering
            if entity["type"] == "LOCATION":
                # Check if it's a country first
                if self.is_country(entity["text"]):
                    # Country - skip redaction
                    continue

                # For cities/locations: apply stricter filtering to avoid false positives
                # Only filter out low-confidence if it looks like a false positive
                entity_score = entity.get("score", 0.85)

                # If confidence is very high (>= 0.90), always keep it (likely real location)
                if entity_score >= 0.90:
                    filtered.append(entity)
                # If moderate confidence (0.85-0.89), keep if not a common word
                elif entity_score >= 0.85:
                    if entity_text_lower not in common_words:
                        filtered.append(entity)
                # If low confidence (<0.85), skip (likely false positive)
                # else: skip
            else:
                # Non-location entities: keep them
                filtered.append(entity)

        return filtered

    def entities_to_tokens(self, entities: List[Dict]) -> List[RedactionToken]:
        """Convert entity dictionaries to RedactionToken objects."""
        tokens = []

        for entity in entities:
            token_value = self.get_next_token(entity["type"])
            low_confidence = entity["score"] < 0.85

            token = RedactionToken(
                type=entity["type"],
                value=token_value,
                original=entity["text"],
                startIndex=entity["start"],
                endIndex=entity["end"],
                confidence=entity["score"],
                lowConfidence=low_confidence
            )
            tokens.append(token)

        return tokens

    def redact_text(self, text: str, tokens: List[RedactionToken]) -> str:
        """Replace entities in text with tokens (in reverse order to preserve indices)."""
        # Sort by start index in reverse order
        sorted_tokens = sorted(tokens, key=lambda t: t.startIndex, reverse=True)

        for token in sorted_tokens:
            text = text[:token.startIndex] + token.value + text[token.endIndex:]

        return text

    def process(self, text: str, sender_name: str = "") -> Tuple[str, List[RedactionToken]]:
        """
        Main NER processing function.
        1. Check sender name for PERSON entity (if provided)
        2. Run Presidio on main text
        3. Run spaCy (English) on main text
        4. If German detected, run German spaCy model
        5. Merge results
        6. Apply location filtering
        7. Create tokens (note: no text redaction needed, just token creation)

        Args:
            text: Main message text (after header removal)
            sender_name: Optional sender name from WhatsApp header to check for PERSON
        """
        self.reset_counters()
        all_person_tokens = []

        if not MODELS_LOADED:
            print("Warning: NER models not loaded, skipping NER processing")
            return text, []

        # Step 0: Check sender name for PERSON entity (if provided)
        if sender_name and sender_name.strip() and sender_name.lower() != "user":
            # Run NER just on the sender name to see if it's a person
            sender_entities = self.run_spacy(sender_name, language="en")

            # Also check German model if sender name looks German
            if self.is_german_text_or_names(sender_name):
                sender_entities_de = self.run_spacy(sender_name, language="de")
                # Merge results
                for de_ent in sender_entities_de:
                    if not any(e["text"] == de_ent["text"] for e in sender_entities):
                        sender_entities.append(de_ent)

            # If sender name detected as PERSON, create a token for it
            person_entities = [e for e in sender_entities if e["type"] == "PERSON"]
            if person_entities:
                # Use the full sender name as the entity
                token = RedactionToken(
                    type="PERSON",
                    value=self.get_next_token("PERSON"),
                    original=sender_name,
                    startIndex=0,  # Placeholder (already redacted by SENDER)
                    endIndex=len(sender_name),
                    confidence=max(e["score"] for e in person_entities),
                    lowConfidence=False
                )
                all_person_tokens.append(token)

        # Step 1: Run Presidio on main text
        presidio_entities = self.run_presidio(text)

        # Step 2: Run spaCy (English) on main text
        spacy_en_entities = self.run_spacy(text, language="en")

        # Step 3: Check for German indicators (improved detection)
        # Run German model if we detect umlauts, German words, OR potential German names
        is_german_text = self.is_german_text_or_names(text)
        spacy_de_entities = []
        if is_german_text:
            # Only run German NER if German is clearly present
            spacy_de_entities = self.run_spacy(text, language="de")
            # Filter German results: only keep high-confidence detections
            spacy_de_entities = [e for e in spacy_de_entities if e.get("score", 0.85) >= 0.87]

        # Step 4: Merge all entities from main text
        all_spacy = spacy_en_entities + spacy_de_entities
        merged_entities = self.merge_entities(presidio_entities, all_spacy)

        # Step 5: Apply location filtering
        filtered_entities = self.filter_locations(merged_entities)

        # Step 6: Convert to tokens
        tokens = self.entities_to_tokens(filtered_entities)

        # Step 7: Redact text
        cleaned_text = self.redact_text(text, tokens)

        # Step 8: Combine sender PERSON tokens with main text tokens
        all_tokens = all_person_tokens + tokens

        return cleaned_text, all_tokens


# Module-level instance for use in pipeline
ner_engine = NEREngine()

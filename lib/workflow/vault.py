"""
Placeholder vault: maps anonymization placeholders back to their original values
and restores them in text returned by an LLM. Never serialize, log, or persist a vault.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

from lib.types import ProcessedMessage

PLACEHOLDER_RE = re.compile(
    r"\[SENDER\]|\[(?:PHONE|EMAIL|URL|HANDLE|AGE|DOB|PERSON|ORG|LOCATION|IBAN|BLOCKLIST)_[0-9A-Za-z]+\]",
    re.IGNORECASE,
)


class VaultIntegrityError(Exception):
    """A placeholder in the anonymized text cannot be mapped to exactly one original."""


@dataclass
class ReenrichResult:
    text: str
    restored: List[str] = field(default_factory=list)
    unknown_placeholders: List[str] = field(default_factory=list)


def build_vault(result: ProcessedMessage) -> Dict[str, str]:
    originals: Dict[str, Set[str]] = {}
    for token in result.tokens:
        if token.original:
            originals.setdefault(token.value, set()).add(token.original)

    vault: Dict[str, str] = {}
    for match in PLACEHOLDER_RE.finditer(result.cleanedText):
        placeholder = match.group(0)
        if placeholder in vault:
            continue
        candidates = originals.get(placeholder)
        if not candidates:
            raise VaultIntegrityError(f"No original recorded for {placeholder}")
        if len(candidates) > 1:
            raise VaultIntegrityError(f"Several originals recorded for {placeholder}")
        vault[placeholder] = next(iter(candidates))
    return vault


def reenrich(text: str, vault: Dict[str, str]) -> ReenrichResult:
    lookup = {placeholder.upper(): original for placeholder, original in vault.items()}
    canonical = {placeholder.upper(): placeholder for placeholder in vault}
    restored: Dict[str, None] = {}
    unknown: Dict[str, None] = {}

    def _swap(match: "re.Match[str]") -> str:
        key = match.group(0).upper()
        if key in lookup:
            restored[canonical[key]] = None
            return lookup[key]
        unknown[match.group(0)] = None
        return match.group(0)

    # A single substitution pass, so restored values are never scanned again.
    new_text = PLACEHOLDER_RE.sub(_swap, text)
    return ReenrichResult(text=new_text, restored=list(restored), unknown_placeholders=list(unknown))

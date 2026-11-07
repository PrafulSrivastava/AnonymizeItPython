import re
from typing import Dict, Set

import pytest

from lib.types import PipelineInput
from lib.pipeline.index import run_pipeline

PLACEHOLDER_RE = re.compile(
    r"\[SENDER\]|\[(?:PHONE|EMAIL|URL|HANDLE|AGE|DOB|PERSON|ORG|LOCATION|IBAN|BLOCKLIST)_[0-9A-Za-z]+\]"
)

CASES = [
    (
        "[07/11/2026, 14:22] Marcus Weber: Hi team — I am Marcus Weber, product manager in Berlin. "
        "Reach me at marcus.weber@acmecorp.com or +49 170 555 0198. My DOB is 12/03/1987. "
        "Bank: DE89 3704 0044 0532 0130 00. @marcusw https://linkedin.com/in/marcus-weber-dev",
        "Marcus Weber,Marcus",
    ),
    (
        "[26/02/2026, 13:01] Susi: Hey! Is the community feature live yet? "
        "My colleague Mo asked me the same thing yesterday.",
        "Susi,Mo",
    ),
    (
        "[24.01.26, 16:40:31] Jonas Weber: Ich bin 34 Jahre alt und arbeite als Manager in Berlin",
        "",
    ),
    (
        "Please email anna.schmidt@example.org and call +44 7911 123456 about John Smith's contract.",
        "John Smith",
    ),
]


@pytest.mark.parametrize("raw_text,blocklist", CASES)
def test_every_placeholder_in_text_maps_to_one_original(raw_text, blocklist):
    result = run_pipeline(PipelineInput(rawText=raw_text, blocklist=blocklist, sessionId="integrity"))

    originals: Dict[str, Set[str]] = {}
    for token in result.tokens:
        if token.original:
            originals.setdefault(token.value, set()).add(token.original)

    in_text = set(PLACEHOLDER_RE.findall(result.cleanedText))
    missing = sorted(p for p in in_text if p not in originals)
    conflicting = sorted(p for p in in_text if len(originals.get(p, ())) > 1)

    assert not missing, f"Placeholders with no original: {missing}\nText: {result.cleanedText}"
    assert not conflicting, f"Placeholders with several originals: {conflicting}"

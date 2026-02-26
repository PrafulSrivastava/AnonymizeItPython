"""
Test cases for WhatsApp anonymization pipeline.
Based on structured test data covering edge cases, multilingual messages, and over-redaction risks.
"""

from typing import List, Dict, Any

# Test case groups based on Sample_tests.md
TEST_CASES: List[Dict[str, Any]] = [
    # ============================================================
    # GROUP 1: Clean WhatsApp format, structural PII (regex-based)
    # ============================================================
    {
        "id": "TC01",
        "group": "structural_pii",
        "description": "Email with German umlaut name - regex + NER",
        "input": {
            "rawText": "[26/02/2026, 09:14] Sarah Müller: Hi everyone! Can someone help me understand the onboarding flow? My email is sarah.mueller@gmail.com and I've been stuck for 2 days.",
            "blocklist": "",
            "sessionId": "benchmark_session_01"
        },
        "must_redact": ["EMAIL", "PERSON", "SENDER"],
        "must_not_redact": ["onboarding flow", "2 days", "Hi everyone"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "Should catch email via regex, name via NER, sender from header"
    },
    {
        "id": "TC02",
        "group": "structural_pii",
        "description": "UK phone number + Instagram handle",
        "input": {
            "rawText": "[26/02/2026, 11:32] James O'Brien: Just joined the group! My number is +44 7911 123456 if anyone wants to chat directly. Also follow me @jamesobrien_dev on Instagram.",
            "blocklist": "",
            "sessionId": "benchmark_session_02"
        },
        "must_redact": ["PHONE", "HANDLE", "PERSON", "SENDER"],
        "must_not_redact": ["Just joined", "Instagram", "group"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "UK phone format, social handle with underscore, Irish name with apostrophe"
    },
    {
        "id": "TC03",
        "group": "structural_pii",
        "description": "German IBAN with spaces",
        "input": {
            "rawText": "[26/02/2026, 14:05] Priya Sharma: Quick question — does the app support IBAN payments? Mine is DE89 3704 0044 0532 0130 00 and I want to test the checkout flow.",
            "blocklist": "",
            "sessionId": "benchmark_session_03"
        },
        "must_redact": ["IBAN", "PERSON", "SENDER"],
        "must_not_redact": ["Quick question", "checkout flow", "app support"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "IBAN with spaces, Indian name should be caught by NER"
    },

    # ============================================================
    # GROUP 2: Age and date of birth variations
    # ============================================================
    {
        "id": "TC04",
        "group": "age_dob",
        "description": "Multiple ages with bucketing",
        "input": {
            "rawText": "[26/02/2026, 10:22] Anna Klein: I'm 34 and honestly the app UX is confusing for someone my age. My mum who is 67 years old also tried it and gave up immediately.",
            "blocklist": "",
            "sessionId": "benchmark_session_04"
        },
        "must_redact": ["AGE", "PERSON", "SENDER"],
        "must_not_redact": ["app UX", "confusing", "gave up"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "Should bucket: 34 → [AGE_30s], 67 → [AGE_60s]. Two age mentions."
    },
    {
        "id": "TC05",
        "group": "age_dob",
        "description": "Birth year in text",
        "input": {
            "rawText": "[26/02/2026, 08:45] Tom Fischer: Born in 1989 so I've seen a lot of apps come and go. This one has potential but the progress tracking feature is broken.",
            "blocklist": "",
            "sessionId": "benchmark_session_05"
        },
        "must_redact": ["DOB", "PERSON", "SENDER"],
        "must_not_redact": ["potential", "progress tracking", "broken"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "'Born in 1989' should match DOB pattern"
    },
    {
        "id": "TC06",
        "group": "age_dob",
        "description": "European date format (DD.MM.YYYY)",
        "input": {
            "rawText": "[26/02/2026, 16:18] Lena Bauer: I signed up on my birthday — 14.03.1991 — and the welcome email never arrived. Can someone check?",
            "blocklist": "",
            "sessionId": "benchmark_session_06"
        },
        "must_redact": ["DOB", "PERSON", "SENDER"],
        "must_not_redact": ["signed up", "birthday", "welcome email"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "DD.MM.YYYY format, common in Europe"
    },

    # ============================================================
    # GROUP 3: NER edge cases - short names, ambiguous names
    # ============================================================
    {
        "id": "TC07",
        "group": "ner_edge_cases",
        "description": "Short names requiring blocklist",
        "input": {
            "rawText": "[26/02/2026, 13:01] Susi: Hey! Is the community feature live yet? My colleague Mo asked me the same thing yesterday and I didn't know what to tell him.",
            "blocklist": "Susi,Mo",
            "sessionId": "benchmark_session_07"
        },
        "must_redact": ["BLOCKLIST", "SENDER"],
        "must_not_redact": ["community feature", "yesterday", "colleague"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "Short names (Susi, Mo) likely won't be caught by NER - need blocklist. Critical test case."
    },
    {
        "id": "TC08",
        "group": "ner_edge_cases",
        "description": "Name matching common word (Ali)",
        "input": {
            "rawText": "[26/02/2026, 09:55] Ali: The push notifications stopped working for me after the last update. Ali from the Berlin team had the same issue btw.",
            "blocklist": "",
            "sessionId": "benchmark_session_08"
        },
        "must_redact": ["PERSON", "SENDER", "LOCATION"],
        "must_not_redact": ["push notifications", "last update"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "Ali appears twice, Berlin should be redacted (city, not country)"
    },
    {
        "id": "TC09",
        "group": "ner_edge_cases",
        "description": "Asian name (Mei) in reference",
        "input": {
            "rawText": "[26/02/2026, 17:44] User: Can you tag Mei on this? She was the one who reported the bug last week and I think she has the screenshot.",
            "blocklist": "",
            "sessionId": "benchmark_session_09"
        },
        "must_redact": ["PERSON"],
        "must_not_redact": ["tag", "reported the bug", "screenshot"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "Short Asian name, may require high NER confidence"
    },

    # ============================================================
    # GROUP 4: Quasi-identifier combinations (should flag for review)
    # ============================================================
    {
        "id": "TC10",
        "group": "quasi_identifiers",
        "description": "Role + location + age combination",
        "input": {
            "rawText": "[26/02/2026, 11:10] Maria Gonzalez: As a senior product manager based in Munich, aged 41, I find the dashboard completely unintuitive. This would never pass a basic usability test.",
            "blocklist": "",
            "sessionId": "benchmark_session_10"
        },
        "must_redact": ["PERSON", "AGE", "LOCATION", "SENDER"],
        "must_not_redact": ["dashboard", "unintuitive", "usability test"],
        "expected_routing": ["review"],
        "notes": "HIGH QI RISK: role (product manager) + location (Munich) + age (41). Should flag quasi_identifier_risk: true"
    },
    {
        "id": "TC11",
        "group": "quasi_identifiers",
        "description": "Role + location + experience (years)",
        "input": {
            "rawText": "[26/02/2026, 15:33] David: I'm a freelance developer in Frankfurt, been coding for 15 years. The API docs are outdated — the endpoint at /api/v1/users returns a 404.",
            "blocklist": "",
            "sessionId": "benchmark_session_11"
        },
        "must_redact": ["PERSON", "LOCATION"],
        "must_not_redact": ["API docs", "endpoint", "15 years", "coding"],
        "expected_routing": ["review", "pass_flagged"],
        "notes": "QI risk: role (freelance developer) + location (Frankfurt) + implied age. '15 years' is experience, not age."
    },

    # ============================================================
    # GROUP 5: Obfuscated PII (hard cases for regex)
    # ============================================================
    {
        "id": "TC12",
        "group": "obfuscated_pii",
        "description": "Obfuscated email (dot/at format)",
        "input": {
            "rawText": "[26/02/2026, 12:44] Jonas Weber: Reach me at jonas dot weber at protonmail dot com — I don't post my email publicly anymore after the last spam wave.",
            "blocklist": "",
            "sessionId": "benchmark_session_12"
        },
        "must_redact": ["EMAIL", "PERSON", "SENDER"],
        "must_not_redact": ["Reach me", "spam wave", "publicly"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "Obfuscated email format: 'dot' and 'at' instead of symbols. Regex should handle this."
    },
    {
        "id": "TC13",
        "group": "obfuscated_pii",
        "description": "Old German phone format with parentheses",
        "input": {
            "rawText": "[26/02/2026, 10:08] Claire: My number is 0049 (0) 160 9876 5432 — old German format, not sure if your system recognises it. Happy to jump on a call.",
            "blocklist": "",
            "sessionId": "benchmark_session_13"
        },
        "must_redact": ["PHONE", "PERSON", "SENDER"],
        "must_not_redact": ["old German format", "system", "jump on a call"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "Tricky phone format: 0049 (0) 160. Should be parsed by phonenumbers library."
    },
    {
        "id": "TC14",
        "group": "obfuscated_pii",
        "description": "LinkedIn URL with path",
        "input": {
            "rawText": "[26/02/2026, 14:52] Fatima Al-Hassan: You can find me at linkedin.com/in/fatima-al-hassan-pm or just search my name — I'm the only one with that exact name on there.",
            "blocklist": "",
            "sessionId": "benchmark_session_14"
        },
        "must_redact": ["URL", "PERSON", "SENDER"],
        "must_not_redact": ["find me", "search"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "URL without http/https prefix. Name with hyphens."
    },

    # ============================================================
    # GROUP 6: Mixed language / code-switched
    # ============================================================
    {
        "id": "TC15",
        "group": "multilingual",
        "description": "German-English code-switching",
        "input": {
            "rawText": "[26/02/2026, 09:30] Björn Eriksson: Das Feature funktioniert nicht auf meinem iPhone. Björn here btw, Maide hat mir die Gruppe empfohlen. Danke schon mal!",
            "blocklist": "",
            "sessionId": "benchmark_session_15"
        },
        "must_redact": ["PERSON", "SENDER"],
        "must_not_redact": ["Feature", "iPhone", "Gruppe"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "German text with umlauts. Should trigger German NER model. Maide should be caught as PERSON."
    },
    {
        "id": "TC16",
        "group": "multilingual",
        "description": "Japanese-English code-switching",
        "input": {
            "rawText": "[26/02/2026, 16:05] Yuki Tanaka: すみません、I'm having trouble with the login page. Yuki from the Tokyo cohort — can someone from support help?",
            "blocklist": "",
            "sessionId": "benchmark_session_16"
        },
        "must_redact": ["PERSON", "LOCATION", "SENDER"],
        "must_not_redact": ["login page", "support"],
        "expected_routing": ["pass", "pass_flagged", "review"],
        "notes": "Japanese text (no Japanese model). Yuki should be caught by EN NER. Tokyo = city (redact). May have lower confidence."
    },

    # ============================================================
    # GROUP 7: Sensitive topics (should pass with content preserved)
    # ============================================================
    {
        "id": "TC17",
        "group": "sensitive_topics",
        "description": "Health-related content without explicit PII",
        "input": {
            "rawText": "[26/02/2026, 13:28] User: I need to be honest — I've been dealing with some health issues lately and the app's reminder feature has actually been really helpful for keeping me on track with medication.",
            "blocklist": "",
            "sessionId": "benchmark_session_17"
        },
        "must_redact": [],
        "must_not_redact": ["health issues", "medication", "reminder feature"],
        "expected_routing": ["pass"],
        "notes": "Sensitive topic but no PII. Should pass cleanly without over-redaction."
    },
    {
        "id": "TC18",
        "group": "sensitive_topics",
        "description": "Personal situation (divorce) without identifiers",
        "input": {
            "rawText": "[26/02/2026, 11:55] Rebecca Hofer: Not sure if this is the right place but I'm going through a divorce and the shared account feature is causing me real problems. Can someone from the team contact me directly?",
            "blocklist": "",
            "sessionId": "benchmark_session_18"
        },
        "must_redact": ["PERSON", "SENDER"],
        "must_not_redact": ["divorce", "shared account", "team"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "Sensitive topic but legitimate feedback. Name should be redacted."
    },

    # ============================================================
    # GROUP 8: Minimal PII - true negatives (must NOT over-redact)
    # ============================================================
    {
        "id": "TC19",
        "group": "true_negatives",
        "description": "Technical bug report - zero PII",
        "input": {
            "rawText": "[26/02/2026, 10:00] User: The dark mode on Android is broken. When I switch from light to dark the nav bar stays white. Happens every time on version 2.4.1.",
            "blocklist": "",
            "sessionId": "benchmark_session_19"
        },
        "must_redact": [],
        "must_not_redact": ["dark mode", "Android", "nav bar", "version 2.4.1"],
        "expected_routing": ["pass"],
        "notes": "CRITICAL: Zero PII. Must preserve all content. Over-redaction = test failure."
    },
    {
        "id": "TC20",
        "group": "true_negatives",
        "description": "Product feedback - zero PII",
        "input": {
            "rawText": "[26/02/2026, 15:15] User: Love the new onboarding flow update! The three-step wizard is much clearer than before. One suggestion — add a progress bar so users know how far along they are.",
            "blocklist": "",
            "sessionId": "benchmark_session_20"
        },
        "must_redact": [],
        "must_not_redact": ["onboarding flow", "three-step wizard", "progress bar"],
        "expected_routing": ["pass"],
        "notes": "CRITICAL: Zero PII. Pure product feedback. Must pass with 100% content preserved."
    },
]


# Additional test cases from real chat data (_chat.txt)
REAL_CHAT_CASES: List[Dict[str, Any]] = [
    {
        "id": "RC01",
        "group": "real_chat",
        "description": "Real chat with email and IP address",
        "input": {
            "rawText": "[24.01.26, 16:40:31] Critic: prafulsrivastava2021@gmail.com",
            "blocklist": "",
            "sessionId": "real_chat_01"
        },
        "must_redact": ["EMAIL", "SENDER"],
        "must_not_redact": [],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "Simple email extraction from real chat"
    },
    {
        "id": "RC02",
        "group": "real_chat",
        "description": "LinkedIn URL with name path",
        "input": {
            "rawText": "[24.01.26, 17:10:25] Critic: https://www.linkedin.com/in/praful-srivastava-b24586171/",
            "blocklist": "",
            "sessionId": "real_chat_02"
        },
        "must_redact": ["URL", "SENDER"],
        "must_not_redact": [],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "LinkedIn URL contains name in path - URL should be redacted"
    },
    {
        "id": "RC03",
        "group": "real_chat",
        "description": "Real chat with person names",
        "input": {
            "rawText": "[25.01.26, 16:36:13] Maide Altas: Hey Prufel, it was a pleasure meeting you all yesterday!",
            "blocklist": "",
            "sessionId": "real_chat_03"
        },
        "must_redact": ["PERSON", "SENDER"],
        "must_not_redact": ["pleasure meeting", "yesterday"],
        "expected_routing": ["pass", "pass_flagged"],
        "notes": "Two names: Maide Altas (sender) and Prufel (in message)"
    },
]


def get_all_test_cases() -> List[Dict[str, Any]]:
    """Return all test cases (structured + real chat)."""
    return TEST_CASES + REAL_CHAT_CASES


def get_test_cases_by_group(group: str) -> List[Dict[str, Any]]:
    """Filter test cases by group."""
    all_cases = get_all_test_cases()
    return [tc for tc in all_cases if tc["group"] == group]


def get_test_case_by_id(test_id: str) -> Dict[str, Any]:
    """Get specific test case by ID."""
    all_cases = get_all_test_cases()
    for tc in all_cases:
        if tc["id"] == test_id:
            return tc
    raise ValueError(f"Test case {test_id} not found")

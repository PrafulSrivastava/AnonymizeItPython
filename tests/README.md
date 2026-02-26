# Test Suite Documentation

Comprehensive test suite for the WhatsApp anonymization pipeline with 23 test cases covering all edge cases and scenarios.

## Test Cases Overview

### 📊 Test Coverage (23 total cases)

| Group | Count | Description |
|-------|-------|-------------|
| **Structural PII** | 3 | Email, phone, IBAN - regex-based detection |
| **Age/DOB** | 3 | Age bucketing, birth dates in various formats |
| **NER Edge Cases** | 3 | Short names, ambiguous names, Asian names |
| **Quasi-identifiers** | 2 | Role + location + age combinations (high risk) |
| **Obfuscated PII** | 3 | Dotted emails, old phone formats, LinkedIn URLs |
| **Multilingual** | 2 | German-English and Japanese-English code-switching |
| **Sensitive Topics** | 2 | Health, divorce - must preserve context |
| **True Negatives** | 2 | CRITICAL: Zero PII, must NOT over-redact |
| **Real Chat** | 3 | Test cases from actual chat data |

### 🎯 Target Accuracy

- **Goal**: ≥17/20 = **85% pass rate**
- **Critical tests**: TC19, TC20 (true negatives - over-redaction = failure)
- **Expected failures**: TC16 (Japanese text without Japanese model)

## Running Tests

### Prerequisites

```bash
# Ensure API is running
uvicorn api.anonymise:app --reload --port 8000

# In another terminal, verify API is up
curl http://localhost:8000/
```

### Run All Tests

```bash
cd tests
python run_benchmark.py --url http://localhost:8000
```

**Output:**
- Console summary with pass/fail for each test
- Detailed JSON results in `benchmark_results.json`
- Exit code 0 if ≥85% pass rate, 1 otherwise

### Run Specific Test Groups

```bash
# Only structural PII tests
python run_benchmark.py --group structural_pii

# Only true negatives (critical for over-redaction check)
python run_benchmark.py --group true_negatives

# Only real chat tests
python run_benchmark.py --real-chat-only
```

### Run Single Test Case

```bash
# Run TC07 (short names test)
python run_benchmark.py --test-id TC07

# Run TC19 (critical: zero PII)
python run_benchmark.py --test-id TC19
```

### Quick Manual Test

```bash
# Test custom message
python quick_test.py "[26/02/2026, 09:14] Sarah: My email is sarah@test.com"

# With blocklist
python quick_test.py "[26/02/2026, 13:01] Susi: Hey Mo!" "Susi,Mo"
```

## Test Case Details

### Critical Test Cases

#### TC07 - Short Names (Blocklist Required)
```
Input: "Susi: Hey! My colleague Mo asked me..."
Blocklist: "Susi,Mo"
Expected: Both names redacted as [BLOCKLIST_01], [BLOCKLIST_02]
Why critical: NER won't catch short names like "Mo", "Ali", "Mei"
```

#### TC10 - Quasi-identifier Risk
```
Input: "As a senior product manager based in Munich, aged 41..."
Expected:
  - Routing: "review"
  - quasi_identifier_risk: true
  - QI count: ≥3 (role + location + age)
Why critical: Tests QI detection logic
```

#### TC19 - True Negative (Zero PII)
```
Input: "The dark mode on Android is broken..."
Expected:
  - Zero tokens
  - "Android", "dark mode", "nav bar" preserved
  - Routing: "pass"
Why critical: Over-redaction = pipeline failure
```

#### TC20 - Product Feedback (Zero PII)
```
Input: "Love the new onboarding flow update!..."
Expected:
  - Zero tokens
  - All product terms preserved
  - Routing: "pass"
Why critical: Must not redact product vocabulary
```

### Edge Cases

#### Obfuscated Email (TC12)
```
Input: "jonas dot weber at protonmail dot com"
Expected: Detected as [EMAIL_01]
Tests: Obfuscated format regex
```

#### Old German Phone Format (TC13)
```
Input: "0049 (0) 160 9876 5432"
Expected: Detected as [PHONE_01]
Tests: phonenumbers library parsing
```

#### German-English Code-Switching (TC15)
```
Input: "Das Feature funktioniert nicht... Björn here btw, Maide..."
Expected:
  - German model triggered (umlauts detected)
  - Both Björn and Maide caught as [PERSON_XX]
Tests: Multilingual NER
```

## Interpreting Results

### Benchmark Output

```
==================================================
BENCHMARK SUMMARY
==================================================
Total tests:     23
Passed:          20 ✓
Failed:          3 ✗
Pass rate:       87.0%
Target:          85.0%
Meets target:    YES ✓

==================================================
RESULTS BY GROUP
==================================================
✓ structural_pii          3/3 (100%)
✓ age_dob                 3/3 (100%)
✗ ner_edge_cases          2/3 (67%)
✓ quasi_identifiers       2/2 (100%)
...
```

### Common Failure Patterns

1. **"Missing expected token type: PERSON"**
   - NER didn't catch name
   - Solution: Add to blocklist or improve NER confidence

2. **"Over-redacted: 'Android' should be preserved"**
   - False positive in NER/regex
   - Solution: Adjust patterns or add to whitelist

3. **"Unexpected routing: got 'pass', expected 'review'"**
   - Confidence scoring issue
   - Check: QI count, NER confidence thresholds

4. **"Expected quasi_identifier_risk flag but not set"**
   - QI detection not triggered
   - Check: Role keyword list, location filtering

## Test Results Analysis

### Expected Pass Rate: 85-90%

**Likely failures:**
- TC16 (Japanese text) - No Japanese NER model
- TC08 (Ali) - Common word, may not be detected as name
- TC09 (Mei) - Very short Asian name

**Must pass:**
- TC19, TC20 (true negatives) - Over-redaction = critical failure
- TC01-TC06 (structural PII) - Basic regex detection
- TC10 (quasi-identifiers) - Core risk detection logic

## Debugging Failed Tests

### Step 1: Run Single Test

```bash
python run_benchmark.py --test-id TC07
```

### Step 2: Check Cleaned Text

Look at the output:
```
Cleaned text:
  [SENDER] Hey! Is the community feature live yet? My colleague Mo...
```

Is "Mo" still there? → Blocklist not working
Is "community" redacted? → Over-redaction issue

### Step 3: Check Token List

```json
"tokens": [
  {"type": "SENDER", "value": "[SENDER]", ...},
  {"type": "BLOCKLIST", "value": "[BLOCKLIST_01]", ...}
]
```

Are expected types present? Are there unexpected tokens?

### Step 4: Check Confidence Signals

```json
"signals": {
  "regexCoverage": 0.95,
  "nerConfidence": 0.88,
  "quasiIdentifierCount": 0,
  "residualTokenDensity": 0.75
}
```

Which signal is low? Adjust corresponding stage.

### Step 5: Use Quick Test for Iteration

```bash
python quick_test.py "[26/02/2026, 13:01] Susi: Hey Mo!" "Susi,Mo"
```

Faster feedback loop for debugging.

## Comparing with TypeScript Implementation

### Side-by-Side Benchmark

```bash
# Python implementation
python run_benchmark.py --url http://localhost:8000 --output python_results.json

# TypeScript implementation (when available)
python run_benchmark.py --url http://localhost:3000 --output typescript_results.json

# Compare
python compare_results.py python_results.json typescript_results.json
```

### Key Metrics to Compare

1. **Pass rate**: Python vs TypeScript
2. **Token counts**: Are they catching similar amounts?
3. **Routing decisions**: Agreement on pass/review?
4. **Over-redaction**: Which preserves more content on TC19/TC20?
5. **QI detection**: Which better identifies quasi-identifiers?

## Continuous Testing

### Pre-deployment Checklist

Before deploying to production:

```bash
# 1. Run full benchmark
python run_benchmark.py

# 2. Check true negatives specifically
python run_benchmark.py --group true_negatives

# 3. Verify quasi-identifier detection
python run_benchmark.py --test-id TC10

# 4. Test real chat cases
python run_benchmark.py --real-chat-only

# 5. Manual spot check
python quick_test.py "Your own test message here"
```

### Regression Testing

Add new failing messages as test cases:

1. Copy failed message from production logs
2. Add to `test_cases.py` in appropriate group
3. Define expected behavior (`must_redact`, `must_not_redact`)
4. Run benchmark to verify fix

## Performance Benchmarks

### Expected Timings (Local)

- Warm request (models loaded): <2s per test
- Cold start (first test): ~5-10s
- Full 23-test suite: ~1-2 minutes

### Vercel Serverless

- First request: 10-15s (cold start)
- Subsequent: <3s (warm)
- Full suite: ~3-5 minutes

## Troubleshooting

### "Connection refused"

```bash
# Check if API is running
curl http://localhost:8000/

# Start API if not running
uvicorn api.anonymise:app --reload --port 8000
```

### "Models not loaded"

```bash
# Verify models installed
python -c "import spacy; print(spacy.load('en_core_web_lg'))"

# Reinstall if needed
pip install --force-reinstall -r requirements.txt
```

### "Import error: test_cases"

```bash
# Run from tests directory
cd tests
python run_benchmark.py

# Or add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:."
```

## Contributing New Tests

### Template

```python
{
    "id": "TC##",
    "group": "group_name",
    "description": "Brief description",
    "input": {
        "rawText": "[26/02/2026, 10:00] User: Message text",
        "blocklist": "",
        "sessionId": "test_session"
    },
    "must_redact": ["TOKEN_TYPE"],
    "must_not_redact": ["specific text"],
    "expected_routing": ["pass"],
    "notes": "Why this test is important"
}
```

Add to appropriate group in `test_cases.py`.

## Files

- `test_cases.py` - All 23 test case definitions
- `run_benchmark.py` - Main benchmark runner
- `quick_test.py` - Quick manual testing utility
- `benchmark_results.json` - Output from last run (generated)
- `README.md` - This file

## Support

For issues with tests:
1. Check troubleshooting section above
2. Review failed test details in `benchmark_results.json`
3. Use `quick_test.py` for isolated debugging
4. Check main project README for API setup

---

**Target**: ≥17/20 tests passing (85%)
**Current**: Run `python run_benchmark.py` to find out! 🚀

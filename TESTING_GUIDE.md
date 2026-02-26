# Testing Guide - Quick Start

Complete guide to testing the WhatsApp anonymization pipeline with the 23-case test suite.

## 🚀 Quick Start (5 minutes)

### Step 1: Install Dependencies

```bash
# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

# Install all dependencies (this will take 5-10 minutes for spaCy models)
pip install -r requirements.txt
```

### Step 2: Start the API

```bash
# Start local server
uvicorn api.anonymise:app --reload --port 8000

# Verify it's running (in another terminal)
curl http://localhost:8000/
# Should return: {"status":"ok", ...}
```

### Step 3: Run Tests

**Windows:**
```batch
run_tests.bat all
```

**Mac/Linux:**
```bash
chmod +x run_tests.sh
./run_tests.sh all
```

**Or manually:**
```bash
cd tests
python run_benchmark.py --url http://localhost:8000
```

## 📊 What You'll See

### Console Output

```
======================================================================
Running TC01: Email with German umlaut name - regex + NER
======================================================================

✓ Status: PASS
  Routing: pass
  Confidence: 0.92
  Tokens found: 3
  Token types: {'EMAIL', 'PERSON', 'SENDER'}

Cleaned text:
  [SENDER] Hi everyone! Can someone help me understand the onboarding flow? My email is [EMAIL_01] and I've been stuck for 2 days.

======================================================================
BENCHMARK SUMMARY
======================================================================
Total tests:     23
Passed:          20 ✓
Failed:          3 ✗
Pass rate:       87.0%
Target:          85.0%
Meets target:    YES ✓
```

### JSON Results

Detailed results saved to `tests/benchmark_results.json`:

```json
{
  "timestamp": "2026-02-26T20:45:00",
  "total_tests": 23,
  "passed": 20,
  "failed": 3,
  "pass_rate": 87.0,
  "meets_target": true,
  "results": [
    {
      "test_id": "TC01",
      "passed": true,
      "details": {
        "cleaned_text": "[SENDER] Hi everyone! ...",
        "tokens": [...],
        "confidence": {...}
      }
    },
    ...
  ]
}
```

## 🎯 Test Suite Breakdown

### 23 Test Cases Covering:

1. **TC01-03**: Structural PII (emails, phones, IBANs)
2. **TC04-06**: Age and DOB handling with bucketing
3. **TC07-09**: NER edge cases (short names, ambiguous)
4. **TC10-11**: Quasi-identifiers (HIGH RISK scenarios)
5. **TC12-14**: Obfuscated PII (tricky formats)
6. **TC15-16**: Multilingual (German-English, Japanese-English)
7. **TC17-18**: Sensitive topics (must preserve context)
8. **TC19-20**: **CRITICAL** - True negatives (zero PII, must NOT over-redact)
9. **RC01-03**: Real chat data tests

### Critical Tests

**Must Pass (Zero Tolerance):**
- ✅ **TC19**: Technical bug report - zero tokens expected
- ✅ **TC20**: Product feedback - zero tokens expected

**High Importance:**
- ✅ **TC07**: Short names (Susi, Mo) - requires blocklist
- ✅ **TC10**: Quasi-identifier risk - must flag for review

**Expected to Fail:**
- ❌ **TC16**: Japanese text (no Japanese NER model)

## 🔍 Testing Scenarios

### Scenario 1: Quick Smoke Test

Test a single message to verify API is working:

```bash
cd tests
python quick_test.py "[26/02/2026, 09:14] Sarah: Email me at sarah@test.com"
```

**Expected output:**
- [SENDER] detected
- [EMAIL_01] detected
- "Email me at" preserved
- Confidence: 0.90+
- Routing: pass

### Scenario 2: Critical Tests Only

Verify no over-redaction (most important):

```bash
# Windows
run_tests.bat critical

# Mac/Linux
./run_tests.sh critical
```

**Expected:**
- TC19: PASS (Android, dark mode preserved)
- TC20: PASS (onboarding flow, progress bar preserved)

### Scenario 3: Quasi-Identifier Detection

Verify high-risk combinations are flagged:

```bash
python run_benchmark.py --test-id TC10
```

**Expected:**
- quasi_identifier_risk: true
- Routing: review
- QI count: ≥3

### Scenario 4: Multilingual Support

Test German language detection:

```bash
python run_benchmark.py --test-id TC15
```

**Expected:**
- German NER model triggered (umlauts detected)
- Björn detected as [PERSON_01]
- Maide detected as [PERSON_02]

### Scenario 5: Full Benchmark

Run complete test suite for production readiness:

```bash
# Windows
run_tests.bat all

# Mac/Linux
./run_tests.sh all
```

**Target:**
- Pass rate: ≥85% (17/20)
- True negatives: 100% (TC19, TC20 must pass)
- QI detection: Working (TC10 flags risk)

## 🐛 Debugging Failed Tests

### Step 1: Identify Failure

```bash
python run_benchmark.py --test-id TC07
```

Output shows:
```
✗ Status: FAIL

✗ Failures:
  - Missing expected token type: BLOCKLIST
```

### Step 2: Check Cleaned Text

```
Cleaned text:
  [SENDER] Hey! Is the community feature live yet? My colleague Mo asked me...
```

Problem: "Mo" is still there, not redacted!

### Step 3: Diagnose Root Cause

- Blocklist matcher not working?
- Word boundary detection issue?
- Aho-Corasick automaton problem?

### Step 4: Test Isolated

```bash
python quick_test.py "[26/02/2026, 13:01] Susi: Hey Mo!" "Susi,Mo"
```

### Step 5: Fix and Retest

After fixing the issue:

```bash
python run_benchmark.py --test-id TC07
# Should now pass
```

## 📈 Performance Expectations

### Local Development

- **First test**: 5-10 seconds (cold start, model loading)
- **Subsequent tests**: <2 seconds each (models cached)
- **Full 23-test suite**: 1-2 minutes total

### Vercel Deployment

- **Cold start**: 10-15 seconds (first request)
- **Warm requests**: <3 seconds
- **Full suite**: 3-5 minutes

## ✅ Pre-Deployment Checklist

Before deploying to production, verify:

```bash
# 1. All tests pass target
run_tests.bat all
# Expected: Pass rate ≥85%

# 2. True negatives perfect
run_tests.bat critical
# Expected: 2/2 (100%)

# 3. QI detection working
python run_benchmark.py --test-id TC10
# Expected: quasi_identifier_risk: true

# 4. Real chat cases work
python run_benchmark.py --real-chat-only
# Expected: 3/3 or 2/3

# 5. Manual spot check
python quick_test.py "Your own test message"
```

## 🔧 Common Issues

### Issue 1: "Connection refused"

**Problem**: API not running

**Solution:**
```bash
# Start API
uvicorn api.anonymise:app --reload --port 8000

# Verify
curl http://localhost:8000/
```

### Issue 2: "ModuleNotFoundError: No module named 'en_core_web_lg'"

**Problem**: spaCy models not installed

**Solution:**
```bash
# Reinstall requirements
pip install --force-reinstall -r requirements.txt

# Verify models
python -c "import spacy; print(spacy.load('en_core_web_lg'))"
```

### Issue 3: "Import error: test_cases"

**Problem**: Wrong directory

**Solution:**
```bash
# Run from project root
cd C:\Users\srivpra\Documents\GitHub\AnonymizeItPython
python tests/run_benchmark.py

# OR run from tests directory
cd tests
python run_benchmark.py
```

### Issue 4: Over-redaction on TC19/TC20

**Problem**: False positives in NER

**Solution:**
1. Check NER confidence thresholds in `ner_engine.py`
2. Review country list (if "Android" being caught as location)
3. Check regex patterns aren't too aggressive

### Issue 5: Under-redaction (missing PII)

**Problem**: Patterns not matching

**Solution:**
1. Check regex patterns in `regex_stripper.py`
2. Verify NER models loaded correctly
3. Test with blocklist to compensate

## 📝 Test Case Examples

### Example 1: Structural PII (TC01)

```python
Input:
  "[26/02/2026, 09:14] Sarah Müller: My email is sarah.mueller@gmail.com"

Expected:
  - Tokens: SENDER, EMAIL, PERSON
  - Preserved: "My", "is", onboarding context
  - Routing: pass or pass_flagged

Result:
  "[SENDER] [PERSON_01]: My email is [EMAIL_01]"
```

### Example 2: True Negative (TC19)

```python
Input:
  "[26/02/2026, 10:00] User: The dark mode on Android is broken..."

Expected:
  - Tokens: [] (ZERO)
  - Preserved: "dark mode", "Android", "nav bar", "version 2.4.1"
  - Routing: pass

Result:
  "The dark mode on Android is broken. When I switch from light to dark..."
```

### Example 3: Quasi-Identifier Risk (TC10)

```python
Input:
  "As a senior product manager based in Munich, aged 41..."

Expected:
  - Tokens: PERSON, LOCATION, AGE
  - quasi_identifier_risk: true
  - Routing: review
  - QI count: ≥3

Result:
  "[PERSON_01]: As a senior product manager based in [LOCATION_01], [AGE_40s]..."
```

## 🎓 Next Steps

1. **Run your first test**: `run_tests.bat quick`
2. **Run full benchmark**: `run_tests.bat all`
3. **Check results**: Open `tests/benchmark_results.json`
4. **Debug failures**: Use `quick_test.py` for iteration
5. **Compare with TypeScript**: Run against both implementations

## 📚 Additional Resources

- **Detailed test docs**: `tests/README.md`
- **Test case definitions**: `tests/test_cases.py`
- **Benchmark runner**: `tests/run_benchmark.py`
- **Quick test utility**: `tests/quick_test.py`
- **Main README**: `README.md`

---

**Target**: ≥17/20 (85% pass rate)

**Ready to test?** Run: `run_tests.bat all` 🚀

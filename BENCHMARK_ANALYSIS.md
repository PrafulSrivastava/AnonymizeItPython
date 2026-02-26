# Benchmark Analysis - Test Results

## 📊 Overall Results

```
Total tests:     23
Passed:          3  ✓
Failed:          20 ✗
Pass rate:       13.0%
Target:          85.0%
Status:          ❌ DOES NOT MEET TARGET
```

## ✅ Tests That Passed (3/23)

1. **TC08**: Name matching common word (Ali) ✓
2. **TC09**: Asian name (Mei) in reference ✓
3. **TC16**: Japanese-English code-switching ✓

## ❌ Critical Issues Found

### Issue 1: Over-Redaction on Clean Messages (CRITICAL)

**TC19**: "Android" detected as [ORG_01] ❌

```
Input:  "The dark mode on Android is broken..."
Output: "The dark mode on [ORG_01] is broken..."

Expected: 0 PII tokens (clean technical feedback)
Got:      2 tokens (SENDER + ORG)
```

**Root Cause:** NER engine incorrectly identifying "Android" as an organization.

**Impact:** FALSE POSITIVE - Pipeline over-redacts legitimate product terms.

**Fix Needed:**
- Add whitelist for common tech terms (Android, iOS, iPhone, etc.)
- Lower NER confidence threshold for common words
- Add validation check for known product names

---

### Issue 2: IBAN Detection Not Working

**TC03**: IBAN with spaces not detected ❌

```
Input:  "Mine is DE89 3704 0044 0532 0130 00"
Output: "Mine is DE[PHONE_01] 0130 00"

Expected: [IBAN_01]
Got:      [PHONE_01] (partial match only)
```

**Root Cause:** IBAN regex requires continuous alphanumeric string, fails on spaces.

**Impact:** IBAN not redacted, sensitive banking info leaked.

**Fix Needed:**
- Update IBAN regex to handle spaces: `r'[A-Z]{2}\s*[0-9]{2}[\s0-9A-Z]{15,30}'`
- Process before phone number detection (order matters)

---

### Issue 3: Blocklist Matching Not Working Correctly

**TC07**: Blocklist terms not matched ❌

```
Input:     "Susi: Hey! My colleague Mo asked..."
Blocklist: "Susi,Mo"
Output:    "[SENDER] Hey! My colleague [PERSON_01] asked..."

Expected: [BLOCKLIST_01], [BLOCKLIST_02]
Got:      [SENDER], [PERSON_01] (NER caught Mo, not blocklist)
```

**Root Cause:** NER running before blocklist OR blocklist not matching correctly.

**Impact:** Custom blocklist terms not being redacted.

**Fix Needed:**
- Verify blocklist runs on text that still contains the terms
- Check Aho-Corasick automaton is built correctly
- Ensure "Susi" from sender header is added to blocklist check

---

### Issue 4: Person Names Not Detected by NER

**TC05**: "Tom Fischer" not detected ❌
**TC06**: "Lena Bauer" not detected ❌

```
TC05 Input:  "Tom Fischer: Born in 1989..."
TC05 Output: Missing [PERSON] token

TC06 Input:  "Lena Bauer: I signed up on my birthday..."
TC06 Output: Missing [PERSON] token
```

**Root Cause:** NER models not recognizing German names OR confidence too low.

**Impact:** Names leaking through pipeline.

**Fix Needed:**
- Verify German NER model (de_core_news_lg) is loading correctly
- Check German language detection heuristic
- Lower NER confidence threshold OR add German name patterns to regex

---

### Issue 5: Routing/Confidence Scoring Too Strict

**TC04, TC20**: Clean messages routed to "review" or "pass_flagged" ❌

```
TC20: Product feedback (no PII except SENDER)
Confidence: 0.796
Routing: pass_flagged (Expected: pass)
```

**Root Cause:** Confidence threshold of 0.90 too high for simple messages.

**Impact:** Too many false alarms, clean messages flagged for review.

**Fix Needed:**
- Adjust confidence weights in `confidence_scorer.py`
- If only SENDER token and residual density >0.8, force routing to "pass"
- Consider special case for "User" as sender (generic name)

---

## 🔍 Failure Breakdown by Category

| Category | Count | Impact |
|----------|-------|--------|
| **Missing tokens** | 12 | HIGH - PII not detected |
| **Routing errors** | 11 | MEDIUM - Too many false alarms |
| **Over-redaction** | 4 | CRITICAL - Breaking clean messages |
| **Connection errors** | 2 | LOW - API startup issue |

---

## 🛠️ Priority Fixes

### Priority 1: CRITICAL (Must fix before deployment)

1. **Fix over-redaction (TC19)**: Add whitelist for tech terms
   - File: `lib/pipeline/ner_engine.py`
   - Add: TECH_TERMS = {"android", "ios", "iphone", ...}
   - Check entity text against whitelist before adding token

2. **Fix IBAN detection (TC03)**: Update regex pattern
   - File: `lib/pipeline/regex_stripper.py`
   - Change IBAN pattern to handle spaces
   - Run IBAN detection BEFORE phone detection

### Priority 2: HIGH (Impacts accuracy)

3. **Fix blocklist matching (TC07)**: Verify blocklist pipeline
   - File: `lib/pipeline/blocklist.py`
   - Debug why "Susi" not matched
   - Ensure blocklist runs on correct text state

4. **Fix German name detection (TC05, TC06)**: Improve NER
   - File: `lib/pipeline/ner_engine.py`
   - Verify German model loading
   - Add logging to see if German detection triggered

### Priority 3: MEDIUM (User experience)

5. **Adjust confidence scoring (TC04, TC20)**: Less aggressive flagging
   - File: `lib/pipeline/confidence_scorer.py`
   - Add special case for clean messages (only SENDER token)
   - Adjust weights or thresholds

---

## 📈 Projected Improvement

If Priority 1 & 2 fixes are implemented:

| Fix | Tests Affected | Expected Improvement |
|-----|----------------|----------------------|
| Over-redaction fix | TC19, TC20 | +2 tests |
| IBAN detection | TC03 | +1 test |
| Blocklist fix | TC07 | +1 test |
| German NER | TC05, TC06 | +2 tests |
| Confidence tuning | TC04, TC11, TC12, TC13, TC14, TC15, TC17, TC18, TC20 | +5-7 tests |
| **TOTAL** | | **~13-15 tests** |

**Projected pass rate after fixes: 60-70%** (still below 85% target)

---

## 🧪 Recommended Next Steps

### Step 1: Quick Wins (30 minutes)

```bash
# Test specific failures individually
cd tests
python quick_test.py "[26/02/2026, 10:00] User: The dark mode on Android is broken"
# Check if Android is detected as ORG

python quick_test.py "[26/02/2026, 14:05] Priya: Mine is DE89 3704 0044 0532 0130 00"
# Check if IBAN detected correctly
```

### Step 2: Implement Priority 1 Fixes (2-3 hours)

1. Add tech term whitelist to `ner_engine.py`
2. Fix IBAN regex in `regex_stripper.py`
3. Rerun benchmark: `python run_benchmark.py`

### Step 3: Implement Priority 2 Fixes (2-3 hours)

4. Debug blocklist matching
5. Verify German NER model
6. Rerun benchmark

### Step 4: Fine-Tune (1-2 hours)

7. Adjust confidence scoring thresholds
8. Test edge cases individually
9. Final benchmark run

---

## 💡 Insights

### What Worked Well

✅ **Japanese name detection (TC16)**: Yuki Tanaka caught by EN NER
✅ **Short names with NER (TC08, TC09)**: Ali, Mei detected
✅ **Basic email/phone regex**: When patterns are simple

### What Needs Work

❌ **NER too aggressive**: Detecting product names as orgs
❌ **IBAN regex**: Doesn't handle spaces (common in real IBANs)
❌ **Blocklist**: Not overriding NER results
❌ **German support**: Names not being caught
❌ **Confidence scoring**: Too strict for clean messages

### Unexpected Findings

- **TC08, TC09 passed but TC07 failed**: NER catching names but blocklist not working
- **TC16 passed**: Japanese text didn't break the pipeline (good resilience)
- **"Android" as ORG**: Shows NER needs domain-specific filtering

---

## 📝 Technical Details

### Test Environment

- API: http://localhost:8000
- Models: en_core_web_lg, de_core_news_lg
- Python: 3.11
- Date: 2026-02-26

### Files to Modify

1. `lib/pipeline/ner_engine.py` - Add whitelist, fix German detection
2. `lib/pipeline/regex_stripper.py` - Fix IBAN regex
3. `lib/pipeline/blocklist.py` - Debug matching logic
4. `lib/pipeline/confidence_scorer.py` - Adjust thresholds

### Testing Strategy

After each fix:
```bash
# Test specific case
python quick_test.py "<test message>"

# Run affected group
python run_benchmark.py --group structural_pii

# Full benchmark
python run_benchmark.py
```

---

## 🎯 Target vs Reality

| Metric | Target | Current | Gap |
|--------|--------|---------|-----|
| Pass rate | 85% | 13% | -72% |
| True negatives | 100% | 0% | -100% |
| Structural PII | 100% | 33% | -67% |
| NER accuracy | 80%+ | 40% | -40% |

**Conclusion:** Significant work needed to reach production quality. Core pipeline is functional but needs tuning and bug fixes.

---

**Next action:** Start with Priority 1 fixes (over-redaction and IBAN detection).

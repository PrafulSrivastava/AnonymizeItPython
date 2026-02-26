"""
Quick verification script to test Priority 1 fixes.
Tests the two critical issues before running full benchmark.
"""

import requests
import json

API_URL = "http://localhost:8000/api/anonymise"

def test_fix(test_name, message, blocklist="", expected_tokens=None, should_not_contain=None):
    """Test a single fix."""
    print(f"\n{'='*70}")
    print(f"Testing: {test_name}")
    print(f"{'='*70}")

    payload = {
        "rawText": message,
        "blocklist": blocklist,
        "sessionId": "verify_fix"
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=10)

        if response.status_code != 200:
            print(f"❌ FAILED: HTTP {response.status_code}")
            print(response.text[:200])
            return False

        result = response.json()["result"]
        cleaned = result["cleanedText"]
        tokens = [t["type"] for t in result["tokens"]]

        print(f"Original: {message}")
        print(f"Cleaned:  {cleaned}")
        print(f"Tokens:   {tokens}")

        success = True

        # Check expected tokens
        if expected_tokens:
            for expected in expected_tokens:
                if expected not in tokens:
                    print(f"❌ Missing expected token: {expected}")
                    success = False

        # Check things that should NOT be redacted
        if should_not_contain:
            for term in should_not_contain:
                if term.lower() not in cleaned.lower():
                    print(f"❌ Over-redacted: '{term}' should be preserved")
                    success = False

        if success:
            print("✅ PASSED")
        else:
            print("❌ FAILED")

        return success

    except requests.exceptions.ConnectionError:
        print("❌ FAILED: Cannot connect to API. Is it running?")
        print("   Start with: uvicorn api.anonymise:app --reload --port 8000")
        return False
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def main():
    print("\n" + "="*70)
    print("VERIFYING PRIORITY 1 FIXES")
    print("="*70)

    results = []

    # Test 1: Android over-redaction fix
    results.append(test_fix(
        "Fix 1: Android should NOT be redacted",
        "[26/02/2026, 10:00] User: The dark mode on Android is broken",
        expected_tokens=["SENDER"],  # Only sender, not ORG
        should_not_contain=["Android", "dark mode", "broken"]
    ))

    # Test 2: IBAN with spaces
    results.append(test_fix(
        "Fix 2: IBAN with spaces",
        "[26/02/2026, 14:05] Priya: Mine is DE89 3704 0044 0532 0130 00",
        expected_tokens=["SENDER", "IBAN", "PERSON"],  # IBAN, not PHONE
        should_not_contain=[]
    ))

    # Test 3: iOS should not be redacted
    results.append(test_fix(
        "Fix 1b: iOS should NOT be redacted",
        "[26/02/2026, 10:00] User: The app crashes on iOS 17",
        expected_tokens=["SENDER"],
        should_not_contain=["iOS", "app", "crashes"]
    ))

    # Test 4: IBAN without spaces (regression check)
    results.append(test_fix(
        "Fix 2b: IBAN without spaces still works",
        "[26/02/2026, 14:05] User: My IBAN is DE89370400440532013000",
        expected_tokens=["SENDER", "IBAN"],
        should_not_contain=[]
    ))

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("✅ ALL FIXES VERIFIED! Ready to run full benchmark.")
    else:
        print("❌ Some fixes failed. Debug before running full benchmark.")

    print(f"\nNext step: cd tests && python run_benchmark.py")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()

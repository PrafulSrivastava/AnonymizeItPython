"""
Quick test script for manual testing of individual messages.
Useful for development and debugging.
"""

import requests
import json
import sys


def test_message(message: str, blocklist: str = "", api_url: str = "http://localhost:8000"):
    """
    Test a single message against the anonymization API.

    Args:
        message: Raw WhatsApp message text
        blocklist: Comma-separated blocklist terms
        api_url: Base URL of the API
    """
    endpoint = f"{api_url.rstrip('/')}/api/anonymise"

    payload = {
        "rawText": message,
        "blocklist": blocklist,
        "sessionId": "quick_test"
    }

    print(f"\n{'='*70}")
    print("QUICK TEST")
    print(f"{'='*70}")
    print(f"API: {endpoint}")
    print(f"\nOriginal:\n{message}")
    print(f"\nBlocklist: {blocklist if blocklist else '(none)'}")

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code != 200:
            print(f"\n✗ Error: HTTP {response.status_code}")
            print(response.text)
            return

        result = response.json()["result"]

        # Print results
        print(f"\n{'='*70}")
        print("RESULT")
        print(f"{'='*70}")
        print(f"\nCleaned text:\n{result['cleanedText']}")

        print(f"\nTokens ({len(result['tokens'])}):")
        for token in result['tokens']:
            print(f"  [{token['type']}] {token['value']} (confidence: {token['confidence']:.2f})")

        print(f"\nConfidence:")
        print(f"  Overall: {result['confidence']['overall']:.2f}")
        print(f"  Routing: {result['confidence']['routing']}")
        print(f"  Signals:")
        print(f"    - Regex coverage: {result['confidence']['signals']['regexCoverage']:.2f}")
        print(f"    - NER confidence: {result['confidence']['signals']['nerConfidence']:.2f}")
        print(f"    - QI count: {result['confidence']['signals']['quasiIdentifierCount']}")
        print(f"    - Residual density: {result['confidence']['signals']['residualTokenDensity']:.2f}")

        if result['confidence']['failureReasons']:
            print(f"\n  Failure reasons:")
            for reason in result['confidence']['failureReasons']:
                print(f"    - {reason}")

        print(f"\nFlags:")
        for key, value in result['flags'].items():
            print(f"  {key}: {value}")

        print(f"\n{'='*70}")
        print("✓ Test completed successfully")
        print(f"{'='*70}\n")

    except requests.exceptions.RequestException as e:
        print(f"\n✗ Request failed: {e}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Example usage
    if len(sys.argv) > 1:
        message = sys.argv[1]
        blocklist = sys.argv[2] if len(sys.argv) > 2 else ""
        test_message(message, blocklist)
    else:
        # Default test message
        test_message(
            "[26/02/2026, 09:14] Sarah Müller: Hi! My email is sarah.mueller@gmail.com",
            blocklist=""
        )

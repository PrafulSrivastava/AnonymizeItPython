"""
Benchmark runner for WhatsApp anonymization pipeline.
Executes test cases and evaluates accuracy against expected results.
"""

import argparse
import json
import requests
import sys
import io
from typing import Dict, List, Any
from datetime import datetime
from test_cases import get_all_test_cases, TEST_CASES, REAL_CHAT_CASES

# Fix Unicode encoding on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


class BenchmarkRunner:
    """Runs benchmark tests against the anonymization API."""

    def __init__(self, api_url: str):
        """
        Initialize benchmark runner.

        Args:
            api_url: Base URL of the API (e.g., http://localhost:8000)
        """
        self.api_url = api_url.rstrip('/')
        self.endpoint = f"{self.api_url}/api/anonymise"
        self.results = []

    def run_single_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a single test case against the API.

        Args:
            test_case: Test case dictionary with input and expected results

        Returns:
            Result dictionary with pass/fail status and details
        """
        test_id = test_case["id"]
        print(f"\n{'='*70}")
        print(f"Running {test_id}: {test_case['description']}")
        print(f"{'='*70}")

        # Make API request
        try:
            response = requests.post(
                self.endpoint,
                json=test_case["input"],
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code != 200:
                return {
                    "test_id": test_id,
                    "group": test_case.get("group", "unknown"),
                    "description": test_case.get("description", ""),
                    "passed": False,
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "failures": [f"HTTP {response.status_code}"],
                    "details": {}
                }

            result = response.json()["result"]

        except requests.exceptions.RequestException as e:
            return {
                "test_id": test_id,
                "group": test_case.get("group", "unknown"),
                "description": test_case.get("description", ""),
                "passed": False,
                "error": f"Request failed: {str(e)}",
                "failures": [f"Request failed: {str(e)}"],
                "details": {}
            }

        # Evaluate result
        try:
            evaluation = self.evaluate_result(test_case, result)

            print(f"\n[OK] Status: {'PASS' if evaluation['passed'] else 'FAIL'}")
            print(f"  Routing: {result['confidence']['routing']}")
            print(f"  Confidence: {result['confidence']['overall']:.2f}")
            print(f"  Tokens found: {len(result['tokens'])}")
            print(f"  Token types: {set(t['type'] for t in result['tokens'])}")

            if evaluation['failures']:
                print(f"\n[X] Failures:")
                for failure in evaluation['failures']:
                    print(f"  - {failure}")

            print(f"\nCleaned text:\n  {result['cleanedText']}")

            return {
                "test_id": test_id,
                "group": test_case["group"],
                "description": test_case["description"],
                "passed": evaluation["passed"],
                "failures": evaluation["failures"],
                "details": {
                    "original_text": test_case["input"]["rawText"],
                    "cleaned_text": result["cleanedText"],
                    "tokens": result["tokens"],
                    "confidence": result["confidence"],
                    "flags": result["flags"],
                    "expected_routing": test_case.get("expected_routing", []),
                    "actual_routing": result["confidence"]["routing"]
                }
            }
        except Exception as e:
            print(f"\n[X] Evaluation error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "test_id": test_id,
                "group": test_case.get("group", "unknown"),
                "description": test_case.get("description", ""),
                "passed": False,
                "error": f"Evaluation failed: {str(e)}",
                "failures": [f"Evaluation error: {str(e)}"],
                "details": {}
            }

    def evaluate_result(self, test_case: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate if the result meets the test case expectations.

        Args:
            test_case: Test case with expected results
            result: API response result

        Returns:
            Dictionary with passed flag and list of failures
        """
        failures = []
        cleaned_text = result["cleanedText"]
        token_types = [t["type"] for t in result["tokens"]]

        # Check must_redact: all expected token types should be present
        must_redact = test_case.get("must_redact", [])
        for expected_type in must_redact:
            if expected_type not in token_types:
                failures.append(f"Missing expected token type: {expected_type}")

        # Check must_not_redact: specific text should still be present
        must_not_redact = test_case.get("must_not_redact", [])
        for text in must_not_redact:
            # Check if text or similar text is present (case-insensitive)
            if text.lower() not in cleaned_text.lower():
                failures.append(f"Over-redacted: '{text}' should be preserved")

        # Check routing decision
        expected_routing = test_case.get("expected_routing", [])
        actual_routing = result["confidence"]["routing"]
        if expected_routing and actual_routing not in expected_routing:
            failures.append(
                f"Unexpected routing: got '{actual_routing}', expected one of {expected_routing}"
            )

        # Special check for quasi-identifier test cases
        if test_case["group"] == "quasi_identifiers":
            qi_risk = result["flags"].get("quasi_identifier_risk", False)
            if not qi_risk and "TC10" in test_case["id"]:
                # TC10 specifically expects QI risk
                failures.append("Expected quasi_identifier_risk flag but not set")

        # Special check for true negatives (TC19, TC20)
        # Note: SENDER tokens don't count as over-redaction (they're message structure, not content PII)
        if test_case["group"] == "true_negatives":
            content_tokens = [t for t in result["tokens"] if t["type"] != "SENDER"]
            if len(content_tokens) > 0:
                failures.append(f"Over-redaction: found {len(content_tokens)} content tokens in clean message")

        passed = len(failures) == 0
        return {"passed": passed, "failures": failures}

    def run_all_tests(self, test_cases: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run all test cases and generate summary.

        Args:
            test_cases: Optional list of specific test cases to run

        Returns:
            Summary dictionary with results
        """
        if test_cases is None:
            test_cases = get_all_test_cases()

        print(f"\n{'='*70}")
        print(f"Starting benchmark run: {len(test_cases)} test cases")
        print(f"API endpoint: {self.endpoint}")
        print(f"{'='*70}")

        results = []
        for test_case in test_cases:
            result = self.run_single_test(test_case)
            results.append(result)

        # Generate summary
        passed_count = sum(1 for r in results if r["passed"])
        total_count = len(results)
        pass_rate = (passed_count / total_count) * 100 if total_count > 0 else 0

        summary = {
            "timestamp": datetime.now().isoformat(),
            "api_url": self.api_url,
            "total_tests": total_count,
            "passed": passed_count,
            "failed": total_count - passed_count,
            "pass_rate": pass_rate,
            "target_pass_rate": 85.0,  # 17/20 = 85%
            "meets_target": pass_rate >= 85.0,
            "results": results
        }

        self.results = results
        return summary

    def print_summary(self, summary: Dict[str, Any]):
        """Print formatted summary of results."""
        print(f"\n{'='*70}")
        print("BENCHMARK SUMMARY")
        print(f"{'='*70}")
        print(f"Total tests:     {summary['total_tests']}")
        print(f"Passed:          {summary['passed']} [OK]")
        print(f"Failed:          {summary['failed']} [X]")
        print(f"Pass rate:       {summary['pass_rate']:.1f}%")
        print(f"Target:          {summary['target_pass_rate']:.1f}%")
        print(f"Meets target:    {'YES [OK]' if summary['meets_target'] else 'NO [X]'}")

        # Group results by category
        print(f"\n{'='*70}")
        print("RESULTS BY GROUP")
        print(f"{'='*70}")

        groups = {}
        for result in summary["results"]:
            group = result["group"]
            if group not in groups:
                groups[group] = {"passed": 0, "failed": 0}
            if result["passed"]:
                groups[group]["passed"] += 1
            else:
                groups[group]["failed"] += 1

        for group, counts in sorted(groups.items()):
            total = counts["passed"] + counts["failed"]
            pass_rate = (counts["passed"] / total * 100) if total > 0 else 0
            status = "[OK]" if counts["failed"] == 0 else "[X]"
            print(f"{status} {group:25s} {counts['passed']}/{total} ({pass_rate:.0f}%)")

        # List failed tests
        failed_tests = [r for r in summary["results"] if not r["passed"]]
        if failed_tests:
            print(f"\n{'='*70}")
            print("FAILED TESTS")
            print(f"{'='*70}")
            for result in failed_tests:
                print(f"\n[X] {result['test_id']}: {result['description']}")
                for failure in result["failures"]:
                    print(f"  - {failure}")

    def save_results(self, summary: Dict[str, Any], output_file: str):
        """Save detailed results to JSON file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Results saved to: {output_file}")


def main():
    """Main entry point for benchmark runner."""
    parser = argparse.ArgumentParser(description="Run anonymization benchmark tests")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--output",
        default="benchmark_results.json",
        help="Output file for results (default: benchmark_results.json)"
    )
    parser.add_argument(
        "--group",
        help="Run only tests from specific group"
    )
    parser.add_argument(
        "--test-id",
        help="Run only specific test case by ID"
    )
    parser.add_argument(
        "--real-chat-only",
        action="store_true",
        help="Run only real chat test cases"
    )

    args = parser.parse_args()

    # Select test cases based on arguments
    if args.test_id:
        from test_cases import get_test_case_by_id
        test_cases = [get_test_case_by_id(args.test_id)]
    elif args.group:
        from test_cases import get_test_cases_by_group
        test_cases = get_test_cases_by_group(args.group)
    elif args.real_chat_only:
        test_cases = REAL_CHAT_CASES
    else:
        test_cases = get_all_test_cases()

    # Run benchmark
    runner = BenchmarkRunner(args.url)

    try:
        summary = runner.run_all_tests(test_cases)
        runner.print_summary(summary)
        runner.save_results(summary, args.output)

        # Exit with appropriate code
        sys.exit(0 if summary["meets_target"] else 1)

    except Exception as e:
        print(f"\n[X] Benchmark failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()

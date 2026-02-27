#!/usr/bin/env python3
"""
Local testing script for OAuth authentication and usage tracking.

This script helps verify the implementation without deploying to production.

Prerequisites:
1. Set up .env file with required environment variables
2. Run database migration
3. Start local server: uvicorn api.anonymise:app --reload --port 8000

Usage:
    python test_auth_local.py
"""

import requests
import json
from typing import Dict, Optional

BASE_URL = "http://localhost:8000"

# ANSI color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_test(name: str):
    """Print test name."""
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}TEST: {name}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}")


def print_success(message: str):
    """Print success message."""
    print(f"{GREEN}✓ {message}{RESET}")


def print_error(message: str):
    """Print error message."""
    print(f"{RED}✗ {message}{RESET}")


def print_info(message: str):
    """Print info message."""
    print(f"{YELLOW}ℹ {message}{RESET}")


def test_health_check() -> bool:
    """Test 1: Health check endpoint."""
    print_test("Health Check")

    try:
        response = requests.get(f"{BASE_URL}/")
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "ok":
            print_success(f"Server is running: {data.get('service')}")
            return True
        else:
            print_error("Unexpected health check response")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to server. Is it running?")
        print_info("Start with: uvicorn api.anonymise:app --reload --port 8000")
        return False
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False


def test_anonymous_usage() -> bool:
    """Test 2: Anonymous usage limits."""
    print_test("Anonymous Usage Limits")

    # Check usage before
    try:
        response = requests.get(f"{BASE_URL}/api/auth/usage")
        usage = response.json()
        print_info(f"Current anonymous usage: {usage['requests_used']}/{usage['quota_limit']}")
    except Exception as e:
        print_error(f"Failed to check usage: {e}")
        return False

    # Make requests until limit
    payload = {
        "rawText": "[26/02/2026, 09:14] Test: Hello world",
        "blocklist": "",
        "sessionId": "test_anonymous"
    }

    success_count = 0
    for i in range(6):
        try:
            response = requests.post(
                f"{BASE_URL}/api/anonymise",
                json=payload
            )

            if response.status_code == 200:
                success_count += 1
                print_success(f"Request {i+1}: Success (200 OK)")
            elif response.status_code == 401:
                print_success(f"Request {i+1}: Blocked (401 Unauthorized) - Limit working!")
                break
            else:
                print_error(f"Request {i+1}: Unexpected status {response.status_code}")
                print_error(f"Response: {response.text}")
        except Exception as e:
            print_error(f"Request {i+1} failed: {e}")

    # Check usage after
    try:
        response = requests.get(f"{BASE_URL}/api/auth/usage")
        usage = response.json()
        print_info(f"Final anonymous usage: {usage['requests_used']}/{usage['quota_limit']}")
    except Exception as e:
        print_error(f"Failed to check usage: {e}")

    if success_count >= 5:
        print_error("Anonymous limit not enforced! More than 5 requests succeeded.")
        return False

    print_success(f"Anonymous usage limit working correctly ({success_count}/5 requests)")
    return True


def test_auth_endpoints() -> bool:
    """Test 3: Authentication endpoints."""
    print_test("Authentication Endpoints")

    # Test /api/auth/me without credentials (should fail)
    try:
        response = requests.get(f"{BASE_URL}/api/auth/me")
        if response.status_code == 401:
            print_success("/api/auth/me returns 401 without credentials")
        else:
            print_error(f"/api/auth/me returned {response.status_code} instead of 401")
            return False
    except Exception as e:
        print_error(f"Failed to test /api/auth/me: {e}")
        return False

    # Test /api/auth/login (should redirect to Google)
    try:
        response = requests.get(f"{BASE_URL}/api/auth/login", allow_redirects=False)
        if response.status_code in [302, 307]:
            location = response.headers.get('location', '')
            if 'google' in location.lower():
                print_success("/api/auth/login redirects to Google OAuth")
            else:
                print_error(f"Unexpected redirect: {location}")
                return False
        else:
            print_error(f"/api/auth/login returned {response.status_code} instead of redirect")
            return False
    except Exception as e:
        print_error(f"Failed to test /api/auth/login: {e}")
        return False

    # Test /api/auth/usage (anonymous)
    try:
        response = requests.get(f"{BASE_URL}/api/auth/usage")
        usage = response.json()
        if not usage.get('is_authenticated'):
            print_success("/api/auth/usage returns anonymous stats")
        else:
            print_error("Usage endpoint shows authenticated without login")
            return False
    except Exception as e:
        print_error(f"Failed to test /api/auth/usage: {e}")
        return False

    return True


def test_oauth_flow_interactive():
    """Test 4: Interactive OAuth flow."""
    print_test("OAuth Flow (Interactive)")

    print_info("To test the full OAuth flow:")
    print_info("1. Open your browser to http://localhost:8000")
    print_info("2. Open browser DevTools (F12)")
    print_info("3. Click 'Login with Google'")
    print_info("4. Complete the OAuth flow")
    print_info("5. Check that you're logged in (avatar appears)")
    print_info("6. Try making requests (should work beyond 5)")
    print_info("7. Click 'Logout' and verify you're logged out")

    input(f"\n{YELLOW}Press Enter after testing the OAuth flow...{RESET}")

    # Verify database has user
    print_info("\nTo verify database records:")
    print_info("psql $POSTGRES_URL -c 'SELECT id, email, name FROM users;'")
    print_info("psql $POSTGRES_URL -c 'SELECT * FROM usage;'")


def test_database_connection() -> bool:
    """Test 5: Database connection (indirect)."""
    print_test("Database Connection")

    # We can't directly test DB without running the app,
    # but we can check if endpoints that require DB work
    try:
        response = requests.get(f"{BASE_URL}/api/auth/usage")
        if response.status_code == 200:
            print_success("Database connection working (usage endpoint accessible)")
            return True
        else:
            print_error(f"Usage endpoint returned {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Database connection test failed: {e}")
        print_info("Check POSTGRES_URL environment variable")
        return False


def main():
    """Run all tests."""
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}OAuth Authentication Test Suite{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}")

    print_info("Testing local server at http://localhost:8000")
    print_info("Make sure server is running!")

    results = {
        "Health Check": test_health_check(),
    }

    # Only continue if server is running
    if results["Health Check"]:
        results["Database Connection"] = test_database_connection()
        results["Authentication Endpoints"] = test_auth_endpoints()
        results["Anonymous Usage Limits"] = test_anonymous_usage()

        # Interactive test
        test_oauth_flow_interactive()

    # Summary
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}Test Summary{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_test in results.items():
        status = f"{GREEN}PASS{RESET}" if passed_test else f"{RED}FAIL{RESET}"
        print(f"{test_name}: {status}")

    print(f"\n{BLUE}Total: {passed}/{total} tests passed{RESET}")

    if passed == total:
        print(f"\n{GREEN}✓ All automated tests passed!{RESET}")
        print_info("Don't forget to test the interactive OAuth flow")
    else:
        print(f"\n{RED}✗ Some tests failed{RESET}")
        print_info("Check the errors above and verify your setup")

    print(f"\n{BLUE}Next Steps:{RESET}")
    print("1. Complete interactive OAuth testing")
    print("2. Check OAUTH_SETUP.md for deployment instructions")
    print("3. Deploy to Vercel for production testing")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Tests interrupted by user{RESET}")
    except Exception as e:
        print(f"\n{RED}Unexpected error: {e}{RESET}")

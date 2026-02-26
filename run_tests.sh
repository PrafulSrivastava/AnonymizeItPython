#!/bin/bash
# Helper script to run tests easily

set -e

echo "=================================================="
echo "WhatsApp Anonymization Pipeline - Test Runner"
echo "=================================================="

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Virtual environment not detected"
    echo "   Activate with: source venv/bin/activate"
    exit 1
fi

# Check if API is running
echo ""
echo "Checking API status..."
if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "✓ API is running on http://localhost:8000"
else
    echo "✗ API is not running!"
    echo ""
    echo "Start the API first:"
    echo "  uvicorn api.anonymise:app --reload --port 8000"
    exit 1
fi

# Run tests based on argument
echo ""
case "${1:-all}" in
    all)
        echo "Running all 23 test cases..."
        python tests/run_benchmark.py --url http://localhost:8000
        ;;
    quick)
        echo "Running quick test..."
        python tests/quick_test.py "[26/02/2026, 09:14] Sarah: My email is sarah@test.com"
        ;;
    critical)
        echo "Running critical tests (true negatives)..."
        python tests/run_benchmark.py --url http://localhost:8000 --group true_negatives
        ;;
    group)
        if [ -z "$2" ]; then
            echo "Usage: ./run_tests.sh group <group_name>"
            echo "Groups: structural_pii, age_dob, ner_edge_cases, quasi_identifiers, obfuscated_pii, multilingual, sensitive_topics, true_negatives, real_chat"
            exit 1
        fi
        echo "Running tests for group: $2"
        python tests/run_benchmark.py --url http://localhost:8000 --group "$2"
        ;;
    single)
        if [ -z "$2" ]; then
            echo "Usage: ./run_tests.sh single <test_id>"
            echo "Example: ./run_tests.sh single TC07"
            exit 1
        fi
        echo "Running single test: $2"
        python tests/run_benchmark.py --url http://localhost:8000 --test-id "$2"
        ;;
    *)
        echo "Usage: ./run_tests.sh [all|quick|critical|group|single]"
        echo ""
        echo "Commands:"
        echo "  all       - Run all 23 test cases (default)"
        echo "  quick     - Run quick manual test"
        echo "  critical  - Run critical tests (true negatives)"
        echo "  group     - Run specific test group"
        echo "  single    - Run single test case by ID"
        exit 1
        ;;
esac

echo ""
echo "=================================================="
echo "✓ Test run completed"
echo "=================================================="

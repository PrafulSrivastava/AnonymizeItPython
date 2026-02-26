@echo off
REM Helper script to run tests easily (Windows)

echo ==================================================
echo WhatsApp Anonymization Pipeline - Test Runner
echo ==================================================

REM Check if virtual environment is activated
if "%VIRTUAL_ENV%"=="" (
    echo WARNING: Virtual environment not detected
    echo    Activate with: venv\Scripts\activate
    exit /b 1
)

REM Check if API is running
echo.
echo Checking API status...
curl -s http://localhost:8000/ >nul 2>&1
if errorlevel 1 (
    echo ERROR: API is not running!
    echo.
    echo Start the API first:
    echo   uvicorn api.anonymise:app --reload --port 8000
    exit /b 1
)
echo SUCCESS: API is running on http://localhost:8000

REM Run tests based on argument
echo.
if "%1"=="" goto all
if "%1"=="all" goto all
if "%1"=="quick" goto quick
if "%1"=="critical" goto critical
if "%1"=="group" goto group
if "%1"=="single" goto single
goto usage

:all
echo Running all 23 test cases...
python tests\run_benchmark.py --url http://localhost:8000
goto end

:quick
echo Running quick test...
python tests\quick_test.py "[26/02/2026, 09:14] Sarah: My email is sarah@test.com"
goto end

:critical
echo Running critical tests (true negatives)...
python tests\run_benchmark.py --url http://localhost:8000 --group true_negatives
goto end

:group
if "%2"=="" (
    echo Usage: run_tests.bat group ^<group_name^>
    echo Groups: structural_pii, age_dob, ner_edge_cases, quasi_identifiers, obfuscated_pii, multilingual, sensitive_topics, true_negatives, real_chat
    exit /b 1
)
echo Running tests for group: %2
python tests\run_benchmark.py --url http://localhost:8000 --group %2
goto end

:single
if "%2"=="" (
    echo Usage: run_tests.bat single ^<test_id^>
    echo Example: run_tests.bat single TC07
    exit /b 1
)
echo Running single test: %2
python tests\run_benchmark.py --url http://localhost:8000 --test-id %2
goto end

:usage
echo Usage: run_tests.bat [all^|quick^|critical^|group^|single]
echo.
echo Commands:
echo   all       - Run all 23 test cases (default)
echo   quick     - Run quick manual test
echo   critical  - Run critical tests (true negatives)
echo   group     - Run specific test group
echo   single    - Run single test case by ID
exit /b 1

:end
echo.
echo ==================================================
echo SUCCESS: Test run completed
echo ==================================================

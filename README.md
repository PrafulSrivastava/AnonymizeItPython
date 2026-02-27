# Text Anonymization Platform (Python)

A serverless Python implementation of text message anonymization using spaCy and Microsoft Presidio for high-accuracy PII detection and redaction.

## Overview

This system processes text messages from various sources (chat apps, SMS, emails, etc.), detects and redacts PII (names, emails, phone numbers, locations, etc.), and provides confidence scoring for routing decisions. Supports multiple text formats including WhatsApp, Telegram, Slack, and plain text.

### Key Features

- **Multi-stage pipeline**: Regex → NER → Blocklist → Scoring → Validation
- **Dual NER engines**: spaCy (en_core_web_lg, de_core_news_lg) + Microsoft Presidio
- **Multilingual support**: English and German language detection
- **Confidence scoring**: Weighted scoring with routing decisions (pass/pass_flagged/review)
- **Quasi-identifier detection**: Identifies role + location + age combinations
- **Privacy-preserving**: Age bucketing, location granularity filtering
- **Serverless ready**: Optimized for Vercel deployment with cold start handling

## Architecture

### Pipeline Stages

1. **Regex Stripper** - Extracts structural PII using patterns:
   - Message headers (timestamp + sender from various formats)
   - Phone numbers (using google-libphonenumber)
   - Email addresses (including obfuscated formats)
   - URLs and social media handles
   - IBANs with checksum validation
   - Dates of birth and ages (with bucketing)

2. **NER Engine** - Named entity recognition:
   - Presidio analyzer (primary, high precision)
   - spaCy English model (en_core_web_lg)
   - spaCy German model (de_core_news_lg, triggered by language detection)
   - Entity types: PERSON, ORG, LOCATION
   - Location filtering: Countries preserved, cities redacted

3. **Blocklist Matcher** - Custom term matching:
   - Aho-Corasick automaton for efficient multi-pattern matching
   - Case-insensitive, whole-word boundary validation
   - Quasi-identifier detection (role keywords + locations + ages)

4. **Confidence Scorer** - Multi-signal confidence calculation:
   - Regex coverage (30% weight)
   - NER confidence (35% weight)
   - Quasi-identifier score (20% weight)
   - Residual token density (15% weight)
   - Routing: pass (≥0.90), pass_flagged (0.75-0.89), review (<0.75)

5. **Validator** - Output validation:
   - Re-run regex suite to detect PII leakage
   - Token integrity check (format validation)
   - Minimum content check (>60% redaction flagging)

## Installation

### Local Development

1. **Clone repository**
   ```bash
   git clone <repository-url>
   cd AnonymizeItPython
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

   **Note:** The spaCy models (~500MB) will be installed automatically from direct wheel URLs.

4. **Verify installation**
   ```bash
   python -c "import spacy; print(spacy.load('en_core_web_lg'))"
   python -c "import spacy; print(spacy.load('de_core_news_lg'))"
   ```

### Vercel Deployment

1. **Install Vercel CLI**
   ```bash
   npm install -g vercel
   ```

2. **Deploy**
   ```bash
   vercel deploy
   ```

   **Important:** First deployment may timeout due to model loading. Subsequent requests will be fast (warm containers).

3. **Environment variables** (if needed)
   ```bash
   vercel env add PYTHON_VERSION 3.11
   ```

## Usage

### Local Server

Start the development server:

```bash
uvicorn api.anonymise:app --reload --port 8000
```

### API Endpoint

**POST** `/api/anonymise`

**Request Body:**
```json
{
  "rawText": "[26/02/2026, 09:14] Sarah: My email is sarah@test.com",
  "blocklist": "Sarah,confidential",
  "sessionId": "test_session_01"
}
```

**Response:**
```json
{
  "result": {
    "messageId": "abc123...",
    "cleanedText": "[SENDER] My email is [EMAIL_01]",
    "tokens": [
      {
        "type": "SENDER",
        "value": "[SENDER]",
        "startIndex": 0,
        "endIndex": 5,
        "confidence": 1.0,
        "lowConfidence": false
      },
      {
        "type": "EMAIL",
        "value": "[EMAIL_01]",
        "startIndex": 13,
        "endIndex": 30,
        "confidence": 1.0,
        "lowConfidence": false
      }
    ],
    "confidence": {
      "overall": 0.92,
      "routing": "pass",
      "signals": {
        "regexCoverage": 0.95,
        "nerConfidence": 0.88,
        "quasiIdentifierCount": 0,
        "residualTokenDensity": 0.75
      },
      "failureReasons": []
    },
    "flags": {
      "quasi_identifier_risk": false,
      "low_signal": false
    },
    "metadata": {
      "original_word_count": 8,
      "cleaned_word_count": 6,
      "token_count": 2
    }
  }
}
```

**Note:** The `original` field in tokens is **never** serialized to the response (server-side only).

### Example Requests

**Basic PII (email + name):**
```bash
curl -X POST http://localhost:8000/api/anonymise \
  -H "Content-Type: application/json" \
  -d '{
    "rawText": "[26/02/2026, 09:14] Sarah Müller: My email is sarah.mueller@gmail.com",
    "blocklist": "",
    "sessionId": "test_01"
  }'
```

**Phone number + handle:**
```bash
curl -X POST http://localhost:8000/api/anonymise \
  -H "Content-Type: application/json" \
  -d '{
    "rawText": "[26/02/2026, 11:32] James: Call me at +44 7911 123456 or follow @jamesobrien",
    "blocklist": "",
    "sessionId": "test_02"
  }'
```

**Blocklist with short names:**
```bash
curl -X POST http://localhost:8000/api/anonymise \
  -H "Content-Type: application/json" \
  -d '{
    "rawText": "[26/02/2026, 13:01] Susi: Mo asked about the feature",
    "blocklist": "Susi,Mo",
    "sessionId": "test_03"
  }'
```

**Clean message (no PII):**
```bash
curl -X POST http://localhost:8000/api/anonymise \
  -H "Content-Type: application/json" \
  -d '{
    "rawText": "[26/02/2026, 10:00] User: The dark mode on Android is broken",
    "blocklist": "",
    "sessionId": "test_04"
  }'
```

## Token Types

| Type | Description | Example |
|------|-------------|---------|
| `SENDER` | WhatsApp message sender | `[SENDER]` |
| `PHONE` | Phone numbers | `[PHONE_01]`, `[PHONE_02]` |
| `EMAIL` | Email addresses | `[EMAIL_01]` |
| `URL` | Web URLs | `[URL_01]` |
| `HANDLE` | Social media handles | `[HANDLE_01]` |
| `IBAN` | Bank account numbers | `[IBAN_01]` |
| `DOB` | Dates of birth | `[DOB_01]` |
| `AGE` | Ages (bucketed) | `[AGE_30s]`, `[AGE_60s]` |
| `PERSON` | Person names (NER) | `[PERSON_01]` |
| `ORG` | Organizations (NER) | `[ORG_01]` |
| `LOCATION` | Locations (NER, cities only) | `[LOCATION_01]` |
| `BLOCKLIST` | Custom blocklist terms | `[BLOCKLIST_01]` |

## Configuration

### Confidence Scoring Weights

Adjust weights in `/lib/pipeline/confidence_scorer.py`:

```python
overall = (
    (regex_coverage * 0.30) +
    (ner_confidence * 0.35) +
    (qi_score * 0.20) +
    (residual_density * 0.15)
)
```

### Routing Thresholds

Modify thresholds in `confidence_scorer.py`:

```python
if overall_score >= 0.90:
    return "pass"
elif overall_score >= 0.75:
    return "pass_flagged"
else:
    return "review"
```

### Role Keywords (Quasi-identifiers)

Add/remove keywords in `/lib/pipeline/blocklist.py`:

```python
ROLE_KEYWORDS = {
    "manager", "developer", "designer", ...
}
```

## Performance

### Cold Start
- First request: ~5-10 seconds (model loading)
- Warm requests: <2 seconds

### Memory Usage
- spaCy models: ~500MB RAM
- Total container: ~600-700MB

### Optimization Tips
1. Use module-level model loading (already implemented)
2. Enable Vercel function warming
3. Consider smaller models for faster cold starts (en_core_web_sm)

## Known Limitations

1. **Model size**: spaCy models are large (~500MB). May hit Vercel limits.
   - **Mitigation**: Direct wheel URLs, external model hosting, or smaller models.

2. **Cold starts**: First request slow on serverless.
   - **Mitigation**: Function warming, health check endpoint.

3. **Language support**: Currently English + German only.
   - **Future**: Add more spaCy models for additional languages.

4. **Japanese/Asian languages**: No support for non-Latin scripts.
   - **Expected**: Some test cases may fail (acceptable for 17/20 target).

## Testing

### Manual Testing

Use the example curl commands above to test various scenarios:
- ✅ Basic PII (emails, phones, names)
- ✅ Obfuscated formats (email [at] domain dot com)
- ✅ Multilingual (German names with umlauts)
- ✅ Quasi-identifiers (role + location + age)
- ✅ Clean messages (no over-redaction)

### Automated Testing

*Coming in Phase 10* - See plan for 20 structured test cases and benchmark runner.

## Security

- **Never serializes `original` field** in RedactionToken (Pydantic serializer)
- **Validation layer** prevents PII leakage
- **Serverless isolation** (Vercel containers)
- **No data persistence** (stateless processing)

## Troubleshooting

### Models not loading

```bash
# Verify models installed
python -m spacy validate

# Reinstall models
pip install --force-reinstall --no-deps \
  https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.7.1/en_core_web_lg-3.7.1-py3-none-any.whl
```

### Vercel timeout on first request

- Normal behavior (cold start)
- Retry request after 10-15 seconds
- Subsequent requests will be fast

### "original field" appearing in response

- Check Pydantic version (must be 2.5.0+)
- Verify `@field_serializer` in `lib/types.py`

## Contributing

1. Fork repository
2. Create feature branch
3. Make changes with tests
4. Submit pull request

## License

[Add license information]

## Contact

[Add contact information]

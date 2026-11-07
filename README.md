# Text Anonymization Platform (Python)

A serverless Python implementation of text message anonymization using spaCy and Microsoft Presidio for high-accuracy PII detection and redaction.

## Overview

This system processes text messages from various sources (chat apps, SMS, emails, etc.), detects and redacts PII (names, emails, phone numbers, locations, etc.), and provides confidence scoring for routing decisions. Supports multiple text formats including WhatsApp, Telegram, Slack, and plain text.

### Key Features

- **Multi-stage pipeline**: Regex → NER → Blocklist → Scoring → Validation
- **Dual NER engines**: spaCy (en_core_web_sm/lg, de_core_news_sm/lg) + Microsoft Presidio
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

### Private Chat Workflow (anonymize → LLM → re-enrich)

**POST** `/api/chat` anonymizes the prompt, sends only the anonymized text to an
OpenAI-compatible LLM, and restores the original values in the answer. The
placeholder-to-original mapping exists only in memory for that one request.

Configure the LLM in `.env` (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`,
`LLM_TIMEOUT_SECONDS`). Defaults target LM Studio at `http://localhost:1234/v1`.

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Draft a two-sentence reply to Marcus Weber (marcus.weber@acmecorp.com) confirming our call on +49 170 555 0198.", "blocklist": "Marcus Weber,Marcus"}'
```

The response contains `answer` (re-enriched), `anonymizedPrompt` (exactly what the
LLM saw), `anonymizedAnswer`, the placeholders sent and restored, any
`unknownPlaceholders` the model invented, and the anonymizer's `routing`.
Prompts are limited to 8000 characters. Set `"strict": true` to refuse sending
prompts the anonymizer routes to `review` (HTTP 422).

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

## Deploying to Vercel (hackathon / demo)

### Required environment variables

| Variable | Purpose | Example |
|---|---|---|
| `LLM_BASE_URL` | OpenAI-compatible API base URL | `https://api.x.ai/v1` |
| `LLM_API_KEY` | API key for the LLM | `xai-…` |
| `LLM_MODEL` | Model identifier | `grok-4.20-0309-non-reasoning` |

All other variables are optional for the demo (see `.env.example` for the full list).

### Optional environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SPACY_MODEL_SIZE` | `sm` | Use `lg` locally for higher accuracy |
| `LLM_TIMEOUT_SECONDS` | `120` | LLM request timeout |
| `CORS_ORIGINS` | localhost | Comma-separated allowed origins |
| `POSTGRES_URL` | *(unset)* | Enables usage tracking & auth |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | *(unset)* | Enables Google OAuth |
| `JWT_SECRET_KEY` | insecure default | Sign JWT cookies (set when using OAuth) |
| `FREE_TIER_LIMIT` | `5` | Anonymous request limit (requires DB) |

### Steps

1. Push this branch to GitHub (or fork the repo).
2. Import the project into [Vercel](https://vercel.com/new).
3. Add the required env vars in **Project → Settings → Environment Variables**.
4. Deploy. Vercel reads `vercel.json` automatically:
   - All routes → `api/anonymise.py` (FastAPI via Mangum)
   - Function runtime: Python 3.12, max duration 60 s
5. The frontend is served at `/` and `/chat`; the API is at `/api/anonymise` and `/api/chat`.

### Bundle size (Hobby plan)

The deployment targets Vercel's **Hobby plan** (50 MB compressed function limit).

| Compressed wheel | Size |
|---|---|
| spacy 3.8.3 (Linux x86_64) | 7.0 MB |
| blis (spacy dep) | 3.7 MB |
| thinc + other spacy deps | 4.0 MB |
| en_core_web_sm-3.8.0 | 12.8 MB |
| de_core_news_sm-3.8.0 | 15.0 MB |
| presidio-analyzer | 0.6 MB |
| phonenumbers | 8.3 MB |
| pydantic + pydantic-core | 2.2 MB |
| fastapi + starlette + mangum + uvicorn | 0.8 MB |
| httpx + httpcore + anyio | 0.7 MB |
| python-jose (no cryptography extra) | 0.1 MB |
| authlib + itsdangerous + multipart | 0.2 MB |
| python-dotenv + pyahocorasick | 0.1 MB |
| **Estimated total** | **~55.5 MB** |

> **What was removed to fit:** `sqlalchemy`, `psycopg2-binary`, and the
> `[cryptography]` extra from `python-jose` are **not** in `requirements.txt`.
> The app handles their absence gracefully (all three default to no-op /
> disabled when missing). Install them locally if you need DB / OAuth features
> (see bottom of `requirements.txt`).

The estimate may fall slightly under or over 50 MB depending on Vercel's
bundler; if the deploy is rejected on Hobby, upgrade to **Pro** (250 MB limit)
or drop `de_core_news_sm` from `requirements.txt` (saves ~15 MB) and accept
English-only NER.

> **maxDuration 60 s** requires a **Pro** plan on Vercel. Hobby is capped at
> 10 s, which is too short for LLM calls. Reduce `maxDuration` to `10` and set
> `LLM_TIMEOUT_SECONDS=8` for a quick Hobby smoke-test of the anonymise
> pipeline only.

Set `SPACY_MODEL_SIZE=lg` **locally** (and install the lg model wheels) to get
higher NER accuracy in development.

### Running locally without a database

```bash
cp .env.example .env
# edit .env: set LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
uvicorn api.anonymise:app --reload --port 8000
```

The app starts, serves the frontend at `http://localhost:8000/`, and both
`/api/anonymise` and `/api/chat` work without `POSTGRES_URL` (all requests
are allowed in demo mode).

## Contributing

1. Fork repository
2. Create feature branch
3. Make changes with tests
4. Submit pull request

## License

[Add license information]

## Contact

[Add contact information]

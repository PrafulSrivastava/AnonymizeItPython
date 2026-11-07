# Text Anonymization Platform (Python)

A serverless Python implementation of text message anonymization using spaCy and Microsoft Presidio for high-accuracy PII detection and redaction.

## Overview

This system processes text messages from various sources (chat apps, SMS, emails, etc.), detects and redacts PII (names, emails, phone numbers, locations, etc.), and provides confidence scoring for routing decisions. Supports multiple text formats including WhatsApp, Telegram, Slack, and plain text.

On top of the anonymizer sits a **private chat**: a prompt is anonymized, only the
anonymized text goes to an AI model, and the original details are put back into the
answer before the user reads it. The model can optionally search the web through
[Exa](https://exa.ai/docs), with every query checked for personal details first.

### Key Features

- **Multi-stage pipeline**: Regex → NER → Blocklist → Scoring → Validation
- **Dual NER engines**: spaCy (en_core_web_lg, de_core_news_lg) + Microsoft Presidio
- **Multilingual support**: English and German language detection
- **Confidence scoring**: Weighted scoring with routing decisions (pass/pass_flagged/review)
- **Quasi-identifier detection**: Identifies role + location + age combinations
- **Privacy-preserving**: Age bucketing, location granularity filtering
- **Serverless ready**: Optimized for Vercel deployment with cold start handling
- **Private chat workflow**: Anonymize → any OpenAI-compatible LLM (e.g. LM Studio) → re-enrich, with a web UI at `/chat`
- **Private web search (optional)**: The model can search the web via Exa; queries containing personal details are blocked

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

5. **Start Postgres** (used for usage quotas; requires Docker)
   ```bash
   docker run -d --name anonymizeit-postgres -e POSTGRES_PASSWORD=postgres \
     -e POSTGRES_DB=anonymizeit -p 5432:5432 postgres:16-alpine
   docker exec -i anonymizeit-postgres psql -U postgres -d anonymizeit < migrations/001_initial_schema.sql
   ```
   On later runs, `docker start anonymizeit-postgres` is enough.

6. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   Set `POSTGRES_URL=postgresql://postgres:postgres@127.0.0.1:5432/anonymizeit` and a
   `JWT_SECRET_KEY` (`openssl rand -hex 32`). For the private chat, point `LLM_BASE_URL`
   at your model server; for web search, add `EXA_API_KEY`. See [Environment variables](#environment-variables).
   Never commit `.env`.

7. **Start a model** (for the private chat): load a chat model in
   [LM Studio](https://lmstudio.ai/) and start its server. Models that support tool
   calling (e.g. `qwen/qwen3-vl-8b`) are needed for web search.

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

Then open:
- `http://localhost:8000/` for the anonymizer
- `http://localhost:8000/chat` for the private chat

`--reload` picks up code changes, but not `.env` changes; restart the server after editing `.env`.

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

```
prompt ──► anonymizer ──► "[PERSON_01] ([EMAIL_01]) …" ──► LLM ──► answer with placeholders
                │                                          │  ▲
                └── vault (in memory, this request only)   │  └── optional Exa web search
                                   │                       ▼      (queries checked first)
                                   └──────────────► re-enrich ──► answer with real details
```

**POST** `/api/chat` anonymizes the prompt, sends only the anonymized text to an
OpenAI-compatible LLM, and restores the original values in the answer. The
placeholder-to-original mapping (the "vault") exists only in memory for that one
request; it is never logged, returned or stored.

Configure the LLM in `.env` (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`,
`LLM_TIMEOUT_SECONDS`). Defaults target LM Studio at `http://localhost:1234/v1`.

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Draft a two-sentence reply to Marcus Weber (marcus.weber@acmecorp.com) confirming our call on +49 170 555 0198.", "blocklist": "Marcus Weber,Marcus"}'
```

**Request fields:**

| Field | Default | Description |
|---|---|---|
| `prompt` | required | 1–8000 characters |
| `blocklist` | `""` | Extra comma-separated words to hide |
| `strict` | `false` | Refuse to send prompts the anonymizer routes to `review` (HTTP 422); also makes the web search guard block any detection |
| `webSearch` | `false` | Let the model search the web (ignored if `EXA_API_KEY` is not set) |

**Response fields:** `answer` (re-enriched), `anonymizedPrompt` (exactly what the
LLM saw), `anonymizedAnswer`, `placeholdersSent`, `placeholdersRestored`,
`unknownPlaceholders` (placeholders the model invented), `routing`, `flags`, `model`,
`searches` and `sources`.

**Errors:** `401`/`403` quota reached, `422` invalid prompt or strict-mode refusal
(`detail.reasons` explains why), `500` a placeholder could not be safely restored
(nothing was sent), `502` the LLM server could not be reached.

#### Chat UI

`/chat` is a web front end for the same endpoint. Each answer has a **You / The AI**
switch: "You" shows the answer with your details restored (highlighted), "The AI"
shows exactly what the model saw and wrote. A receipt under each answer counts the
hidden and restored details. The composer offers "Hide extra words" (blocklist),
"Don't send if unsure" (strict mode) and, when configured, "Search the web".

#### Web search (optional, via Exa)

Set `EXA_API_KEY` in `.env` (get one at [dashboard.exa.ai](https://dashboard.exa.ai/api-keys))
and restart the server. The chat then shows a "Search the web" toggle;
`GET /api/chat/config` returns `{"webSearch": true}`.

- **The model decides** when to search, through a `web_search` tool, up to 3 searches
  per message. Each search asks Exa `/search` for 5 results with highlights.
- **Every query is checked before it leaves.** It is blocked if it contains a
  placeholder, any of the original values from the prompt, or a detected name, email,
  phone number, IBAN, birth date, handle or blocklisted word. Organizations, places,
  URLs and ages are allowed (normal searches like "ADA guidelines" trigger them),
  except in strict mode, which blocks any detection.
- **Failures never block the answer.** A blocked query or an Exa error is reported to
  the model, which answers without it; the UI shows a notice.
- The response lists every query in `searches` (`query`, `status`: `sent` / `blocked` /
  `failed`, `resultCount`) and the result links in `sources` (`title`, `url`).

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Search the web for what changed in the 2026 GOLD COPD report, then write a short note to my patient Hans Müller (hans.mueller@gmx.de) explaining what it means for his inhaler.", "webSearch": true}'
```

```json
{
  "anonymizedPrompt": "Search the web for what changed in the 2026 GOLD COPD report, then write a short note to my patient [PERSON_01] ([EMAIL_01]) explaining what it means for his inhaler.",
  "searches": [{"query": "2026 GOLD COPD report changes inhaler guidelines", "status": "sent", "resultCount": 5}],
  "sources": [{"title": "GOLD REPORT 2026 KEY CHANGES SUMMARY", "url": "https://goldcopd.org/..."}],
  "answer": "Dear Hans Müller, …"
}
```

Server logs never contain search queries or results. To audit Exa usage, use the
usage page in the Exa dashboard.

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

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_URL` | — | Postgres connection string (usage quotas) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | — | Google OAuth login |
| `JWT_SECRET_KEY` | — | Session/JWT signing key |
| `FREE_TIER_LIMIT` | `5` | Requests allowed before login is required |
| `CORS_ORIGINS` | `http://localhost:8000,http://127.0.0.1:8000` | Allowed browser origins |
| `LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible server for the private chat |
| `LLM_API_KEY` | `lm-studio` | API key for that server |
| `LLM_MODEL` | empty | Model id; empty picks the first non-embedding model the server lists |
| `LLM_TIMEOUT_SECONDS` | `120` | LLM request timeout |
| `EXA_API_KEY` | empty | Enables web search; leave empty to disable |
| `EXA_TIMEOUT_SECONDS` | `20` | Exa request timeout |

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

5. **Detection gaps**: Street addresses are often not detected, and some dates of
   birth or ID numbers are labelled as phone numbers (still hidden, but with the
   wrong type). Add such terms to the blocklist, and check "The AI" view in the chat.

6. **Pseudonymization, not anonymization**: Clinical or other context left in the
   text can still identify someone in combination (e.g. age + rare condition +
   postcode). Under GDPR this counts as pseudonymized data. Running the LLM locally
   (e.g. LM Studio) keeps it on your own machine.

7. **No chat memory**: Each private chat message is sent on its own; the model does
   not see earlier messages.

## Testing

### Manual Testing

Use the example curl commands above to test various scenarios:
- ✅ Basic PII (emails, phones, names)
- ✅ Obfuscated formats (email [at] domain dot com)
- ✅ Multilingual (German names with umlauts)
- ✅ Quasi-identifiers (role + location + age)
- ✅ Clean messages (no over-redaction)

### Automated Testing

```bash
./venv/bin/pytest tests -q --deselect tests/test_sample_cases.py --ignore tests/quick_test.py
```

Covers placeholder integrity, the vault and re-enrichment, input limits, the LLM
client (including tool calls), the private chat workflow, the web search client and
query guard, and the `/api/chat` endpoint. LLM and Exa calls are faked, so no model
server or API key is needed.

`tests/test_sample_cases.py` is the detection benchmark; 5 of its cases currently
fail (German/English code-switching and some city names). `tests/quick_test.py` is a
manual script, not a pytest suite.

## Security

- **Never serializes `original` field** in RedactionToken (Pydantic serializer)
- **Validation layer** prevents PII leakage
- **Serverless isolation** (Vercel containers)
- **No data persistence** (stateless processing)
- **Private chat vault** lives only in memory for one request; never logged, returned or stored
- **Fail closed**: if a placeholder cannot be restored safely, the prompt is not sent
- **Web search guard** blocks queries with placeholders, original values or detected personal details before they reach Exa

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

### Private chat says "Couldn't reach the AI model" (HTTP 502)

- Check that LM Studio's server is running and a model is loaded
- Check `LLM_BASE_URL` (LM Studio may serve on your LAN IP rather than `localhost`):
  `curl $LLM_BASE_URL/models`
- Restart uvicorn after changing `.env`

### "Search the web" toggle does not appear

- Set `EXA_API_KEY` in `.env` and restart uvicorn
- `curl http://localhost:8000/api/chat/config` should return `{"webSearch":true}`
- If the model never searches, make sure it supports tool calling, or ask it explicitly to search the web

### "Failed to fetch" in the browser

- Open the app on an origin listed in `CORS_ORIGINS` (default `localhost:8000` / `127.0.0.1:8000`)

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

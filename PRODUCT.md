# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
End users who want to chat with an AI assistant without handing it their personal data. They type or paste ordinary prompts (emails to draft, messages to reply to, documents to summarize) that naturally contain names, emails, phone numbers, addresses, and bank details. They mostly care about getting a good answer; the privacy happens around them.

## Product Purpose
A text anonymization platform. Its private chat workflow anonymizes a prompt, sends only the anonymized text to an AI model, and restores the original values in the model's answer before the user sees it. Success: the user gets a useful, natural answer containing their real details, and the AI model never received them.

## Positioning
The model only ever sees placeholders such as `[PERSON_01]` or `[EMAIL_01]`; the mapping back to real values lives in memory for one request and is never stored, logged, or returned. Users can inspect exactly what the model saw.

## Operating Context
- Runs as a FastAPI app (`api/anonymise.py`) serving static pages from `public/`.
- Private chat endpoint: `POST /api/chat` with `{prompt, blocklist, strict}`; returns `answer`, `anonymizedPrompt`, `anonymizedAnswer`, `placeholdersSent`, `placeholdersRestored`, `unknownPlaceholders`, `routing`, `flags`, `model`.
- The AI model is any OpenAI-compatible server; locally an LM Studio instance.
- Existing anonymizer tester page at `/` (`public/index.html`).
- Anonymous users have a free request quota; Google login exists but needs real OAuth credentials.

## Capabilities and Constraints
- Prompts up to 8000 characters.
- Each request is independent: no multi-turn memory on the server; placeholders are renumbered per request.
- Detection is imperfect (e.g. some city names are missed); `routing` (`pass`, `pass_flagged`, `review`) signals confidence, and `strict` refuses to send prompts routed to `review`.
- Optional custom blocklist of comma-separated terms to always redact.
- The model may emit placeholders it was never sent (`unknownPlaceholders`); these stay unrestored.

## Brand Commitments
- Product name in UI copy: "Text Anonymization Platform".
- The chat page was first modeled on Wispr Flow (https://wisprflow.ai/); the user then asked that it not read as a copy of Wispr. Keep the clean, calm chat structure, but not Wispr's palette or type.

## Evidence on Hand
No testimonials, customer logos, benchmarks, or pricing exist. Do not fabricate them.

## Product Principles
1. The answer comes first; privacy details are one click away, never in the way.
2. Always be truthful about what the model saw.
3. Never show or keep more personal data than the user already typed.
4. Be honest about detection limits instead of implying perfect protection.

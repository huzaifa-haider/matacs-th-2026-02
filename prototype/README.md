# Proposal triage prototype

Run locally with Python 3.11 or newer. Install pypdf for PDF extraction. DOCX/TXT extraction and scoring need no API key.

```powershell
cd prototype
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8765. Load the A–E demo, inspect the JSON, enter your reviewer name and rationale, confirm review, and create a run. Export ranking.json to inspect the assessment-compatible output. Press Ctrl+C to stop.

## Included

- Editable category configuration: dates, constraints, weights and scoring targets.
- A–E derived-fact demonstration without the brief or source proposal text.
- JSON imports with typed facts, source text, exact evidence quotes and warnings.
- Explicit reviewer approval, notes and confirmed mandatory-documentation failures.
- Deterministic scoring, full-precision breakdowns, exact-score tie handling and null scores for held/ineligible proposals.
- Immutable SQLite run snapshots with timestamps, reviewer, reason, configuration, evidence and SHA-256 digest.
- Run inspection and exported rankings. To correct facts or change criteria, open a saved run, edit it, then save a new run with a reason. Both snapshots remain available for comparison.

## Evidence import

Use demo.json as the structure, set demo to false, and provide sources and evidence for every non-null fact before approval. Example evidence structure (illustrative, not proposal text):

```json
{"sources":{"p1":"Total CAD price: 240000"},"evidence":{"price":[{"source_id":"p1","quote":"Total CAD price: 240000"}]}}
```

Keep all twelve facts; use null for unknown values. Counts are nonnegative integers; prices and schedules must be positive. Boolean false requires actual evidence of absence, not silence. Quote matching checks provenance; a reviewer must verify meaning, dates, capacity qualification and warnings. The demo explicitly bypasses evidence requirements and is labelled as such in the interface.

## Scope and limits

Upload 1–5 documents (one proposal per file) in PDF, DOCX, TXT or Markdown format. The server extracts text, preserving page or paragraph source IDs, and computes a file hash. Local mode recognizes explicit field:value lines such as `price: 240000` and `licence: true`; other facts remain null. For free-form proposals, select AI structured extraction. The interface shows extracted text, editable evidence JSON, ranked results and formatted ranking JSON.

To use AI mode, set OPENAI_API_KEY and OPENAI_MODEL in your server shell before starting app.py. Choose a Responses API model supporting strict JSON-schema output. Do not put keys in source files. AI mode transmits extracted text and configuration to OpenAI with store=false. The exact system prompt is extraction_prompt.txt; ingestion.py defines the schema and request. The fixture does not claim model extraction. Network calls are bounded to 90 seconds, with no automatic retries or default scores on failure.

Review every extracted fact, quote and warning. Enter a review rationale, click Confirm all extracted evidence reviewed, confirm the run, and create a run. Unknown values stay flagged; confirmed mandatory failures are ineligible. Use the JSON editor for individual approval, correction and documentation-failure decisions. Download the final ranking.json using Export.

This is a local prototype, not a complete production ingestion system. Scanned/image-only PDF pages require OCR before upload; unreadable pages are rejected rather than silently skipped. DOCX extraction reads body paragraphs and tables, not headers, footers or embedded images. The server does not verify credentials or make an award. Original binary documents are hashed but not stored; extracted text and facts are persisted with saved runs. JSON mode and configuration changes still require human evidence verification.

The category name and numeric policy are editable, but field names and the five scoring formula families implement the solar example; arbitrary category schemas require code changes. The server binds to localhost and has no authentication or encryption at rest. Use only fictional assessment data. Do not deploy it publicly. Local database files and secrets are ignored by Git. File uploads are limited to 10 MB each, 20 MB per encoded request, 50 PDF pages and 100,000 extracted characters per document.

The experience date assumption remains 1 January 2026 with an inclusive start of 1 January 2021. Changing dates requires the reviewer to revalidate project counts; the application does not infer dates from aggregate counts.

## Tests

```powershell
python -m unittest -v
```

Tests cover expected scores, missing evidence, fabricated quotes, unreviewed holds, mandatory failures, invalid inputs, policy validation, immutable runs and ties.

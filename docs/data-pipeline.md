# Data Ingestion & Preprocessing Pipeline Specification

## 1. End-to-End Data Lifecycle

The data pipeline standardizes unstructured, noisy customer inputs into normalized, classified, and indexed signals ready for analysis and downstream generative modeling.

```text
  [ Raw CSV File / JSON Payload / API Request ]
                       │
                       ▼
    ┌───────────────────────────────────────┐
    │ 1. Encoding & Header Normalization    │
    │   • Detects UTF-8, Latin-1, CP1252    │
    │   • Fuzzy-matches column names        │
    └──────────────────┬────────────────────┘
                       │
                       ▼
    ┌───────────────────────────────────────┐
    │ 2. Row Validation & Field Check       │
    │   • Checks for non-empty text         │
    │   • Flags malformed rows into errors  │
    └──────────────────┬────────────────────┘
                       │
                       ▼
    ┌───────────────────────────────────────┐
    │ 3. Signature-Based Deduplication      │
    │   • In-memory duplicate check         │
    │   • Historical MongoDB match check    │
    └──────────────────┬────────────────────┘
                       │
                       ▼
    ┌───────────────────────────────────────┐
    │ 4. Python Text Preprocessing          │
    │   • HTML / Tag Stripping              │
    │   • URL & Link Removal                │
    │   • Email Masking (PII Protection)    │
    │   • Contraction Expansion             │
    │   • Whitespace & Linebreak Normalize  │
    └──────────────────┬────────────────────┘
                       │
                       ▼
    ┌───────────────────────────────────────┐
    │ 5. Controlled 10-Domain Classifier    │
    │   • Word-boundary regex scoring       │
    │   • Confidence score (0.00 to 1.00)   │
    │   • Sentiment & Priority heuristics   │
    └──────────────────┬────────────────────┘
                       │
                       ▼
    ┌───────────────────────────────────────┐
    │ 6. Batch MongoDB Insertion            │
    │   • Async insert_many into collection │
    │   • Generates Ingestion Quality Report│
    └──────────────────┬────────────────────┘
                       │
                       ▼
    ┌───────────────────────────────────────┐
    │ 7. React PM Workspace Presentation    │
    │   • Real-time KPI updates             │
    │   • Verbatim vs Cleaned text toggling │
    │   • Interactive Category drilldowns   │
    └───────────────────────────────────────┘
```

---

## 2. Stage-by-Stage Breakdown

### Stage 1: File Encoding & Header Normalization
Incoming CSV datasets often vary by software source (e.g. Microsoft Excel outputs CP1252/Latin-1, web exports produce UTF-8-BOM).
* The parser attempts cascading decoding: `utf-8` -> `utf-8-sig` -> `latin-1` -> `cp1252`.
* Header columns are matched against candidate lists (e.g., `["text", "feedback", "review", "issue", "comment"]`).

### Stage 2: Row Validation
* Records missing text or containing only whitespace are rejected from database insertion and cataloged into the `IngestionReport.errors` array with explicit line numbers.

### Stage 3: Deduplication Engine
* Prevents data pollution when users upload overlapping exports.
* Computes signature: `<customer_id>:<source>:<text_string>`.
* Compares against both the current batch and existing MongoDB documents.

### Stage 4: Text Cleaning & Preprocessing (`preprocessing.py`)
1. **HTML Removal**: Uses regex `<[^<]+?>` to strip tags while preserving text contents.
2. **URL Removal**: Eliminates `http://`, `https://`, and `www.` URLs including query parameters.
3. **PII Masking**: Detects email addresses (`[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+`) and masks them.
4. **Contraction Expansion**: Expands 20+ English contractions (e.g., `"can't"` -> `"cannot"`, `"won't"` -> `"will not"`, `"it's"` -> `"it is"`).
5. **Whitespace Normalization**: Collapses multi-spaces, tab characters, and irregular line breaks into single space characters.

### Stage 5: Classification, Confidence, Sentiment & Priority (`classification.py`)
* **10 Controlled Domains**:
  - `Authentication`, `Performance`, `Payment`, `Bug`, `UI/UX`, `Feature Request`, `Notifications`, `Account Management`, `Integration`, `Other`.
* **Confidence Scoring Algorithm**:
  - Scores weighted keywords (`2.0` for multi-word phrases, `1.0` for single tokens).
  - Normalizes scores based on categorical uniqueness and match depth (`0.76` baseline for single matches, scaling up to `0.96` for 4+ matches).
* **Sentiment Polarity**:
  - Evaluates positive vs negative emotional tokens.
* **Priority Heuristic**:
  - Assigns `Urgent` for revenue loss, severe crashes, or data deletion keywords.
  - Assigns `High` for critical domain errors with negative sentiment.

### Stage 6: Database Persistence & Quality Reporting
* Batched asynchronously using Motor's `insert_many()`.
* Returns an `IngestionReport` JSON with:
  - `total_records`, `processed_records`, `duplicate_records`, `empty_text_records`, `categories_summary`, `sentiment_summary`, and `errors`.

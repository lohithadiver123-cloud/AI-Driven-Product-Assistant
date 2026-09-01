# System Requirements Specification (SRS) — Milestone 1

## 1. Project Overview & Scope
**Project Title**: AI-Driven Product Assistant based on Customer Feedback with Planning & Requirements Generation Workspace  
**Phase**: Milestone 1 (Foundation, Data Ingestion, Cleaning, Categorization, and PM Workspace)

The system automates the intake, sanitization, structural normalization, domain classification, and exploratory analysis of unstructured customer feedback and support tickets. It provides a single source of truth for product management teams before feeding downstream AI generative modules.

---

## 2. Functional Requirements (FR)

### FR-1: Customer Feedback Ingestion
* **FR-1.1**: The system shall accept customer feedback via CSV file uploads (`.csv`) with automatic character encoding detection (`UTF-8`, `UTF-8-SIG`, `Latin-1`, `CP1252`).
* **FR-1.2**: The system shall accept batch JSON array payloads containing customer feedback objects.
* **FR-1.3**: The system shall support flexible column detection matching variations of text, user ID, channel, and timestamp headers.
* **FR-1.4**: The system shall detect and skip duplicate feedback records within the same batch and against historical MongoDB documents based on signature hashing.
* **FR-1.5**: The system shall generate an `IngestionReport` detailing total records, processed count, duplicates skipped, empty rows rejected, and validation error lines.

### FR-2: Support Ticket Ingestion
* **FR-2.1**: The system shall accept support ticket CSV file uploads with external `ticket_id`, customer ID, channel, issue text, priority, and ticket status.
* **FR-2.2**: The system shall accept batch support ticket JSON payloads.
* **FR-2.3**: The system shall deduplicate support tickets based on `ticket_id` and issue content.

### FR-3: Text Preprocessing & Data Cleaning
* **FR-3.1**: The system shall strip HTML/XML tags and markup from raw input text.
* **FR-3.2**: The system shall remove URLs, links, and query parameters.
* **FR-3.3**: The system shall mask or remove plain-text email addresses to prevent PII exposure.
* **FR-3.4**: The system shall expand standard English contractions (e.g., `"can't"` -> `"cannot"`, `"won't"` -> `"will not"`).
* **FR-3.5**: The system shall normalize excessive whitespace, non-standard line breaks, and trailing spaces.
* **FR-3.6**: The system shall preserve verbatim raw text alongside cleaned text for auditability.

### FR-4: Controlled Domain Categorization & Classification
* **FR-4.1**: The system shall classify each incoming text signal into one of 10 controlled categories:
  1. `Authentication`
  2. `Performance`
  3. `Payment`
  4. `Bug`
  5. `UI/UX`
  6. `Feature Request`
  7. `Notifications`
  8. `Account Management`
  9. `Integration`
  10. `Other`
* **FR-4.2**: The system shall compute an explainable confidence score between `0.00` and `1.00` based on phrase weight and match uniqueness.
* **FR-4.3**: The system shall evaluate sentiment polarity into `Positive`, `Neutral`, or `Negative`.
* **FR-4.4**: The system shall evaluate priority severity into `Urgent`, `High`, `Medium`, or `Low`.

### FR-5: Data Querying, Filtering & Analytics
* **FR-5.1**: The system shall provide paginated querying of feedback and support tickets with configurable page size.
* **FR-5.2**: The system shall provide full-text regex search across verbatim text, preprocessed text, customer ID, and ticket ID.
* **FR-5.3**: The system shall support filtering by category, sentiment, priority, status, and source channel.
* **FR-5.4**: The system shall aggregate live statistics computing category breakdown, sentiment split, priority spread, and average confidence scores.

### FR-6: React Product Manager Workspace
* **FR-6.1**: The frontend shall display executive KPI cards summarizing total feedback, negative sentiment percentage, high-priority blocker percentage, and feature request volume.
* **FR-6.2**: The frontend shall provide interactive category distribution bars that navigate directly to filtered repository records.
* **FR-6.3**: The frontend shall display a data table with colored pills for category, confidence, sentiment, priority, and ticket status.
* **FR-6.4**: The frontend shall allow switching between raw verbatim text and preprocessed text.
* **FR-6.5**: The frontend shall provide a modal inspector showing complete metadata and side-by-side text comparisons.
* **FR-6.6**: The frontend shall provide a drag-and-drop CSV dataset ingestion hub with real-time quality reporting.

---

## 3. Non-Functional Requirements (NFR)

### NFR-1: Usability & User Experience
* Modern, dark-themed glassmorphic interface with clear visual hierarchy, accessible contrast ratios, and intuitive micro-interactions.
* Clear error messaging and actionable ingestion validation feedback.

### NFR-2: Performance & Scalability
* Ingestion of batch CSV datasets (up to 5,000 rows) completed in under 2.5 seconds using asynchronous database batch writes (`insert_many`).
* Sub-100ms API response latency for paginated repository queries and live statistics aggregation.

### NFR-3: Reliability & Fault Tolerance
* Zero crashes on corrupted, non-UTF8, or structurally malformed CSV files.
* MongoDB connection failures are caught cleanly, returning structured HTTP 503 Service Unavailable responses without leaking stack traces.

### NFR-4: Maintainability & Modularity
* Decoupled 3-tier architecture: Presentation Layer (React), API/Orchestration Layer (FastAPI), Database Layer (Motor/MongoDB).
* Separation of business logic into distinct service modules (`preprocessing.py`, `classification.py`, `ingestion.py`).

### NFR-5: Security & Confidentiality
* All environment secrets and MongoDB connection strings managed via `.env` and strictly excluded from Git version control.
* Ingestion pipelines scrub email addresses and sanitize HTML tags to prevent cross-site scripting (XSS) in the PM workspace.

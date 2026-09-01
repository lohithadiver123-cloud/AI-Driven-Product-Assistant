# System Architecture & Technical Design Document

## 1. Architectural Overview

The **AI-Driven Product Assistant based on Customer Feedback with Planning & Requirements Generation Workspace** is architected as a modular, three-tier cloud-native web application designed to support high-throughput customer signal intake, automated preprocessing, rule-based categorization, and an interactive Product Manager workspace.

```text
┌────────────────────────────────────────────────────────┐
│                   React Frontend (Vite)                │
│  ┌──────────────────────────────────────────────────┐  │
│  │ PM Workspace & Interactive Analytics Dashboard   │  │
│  │   • KPI Summary Cards & Pain Point Visualizers   │  │
│  │   • Feedback & Ticket Repositories (Search/Modal)│  │
│  │   • Dataset Ingestion Hub (Drag-and-Drop CSV)    │  │
│  └────────────────────────┬─────────────────────────┘  │
└───────────────────────────┼────────────────────────────┘
                            │ HTTP / JSON & Multipart Form Data
                            │ CORS (localhost:5173 -> localhost:8000)
┌───────────────────────────▼────────────────────────────┐
│                    FastAPI Backend                     │
│  ┌──────────────────────────────────────────────────┐  │
│  │ API Routing Layer                                │  │
│  │   • /health, /health/database                    │  │
│  │   • /api/v1/feedback (List, CRUD, /stats)        │  │
│  │   • /api/v1/feedback/categories (10 Categories)  │  │
│  │   • /api/v1/feedback/upload (CSV/JSON Ingestion) │  │
│  │   • /api/v1/support-tickets (List, CRUD, /upload)│  │
│  └────────────────────────┬─────────────────────────┘  │
│                           │                            │
│  ┌────────────────────────▼─────────────────────────┐  │
│  │ Python Services & Business Logic Layer           │  │
│  │   • app.services.preprocessing (Text Cleaning)   │  │
│  │   • app.services.classification (10 Domains)     │  │
│  │   • app.services.ingestion (Batch Deduplication) │  │
│  └────────────────────────┬─────────────────────────┘  │
│                           │                            │
│  ┌────────────────────────▼─────────────────────────┐  │
│  │ Database Layer (Motor Async Driver)              │  │
│  │   • Connection pooling, reconnects & ping checks │  │
│  └────────────────────────┬─────────────────────────┘  │
└───────────────────────────┼────────────────────────────┘
                            │ Async TLS MongoDB Protocol
┌───────────────────────────▼────────────────────────────┐
│                   MongoDB Atlas Cluster                │
│   Collections: feedback, support_tickets, features,    │
│                users, workspaces, themes, analytics    │
└────────────────────────────────────────────────────────┘
```

---

## 2. Component Breakdown & Responsibilities

### 2.1. Presentation Layer (React 19 + Vite)
* **Single-Page Application (SPA)**: Built with React 19 and modern CSS custom property design tokens.
* **Component Hierarchy**:
  - `Navbar.jsx`: Application header with live WebSocket/HTTP health beacon.
  - `Dashboard.jsx`: Executive PM overview showing KPI statistics, 10-category progress bars, sentiment breakdowns, and priority severity grids.
  - `FeedbackTable.jsx`: Unified repository for feedback and support tickets with live search, multi-field filtering, pagination, verbatim-vs-cleaned text toggle, and deep inspection modal.
  - `UploadModal.jsx`: Dataset ingestion interface supporting CSV drag-and-drop, format validation, and real-time Ingestion Quality Reports.
  - `api.js`: Centralized REST API service communicating asynchronously with the FastAPI backend.

### 2.2. API & Orchestration Layer (FastAPI)
* **Asynchronous Execution**: High-concurrency async endpoints utilizing `asyncio` and `Motor`.
* **Lifespan Management**: Automatically establishes MongoDB connection pool on startup and cleanly closes pool on shutdown.
* **CORS Security**: Cross-Origin Resource Sharing configured for development and staging origins (`localhost:5173`, `localhost:3000`).
* **Validation & Serialization**: Strict Pydantic v2 schemas validating request inputs and generating OpenAPI/Swagger schemas.

### 2.3. Python Processing & Services Layer
* **`app.services.preprocessing`**:
  - Strips HTML tags, markdown artifacts, URLs, and query parameters.
  - Anonymizes plain-text emails to comply with data privacy.
  - Normalizes contractions and whitespace.
* **`app.services.classification`**:
  - Evaluates domain rules using compiled word-boundary regular expressions (`\b<kw>\b`).
  - Assigns text into 10 controlled categories with confidence scores (`0.30` to `0.96`).
  - Tags sentiment polarity (`Positive`, `Neutral`, `Negative`) and priority rating (`Urgent`, `High`, `Medium`, `Low`).
* **`app.services.ingestion`**:
  - Handles multi-encoding CSVs (`UTF-8`, `UTF-8-SIG`, `Latin-1`, `CP1252`).
  - Fuzzy-matches dynamic column headers.
  - Deduplicates items in-memory and against MongoDB signatures.
  - Batches writes using MongoDB `insert_many` for efficiency.

### 2.4. Persistence Layer (MongoDB Atlas)
* **Document Model**: Flexible schema-less storage enabling rich metadata storage alongside structured classification attributes.
* **Asynchronous Driver**: Motor driver enabling non-blocking I/O across all CRUD and aggregation operations.

---

## 3. Future AI Module Integration (Milestones 2 & 3)

The architecture is explicitly designed for seamless downstream AI extensions:
1. **Embedding Pipeline**: Preprocessed `cleaned_text` fields will feed vector embedding models (e.g. OpenAI `text-embedding-3-small` or SentenceTransformers).
2. **Semantic Clustering**: Vector representations stored in a vector index will enable unsupervised HDBSCAN/K-Means clustering to discover emerging **Product Themes**.
3. **Generative PRD & User Story Workspace**: Clustered feedback threads will be injected into LLM context prompts to generate structured PRDs, user stories, acceptance criteria, and roadmap priorities.

# 🚀 PM Copilot — AI-Driven Product Assistant

> An intelligent product management platform that collects customer feedback from multiple sources, cleans and analyzes it using NLP + AI, identifies recurring issues, extracts actionable themes, and helps product managers make data-driven decisions — all from a single dashboard.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [System Architecture](#system-architecture)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [API Reference](#api-reference)
- [Data Models](#data-models)
- [Milestone 1 — Feedback Pipeline (Completed)](#milestone-1--feedback-pipeline-completed)
- [Milestone 2 — AI-Powered Insights (Completed)](#milestone-2--ai-powered-insights-completed)
- [Milestone 3 — Planning & Requirements Generation Workspace (Completed)](#milestone-3--planning--requirements-generation-workspace-completed)
- [Milestone 4 — Roadmap Planning, Reporting & Output Quality (Completed)](#milestone-4--roadmap-planning-reporting--output-quality-completed)
- [Documentation](#documentation)
- [Setup & Installation](#setup--installation)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [Future Work](#future-work)

---

## Overview

**PM Copilot** helps product managers:

1. **Collect** customer feedback from CSV/JSON files (app reviews, support tickets, surveys)
2. **Clean & Preprocess** raw text — normalize, deduplicate, and sanitize
3. **Categorize** feedback into bug reports, feature requests, performance issues, or general feedback
4. **Detect Sentiment** — positive, neutral, or negative (rule-based + rating-based)
5. **Extract Themes** — identify recurring product topics across all feedback
6. **Surface Pain Points** — detect and rank customer friction areas with explainable impact scores
7. **Cluster Feature Requests** — semantically group user requests into product opportunities
8. **Analyze Trends** — track sentiment shifts, volume patterns, and product health over time
9. **AI Intelligence** — optionally leverage Groq LLMs for executive summaries, root-cause analysis, and strategic insights

---

## Tech Stack

| Layer         | Technology                         | Purpose                                      |
| ------------- | ---------------------------------- | -------------------------------------------- |
| **Frontend**  | React 18 + Vite 5                  | Single-page application with protected routes |
| **Backend**   | FastAPI (Python)                   | RESTful API with async request handling       |
| **Database**  | MongoDB Atlas (Motor async driver) | Cloud-hosted NoSQL document store             |
| **Auth**      | JWT (python-jose) + bcrypt         | Stateless token-based authentication          |
| **NLP**       | NLTK + Custom keyword engine       | Text normalization, tokenization, n-grams     |
| **AI (Optional)** | Groq Cloud LLMs (ALLaM, Qwen, GPT) | Executive summaries & root-cause analysis |
| **Data**      | Pandas                             | CSV/JSON import and data transformation       |
| **Styling**   | Vanilla CSS                        | Custom dark-theme UI with responsive design   |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + Vite)                      │
│                                                                     │
│   ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────────┐ │
│   │  Login   │ │ Register │ │ Dashboard │ │ Insights Dashboard   │ │
│   └──────────┘ └──────────┘ └───────────┘ └──────────────────────┘ │
│   ┌────────────────────┐ ┌────────────────────┐ ┌────────────────┐ │
│   │  PRD Studio (M3)   │ │ User Stories (M3)  │ │ Prioritize(M3) │ │
│   │  • AI Doc View     │ │ • Kanban Board     │ │ • RICE Scoring │ │
│   │  • Markdown Export │ │ • Gherkin Criteria │ │ • 2x2 Matrix   │ │
│   └────────────────────┘ └────────────────────┘ └────────────────┘ │
│   ┌────────────────────────────────┐ ┌───────────────┐ ┌─────────┐ │
│   │  Conversational Copilot (M3)   │ │ Feedback List │ │ Import  │ │
│   │  • Grounded Chat & Citations   │ └───────────────┘ └─────────┘ │
│   └────────────────────────────────┘                               │
│                                                                     │
│   Components: Navbar, Charts, FloatingCopilot Widget                │
│   Services:   api.js (Axios HTTP client with JWT interceptor)       │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP (REST API)
                             │ Vite Dev Proxy → localhost:8000
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI + Python)                       │
│                                                                     │
│   ┌─────────────────────── API ROUTERS ──────────────────────────┐  │
│   │                                                               │  │
│   │  /api/auth           → Register, Login, JWT auth              │  │
│   │  /api/workspaces     → Create, list, manage workspaces        │  │
│   │  /api/feedback       → Import, clean, categorize feedback     │  │
│   │  /api/insights       → Themes, pain points, feature clusters  │  │
│   │  /api/prd (M3)       → AI PRD generation, Markdown export     │  │
│   │  /api/user-stories(M3)→ Agile stories, Gherkin criteria, DoD   │  │
│   │  /api/prioritization(M3)→ RICE, 2x2 Matrix, MoSCoW, Weighted   │  │
│   │  /api/copilot (M3)   → Grounded multi-turn conversational AI   │  │
│   │  /api/health         → Health check endpoint                  │  │
│   │                                                               │  │
│   └───────────────────────────┬───────────────────────────────────┘  │
│                               │                                      │
│   ┌─────────────── SERVICES LAYER ──────────────────────────────┐   │
│   │                                                              │   │
│   │  prd_service.py           → Generative AI PRD synthesis      │   │
│   │  user_story_service.py    → Agile decomposition engine       │   │
│   │  prioritization_service.py→ Configurable scoring frameworks  │   │
│   │  copilot_service.py       → Grounded PM assistant & chat     │   │
│   │  theme_extraction.py      → NLP theme mining & pain points   │   │
│   │  clustering.py            → Feature request semantic cluster │   │
│   │  trend_analysis.py        → Sentiment trajectory & health    │   │
│   │  ai_service.py            → Gemini 3.6 Flash & Groq fallback │   │
│   │                                                              │   │
│   └──────────────────────────┬───────────────────────────────────┘   │
│                              │                                       │
│   ┌───────────── DATA LAYER ────────────────────────────────────┐   │
│   │  database.py   → Motor async MongoDB connection manager      │   │
│   │  fallback_db.py → In-memory JSON store for dev/demo mode     │   │
│   │  config.py      → Centralized settings from .env             │   │
│   └──────────────────────────┬───────────────────────────────────┘   │
└──────────────────────────────┼───────────────────────────────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │     MongoDB Atlas (Cloud)       │
              │                                │
              │  Collections:                  │
              │   • users                      │
              │   • workspaces                 │
              │   • feedback                   │
              │   • import_logs                │
              │   • workspace_insights         │
              └────────────────────────────────┘
```

---

## Project Structure

```
pm-AI/
├── backend/
│   ├── main.py                          # FastAPI app entry point + lifespan
│   ├── config.py                        # Environment settings (Mongo, JWT, CORS)
│   ├── database.py                      # Motor async MongoDB connection
│   ├── fallback_db.py                   # In-memory JSON fallback for dev/demo
│   ├── check_mongo.py                   # MongoDB connectivity diagnostic tool
│   ├── requirements.txt                 # Python dependencies
│   │
│   ├── models/
│   │   ├── user.py                      # User schema (registration, login)
│   │   ├── workspace.py                 # Workspace schema
│   │   ├── feedback.py                  # Feedback record schema
│   │   ├── insights.py                  # Insights response models (themes, pain points, clusters)
│   │   ├── prd.py                       # PRD document schema
│   │   ├── user_story.py                # User story + Gherkin criteria schema
│   │   ├── prioritization.py            # RICE / Value-vs-Effort / MoSCoW / weighted schemas
│   │   ├── copilot.py                   # Copilot chat schemas
│   │   ├── roadmap.py                   # Roadmap, milestones, releases (Milestone 4)
│   │   ├── report.py                    # Executive & strategy report schemas (Milestone 4)
│   │   └── quality.py                   # Output quality evaluation schemas (Milestone 4)
│   │
│   ├── routers/
│   │   ├── auth.py                      # /api/auth — register, login, JWT
│   │   ├── workspace.py                 # /api/workspaces — CRUD operations
│   │   ├── feedback.py                  # /api/feedback — import, list, clean, categorize
│   │   ├── insights.py                  # /api/insights — full analysis pipeline
│   │   ├── prd.py                       # /api/prd — generate, edit, export
│   │   ├── user_stories.py              # /api/user-stories — generate, status, export
│   │   ├── prioritization.py            # /api/prioritization — frameworks, weights, auto-seed
│   │   ├── copilot.py                   # /api/copilot — conversational assistant
│   │   ├── roadmap.py                   # /api/roadmap — plan, reschedule, export (Milestone 4)
│   │   ├── reports.py                   # /api/reports — executive & strategy reports (Milestone 4)
│   │   ├── quality.py                   # /api/quality — output quality evaluation (Milestone 4)
│   │   └── outcome.py                   # /api/outcome — measured change between two imports
│   │
│   ├── services/
│   │   ├── preprocessing.py             # Text normalization + tokenization
│   │   ├── data_cleaning.py             # Text sanitization, dedup, missing values
│   │   ├── categorization.py            # Rule-based category + sentiment detection
│   │   ├── text_mining.py               # Corpus mining primitives shared by all analyses
│   │   ├── theme_extraction.py          # NLP theme mining + pain point identification
│   │   ├── clustering.py               # Feature request semantic clustering
│   │   ├── trend_analysis.py            # Temporal trends + product health scoring
│   │   ├── ai_service.py               # Provider chain: Gemini → Mistral → Groq
│   │   ├── prd_service.py               # PRD generation + evidence grounding
│   │   ├── user_story_service.py        # User story + acceptance criteria generation
│   │   ├── prioritization_service.py    # Scoring frameworks + auto-seeding
│   │   ├── copilot_service.py           # Grounded conversational answers
│   │   ├── workspace_context.py         # Shared loaders for the planning services
│   │   ├── roadmap_service.py           # Sequencing, release packing, milestones (M4)
│   │   ├── report_service.py            # Executive & strategy report generation (M4)
│   │   └── quality_service.py           # Output quality evaluation (M4)
│   │
│   └── tests/
│       ├── test_milestone1.py           # Milestone 1 validation tests
│       ├── test_milestone2.py           # Milestone 2 validation tests
│       ├── test_milestone3.py           # PRDs, stories, prioization, copilot
│       ├── test_milestone3_integration.py # Service pipelines (calls live providers)
│       ├── test_milestone4.py           # Roadmap, reports, quality evaluation (29 tests)
│       ├── test_outcome.py              # Import-to-import outcome comparison (35 tests)
│       └── test_10k_benchmark.py        # Performance benchmark (10k+ records)
│
├── frontend/
│   ├── index.html                       # App entry HTML
│   ├── package.json                     # Node.js dependencies
│   ├── vite.config.ts                   # Vite dev server + API proxy config
│   │
│   └── src/
│       ├── index.jsx                    # React DOM render entry
│       ├── index.css                    # Global styles (dark theme)
│       ├── App.jsx                      # Router setup + protected routes
│       │
│       ├── components/
│       │   ├── Navbar.jsx               # Navigation bar with auth state
│       │   └── Charts.jsx              # SVG data visualization components
│       │
│       ├── pages/
│       │   ├── Login.jsx                # User login page
│       │   ├── Register.jsx             # User registration page
│       │   ├── Dashboard.jsx            # Workspace overview + feedback stats
│       │   ├── ImportData.jsx           # CSV/JSON file upload interface
│       │   ├── FeedbackList.jsx         # Paginated feedback browser
│       │   ├── InsightsDashboard.jsx    # AI insights + analytics dashboard
│       │   ├── PRDWorkspace.jsx         # PRD generation and editing
│       │   ├── UserStoriesWorkspace.jsx # Stories, criteria, Kanban
│       │   ├── PrioritizationHub.jsx    # RICE, matrix, MoSCoW, weighted scoring
│       │   ├── RoadmapPlanner.jsx       # Release lanes + milestone recommendations (M4)
│       │   ├── ExecutiveReports.jsx     # Reports + output quality evaluation (M4)
│       │   ├── OutcomeTracker.jsx       # What changed between two imports
│       │   └── CopilotChat.jsx          # Conversational assistant
│       │
│       └── services/
│           └── api.js                   # Axios HTTP client with JWT auth
│
├── docs/
│   ├── TECHNICAL_REPORT.md              # Architecture, modules, testing, verified results
│   ├── UI_DESIGN_RULES.md               # Cognitive-load rules: one answer per page, what collapses
│   └── FINAL_DEMO_SCRIPT.md             # Demonstration runbook + Q&A preparation
├── README.md
├── start_all.bat                        # Launches backend + frontend together
├── .gitignore
└── .env.example                         # Environment variable template
```

---

## How It Works

### End-to-End Data Flow

```
 CSV/JSON File Upload
        │
        ▼
 ┌──────────────────┐
 │  1. IMPORT        │  Parse CSV/JSON → validate fields → store raw records
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │  2. CLEAN         │  Normalize text → remove HTML/special chars → dedup
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │  3. CATEGORIZE    │  Rule-based keyword matching → assign category
 │                   │  Bug Report | Feature Request | Performance | General
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │  4. SENTIMENT     │  Rating-based (1-5★) or keyword-based detection
 │                   │  Positive | Neutral | Negative
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │  5. THEME MINING  │  Domain topic matching → group by recurring themes
 │                   │  (Auth, Performance, UI/UX, Search, Billing, etc.)
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │  6. PAIN POINTS   │  Filter negative/bug items → group by domain →
 │                   │  Score impact: Volume(35%) + Rating(25%) +
 │                   │  Negative%(25%) + Bug Ratio(15%)
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │  7. CLUSTERING    │  Group feature requests by semantic similarity
 │                   │  (Jaccard token overlap + keyword patterns)
 │                   │  Score priority: Volume(45%) + Users(30%) + Rating(25%)
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │  8. TRENDS        │  Aggregate by date → compute sentiment velocity
 │                   │  Calculate Product Health Score (0-100)
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │  9. AI LAYER      │  (Optional) Groq LLM executive summary,
 │                   │  root-cause analysis, strategic recommendations
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │  10. DASHBOARD    │  Visualize all insights with interactive charts
 └──────────────────┘
```

### User Workflow

1. **Register / Login** → Create an account and receive a JWT token
2. **Create a Workspace** → Organize feedback by product or project
3. **Import Feedback** → Upload CSV or JSON files with customer feedback
4. **Auto-Process** → System cleans, categorizes, and detects sentiment
5. **View Dashboard** → See workspace stats, category breakdowns, sentiment overview
6. **Run Analysis** → Trigger the full insights pipeline
7. **Explore Insights** → Dive into themes, pain points, feature clusters, and trends
8. **AI Intelligence** → (Optional) Get LLM-powered executive summaries and root-cause analysis

---

## API Reference

### Authentication

| Method | Endpoint             | Description                    |
| ------ | -------------------- | ------------------------------ |
| POST   | `/api/auth/register` | Register a new user            |
| POST   | `/api/auth/login`    | Login and receive JWT token    |

### Workspaces

| Method | Endpoint                  | Description                    |
| ------ | ------------------------- | ------------------------------ |
| POST   | `/api/workspaces`         | Create a new workspace         |
| GET    | `/api/workspaces`         | List user's workspaces         |
| GET    | `/api/workspaces/:id`     | Get workspace details          |

### Feedback

| Method | Endpoint                               | Description                          |
| ------ | -------------------------------------- | ------------------------------------ |
| POST   | `/api/feedback/:workspace_id/import`   | Import feedback from CSV/JSON file   |
| GET    | `/api/feedback/:workspace_id`          | List feedback (paginated)            |
| POST   | `/api/feedback/:workspace_id/clean`    | Run cleaning pipeline                |
| POST   | `/api/feedback/:workspace_id/categorize` | Run categorization + sentiment     |

### Insights (Milestone 2)

| Method | Endpoint                                    | Description                                |
| ------ | ------------------------------------------- | ------------------------------------------ |
| POST   | `/api/insights/:workspace_id/analyze`       | Run full analysis pipeline                 |
| GET    | `/api/insights/:workspace_id`               | Get cached or computed insights            |
| GET    | `/api/insights/:workspace_id/themes`        | Get extracted themes only                  |
| GET    | `/api/insights/:workspace_id/pain-points`   | Get pain points with severity rankings     |
| GET    | `/api/insights/:workspace_id/clusters`      | Get feature request clusters               |
| GET    | `/api/insights/:workspace_id/trends`        | Get trend trajectory data                  |
| GET    | `/api/insights/ai/status`                   | Report which AI providers are configured    |
| POST   | `/api/insights/ai/configure-key`            | Set provider API keys at runtime            |

### Roadmap (Milestone 4)

| Method | Endpoint                                            | Description                                        |
| ------ | --------------------------------------------------- | -------------------------------------------------- |
| POST   | `/api/roadmap/generate`                             | Sequence the backlog into releases + milestones     |
| GET    | `/api/roadmap/:workspace_id`                        | Read the stored roadmap                             |
| PATCH  | `/api/roadmap/:workspace_id/items/:item_id`         | Move an initiative to another release               |
| DELETE | `/api/roadmap/:workspace_id`                        | Delete the stored roadmap                           |
| GET    | `/api/roadmap/:workspace_id/export`                 | Export the roadmap as Markdown                      |

### Reports (Milestone 4)

| Method | Endpoint                                    | Description                                       |
| ------ | ------------------------------------------- | ------------------------------------------------- |
| POST   | `/api/reports/generate`                     | Generate an executive summary or strategy report   |
| GET    | `/api/reports/workspace/:workspace_id`      | List reports for a workspace (newest first)        |
| GET    | `/api/reports/:report_id`                   | Read one report                                    |
| PUT    | `/api/reports/:report_id`                   | Update editable report fields                      |
| DELETE | `/api/reports/:report_id`                   | Delete a report                                    |
| GET    | `/api/reports/:report_id/export`            | Export the report as Markdown                      |

### Output Quality (Milestone 4)

| Method | Endpoint                                    | Description                                            |
| ------ | ------------------------------------------- | ------------------------------------------------------ |
| GET    | `/api/quality/:workspace_id/evaluate`       | Evaluate completeness, grounding, freshness, consistency |
| GET    | `/api/quality/:workspace_id/export`         | Export the evaluation as Markdown                       |

### Outcome Tracking

| Method | Endpoint                                     | Description                                                     |
| ------ | -------------------------------------------- | --------------------------------------------------------------- |
| GET    | `/api/outcome/:workspace_id/batches`         | The imports this workspace's feedback arrived in, oldest first   |
| GET    | `/api/outcome/:workspace_id/compare`         | Measured change between two imports (`?before=&after=&max_themes=`) |
| GET    | `/api/outcome/:workspace_id/export`          | Export the comparison as Markdown                                |

### Health

| Method | Endpoint       | Description                 |
| ------ | -------------- | --------------------------- |
| GET    | `/api/health`  | API health check            |

---

## Data Models

### User
```json
{
  "_id": "ObjectId",
  "name": "string",
  "email": "string",
  "password_hash": "string",
  "role": "product_manager",
  "workspace_ids": ["workspace_id_1", "workspace_id_2"],
  "created_at": "datetime"
}
```

### Workspace
```json
{
  "_id": "ObjectId",
  "name": "string",
  "description": "string",
  "created_by": "user_id",
  "created_at": "datetime"
}
```

### Feedback
```json
{
  "_id": "ObjectId",
  "workspace_id": "string",
  "source": "app_review | support_ticket | survey | social_media | email",
  "title": "string",
  "content": "string",
  "customer_name": "string",
  "customer_email": "string",
  "rating": 1-5,
  "category": "bug_report | feature_request | performance_issue | general_feedback",
  "sentiment": "positive | neutral | negative",
  "theme": "Authentication & Access | Performance & Stability | ...",
  "status": "new | reviewed | resolved",
  "cleaned": true,
  "created_at": "datetime",
  "imported_at": "datetime"
}
```

### Workspace Insights
```json
{
  "workspace_id": "string",
  "total_analyzed": 500,
  "health_score": 72.5,
  "themes": [{ "title": "...", "frequency": 45, "sentiment_score": -0.3 }],
  "pain_points": [{ "title": "...", "severity": "high", "impact_score": 85.0 }],
  "feature_clusters": [{ "cluster_name": "...", "demand_level": "high", "priority_score": 88.0 }],
  "trends": [{ "period": "2025-01-15", "sentiment_score": 0.2, "total_count": 25 }],
  "ai_summary": { "headline": "...", "overview": "...", "top_frictions": [], "quick_wins": [] },
  "analyzed_at": "datetime"
}
```

---

## Milestone 1 — Feedback Pipeline (Completed ✅)

Milestone 1 covers the core feedback ingestion, cleaning, and rule-based analysis:

- ✅ User authentication (register + login with JWT)
- ✅ Workspace management (create, list, switch)
- ✅ Feedback import from CSV and JSON files
- ✅ Text cleaning and preprocessing (normalization, sanitization, dedup)
- ✅ Rule-based categorization (keyword matching across 4 categories)
- ✅ Sentiment detection (rating-based + keyword-based fallback)
- ✅ Dashboard with workspace statistics and summary breakdowns
- ✅ JSON fallback mode when MongoDB is unreachable (for dev/demo)

---

## Milestone 2 — AI-Powered Insights (Completed ✅)

Milestone 2 adds the full intelligence and analytics layer:

- ✅ **Theme Extraction** — NLP-based topic detection across 8 domain areas (Auth, Performance, UI/UX, Search, Notifications, Data Management, Billing, Support)
- ✅ **Pain Point Detection** — Identifies and ranks customer friction areas with explainable impact scores using a deterministic formula: `Volume (35%) + Low Rating (25%) + Negative Sentiment % (25%) + Bug Ratio (15%)`
- ✅ **Feature Request Clustering** — Semantic grouping using Jaccard similarity + keyword-based pattern matching with priority scoring: `Request Volume (45%) + Unique Users (30%) + Rating Satisfaction (25%)`
- ✅ **Trend Analysis** — Chronological sentiment tracking, volume aggregation, and sentiment velocity computation
- ✅ **Product Health Score** — Overall 0–100 health metric based on: `Sentiment Ratio (45pts) + Avg Rating (35pts) + Stability/Bug Ratio (20pts)`
- ✅ **Groq LLM Integration** — Optional AI layer using Groq Cloud (ALLaM, Qwen, GPT models) for executive summaries, root-cause analysis, and strategic recommendations with graceful fallback to heuristic engine
- ✅ **Insights Dashboard** — Full-featured analytics UI with interactive charts, theme breakdowns, pain point rankings, cluster visualizations, and AI summary panel
- ✅ **Performance Optimized** — Sub-second analysis on 10,000+ feedback records with batched DB writes, subsampling, and pre-compiled regex

---

## Milestone 3 — Planning & Requirements Generation Workspace (Completed ✅)

Milestone 3 implements the complete Planning & Requirements Workspace powered by Generative AI:

1. **Generative AI PRD Generation (`/api/prd`)**
   - Integrates Google Gemini (`gemini-3.6-flash`, 1,000,000 token context window) with Groq and deterministic fallback engines.
   - Grounded 100% in real customer feedback, user reviews, and pain points.
   - Comprehensive PRD structure:
     - Executive Summary & Context
     - Problem Statement & Customer Evidence
     - Target User Personas (Frictions, Motivations, Goals)
     - Strategic Goals & Quantitative OKRs
     - Scope Definition (In-Scope vs. Out-of-Scope)
     - Key User Journeys (Discovery, Execution, Outcome)
     - Functional Requirements (ID, P0/P1/P2 priorities, acceptance criteria, edge cases)
     - Non-Functional Requirements (Performance SLAs, Security, Scalability, WCAG Accessibility)
     - Success Metrics & KPIs Table (Baselines, Targets, Telemetry Mechanisms)
     - Technical Dependencies & Risks Mitigation Matrix
   - Export options: One-click copy, download as GitHub-flavored Markdown (.md), and direct user story generation.

2. **Automated User Story & Acceptance Criteria Generation (`/api/user-stories`)**
   - Decomposes PRDs, feature clusters, or custom initiatives into vertical sprint-ready user stories.
   - Standard Agile format: `"As a <role>, I want to <action>, so that <benefit>."`
   - Gherkin-syntax Acceptance Criteria: Scenario with `Given`, `When`, `Then` blocks.
   - Fibonacci Story Points (`1, 2, 3, 5, 8, 13`) and T-Shirt sizing (`XS, S, M, L, XL`).
   - Definition of Done (DoD) checklist and technical architectural notes.
   - Interactive Kanban Board (Backlog → In Progress → In Review/QA → Done) and List/Table view with CSV export.

3. **Feature Prioritization with Configurable Scoring Frameworks (`/api/prioritization`)**
   - Four industry-standard prioritization frameworks in a single unified interface:
     - **RICE Scoring**: `(Reach × Impact × Confidence) / Effort` with inline interactive sliders and instant rank reordering.
     - **Value vs Effort (2x2 Matrix)**: Interactive scatter plot with automatic quadrant mapping:
       - ⚡ *Quick Wins* (High Value, Low Effort)
       - 🚀 *Major Projects* (High Value, High Effort)
       - 🛠️ *Fill-ins* (Low Value, Low Effort)
       - ⏳ *Thankless Tasks* (Low Value, High Effort)
     - **MoSCoW Method**: Interactive 4-column board (Must Have, Should Have, Could Have, Won't Have).
     - **Custom Weighted Scoring**: Dynamic sliders for Customer Demand (%), Business Impact (%), Technical Feasibility (%), and Risk Mitigation (%) with live-updating leaderboards.
   - **Auto-Seed from Feedback**: One-click extraction from Milestone 2 Feature Clusters and Pain Points.
   - **AI Re-Score All**: Leverages Google Gemini to calibrate parameters based on customer demand and sentiment severity.

4. **Conversational Product Intelligence Assistant / Copilot (`/api/copilot`)**
   - Grounded conversational AI assistant (PM Copilot) with real-time access to workspace feedback, pain points, themes, and PRDs.
   - Dedicated Copilot Page (`/copilot`) plus a global **Floating Copilot Widget** accessible from any page.
   - Multi-turn conversation capability with chat history persistence per workspace session.
   - Sources Cited citations: Points directly to supporting feedback quotes, customer volume, and themes.
   - Quick suggested follow-up chips and interactive shortcut buttons ("Generate PRD for this", "User Stories").

---

## Milestone 4 — Roadmap Planning, Reporting & Output Quality (Completed ✅)

Milestone 4 closes the loop from feedback to a committed plan — and makes the quality of everything
generated something the system can actually demonstrate.

1. **Roadmap Planning & Milestone Recommendation (`/api/roadmap`, `/roadmap`)**
   - Sequences the prioritization backlog into fixed four-week release windows across a configurable horizon.
   - Ordering rule: RICE → weighted multi-factor score → defect/performance/security work ahead of feature work at equal value → customer volume.
   - Capacity-aware packing: an initiative that does not fit an early window stays a candidate for the next one; anything beyond the horizon becomes a backlog with its scores intact.
   - Recommends one milestone per window with a name, objective, sequencing rationale, evidence-confidence level (high / medium / low), exit criteria and success metrics.
   - **Interactive**: move any initiative to another release and the milestones, capacity totals, exit criteria and Markdown are recomputed around it.
   - Baselines are labelled `Measured:` and targets `Proposed:` — the same honesty convention the PRD uses. AI writes narrative only; it cannot reorder work, move a date or change a number.

2. **Executive Summaries & Product Strategy Reports (`/api/reports`, `/reports`)**
   - Two report types — executive summary and product strategy — for a chosen audience and period.
   - Sections: headline, executive summary, measured product-health snapshot, key findings, strategic pillars, roadmap outlook, product indicators, risks, recommendations, evidence & method.
   - Strategic pillars are the roadmap milestones when a plan exists; otherwise the highest-impact pain points and highest-demand clusters.
   - Risks come from the plan's own weak points: stale analysis, no delivery buffer, no PRD behind the backlog, milestones resting on thin evidence.
   - Markdown export and print/PDF-ready layout.

3. **Output Quality Evaluation (`/api/quality`)**
   - Scores six artefact families — insights, prioritization, roadmap, PRDs, user stories, reports — against checks verifiable from the workspace itself.
   - Categories: completeness, evidence grounding, freshness, internal consistency.
   - **Traceability scan**: every number written into generated prose is checked against the values this workspace has actually measured, so an invented figure is reported rather than trusted.
   - **Duplicate-scope scan**: two initiatives describing the same subject are flagged so a milestone cannot credit itself twice.
   - Deterministic and model-free — it cannot flatter a generation. Scoring is the mean of pass/warn/fail, graded excellent / good / fair / needs_review.
   - Exportable as Markdown for the technical report or a review pack.

4. **Documentation & Final Demonstration**
   - [`docs/TECHNICAL_REPORT.md`](docs/TECHNICAL_REPORT.md) — architecture, data model, module-by-module implementation, verified results, testing, limitations.
   - [`docs/FINAL_DEMO_SCRIPT.md`](docs/FINAL_DEMO_SCRIPT.md) — click-by-click demonstration runbook with expected outputs, Q&A preparation and recovery plans.

**Verified on the `spotify` workspace** (10,000 analysed records, health 77.7): 9 initiatives scheduled
across 3 release windows, 3 recommended milestones, 4,955 customer records behind planned work,
must-have coverage 7 of 7, and an output-quality verdict of 96/100 with 24 checks passed, 3 warned and
0 failed — the three warnings being real defects the evaluator found in the workspace.

---

## Outcome Tracking — what happened after the plan

Every other part of this system argues about what *should* be built. Outcome tracking answers the
question that follows: **between the two times this workspace collected customer feedback, did anything
actually move?**

No new data has to be collected and no date has to be remembered. Every imported record already carries
the import it arrived in, so uploading the same product's feedback again later — a month after a release,
a week after a fix ships — creates the comparison automatically.

- **Compared unit:** one import of the workspace. The earlier import is the baseline, the later one is the
  follow-up, and the gap between them is the measurement window.
- **Topic axis:** mined once from both imports together, then each record is counted in exactly one topic
  (the one whose mined phrase matches it most specifically). One vocabulary measured twice — and a common
  word like `review` cannot inflate every topic, because the topic counts always add up to the collection.
- **Normalised per 100 records**, because the two collections are rarely the same size; raw counts would
  report a larger import as a rise in everything at once.
- **Thresholds stated with the result:** a movement is only claimed above 5 mentions on both sides and 0.05
  per 100 records, or 10% of the earlier value — whichever is larger. Below that a topic is reported as
  steady, and a topic short of evidence is reported as such rather than as a trend. The rate base travels
  in the payload (`method.rate_base`), so the figures and their unit can never drift apart.
- **Comparability caveats are surfaced, not buried:** two imports an order of magnitude apart in size, or
  dominated by different sources, are flagged as indicative rather than precise — because part of the change
  is then a change in who was heard.
- **Never inferred:** revenue, retention, conversion and crash-free rate are never stated, because this
  workspace does not measure them.

A fresh two-import workspace demonstrates the clean case:

```
GET /api/outcome/{workspace_id}/compare
Complaint volume fell 75.0% (40.0 → 10.0 problem mentions per 100 records).
Average rating is up 1.3 (3.4 → 4.7).

Playlist Screen        bug report   40 → 10   Falling   Fell 75.0% (40.0 → 10.0 per 100)
Unclassified mentions  general      60 → 90   Rising    Rose 50.0% (60.0 → 90.0 per 100)
```

Run against the real `spotify` workspace — 10,000 records (2026-09-29) against 100 (2026-10-05) — the same
endpoint reports complaint mentions going 3.96 → 24.0 per 100 and the rating 3.8 → 3.25, **and says why
that is not a clean before-and-after**: the two imports differ greatly in size and are dominated by
different sources (`survey` then `Apple App Store`), so the movement is indicative rather than a
like-for-like product change. That caveat is the feature.

---

## Documentation

| Document | Contents |
| :--- | :--- |
| [`docs/TECHNICAL_REPORT.md`](docs/TECHNICAL_REPORT.md) | Problem statement, architecture, data model, module mapping, Milestone 4 design, verified results, testing, limitations |
| [`docs/UI_DESIGN_RULES.md`](docs/UI_DESIGN_RULES.md) | Measured text volume per page, the one-answer-per-page principle, eight checkable rules, and a per-page collapse plan |
| [`docs/FINAL_DEMO_SCRIPT.md`](docs/FINAL_DEMO_SCRIPT.md) | Pre-demo checklist, 15-minute demonstration script, questions to expect, recovery plans |

---

## Setup & Installation

### Prerequisites

- **Python** 3.10+
- **Node.js** 18+
- **MongoDB Atlas** account (or use the built-in fallback mode for demo)

### Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp ../.env.example .env
# Edit .env with your MongoDB URI and secret key

# Start the API server
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server (proxied to backend on port 8000)
npm run dev -- --host 0.0.0.0 --port 5173
```

The frontend dev server at `http://localhost:5173` automatically proxies API requests to the backend at `http://localhost:8000`.

---

## Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# MongoDB Connection
MONGO_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?appName=<app-name>
DB_NAME=pm_copilot

# JWT Secret (change in production!)
SECRET_KEY=your-secure-secret-key

# (Optional) AI provider keys — tried in this order, each falling back to the next
GEMINI_API_KEY=your_google_ai_studio_key
MISTRAL_API_KEY=your_mistral_key
GROQ_API_KEY=gsk_your_groq_api_key_here
```

> With no provider key configured, every analysis, document, roadmap and report is produced by the
deterministic engines from workspace feedback — the application is fully functional offline.

> **Note:** If `MONGO_URI` is not configured or MongoDB is unreachable, the app automatically falls back to an in-memory JSON data store for development and demos.

---

## Running Tests

```bash
cd backend

# Milestone 1 validation
python -m unittest tests/test_milestone1.py

# Milestone 2 validation
python -m unittest tests/test_milestone2.py

# Milestone 3 validation (PRD, Stories, Prioritization, Copilot)
python -m unittest tests/test_milestone3.py

# Milestone 3 Integration pipeline
python -m unittest tests/test_milestone3_integration.py

# Milestone 4 validation (Roadmap, Reports, Output Quality) — 29 tests
python -m unittest discover -s tests -p "test_milestone4.py"

# Outcome tracking (import-to-import comparison) — 35 tests
python -m unittest discover -s tests -p "test_outcome.py"

# Milestone 1-4 unit suites together
python -m unittest discover -s tests -p "test_milestone*.py"
```

> `test_milestone2` and `test_milestone3_integration` exercise the live AI provider chain, so they need
> network access and can be slow while a provider is throttled. Every other suite runs fully offline.

---

## Future Work

Milestone 4 is complete. The following remain as deliberate next steps:

- 🔗 Two-way sync with Jira, Linear and GitHub Issues, so a roadmap release becomes a real backlog
- 🎙️ Meeting transcript ingestion as an additional feedback source
- 🧭 Server-side PDF rendering for reports (today they export as Markdown and print from the browser)
- 👥 Real-time collaboration on roadmaps and prioritization with per-change history
- 📈 Longitudinal tracking: store each analysis so the quality evaluation can compare a release
  against the baseline it promised to improve
- ⚡ Parallelise the per-record clean and categorize pipelines for very large workspaces

---

## License

This project is part of an academic/portfolio demonstration of AI-driven product management tooling.

---

<p align="center">
  Built with ❤️ using FastAPI, React, MongoDB, and Groq AI
</p>

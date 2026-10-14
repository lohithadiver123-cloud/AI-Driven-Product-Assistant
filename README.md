# 🚀 PM Copilot — AI-Driven Product Assistant

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)](https://vitejs.dev)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com)
[![AI Engine](https://img.shields.io/badge/AI_Engine-Gemini_|_Mistral_|_Groq-4285F4?logo=google&logoColor=white)](https://aistudio.google.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> An intelligent, end-to-end product management platform that collects customer feedback from multiple channels, normalizes and analyzes it using NLP and Generative AI, extracts actionable themes and pain points, structures Agile PRDs and user stories, sequences capacity-aware release roadmaps, and tracks longitudinal product outcomes — all from a single reactive workspace.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Capabilities](#key-capabilities)
- [Tech Stack](#tech-stack)
- [System Architecture](#system-architecture)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [User Journey & Lifecycle](#user-journey--lifecycle)
- [API Reference](#api-reference)
- [Data Models](#data-models)
- [Milestones & Implementation](#milestones--implementation)
  - [Milestone 1 — Feedback Pipeline](#milestone-1--feedback-pipeline-completed-)
  - [Milestone 2 — AI-Powered Insights](#milestone-2--ai-powered-insights-completed-)
  - [Milestone 3 — Planning & Requirements Workspace](#milestone-3--planning--requirements-generation-workspace-completed-)
  - [Milestone 4 — Roadmap, Executive Reports & Quality](#milestone-4--roadmap-planning-reporting--output-quality-completed-)
  - [Outcome Tracking — Measured Change](#outcome-tracking--what-happened-after-the-plan)
- [Quick Start Guide](#quick-start-guide)
- [Setup & Installation](#setup--installation)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [Future Work](#future-work)

---

## Overview

**PM Copilot** bridges the gap between raw customer sentiment and committed engineering delivery. Instead of product managers manually reading hundreds of app reviews, survey answers, and support tickets across disconnected spreadsheets, PM Copilot automatically:

1. **Ingests & Normalizes** raw feedback from CSV or JSON files with deduplication and text sanitization.
2. **Classifies & Scores** sentiment, categories (bugs, features, performance, general), and domain themes.
3. **Surfaces Customer Friction** with explainable, deterministic impact and severity scores.
4. **Synthesizes Comprehensive PRDs** with problem statements, personas, OKRs, and functional/non-functional requirements grounded in measured customer evidence.
5. **Generates Agile User Stories** with Gherkin-syntax acceptance criteria (`Given/When/Then`), story points, and Kanban boards.
6. **Prioritizes Backlogs** using four industry frameworks: RICE, Value vs. Effort 2x2 Matrix, MoSCoW, and Custom Weighted Scoring.
7. **Builds Release Roadmaps** packed into four-week windows with capacity constraints and milestone recommendations.
8. **Tracks Measured Outcomes** comparing two feedback imports over time to verify whether released initiatives actually moved customer sentiment.
9. **Operates 100% Offline When Needed**: Dual-layer architecture with MongoDB Atlas and an automatic zero-config JSON fallback database, plus deterministic NLP engines that run without any external LLM keys.

---

## Key Capabilities

| Capability | Description |
| :--- | :--- |
| **Multi-Provider AI Chain** | Primary: **Google Gemini 2.0 / 1.5 Flash** → Fallback: **Mistral AI** → Fallback: **Groq Cloud (LLaMA 3.3 / ALLaM)** → Deterministic Heuristics. Zero runtime lock-in. |
| **Evidence Grounding** | AI synthesis cites exact customer quote samples, review counts, and measured severity scores. Zero hallucinated metrics. |
| **Dual Storage Layer** | Connects to cloud **MongoDB Atlas** with background indexing, or falls back seamlessly to a local in-memory JSON database. |
| **Interactive Prioritization** | Real-time RICE sliders, interactive 2x2 scatter matrix with drag-and-drop quadrants, and AI re-scoring. |
| **Conversational Copilot** | Persistent multi-turn PM Copilot with global floating widget and contextual citation chips. |
| **Output Quality Audit** | Automated deterministic audit engine scoring completeness, grounding, freshness, and consistency across all generated artifacts. |

---

## Tech Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | React 19 + Vite 5 | Reactive Single-Page Application with custom dark-mode theme |
| **Frontend Routing** | React Router DOM v7 | Protected routes, layout persistence, and view transitions |
| **Styling** | Vanilla CSS Design System | High-performance tokens, micro-animations, and responsive layout |
| **Backend API** | FastAPI (Python 3.10+) | High-throughput asynchronous RESTful API with Pydantic validation |
| **Primary Database** | MongoDB Atlas (Motor async driver) | Cloud NoSQL document store with compound indexes |
| **Fallback Database**| Custom In-Memory JSON Store | Zero-configuration dev & demo data persistence |
| **Authentication** | JWT (python-jose) + bcrypt | Stateless secure bearer token authentication |
| **NLP & Text Mining**| NLTK + Custom Vector Engine | Tokenization, n-grams, text cleaning, and Jaccard clustering |
| **AI LLM Chain** | Gemini 2.0 / Mistral / Groq | Generative PRDs, acceptance criteria, strategic narratives |
| **Data Processing** | Pandas | High-speed batch parsing of CSV and JSON feedback imports |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React 19 + Vite 5)                      │
│                                                                             │
│   ┌──────────────────────── GLOBAL NAVBAR & SECTION BAR ────────────────┐   │
│   │  Workspace Switcher  │  Capture & Analyze  │  Plan  │  Track  │ User│   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌───────────────┐ ┌────────────────────┐ ┌───────────────────────────┐   │
│   │ Dashboard     │ │ Feedback List      │ │ Insights Analytics        │   │
│   │ • Key Metrics │ │ • Paginated Grid   │ │ • Themes & Pain Points    │   │
│   │ • Stage Trail │ │ • Search & Filters │ │ • Feature Request Clusters│   │
│   └───────────────┘ └────────────────────┘ └───────────────────────────┘   │
│   ┌────────────────────┐ ┌────────────────────┐ ┌───────────────────────┐   │
│   │ PRD Workspace      │ │ User Stories       │ │ Prioritization Hub    │   │
│   │ • AI PRD Generator │ │ • Agile Stories    │ │ • RICE Scoring        │   │
│   │ • Markdown Export  │ │ • Kanban Board     │ │ • 2x2 Value/Effort    │   │
│   └────────────────────┘ └────────────────────┘ └───────────────────────┘   │
│   ┌────────────────────┐ ┌────────────────────┐ ┌───────────────────────┐   │
│   │ Roadmap Planner    │ │ Executive Reports  │ │ Outcome Tracker       │   │
│   │ • Release Windows  │ │ • Strategy Reports │ │ • Import-to-Import    │   │
│   │ • Milestones Rec.  │ │ • Quality Audit    │ │ • Delta Metrics       │   │
│   └────────────────────┘ └────────────────────┘ └───────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ Conversational Copilot: Full Page (`/copilot`) & Floating Widget    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / REST API (JWT Authenticated)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BACKEND (FastAPI + Python)                         │
│                                                                             │
│   ┌────────────────────────── API ROUTERS (12) ─────────────────────────┐   │
│   │  /api/auth          /api/workspaces    /api/feedback    /api/insights│  │
│   │  /api/prd           /api/user-stories  /api/prioritize  /api/copilot │  │
│   │  /api/roadmap       /api/reports       /api/quality     /api/outcome │  │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                      │
│   ┌────────────────────── SERVICES & ENGINES LAYER ─────────────────────┐   │
│   │  • ai_service.py: Gemini 2.0 Flash → Mistral → Groq Fallback Chain  │   │
│   │  • text_mining.py & preprocessing.py: NLP Normalization & Stopwords │   │
│   │  • categorization.py & clustering.py: Semantic Request Grouping     │   │
│   │  • theme_extraction.py: Domain Topics & Pain Point Impact Scoring   │   │
│   │  • prd_service.py: Grounded AI Requirements Synthesis               │   │
│   │  • user_story_service.py: Gherkin Acceptance Criteria & DoD         │   │
│   │  • prioritization_service.py: RICE, MoSCoW, 2x2 & Weighted Ranker   │   │
│   │  • roadmap_service.py: Horizon Sequencing & Capacity Packing        │   │
│   │  • report_service.py & quality_service.py: Executive Audit Engine   │   │
│   │  • outcome_service.py: Longitudinal Import Delta Comparison         │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                      │
│   ┌─────────────────────────── STORAGE LAYER ───────────────────────────┐   │
│   │  database.py (Motor async MongoDB)  ◄──►  fallback_db.py (In-Memory)│   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       ▼
                     ┌───────────────────────────────────┐
                     │     MongoDB Atlas (Cloud Store)   │
                     │  • users         • workspaces     │
                     │  • feedback      • insights       │
                     │  • prds          • user_stories   │
                     │  • roadmaps      • reports        │
                     └───────────────────────────────────┘
```

---

## Project Structure

```
AI-Driven-Product-Assistant/
├── MunchMate_500_reviews.csv        # Canonical demo dataset (496 authentic reviews)
├── README.md                        # Project documentation & manual
├── start_all.bat                    # One-click Windows development launcher
├── .gitignore                       # Clean Git exclusion rules
├── .env.example                     # Environment template (Gemini, Mistral, Groq, Mongo)
│
├── backend/
│   ├── main.py                      # FastAPI application entry point & lifespan
│   ├── config.py                    # Centralized settings & environment loader
│   ├── database.py                  # Motor async MongoDB connection manager
│   ├── fallback_db.py               # In-memory JSON fallback store for dev/demo
│   ├── check_mongo.py               # MongoDB connectivity diagnostic tool
│   ├── sample_feedback.csv          # Lightweight starter dataset
│   ├── requirements.txt             # Pinned Python backend dependencies
│   ├── migrate_prioritization_schema.py # Database schema migrator
│   ├── migrate_titles.py            # Item normalization migration script
│   ├── purge_benchmark_feedback.py  # Utility to clean benchmark runs
│   │
│   ├── models/                      # Pydantic schemas and database models
│   │   ├── user.py                  # User authentication & registration schemas
│   │   ├── workspace.py             # Workspace data models
│   │   ├── feedback.py              # Customer feedback record schemas
│   │   ├── insights.py              # Themes, pain points & cluster response models
│   │   ├── prd.py                   # PRD document schema
│   │   ├── user_story.py            # User story, Gherkin criteria & Kanban status
│   │   ├── prioritization.py        # RICE, 2x2 matrix, MoSCoW & weighted models
│   │   ├── copilot.py               # Grounded copilot chat models
│   │   ├── roadmap.py               # Horizon, release windows & milestones schemas
│   │   ├── report.py                # Executive summary & product strategy schemas
│   │   └── quality.py               # Output quality audit evaluation models
│   │
│   ├── routers/                     # FastAPI route controllers
│   │   ├── auth.py                  # /api/auth — JWT token issuance & registration
│   │   ├── workspace.py             # /api/workspaces — Workspace management
│   │   ├── feedback.py              # /api/feedback — Import, list, clean, categorize
│   │   ├── insights.py              # /api/insights — Mining pipeline & cluster views
│   │   ├── prd.py                   # /api/prd — Synthesis, editing & Markdown export
│   │   ├── user_stories.py          # /api/user-stories — Agile decomposition & Kanban
│   │   ├── prioritization.py        # /api/prioritization — Scoring & auto-seeding
│   │   ├── copilot.py               # /api/copilot — Grounded chat assistant
│   │   ├── roadmap.py               # /api/roadmap — Sequencing & rescheduling
│   │   ├── reports.py               # /api/reports — Executive & strategy generation
│   │   ├── quality.py               # /api/quality — Deterministic output audit
│   │   └── outcome.py               # /api/outcome — Longitudinal import comparison
│   │
│   ├── services/                    # Business logic and intelligence algorithms
│   │   ├── ai_service.py            # Multi-provider LLM chain (Gemini/Mistral/Groq)
│   │   ├── preprocessing.py         # Text normalization & tokenization
│   │   ├── data_cleaning.py         # Sanitization, deduplication & normalization
│   │   ├── categorization.py        # Keyword rule-based categorization & sentiment
│   │   ├── text_mining.py           # Shared corpus extraction primitives
│   │   ├── theme_extraction.py      # Domain topic extraction & pain point scoring
│   │   ├── clustering.py            # Semantic feature request clustering
│   │   ├── trend_analysis.py        # Sentiment velocity & product health score
│   │   ├── prd_service.py           # Grounded PRD generation engine
│   │   ├── user_story_service.py    # Acceptance criteria & story point estimator
│   │   ├── prioritization_service.py# RICE, MoSCoW, 2x2 & weighted rank calculations
│   │   ├── roadmap_service.py       # Capacity packing & release sequencing
│   │   ├── report_service.py        # Executive report generator
│   │   ├── quality_service.py       # Deterministic generation audit engine
│   │   ├── outcome_service.py       # Comparative import outcome analysis
│   │   ├── title_normalizer.py      # Title standardization utility
│   │   ├── analysis_jobs.py         # Background analysis job runner
│   │   └── workspace_context.py     # Shared context loaders for planning services
│   │
│   ├── agents/                      # CrewAI multi-agent coordinator (Milestone 2)
│   │   ├── crew.py                  # Agent pipeline orchestrator
│   │   ├── theme_agent.py           # Theme analyst agent
│   │   ├── feature_agent.py         # Feature opportunity strategist agent
│   │   └── trend_agent.py           # Sentiment trajectory analyst agent
│   │
│   ├── tools/                       # Demo builders and verification tools
│   │   ├── _demo_data.py            # Content pools for MunchMate dataset
│   │   ├── _demo_build.py           # MunchMate demo CSV builder
│   │   ├── _demo_verify.py          # Demo verification utility
│   │   ├── _engine_audit.py         # Engine accuracy testing tool
│   │   ├── _outcome_e2e.py          # End-to-end outcome runner
│   │   └── feedback_tools.py        # Feedback querying tools
│   │
│   └── tests/                       # Automated test suites
│       ├── test_milestone1.py       # Pipeline, cleaning & categorization tests
│       ├── test_milestone2.py       # Theme extraction & clustering tests
│       ├── test_milestone3.py       # PRD, stories & prioritization unit tests
│       ├── test_milestone3_integration.py # Live provider integration tests
│       ├── test_milestone4.py       # Roadmap, reports & quality audit (29 tests)
│       ├── test_outcome.py          # Outcome comparison & delta tests (35 tests)
│       ├── test_engine_accuracy.py  # Precision & accuracy tests
│       └── test_10k_benchmark.py    # 10,000-record sub-second performance tests
│
└── frontend/
    ├── index.html                   # HTML entry point with dark theme
    ├── package.json                 # Node dependencies (React 19, React Router 7)
    ├── vite.config.ts               # Vite configuration with API proxy to port 8000
    │
    └── src/
        ├── index.jsx                # React root mount
        ├── index.css                # Global design system & theme variables
        ├── theme.js                 # Theme tokens & colour definitions
        ├── App.jsx                  # Main router setup & protected routes
        │
        ├── fonts/
        │   └── inter-latin.woff2    # Bundled offline typography asset
        │
        ├── hooks/
        │   └── useAnalysisStatus.js # Reactive polling hook for background analysis
        │
        ├── context/
        │   ├── WorkspaceContext.jsx # Active workspace state & switcher provider
        │   └── BusyContext.jsx      # Global background processing context
        │
        ├── components/
        │   ├── Navbar.jsx           # Global 4-stage lifecycle navigation bar
        │   ├── AppLayout.jsx        # Shell wrapper with sticky header & breadcrumbs
        │   ├── Charts.jsx           # Responsive SVG charts (Area, Donut, Bar, Matrix)
        │   ├── FloatingCopilot.jsx  # Expandable global copilot widget
        │   ├── Icon.jsx             # Feather-inspired SVG icon system
        │   ├── ErrorBoundary.jsx    # Component failure safety boundary
        │   ├── ViewTransitions.jsx  # Smooth view progression helper
        │   └── ui/                  # Reusable UI component library
        │       ├── Button.jsx       # Standard styled action buttons
        │       ├── Card.jsx         # Elevating container cards
        │       ├── Controls.jsx     # Form controls, inputs & dropdowns
        │       ├── Feedback.jsx     # Alerts, empty states & notifications
        │       ├── Hint.jsx         # Contextual disclosure tooltips
        │       ├── Layout.jsx       # Grid & column helpers
        │       ├── Menu.jsx         # Context & overflow menus
        │       ├── Modal.jsx        # Accessible dialog overlays
        │       ├── ProgressTrail.jsx# 4-stage product lifecycle breadcrumb
        │       ├── Skeleton.jsx     # Content loading placeholders
        │       ├── Tabs.jsx         # Tabbed container switcher
        │       └── WorkspaceSwitcher.jsx # Global workspace selector
        │
        ├── pages/                   # Application screens
        │   ├── Login.jsx            # User authentication
        │   ├── Register.jsx         # User registration
        │   ├── Dashboard.jsx        # Workspace summary & quick actions
        │   ├── ImportData.jsx       # Drag-and-drop CSV/JSON upload
        │   ├── FeedbackList.jsx     # Paginated, filterable feedback browser
        │   ├── InsightsDashboard.jsx# Themes, pain points & clusters visualizer
        │   ├── PRDWorkspace.jsx     # PRD synthesis, editor & export
        │   ├── UserStoriesWorkspace.jsx # Agile stories, criteria & Kanban
        │   ├── PrioritizationHub.jsx# RICE, 2x2 matrix, MoSCoW & weights
        │   ├── RoadmapPlanner.jsx   # 4-week release lanes & milestone sequencing
        │   ├── ExecutiveReports.jsx # Strategy summaries & output quality audit
        │   ├── OutcomeTracker.jsx   # Longitudinal import delta comparisons
        │   └── CopilotChat.jsx      # Full-page grounded conversational copilot
        │
        └── services/
            └── api.js               # Axios client with JWT auto-injection
```

---

## How It Works

### End-to-End Data Pipeline

```
  CSV / JSON Upload (e.g. MunchMate_500_reviews.csv)
           │
           ▼
  ┌──────────────────┐
  │  1. INGESTION     │  Validate schemas → stream records → create import batch
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │  2. SANITIZATION │  Normalize Unicode → strip HTML/noise → dedup text
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │  3. CLASSIFY     │  Deterministic rule engine → category (bug/feature/perf/gen)
  │                  │  Sentiment scoring: 1-5★ rating mapping or keyword valence
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │  4. MINING       │  Extract domain themes across 8 core operational areas
  │                  │  Rank pain points: Volume(35%) + Low Rating(25%) + Negative%(25%) + Bugs(15%)
  │                  │  Cluster feature requests: Jaccard token overlap + demand scoring
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │  5. PLANNING     │  • Synthesize PRDs citing measured customer quotes & counts
  │                  │  • Generate Agile User Stories with Gherkin acceptance criteria
  │                  │  • Score features via RICE, 2x2 Matrix, MoSCoW, or Weighted Formulas
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │  6. ROADMAP      │  Pack backlog into capacity-bounded 4-week release windows
  │                  │  Formulate milestone recommendations and success metrics
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │  7. REPORTING    │  Generate executive summaries and product strategy reports
  │                  │  Run deterministic Output Quality Audit (0-100 score)
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │  8. OUTCOMES     │  Compare new import against prior baseline to verify movement
  └──────────────────┘
```

---

## User Journey & Lifecycle

The navigation bar organizes product work into four distinct lifecycle stages:

1. **Capture (`/import`, `/feedback`)**: Ingest customer feedback, review paginated raw records, filter by sentiment or rating, and trigger text cleaning.
2. **Analyze (`/insights`, `/dashboard`)**: Examine extracted themes, explore ranked pain points, review semantic feature clusters, and inspect overall Product Health (0–100).
3. **Plan (`/prioritize`, `/prd`, `/user-stories`, `/roadmap`)**:
   - Auto-seed backlog items directly from customer pain points.
   - Score initiatives via RICE, 2x2 Value vs. Effort matrix, or MoSCoW boards.
   - Generate grounded PRDs and decompose them into vertical Agile user stories with Gherkin tests.
   - Sequence work into 4-week capacity-aware release lanes.
4. **Track (`/reports`, `/outcomes`, `/copilot`)**:
   - Generate executive summaries and product strategy reports.
   - Run the Output Quality Audit to verify artifact completeness and evidence grounding.
   - Track longitudinal import deltas to prove customer sentiment improved after a release.
   - Consult the conversational PM Copilot anytime via full page or floating widget.

---

## API Reference

### Authentication & Workspaces
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/register` | Register a new product manager account |
| `POST` | `/api/auth/login` | Authenticate and obtain JWT access token |
| `GET` | `/api/workspaces` | List all available workspaces |
| `POST` | `/api/workspaces` | Create a new isolated product workspace |
| `GET` | `/api/workspaces/{id}/stats` | Retrieve workspace feedback summary statistics |

### Feedback Ingestion & Processing
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/feedback/import` | Upload CSV/JSON feedback files with multipart streaming |
| `GET` | `/api/feedback` | List paginated feedback with filtering (category, sentiment, source) |
| `POST` | `/api/feedback/clean` | Trigger text normalization and deduplication |
| `POST` | `/api/feedback/categorize` | Trigger rule-based category and sentiment classification |
| `GET` | `/api/feedback/import-logs` | Retrieve batch import history |

### Insights & Intelligence
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/insights/{workspace_id}/analyze` | Execute the full intelligence pipeline |
| `GET` | `/api/insights/{workspace_id}` | Retrieve complete workspace insights & health score |
| `GET` | `/api/insights/{workspace_id}/themes` | Retrieve extracted customer feedback themes |
| `GET` | `/api/insights/{workspace_id}/pain-points` | Retrieve ranked friction points with impact scores |
| `GET` | `/api/insights/{workspace_id}/clusters` | Retrieve semantic feature request clusters |
| `GET` | `/api/insights/{workspace_id}/trends` | Retrieve chronological sentiment and volume trends |

### Requirements & Agile Workspace
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/prd/generate` | Synthesize an evidence-grounded PRD via AI |
| `GET` | `/api/prd/workspace/{workspace_id}` | List all PRDs in a workspace |
| `GET` | `/api/prd/{id}` | Retrieve complete PRD document |
| `PUT` | `/api/prd/{id}` | Update editable PRD sections |
| `GET` | `/api/prd/{id}/export` | Export PRD as GitHub-flavored Markdown |
| `POST` | `/api/user-stories/generate` | Generate Agile stories with Gherkin criteria |
| `GET` | `/api/user-stories/workspace/{workspace_id}` | List user stories (optionally filtered by PRD) |
| `PATCH` | `/api/user-stories/{id}/status` | Update Kanban status (`backlog`, `in_progress`, `in_review`, `done`) |

### Prioritization & Roadmapping
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/prioritization/workspace/{workspace_id}` | List prioritization backlog items |
| `POST` | `/api/prioritization/workspace/{workspace_id}/auto-seed` | Auto-seed items from pain points & clusters |
| `POST` | `/api/prioritization/workspace/{workspace_id}/ai-evaluate` | Recalibrate priority scores via LLM |
| `GET` | `/api/prioritization/workspace/{workspace_id}/weights` | Read configurable weighted scoring rules |
| `POST` | `/api/prioritization/workspace/{workspace_id}/weights` | Update dynamic weighting parameters |
| `POST` | `/api/roadmap/generate` | Sequence backlog into 4-week release windows |
| `GET` | `/api/roadmap/{workspace_id}` | Retrieve active workspace release plan |
| `PATCH` | `/api/roadmap/{workspace_id}/items/{item_id}` | Move initiative to another release window |
| `GET` | `/api/roadmap/{workspace_id}/export` | Export complete roadmap as Markdown |

### Reporting, Quality & Outcomes
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/reports/generate` | Generate Executive Summary or Strategy Report |
| `GET` | `/api/reports/workspace/{workspace_id}` | List all generated reports |
| `GET` | `/api/reports/{id}/export` | Export report as Markdown |
| `GET` | `/api/quality/{workspace_id}/evaluate` | Run deterministic output quality audit |
| `GET` | `/api/quality/{workspace_id}/export` | Export audit evaluation as Markdown |
| `GET` | `/api/outcome/{workspace_id}/batches` | List import batches for longitudinal comparison |
| `GET` | `/api/outcome/{workspace_id}/compare` | Compute measured movement between two imports |
| `GET` | `/api/outcome/{workspace_id}/export` | Export comparison analysis as Markdown |

### Conversational Copilot
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/copilot/chat` | Send grounded query to PM Copilot |
| `GET` | `/api/copilot/history/{workspace_id}` | Retrieve conversation history |
| `DELETE` | `/api/copilot/history/{workspace_id}` | Reset conversation session |
| `GET` | `/api/copilot/context/{workspace_id}` | Inspect active knowledge grounding context |

---

## Data Models

### Feedback Record
```json
{
  "_id": "66f4b1e2a9b3c4d5e6f70891",
  "workspace_id": "66f4b1e2a9b3c4d5e6f70890",
  "source": "app_review",
  "title": "Frequent crash on checkout",
  "content": "Every time I tap place order after adding a coupon, the app freezes and crashes.",
  "customer_name": "Sarah J.",
  "rating": 1,
  "category": "bug_report",
  "sentiment": "negative",
  "theme": "Checkout & Payments",
  "status": "new",
  "cleaned": true,
  "created_at": "2026-10-12T14:22:10Z",
  "batch_id": "batch_20261012_142210"
}
```

### Prioritization Item
```json
{
  "id": "item_auth_biometric",
  "name": "Biometric FaceID / Fingerprint Authentication",
  "workspace_id": "66f4b1e2a9b3c4d5e6f70890",
  "rice": {
    "reach": 850,
    "impact": 3,
    "confidence": 80,
    "effort": 2,
    "score": 1020.0
  },
  "value_vs_effort": {
    "value": 85,
    "effort": 30,
    "quadrant": "quick_wins"
  },
  "moscow": "must_have",
  "weighted": {
    "customer_demand": 92,
    "business_impact": 85,
    "technical_feasibility": 80,
    "risk_mitigation": 70,
    "score": 83.4
  },
  "rank": 1
}
```

---

## Milestones & Implementation

### Milestone 1 — Feedback Pipeline (Completed ✅)
- Multi-source file ingestion (CSV and JSON) with automatic column mapping.
- Text normalization, whitespace stripping, HTML/URL removal, and deduplication.
- Rule-based keyword categorization across Bug Reports, Feature Requests, Performance Issues, and General Feedback.
- Deterministic sentiment scoring using rating thresholds and keyword valence.
- Zero-config in-memory JSON fallback when MongoDB is unconfigured or unreachable.

### Milestone 2 — AI-Powered Insights (Completed ✅)
- **Theme Mining**: Identifies product topics across 8 domains (Auth, Performance, UI/UX, Payments, Notifications, Search, Stability, General).
- **Pain Point Engine**: Ranks friction using: `Volume (35%) + Low Rating (25%) + Negative Sentiment % (25%) + Bug Ratio (15%)`.
- **Feature Request Clustering**: Semantic grouping via Jaccard token overlap + demand scoring: `Volume (45%) + Unique Users (30%) + Rating Inversion (25%)`.
- **Product Health Metric**: Composite 0–100 score: `Sentiment Ratio (45pts) + Avg Rating (35pts) + Bug Ratio (20pts)`.
- **CrewAI Multi-Agent Pipeline**: Optional 3-agent intelligence suite (Theme Analyst, Opportunity Strategist, Trend Specialist).

### Milestone 3 — Planning & Requirements Generation Workspace (Completed ✅)
- **Generative AI PRD Synthesis**: Comprehensive documents with Problem Statements, User Personas, Functional Requirements, Non-Functional SLAs, and KPI telemetry.
- **Evidence Grounding**: Direct citation of customer review counts, negative sentiment percentages, and verbatim quotes.
- **Agile User Stories**: Auto-generated stories with Gherkin acceptance criteria (`Given/When/Then`), story points, and Kanban boards.
- **Interactive Prioritization Hub**: RICE, 2x2 Value vs. Effort matrix, MoSCoW boards, and weighted custom formulas with real-time recalculation.
- **Conversational PM Copilot**: Persistent assistant with global floating widget and grounded citation chips.

### Milestone 4 — Roadmap Planning, Reporting & Output Quality (Completed ✅)
- **Capacity-Aware Roadmapping**: Sequences the backlog into 4-week release windows based on RICE, weighted scores, defect precedence, and customer demand.
- **Milestone Recommendations**: Formulates one milestone per release window with sequencing rationale, exit criteria, and telemetry success metrics.
- **Interactive Rescheduling**: Moving an initiative to another window automatically rebalances capacity and recomputes milestone narratives.
- **Executive Summaries & Strategy Reports**: Structured reports covering executive headlines, product health snapshots, strategic pillars, and delivery risks.
- **Deterministic Quality Audit**: Automated evaluation of completeness, grounding, freshness, and consistency across all generated artifacts (scored 0–100).

### Outcome Tracking — What Happened After the Plan
- Longitudinal comparison between two feedback imports of the same workspace.
- Normalized topic frequency per 100 records to eliminate sample size distortion.
- Statistical significance thresholds (minimum mention volumes and percentage shifts) to avoid reporting random noise as product trends.
- Surfacing comparability caveats (e.g., changes in review source distribution).

---

## Quick Start Guide

### Option A: One-Click Startup (Windows)
Double-click [start_all.bat](file:///c:/Users/Asus/Desktop/project2/start_all.bat) or run:
```cmd
start_all.bat
```
This automatically launches the FastAPI backend on `http://127.0.0.1:8000` and the React frontend on `http://localhost:5173` in separate terminals.

### Option B: Immediate Demo Data Testing
1. Open `http://localhost:5173` and register/login.
2. Create a workspace (e.g., "MunchMate Delivery").
3. Navigate to **Capture → Import Feedback**.
4. Drag and drop [MunchMate_500_reviews.csv](file:///c:/Users/Asus/Desktop/project2/MunchMate_500_reviews.csv) (bundled in the root folder).
5. Click **Run Analysis** to populate themes, pain points, feature clusters, and health score in seconds.

---

## Setup & Installation

### Prerequisites
- **Python**: 3.10, 3.11, 3.12, or 3.13
- **Node.js**: 18+ (includes npm)
- **MongoDB Atlas** (Optional: falls back automatically to local storage if omitted)

### 1. Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend server
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup
```bash
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Environment Variables

Copy [.env.example](file:///c:/Users/Asus/Desktop/project2/.env.example) to `backend/.env`:

```env
# MongoDB Connection (Optional: uses in-memory JSON database if omitted)
MONGO_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/?appName=pm_copilot
DB_NAME=pm_copilot

# JWT Secret Key (Change in production!)
SECRET_KEY=your-secure-secret-key-32-characters-or-longer

# AI Provider 1 (Primary): Google Gemini
# Free API key at https://aistudio.google.com/
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# AI Provider 2 (Fallback): Mistral AI
# Free API key at https://console.mistral.ai/
MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-small-latest

# AI Provider 3 (Fallback): Groq Cloud
# Free API key at https://console.groq.com/
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
```

> **Note on Offline Operation**: If no AI API keys are configured, all core features (categorization, sentiment, themes, pain points, clustering, RICE scoring, roadmaps, and reports) execute using deterministic NLP and heuristic engines.

---

## Running Tests

All automated test suites execute locally using Python's built-in `unittest` runner:

```bash
cd backend

# Milestone 1: Feedback Ingestion, Cleaning & Categorization
python -m unittest tests/test_milestone1.py

# Milestone 2: Theme Extraction, Pain Points & Clustering
python -m unittest tests/test_milestone2.py

# Milestone 3: PRDs, User Stories & Prioritization Hub
python -m unittest tests/test_milestone3.py

# Milestone 4: Roadmap Planning, Reports & Quality Evaluation (29 tests)
python -m unittest discover -s tests -p "test_milestone4.py"

# Outcome Tracking: Longitudinal Import Comparison (35 tests)
python -m unittest discover -s tests -p "test_outcome.py"

# Engine Precision & Accuracy Verification
python -m unittest tests/test_engine_accuracy.py

# 10,000-Record Sub-Second Benchmark
python tests/test_10k_benchmark.py

# Run all test suites together
python -m unittest discover -s tests -p "test_*.py"
```

---

## Future Work

- 🔗 **Two-Way Issue Tracker Sync**: Native integrations with Jira, Linear, and GitHub Issues.
- 🎙️ **Voice & Meeting Transcripts**: Ingestion of customer interview audio and Zoom/Meet call transcripts.
- 👥 **Real-Time Multiplayer**: Collaborative roadmapping and live backlog refinement.
- 🧭 **Server-Side PDF Generation**: Direct vector PDF export for executive reports.
- ⚡ **Distributed Worker Queues**: Celery/Redis worker queues for massive million-row feedback corpora.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

<p align="center">
  <b>Built with ❤️ using FastAPI, React 19, MongoDB Atlas, and Google Gemini AI</b>
</p>

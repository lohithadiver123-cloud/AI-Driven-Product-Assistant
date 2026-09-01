# AI-Driven Product Assistant based on Customer Feedback with Planning & Requirements Generation Workspace

An intelligent AI Product Manager Copilot designed to ingest, process, categorize, and synthesize customer feedback, support tickets, and feature requests into actionable product requirement documents (PRDs), user stories, and strategic roadmaps.

---

## 🚀 Technology Stack

- **Frontend**: React 19, Vite, React Router, JavaScript, CSS (Modern Glassmorphic PM Dashboard)
- **Backend**: Python 3.14+, FastAPI, Uvicorn, Pydantic, Motor, PyMongo, Pandas, PyJWT, Argon2-cffi, aiosmtplib
- **Authentication**: JWT Access Tokens (30 min) + Rotatable Stored Refresh Tokens (14 days), Argon2id Hashing, Single-Use Password Reset & Email Verification Tokens
- **Database**: MongoDB Atlas (`ai_product_assistant`)
- **Multi-Tenancy**: Organization & Workspace Isolation scoping all datasets, feedback, support tickets, and metrics
- **Data Pipelines**: Text Preprocessing, Regex Normalization, Controlled 10-Domain Categorization, Confidence Scoring, Quality Reporting

---

## 📁 Project Architecture & Folder Structure

```text
AI-Product-Assistant/
│
├── frontend/                     # React + Vite Frontend
│   ├── src/
│   │   ├── context/
│   │   │   └── AuthContext.jsx   # Global Authentication & Workspace State
│   │   ├── pages/
│   │   │   ├── Login.jsx         # User Authentication
│   │   │   ├── Register.jsx      # Workspace & Account Registration
│   │   │   ├── ForgotPassword.jsx# Password Recovery
│   │   │   ├── ResetPassword.jsx # Single-Use Password Reset
│   │   │   └── VerifyEmail.jsx   # Email Verification Handler
│   │   ├── components/           # UI Components
│   │   │   ├── ProtectedRoute.jsx# Auth Route Guard
│   │   │   ├── Navbar.jsx        # Navigation, User Profile, Role Badge, Workspace Switcher
│   │   │   ├── WorkspaceSettingsModal.jsx # Team Members & Role Management
│   │   │   ├── ChangePasswordModal.jsx    # In-App Password Update
│   │   │   ├── Dashboard.jsx     # KPI Cards, Distribution Bars, Pain Point Visualizers
│   │   │   ├── FeedbackTable.jsx # Multi-Filter Table, Search, Detail Modal
│   │   │   └── UploadModal.jsx   # Drag & Drop Ingestion with Live Report
│   │   ├── services/
│   │   │   └── api.js            # REST API Client with JWT Interceptors & Auto-Refresh
│   │   ├── App.jsx               # Application Coordinator & React Router
│   │   ├── App.css               # Styling System & Layouts
│   │   └── main.jsx              # React DOM Entrypoint
│   ├── package.json              # Node dependencies & scripts
│   └── vite.config.js            # Vite bundler configuration
│
├── backend/                      # FastAPI Python Backend
│   ├── app/
│   │   ├── api/                  # Modular REST API endpoints
│   │   │   ├── health.py         # /health & /health/database checks
│   │   │   ├── auth.py           # Register, Login, Refresh, Logout, Verify, Reset
│   │   │   ├── workspaces.py     # Workspaces CRUD, Member Management, Switcher
│   │   │   ├── feedback.py       # Scoped Feedback CRUD, /stats, /categories, /upload
│   │   │   ├── support_tickets.py# Scoped Support Ticket endpoints
│   │   │   └── router.py         # Main router aggregator (/api/v1)
│   │   ├── database/             # MongoDB connection & collections
│   │   │   ├── connection.py     # Async Motor client, lifecycle & index setup
│   │   │   └── collections.py    # Collection name definitions
│   │   ├── dependencies/         # Security & RBAC dependencies
│   │   │   └── auth.py           # get_current_user, require_role, workspace isolation
│   │   ├── schemas/              # Pydantic data schemas & serializers
│   │   │   ├── common.py         # Base models, Pagination, PyObjectId
│   │   │   ├── user.py           # User models & profile schemas
│   │   │   ├── workspace.py      # Workspace & member schemas
│   │   │   ├── auth.py           # Token & password recovery schemas
│   │   │   ├── feedback.py       # Feedback schemas with workspace_id
│   │   │   ├── stats.py          # Statistics & Category Info schemas
│   │   │   ├── support_ticket.py # Support ticket schemas with workspace_id
│   │   │   ├── feature_request.py# Feature request schemas
│   │   │   ├── health.py         # Diagnostic response schemas
│   │   │   └── ingestion.py      # Quality & Ingestion report schemas
│   │   ├── services/             # Security, Ingestion, and Business logic
│   │   │   ├── password_service.py # Argon2id password hashing & strength validation
│   │   │   ├── token_service.py  # JWT encoding, cryptographic token generation & rotation
│   │   │   ├── email_service.py  # Modular SMTP dispatcher with dev-mode mock fallback
│   │   │   ├── preprocessing.py  # Text cleaning, normalization
│   │   │   ├── classification.py # 10 Controlled categories, Confidence, Sentiment, Priority
│   │   │   └── ingestion.py      # Ingestion engine (CSV/JSON, deduplication, batch)
│   │   ├── config.py             # Environment configuration (Pydantic Settings)
│   │   └── main.py               # FastAPI application entrypoint with CORS
│   ├── .env                      # Local configuration (Secrets ignored by git)
│   ├── .env.example              # Configuration template
│   ├── requirements.txt          # Python dependencies
│   ├── test_auth_complete.py     # Automated Auth & RBAC test suite
│   └── test_milestone1_complete.py # Full Milestone 1 verification suite
│
├── data/                         # Sample datasets
│   └── raw/
│       ├── sample_feedback.csv
│       ├── sample_feedback.json
│       ├── sample_support_tickets.csv
│       ├── sample_support_tickets.json
│       └── invalid_feedback.csv
│
└── docs/                         # Comprehensive Documentation
    ├── system-requirements.md    # SRS Specification
    ├── system-architecture.md    # System Architecture & Diagrams
    ├── database-schema.md        # MongoDB Schema & Collection Dictionary
    ├── data-pipeline.md          # 7-Stage Preprocessing Pipeline
    └── api.md                    # REST API Endpoints Specification
```

---

## 🔒 Authentication & Authorization Architecture

### 1. Registration & Default Workspace
- When a user registers (`POST /api/v1/auth/register`), an Argon2id hash of their password is stored in `users`.
- A default Workspace is provisioned and linked to the user as `OWNER`.
- A 24-hour single-use cryptographic email verification token is generated and dispatched via email.
- The session is issued an immediate short-lived JWT Access Token (30 min) and a Rotatable Refresh Token (14 days).

### 2. Role-Based Access Control (RBAC)
| Role | Permissions |
|---|---|
| `OWNER` | Full workspace administration, manage team members, change roles, upload datasets, create/edit/delete records |
| `ADMIN` | Manage workspace members (except owner), upload datasets, create/edit/delete feedback & tickets |
| `MEMBER` | View dashboards, create single items, edit records, upload datasets |
| `VIEWER` | Read-only access to dashboards, feedback repository, and reports |

### 3. Multi-Tenant Workspace Isolation
Every feedback and support ticket document is tagged with `workspace_id`. All queries, statistics aggregations, and ingestion pipelines strictly partition data by the user's active workspace.

---

## 📧 Email Configuration (SMTP & Dev Mode)

The system supports standard SMTP credentials configured via `backend/.env`:

```env
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=your_smtp_password
SMTP_FROM_EMAIL=noreply@aiproductassistant.com
SMTP_FROM_NAME=AI Product Assistant
SMTP_USE_TLS=true
```

> **Development Mode Fallback**: If `SMTP_HOST` is left blank, the application automatically enters **Dev Mock Mode**. Email links (verification & password reset) are safely logged to the console and stored in memory without crashing the server.

---

## ⚡ Setup & Execution

### 1. Backend Server
```bash
cd backend
# Activate virtual environment
.\venv\Scripts\activate
# Install requirements
pip install -r requirements.txt
# Run FastAPI server
python -m uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Development Server
```bash
cd frontend
# Install packages
npm install
# Run Vite dev server
npm run dev
```

### 3. Automated Test Verification
```bash
cd backend
# Run complete Auth & RBAC test suite
python test_auth_complete.py

# Run Milestone 1 data pipeline tests
python test_milestone1_complete.py
```

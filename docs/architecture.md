# System Architecture & Technical Specification

## 1. Executive Summary

The **AI-Driven Product Assistant based on Customer Feedback with Planning & Requirements Generation Workspace** is an intelligent Product Manager Copilot designed to automate the lifecycle of product requirement discovery. 

It unifies incoming feedback from diverse channels (reviews, support tickets, survey responses, social feedback, CSV/JSON batch imports), cleans and preprocesses raw text, performs categorization and sentiment analysis across 10 controlled categories with confidence scoring, and provides a modern React workspace for product managers to analyze feedback signals and track product metrics.

---

## 2. High-Level Architecture Diagram

```
┌────────────────────────────────────────────────────────┐
│                   React Frontend (Vite)                │
│  ┌──────────────────────────────────────────────────┐  │
│  │ PM Workspace & Interactive Analytics Dashboard   │  │
│  │   • KPI Summary Cards & Pain Point Visualizers   │  │
│  │   • Feedback Repository (Search, Filter, Detail) │  │
│  │   • Dataset Ingestion Hub (Drag-and-Drop CSV)    │  │
│  └────────────────────────┬─────────────────────────┘  │
└───────────────────────────┼────────────────────────────┘
                            │ HTTP / REST & Multipart Form-Data
                            │ CORS Protected (:5173 -> :8000)
┌───────────────────────────▼────────────────────────────┐
│                    FastAPI Backend                     │
│  ┌──────────────────────────────────────────────────┐  │
│  │ API Routing & Controllers                        │  │
│  │   • /health, /health/database                    │  │
│  │   • /api/v1/feedback (List, CRUD, Search)        │  │
│  │   • /api/v1/feedback/stats (Live Aggregations)   │  │
│  │   • /api/v1/feedback/categories (10 Definitions) │  │
│  │   • /api/v1/feedback/upload (CSV Ingestion)      │  │
│  │   • /api/v1/feedback/upload-json (JSON Ingest)   │  │
│  │   • /api/v1/support-tickets (Support Desk CRUD)  │  │
│  └────────────────────────┬─────────────────────────┘  │
│                           │                            │
│  ┌────────────────────────▼─────────────────────────┐  │
│  │ Python Services & Business Logic Layer           │  │
│  │   • Preprocessing & Cleaning (Regex/HTML/URLs)   │  │
│  │   • Controlled Classifier (10 Categories, Conf)  │  │
│  │   • Sentiment & Priority Heuristics              │  │
│  │   • Ingestion Pipeline (Encoding, Deduplication) │  │
│  └────────────────────────┬─────────────────────────┘  │
│                           │                            │
│  ┌────────────────────────▼─────────────────────────┐  │
│  │ Database Abstraction Layer (Motor / PyMongo)     │  │
│  │   • Async Connection Pool & Ping Health Checks   │  │
│  └────────────────────────┬─────────────────────────┘  │
└───────────────────────────┼────────────────────────────┘
                            │ Async Driver (TLS)
┌───────────────────────────▼────────────────────────────┐
│                   MongoDB Atlas Cluster                │
│   Collections: feedback, support_tickets, features,    │
│                users, workspaces, themes, analytics    │
└────────────────────────────────────────────────────────┘
```

---

## 3. Controlled Categorization & Classification System

The classification service groups raw feedback into 10 mutually exclusive, explainable product management domains:

| # | Category | Description | Primary Keywords / Triggers |
|---|---|---|---|
| 1 | **Authentication** | Login, access, credentials, MFA | `login`, `sso`, `password`, `2fa`, `mfa`, `token`, `oauth`, `faceid` |
| 2 | **Performance** | Speed, load times, responsiveness | `slow`, `lag`, `latency`, `timeout`, `hang`, `battery drain`, `504` |
| 3 | **Payment** | Billing, credit cards, pricing | `charge`, `payment`, `refund`, `invoice`, `subscription`, `stripe`, `vat` |
| 4 | **Bug** | Crashes, broken UI, exceptions | `crash`, `error`, `exception`, `500`, `502`, `bug`, `broken`, `glitch` |
| 5 | **UI/UX** | Design, readability, navigation | `dark mode`, `theme`, `contrast`, `color`, `font`, `button`, `sidebar` |
| 6 | **Feature Request** | New functionality suggestions | `feature`, `please add`, `request`, `would love`, `allow custom` |
| 7 | **Notifications** | Alerts, push notifications, email | `notification`, `push`, `email alert`, `sms`, `mention`, `reminder` |
| 8 | **Account Management** | Roles, workspaces, team, GDPR | `account`, `workspace`, `organization`, `member`, `gdpr`, `ownership` |
| 9 | **Integration** | 3rd party connections | `jira`, `figma`, `notion`, `slack`, `github`, `gitlab`, `zapier` |
| 10 | **Other** | General inquiries & uncategorized | Fallback if keyword match score is 0 or confidence < 0.35 |

---

## 4. End-to-End Data Pipeline

```
Raw Customer Feedback (CSV / JSON / API)
       │
       ▼
[1. Structural Validation] (Non-empty text, required columns)
       │
       ▼
[2. Deduplication Engine] (Signature: customer_id + source + text against DB)
       │
       ▼
[3. Python Text Cleaning] (HTML strip, URL removal, Contractions, Whitespace)
       │
       ▼
[4. Rule-Based Classifier] (Calculates Category & Category Confidence 0.70 - 0.96)
       │
       ▼
[5. Sentiment & Priority Tagger] (Positive/Neutral/Negative; Urgent/High/Med/Low)
       │
       ▼
[6. MongoDB Document Insertion] (Stores verbatim `text`, `cleaned_text`, `category_confidence`)
       │
       ▼
[7. Aggregated REST API] (Serves paginated list, search, and live stats to React)
       │
       ▼
[8. React UI Workspace] (Interactive Dashboard, Feedback Table, and Upload Hub)
```

---

## 5. MongoDB Schema (Feedback)

```json
{
  "_id": "6a95bfaf2c4783e324933a52",
  "customer_id": "CUST-1001",
  "source": "AppStore",
  "type": "review",
  "text": "The new login flow with Google SSO is completely broken on iOS 17. https://app.example.com/login",
  "cleaned_text": "The new login flow with Google SSO is completely broken on iOS 17.",
  "category": "Authentication",
  "category_confidence": 0.92,
  "sentiment": "Negative",
  "priority": "High",
  "status": "New",
  "created_at": "2026-08-01T10:15:00.000Z",
  "updated_at": "2026-08-31T23:30:00.000Z",
  "metadata": {}
}
```

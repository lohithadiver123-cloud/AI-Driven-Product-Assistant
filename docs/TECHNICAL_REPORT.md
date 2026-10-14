# PM Copilot — Technical Report

**Project:** AI-Driven Product Assistant based on Customer Feedback with Planning & Requirements Generation Workspace
**Version:** 0.4.0 (Milestone 4)
**Stack:** FastAPI + Motor (MongoDB) + Pydantic · React 18 + Vite
**Test suite:** 29 Milestone 4 tests, 24 Milestone 1–3 tests

---

## 1. Problem Statement

Product managers collect far more signal than they can read: support tickets, app-store reviews,
survey answers, in-app feedback and feature requests. Turning that volume into decisions means
answering five questions repeatedly — *what are customers actually complaining about, what should we
build next, what does the requirement look like, what ships when, and how do we know any of this is
true?*

This system answers all five from one workspace. Feedback is imported, cleaned, categorised, mined
for themes and pain points, clustered into feature demand, scored with configurable prioritisation
frameworks, turned into PRDs and Agile user stories, sequenced into a roadmap, and reported on —
with every generated artefact carrying the measured evidence it was built from.

## 2. Architecture

```
┌──────────────────────────── React + Vite (SPA) ────────────────────────────┐
│ Login · Dashboard · Insights · Feedback · PRD Studio · User Stories        │
│ Prioritization · Roadmap · Reports · Copilot · Import                      │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │ REST + JWT (Bearer)
┌───────────────────────────────────▼────────────────────────────────────────┐
│                            FastAPI (backend/main.py)                       │
│  routers/  auth · workspace · feedback · insights · prd · user_stories      │
│            prioritization · copilot · roadmap · reports · quality           │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │ Depends(get_authorization_header)
┌───────────────────────────────────▼────────────────────────────────────────┐
│                                 services/                                  │
│  Deterministic engines            AI layer                Document layer    │
│  categorization · text_mining ·   ai_service (Gemini →    prd_service ·     │
│  theme_extraction · clustering ·  Mistral → Groq →        user_story_service│
│  trend_analysis · data_cleaning   deterministic)          report_service ·  │
│  prioritization_service           workspace_context       roadmap_service · │
│                                                           copilot_service · │
│                                                           quality_service   │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │ motor (async)
                    ┌───────────────▼────────────────┐
                    │  MongoDB (or JSON fallback in  │
                    │  backend/.demo_data/*.json)    │
                    └────────────────────────────────┘
```

**Design rule that shapes everything:** the deterministic engines are the product, and the LLM is an
optional narrator. Every AI call sits in a chain — **Gemini → Mistral → Groq → deterministic engine**
(`services/ai_service.py`, `GEMINI_MODELS`, `MISTRAL_MODELS`, `GROQ_MODELS`). If every provider is
down, out of quota or misconfigured, the feature still returns a complete, evidence-grounded result,
and each artefact records which engine actually produced it (`ai_model`, and a provenance block).

**Persistence rule:** `database._mongodb_available` decides between MongoDB and the JSON fallback in
`backend/fallback_db.py`. Every service branches the same way, so the application runs unchanged on a
laptop with no database.

## 3. Data Model

| Collection | Written by | Purpose |
| :--- | :--- | :--- |
| `users` | auth | PBKDF2-hashed credentials, workspace membership |
| `workspaces` | workspace | One product under analysis |
| `feedback` | feedback import | Normalised records: `title`, `content`, `rating`, `source`, `customer`, `category`, `sentiment`, `cleaned`, `created_at` |
| `import_logs` | feedback import | Per-file import audit: rows read, succeeded, failed |
| `workspace_insights` | insights analyze | `total_analyzed`, `health_score`, `themes`, `pain_points`, `feature_clusters`, `trends`, `*_distribution`, `ai_summary`, `ai_model` |
| `prds` | prd | Structured PRD + rendered Markdown + evidence block |
| `user_stories` | user_stories | Stories with Gherkin acceptance criteria, points, status |
| `prioritization_items` | prioritization | RICE, Value vs Effort, MoSCoW, weighted scores, source cluster/pain point |
| `framework_weights` | prioritization | Per-workspace weights for the weighted framework |
| `copilot_chats` | copilot | Conversation history per workspace/session |
| `roadmaps` | roadmap *(new)* | The sequenced plan: releases, milestones, items, deferred backlog, evidence |
| `reports` | reports *(new)* | Executive summaries and product strategy reports |

Each roadmap and report document stores an `evidence` block: which engine produced it, how many
records were analysed, how many support the content, and the method used. A reader can therefore
audit any generated document without leaving it.

## 4. Modules Implemented

| # | Module | Where it lives | Notes |
| :-- | :--- | :--- | :--- |
| 1 | User authentication & workspace management | `routers/auth.py`, `routers/workspace.py` | JWT (HS256), PBKDF2 (600k iterations) with legacy bcrypt verification, workspace CRUD + stats |
| 2 | Feedback & support-ticket ingestion | `routers/feedback.py` | CSV/JSON import with column aliases, dedupe, clean, batch categorise, import logs |
| 3 | Product analytics integration | `routers/feedback.py`, `routers/workspace.py`, `routers/outcome.py` | Multi-source records with per-source statistics, plus a real time axis (§5.4): change is measured between the imports a workspace's feedback arrived in. Product **telemetry** (sessions, retention, crash-free rate, conversion) is not ingested and is never stated |
| 4 | Classification & theme extraction | `services/categorization.py`, `services/theme_extraction.py`, `services/text_mining.py` | Rule-based categories/sentiment + mined themes and impact-scored pain points |
| 5 | Feature request aggregation | `services/clustering.py` | Order-independent canonical grouping with unique-requester counting |
| 6 | Prioritization & impact analysis | `services/prioritization_service.py` | RICE, Value vs Effort, MoSCoW, configurable weighted scoring, auto-seed from clusters/pain points |
| 7 | PRD & user story generation | `services/prd_service.py`, `services/user_story_service.py` | Structured documents, Markdown export, Gherkin criteria, Fibonacci points |
| 8 | **Roadmap planning & visualization** | `services/roadmap_service.py`, `routers/roadmap.py`, `pages/RoadmapPlanner.jsx` | **Milestone 4** |
| 9 | Conversational product intelligence | `services/copilot_service.py`, `pages/CopilotChat.jsx` | Question answering grounded in stored analysis, prioritisation and documents |
| 10 | Reporting & insights dashboard | `services/report_service.py`, `services/quality_service.py`, `pages/ExecutiveReports.jsx` | **Milestone 4** — reporting plus output-quality evaluation |

## 5. Milestone 4 — What Was Added

### 5.1 Roadmap planning and milestone recommendation

`POST /api/roadmap/generate` sequences the prioritisation backlog into release windows and recommends
the milestones inside each one.

**Inputs:** the workspace's prioritization items (their RICE/weighted scores, effort, MoSCoW
classification and feedback volume), the stored analysis behind them (pain points, clusters,
sentiment and rating breakdowns), and three planning parameters — horizon in weeks, capacity per
release, and an optional strategic focus.

**Sequencing rule** (`roadmap_service._order_key`):

1. RICE score, descending — the framework the user configured.
2. Weighted multi-factor score, descending.
3. Defect, performance and security work breaks a tie ahead of feature work at equal value.
4. Feedback volume, then name — so the order is total and reproducible.

**Packing** (`_pack_items`): release windows are fixed four-week blocks (`WEEKS_PER_RELEASE = 4`),
and each window holds a configured capacity in effort units. Items are placed highest-value first into
the earliest window with room. An item that does not fit an early window stays a candidate for the
next one, so a large initiative never strands a small one behind it. Work that fits nowhere is
returned as a backlog with its scores intact — never silently dropped.

**Milestones** (`_build_milestone`): one per window that has work. Each carries a theme derived from
its own composition (*Trust & Reliability* when fix work dominates, *Growth & Experience* otherwise),
a scope objective naming the items and the customer records behind them, a confidence level from the
evidence volume (high ≥ 500 records, medium ≥ 100, low below), exit criteria and success metrics.

Exit criteria and metrics follow the repository's honesty convention, taken from the PRD service:

* Baselines are labelled `Measured:` and targets `Proposed:`.
* Metrics are only those this workspace can observe — item throughput, records behind the milestone,
  negative-sentiment share and average rating of the matching records.
* Telemetry the product cannot see (revenue, retention, latency) is never asserted.

**AI usage:** `_ai_narrative` sends the *already computed* plan to Gemini, Mistral or Groq and asks
only for a strategy paragraph, milestone names, objectives and rationales. The prompt forbids
changing sequence, dates or figures, and the merge step only accepts narrative fields — a
hallucinated number or reordered release cannot reach the user through it. When no provider answers,
the plan stands on its deterministic narrative and records
`"Deterministic planning engine"` as its author.

**Interactive planning:** `PATCH /api/roadmap/{workspace_id}/items/{item_id}` moves one initiative to
another release and rebuilds milestones, capacity totals, exit criteria and the Markdown around it.
A milestone whose scope is unchanged keeps its AI-written narrative, so a model is never asked to
describe work it did not see.

### 5.2 Executive summaries and product strategy reports

`POST /api/reports/generate` produces either an `executive_summary` or a `product_strategy` report.

Sections: headline, executive summary, measured product-health snapshot, key findings, strategic
pillars, roadmap outlook, product indicators, risks, recommendations, and an evidence-and-method
block. Reports render to GitHub-flavoured Markdown and can be exported or printed.

What makes them trustworthy:

* **Health snapshot** is read from the stored analysis, including a `coverage_note` that compares the
  analysed record count with what is stored now.
* **Strategic pillars** are the roadmap milestones when a plan exists (the strategy actually being
  executed); without a roadmap they are derived from the highest-impact pain points and
  highest-demand clusters.
* **Risks** are the plan's own weak points — a stale analysis, every initiative committed with no
  buffer, no PRD behind the backlog, a milestone resting on thin evidence.
* **AI usage** is limited to prose: headline, executive summary and pillar wording. Pillar names,
  scope, linked items and every figure stay computed.

### 5.3 Output quality evaluation

`GET /api/quality/{workspace_id}/evaluate` scores six artefact families — insights, prioritization,
roadmap, PRD, user stories, reports — against checks that are verifiable from the workspace itself.

| Category | What it verifies |
| :--- | :--- |
| Completeness | Required sections exist and are populated |
| Grounding | Every pain point rests on more than one report; documents carry a provenance block; PRD baselines/targets are labelled; **numeric claims trace back to measured values** |
| Freshness | The analysis covers every stored record |
| Consistency | Distributions add up to the analysed total; capacity respected; milestone membership consistent; report matches the current roadmap; **no two roadmap items plan the same work** |

The evaluator is deterministic and never calls a model, so it cannot flatter a generation. Scoring is
the mean of pass (100), warn (60) and fail (0), graded `excellent ≥ 90`, `good ≥ 75`, `fair ≥ 60`,
otherwise `needs_review`.

**Traceability scan.** `_collect_measured_numbers` builds the vocabulary of numbers the workspace has
actually measured (analysis, backlog scores, roadmap, documents). `_scan_untraceable_numbers` then
flags numeric claims in generated prose that no measured value supports — allowing small ordinals and
±0.5 rounding. It is the mechanical answer to "did the model invent a number?"

**Duplicate-scope scan.** Two initiatives that describe the same subject with different framing verbs
(*"Resolve: Removal of What's New Tab"* vs *"Reintroduce What's New Tab"*) are flagged, because a
milestone would otherwise credit itself twice for one piece of work.

### 5.4 Outcome tracking — what changed between two imports

Everything above argues about what should be built. This closes the loop and asks what happened after it
started shipping: between the two times a workspace collected customer feedback, did the signal move?

- **Compared unit:** one import. Every record already carries `imported_via`, the import log it arrived in,
  so the time axis exists without anyone remembering a release date or editing a CSV. Importing the same
  product's feedback again later is what creates a comparison.
- **Topic axis mined once** from both imports together, then each record is assigned to exactly one topic by
  its most specific mined phrase. This replaced a first attempt that OR-matched each topic's phrase list —
  which counted every record in every topic whose list contained a common word (`review`, from the title
  column), the defect the count invariant now guards: the topic counts always add up to the collection.
- **Rates, not counts:** mentions per 100 records in each import, since the later collection is rarely the
  same size and raw counts would report a larger import as a rise in everything.
- **Stated thresholds:** a movement is claimed only above 5 mentions on both sides and 0.05 per 100
  records, or 10% of the earlier value — whichever is larger. Below that: steady. Below the mention floor:
  insufficient evidence. The rate base (100) travels in the payload as `method.rate_base`, so a figure and
  its unit cannot drift apart.
- **Comparability caveats, not buried:** imports an order of magnitude apart in size, or dominated by
  different sources, are flagged as indicative rather than precise.

**Verified end to end against the running API** (two 100-record imports into one workspace):

```
Complaint volume fell 75.0% (40.0 → 10.0 problem mentions per 100 records).
Average rating is up 1.3 (3.4 → 4.7).

Playlist Screen        bug report   40 → 10   Falling   Fell 75.0% (40.0 → 10.0 per 100)
Unclassified mentions  general      60 → 90   Rising    Rose 50.0% (60.0 → 90.0 per 100)
```

**Verified against the real `spotify` workspace** (10,000 records from 2026-09-29 versus 100 from
2026-10-05): complaint mentions 3.96 → 24.0 per 100 and rating 3.8 → 3.25, with the response itself
reporting that the two imports differ greatly in size and are dominated by different sources (`survey`
then `Apple App Store`) — so the movement is indicative, not a like-for-like product change. Confidence
was reported as `low`. The caveats are the feature: a smaller or differently sourced second collection
does not silently masquerade as an outcome.

## 6. Verified Results

All figures below were produced by the running system against the `spotify` workspace (10,000 analysed
records, health score 77.7), not hand-written.

**Roadmap** (`horizon_weeks=12`, `velocity=8`, generated by `Google Gemini (gemini-3.6-flash)`):

| Release | Horizon | Window | Items | Effort |
| :--- | :--- | :--- | :--- | :--- |
| Release 1 · Q4 2026 | now | 2026-10-07 → 2026-11-03 | 3 | 7.0 / 8.0 |
| Release 2 · Q4 2026 | next | 2026-11-04 → 2026-12-01 | 3 | 7.0 / 8.0 |
| Release 3 · Q4 2026 | later | 2026-12-02 → 2026-12-29 | 3 | 8.0 / 8.0 |

Milestones: *Core Stability and Ad Controls* (high evidence, 3,609 records), *Playlist Management and
Account Recovery* (high, 1,142), *Offline Listening and Content Discovery* (medium, 204). Must-have
coverage: **7 of 7 scheduled**; backlog beyond the horizon: 0; customer records behind planned work:
**4,955**.

**Reschedule check:** moving an item into Release 1 recomputed that window to 4 items / 10.0 effort
(rendered as *Over capacity*), rebuilt the affected milestone deterministically, preserved the
untouched milestones' AI narratives, and re-derived must-have coverage.

**Report** (`product_strategy`, Q4 2026, written by `Groq (openai/gpt-oss-20b)`): 7 key findings,
3 pillars drawn from the roadmap milestones, 3 roadmap windows, 5 KPIs, 2 risks, 5 recommendations,
7,377 characters of Markdown.

**Output quality** (six families evaluated):

| Artefact | Score | Passed | Warned | Failed |
| :--- | :--- | :--- | :--- | :--- |
| Product insights analysis | 92 | 4 | 1 | 0 |
| Prioritization backlog | 90 | 3 | 1 | 0 |
| Roadmap plan | 93 | 5 | 1 | 0 |
| Product Requirement Document | 100 | 4 | 0 | 0 |
| User stories | 100 | 4 | 0 | 0 |
| Executive / strategy report | 100 | 4 | 0 | 0 |
| **Overall** | **96** | **24** | **3** | **0** |

The three warnings are the evaluator doing its job on real data:

1. `insights.freshness.record_count` — 10,100 records are stored but 10,000 were analysed; 100 rows
   were imported after the last analysis and are absent from every figure quoted from it.
2. `prioritization.grounding.placeholder_inputs` — 9 of 9 items still carry neutral 50 feasibility and
   risk scores, so their weighted score is not yet decision-grade.
3. `roadmap.consistency.duplicate_scope` — two initiatives describe the same subject (removal vs
   reintroduction of the same tab), which would double-count one piece of work.

## 7. Testing

| Suite | Tests | Scope |
| :--- | :--- | :--- |
| `test_milestone1.py` | 5 | Auth, workspace, import, clean, categorise |
| `test_milestone2.py` | 10 | Theme/pain-point mining, clustering, trends, AI fallback |
| `test_milestone3.py` | 7 | PRD schema/Markdown, stories, RICE, weighted scoring, copilot fallback |
| `test_milestone3_integration.py` | 2 | Service pipelines end to end (calls live providers) |
| `test_10k_benchmark.py` | — | 10k-record ingestion and analysis benchmark |
| `test_milestone4.py` | **29** | Sequencing, packing, milestones, reports, quality checks, routing, auth |
| `test_outcome.py` | **35** | Batch grouping, per-100 normalisation, thresholds, count invariant, caveats, Markdown, routing, auth |

Milestone 4 tests avoid both the network and the demo data files: fixtures drive the services with
persistence replaced by `AsyncMock`, so ordering, capacity, spill-to-backlog, determinism, report
sections and every quality check are asserted without writing to `backend/.demo_data/`.

```bash
cd backend
./.venv/Scripts/python.exe -m unittest discover -s tests -p "test_milestone4.py"
# Ran 29 tests ... OK
```

Two defects were found by the suite and the live run before they reached a demo:

* **Sequencing precedence** — the first `_order_key` put fix-work precedence as the primary key, so a
  low-scoring defect outranked a high-scoring feature. Now fix work only breaks ties (test
  `test_plan_sequences_items_and_builds_milestones`).
* **Storage key written back** — rescheduling read the stored roadmap (with `_id` serialised to a
  string) and wrote it back, which MongoDB rejects as an immutable-field change. Plans are now
  persisted without the storage key (`_persist_plan`), covered by
  `test_persisting_an_evaluated_plan_strips_the_storage_id`.

## 8. Known Limitations

* Analysis is a point-in-time snapshot. Records imported after it are invisible until the analysis is
  re-run; the report and the evaluator both surface this rather than hiding it.
* Feasibility and risk inputs to the weighted framework are neutral until a person sets them, because
  they are not derivable from customer feedback. The evaluator warns until they are.
* Release windows are fixed four-week blocks; the horizon, capacity and focus are configurable, but
  arbitrary calendar shapes are not modelled.
* Free AI tiers throttle. Gemini and Mistral were intermittently unavailable during development
  (503/429); the chain degraded to Groq or the deterministic engine without user-visible failure.
* `POST /api/feedback/clean` is serial per record and takes minutes on a 10,000-row workspace.
* Quality checks are heuristic in two places: the ±0.5 numeric tolerance and the framing-verb list
  used for duplicate detection. Both report warnings for review rather than asserting correctness.
* Product **telemetry** is still not ingested. Outcome tracking measures the customer signal (mentions,
  sentiment, ratings, health) between two imports; it cannot state session, retention, conversion or
  crash-free-rate movement, because nothing in the workspace measures them. A metrics importer is the
  remaining piece of brief module 3.
* The source file's own dates are still ignored on import: a record is dated by the import it arrived in.
  Batch-to-batch comparison does not need row dates, but a continuous weekly curve would.
* `POST /api/feedback/clean` de-duplicates the whole workspace without an order, so an overlapping
  re-export can leave the older copy of a review in place and attribute it to the earlier import.

## 9. Conclusion

Milestone 4 completes the product lifecycle the brief describes. A workspace's feedback now flows
from import through analysis, prioritisation, requirements and user stories into a sequenced roadmap,
an executive report, and a quality verdict on all of it. Every step is measurable, every generated
document states its provenance, and the system degrades to deterministic engines instead of failing —
so the same demo runs on a laptop with no database, no network and no API keys.

---

## Appendix — Milestone 4 API

| Method | Path | Purpose |
| :--- | :--- | :--- |
| `POST` | `/api/roadmap/generate` | Sequence the backlog into releases and recommend milestones |
| `GET` | `/api/roadmap/{workspace_id}` | Read the stored roadmap |
| `PATCH` | `/api/roadmap/{workspace_id}/items/{item_id}` | Move an initiative to another release |
| `DELETE` | `/api/roadmap/{workspace_id}` | Delete the stored roadmap |
| `GET` | `/api/roadmap/{workspace_id}/export` | Markdown export |
| `POST` | `/api/reports/generate` | Generate an executive summary or strategy report |
| `GET` | `/api/reports/workspace/{workspace_id}` | List reports, newest first |
| `GET` | `/api/reports/{report_id}` | Read one report |
| `PUT` | `/api/reports/{report_id}` | Update editable fields |
| `DELETE` | `/api/reports/{report_id}` | Delete a report |
| `GET` | `/api/reports/{report_id}/export` | Markdown export |
| `GET` | `/api/quality/{workspace_id}/evaluate` | Evaluate every generated artefact |
| `GET` | `/api/quality/{workspace_id}/export` | Markdown export of the evaluation |

All endpoints authenticate with `Authorization: Bearer <JWT>` and verify workspace ownership before
returning anything.

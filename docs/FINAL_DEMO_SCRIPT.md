# Final Demonstration Script — PM Copilot

**Duration:** ~15 minutes · **Audience:** internship mentor / evaluation panel
**Workspace used:** `Spotify`, holding **10,100 analysed records** (health score 77.7). Signed in as
`lohith123@gmail.com` the switcher lists exactly two workspaces — `Spotify` and `swagger-auth-test`
(10 records) — so select `Spotify` and confirm the Dashboard's "Feedback items" reads **10,100**
before the audience arrives. Other accounts on this database hold look-alike workspaces (an empty
`spotify`, un-analysed `Instagram Mobile App Insights`): if the demo workspace is missing, **verify you
are on `lohith123@gmail.com`** rather than picking a similarly named entry.
**Order:** the product lifecycle, end to end — import → insight → prioritisation → documents → plan → report → quality

**Measured timings on this machine** (10,000-record workspace, taken from the running system):
import returns in **~9 s**, the analysis it queues finishes in **~26 s**, and **Re-run analysis** takes
**~24 s**. Both timings are for a *live model* answering; if the fast provider is rate limited the
chain moves to the next one and adds ~15 s rather than failing.

> Every number in the "expect" column was produced by the running system. Figures depend on the
> workspace you show; read the value off the screen rather than promising a number you did not verify
> that morning.

---

## Before the session (5 minutes)

```bash
# 1. Start the backend
cd backend
./.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000

# 2. Start the frontend (separate terminal)
cd frontend
npm run dev
```

Or double-click `start_all.bat` at the repository root.

Checks before the audience arrives:

| Check | Where | Expected |
| :--- | :--- | :--- |
| API alive | <http://127.0.0.1:8000/docs> | Swagger loads, **Authorize** padlock visible |
| UI alive | <http://localhost:5173> | Sign-in page renders |
| Sign in | `lohith123@gmail.com` / `lohith` | Dashboard loads |
| Right workspace | switcher → `Spotify` | Dashboard "Feedback items" reads **10,100** (the only other workspace has 10) |
| AI status | Insights → banner | "Keys configured for Groq, OpenRouter, Gemini and Mistral…" |
| AI is really answering | any analysis → **AI model** row | A provider name, not "Deterministic engine" |
| Roadmap exists | `/roadmap` | Plan renders (generate it if not) |
| Report exists | `/reports` | A saved report chip exists (generate it if not) |

**Generate anything you need *before* the demo.** Generation calls a live model and takes 15–25
seconds; during the demo you want to *show* results, not wait for them.

### How many rows for a live import?

The analysis is dominated by a fixed cost — the model call — not by the row count, so a smaller file
buys very little. Measured through the API, end to end:

| rows imported | import | analysis | total |
| :--- | ---: | ---: | ---: |
| 496 · `MunchMate_500_reviews.csv` | 2.2 s | 19.2 s | ~21 s |
| 1,000 | 2.6 s | 15.3 s | ~18 s |
| 2,000 | 4.8 s | 13.1 s | ~18 s |
| 10,000 · `Spotify.csv` | 8.6–9.0 s | 25.8–28.4 s | ~35 s |

Shrink the file **only if you intend to import in front of the mentor**. Below roughly 300 rows the
output thins out: the pipeline targets five themes, five pain points and five clusters and a corpus
that small cannot support them. Prefer `MunchMate_500_reviews.csv` (496 rows, 411 named customers)
for a live import — it carries customer names, so "unique customers" is a measured number rather than
"unavailable", which is the case for the review-only files.

**Rehearse the import at most once.** The free model tiers meter tokens per minute, and repeated
rehearsals exhaust them: measured live, two runs inside a minute fell back to the deterministic
engine. Leave five minutes before the real thing.

---

## The demo

### 1 · Sign in and set the scene (1 min)

Show the sign-in screen, then the Dashboard.

**Say:** "A product manager's problem is volume. This workspace holds ten thousand real customer
records from app-store reviews, surveys, support tickets and in-app feedback. Everything from here is
computed from those records — nothing is hardcoded."

**Expect:** Dashboard shows `10,000` items analysed, sentiment split, category split, and the
per-source breakdown.

### 2 · Insights — what customers are saying (2 min)

Go to **Insights**.

**Point at:** health score, themes, pain points with impact scores, feature clusters, trend line.

**Say:** "Themes and pain points are mined from the phrases customers actually wrote — the same engine
works on a music app, a bank app or an internal tool, because no product vocabulary is baked in.
Severity is a deterministic function of volume, ratings and negative share."

### 3 · Feedback and import (1 min)

Go to **Feedback**, open one record; then **Import** and show an import log.

**Say:** "Import accepts CSV or JSON, normalises column names, skips empty rows and writes an audit
row per file. And importing *is* the analysis trigger: the rows land, the pipeline is queued in the
background, and this page reports each stage as it runs — reading, categorising, themes, AI,
normalising titles, trends. Nobody has to remember to press anything, and nothing on the page waits
for the model."

If you import during the demo, expect the button to take a few seconds for a 10,000-row file and the
stage list below it to move for roughly half a minute. Import a small file (or none) if you would
rather not wait; the numbers below come from the workspace analysed beforehand.

*Do not click "Clean text" on this workspace during the demo* — it re-processes 10,000 records
serially and takes minutes.

### 4 · Prioritization — what to build next (2 min)

Go to **Prioritization**. Show the RICE table and the weighted tab.

**Expect:** 9 initiatives; the top RICE score is about `114,953` ("Resolve: Frequent App Crashes").

**Say:** "The backlog was auto-seeded from the clusters and pain points, so every item traces back to
customer evidence. RICE is *(Reach × Impact × Confidence) ÷ Effort*; feasibility and risk stay
neutral until a person sets them, because they cannot be derived from feedback — the system says so
rather than inventing a number."

### 5 · PRD Studio (1.5 min)

Go to **PRD Studio**, open the Pay Premium PRD.

**Point at:** the `Measured:` versus `Proposed:` labelling, the evidence block, the NFRs phrased as
proposals.

**Say:** "The document states its own provenance — which engine wrote it and how many records support
it — and every baseline is a measured value. Where a conventional PRD would invent an adoption
target, this one labels it a proposal."

### 6 · User Stories (1 min)

Go to **User Stories**.

**Point at:** Fibonacci points, Given/When/Then criteria, a partly filled Kanban.

### 7 · Copilot (1 min)

Go to **Copilot** and ask something the data answers, e.g. *"What are the top complaints?"*

**Expect:** ranked complaints with impact scores, tied to the stored analysis.

### 8 · Roadmap — plan the work (2.5 min) — **Milestone 4**

Go to **Roadmap**.

**Point at, in order:**

1. The **strategy paragraph** — how the plan was sequenced.
2. The **three release lanes** with their four-week windows and effort against capacity.
3. **Three milestones**, each with a name, an objective, a confidence level and an expandable detail
   panel: *exit criteria* and *success metrics*, baselines labelled `Measured:`, targets `Proposed:`.
4. The **stat row**: 9 initiatives scheduled, 0 beyond the horizon, ~4,955 customer records behind
   planned work, must-have coverage 7 of 7.
5. One item's **"Why here"** disclosure — RICE rank, weighted score, record volume, MoSCoW.

**Say:** "The order is RICE, then the workspace's weighted score, then defect work ahead of feature
work at equal value, then customer volume — so the sequence is explainable and reproducible. Items
are packed into four-week windows at a capacity the PM sets; anything that doesn't fit stays in the
backlog with its scores intact rather than disappearing. The model wrote the names and the narrative
— it cannot move an item, change a date or alter a number."

**Then move one initiative:** pick an item in a later release and change its **Move to** dropdown.

**Expect:** the lanes re-balance, the affected milestone is recomputed, and if a window is
over-committed it is labelled *Over capacity* rather than silently overloaded.

**Say:** "That's the interactive half of planning — and the recomputation is deterministic, so the
plan stays auditable."

### 9 · Reports — the executive view (2 min) — **Milestone 4**

Go to **Reports**. Open the saved strategy report (or generate one: type *Product strategy*, period
`Q4 2026`, audience *Executive leadership*).

**Point at:**

* The **headline** — one sentence with the measured health score and negative share.
* The **health snapshot** stat row.
* **Key findings** — each with its measured evidence underneath.
* **Strategic pillars** — the roadmap milestones, i.e. the strategy actually being executed.
* **Roadmap outlook** table, **indicators**, **risks**, **recommendations**.
* The **Data coverage** banner: "100 record(s) were imported after the last analysis and are not
  reflected in these figures."

**Say:** "The report is an argument made from measurements. It will not claim revenue, retention or
churn it cannot observe — and when the analysis is behind the stored feedback it says so in the
report *and* raises it as a high risk with a recommended action. That is the difference between a
generated report and a plausible-sounding one."

Show **Export** (Markdown download) and **Print / PDF**.

### 10 · Output quality evaluation — the finale (2 min) — **Milestone 4**

On the same page, click **Evaluate output quality**.

**Expect:** six artefact cards with scores and a set of pass/warn/fail checks; overall around
`96/100` with 24 checks passed, 3 warned, 0 failed.

**Read the three warnings aloud — they are the point of the feature:**

1. *Insights:* "10,100 records are stored but 10,000 were analysed, so 100 arrived after the last run."
2. *Prioritization:* "9 of 9 items still carry the neutral 50 feasibility and risk placeholders."
3. *Roadmap:* two initiatives describe the same subject (removal vs reintroduction of the same tab).

**Say:** "This is the output-quality evaluation. It never calls a model, so it cannot flatter one. It
checks that required sections exist, that distributions reconcile with the record count, that the
analysis is not older than the data, that scores have not stalled on placeholders — and it scans every
number a model wrote for a measured value behind it. The three warnings are real defects in this
workspace, found by the system rather than by me."

Click **Export evaluation** and show the Markdown.

### 11 · Close (30 s)

**Say:** "One workspace goes from raw feedback to insights, priorities, requirements, user stories, a
sequenced roadmap, an executive report and a quality verdict — and every generated artefact states
what it was built from. It runs offline on deterministic engines when the AI providers are
unavailable, which is also how it survives a venue with no internet."

---

## Questions to expect

If he asks **"does this really work, or is it a bluff?"** — do not defend it with words, offer him a
check. Three that involve him and take under a minute:

1. **Make him add up the numbers.** Insights shows the category split and the sentiment split;
   Feedback shows the total record count. On a 1,000-record workspace these were
   `845 + 100 + 39 + 16 = 1,000` categories and `696 + 60 + 244 = 1,000` sentiments, both equal to the
   count the list endpoint reported — because they are counted from the stored rows, not written by a
   model. (If the split does not tie out, something *is* wrong and the quality page will say so.)
2. **Import a file in front of him.** Every number moves with the file: 496 rows imports and the whole
   workspace totals 496. Hardcoded demo data cannot follow a file he watched arrive.
3. **Take the models away and re-run the analysis** — the run still completes and reports
   "Deterministic engine": the model is an enhancement on top of the engine, not the engine. Do it by
   blanking the AI keys in `backend/.env` and restarting the backend, **not** by unplugging the
   network: the feedback lives in a remote Atlas cluster, so losing the internet takes the data with
   it and you would prove the opposite of what you meant. Restore the keys and restart before the
   next step.

What you may claim, precisely: **measurements are computed, wording is generated.** Verified by
analysis the same 1,000 records twice: totals, category split, sentiment split, health score, trend
points and theme names were byte-identical between runs, and only the prose changed.

What you must **not** claim: that re-running gives the same *topic list*. It does not. Across those
same two runs the model named 8 pain points the first time and 3 the second (a different model
answered each), with different cluster volumes. The counts underneath each topic are measured; which
topics get named is the model's proposal. Say that if he notices, because he will.

| Question | Answer |
| :--- | :--- |
| Is this real data? | Yes — `Spotify` holds 10,100 imported records with their ratings, sources and dates. Nothing on screen is typed in: every figure is read back out of the database. |
| Does the AI hallucinate? | It can only write narrative. Numbers, ordering, dates and scores are computed in Python; the quality evaluator scans generated prose for untraceable numbers and reports them. |
| What if the internet dies during this? | Two different outages. If a *model provider* is down or rate limited, every AI call falls back: Groq → OpenRouter → Gemini → Mistral, each with its own time slice, then the deterministic engine — the feature still returns a complete result and records which engine produced it (`Groq (openai/gpt-oss-20b)` or `Deterministic engine`). If the *venue's* internet is down, the feedback itself is unreachable: this build stores its records in a remote Atlas cluster, so the app needs the network for the data, not just for the models. |
| How do you know the outputs are any good? | That is the quality evaluation on this page: 32 checks across six artefact families, each verifiable from the workspace itself. It never calls a model, so it cannot flatter one — and it reports the defects it finds, including its own placeholder scores. |
| Can I see the evidence without the UI? | Yes: `backend/tools/_engine_audit.py <workspace_id>` re-runs the engines over the stored records and prints what the stored analysis got right or wrong, and `backend/tests/` holds 124 tests including the accuracy suite. |
| Why is the roadmap order like that? | RICE descending, then weighted score, then defect work at equal value, then record volume — shown per item under "Why here". |
| Why 96 and not 100? | Because three real defects exist in this workspace and the evaluator reports them. A perfect score would mean it checks nothing. |

## Do not click during the demo

* **Clean text** on a 10,000-row workspace — serial per record, takes minutes.
* **Run agent crew** — it re-runs the analysis through the agent path.
* Creating or deleting workspaces.

**Re-run analysis** is safe to press and takes ~24 s. Press it early (step 2) so it has finished by
the time you reach the pages that read it, or press it and keep talking — the button reports
"Analysing…" and the Dashboard's "✓ Done".

## Recovery plans

| If this happens | Do this |
| :--- | :--- |
| Generation is slow (> 30 s) | Talk through the stored plan/report you generated earlier; generation already happened. |
| A provider returns an error | Nothing visible happens — the chain falls through silently. If an artefact is attributed to a deterministic engine, say: "this is the offline path; the numbers are identical." |
| An analysis reports "Deterministic engine" | The free tiers meter tokens per minute, so back-to-back analyses can exhaust them. Say "the deterministic engine produced this — same numbers, no model", and press **Re-run analysis** a minute later to show the AI path. |
| A page is empty | Check the workspace switcher: every page follows the selected workspace, and on `lohith123@gmail.com` only `Spotify` holds 10,100 items. If you are signed in as another account, its workspaces are look-alikes — sign back in as `lohith123@gmail.com`. |
| Roadmap 404s | The workspace has not been planned — click **Generate plan**. |
| Backend unreachable | Restart with the command at the top; the frontend proxies to port 8000. |

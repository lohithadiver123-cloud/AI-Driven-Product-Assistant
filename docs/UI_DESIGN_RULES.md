# PM Copilot — UI design rules

This document exists because the interface is complete, consistent, and tiring to look at. Every
screen was assembled from the same parts — page header, action buttons, a row of stat cards, one
big content card, a table — so every screen speaks at the same volume, and nothing on any of them
says *look here first*.

The fix is not a redesign. Nothing is restyled, no palette changes, and no evidence is deleted.
The fix is **hierarchy**: one answer per page, and everything that explains *how* the answer was
produced moves one click away instead of sitting on the surface.

This is a plan. It is written so each rule can be checked mechanically, and so a future pass —
human or agent — can pick up any single page and apply it without re-deriving the argument.

---

## 1. What we measured

Live app, `spotify` workspace, desktop viewport, 2026-10-10. Words in the rendered `<main>`:

| Page | Words | What fills them |
| :--- | ---: | :--- |
| Insights | 1,615 | AI summary prose, severity breakdown, per-cluster explanation, tab content |
| Reports | 1,168 | Findings, pillars, risks, recommendations, evidence block, quality checks |
| Prioritization | 1,015 | Four frameworks' worth of formula hints and leaderboard context |
| Roadmap | 825 | Planning inputs, per-release hints, per-item rationale |
| Outcomes | 595 | Summary, topic table sentences, methodology list, caveats |
| Feedback | 495 | Table of records — mostly data, and the least tiring page by feel |
| Dashboard | 301 | Two charts and three stats — the lightest page in the app |

Across the codebase: **11 flat navigation links**, **33 `<Stat>` instances**, **51 `hint=`
strings**, **16 page/modal descriptions**, and exactly **one collapsed content region** in the
whole UI (a `<details>` in RoadmapPlanner). Nothing anywhere starts collapsed.

Reproduce a page's count with this in the browser console:

```js
document.querySelector('main').innerText.trim().split(/\s+/).length;
```

Two of those pages carry their length honestly — the methodology on Outcomes and the evidence
block in Reports are there so a reader can check the numbers rather than trust them. That intent
survives this plan intact. What changes is *where* it sits.

---

## 2. The principle

> **A page is one answer, plus its evidence.**

Three tiers, in order of how far the reader has to reach:

1. **On the surface** — the answer to the page's question, and the controls that change it.
2. **One click away** — everything describing *how* the answer was produced: method, thresholds,
   caveats, provenance, formulas.
3. **Never deleted** — evidence stays in the API payload and in every Markdown export. Demoted,
   not removed. A reader who wants to audit the number still can, and the export still says
   everything the page used to say.

The tiers are ordered by reach, not by importance. Tier 2 is the part this product is *for* — the
deterministic engines and their stated limits are the product. It just does not need to be the
first thing on every screen.

---

## 3. The rules

Each rule is written to be checkable without interpretation.

**R1 — One question per page.** Every page answers exactly one question, named in a comment at the
top of its file. `PageHeader` descriptions stay at or under 14 words and state what the page
answers, never what the page contains.

**R2 — The answer comes first.** Above the fold: the answer, then the controls. At most **three**
`<Stat>` cards, one marked `featured`. A row that fills fewer than three cells is a defect —
delete a stat or merge two. Six stats (Roadmap today) always means three of them are not the
answer.

**R3 — Explanation collapses.** Anything that says *how* or *why* rather than *what* renders
inside a `<Disclosure>`, closed by default. `Section` and `CardHeader` hints over **12 words**
move into the disclosure they explain; the hint slot then carries at most a short pointer or
nothing.

**R4 — Verdict first, sentence second.** Tables show the judgement as a badge plus the numbers.
The full-sentence reading currently repeated on every row (`Rose 821.1% (0.76 → 7.0 per 100
records).`) belongs in the expanded row, not in the cell. A table of nine rows should not contain
nine paragraphs.

**R5 — Two levels of nesting, never three.** Page → card → content. The pattern now common on
Roadmap and Prioritization — toolbar card → stat cards → tabs → card → table — puts four bordered
boxes between the reader and the data. Merge or flatten.

**R6 — One primary action per page.** Exactly one visible `variant="primary"` button; everything
else is `secondary` or `ghost`. Headers mostly hold to this already (Dashboard's header has one,
plus more inside its create form and empty state), which is the point of writing it down: the
limit has been kept by habit, not by rule, and it drifts the moment a second action wants the
click.

**R7 — Navigation is a sequence, not a list.** The eleven links are the pipeline in order. Group
them by stage and keep that order:

| Stage | Destinations |
| :--- | :--- |
| Understand | Dashboard · Insights · Feedback · Import |
| Plan | PRD Studio · User Stories · Prioritization · Roadmap |
| Measure | Outcomes · Reports |
| Ask | Copilot |

Copilot stays reachable from everywhere; it is already a floating button.

**R8 — Never restate what the data already says.** If a sentence's only job is to repeat a number
visible two lines above it, delete the sentence. Prose earns its place by interpreting, comparing
or qualifying.

---

## 4. The one component this needs

A `<Disclosure>` in the UI kit — a summary row that opens a region, styled once, used everywhere:

```jsx
<Disclosure summary="How this was measured" meta="5 points">
  …the full methodology list, unchanged…
</Disclosure>
```

Built on native `<details>` so keyboard and screen-reader behaviour is free, styled in
`index.css`, exported from `components/ui/index.js`. RoadmapPlanner's inline `<details>` migrates
to it; nothing else changes shape. This is the only new primitive the whole plan requires.

---

## 5. Per-page plan

"One question" is what the page comment will say. "Visible" is the word budget for the default
state — the surface, before any disclosure is opened.

| Page | One question | Moves into disclosures | Visible budget |
| :--- | :--- | :--- | ---: |
| Dashboard | Is the pipeline healthy? | Nothing — already the model page | ~300 (keep) |
| Feedback | What did people say? | Nothing — data, not prose | ~500 (keep) |
| Insights | What is hurting users most? | AI summary body, severity breakdown, per-cluster prose | 1,615 → ~550 |
| Reports | What does the evidence say to do? | Evidence & method, quality checks, risk mitigations | 1,168 → ~450 |
| Prioritization | What should we build first? | Formula hints, weighted-scoring context | 1,015 → ~450 |
| Roadmap | What ships when, and why? | Planning inputs (after first run), per-item rationale | 825 → ~400 |
| Outcomes | Did anything change? | Methodology list, caveats, per-row readings | 595 → ~250 |
| PRD Studio | What are we building? | Generation hints only | trim descriptions |
| User Stories | What do we build this sprint? | Generation hints only | trim descriptions |
| Copilot | What does the evidence say when I ask? | Nothing — the chat is the surface | keep |

Caveats and methodology are never removed — they move. The Outcomes export still contains the
full threshold list and both caveat alerts; the page simply stops leading with them.

---

## 6. What this plan does not do

- No restyle, no new palette, no typography pass, no motion work.
- No methodology, threshold or caveat is deleted from any page or any export.
- No page loses a control. Filters move; they do not disappear.
- No new state is invented for the reader. Every disclosure is one click and remembers nothing.

---

## 7. Order of work

1. `<Disclosure>` component and its CSS.
2. **Outcomes** — smallest page, most concentrated text, and the one whose honesty rules matter
   most. Apply R2–R4 here, review, then continue.
3. **Insights** and **Reports** — the two worst offenders by word count.
4. **Roadmap** and **Prioritization** — the nesting fixes (R5) land here.
5. **Navigation grouping** (R7), last, because it touches every page's mental model at once.
6. README screenshots and copy refreshed to match.

**Done** means: every page passes its visible-word budget from §5, its file comment names the one
question, it has at most three stats and one primary action, and the measurement snippet in §1
reproduces the numbers. A page that cannot meet its budget is a page with two questions — split
it, do not stretch the budget.

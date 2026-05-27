# Careerbot data schema

This document is the contract between the markdown files in this repo and any consumer that reads them — including future SQLite import.

There are three entities: **Applications**, **Companies**, **Answer Bank**. Each one is a folder; each row is a single `.md` file with YAML frontmatter plus a markdown body. Status (or theme, for answers) is encoded in the parent folder name, not in frontmatter.

## Rules that apply to every entity

- **One file = one row.** No multi-row files.
- **Frontmatter is typed.** Strings, integers, ISO dates (`YYYY-MM-DD`), `null`, or YAML lists of strings. No nested objects, no mixed types in a list. This makes SQLite import a straight column-by-column copy.
- **The body is one TEXT column** in SQLite. It's markdown; render it however.
- **Enums are documented here.** Any value outside the declared set is a schema violation.
- **Foreign keys are slugs.** Never page IDs, never absolute paths.
- **Dates are ISO-8601 `YYYY-MM-DD`.** Bare, unquoted in YAML.
- **Booleans are `true` / `false`.** Don't use yes/no.
- **Quote any string value that contains a `:`, `#`, leading `-`/`*`/`&`/`!`/`?`/`|`/`>`/`%`/`@`/backtick, or could be read as a YAML type** (`yes`, `no`, `null`, a bare number, an ISO date). Unquoted inline `:` in particular breaks the entire dashboard's frontmatter parse: a value like `stage: public (NYSE: FSLY)` must be written `stage: "public (NYSE: FSLY)"`. When in doubt, quote.

## Folder-as-status

The SQLite importer derives the `status` (Applications, Companies) or `theme` (Answer Bank) column from the parent folder name:

| Entity | Status column derived from |
| --- | --- |
| Applications | `applications/<status>/<company>/<file>.md` → `status` |
| Companies | `companies/<status>/<file>.md` → `status` |
| Answer Bank | `answer-bank/<theme>/<file>.md` → `theme` |

Status changes are filesystem moves (`git mv`). The frontmatter never repeats this field.

---

## Applications

**Path**: `applications/<status>/<company-slug>/<ats-id>-<title-slug>.md`
**Primary key**: `(company, ats_id)`
**Foreign key**: `company` → `companies.slug`

### Status enum (folders)

`in-review`, `applied`, `interview`, `rejected`, `offered`, `archived`

### Frontmatter

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `title` | string | yes | Verbatim job title from posting |
| `company` | string (slug) | yes | FK → `companies.slug` |
| `ats_id` | string | yes | Quoted in YAML; may be alphanumeric |
| `url` | string | yes | Full canonical posting URL |
| `source` | enum | no | `greenhouse` \| `lever` \| `ashby` \| `workday` \| `careers-page` \| `other` |
| `posted_at` | date | no | ISO `YYYY-MM-DD`. Posting date as reported by the ATS (Greenhouse `updated_at`, Lever `createdAt`, Ashby `published`, Workable `published`, Workday `postedOn`). Null when the source doesn't expose one (custom HTML scrape). |
| `date_found` | date | no | **Deprecated** — still parsed for back-compat but no UI reads or writes it. Safe to omit on new applications. |
| `salary_min` | integer | no | USD; bare number, no `$` |
| `salary_max` | integer | no | USD |
| `location` | string | no | As stated in posting |
| `notes` | string | no | **Deprecated** — still parsed for back-compat but no UI reads or writes it. Safe to omit on new applications. |

### Body

- `## Job description` — verbatim JD from posting. May contain H3 subsections (About the Role, Responsibilities, etc.).
- `## Application form responses` — wrapper H2 marking the transition from JD to form questions. Required so the web UI can split the two cleanly. The wrapper itself has no body content.
- `### <question>` — one per form field under the wrapper, with answer paragraph(s) below.
- Optional `[source: answer-bank/<theme>/<slug>.md]` provenance tag at the end of an answer.

### Example

```markdown
---
title: "Senior Software Engineer, Payments"
company: stripe
ats_id: "1234567890"
url: "https://stripe.com/jobs/1234567890"
source: greenhouse
posted_at: 2026-05-08
date_found: 2026-05-10
salary_min: 180000
salary_max: 250000
location: "San Francisco, CA"
notes: ""
---

## Job description
…

## Application form responses
### Why do you want to work at Stripe?
…
[source: answer-bank/why-us/stripe-craft.md]
```

---

## Companies

**Path**: `companies/<status>/<slug>.md`
**Primary key**: `slug`

### Status enum (folders)

`in-review`, `interested`, `not-interested`

### Frontmatter

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | yes | Legal / display name |
| `slug` | string | yes | Lowercase, hyphenated; matches filename |
| `industry` | list of strings | no | Kebab-case tags, e.g. `[fintech, b2b-saas]` |
| `match_score` | integer | no | 1–10; `null` for `/add-company` entries |
| `headcount` | string | no | Free-form, e.g. `"~500"`, `"150-200"` |
| `stage` | string | no | Free-form, e.g. `"Series C"`, `"Public"` |
| `valuation` | string | no | Free-form, e.g. `"$1.5B"`, `"$95B market cap"` |
| `hq` | string | no | City, region/country |
| `offices` | list of strings | no | Other office locations |
| `remote_policy` | enum | no | `remote` \| `hybrid` \| `onsite` |
| `careers_url` | string (URL) | no | Public careers / jobs page; renders next to **Open roles** in the UI |
| `ats` | enum | no | Which ATS hosts the careers page. `greenhouse` \| `lever` \| `ashby` \| `workday` \| `smartrecruiters` \| `workable` \| `custom`. Populated by `/find-roles` backfill (`lib/backfill_ats_metadata.py`). |
| `ats_slug` | string | no | The slug on that ATS (the path segment after the host). For Workday, format is `<tenant>/wd<N>/<site>` (e.g. `adobe/wd5/external_experienced`). For all others, a single token. |
| `discovered_via` | enum | no | How this company entered the tree. `find-roles` \| `find-companies` \| `add-company` \| `manual`. Set on stub creation; never updated thereafter. |
| `researched_on` | date | no | When the dossier was written |
| `not_interested_reason` | string | no | Required iff `status = not-interested`; otherwise `null` |

### Body

Full dossiers (statuses `in-review`, `interested`) use H2 sections:

- `## Why this is a good match`
- `## What they do`
- `## Recent news`
- `## Engineering culture`
- `## Company culture & work-life balance`
- `## Stock / financial trajectory`
- `## Concerns / controversies`
- `## Open roles`
- `## Sources`

Rejected dossiers carry only 1–3 paragraphs explaining the rejection.

### Example

```markdown
---
name: "Stripe"
slug: stripe
industry: [fintech, b2b-saas]
match_score: 9
headcount: "~5000"
stage: "Series K"
valuation: "$95B"
hq: "San Francisco, CA"
offices: ["San Francisco, CA", "Dublin, IE"]
remote_policy: hybrid
careers_url: "https://stripe.com/jobs"
ats: greenhouse
ats_slug: stripe
researched_on: 2026-05-12
not_interested_reason: null
---

## Why this is a good match
…
```

---

## Answer Bank

**Path**: `answer-bank/<theme>/<slug>.md`
**Primary key**: `(theme, slug)`
**Foreign key**: `variant_of` → another `(theme, slug)` in this same table

The Answer Bank holds **portable raw material about the user** — facts, beliefs, stories, skills — that the AI uses to synthesize finished application prose. Entries here should NEVER be company-specific or role-specific. They're inputs to generation, not finished answers.

### Theme enum (folders)

`identity`, `beliefs`, `stories`, `career`, `skills`, `voice`

| Theme | What it holds | Typical count |
| --- | --- | --- |
| `identity` | Hard facts: legal name, contact, links, work auth, visa, location, start date, relocation openness, salary floor, demographic | 15–20 |
| `beliefs` | Stable views about how you work, what you value, what good/bad looks like. Written in your voice, not tied to a specific company. | 10–15 |
| `stories` | Specific S-A-O anecdotes from your work history, tagged by what they illustrate (leadership, conflict, 0-to-1, scale, ambiguity, etc.) | 8–12 |
| `career` | Past role annotations (why joined / shipped / learned / left), what you want next, where you're heading, companies you admire | 5–10 |
| `skills` | Technical stack with comfort levels, tools you reach for, languages spoken, public artifacts (writing, talks, OSS) | 10–20 |
| `voice` | Writing samples for the AI to mimic tone, phrases you use, phrases you avoid | 3–5 |

### Frontmatter

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `question` | string | yes | Representative phrasing or short title of what this entry is |
| `tags` | list of strings | no | Kebab-case; especially important for `stories` (e.g. `[leadership, 0-to-1, design-systems]`) |
| `variant_of` | string | no | `<theme>/<slug>` of the canonical entry, or `null` |

### Body

The entire markdown body is the entry content. For `stories`, recommended structure:

```
**Situation:** what was happening, the context.
**Action:** what you did, the call you made.
**Outcome:** what happened, what you learned, what you'd do differently.
```

For other themes, freeform prose in your own voice. Keep entries focused on one idea per file.

### Example — beliefs

```markdown
---
question: "How I think about AI in products I use daily"
tags: [ai-trust, design-systems]
variant_of: null
---

I treat AI features like a junior teammate with great recall and shaky judgment. Two design rules I keep returning to: the user has to see what the agent intends *before* it acts on shared state, and any action the agent takes has to be reversible without a support ticket…
```

### Example — story

```markdown
---
question: "Thunderbolt design-system handoff to engineering"
tags: [design-systems, ai-trust, founder, 0-to-1]
variant_of: null
---

**Situation:** First product designer on Mozilla Thunderbolt. The Figma file and the Tailwind code were drifting weekly…
**Action:** Mapped every Figma token 1:1 to a Tailwind config key…
**Outcome:** Engineers stopped pinging me to verify hex codes. Shipping cadence on UI tickets ~2x'd…
```

### Stubs

A **stub** is an answer-bank file with frontmatter set (`question`, `tags`, `variant_of`) but an **empty body**. Stubs are how the system records "we know we need an answer to this question, the user just hasn't given one yet."

**Stubs are created exclusively by `/find-roles`** (and only `/find-roles`) when it walks the input checklist below for an essay it's trying to draft and finds a gap. The skill writes a generic, portable, reusable question (never company- or role-specific) so the same answer unblocks every future essay that needs the same input. There is no starter pack or pre-seeded question list — the entire question set is generated lazily from real application demand.

`/seed-answer-bank` walks every stub and inserts the user's answer into the body, but never creates new stubs. `/draft-missing-answers` never writes to `answer-bank/` at all — it only re-reads filled bodies and re-synthesizes essays as gaps close. Consumers (`/find-roles`, `/draft-missing-answers`) treat empty-body entries as unsatisfied inputs and skip them during synthesis.

### How AI uses each theme (fine-grained input requirements)

This is the contract `/find-roles` follows when drafting application questions. For each essay pattern, the AI walks an **input checklist**. Each line is one required input — typically an answer-bank entry matched by theme + tag, but sometimes the company dossier or a `context/` file.

An input is **satisfied** when a matching `answer-bank/<theme>/*.md` file exists and has a **non-empty body**. A file with frontmatter set but empty body is a **stub** (see above) and counts as an unsatisfied input.

When a checklist surfaces a gap with no matching stub, `/find-roles` generates one and writes it to `answer-bank/<theme>/<slug>.md` for the user to fill later.

| Essay question pattern | Input checklist |
|---|---|
| **"Why us?" / "Why <company>?"** | `beliefs` tagged `mission-fit`; `beliefs` tagged `culture-fit`; `beliefs` tagged `ethics-line`; `career` tagged `companies-admired`; `career` tagged `what-i-want-next`; company dossier at `companies/interested/<slug>.md` |
| **"Why this role?" / "Why are you a good fit?"** | `career` tagged `what-i-want-next`; ≥1 `skills` entry whose body intersects the JD's "Requirements"; ≥1 `stories` entry whose tags intersect the JD's domain |
| **"Tell us about a challenging project" / "Greatest accomplishment"** | ≥1 `stories` entry tagged `ambiguity`, `0-to-1`, `scale`, or `technical-depth` |
| **"Conflict / disagreement"** | `beliefs` tagged `disagreement`; ≥1 `stories` entry tagged `conflict` |
| **"Leadership / mentoring example"** | `beliefs` tagged `collaboration`; ≥1 `stories` entry tagged `leadership` |
| **"Walk us through your design process"** | `beliefs` tagged `good-design`; `beliefs` tagged `handling-ambiguity`; ≥1 `stories` entry tagged `design-systems` or `0-to-1` |
| **"Experience with AI / AI tools"** | `beliefs` tagged `ai-in-products`; ≥1 `stories` entry tagged `ai-trust`; `skills` entry tagged `daily-tools` |
| **"Strengths / what sets you apart"** | `skills` tagged `soft-skills`; ≥1 `stories` entry; `beliefs` tagged `good-design` OR `mission-fit` |
| **"Anything else / cover letter"** | `beliefs` tagged `mission-fit` OR `culture-fit`; ≥1 `stories` entry; company dossier |
| **Personal info / logistics fields** | `identity` entry whose `question` matches the form field (verbatim — no synthesis, no stub generation) |

`voice` entries are not in any checklist because they're sampled universally — every essay draws on them for tone and phrasing, regardless of pattern.

---

## Schema invariants

A `/migrate-from-notion` reconciliation report or any future validator should check:

1. Every required field is present and non-null.
2. Every enum field's value is in the declared set.
3. Every date parses as ISO `YYYY-MM-DD`.
4. Every `applications/*/company` resolves to an existing `companies/**/<slug>.md`.
5. Every `answer-bank/*/variant_of` resolves to an existing answer file.
6. `(company, ats_id)` is unique across all `applications/`.
7. `slug` is unique across all `companies/` (across all status folders).
8. `(theme, slug)` is unique across all `answer-bank/`.
9. For Companies with `status = not-interested`, `not_interested_reason` is non-null.

---

## Mapping to SQLite (future)

```sql
CREATE TABLE companies (
  slug TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('in-review','interested','not-interested')),
  name TEXT NOT NULL,
  industry TEXT,             -- JSON array
  match_score INTEGER,
  headcount TEXT,
  stage TEXT,
  valuation TEXT,
  hq TEXT,
  offices TEXT,              -- JSON array
  remote_policy TEXT CHECK (remote_policy IN ('remote','hybrid','onsite')),
  careers_url TEXT,
  ats TEXT CHECK (ats IN ('greenhouse','lever','ashby','workday','smartrecruiters','workable','custom')),
  ats_slug TEXT,
  discovered_via TEXT CHECK (discovered_via IN ('find-roles','find-companies','add-company','manual')),
  researched_on DATE,
  not_interested_reason TEXT,
  body TEXT
);

CREATE TABLE applications (
  company TEXT NOT NULL REFERENCES companies(slug),
  ats_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('in-review','applied','interview','rejected','offered','archived')),
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  source TEXT CHECK (source IN ('greenhouse','lever','ashby','workday','careers-page','other')),
  posted_at DATE,
  date_found DATE,
  salary_min INTEGER,
  salary_max INTEGER,
  location TEXT,
  notes TEXT,
  body TEXT,
  PRIMARY KEY (company, ats_id)
);

CREATE TABLE answer_bank (
  theme TEXT NOT NULL CHECK (theme IN ('identity','beliefs','stories','career','skills','voice')),
  slug TEXT NOT NULL,
  question TEXT NOT NULL,
  tags TEXT,                 -- JSON array
  variant_of TEXT,           -- "<theme>/<slug>" pair, nullable
  body TEXT,                 -- the entry content
  PRIMARY KEY (theme, slug)
);
```

The importer walks each top-level folder, parses every `.md` with a YAML frontmatter parser, treats the parent folder name as the status/theme column, and inserts one row per file. Lists in YAML serialize to JSON arrays. Body content goes in the `body` TEXT column.

---
name: add-application
description: Add a single application by URL. The user pastes one job posting link; the skill fetches the JD, drafts answers from the Answer Bank, and writes one markdown file at applications/in-review/<company>/<ats-id>-<title-slug>.md so it surfaces immediately on the dashboard's Applications page. Auto-adds the company at companies/interested/<slug>.md if it isn't tracked yet. Refuses to duplicate an existing application. Single-target counterpart to /find-roles. Use whenever the user pastes a job URL, says "add this application", "track this job", "draft an application for this", or otherwise names one specific posting they want drafted.
---

# Add Application

Draft one application from one URL the user already knows they want to apply to. Minimal input, AI-filled metadata + answers, one markdown file at `applications/in-review/<company>/<ats-id>-<title-slug>.md`.

This skill is **single-target**, one URL per run. For batch discovery across every company in `companies/interested/`, use `/find-roles` instead.

The full schema is in `SCHEMA.md` at the repo root.

## Prerequisites

The `applications/`, `companies/`, and `answer-bank/` folders exist. `SCHEMA.md` exists at the repo root. `context/preferences.md`, `context/index.md`, and `context/resume.pdf` exist.

If `context/preferences.md` or `context/index.md` is missing, stop and tell the user to run `/onboard` first.

## Workflow

### 1. Resolve inputs

Pull the URL from the user's message. If they pasted multiple URLs, ask which one (one URL per run is the hard rule). If they pasted text without a URL, ask for the canonical job posting link.

### 2. Detect the ATS source

Inspect the URL host/path to pick a value for the `source` frontmatter field. The accepted enum lives in `web/src/lib/types.ts` (`ApplicationSource`):

| Host pattern | `source` |
|---|---|
| `boards.greenhouse.io`, `*.greenhouse.io` | `greenhouse` |
| `jobs.lever.co` | `lever` |
| `jobs.ashbyhq.com`, `*.ashbyhq.com` | `ashby` |
| `*.myworkdayjobs.com`, `workday.com` | `workday` |
| company's own careers site | `careers-page` |
| anything else | `other` |

Extract the **ATS ID** from the canonical URL path:

- Greenhouse: numeric segment, e.g. `boards.greenhouse.io/anthropic/jobs/4567890123` → `"4567890123"`.
- Lever: the trailing slug, e.g. `jobs.lever.co/figma/abc-123-def` → `"abc-123-def"`.
- Ashby: the UUID-ish trailing segment.
- Workday: the `R-<digits>` job code if present; else the slug segment after `/job/`.
- Careers page / other: derive the most stable identifier the URL exposes. If nothing usable exists, fall back to a slugified version of the job title (less ideal because re-postings won't dedup).

Quote `ats_id` in the frontmatter (YAML safety, since IDs can be alphanumeric).

### 3. Identify the company and ensure it's tracked

Infer the company from the URL host (the path segment for greenhouse/lever/ashby; the apex domain for `careers-page`) and from the JD's "About the company" section once you fetch it. Derive the slug per the convention in `.agents/skills/add-company/SKILL.md` (lowercase, hyphenated, alphanumeric).

Check whether the company is already on file:

```bash
ls companies/in-review/<slug>.md companies/interested/<slug>.md companies/not-interested/<slug>.md 2>/dev/null
grep -rl --include='*.md' "^slug: <slug>$" companies/
```

- **Already in `interested/`** — use this slug; proceed.
- **In `in-review/` or `not-interested/`** — use this slug; proceed (the application doesn't change the company's status, that's the user's call).
- **Not on file anywhere** — run the **add-company sub-workflow** inline (`.agents/skills/add-company/SKILL.md` steps 3-4):
  1. Use WebFetch / WebSearch / training to fill three fields: `hq` (string or null), `industry` (1-3 kebab-case tags or empty), `remote_policy` (`remote` | `hybrid` | `onsite` or null).
  2. Write `companies/interested/<slug>.md` per the Companies frontmatter in `SCHEMA.md`. Body is empty. The user can run `/find-companies` later for a full research pass.
  3. Note in the final report that the company was auto-added.

### 4. Dedup against existing applications

Hard gate, before any drafting work. The primary key on the Applications table is `(company, ats_id)` per `SCHEMA.md`.

```bash
ls applications/*/<company-slug>/*.md 2>/dev/null
```

For each existing file, grep the `ats_id:` and `url:` lines from the frontmatter. If either matches the current posting:

- **Refuse.** Print the existing file path and its current status (= the parent status folder).
- Do NOT overwrite. If the user explicitly asks to "re-draft", proceed only after they confirm; even then, never wipe their manual edits silently.

This dedup applies across **all seven status folders** (`in-review`, `applied`, `interview`, `rejected`, `offered`, `withdrawn`, `not-interested`). A posting the user already withdrew from or was rejected from is still "on file" and must not be re-drafted.

### 5. Fetch the JD

Use WebFetch on the canonical posting URL. Use this exact prompt:

> Return the COMPLETE job description verbatim, preserving section headings and lists. Do not summarize.

Capture everything per `.agents/skills/find-roles/SKILL.md` step 4: the role overview, "About the team", full Responsibilities list, full Requirements list (including bonus / nice-to-haves), comp / equity / benefits as written, location and work-arrangement details, interview process if mentioned, perks, EEO note. Drop only nav chrome, footer links, "Apply now" labels, and pure visual elements.

Also extract:
- Canonical job title (verbatim from the posting).
- Salary range if disclosed (parse into `salary_min` / `salary_max` integers, USD, no `$`).
- Location string as stated in the posting.
- Posting date if the ATS exposes one (Greenhouse `updated_at`, Lever `createdAt`, Ashby `published`, Workable `published`, Workday `postedOn`) → `posted_at` as ISO `YYYY-MM-DD`. Use `null` if the source doesn't expose one (custom HTML page).

**Fetch fallback.** If the fetch returns empty, a login wall, JS-only chrome, or otherwise unusable content (common for Workday and some Greenhouse embeds), do NOT bail. Tell the user:

> Couldn't fetch the JD from <url> (looks like <reason: JS-rendered / login wall / etc.>). Paste the JD body here and I'll use what you paste.

Then proceed with whatever they paste. Drafted answers' quality depends on the JD content, so getting it from the user is far better than skipping.

### 6. Enumerate the application form's questions

Same logic as `.agents/skills/find-roles/SKILL.md` step 4 (the "application form's questions" sub-list). Walk for:

- **Personal info**: legal name, preferred name, name pronunciation, pronouns, phone, email, current city/state, country, work authorization, visa sponsorship.
- **Professional links**: LinkedIn, GitHub, portfolio, X/Twitter.
- **Essay / free-text**: cover letter, "why this company", "why this role", "tell us about a project", "design process", etc.
- **Logistics**: earliest start date, relocation openness, referrals, prior compensation.
- **Demographic**: pronouns, gender, ethnicity, veteran status (always TODO, user fills in directly).

If the application form is gated (behind login) and you can't enumerate fields, draft only the cover letter and a standard "Why this role?" / "Why this company?" pair, and note the gap in the final report. Do not fabricate form questions.

### 7. Load the Answer Bank

Six themes under `answer-bank/<theme>/`: `identity`, `beliefs`, `stories`, `career`, `skills`, `voice`. Build the same `filled` + `stubs` structures `/find-roles` uses in its step 5:

- `identity_lookup` (filled entries by question, case-insensitive), `identity_stubs` (empty-body entries).
- `beliefs`, `stories`, `career`, `skills`, `voice` and their `*_stubs` lists.

Stubs are answer-bank files with frontmatter but empty body. Treat them as **unsatisfied** for synthesis purposes.

### 8. Classify and synthesize each form question

Direct reuse of `.agents/skills/find-roles/SKILL.md` steps 6-8. Summary:

- **Identity questions** — match the form field (case-insensitive, fuzzy) against the form-field → identity-question mapping. Matched + filled → paste body **verbatim**, no provenance tag (identity is data, not synthesis). Matched + stub → `TODO: fill in answer-bank/identity/<slug>.md`. Unmatched → generate a stub at `answer-bank/identity/<slug>.md` with the form field's label as `question:`, then write the same TODO.
- **Essay questions** — classify against the essay-pattern table in `SCHEMA.md` ("How AI uses each theme"). Walk the input checklist for that pattern. Mark each input **satisfied** (filled answer-bank entry exists), **pending** (stub exists from a prior run), or **just-stubbed** (gap, freshly stubbed this run). Then:
  - All inputs satisfied → full synthesis. End with `[synthesized from: answer-bank/<theme>/<slug>, ..., companies/interested/<slug>.md]`.
  - Some satisfied → partial synthesis using only the satisfied inputs. End with `[partial - pending: answer-bank/<theme>/<slug>, ...]` listing the unsatisfied paths. Do NOT include a `[synthesized from: ...]` tag in this case.
  - All unsatisfied → TODO block, one bullet per missing input, each citing the corresponding `answer-bank/<theme>/<slug>.md` path. Do not fabricate.
- **Demographic questions** — emit `### <question>` with body `TODO: user fills in directly`. Never draft demographic answers. Never stub them.

**Stub generation is allowed** in this skill (same as `/find-roles`). Only `/draft-missing-answers` is the read-only counterpart that never writes new stubs.

Anchor every essay to concrete experience from `context/` (resume, projects, personal site) and to JD-specific phrasing. Same drafting guidance as `find-roles/SKILL.md` step 6d (especially the `context/index.md` one-hop link-following rule for project-naming essays) and step 8: tight cover letters, no generic "I'm passionate about" filler, no fabrication.

### 9. Write the file

Compute the filename slug: lowercase the job title, strip punctuation, replace whitespace with `-`, cap at ~60 chars. Concat with the ATS ID: `<ats-id>-<title-slug>.md`.

Write to `applications/in-review/<company-slug>/<ats-id>-<title-slug>.md` (create the company subdirectory if needed). Frontmatter per the Applications section of `SCHEMA.md`.

**YAML quoting (CRITICAL):** wrap every string value in double quotes when its content contains a `:`, `#`, leading `-`/`*`/`&`/`!`/`?`/`|`/`>`/`%`/`@`/backtick, or could be parsed as a YAML type (`yes`, `no`, `null`, a bare number, an ISO date). Job titles often contain `:` (e.g. "Product Designer, Claude: Code"); the `title:`, `url:`, and `location:` fields are the highest-risk surfaces. An unquoted `:` breaks the entire dashboard's frontmatter parse, not just one row. When in doubt, quote.

Frontmatter spec:

```yaml
---
title: "<exact job title from posting>"
company: <company-slug>
ats_id: "<ATS ID>"
url: "<canonical posting URL>"
source: <greenhouse|lever|ashby|workday|careers-page|other>
posted_at: <ISO YYYY-MM-DD from ATS, or null if not exposed>
date_found: <today YYYY-MM-DD>
salary_min: <integer or null>
salary_max: <integer or null>
location: "<as stated in posting or null>"
notes: ""
---
```

Body has exactly two top-level sections, in this order:

1. `## Job description` — the verbatim JD content from step 5 (or whatever the user pasted). End with `Source: <url>`. Preserve H3 subsections, lists, comp details, EEO notes. Drop only nav / footer / "Apply" buttons.
2. `## Application form responses` — literal H2 heading, then one `### <question text verbatim>` per form field, each followed by the synthesized answer (or TODO). The web UI (`web/src/lib/split-application-blocks.ts`) splits the body on these exact H2 headings to populate the JD and Answers tabs, so don't substitute the heading text.

### 10. Report back

Print:

- The path to the new file.
- Whether the company was auto-added (path of the new `companies/interested/<slug>.md` if so).
- Synthesis stats: N full / N partial / N TODO / N demographic / N identity-verbatim sections.
- List of any newly-generated stubs (`answer-bank/<theme>/<slug>.md`) with their question text, so the user can fill them via `/seed-answer-bank` and then upgrade the partial sections with `/draft-missing-answers`.
- A reminder: this skill never submits. The user reviews and submits manually, then moves the file with `/applicationstatus` once they apply.

Do NOT commit. The user runs `/commitandpush` when ready (and instance files under `applications/` are gitignored by default).

## Hard rules

- **One URL per run.** Never batch. If the user pastes multiple URLs, ask which one or tell them to use `/find-roles` for batch.
- **Never duplicate.** Always dedup on `(company-slug, ats_id)` across all seven status folders before drafting. Refuse on match.
- **Status is always `in-review`.** This skill writes to `applications/in-review/<co>/<id>.md`. Status changes are `/applicationstatus`' job.
- **Never submit.** This skill drafts. The user submits manually.
- **Never fabricate.** If a required input is a stub or missing, write the TODO; never invent beliefs, stories, career facts, or skills. JD content is verbatim from the posting or from what the user pasted, never paraphrased.
- **Never paste a `beliefs` / `stories` / `career` / `skills` / `voice` file verbatim into an essay.** Always synthesize. Identity entries are the only ones that go in verbatim.
- **Never use em dashes (`—`)** in any drafted prose. Substitute with commas, periods, parens, or rewrite. Per `context/preferences.md` Voice rule. Hyphens (`-`) and en dashes (`–`) are fine. Verbatim JD content (the company's own text) is exempt.
- **Never `git commit`** — the user runs `/commitandpush`.
- **Hard deal-breakers from `context/preferences.md`** still apply. If the URL points to a role at a company on the avoid list (defense / gambling / etc.), warn the user before drafting. They can override.

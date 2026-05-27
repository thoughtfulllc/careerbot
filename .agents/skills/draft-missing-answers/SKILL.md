---
name: draft-missing-answers
description: Walk every application markdown file under applications/in-review/, find Q&A sections that are empty, TODO placeholders, or `[partial - pending: ...]` essays whose pending stubs have since been filled, and re-synthesize them using the same gap-analysis + synthesis logic as /find-roles (identity verbatim, essay synthesis from satisfied inputs in the SCHEMA.md checklist). Skip any section with substantive user-revised content, all demographic sections, and any section whose required answer-bank inputs are still stubs. Use after /seed-answer-bank fills stubs that /find-roles generated, to bulk-rewrite the affected applications without touching the user's manual edits.
---

# Draft Missing Answers

Fill in the Q&A sections of in-review applications that `/find-roles` left as TODOs, without touching sections the user has already filled in. Designed to be re-run after `/seed-answer-bank` adds more substrate.

The full schema is in `SCHEMA.md` at the repo root.

## Prerequisites

- `applications/`, `companies/`, `answer-bank/` folders exist.
- `context/preferences.md`, `context/index.md`, `context/resume.pdf` exist.
- At least one application file under `applications/in-review/<co>/<id>.md`.
- The web app's splitter helpers exist (read but not required to invoke):
  - `web/src/lib/split-application-blocks.ts` — `splitApplicationBlocks(blocks, source)` and `replaceApplicationSectionBody(source, sectionIndex, newBodyText)`.

If `context/preferences.md` is missing, stop.

## Scope

**Only `applications/in-review/<co>/<id>.md`.** Never read or write any other status folder. Files under `applied/`, `interview/`, `rejected/`, `offered/`, or `archived/` are off-limits.

## Workflow

### 1. Load context (same as /find-roles)

Load in this order:

- **`context/preferences.md`** — voice, location, comp, industry filters.
- **`context/index.md`** — entry point to projects and supporting material.
- **`context/resume.pdf`** — factual ground truth (companies, dates, projects, stack).
- **`answer-bank/<theme>/*.md`** — survey every file under each theme. Skip files with empty bodies (frontmatter-only stubs); these are unseeded.

Build the same in-memory structures `/find-roles` uses (`.agents/skills/find-roles/SKILL.md` step 5), including the parallel **stubs** structures:
- `identity_lookup`: Map of `question` (case-insensitive) → body, **filled entries only**.
- `identity_stubs`: Set of `question` (case-insensitive), **stubs only**.
- `beliefs`, `stories`, `career`, `skills`, `voice`: lists of `{ slug, question, tags, body }`, **filled entries only**.
- `beliefs_stubs`, `stories_stubs`, `career_stubs`, `skills_stubs`, `voice_stubs`: same shape, **stubs only**.

Track per-theme fill state:
```
identity: N filled / N stubs awaiting
beliefs:  N filled / N stubs awaiting
stories:  N filled / N stubs awaiting
career:   N filled / N stubs awaiting
skills:   N filled / N stubs awaiting
voice:    N filled / N stubs awaiting
```

### 2. Walk every in-review application

```bash
find applications/in-review -name "*.md" -type f
```

For each file:

- Read it via the Read tool.
- Parse frontmatter and body (gray-matter style: text between the first two `---` lines is YAML, rest is body).
- Look up the company profile at `companies/interested/<company-slug>.md` (`company-slug` is from frontmatter `company:`). If it's not under `interested/`, try `in-review/` and `not-interested/`. If found, read it for synthesis context. If not found, note in the report and proceed without company profile (essay quality will suffer).

### 3. Split the body into sections

Parse the body the same way `splitApplicationBlocks` does:

- Skip everything between `## Job description` and the next H2 (that's verbatim JD; never touched).
- The wrapper H2 `## Application form responses` (or `## Application form`, `## Application questions`, `## Form responses`) is a transition marker. Drop any non-heading content immediately after it (rare).
- Every H3 under the wrapper is a section: heading = the form question, body = everything between this H3 and the next H3 (or EOF), with leading/trailing blank lines trimmed.
- Other top-level H2s (not the JD heading, not the wrapper, not the Overview synthetic) become their own sections too.

Track each section's **line range in the source** so you can splice a replacement back in without touching the rest of the file. The helper `replaceApplicationSectionBody(source, sectionIndex, newBodyText)` in `web/src/lib/split-application-blocks.ts` does this exact splice; you can either invoke it via a small Node one-liner or replicate its behavior inline:

1. Re-run the source walker to compute `bodyStartLine`/`bodyEndLine` for the target section.
2. Splice lines `[bodyStartLine..bodyEndLine]` with the new body lines.
3. If the line immediately after the original body is a heading (`^##|^###`), keep a single blank line between the new body and that heading.

### 4. Classify each section

For each section's `bodyText` (the section body, trimmed of leading/trailing blank lines):

| Pattern | Eligible? | Action |
|---|---|---|
| Empty / whitespace only | **yes** | Try to fill (step 5). |
| Starts with `TODO: fill in answer-bank/identity/...` | **yes** | Re-look-up the identity entry; if still empty, leave the TODO. |
| Starts with `TODO: needs answer` (the block `/find-roles` writes for an all-inputs-missing essay, followed by bullets pointing to `answer-bank/<theme>/<slug>.md` paths) | **yes** | Re-run gap analysis (step 5). If every referenced stub now has a non-empty body, full-synthesize. If some are filled, partial-synthesize. If none are filled, leave the TODO untouched. |
| Starts with `TODO: synthesize once answer-bank/.../ is seeded` | **yes** | Legacy pattern. Re-run gap analysis the same way as above. |
| Starts with `TODO:` (any other) | **yes** | Try to fill via classification (step 5). |
| Ends with `[partial - pending: answer-bank/<theme>/<slug>, ...]` | **yes (conditional)** | Read the pending paths from the tag. If ANY of them now has a non-empty body, re-run gap analysis and re-synthesize (the new body may upgrade the essay from partial → full, or expand which inputs are satisfied). If none of the pending paths is newly filled, **skip** — the existing partial draft is still the best we can do, and the user may have hand-edited around the gaps. |
| Equals `TODO: user fills in directly` | **no** | Skip. Always user-filled (demographic etc.). |
| Ends with `[synthesized from: ...]` (no `partial`) | **no** | Skip. Already fully synthesized; don't churn unless the user manually re-TODOs it. |
| Anything else | **no** | Skip. Substantive content. Do not overwrite. |

Comparison is case-insensitive on the leading token (`TODO:`). Whitespace trim before comparing.

For the `[partial - pending: ...]` check: parse the comma-separated paths inside the brackets. For each path, look up the file; if its body is non-empty (trimmed), it counts as "newly filled."

### 5. Synthesize eligible sections

Reuse the exact logic from `find-roles/SKILL.md` steps 6 → 7 → 8 — classification, gap analysis, synthesis. The summary:

**a) Identity / logistics questions** — match the section's heading (case-insensitive, fuzzy) against the form-field → identity-question mapping in `find-roles/SKILL.md` step 6a.

- Matched, `identity_lookup` has a non-empty entry → paste body verbatim. No contextualization, no provenance tag (identity is data, not synthesis).
- Matched, only an `identity_stubs` entry exists → leave the TODO (`TODO: fill in answer-bank/identity/<slug>.md`). Flag in report.
- Matched, no entry exists → **do not generate a new identity stub** from `/draft-missing-answers` (that's `/find-roles`' job at drafting time). Leave the original TODO and flag in the report so the user knows the form field had no answer-bank match.
- Demographic (gender / ethnicity / veteran / disability) — already filtered out in step 4 as `TODO: user fills in directly`. Belt-and-braces: if one slips through, still leave it untouched.

**b) Essay questions** — classify against the essay-pattern table in `SCHEMA.md` ("How AI uses each theme"), then walk the input checklist for that pattern using the gap-analysis procedure documented in `find-roles/SKILL.md` step 7. For each input, mark **satisfied** / **pending** (stub exists from a prior `/find-roles` run) / **gap** (no entry at all).

Synthesis behavior is the same three-way split as `/find-roles` step 8:

- **All inputs satisfied** → full synthesis. Substrate from beliefs + stories + career + skills + voice + company profile + JD-specific phrasing (from the application's own `## Job description` section). End with `[synthesized from: answer-bank/<theme>/<slug>, ..., companies/interested/<co>.md]`.
- **Some inputs satisfied** → partial synthesis using only the satisfied inputs. End with `[partial - pending: answer-bank/<theme>/<slug>, ...]` listing the still-unsatisfied paths. Do not include a `[synthesized from: ...]` tag in this case.
- **All inputs unsatisfied** → leave the existing TODO untouched (or, for an empty body, write the same TODO block `/find-roles` would write: one bullet per missing input, each citing the corresponding `answer-bank/<theme>/<slug>.md` path).

**`/draft-missing-answers` does NOT generate new stubs.** Stub generation is `/find-roles`' responsibility at drafting time. This skill only consumes existing stubs and re-synthesizes essays as those stubs get filled. If gap analysis surfaces an input that has neither a filled entry nor a pending stub, treat the input as "gap" for the purposes of partial synthesis but do NOT write a new file under `answer-bank/`.

**c) Always anchor essay synthesis to `context/`** (resume facts, personal context, `index.md`-linked project material). Follow the same rule as `/find-roles` step 6d, including one-hop link following from `context/index.md` for project-naming essays. Cite any `context/` files actually consulted in the `[synthesized from: ...]` tag. Don't fabricate experiences.

**d) Voice rule** — **never use em dashes (`—`) in any drafted prose.** Substitute with commas, periods, parens, or rewrite. Per `context/preferences.md` Voice rule. Hyphens (`-`) and en dashes (`–`) are fine.

### 6. Write the file back

For each section that got a new body:

1. Compute the new source with the splice described in step 3.
2. Write the file via Write tool (rewriting the whole file is fine — gray-matter frontmatter + new body).
3. Preserve frontmatter byte-for-byte. Never touch `status`, `ats_id`, `url`, `company`, `source`, `date_found`, `salary_min`, `salary_max`, `location`, or `notes`.
4. Preserve the `## Job description` section byte-for-byte.
5. Preserve every section that was classified as "skip" (already filled OR `TODO: user fills in directly`) byte-for-byte.

If a file had zero eligible-and-fillable sections, don't write at all (preserves mtime).

### 7. Report back

After processing all files, print a structured report:

```
draft-missing-answers run report
================================

Answer-bank state:
  identity: N filled / N stubs awaiting
  beliefs:  N filled / N stubs awaiting
  stories:  N filled / N stubs awaiting
  career:   N filled / N stubs awaiting
  skills:   N filled / N stubs awaiting
  voice:    N filled / N stubs awaiting

Applications processed: <count>

  applications/in-review/<co>/<file>.md
    - <N> sections upgraded to full synthesis (all inputs satisfied)
    - <N> sections re-drafted as partial synthesis (some inputs satisfied)
    - <N> sections still TODO (no inputs satisfied)
    - <N> demographic sections skipped (always user-filled)
    - <N> sections preserved (already filled — not touched)
  ...

Files unchanged: <count> (no eligible sections to upgrade)

Next steps:
  - Run /seed-answer-bank to fill the N stubs still pending
  - Re-run /draft-missing-answers afterward to upgrade more essays
  - Use the web UI editor for per-section manual revisions
```

Do NOT commit. The user runs `/commitandpush` when ready.

## Hard rules

- **Only `applications/in-review/<co>/<id>.md` files.** Never read or write any other status folder. The presence of a file in `applied/`, `interview/`, etc. means it's been submitted or otherwise committed; we don't retroactively rewrite history.
- **Never overwrite a section that has substantive content.** If the body doesn't match an eligible pattern in step 4, leave it alone. Even if it's terse, low-quality, or you think you could write a better version. The user is the source of truth on revised answers.
- **Never write new stubs.** Stub generation belongs to `/find-roles` at drafting time. This skill consumes existing stubs; it never adds to `answer-bank/`.
- **Never re-overwrite a `[partial - pending: ...]` essay with the same partial output.** If gap analysis shows the same satisfied-input set as before (none of the pending paths got filled), skip. The skill must be idempotent.
- **Never fabricate beliefs / stories / career / skills / voice.** If the relevant input is still a stub, leave the TODO. Falling back to context-only synthesis is explicitly out of scope.
- **Never touch demographic sections.** The `TODO: user fills in directly` pattern is intentional and must remain.
- **Never change the heading of a section.** Only the body lines between the heading and the next heading get rewritten.
- **Never change the frontmatter.** Status, ats_id, url, salary, location, notes — all preserved byte-for-byte.
- **Never change the `## Job description` section.** It's the company's verbatim text.
- **Never paste a `beliefs` / `stories` / `career` / `skills` / `voice` file verbatim** into an essay answer. Always synthesize (same rule as `/find-roles`).
- **Identity entries are the only ones that go in verbatim** — those are facts.
- **Never use em dashes (`—`)** in any synthesized prose. Substitute with commas, periods, parens, or rewrite. Per `context/preferences.md` Voice rule and `AGENTS.md` Voice section. Hyphens (`-`) and en dashes (`–`) are fine; only em dashes (`—`) are out. Verbatim JD content is exempt — never reached here anyway since the skill doesn't touch the JD section.
- **Never `git mv` or move files.** The skill only edits existing files in place.
- **Never `git commit`** — the user runs `/commitandpush`.
- **Idempotent.** Running the skill twice in a row with no other changes must produce zero file writes the second time.

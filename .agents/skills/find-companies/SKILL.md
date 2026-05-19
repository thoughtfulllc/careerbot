---
name: find-companies
description: Search for companies that match the user's background, skills, and preferences. For each viable match, spawn a research subagent in parallel to produce a deep profile (products, news, stock/financials, engineering culture, work-life balance, Glassdoor signal, controversies, offices) and write a markdown file to companies/in-review/<slug>.md. Candidates that don't meet the bar also get a one-paragraph markdown file at companies/not-interested/<slug>.md so they never get re-surfaced. Reads seeds from companies/ideas.md.
---

# Find Companies

Surface companies the user should consider applying to, then queue each one for review by writing a deep research profile to `companies/in-review/<slug>.md`. The user reviews and decides; this skill never submits applications and never moves files between status folders on its own.

**Goal: end the run with at least 10 NEW profiles added to `companies/in-review/`** (i.e. 10 candidates that survived pre-filter and scored `match_score` ≥ 5). If the first research pass yields fewer than 10, generate more candidates and dispatch another round — repeat until the threshold is met or you've exhausted reasonable sources.

The full schema is in `SCHEMA.md` at the repo root.

## Prerequisites

The `companies/` folder exists. `SCHEMA.md` exists at the repo root.

## Workflow

### 1. Load the user's context

Read these in parallel — everything downstream depends on them:

- `context/index.md` — entry point linking to all background material
- `context/preferences.md` — current job preferences (titles, comp floor, locations, target industries, named target companies, deal-breakers)
- `context/resume.pdf` — resume
- Any project folders linked from `context/index.md`
- **`companies/ideas.md`** — the user's free-form list of URLs, company names, and notes. Stays in the repo as a seed input.

### 2. Inventory existing entries to avoid duplicates

Walk every markdown file under `companies/` and `applications/` to build the "already-known" set:

```bash
ls companies/in-review/*.md companies/interested/*.md companies/not-interested/*.md 2>/dev/null
```

For each file, the slug = the filename without `.md`. Also collect the `slug:` frontmatter value as a safety check (filename and slug should always agree).

For applications, collect the company-slug segment of the path: `applications/*/<company-slug>/*.md` → `<company-slug>`.

**Every candidate generated in step 3 must be checked against this set before any research effort is spent.** A company with any status (`in-review`, `interested`, `not-interested`) must not be re-researched. **Anything under `companies/not-interested/` is a hard skip — never re-surface it, not even under a different slug spelling.**

### 3. Generate a candidate list

Use whatever web-search and page-fetch capability is available to assemble candidate companies. **Aim to surface enough candidates that at least 10 will survive pre-filter and score ≥ 5** — in practice that means generating ~15–25 candidates per pass, since some will dedup out, some will get pre-filtered, and some will score low. Pull from:

- **`companies/ideas.md`** — always include every entry here that doesn't already exist in `companies/`. Format is loose: bare URLs, bare names, optional `- note` suffix, markdown headings as informal groupings.
- **"If you like X, you might like Y" look-alikes** — for each company in `companies/ideas.md` AND each company under `companies/interested/`, generate 1–3 similar companies the user is likely to also like. "Similar" means competing in the same space, building adjacent products for the same audience, sharing engineering DNA (ex-employees, similar stack), or otherwise occupying the same niche. Skip the source company itself; only emit the look-alikes. This is the primary engine for expanding the candidate pool — lean on it.
- The named-companies list in `preferences.md` (always include any not already on file).
- Industry peers in each target industry from `preferences.md`.
- Companies whose tech stack and product overlap with the user's resume and project work.
- Recently funded / notable companies in adjacent spaces.

**Before adding a candidate to the research queue, check it against the already-known set from step 2 and drop it if it matches.** Don't waste a subagent on a company that's already on file.

### 4. Pre-filter the candidates

For each candidate, decide one of three outcomes before spending research effort:

- **Skip silently** — already exists in `companies/` or as a company-slug under `applications/`. Don't write anything.
- **Reject** — clearly violates `preferences.md` (deal-breakers like surveillance tech, defense contractors, gambling, crypto, politically-leaning, anything Elon-affiliated; comp floor unmeetable; location incompatible). Create a short markdown file at `companies/not-interested/<slug>.md` with `not_interested_reason` set, so it never gets re-surfaced.
- **Research** — survives pre-filter; proceed to step 5.

Mention the cut candidates in your reply too — the user wants to see who got dropped and why.

### 5. Spawn one research subagent per surviving candidate, in parallel

Dispatch the candidates to whatever sub-agent / parallel-task mechanism the host harness provides. Launch them concurrently — issue all dispatch calls in a single batch so the research happens in parallel rather than serially.

Each sub-agent prompt must be **self-contained** — assume the sub-agent has no view of this conversation and no shared memory with you. Include:

- The company name
- A summary of the user's preferences and background it should match against (paste the relevant excerpts from `preferences.md` and `context/index.md` — do not just reference them by path; the sub-agent may not read the same files you did)
- The full **File format** spec (below) so it writes the markdown file correctly, including the path to write to
- The full **Research dimensions** list (below)
- The full **Match score calibration** rubric (below)
- The output routing rule: **if final `match_score` ≥ 5**, write to `companies/in-review/<slug>.md`. **If `match_score` ≤ 4**, write a short file at `companies/not-interested/<slug>.md` with `not_interested_reason` set. Either way, one file per candidate so it never gets re-researched.
- Slug rule: lowercase, hyphenated, alphanumeric.
- Instructions to use the host's web-search / page-fetch tools freely, cite sources inline as markdown links, and never invent facts
- A request for a one-line summary AND the final `match_score` in its return message so this skill can render a final report

If the host harness has no sub-agent mechanism, fall back to researching candidates sequentially in this same conversation, applying the same prompt template and writing the same markdown files.

### 6. Top up if under 10 new profiles

After all subagents return, count the new files added to `companies/in-review/` this run. **If that count is below 10**, return to step 3 and generate a fresh batch of candidates — biased toward dimensions you haven't exhausted yet (e.g. more look-alikes for `interested` entries you haven't mined, different target industries, different funding stages). Re-apply step 2's dedup check (the already-known set has grown — include the files you just wrote). Dispatch another parallel research round. Repeat until you've landed at least 10 new `in-review/` profiles, or until you've genuinely exhausted plausible candidates (in which case say so explicitly in the final report).

### 7. Render a summary table

Once all subagents finish, present two tables:

**Researched (in-review)** — `match_score` ≥ 5, sorted by `match_score` descending:

| Company | Industry | Match | Headcount | Why it fits (one line) | File path |

**Not interested** — pre-filter cuts from step 4 plus subagent cuts (`match_score` ≤ 4):

| Company | Reason | File path |

Call out any companies a subagent flagged with serious concerns even if they cleared the threshold.

Do NOT commit. The user runs `/commitandpush` when ready (and instance files under `companies/in-review/` and `companies/not-interested/` are gitignored).

## File format

Each profile is a new markdown file written via the Write tool. Path = `companies/<status>/<slug>.md` where `<status>` is `in-review` (match_score ≥ 5) or `not-interested` (match_score ≤ 4).

**Frontmatter (for `match_score` ≥ 5):**

```yaml
---
name: "Company Name"
slug: <company-slug>
industry: [<kebab-case tags, e.g. ai-ml, dev-tools, infrastructure, data>]
match_score: <1–10 integer>
headcount: "<e.g. ~500, 150-200, 5000+>"
stage: "<e.g. Series C, Public, Bootstrapped>"
valuation: "<e.g. $1.5B, $95B market cap, undisclosed>"
hq: "<City, Country>"
offices: [<list of additional office locations>]
remote_policy: <remote|hybrid|onsite>
researched_on: <today YYYY-MM-DD>
not_interested_reason: null
---
```

**Body** (omit any section with nothing verified to say, never pad):

- `## Why this is a good match` — explicit ties to `preferences.md` and the user's resume / projects
- `## What they do` — current products, primary business, who their customers are
- `## Recent news` — last ~6 months: launches, funding, leadership, layoffs, partnerships
- `## Engineering culture` — tech stack, eng blog highlights, public talks, OSS work, hiring bar signals
- `## Company culture & work-life balance` — Glassdoor themes, Blind/Reddit signal, hours, on-call, RTO posture
- `## Stock / financial trajectory` — public: stock perf + analyst sentiment; private: funding history, revenue/growth if disclosed
- `## Concerns / controversies` — layoffs, lawsuits, exec scandals, ethical issues, customer-base concerns
- `## Open roles` — careers page link; flag any roles matching titles in `preferences.md`
- `## Sources` — full list of URLs cited above as a bulleted list

**Frontmatter (for `match_score` ≤ 4, not-interested file):**

```yaml
---
name: "Company Name"
slug: <company-slug>
industry: []
match_score: <1–4>
headcount: null
stage: null
valuation: null
hq: null
offices: []
remote_policy: null
researched_on: <today YYYY-MM-DD>
not_interested_reason: "<one short phrase, e.g. 'defense contractor', 'below comp floor', 'no remote'>"
---
```

**Body for not-interested files:** 1–3 paragraphs explaining why this one was cut. Cite a source if the reason is a specific factual claim. No need for full research dimensions.

## Research dimensions (paste into each subagent prompt)

The subagent should investigate:

- **Products** — what they ship, who uses it, recent launches, roadmap signals
- **News (last 6 months)** — funding rounds, acquisitions, layoffs, leadership changes, controversies
- **Stock / financials** — for public: stock performance + analyst sentiment; for private: funding history, last-known valuation, revenue if disclosed
- **Engineering culture** — tech stack, engineering blog, conference talks, OSS contributions, interview-process signals
- **Company culture** — Glassdoor ratings + recurring review themes, Blind threads, Reddit, exit-interview reporting
- **Work/life balance** — typical hours, on-call expectations, vacation policy, RTO/remote stance
- **Locations** — offices and remote policy; flag if compatible with the user's preferred cities
- **Concerns** — antitrust, lawsuits, ethical issues, founder/exec controversies, customer-base concerns (defense, surveillance), recent layoffs
- **Match assessment** — explicit comparison to `context/preferences.md` and the user's resume; produce a numeric `match_score` 1-10 with justification

## Match score calibration

- **9–10** — named in `preferences.md` specific-companies list, OR near-perfect fit on industry + role-level + culture + comp + location → file goes to `companies/in-review/`
- **7–8** — strong fit on most dimensions; one or two soft mismatches → `in-review/`
- **5–6** — adjacent fit; worth knowing about but not a top target → `in-review/`
- **1–4** — below threshold; write a short file to `companies/not-interested/` so it never gets re-researched. Do NOT write a full profile body.

## Constraints

- **Never invent facts.** If something can't be verified, omit it or say "not publicly disclosed."
- **Never create a duplicate file.** Always check `companies/{in-review,interested,not-interested}/<slug>.md` before writing; skip if any exists.
- **Never re-surface a not-interested company.** Anything in `companies/not-interested/` is final unless the user explicitly removes it.
- **Never submit applications.** This skill only surfaces companies for the user's review.
- **One file per company**, with the path reflecting the outcome. Per-role tracking belongs in `applications/`.
- **Cite every non-obvious claim.** Inline links in the body, full list in the Sources section.
- **Hard deal-breakers in `preferences.md` are absolute.** Do not surface a defense contractor or a crypto company because the match-score math otherwise looks good.
- **Never move files between status folders.** That's the user's call (or `/applicationstatus`'s, for applications). This skill only creates new files under `in-review/` or `not-interested/`.
- **Never `git commit`** — the user runs `/commitandpush`.

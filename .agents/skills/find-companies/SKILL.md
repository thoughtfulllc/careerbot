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

Use `WebSearch` plus `WebFetch` to assemble candidates. **Aim to surface enough that at least 10 will survive pre-filter and score ≥ 5** — in practice ~15–25 candidates per pass.

Pull from two buckets: **Seed** (always include) and **Discovery** (required quota — must come with a verifiable source URL).

**Critical:** every Discovery candidate must be backed by a real URL you actually fetched (a YC company page, a Greenhouse/Lever/Ashby board, a funding-announcement article). If you cannot produce that URL on demand, the candidate is name-from-memory and does NOT count toward the Discovery quota.

#### 3a. Seed bucket (always include)

- **`companies/ideas.md`** — include every entry that doesn't already exist in `companies/`. Format is loose: bare URLs, bare names, optional `- note` suffix, markdown headings as informal groupings. **Skip any entry that looks like an example placeholder** (`example.com`, `acme.*`, `beta.ai`, `Acme Corp`, `Beta Inc`) — those are leftovers from the example file.
- **"If you like X, you might like Y" look-alikes** — for each company in `companies/ideas.md` AND each company under `companies/interested/`, generate 1–3 similar companies. "Similar" means competing in the same space, building adjacent products for the same audience, sharing engineering DNA (ex-employees, similar stack), or otherwise occupying the same niche. Skip the source company itself; only emit the look-alikes.
- The named-companies list in `preferences.md` (always include any not already on file).
- Industry peers in each target industry from `preferences.md`.
- Companies whose tech stack and product overlap with the user's resume and project work.

#### 3b. Discovery sources (required — at least 8 candidates per round, each with a fetched source URL)

Look-alikes and seeds skew toward names the user already knows. To surface startups they wouldn't otherwise see, **at least 8 of each round's candidates must come from these sources**. Fan the fetches out in parallel — issue them as a single batch of tool calls, not one at a time.

The directories listed below are picked specifically because they are *fetchable* (server-rendered HTML, public JSON, or well-indexed by Google so `WebSearch` works). The old skill pointed at SPAs like `ycombinator.com/companies` and `wellfound.com/startups` that return empty shells to `WebFetch`; those are intentionally NOT in this list.

**Primary: ATS-level discovery (jobs-first → company)**

This is the highest-signal path because a live job posting implies the company is actively hiring for the role the user wants. For each role title and location combo from `preferences.md`, run two or three `WebSearch` queries like:

- `site:boards.greenhouse.io "<role title>" "<location or remote>"`
- `site:job-boards.greenhouse.io "<role title>" "<location or remote>"`
- `site:jobs.lever.co "<role title>" "<location or remote>"`
- `site:jobs.ashbyhq.com "<role title>" "<location or remote>"`
- `site:jobs.workable.com "<role title>" "<location or remote>"`

The URL path segment after the host is the company slug (e.g. `boards.greenhouse.io/anthropic` → `anthropic`). Dedupe to company-level — multiple postings from the same company collapse to one candidate. Optionally hit the public JSON to confirm the board is live:

- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs`
- Lever: `https://api.lever.co/v0/postings/<slug>?mode=json`
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/<slug>`

**Secondary: Y Combinator (directory-first → check for jobs)**

YC's main `/companies` directory is a JS SPA and does NOT respond to `WebFetch`. Use these alternatives instead:

- **`https://www.workatastartup.com/companies`** — YC's official jobs board, server-rendered, filterable by role/remote/batch. This is the right primary YC surface.
- **`https://yc-oss.github.io/api/companies/all.json`** — community-maintained JSON of every YC company with batch/industry/status tags. One fetch returns the entire directory; filter client-side by `batch in [W24, S24, W25, S25, F25, W26]`, `status: Active`, and industry tags matching `preferences.md`.
- **`WebSearch` fallback** — `site:ycombinator.com/companies/ <industry> <batch>` surfaces individual indexed company pages.

**Tertiary: funding-announcement roundups**

`WebSearch` queries like `"raised" "Series A" <target industry> 2026 site:techcrunch.com` or the same against `news.crunchbase.com`. Filter to seed–Series C in target industries within the last 90 days.

**Do not use** (previously listed but not actually fetchable in practice): Wellfound `/startups` (auth-walled SPA), Product Hunt category pages (infinite-scroll JS), GitHub trending (rarely maps cleanly to a company). If you can find a fetchable equivalent for any of these, fine — otherwise skip them rather than rationalizing memory-generated names as "Discovery (Wellfound)".

A candidate counts toward the Discovery quota only if (a) you fetched the source URL this run and (b) the user is unlikely to already know it. Rough proxy for (b): if it would appear in the top 50 results for "best AI startups 2025," it does NOT count toward Discovery — put it in Seed (look-alike) instead.

#### 3c. Dedup, verify, and label

**Before adding a candidate to the research queue:**

1. Check it against the already-known set from step 2 and drop it if it matches. When checking against `not-interested/`, normalize for common slug variants (e.g. `cal-com` vs `calcom`, `hugging-face` vs `huggingface`) before deciding.
2. For Discovery candidates, confirm the source URL is one you actually fetched this run — not one you remember existing. If you can't quote the fetched URL, downgrade the candidate to Seed (look-alike) or drop it.

Track each surviving candidate's source so the final summary table (step 7) can label it precisely: `Discovery (Greenhouse: anthropic)`, `Discovery (YC W25 via workatastartup)`, `Discovery (yc-oss API)`, `Discovery (TechCrunch funding roundup)`, `Look-alike (Linear)`, `Seed (ideas.md)`, `Seed (preferences.md)`, etc. The source label must reference the concrete fetched artifact, not the abstract bucket.

**Self-check before moving to step 4:** if fewer than 8 of your candidates have a Discovery source URL you actually fetched this round, go back and run more ATS-level or YC searches. Don't proceed with a round that's secretly all Seed.

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

After all subagents return, count the new files added to `companies/in-review/` this run. **If that count is below 10**, return to step 3 and generate a fresh batch of candidates — biased toward dimensions you haven't exhausted yet (e.g. more `site:boards.greenhouse.io` searches with different role titles or locations, a different YC batch slice from the `yc-oss` JSON, different target industries, different funding stages). Re-apply step 2's dedup check (the already-known set has grown — include the files you just wrote). Dispatch another parallel research round. Repeat until you've landed at least 10 new `in-review/` profiles, or until you've genuinely exhausted plausible candidates (in which case say so explicitly in the final report).

### 7. Render a summary table

Once all subagents finish, present two tables:

**Researched (in-review)** — `match_score` ≥ 5, sorted by `match_score` descending:

| Company | Source | Industry | Match | Headcount | Why it fits (one line) | File path |

The `Source` column should use the labels from step 3c (`Discovery (YC W25)`, `Look-alike (Linear)`, `Seed (ideas.md)`, etc.) so the user can see at a glance whether the round actually surfaced unknowns or just regurgitated their existing list.

**Not interested** — pre-filter cuts from step 4 plus subagent cuts (`match_score` ≤ 4):

| Company | Reason | File path |

Call out any companies a subagent flagged with serious concerns even if they cleared the threshold.

Do NOT commit. The user runs `/commitandpush` when ready (and instance files under `companies/in-review/` and `companies/not-interested/` are gitignored).

## File format

Each profile is a new markdown file written via the Write tool. Path = `companies/<status>/<slug>.md` where `<status>` is `in-review` (match_score ≥ 5) or `not-interested` (match_score ≤ 4).

### YAML quoting rules (CRITICAL — past runs have broken the dashboard)

YAML will silently mis-parse unquoted string values that contain certain characters, taking down the entire web UI. **Wrap any string value in double quotes when its content contains any of these:**

- A colon `:` anywhere in the value (e.g. `stage: "public (NYSE: FSLY)"`, never `stage: public (NYSE: FSLY)` — YAML reads the inline `:` as a nested mapping and the whole frontmatter fails to parse).
- A `#` (read as a comment start).
- Leading whitespace, a leading `-`, `*`, `&`, `!`, `?`, `|`, `>`, `%`, `@`, or backtick.
- A value that could be interpreted as a YAML type (`yes`, `no`, `on`, `off`, `null`, `~`, a bare number like `2.0`, or an ISO date).

Common offenders in this skill's output: `stage:` ("public (NYSE: NET)"), `valuation:` ("$95B market cap (May 2026)" — parens are fine but if you ever add a `:`, quote), `headcount:` (e.g. "~5,000 (post-layoff)"), `remote_policy:` (must be the bare enum `remote` | `hybrid` | `onsite` — do NOT add qualifiers like "hybrid (flexible)"; put qualifiers in the body). When in doubt, quote.

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

- **Bias toward companies the user is unlikely to already know.** Famous unicorns (Stripe, Notion, Figma class) are fine to include if they fit, but they don't count toward the Discovery quota in step 3b. If a round comes back with only household names, redo candidate generation with heavier weight on ATS-level searches (Greenhouse/Lever/Ashby `site:` queries) and the `yc-oss` JSON dump filtered to recent batches.
- **Never invent facts.** If something can't be verified, omit it or say "not publicly disclosed."
- **Never create a duplicate file.** Always check `companies/{in-review,interested,not-interested}/<slug>.md` before writing; skip if any exists.
- **Never re-surface a not-interested company.** Anything in `companies/not-interested/` is final unless the user explicitly removes it.
- **Never submit applications.** This skill only surfaces companies for the user's review.
- **One file per company**, with the path reflecting the outcome. Per-role tracking belongs in `applications/`.
- **Cite every non-obvious claim.** Inline links in the body, full list in the Sources section.
- **Hard deal-breakers in `preferences.md` are absolute.** Do not surface a defense contractor or a crypto company because the match-score math otherwise looks good.
- **Never move files between status folders.** That's the user's call (or `/applicationstatus`'s, for applications). This skill only creates new files under `in-review/` or `not-interested/`.
- **Never `git commit`** — the user runs `/commitandpush`.

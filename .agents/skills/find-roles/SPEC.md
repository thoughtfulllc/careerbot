# Find Roles v2: Maximize Discovery

**Status:** draft / proposed
**Owner:** Jessica
**Scope of change:** `.agents/skills/find-roles/SKILL.md`, `companies/interested/*.md` frontmatter, plus new `.agents/skills/find-roles/scripts/` helpers and a `SCHEMA.md` addition for the company `ats:` / `ats_slug:` fields.

## 1. Goal

Maximize the number of relevant, fresh, applyable open roles surfaced per `/find-roles` run, without regressing the existing drafting / synthesis quality.

"Relevant" = matches the user's title synonyms, location flexibility, comp floor, and industry filters from `context/preferences.md`.
"Fresh" = posted or updated within the configurable freshness window (default: last 90 days).
"Applyable" = the user can submit the application herself; live ATS posting with a known canonical URL.

## 2. Non-goals

- Changing the answer-bank synthesis logic (steps 5-8 of the current skill). Those work and are out of scope.
- Submitting applications.
- Auto-filling demographic fields.
- Crawling LinkedIn or Indeed as a primary source (they remain backup only).
- Building a long-term jobs database. Each `/find-roles` run is stateless aside from the dedup set on disk.

## 3. Problem statement (one paragraph)

The current skill scans 69+ companies sequentially, fetching each careers page as opaque HTML. JS-rendered careers pages (Workday, custom SPAs) return empty shells; the skill has no fallback. Title-synonym matching is implicit, so the agent silently drops "Staff Designer" / "Founding Designer" / "UX Engineer" variants the user would have wanted. The "be selective" rule fights the user's stated goal of maximum finding. There's no freshness filter, no cross-cutting ATS pass, and no parallelism — so 69 companies × per-role JD-verbatim-fetch is the bottleneck that causes the agent to abandon part of the list each run. See the `/find-roles` skill review (conversation 2026-05-22) for the full 15-item debugging breakdown.

## 4. Architecture overview

Two structural shifts:

### 4a. Phase split: Discovery (cheap, parallel) → Drafting (expensive, per-role)

Today `/find-roles` does both in one loop per company. The spec splits them:

- **Discovery** produces a list of `LeadRecord` objects (title, URL, location, ATS-id, posted-at, match-confidence). Cheap: one ATS API call per company plus minimal title matching.
- **Drafting** produces the application markdown with full verbatim JD + form-question synthesis. Expensive: same as today's steps 4-8.

The default `/find-roles` invocation still runs both phases end-to-end. The phase split is internal — it just means a discovery failure on one company no longer blocks drafts for the others, and an interrupted run leaves a complete leads list on disk.

**Optional new flag (future):** `/find-roles --discover-only` — produces only the leads file, no drafts. Useful when the user wants to triage 200 leads before committing to drafting.

### 4b. ATS adapter layer

Each company resolves to one of six ATS adapters. Adapters are pure functions: `(company_slug, ats_slug, filters) → LeadRecord[]`. The skill prompt invokes adapters; adapters encapsulate per-ATS endpoint quirks. Adapters are documented as endpoint specs in this file; implementation lives in `.agents/skills/find-roles/scripts/` as small Python or shell helpers invokable via the Bash tool.

## 5. Component specs

### 5.1 Company frontmatter extension

Add to every `companies/interested/<slug>.md` file (and the SCHEMA.md DDL):

```yaml
ats: greenhouse | lever | ashby | workday | smartrecruiters | workable | custom | null
ats_slug: "<slug on that board, e.g. 'anthropic' or 'apple/External'>"
careers_url: "<canonical careers URL>"
```

- `ats` = the ATS host family. `null` if unknown / not yet resolved.
- `ats_slug` = the path segment after the host. For Workday this is `<tenant>/<site>` (two segments).
- `careers_url` already exists in SCHEMA but is under-used.

**Resolution order at runtime (when `ats` is null):**
1. WebFetch the `careers_url` page and detect the host substring (`boards.greenhouse.io` → `greenhouse`; `jobs.lever.co` → `lever`; etc.).
2. If detected, write the result back to the company file's frontmatter so future runs skip resolution.
3. If not detected after one pass, mark `ats: custom` and use the generic HTML adapter.

**One-time backfill:** a Bash + WebFetch loop populates the 69 existing company files. See §8 Migration.

### 5.2 ATS adapters

All adapters take the same filter set and return the same `LeadRecord` shape.

**Filter set (applied uniformly across adapters):**
```python
{
  "title_patterns": ["(senior|sr\\.?|staff|lead|principal|founding) ?(product )?(designer|design engineer)", ...],
  "locations_allow": ["remote", "us", "san francisco", "new york", "los angeles", "seattle", ...],
  "locations_block": ["india", "germany", "uk only", ...],  # locations that block on-site requirements
  "freshness_days": 90,
  "exclude_ats_ids": [...],  # from dedup set
}
```

**LeadRecord shape:**
```python
{
  "ats_id": "5223916008",
  "title": "Design Engineer, Web",
  "location": "San Francisco, CA | Remote US",
  "department": "Design",
  "posted_at": "2026-05-09",
  "posting_url": "https://job-boards.greenhouse.io/anthropic/jobs/5223916008",
  "comp_min": 200000,        # null if not in posting
  "comp_max": 280000,        # null if not in posting
  "content_excerpt": "...",  # first ~500 chars of JD; full JD fetched in drafting phase
  "source": "greenhouse",
  "match_confidence": "high|medium|low",
  "match_reasons": ["title=Senior Product Designer match", "location=remote-us", "freshness=12d"],
}
```

#### 5.2.1 Greenhouse adapter

- **List endpoint:** `https://boards-api.greenhouse.io/v1/boards/<ats_slug>/jobs?content=true`
- **Question schema endpoint:** `https://boards-api.greenhouse.io/v1/boards/<ats_slug>/jobs/<id>?questions=true` (used in drafting phase only)
- **Posting URL pattern:** `https://job-boards.greenhouse.io/<ats_slug>/jobs/<id>` (newer) or `https://boards.greenhouse.io/<ats_slug>/jobs/<id>` (older)
- **Date field:** `updated_at` ISO string
- **Location field:** `location.name` (free text; sometimes "Remote", sometimes city)
- **Notes:** returns ALL active jobs in one call. Free. No auth.

#### 5.2.2 Lever adapter

- **List endpoint:** `https://api.lever.co/v0/postings/<ats_slug>?mode=json`
- **Posting URL pattern:** `https://jobs.lever.co/<ats_slug>/<id>`
- **Date field:** `createdAt` epoch ms
- **Location field:** `categories.location`
- **Notes:** returns all active postings in one call. Free. No auth.

#### 5.2.3 Ashby adapter

- **List endpoint:** `https://api.ashbyhq.com/posting-api/job-board/<ats_slug>?includeCompensation=true`
- **Posting URL pattern:** `https://jobs.ashbyhq.com/<ats_slug>/<id>`
- **Date field:** `publishedDate` ISO
- **Location field:** `locationName` or `secondaryLocations[].locationName`
- **Compensation:** present in `compensation.compensationTierSummary` when included
- **Notes:** returns all active. Free. No auth.

#### 5.2.4 Workday adapter

The hard case. Workday is what Apple / Meta / Salesforce / Adobe / Cisco / many F500 use.

- **List endpoint:** `POST https://<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs`
- **Body:**
  ```json
  {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
  ```
- **Pagination:** increment `offset` by `limit` until `total` is reached.
- **Posting URL pattern:** `https://<tenant>.wd<N>.myworkdayjobs.com/<site>/job/<location-slug>/<title-slug>_<id>`
- **Date field:** `postedOn` ("Posted Today", "Posted 3 Days Ago"; parse relative)
- **Location field:** `locationsText`
- **Notes:**
  - Requires `Content-Type: application/json` + browser-like User-Agent or it returns 403.
  - The `<tenant>` and `<N>` (e.g. `wd5`) are part of the URL — must be captured in `ats_slug` as `<tenant>/wd<N>/<site>`. Example for Apple: `apple/wd1/External`.
  - Anti-scraping is light but real; throttle to one request per second per tenant.

**Companies on Workday in current `interested/`:** apple, adobe (some roles), microsoft (some — also their own portal), and likely others. Spec calls for resolving each at backfill time.

#### 5.2.5 SmartRecruiters / Workable adapters

Lower-priority because few interested companies use them, but documented for completeness:

- **SmartRecruiters list:** `https://api.smartrecruiters.com/v1/companies/<ats_slug>/postings`
- **Workable list:** `https://apply.workable.com/api/v1/widget/accounts/<ats_slug>?details=true`

#### 5.2.6 Custom HTML adapter (fallback)

For companies on home-grown careers pages (Google, Meta sometimes, Stripe partially, etc.):

- Use `WebFetch` with the explicit prompt: *"Return every job posting on this page as a list. For each, give me: title, location, full URL to the individual posting, and posted date if visible. Do not summarize."*
- Parse the response into `LeadRecord`s with `match_confidence` capped at "medium" (less structured data → less confidence).
- For Google / Meta specifically, document the known direct-careers-search URLs:
  - Google: `https://www.google.com/about/careers/applications/jobs/results/?q=%22<title>%22&location=United+States`
  - Meta: `https://www.metacareers.com/jobs/?q=<title>&offices[0]=Remote%2C+US`
- For Apple (Workday-backed but with a search UI), prefer the Workday adapter on `apple/wd1/External`.

### 5.3 Title matching (explicit synonym list)

Hard-coded in the skill, mapped against `preferences.md` titles:

```python
# preferences.md "Senior Product Designer" + "Design Engineer" expand to:
TITLE_PATTERNS = [
    # Product Designer family
    r"\b(senior|sr\.?|staff|lead|principal|founding)\s+(product\s+)?designer\b",
    r"\bproduct\s+designer,?\s+(senior|sr|staff|lead|principal)\b",
    r"\b(senior|sr\.?|staff|lead|principal|founding)\s+designer\b",  # may match too broadly; use locations_block
    # Design Engineer family
    r"\b(senior|sr\.?|staff|lead|principal|founding)?\s*design\s+engineer\b",
    r"\b(senior|sr\.?|staff|lead|principal|founding)?\s*ux\s+engineer\b",
    r"\bdesign\s+technologist\b",
    # Specialty designers explicitly in user's specialties list
    r"\b(senior|staff|lead)?\s*(brand|visual|motion|design\s+systems?)\s+designer\b",
    r"\bdesign\s+systems?\s+engineer\b",
    # Product Engineer (design-focused) — uncommon but valid
    r"\bproduct\s+engineer\b.*\b(design|frontend|ui)\b",
]

# Excluded — these are NOT designer roles even if "design" appears
TITLE_EXCLUDE = [
    r"\bhardware\s+design\b", r"\bASIC\s+design\b", r"\bchip\s+design\b",
    r"\b(circuit|PCB|RF|mechanical|electrical)\s+design\b",
    r"\bgame\s+designer\b",  # unless user explicitly wants games (preferences.md doesn't)
]
```

The synonym list lives in the skill prompt (so any subagent applying it stays consistent) AND ideally in a single shared file under `.agents/skills/find-roles/scripts/title_patterns.py` so the helper scripts can import the same list.

**Match confidence:**
- `high` = exact match against the user's two listed titles (`Senior Product Designer`, `Design Engineer`).
- `medium` = match against an explicit synonym in the list above.
- `low` = title contains "designer" or "design engineer" tokens but doesn't match a synonym pattern; surfaced anyway, flagged for human review.

### 5.4 Location matching

Honor all four `open_to_*` flags from preferences.md. Effective allowlist:

```python
def location_matches(posting_location: str, prefs) -> bool:
    text = posting_location.lower()
    # Hard blockers — out of country unless explicitly remote
    if any(x in text for x in ["india", "europe only", "emea only", "apac only", "uk only", "germany only"]):
        return False
    # Match any of:
    return (
        "remote" in text and ("us" in text or "north america" in text or "anywhere" in text or "remote" == text.strip())
        or any(city in text for city in ["san francisco", "bay area", "new york", "nyc", "los angeles", "la,", "seattle"])
        or any(state in text for state in ["california", "new york state", "washington", "washington,", "oregon"])  # within preferred-relocation radius
        or "united states" in text and prefs.open_to_relocation  # any US city if open to relocation
    )
```

Spec: when `open_to_relocation: true` (current preferences), ANY US-based role counts as a location match. Cities outside SF/NYC/LA/Seattle get flagged as `match_reasons: ["location=US-relocation-required"]` so the user can prioritize.

### 5.5 Freshness filter

- Default cutoff: 90 days from today.
- Source field per adapter: `updated_at` (Greenhouse), `createdAt` (Lever), `publishedDate` (Ashby), `postedOn` (Workday, parsed from relative text).
- Override: add `freshness_days:` to `context/preferences.md` if user wants a different default.
- All leads carry `posted_at` in the LeadRecord; the report sorts by recency descending.

### 5.6 Parallelization

The current skill is silent on parallelism. Spec: explicit fan-out.

**Strategy A: one subagent per company** (similar to `/find-companies`).
- 69 subagents × ~5s per ATS API call ≈ ~6 wall-clock seconds (Sonnet-tier is plenty for this).
- Each subagent gets: company slug, ATS hint, dedup set excerpt, filter set.
- Each returns: `LeadRecord[]` + a per-company status (success / partial / failed-needs-fallback).

**Strategy B: one subagent per ATS, batching all companies on that ATS.**
- Greenhouse subagent handles all ~40 Greenhouse companies in one prompt.
- Tighter coupling but fewer subagent overhead costs.

**Recommendation: Strategy A** — simpler, mirrors the find-companies pattern the user is now familiar with, easier to debug per-company failures.

### 5.7 Cross-cutting ATS search pass

After the per-company sweep, run 4-6 `WebSearch` queries to catch roles posted to ATS subdomains the per-company crawl missed:

```python
CROSS_CUTTING_QUERIES = [
    f'site:boards.greenhouse.io ("Senior Product Designer" OR "Design Engineer") "Remote"',
    f'site:job-boards.greenhouse.io ("Senior Product Designer" OR "Design Engineer") "Remote"',
    f'site:jobs.ashbyhq.com ("Senior Product Designer" OR "Design Engineer")',
    f'site:jobs.lever.co ("Senior Product Designer" OR "Design Engineer")',
]
```

For each result, extract the company slug from the URL. **Only keep** results whose company-slug matches a company in `companies/interested/`. (We're not surfacing new companies here — `/find-companies` does that.)

The cross-cutting pass also catches roles at multi-ATS companies (e.g. eng on Greenhouse, design on Ashby) where the per-company crawl only hit one board.

### 5.8 Match confidence + "surface, don't reject"

Replace the current Step 3 instruction "Be selective. A handful of strong matches beats a dump of weak ones" with:

> Surface every plausible match. The user reviews and prunes; the agent is not the final filter.
>
> Reject only on hard rules: industries_avoid match (gambling/defense), explicit location blockers, salary-below-floor when the floor is stated in the posting.
>
> Mark borderline matches `match_confidence: low` with a one-line reason. They still appear in the report.

Per-company top-N cap, configurable, defaulting to:

```yaml
# in preferences.md
max_roles_per_company: 8        # surface up to 8 roles per company per run
max_roles_total: 100            # total across all companies, sorted by confidence + freshness
```

### 5.9 Dedup enhancements

Today: dedup by `url:` and `ats_id:` (line 39 of SKILL.md).

Add: dedup by **content hash** — `sha1(normalized_title + normalized_company + normalized_location)`. Prevents the same role at different URLs (cross-posted on LinkedIn / Wellfound / the company's own page) from creating duplicate application files.

The dedup set in step 1 becomes `(urls, ats_ids, content_hashes)`.

### 5.10 Preflight checks

Before any discovery work, run these checks and surface the results before fanning out:

1. **Answer-bank fill state** — count filled vs stub entries per theme. If `voice/` is empty, print:
   *"Heads up: answer-bank/voice/ has 0 entries. Essay synthesis quality will be degraded until you add at least 1-2 voice samples via /seed-answer-bank."*
2. **Company-frontmatter ATS-coverage** — count companies with `ats:` set vs `null`. Print:
   *"42 of 69 interested companies have `ats:` resolved. 27 will use slower careers-page detection on this run. Run the one-time backfill script to lock these in."*
3. **Identity-bank coverage** — confirm all 17 canonical identity stubs are filled. If any are stubs, print and abort drafting (since every application would have TODO holes).

These checks run cheap; their job is to set expectations and surface fill-state drift early.

### 5.11 Report shape (updated)

Current report (lines 319-342 of SKILL.md) is good but adds the following sections:

```
=== Discovery summary ===
Companies scanned:        69
  - Greenhouse:           38 (avg 4.2 roles each)
  - Lever:                 9
  - Ashby:                12
  - Workday:               5
  - Custom HTML:           5
  - Failed:                0
Leads found (total):     287
  - high confidence:      94
  - medium:              141
  - low:                  52
Leads after dedup:       212
Leads matching filters:  118
Drafted this run:         42
Skipped (already on file): 76

=== Per-company breakdown ===
Anthropic (greenhouse:anthropic) — 12 leads, 3 new (drafted)
  - Senior Product Designer, Claude.ai (5223916008)              high   posted 12d ago
  - Design Engineer, Web (5223916008)                            high   posted  3d ago
  - Staff Product Designer, API Platform (5223916012)            medium posted 21d ago
  ...

=== Cross-cutting pass ===
Hits across all interested-company ATSes:  17
New leads after dedup against per-company sweep: 3
  - Linear (ashby:linear): Founding Brand Designer — missed by per-company crawl because it lives on a separate Ashby board

=== Stubs generated ===
(unchanged from current spec)

=== Identity / voice gaps ===
voice: 0 samples — synthesis quality degraded
identity: all 17 filled

=== Borderline leads worth a human eyeball ===
- Replicate (lever:replicate): "Lead Designer" — title pattern matches but JD reads more like a Brand role; flag if you want
...
```

## 6. Implementation plan (phases)

### Phase A — adapter library + frontmatter migration (1-2 sessions)

1. Write `.agents/skills/find-roles/scripts/` helpers:
   - `adapters/greenhouse.py` — single function `fetch(ats_slug) -> list[LeadRecord]`
   - `adapters/lever.py`
   - `adapters/ashby.py`
   - `adapters/workday.py`
   - `adapters/custom.py` (WebFetch wrapper with structured-extraction prompt)
   - `scripts/filters.py` — shared synonym list
   - `scripts/model.py` — dataclass + JSON serialization
2. Write a one-off migration script `scripts/backfill_ats_metadata.py` that walks `companies/interested/*.md`, detects ATS host from `careers_url:`, and writes `ats:` + `ats_slug:` back to the frontmatter. Idempotent; safe to re-run.
3. Update `SCHEMA.md` to document the new frontmatter fields.

### Phase B — skill prompt rewrite (1 session)

Update `SKILL.md`:
- Replace step 2 with the ATS-adapter dispatch table.
- Replace step 3 with the title-pattern + location-match + freshness filter spec.
- Insert §5.7 cross-cutting pass after step 3.
- Insert §5.8 confidence + cap rules in step 3.
- Insert §5.10 preflight checks before step 1.
- Insert parallelization instruction at the top of the workflow ("dispatch one subagent per company in parallel").
- Update §5.11 report shape.
- Leave steps 5-8 (answer-bank load, classify, gap-analysis, draft) unchanged.

### Phase C — voice-bank & ergonomic polish (optional, can wait)

- Add the `voice` warning to preflight.
- Add `max_roles_per_company` and `max_roles_total` config to preferences.md.
- Add `freshness_days` config.

### Phase D — discover-only flag (optional, v2.1)

- Wire `/find-roles --discover-only` to short-circuit after discovery, writing `applications/_leads.md` and skipping drafting.
- Wire `/find-roles --draft <leads-file>` to consume that leads file.

Phases C and D are nice-to-haves and can be deferred without blocking the main maximize-finding goal. Phases A + B together deliver ≥80% of the impact.

## 7. Migration

**Frontmatter backfill** — 69 companies, run once. Script reads each file's `careers_url:`, fetches it, detects the ATS host, and writes `ats:` + `ats_slug:` back. Companies without a `careers_url:` fall back to a brief WebSearch ("<company name> careers"). Companies that can't be resolved get `ats: custom`, `ats_slug: null` and are documented in a `migration-report.md` for the user to inspect manually.

**No data migration on the `applications/` side** — existing application files keep their current frontmatter; the new adapter layer is purely additive.

**Backward compatibility:** the skill still works on company files without the new fields. They get routed through the custom HTML adapter (slower but works). The migration just unlocks the fast path for known-ATS companies.

## 8. Open questions

1. **Per-ATS rate limits.** Greenhouse, Lever, Ashby are open and ungated in practice; Workday is more aggressive. Recommended: throttle Workday to 1 req/sec per tenant. Open: do we need persistent rate-limiting state across runs?

2. **Adapter language.** Python helpers vs pure-prompt with WebFetch + jq in Bash. Spec assumes Python because the JSON parsing + filtering logic gets verbose in shell. Question: any precedent for Python helpers in `.agents/skills/`? (Today there isn't — this would be the first.)

3. **Where do leads live during phase split?** If Phase D ships, leads go to `applications/_leads.md` (single file, gitignored, single source of truth between discovery and drafting). The underscore prefix keeps it out of the alphabetized `applications/` UI rendering. Open: better name? `applications/.leads.json`?

4. **Cross-cutting query budget.** Each `WebSearch` is a real cost. Recommended cap: 6 queries per cross-cutting pass. Open: should the cap be configurable?

5. **Stale `interested/` cleanup.** Some companies in `interested/` may be defunct or stopped hiring entirely. Out of scope for this spec, but worth a `/companystatus` skill in the future.

6. **Per-company role cap (§5.8) — surface vs reject.** With `max_roles_per_company: 8`, if Anthropic has 25 designer-adjacent roles, we surface 8 and drop 17. Spec calls for sorting the 25 by (confidence, freshness) and taking top 8. Open: should the dropped 17 still appear in the report as a one-line note?

7. **Apple's Workday tenant resolution.** Apple uses Workday but their public careers URL hides the tenant. Manual resolution (one-time) writes `ats_slug: apple/wd1/External` or whichever combo is correct. Spec recommends a manual entry for Apple specifically rather than auto-detection.

## 9. Out of scope

- Drafting / synthesis logic (steps 5-8 of current SKILL.md): unchanged.
- Voice answer-bank seeding: user task, not skill task.
- LinkedIn / Indeed / Wellfound primary integration: aggregators stay backup-only.
- A persistent jobs database / cron-watcher: every run is stateless.
- Salary negotiation logic, interview prep, follow-up nudges: separate skills.

## 10. Success criteria

When Phase A + B ship:

- A `/find-roles` run on the current 69-company `interested/` list surfaces **≥3x** the number of roles compared to the current skill, with no manual intervention.
- All four big-tech companies (Apple, Google, Meta, Microsoft) produce **at least one role each** on a typical run (today they likely produce zero).
- No designer-adjacent role posted in the last 30 days at a Greenhouse / Lever / Ashby `interested/` company is missed.
- Title-synonym coverage tested on at least the following actual postings and they all match: "Staff Product Designer," "Founding Designer," "UX Engineer," "Design Systems Engineer," "Senior IC, Design."
- Run wall-clock time stays under 5 minutes for 69 companies (parallel fan-out makes this trivial).
- Report explicitly lists per-company status; no silent failures.

---

# Part 2 — Role-First Discovery (v2)

**Status:** proposed
**Date:** 2026-05-22
**Supersedes from Part 1:** §4 architecture, §5.6 parallelization, §5.7 cross-cutting pass, §5.8 confidence + cap, §5.11 report shape, and the corresponding sections of `SKILL.md` workflow steps 2-3.
**Preserves from Part 1:** §5.1 frontmatter extension, §5.2 ATS adapters, §5.3 title patterns, §5.4 location matching, §5.5 freshness, §5.9 dedup hash, §5.10 preflight, all of `scripts/adapters/*.py`, `scripts/filters.py`, `scripts/filters.py`, `scripts/filters.py`, `scripts/model.py`, `scripts/find_roles.py` (used as Stream B in the new model).

## 11. Goal restatement

Maximize lead count by **inverting the discovery model**. Today the skill iterates over `companies/interested/` and pulls each board — a role only surfaces if its company was already on the list. The inversion: search ATS-wide for matching titles first, then enrich each hit with company info. `companies/interested/` becomes a *ranking signal* and a *completeness target*, not a *gate*.

## 12. User decisions (locked)

1. **Industry filter on unknown companies: lightweight inline lookup.** One `WebSearch` + one homepage fetch per unknown company, grepping for `industries_avoid` keywords. Drop hard matches, surface the rest.
2. **Auto-stub unknown companies** into `companies/in-review/<slug>.md` (frontmatter only, `discovered_via: find-roles`). Threads find-roles back into the user's `/find-companies` flow.
3. **Total leads cap: 80** per run.
4. **Keep the completeness sweep** of `interested/` boards in parallel with the title-wide search. Cheap (ATS APIs return all jobs in one call) and catches edge cases the title-search misses.

## 13. New architecture — three discovery streams

```
                          /find-roles
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   Stream A:             Stream B:              Stream C:
   Title-wide      Completeness sweep      YC firehose
   ATS search      of interested/         (workatastartup +
   (Greenhouse +   boards — v1 logic      yc-oss API, filtered
   Ashby + Lever   reused as-is via       to recent batches +
   `site:` queries) find_roles.py          hiring + title regex)
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              ▼
                    Unified LeadRecord stream
                              │
              ┌───────────────┼───────────────┐
              ▼                               ▼
      Per-lead enrichment              Per-lead routing:
      • industry hard filter           • interested/  → priority=known-good
        (only for unknowns)            • in-review/   → priority=in-review
      • location, freshness            • not-interested/ → drop
      • title scoring                  • applications/  → drop (dedup)
                                       • unknown      → priority=new-discovery
                                                       + auto-stub
                              ▼
              Sort by (priority, confidence, freshness)
              Apply per-priority caps → top 80
                              ▼
              Drafting phase (Part 1 §steps 4-8, unchanged)
                              ▼
                          Report
```

### 13.1 Stream A — Title-wide ATS search

The primary discovery vector. Issues `WebSearch` queries across each major ATS host with the user's title synonyms ORed together.

**Search matrix:** 4 hosts × 4 title-group queries = 16 `WebSearch` calls per run.

```python
# In the skill prompt; not Python lib
HOSTS = [
    "site:boards.greenhouse.io",
    "site:job-boards.greenhouse.io",
    "site:jobs.ashbyhq.com",
    "site:jobs.lever.co",
]
TITLE_GROUPS = [
    '("Senior Product Designer" OR "Sr Product Designer" OR "Sr. Product Designer")',
    '("Staff Product Designer" OR "Lead Product Designer" OR "Principal Product Designer" OR "Founding Designer")',
    '("Design Engineer" OR "UX Engineer" OR "Design Technologist" OR "Design Systems Engineer")',
    '("Brand Designer" OR "Motion Designer" OR "Visual Designer" OR "Product Design Lead")',
]
LOCATION_HINT = '("Remote" OR "United States" OR "San Francisco" OR "New York")'

# Total: 16 WebSearch calls. Each returns up to ~10 hits.
```

For each search hit, extract `(ats, ats_slug, ats_id, posting_url)` from the URL host+path. Convert each hit into a `LeadRecord` skeleton with `source: greenhouse|ashby|lever`. Then **batch-call the ATS adapters** (one per unique `(ats, ats_slug)`) to pull full structured data — title, location, posted_at, comp — for the matched roles only. The adapter calls dedupe naturally: hitting `boards-api.greenhouse.io/v1/boards/<slug>/jobs` once returns everything we need from that slug.

**Why two-pass (search → adapter) instead of trusting the search snippet:** the search snippet is unstructured and unreliable for location/comp/posted_at. The adapter call costs one HTTP request per unique slug (cheap) and returns canonical structured data we can filter against `scripts/filters.py` and `scripts/filters.py`.

### 13.2 Stream B — Completeness sweep of interested/

Unchanged from Part 1. Runs `find_roles.py --companies-dir companies/interested ...` in parallel with Streams A and C. Catches edge cases the title-wide search misses (e.g. a company whose careers page lives on a non-major ATS, mis-mapped slugs, weird title casing the search query didn't anticipate).

Companies in `interested/` that already produce hits in Stream A get deduped at the unified-stream merge step — they don't double-count.

### 13.3 Stream C — YC firehose

For YC startups not already on the user's `interested/` list:

1. Fetch `https://yc-oss.github.io/api/companies/all.json`.
2. Filter to `status: Active`, `isHiring: true`, and `batch in {W24, S24, F24, W25, S25, F25, X25, W26}` (last ~2 years).
3. For each surviving company, check if its slug is already in `companies/interested/`, `companies/in-review/`, `companies/not-interested/`, or `applications/*`. If so, skip (Stream B or dedup will handle it).
4. For each new candidate, fetch their careers page via the existing `scripts/adapters/custom_html.py` OR look them up on `workatastartup.com`. Extract role list, apply title patterns.

Cap Stream C at the top **40 YC companies** by `isHiring: true` + match against industry tags in `preferences.md.industries_want` (developer-tools, ai-ml, healthcare). Don't blow the budget on every YC company.

## 14. Enrichment + filter pipeline

Applied to the merged stream from A + B + C.

### 14.1 Dedup pass

For each LeadRecord, drop if:

- `(company_slug, ats_id)` already exists in any `applications/**/*.md`
- `posting_url` already exists in any `applications/**/*.md`
- `(company_slug, normalized_title, normalized_location)` content-hash already seen this run (cross-stream dedup)

### 14.2 Status routing (assigns `priority`)

```
company_slug in companies/interested/<slug>.md     → priority = "known-good"
company_slug in companies/in-review/<slug>.md      → priority = "in-review"
company_slug in companies/not-interested/<slug>.md → DROP (user already passed)
company_slug nowhere in companies/                  → priority = "new-discovery"
```

Priority is in the LeadRecord and used as the primary sort key (§14.5).

### 14.3 Hard industry filter (unknown companies only)

For each `new-discovery` lead, run a one-shot industry check before surfacing. Skip this for `known-good` and `in-review` (already vetted by `/find-companies`).

**Implementation (corrected after E6 smoke test):** spawn ONE subagent that takes the unknown-slug list and produces verdicts via LLM judgment, NOT regex. Concrete steps:

1. For each slug, issue ONE clean `WebSearch`: `"<company-name>" company what they do`. **Do NOT** issue queries that OR together blocker keywords (`"<co>" (defense OR weapons OR gambling OR ...)`); those queries return topical SEO noise that triggers regex false positives.
2. The subagent reads the search snippets and applies LLM judgment: a company is blocked only if its core product / customer base is defense or gambling. A SaaS tool with one defense customer = CLEAN. A company that builds weapons or runs a sportsbook = BLOCKED.
3. Subagent writes `.cache/find-roles/industry-output.json` shaped `{slug: {status: clean|blocked|skipped, reason, company_name}}`.
4. `enrich_leads.py --phase finalize` consumes this file directly. No regex pass needed.

**Why this changed from the original SPEC §14.3 design:** the E6 smoke test (2026-05-22) ran 21 unknown companies through the regex-based check using OR-keyword search queries. Result: 20/21 false positives. SEO-spam pages, defense-industry news roundups, and unrelated topical articles consistently mention "DoD" or "gambling" alongside random company names. Regex matching at this baseline produces an unusably high block rate. LLM judgment on clean-query snippets correctly returned 21 clean verdicts in the same test.

**`scripts/industry_check.py` is preserved as a fallback** for cases where the user provides a clean structured input (e.g. a curated review batch where searches were issued cleanly). It still implements the keyword-match logic from the original §14.3 spec; just don't feed it boilerplate-laden search results.

**Cache verdicts per slug for the run.** A slug surfaced N times in the stream gets one verdict.

Keyword list still lives in `preferences.md.find_roles.industry_check_blockers` (§16) and informs both LLM-judgment prompts (subagent reads the list to know what to look for) and the regex fallback. Defaults: `defense, weapons, DoD, military, lethal autonomous, autonomous weapons, gambling, casino, sportsbook, betting, surveillance contract`.

### 14.4 Standard filters (all leads)

- **Title match:** already filtered at Stream A search time; re-verified via `scripts/filters.classify_title()` after adapter enrichment. Cheap belt-and-suspenders.
- **Location:** `scripts/filters.location_matches()`. Drop international-only; accept any US + remote-US.
- **Freshness:** `scripts/filters.is_fresh()`. Default 90 days. Configurable via `preferences.md.find_roles.freshness_days`.

### 14.5 Sort and cap

**Sort key** (tuple, all DESC except where noted):

```python
(priority_rank, confidence_rank, -recency_days)
```

- `priority_rank`: `known-good=0, in-review=1, new-discovery=2` (lower = better)
- `confidence_rank`: `high=0, medium=1, low=2`
- `recency_days`: days since posting (negative because ASC = newest first)

**Per-priority caps** (configurable in `preferences.md`):

```yaml
find_roles:
  per_priority_caps:
    known-good: 30      # of the 80, up to 30 from interested/
    in-review: 10       # up to 10 from already-stubbed in-review
    new-discovery: 40   # remaining 40 slots for new discoveries
```

**Cascade rule:** if a bucket underfills, unused slots cascade down (known-good → in-review → new-discovery). Inverse cascade is also allowed: if new-discovery overflows but known-good underfills, the surplus is dropped (we don't backfill an upper bucket from new-discovery; that would dilute the priority signal).

**Total cap: 80.**

### 14.6 Auto-stub creation (new-discovery companies that survive cap)

For each `new-discovery` lead that survives §14.5's cap, ensure the company has a stub at `companies/in-review/<slug>.md`. If the file doesn't already exist:

```yaml
---
name: "<extracted from ATS posting page or guessed Title-Case from slug>"
slug: <slug>
industry: []
match_score: null
headcount: null
stage: null
valuation: null
hq: null
offices: []
remote_policy: null
careers_url: "<the ATS host root for this slug, e.g. https://job-boards.greenhouse.io/<slug>>"
ats: <greenhouse|ashby|lever|workable|workday>
ats_slug: <slug>
researched_on: <today>
not_interested_reason: null
discovered_via: find-roles
---
```

Body empty. Future runs of `/find-companies` (single-company mode via `/add-company` or batch mode) can flesh out the body.

The auto-stub is the connective tissue between `/find-roles` and `/find-companies` — without it, every run rediscovers the same unknown companies from scratch.

## 15. LeadRecord additions

Extend `scripts/model.py`:

```python
@dataclass
class LeadRecord:
    # ... existing fields ...
    priority: str = ""                # "known-good" | "in-review" | "new-discovery"
    company_name: str = ""             # extracted from posting page or stub Title-Case
    industry_check: str = ""           # "verified-clean" | "verified-blocked" | "skipped" | "n/a"
    industry_check_reason: str = ""    # human-readable, only set when "verified-blocked"
    stream: str = ""                   # "A" | "B" | "C" — for the per-stream report breakdown
```

Backward-compatible additions (defaults are empty strings, so existing JSON consumers don't break).

## 16. Configuration knobs

Add to `context/preferences.md` frontmatter (all optional, with documented defaults):

```yaml
find_roles:
  max_total: 80
  freshness_days: 90
  per_priority_caps:
    known-good: 30
    in-review: 10
    new-discovery: 40
  industry_check_blockers:
    - defense
    - weapons
    - DoD
    - military
    - lethal autonomous
    - autonomous weapons
    - gambling
    - casino
    - sportsbook
    - betting
    - surveillance contract
  search_titles_extra: []   # add extra title queries beyond the default 4 groups
```

If `find_roles:` is absent, all defaults apply. No migration needed on existing `preferences.md` files.

## 17. SCHEMA.md additions

Add one optional field to the Companies frontmatter table:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `discovered_via` | enum | no | `find-roles` \| `find-companies` \| `add-company` \| `manual`. Set on stub creation by the corresponding skill; never updated thereafter. |

Update the SQLite DDL accordingly:

```sql
ALTER TABLE companies ADD COLUMN discovered_via TEXT
  CHECK (discovered_via IN ('find-roles','find-companies','add-company','manual'));
```

## 18. Orchestration model

`/find-roles` is a hybrid: the skill prompt orchestrates Claude-tool calls (WebSearch, WebFetch); Python helpers do pure-data work (filtering, sorting, dedup, file I/O, ATS adapter calls).

**Why split:** WebSearch is a Claude tool — only callable from the skill prompt. Pure-data work is faster, more testable, and easier to debug as Python.

**Per-step ownership:**

| Step | Owner | Why |
|---|---|---|
| Preflight | Bash → `scripts/preflight.py` | pure data |
| Stream A search queries | Skill prompt | needs WebSearch |
| Stream A → adapter enrichment | Bash → `scripts/adapters/*.py` via new helper | pure HTTP |
| Stream B (sweep) | Bash → `scripts/find_roles.py` (existing) | pure HTTP |
| Stream C (YC firehose) | Bash → new `scripts/streams/yc.py` | pure HTTP |
| Merge + dedup | Bash → new `scripts/enrich_leads.py` | pure data |
| Industry check (unknowns) | Skill prompt | needs WebSearch + WebFetch |
| Status routing | Bash → `scripts/enrich_leads.py` | pure data |
| Sort + cap | Bash → `scripts/enrich_leads.py` | pure data |
| Auto-stub creation | Bash → new `scripts/auto_stub.py` | pure data |
| Drafting per lead | Skill prompt (existing steps 4-8) | needs WebFetch + Claude reasoning |
| Report | Skill prompt | user-facing |

The skill prompt's job is to be a thin orchestrator: issue tool calls, save intermediate JSON to `.cache/find-roles/`, invoke Python helpers, render the final report. (As implemented in F4, the per-step `/tmp/` JSON pipes between scripts have been collapsed into one in-process `scripts/pipeline.py` invoked twice — once for `discover` and once for `finalize`.)

## 19. Implementation plan (phases E1-E6)

### E1: Industry check library + protocol
- `scripts/industry_check.py` — pure-Python utilities: keyword list loader, response parser, per-run cache (filesystem-based at `.cache/find-roles/industry-cache.json`)
- Document the WebSearch-call protocol in `SKILL.md` (one search per unknown slug, batched 10 at a time in parallel)
- Test on 3-5 known companies (1 known defense like Anduril → blocked; 1 known clean like Anthropic → clean; 1 ambiguous)

### E2: Stream A search + adapter enrichment
- `scripts/streams/title_search.py` — takes a JSON file of search hits (URL strings), parses out `(host, ats, ats_slug, ats_id)`, deduplicates to unique slugs, calls the existing adapters for each slug, filters to roles whose `ats_id` is in the original hit set
- Document the 4×4 = 16 WebSearch call matrix in SKILL.md
- The skill prompt does the searches, writes hits to `.cache/find-roles/stream-a-hits.json`, then invokes `pipeline.py discover` (which calls `title_search.enrich` in-process)

### E3: Stream C — YC firehose
- `scripts/streams/yc.py` — fetches `yc-oss.github.io/api/companies/all.json`, filters by batch + hiring + industry tags, returns top-N company candidates
- For each candidate, attempt adapter resolution via slug-probe (reuse `backfill_ats_metadata.probe_by_slug`)
- For unresolved YC companies, skip in v2 (don't blow the budget on custom HTML fallback during Stream C; the user can manually triage later)

### E4: Unified enrichment + cap + auto-stub
- `scripts/enrich_leads.py` — takes JSON paths for {A, B, C, industry_check_results, dedup_paths}, emits final JSON with status routing + sort + per-priority caps applied
- `scripts/auto_stub.py` — takes a list of (slug, name, ats, ats_slug, careers_url) tuples + writes stubs to `companies/in-review/`
- Extend `LeadRecord` with the new fields from §15
- Add `discovered_via` field to SCHEMA.md and to backfill script's quote rules

### E5: SKILL.md rewrite — workflow steps 1-3
- Replace current Step 2 (single `find_roles.py` call) with the three-stream orchestration:
  - Step 2a: Stream A — issue 16 WebSearch calls in parallel
  - Step 2b: Stream B — invoke `find_roles.py` for `interested/` sweep
  - Step 2c: Stream C — invoke `streams/yc.py`
  - Step 2d: Merge streams via `pipeline.py discover` (in-process; no intermediate JSON files)
  - Step 2e: Run industry check for unknown companies (skill issues N more WebSearch calls)
  - Step 2f: Invoke `enrich_leads.py` to produce final 80
  - Step 2g: Invoke `auto_stub.py` to write company stubs
- Update Step 9 report to include per-priority + per-stream breakdowns
- Steps 4-8 (drafting + synthesis) unchanged

### E6: Smoke test + tuning
- End-to-end run on real data
- Expect ~80 leads vs today's 15
- Tune per-priority caps if known-good underfills consistently
- Document any companies that get auto-stubbed but shouldn't have

**Phase E1-E6 sequencing:** E1 → E2 → E3 in parallel after E1; E4 sequentially; E5 sequentially; E6 final. Estimated 4-6 focused sessions.

## 20. Out of scope (explicitly deferred)

- **LinkedIn / Indeed integration** — both gate against scraping and the existing 3-ATS coverage plus YC is enough for v2. Revisit if user reports specific gaps.
- **Wellfound / Workatastartup direct adapters** — workatastartup is touched lightly in Stream C; a full adapter can wait for v3.
- **Per-role JD verbatim fetch in discovery** — drafting phase already does this for each surviving lead. Don't duplicate at discovery.
- **Multi-user / multi-profile support** — single user, single `preferences.md`.
- **Persistent cross-run cache** — industry check cache is per-run only. Adding a longer-lived cache invites stale-data bugs.
- **Salary negotiation, comp ranking** — flag salaries below floor; no further logic.
- **Re-running industry check on `interested/` companies** — assume `/find-companies` did its job. If the user wants paranoid re-validation, that's a separate skill.

## 21. Success criteria

When Phases E1-E5 ship:

- A `/find-roles` run surfaces **≥50 leads on average** (vs Part 1's 15 baseline), with ≥20 from new-discovery companies the user hasn't researched yet.
- Industry hard filter catches **≥95% of defense/gambling false-positives** on a labeled smoke set of 20 companies (10 known-clean, 10 known-blocked).
- Auto-stubbed `companies/in-review/<slug>.md` files pass `SCHEMA.md` validation and are picked up correctly by future `/find-companies` runs.
- Stream A adds **at least 30%** of total leads (i.e. v2 isn't just v1 + YC; the title-wide search is the load-bearing surface).
- Wall-clock under **8 minutes** for a typical run (16 WebSearch + ~30 unknown-company industry checks + 68 sweep companies + ~40 YC candidates).
- `companies/interested/` underfill (fewer than 30 leads from there) triggers cascade to fill the remaining slots; no run ever returns fewer than 50 leads when there are leads available.

## 22. Open questions still on the table

These can be decided during implementation:

1. **Stream A title-group rotation.** If 16 fixed queries underperform (e.g. always returns the same 30 companies), should we rotate through different title groupings per run? Decide after E2 ships and we see real query results.
2. **Industry check granularity.** Should we also flag companies whose *primary* customers are in `industries_avoid`, even if the company itself doesn't make weapons? E.g. a SaaS for ammunition logistics. Default to *no* (too noisy); revisit if user reports specific bad surfaces.
3. **Auto-stub naming.** When extracting `name:` from posting page fails, fall back to Title-Casing the slug? Or leave `name: ""` and let `/find-companies` fill? Default: Title-Case the slug as a reasonable guess.
4. **Multi-region splitting.** Some companies (e.g. Stripe) have separate boards per region. Right now we treat each board as a separate slug. Acceptable for v2; revisit if it produces obvious duplicates.

---

# Part 3 — Role config decoupling

**Status:** proposed
**Date:** 2026-05-22
**Affected files:** `.agents/skills/find-roles/scripts/filters.py`, `.agents/skills/find-roles/SKILL.md` (step 2a query list), `.agents/skills/onboard/SKILL.md` (role section), `context/preferences.md` (new fields), `context/preferences.example.md`, `web/src/lib/preferences-shape.ts` (Preferences type + defaults), `web/src/lib/preferences.ts` (body renderer).
**Preserves:** all of Part 1 + Part 2; the only break is moving title patterns from compile-time constants to runtime config.

## 23. Problem

Title-matching patterns and WebSearch query strings are hardcoded in the skill, not driven by `preferences.md`. Concrete evidence:

- `scripts/filters.py` defines `TITLE_PATTERNS` and `TITLE_EXCLUDE` as compile-time constants — `\b(senior|sr\.?)\s+product\s+designer\b` literal, plus 14 designer-family synonyms and 12 exclusion patterns.
- `SKILL.md` step 2a lists 16 literal WebSearch query strings with `"Senior Product Designer"`, `"Design Engineer"`, etc. baked in as text.

Meanwhile `preferences.md` has `role.titles: [Senior Product Designer, Design Engineer]`, `role.specialties: [...]`, and `role.track: IC` — and the skill ignores all three at filter time.

Result: if the user changes preferences (e.g. shifts to "Engineering Manager" or "Brand Designer only"), the skill silently keeps surfacing designer-family roles. The skill is currently coupled to one role family by accident of how it was written, not by design.

## 24. Goal

Derive both the regex title patterns AND the WebSearch query list from `preferences.md` at runtime. The skill should follow whatever `role.titles`, `role.specialties`, and `role.exclude_titles` say, with sensible auto-expansion of common level synonyms.

Non-goal: making the skill work for every conceivable role family. The user can still hit unsupported corners (e.g. very niche titles); the skill should fail safely (low confidence) rather than silently wrong.

## 25. New `preferences.md` fields

Add two optional fields under `role:`:

```yaml
role:
  titles:                          # already exists
    - Senior Product Designer
    - Design Engineer
  track: IC                         # already exists (IC | Management)
  specialties:                      # already exists
    - Product/UX
    - Visual/Brand
    - Design systems
    - Prototyping/motion
  exclude_titles: []                # NEW — titles to NEVER surface, even if a regex matches
  title_synonyms: {}                # NEW — optional explicit synonym map; defaults via auto-expansion
```

`exclude_titles` is a flat list of role-name strings. Each becomes a case-insensitive substring exclude — e.g. `["Engineering Manager", "Game Designer"]` rejects any title containing those phrases.

`title_synonyms` is a `{title: [synonyms...]}` map for cases where auto-expansion isn't enough. Most users won't need it; the default expansion (§27) covers level prefixes and common variants.

Both default to empty (`[]` / `{}`). Backwards compatible — existing `preferences.md` files keep working.

## 26. New `scripts/role_config.py` module

```python
# scripts/role_config.py

@dataclass(frozen=True)
class RoleConfig:
    titles: list[str]                         # ["Senior Product Designer", "Design Engineer"]
    specialties: list[str]                    # ["Product/UX", "Visual/Brand", ...]
    track: str                                # "IC" | "Management"
    exclude_titles: list[str]                 # ["Engineering Manager", ...]
    title_synonyms: dict[str, list[str]]      # {"Design Engineer": ["UX Engineer", ...]}

    @classmethod
    def from_preferences(cls, path: str = "context/preferences.md") -> "RoleConfig":
        """Parse preferences.md frontmatter, return RoleConfig."""

    def title_patterns(self) -> list[tuple[re.Pattern, str]]:
        """Generate (regex, confidence) pairs from titles + synonyms + specialties.

        Auto-expansion rules per title:
        - "Senior X" → matches "Senior|Sr|Sr." prefix forms
        - "Staff X" → adds Staff/Lead/Principal as siblings
        - Bare "X" → adds Founding/Junior/Mid variants at lower confidence
        - Confidence: exact-title-match=high, level-variant=medium, specialty-prefix=low

        Plus any explicit synonyms from title_synonyms.
        """

    def exclude_patterns(self) -> list[re.Pattern]:
        """Generate exclude regexes from exclude_titles + track-derived defaults.

        track == "IC"          → adds manager/director/VP/Head excludes
        track == "Management"  → adds the inverse (excludes IC-only titles like "Designer (IC)")

        Plus universal excludes (recruiter, sourcer, sales engineer) regardless of track.
        """

    def search_queries(self, hosts: list[str] = None) -> list[str]:
        """Generate the WebSearch query list for Stream A.

        Default hosts: greenhouse (×2 subdomains), ashby, lever. Override for testing.

        Groups titles into ~4 batches of synonyms ORed together, multiplied by hosts.
        Default: 4 hosts × ceil(len(titles) / 1) groups = ~16 queries, same as today
        but derived not hardcoded.
        """
```

## 27. Auto-expansion rules

For each entry in `role.titles`, the module auto-generates level-prefix variants without the user listing them:

| User entry | Auto-expanded variants | Confidence |
|---|---|---|
| "Senior Product Designer" | `Senior|Sr\.?` + `Product Designer` | high |
| "Senior Product Designer" | `Staff|Lead|Principal|Founding` + `Product Designer` | medium |
| "Senior Product Designer" | bare `Product Designer` (no level) | low |
| "Design Engineer" | `(Senior|Staff|Lead|Principal|Founding)? Design Engineer` | high |
| "Design Engineer" | `UX Engineer`, `Design Technologist`, `Design Systems Engineer` | high (from `title_synonyms` if listed; otherwise medium) |
| "Engineering Manager" (hypothetical) | `(Senior|Staff)? Engineering Manager` | high |
| "Engineering Manager" | `EM`, `Eng Manager` | medium (if user doesn't override via synonyms) |

The auto-expansion is conservative: it only adds variants that are obviously the same role at a different seniority. It does NOT auto-add cross-role synonyms — that requires explicit `title_synonyms` entries.

For `role.specialties`, the module generates lower-confidence patterns:
- `"Visual/Brand"` → matches `(Senior|Staff|Lead)? (Visual|Brand) Designer` at medium confidence
- `"Design systems"` → matches `Design Systems (Designer|Engineer)` at high confidence
- `"Prototyping/motion"` → matches `(Senior|Staff)? Motion Designer` at medium confidence

If a specialty doesn't pattern-match cleanly (e.g. `"Product/UX"`), it's used as a tiebreaker in the company-profile match, not in title filtering.

## 28. Track-driven excludes

Universal excludes (always applied, regardless of track):
- recruiter, sourcer, talent partner
- sales engineer
- "Apply now" / "Open application" boilerplate titles

Conditional excludes — only when `track == "IC"`:
- manager, director, head of, VP, vice president, chief
- "Design Manager", "Design Director" (these are management roles)

Conditional excludes — only when `track == "Management"`:
- "Designer (IC)", "Senior Designer IC", "IC track" qualifiers (if a posting explicitly marks IC, it's not a fit for a management seeker)

Plus everything in `role.exclude_titles` — user-explicit overrides applied as case-insensitive substring matches.

## 29. SKILL.md changes (step 2a)

Replace the 16 literal query strings with a derivation:

> Issue the 16 `WebSearch` calls listed by `python3 .agents/skills/find-roles/scripts/role_config.py --print-queries`. Output is one URL-encoded query per line, ready to feed each to `WebSearch` in parallel.

Add a CLI mode to `role_config.py` so the skill prompt can preview the queries without running the full pipeline:

```bash
$ python3 scripts/role_config.py --print-queries
site:boards.greenhouse.io ("Senior Product Designer" OR "Sr Product Designer" OR "Sr. Product Designer") (Remote OR "United States")
site:boards.greenhouse.io ("Staff Product Designer" OR "Lead Product Designer" ...) ...
...
```

This is a one-line change in `SKILL.md` (lines ~55-75 collapse to "run this command") but it's the load-bearing decoupling — the skill no longer carries role-specific query text.

## 30. Implementation plan (phases G1-G6)

### G1: Write this spec (this section)
Done as part of writing this Part 3.

### G2: Add `exclude_titles` to the schema right now
Add `exclude_titles: string[]` (and skip `title_synonyms` for now) to:
- `web/src/lib/preferences-shape.ts` (`Preferences.role` + `DEFAULT_PREFERENCES.role`)
- `web/src/lib/preferences.ts` `renderPreferencesMarkdown` (one new bullet in the Role section)
- `context/preferences.md` (the user's actual file — add the field, default `[]`)
- `context/preferences.example.md` (template the onboard skill copies)

This is the immediate small change. It puts the field in place without requiring the full `role_config.py` refactor. The skill still uses hardcoded patterns until G4 ships; `exclude_titles` just sits there as data until then.

### G3: Add the onboard question
Update `.agents/skills/onboard/SKILL.md`:
- Add `exclude_titles: string[]` to the schema reference (around line 90)
- Add an onboarding question under the Role section ("Any role titles you want to NEVER surface? — Engineering Manager, Game Designer, etc.")
- Update the body template to render the new field

### G4: Build `scripts/role_config.py`
Per §26. New module, ~150 LOC, no deps. Includes `--print-queries` CLI mode.

### G5: Refactor `scripts/filters.py` to consume `RoleConfig`
- `classify_title(title, config)` accepts a `RoleConfig` parameter
- `_COMPILED_PATTERNS` / `_COMPILED_EXCLUDES` become per-instance, derived once per run
- Backwards-compat shim: `classify_title(title)` with no config uses a hardcoded `RoleConfig` matching today's behavior (so existing callers don't break during transition)

### G6: Add `title_synonyms` field
After G2-G5 ships and we see how often the auto-expansion fails. If `exclude_titles` covers 95% of real cases (likely), `title_synonyms` can stay deferred.

### G7: Update SKILL.md step 2a
Replace the 16 literal queries with the `--print-queries` invocation.

**Sequencing:** G2 + G3 are immediate (small footprint, no skill behavior change). G4-G7 are the actual decoupling work — bigger refactor, defer until G2-G3 ship.

## 31. Out of scope

- **Generic "any job" support.** This is a designer/IC-track tool by current preferences. The decoupling makes it follow preferences, not become role-agnostic across the entire labor market. The auto-expansion rules in §27 are designer-tuned defaults.
- **Cross-role-family search.** If you want to look for both designer roles AND PM roles in the same run, you'd need a more elaborate config. Defer.
- **Per-stream config.** All three streams (A/B/C) use the same `RoleConfig`. No per-stream overrides.

## 32. Success criteria

**G2-G3 shipped (2026-05-22):**
- `preferences.md` has `role.exclude_titles: []` and `role.title_synonyms: {}` as typed fields. ✓
- `web/src/lib/preferences-shape.ts` Preferences type extended; dashboard form will surface both fields. ✓
- `/onboard` asks about both fields during first-run. ✓

**G4-G7 shipped (2026-05-22):**
- `scripts/role_config.py` is the single source of truth for title patterns + excludes + WebSearch queries — ~370 LOC, stdlib only. ✓
- `scripts/filters.py` has zero hardcoded title-family strings; `classify_title` accepts an optional `RoleConfig` (defaults to one loaded from `preferences.md`). ✓
- `SKILL.md` step 2a derives queries via `python3 scripts/role_config.py --print-queries` — no literal queries in the skill prompt. ✓
- Auto-expansion rules implemented: `Senior X` → `Senior|Sr|Sr.` variants high-confidence + Staff/Lead/Principal/Founding medium; bare titles match all levels. ✓
- Track-driven excludes: IC excludes manager/director/VP; Management excludes `(IC)` / "individual contributor" qualifiers. ✓
- Universal + designer-family excludes preserved (recruiter, sales engineer, hardware/game, etc.). ✓
- Changing `preferences.md.role.titles` causes the next `/find-roles` run to follow the new pattern set (verified via test `role_config:management-track-excludes-IC`). ✓
- Smoke test suite extended from 36 → 57 tests; all pass. ✓
- End-to-end pipeline run produces same lead-count behavior as pre-refactor (15 known-good leads, no regression). ✓

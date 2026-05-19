---
name: find-roles
description: Find matching open roles at the user's interested companies and draft an application markdown file for each match under applications/in-review/. Use whenever the user wants to look for new jobs, scan their interested companies, or fill their applications pipeline. Reads companies from companies/interested/, fetches each careers page, filters open roles against context/preferences.md, dedupes against every existing application under applications/**/*.md (any status), and writes one markdown file per match — pre-filling form questions by reusing entries from answer-bank/ where they exist. Never submits applications.
---

# Find Roles

Find open roles at the companies the user is already interested in, then draft an application markdown file for each match under `applications/in-review/`. The user reviews and submits manually — this skill never submits.

The full schema is in `SCHEMA.md` at the repo root.

## Prerequisites

The `companies/`, `applications/`, and `answer-bank/` folders exist. `SCHEMA.md` exists at the repo root. `context/preferences.md` and `context/index.md` exist.

## Inputs

Load context in this order:

1. **`context/preferences.md`** — required filter. Defines target titles, comp floor, location, industries, must-avoid culture/ethics constraints. Treat the avoid list as a hard filter.
2. **`context/index.md`** — entry point. Follow its links to project folders, the resume, personal site, and any other supporting material.
3. **`context/resume.pdf`** — read for concrete experience to draw on when drafting.
4. **`companies/interested/*.md`** — every file under here is a company to scan. For each one, read the frontmatter (name, slug, industry, etc.) and the body (profile) for context. The slug = the filename without `.md`.

If `context/preferences.md` or `context/index.md` is missing, stop.

## Workflow

For each company file under `companies/interested/`:

### 1. Build the dedup set

Before fetching anything, walk every existing application across **all** status folders for this company:

```bash
ls applications/*/<company-slug>/*.md 2>/dev/null
```

For each existing file, grep out the `url:` and `ats_id:` values from the frontmatter. Collect them into a set. Any posting matching one of these is already on file and must be skipped. **Crucially: don't re-surface roles you were rejected from, withdrew from, or marked not interested**, so the skip applies across all seven status folders, not just `applied/` and `in-review/`.

### 2. Locate the careers page

Check the company's profile body (`companies/interested/<slug>.md`) for an explicit careers URL first — usually under the `## Open roles` heading. If none, use WebSearch to find the official careers/jobs page (Greenhouse, Lever, Ashby, Workday, or in-house). Prefer the canonical job board over aggregators (LinkedIn, Indeed) — the canonical board has the real ATS IDs and application questions.

### 3. Pull open roles and filter

Fetch the listing index. For each role, decide match vs. no-match against `preferences.md`:

- **Title** — match the role to the titles/levels listed in `preferences.md`. Reject obvious mismatches outside the user's domain.
- **Location** — must be compatible with the locations/remote policy in `preferences.md`.
- **Comp** — if the posting lists comp, enforce any salary/total-comp floor. If not listed, don't reject on that alone; flag it in the body.
- **Industry / culture** — apply the avoid list strictly. Hard filter, not tiebreaker.
- **Tech stack** — prefer roles using stacks the user wants; deprioritize avoided stacks but don't auto-reject unless marked hard-avoid.

Be selective. A handful of strong matches beats a dump of weak ones.

### 4. For each match, fetch the actual posting

Open the role's individual page. Extract:

- Canonical job title and ATS ID (the numeric/slug ID in the URL).
- Source (which ATS — used to populate the `source` frontmatter field).
- **The complete JD — every section the posting contains, verbatim.** Do NOT summarize, do NOT trim to "the important parts." Capture all of it so the user has the full context for later reference. Specifically: the intro / role overview, the "About the company" or "About the team" paragraphs, the FULL "Responsibilities" / "What you'll do" list, the FULL "Requirements" / "What we're looking for" list (including bonus / nice-to-have items), all compensation / salary / equity / benefits details as written, location and work-arrangement details, interview process if mentioned, perks, application instructions, and any EEO / accessibility note. Preserve the original section structure (H3 subsections). Lists stay as lists. The only things you can drop are nav chrome, footer links, the "Apply now" button label, and pure visual elements (images, icons without alt text). If the posting is gated or rendered client-side and you only have a partial fetch, capture what you have and note the gap explicitly — don't substitute with a summary.

  When the fetch tool you have (WebFetch, browser, or other) accepts a prompt, give it the instruction: "Return the COMPLETE job description verbatim, preserving section headings and lists. Do not summarize."
- **The application form's questions.** Look for ALL of these:
  - **Personal info fields** — legal name, preferred name, name pronunciation, pronouns, phone, email, current city/state, country, work authorization, visa sponsorship requirement.
  - **Professional links** — LinkedIn, GitHub, portfolio, X/Twitter.
  - **Essay / free-text questions** — cover letter, "why this company", "why this role", "tell us about a project", "design process", etc.
  - **Logistics** — earliest start date, relocation openness, referrals, prior compensation.
  - **Demographic** — pronouns, gender, ethnicity, veteran status (always TODO — user fills in directly).

If you can't reach the application form (gated behind login), note that in the resulting file and draft only the cover letter — don't fabricate questions.

### 5. Load the Answer Bank as raw material

The Answer Bank now stores **portable raw material**, not finished answers. Six themes:

- **`identity`** — hard facts (name, email, phone, links, visa, location, start date, relocation, salary floor, demographic). Used verbatim.
- **`beliefs`** — stable views about how the user works, what they value (e.g. "How I think about AI in products", "What kind of company culture energizes me"). Used as substrate for essay synthesis.
- **`stories`** — specific S-A-O anecdotes from the user's career, tagged by what they illustrate (`leadership`, `conflict`, `0-to-1`, `scale`, `ambiguity`, `design-systems`, `ai-trust`, etc.). Used as concrete material in essay answers.
- **`career`** — past role annotations, what's next, where heading, companies admired, hard nos.
- **`skills`** — technical stack with comfort levels, daily tools, languages, public artifacts.
- **`voice`** — writing samples for tone-matching, do-say / don't-say lists.

Read every file under each theme into memory. Parse `question`, `tags`, and body. Build two parallel structures per theme — **filled** entries (non-empty body, eligible for synthesis) and **stubs** (frontmatter set, empty body — known gaps already on file from past runs, not eligible for synthesis but also not new gaps that need a freshly-generated stub):

- `identity_lookup`: a Map of `question` (case-insensitive) → body, **filled entries only**
- `identity_stubs`: a Set of `question` (case-insensitive), **stubs only**
- `beliefs`, `stories`, `career`, `skills`, `voice`: lists of `{ slug, question, tags, body }`, **filled entries only**
- `beliefs_stubs`, `stories_stubs`, `career_stubs`, `skills_stubs`, `voice_stubs`: same shape, **stubs only**

Stub detection: a file's body is empty if, after trimming leading/trailing whitespace, the result is the empty string. Frontmatter-only files and files containing only blank lines both count as stubs.

### 6. Classify each form question

For each application form question:

**a) Identity / logistics questions** — paste from `identity_lookup` verbatim.

Form-field → identity-question mapping (case-insensitive, fuzzy):
- Legal name / full name → `Legal name`
- Preferred name → `Preferred name`
- Name pronunciation / how do you pronounce → `Name pronunciation`
- Pronouns → `Pronouns`
- Email → `Email address`
- Phone → `Phone number`
- City / state → `Current city / state`
- Country → `Country of residence`
- LinkedIn → `LinkedIn URL`
- GitHub → `GitHub URL`
- Portfolio → `Portfolio URL`
- X / Twitter → `X / Twitter URL`
- Work authorization → `Work authorization status`
- Visa sponsorship → `Visa sponsorship requirement`
- Earliest start date / availability → `Earliest start date`
- Open to office / relocation → `Relocation openness` (file `relocation.md`)
- Demographic (gender / ethnicity / veteran status / disability) → leave as `TODO: user fills in directly` (never auto-fill)

For identity matches: paste the body verbatim. No contextualization. If the matched file's body is empty, write `TODO: fill in answer-bank/identity/<slug>.md` and flag it in the report. If no match, write `TODO: <field>` and suggest the user add it.

**b) Essay questions** — classify against the essay-pattern table in `SCHEMA.md` under "How AI uses each theme (fine-grained input requirements)". That table is the single source of truth for which inputs each pattern needs. Record the pattern name for each essay question so step 7 can walk its checklist.

If the question doesn't match any of the listed patterns cleanly, pick the closest match and note the mismatch in the report. Do not invent new patterns inline; if a pattern is genuinely missing, surface it so SCHEMA.md can be extended.

**c) Demographic questions** (gender, ethnicity, veteran status, disability) — always leave as `TODO: user fills in directly`. Skip step 7 for these — never auto-fill, never generate stubs.

**Ranking `stories` when multiple satisfy a checklist input:**
1. Tag overlap with the requested pattern (e.g. for "challenging project": prefer `0-to-1` > `scale` > `ambiguity` matches).
2. Tag overlap with the company's `industry` field (e.g. `b2b` for a B2B company).

Take the top 1–2 candidates per essay.

**d) Always anchor to context** — `context/preferences.md`, `context/index.md`, `context/resume.pdf`. The Answer Bank is the user's voice; `context/` is their factual ground truth.

### 7. Gap analysis and stub generation

For each essay question classified in step 6b, walk its input checklist from `SCHEMA.md`:

1. For each required input (e.g. *"`beliefs` entry tagged `mission-fit`"*):
   - Scan the in-memory filled-entries structure for that theme. A filled entry **satisfies** the input if its `tags:` list contains the required tag (or the body intersects the JD when the requirement is e.g. "≥1 `skills` entry whose body intersects the JD's Requirements").
   - If no filled entry matches but a stub does (same tag, empty body), mark the input **pending** — a stub from a prior run is already on file. Do NOT generate a new stub.
   - Otherwise mark the input **gap**.
2. For each **gap**, generate exactly one **generic, portable context-gathering question** that, once answered, would unblock this and similar future essay questions. Hard rules on the generated question text:
   - **Generic.** No company name, no role title, no JD-specific phrasing. "What kinds of missions feel meaningful to you?" YES. "Why do you want to join Anthropic?" NO.
   - **Decomposed.** The question targets the underlying belief / story / skill / career fact, not the application question. The application question lives in the application file; the answer-bank entry is the upstream input that feeds many applications.
   - **Reusable.** Phrased so the same answer serves many future essays. "Describe a time you navigated a 0-to-1 launch with no precedent" beats "Tell me about an ambiguous launch at Stripe."
   - **Specific enough to answer.** Not so abstract that the user can't picture what to say. "What gives you a sense of purpose at work?" is answerable; "What do you think about work?" is not.
3. **Consult the canonical stub catalog first (next section, "Canonical stubs").** If the gap matches a catalog row — by concept, not by exact phrasing — use that row's `slug`, `question`, and `tags` verbatim. Do NOT invent a new slug. This is the primary defense against duplicates: every subagent that hits "what city do you live in" must converge on `identity/location.md`, not invent `state-residence.md` or `intended-work-location.md` in parallel.
4. Only if the gap is genuinely outside the catalog: fuzzy-check against every existing `answer-bank/<theme>/*.md` file (filled or stub) and skip if a match exists:
   - If a file's `question:` shares ≥60% normalized token overlap, skip — treat the existing file as the pending stub for this gap.
   - If a file's `tags:` is a superset of the required tag plus any 1–2 of your proposed keyword tags, skip.
   - If the gap is *semantically* the same as an existing file's question (same underlying concept, even with low token overlap — e.g. "what state do you live in?" vs "what city are you based in?"), skip. Use judgment, not just token overlap.
   - Track skipped duplicates for the end-of-run report.
5. For each surviving generated question, write a stub at `answer-bank/<theme>/<slug>.md`:
   ```yaml
   ---
   question: "<the generic question, verbatim>"
   tags: [<the required tag from the checklist, plus 1–3 keyword tags>]
   variant_of: null
   ---
   ```
   Body **empty** — frontmatter then end-of-file. No placeholder text, no whitespace lines.

   `slug` = the catalog slug if applicable; otherwise lowercased question text, alphanumerics + hyphens only, ~50 chars max. On collision, append `-2`, `-3`, etc.

#### Canonical stubs

Use these slugs and questions verbatim whenever a gap maps to a row below. The "Form aliases" column lists common form-field phrasings that all map to the same canonical stub — when you see any of them in an application form, do NOT mint a new stub, write a TODO that references the canonical slug.

**Identity** (one entry per logical field, all in `answer-bank/identity/`):

| Slug | Canonical question | Form aliases that map here |
| --- | --- | --- |
| `legal-name` | What is your full legal name? | full name, legal name, name on government ID |
| `preferred-name` | What name do you go by professionally? | preferred name, nickname, what should we call you |
| `pronouns` | What are your pronouns? | pronouns |
| `email` | What email address should employers use to contact you? | email, contact email |
| `phone` | What phone number should employers use to contact you? | phone, mobile, contact number |
| `location` | What city and country are you currently based in? | city, state, country, residence, current location, where are you based |
| `linkedin` | What is the URL of your LinkedIn profile? | LinkedIn, LinkedIn URL, LinkedIn profile |
| `github` | What is the URL of your GitHub profile? | GitHub, GitHub URL |
| `twitter` | What is the URL of your X / Twitter profile? | Twitter, X, X / Twitter URL |
| `portfolio` | What is the URL of your portfolio or personal website? | portfolio, personal site, website, personal website |
| `work-authorization` | Are you legally authorized to work in the country where this role is based? | work authorization, eligible to work, authorized to work in [country], US work authorization |
| `visa-sponsorship` | Do you now or will you in the future require visa sponsorship to work in this country? | visa sponsorship, immigration sponsorship, will you need sponsorship |
| `start-date` | When could you start a new role? | earliest start date, availability, when can you start |
| `relocation-openness` | Are you open to relocating for this role? | relocation, willing to relocate, open to relocation |
| `hybrid-onsite-availability` | Are you able to work from a company office on a hybrid or on-site schedule? | hybrid, on-site availability, in-office, RTO |
| `referral-source` | How did you hear about this role? | referral source, how did you hear, referred by |
| `prior-employer-history` | Have you previously worked at or interviewed with this company? | prior employment, previously interviewed, prior contact (generic — answer applies across all companies) |

Demographic fields (gender, ethnicity, veteran status, disability) **never** get a stub. Always emit `TODO: user fills in directly` in the application file.

**Beliefs** (one entry per essay-pattern tag, all in `answer-bank/beliefs/`):

| Slug | Canonical question | Primary tag |
| --- | --- | --- |
| `mission-fit` | What kinds of company missions feel meaningful to you, and why? | `mission-fit` |
| `culture-fit` | What kinds of cultures have you thrived in vs. burned out in? | `culture-fit` |
| `ethics-line` | What ethical lines would you not cross for a job, and why? | `ethics-line` |
| `good-design` | What makes design "good" to you? | `good-design` |
| `ai-in-products` | How do you think about AI in the products you use and build? | `ai-in-products` |
| `handling-ambiguity` | How do you operate when the problem isn't clearly defined? | `handling-ambiguity` |
| `collaboration` | How do you collaborate with engineers, PMs, and other designers? | `collaboration` |
| `disagreement` | How do you handle disagreement with a colleague or leader? | `disagreement` |

**Career** (all in `answer-bank/career/`):

| Slug | Canonical question | Primary tag |
| --- | --- | --- |
| `what-i-want-next` | What do you want in your next role that you don't have today? | `what-i-want-next` |
| `companies-admired` | Which companies do you admire, and what specifically about them? | `companies-admired` |

**Stories** (one entry per S-A-O tag, all in `answer-bank/stories/`):

| Slug | Canonical question | Primary tag |
| --- | --- | --- |
| `0-to-1` | Describe a time you navigated a 0-to-1 launch with no precedent. | `0-to-1` |
| `leadership` | Describe a time you led without authority. | `leadership` |
| `conflict` | Describe a time you had significant disagreement with a teammate and how you handled it. | `conflict` |
| `design-systems` | Describe a design system you built or significantly contributed to. | `design-systems` |
| `ai-trust` | Describe a time you designed for AI transparency, trust, or user agency. | `ai-trust` |
| `ambiguity` | Describe a time you operated under significant ambiguity. | `ambiguity` |
| `scale` | Describe a time you designed for a product at significant scale. | `scale` |
| `technical-depth` | Describe a time your technical depth changed the outcome of a design decision. | `technical-depth` |

**Skills** (all in `answer-bank/skills/`):

| Slug | Canonical question | Primary tag |
| --- | --- | --- |
| `daily-tools` | What tools do you reach for every day, and what comfort level do you have with each? | `daily-tools` |
| `soft-skills` | What soft skills do colleagues say make you effective? | `soft-skills` |

When you encounter a gap that maps to a catalog row, the file content is fully prescribed: slug, question, and the primary tag from the table. You may add 1-3 keyword tags after the primary tag if useful, but the primary tag must come first. The body is always empty (this is a stub).
6. Record per-essay results so step 8 knows whether each input is **satisfied**, **pending** (stub on file from prior run), or **just-stubbed** (gap freshly stubbed this run). Pending and just-stubbed are both unsatisfied for the purposes of synthesis.

### 8. Draft the application

Decide the filename slug: take the job title, lowercase, strip punctuation, replace whitespace with `-`, limit to ~60 chars. Concat with the ATS ID: `<ats-id>-<title-slug>.md`.

Write the file to `applications/in-review/<company-slug>/<ats-id>-<title-slug>.md` with frontmatter per `SCHEMA.md`:

```yaml
---
title: "<exact job title from posting>"
company: <company-slug>
ats_id: "<ATS ID>"
url: "<canonical posting URL>"
source: <greenhouse|lever|ashby|workday|careers-page|other>
date_found: <today YYYY-MM-DD>
salary_min: <integer or null>
salary_max: <integer or null>
location: "<as stated in posting or null>"
notes: ""
---
```

Body has two top-level sections: `## Job description` (verbatim posting content), then `## Application form responses` (the form's questions and answers). The wrapper H2 between them is required — the web UI splits on it to put JD content in the JD tab and form questions in the Answers tab.

- **First** emit `## Job description`, followed by the **full** JD content scraped from the posting URL. Capture the entire posting as-is so the user has every piece of context they might want to reference later:
  - The role overview / team summary (intro paragraphs).
  - The "About the company" or "About the team" section if present.
  - The complete "Responsibilities" / "What you'll do" list.
  - The complete "Requirements" / "What we're looking for" list (including bonus / nice-to-have items).
  - Compensation, salary range, equity, and benefits as listed.
  - Location, work arrangement, time zones.
  - Anything else the posting includes (interview process, perks, application instructions, EEO note).
  - Cite the source URL at the very end (e.g. `Source: <url>`).
- Preserve the original structure with H3 subsections where the posting uses them. Lists stay as lists.
- The only things you should drop: navigation chrome, footer links, "Apply now" buttons, and visual elements that aren't textual context.
- **Then** emit `## Application form responses` (literally — this exact heading), and for each application form question emit a `### <question text verbatim>` heading followed by the synthesized answer. Do NOT mix form questions into the `## Job description` section — they belong under the wrapper.

**Synthesis rules — this is the critical part:**

- **For identity questions** (legal name, phone, LinkedIn, work auth, etc.): paste the matched `identity` entry's body **verbatim**. No rewriting. These are facts, not prose. No provenance tag. If the matched entry is a stub (empty body), write `TODO: fill in answer-bank/identity/<slug>.md` instead. If no matching identity entry exists at all, generate a stub at `answer-bank/identity/<slug>.md` with the form field's label as the `question:`, then write the same TODO.
- **For essay questions**: do NOT paste any single `beliefs` / `stories` / `career` / `skills` file verbatim. Instead, **synthesize** — write a new answer in the user's voice that draws on the satisfied inputs identified in step 7. Pull specific phrasing, concrete details, and tonal signatures from the `voice` samples. The output should read like the user wrote it from scratch for this specific company/role.

  Behavior depends on the per-input results from step 7:

  - **All inputs satisfied** → full synthesis. End with the existing provenance tag:
    ```
    [synthesized from: answer-bank/beliefs/<slug>, answer-bank/stories/<slug>, companies/interested/<slug>.md]
    ```
  - **Some inputs satisfied, others pending or just-stubbed** → **partial synthesis** using only the satisfied inputs. Be honest about scope; don't pad with filler to compensate for missing inputs. End with a different tag listing the unsatisfied inputs the user still needs to answer:
    ```
    [partial — pending: answer-bank/beliefs/<slug>, answer-bank/career/<slug>]
    ```
    Do NOT include a `[synthesized from: ...]` tag in this case; the `[partial — pending: ...]` tag is the only provenance line.
  - **All inputs unsatisfied** (every required input is a stub or just-stubbed gap) → write a TODO block instead of prose. One bullet per missing input:
    ```
    TODO: needs answers for the following before this can be drafted:
    - "<question text>" — answer-bank/beliefs/<slug>.md
    - "<question text>" — answer-bank/career/<slug>.md
    ```
    Do not fabricate beliefs, stories, career facts, or skills.
- **Always tie the synthesis to JD-specific language and company-specific signal** (from the company profile under `companies/interested/<slug>.md`). The whole point is that the same `beliefs.what-energizes-me` entry produces a different "Why us?" answer for Stripe vs. Anthropic, because it's combined with different profile content.
- **For demographic questions**: emit a `###` with the question and a paragraph saying `TODO: user fills in directly` — never draft demographic answers, never generate stubs for them.

Drafting guidance:

- Anchor every answer in concrete experience from `context/` — the resume, projects, personal site.
- Tie the user's experience to the role's specific responsibilities. Quote the JD's language where it fits naturally.
- Keep cover letters tight (≤ ~400 words unless the form asks for more): one opening hook, 2–4 specific points of overlap, one logistics line if relocation/travel is relevant, sign-off.
- Avoid generic phrasing ("I'm passionate about…", "I'd love to contribute…"). Specifics are always stronger than adjectives.
- If a question genuinely can't be answered from `context/`, leave a clearly marked `TODO: <question>` paragraph rather than inventing.

### 9. Report back

After processing all companies, give the user:

- Companies scanned, companies skipped (all open roles already in pipeline).
- New application files created, grouped by company. Include the file path and a one-line "why this matched."
- Answer-bank reuse stats: how many essays were full-synth vs. partial-synth vs. all-TODO.
- **Stubs generated this run** — grouped by theme, with paths and the generated question. Example:
  ```
  Stubs generated (4):
    answer-bank/beliefs/
      - "What kinds of missions feel meaningful to you?"        mission-fit-meaningful-missions.md
      - "What cultures have you thrived in vs. burned out in?"  culture-fit-thrive-vs-drain.md
    answer-bank/career/
      - "Which companies do you admire, and why specifically?"  companies-admired-and-why.md
    answer-bank/stories/
      - "Describe a time you navigated a 0-to-1 launch..."      zero-to-one-launch-no-precedent.md

  → Fill them via /seed-answer-bank, then run /draft-missing-answers to backfill the
    partial / TODO essays in applications/in-review/.
  ```
- **Stubs skipped as duplicates** — count only (no need to list each).
- **Identity stubs flagged** — if any `answer-bank/identity/*.md` entries are empty stubs, list each missing field with its path so the user can fill them once and every future application auto-fills.
- Borderline roles worth a human eyeball.
- Any companies where the careers page or ATS was unreachable.

Do NOT commit. The user runs `/commitandpush` when ready.

## Hard rules

- **Never submit.** This skill only creates markdown files under `applications/in-review/`. Never click apply, never fill external forms, never email recruiters.
- **Never invent ATS IDs or URLs.** If you can't find the canonical posting, skip the role and note it in the report.
- **Never write a question the form didn't ask.** The body should map 1:1 to the application form.
- **Never re-draft an existing application.** Check `applications/**/<company>/*.md` across **all seven status folders** before writing — including `rejected/`, `withdrawn/`, and `not-interested/` (don't re-surface after a no).
- **Stubs must be generic and portable.** Every stub generated in step 7 must read as a question about the user (their beliefs, stories, skills, career, identity), never about a specific company, role, or application. "What kinds of missions feel meaningful to you?" YES. "Why Anthropic?" NO. If the most natural question contains a company or role name, rewrite it as the underlying generic question before writing the file.
- **Never generate a stub for a demographic field.** Demographic questions stay as `TODO: user fills in directly` forever.
- **Never write a non-empty body for a stub.** Stubs are frontmatter-only. No placeholder text, no "TODO" body, no whitespace lines. The empty body is the signal that this is unfilled.
- **Canonical catalog takes precedence over invention.** Before generating any stub, look up the gap in the catalog under step 7's "Canonical stubs" section. If it matches (by concept, not exact phrasing), use the catalog row's slug, question, and primary tag verbatim. This is what guarantees parallel subagents converge on the same filenames instead of producing `state-residence.md` + `intended-work-location.md` + `location.md` for the same concept.
- **Always fuzzy-dedupe before writing a stub.** If a filled entry or existing stub already covers the gap (≥60% token overlap on `question:`, or tag-set superset, or semantically equivalent question), skip and treat the existing file as the pending stub for this input. Token overlap alone is not enough; use judgment about whether two questions are asking for the same thing.
- **No company-specific identity stubs.** Form questions like "Have you interviewed at Anthropic before?" or "Have you worked at Figma before?" all map to the single canonical `identity/prior-employer-history.md` stub. Do not create `prior-anthropic-interviews.md` or `prior-figma-employment.md` — those are application-form variants of the same underlying generic question.
- **Never paste a `beliefs` / `stories` / `career` / `skills` / `voice` file verbatim.** Always synthesize — combine substrate from multiple files, plus the JD and company profile, into a fresh answer in the user's voice. The Answer Bank is raw material, not finished prose.
- **Identity entries are the only ones that go in verbatim** — those are facts.
- **Never draft demographic answers.** Leave them as `TODO: user fills in directly`.
- **Never `git mv` or move existing files.** This skill only writes new files under `applications/in-review/`.
- **Never `git commit`** — the user runs `/commitandpush`.
- **Never use em dashes (`—`) in any drafted answer.** Substitute with commas, periods, parentheses, or rewrite. Applies to cover letters, "Why us?" essays, project descriptions, every synthesized answer under `## Application form responses`, and any voice/style note you add. Hyphens (`-`) and en dashes (`–`) are fine; only em dashes (`—`) are out. Verbatim JD content is exempt — keep the company's own text intact.

---
name: onboard
description: First-run setup wizard for careerbot. Detects what's missing in a fresh repo (context/preferences.md, context/index.md, context/resume.pdf, companies/ideas.md, plus folder scaffolding), copies the index and ideas example templates into place, then walks the user through every preference section one question at a time, writing answers into preferences.md as YAML frontmatter (typed source of truth for the dashboard form) plus a markdown body (human-readable, what consumer skills read). Resumable — re-running only asks about sections whose frontmatter fields still equal defaults. Hands off to /find-companies, /find-roles, and /seed-answer-bank at the end without auto-invoking them. Use whenever the user says "onboard me", "start over", "first-time setup", "I just cloned the repo", or otherwise needs to bootstrap careerbot from an empty state.
---

# Onboard

Bootstrap a fresh careerbot install. Survey what's already in place, scaffold the missing folders, copy the index and ideas templates, then interview the user to fill `context/preferences.md` (built as YAML frontmatter + rendered body — same shape the dashboard's Configuration page produces on Save) and `context/index.md`. The skill is interactive, resumable, and never overwrites existing user content.

The full schema is in `SCHEMA.md` at the repo root.

## When to use

Run this skill when:
- The user just cloned careerbot for the first time.
- The user wiped their config and wants to start fresh.
- The user says "onboard me", "first-time setup", "I'm new here", "start the onboarding process", or similar.
- A different skill (e.g. `/find-roles`) failed with "context/preferences.md is missing — stop." This is the recovery path.

If `context/preferences.md` and `context/index.md` already exist and both look fully populated, the skill becomes a no-op that just reports the next-step menu (step 8 below).

## Prerequisites

- The repo's example templates exist (verify before doing anything else):
  - `context/preferences.example.md`
  - `context/index.example.md`
  - `companies/ideas.example.md`
- The user is running the skill from inside the careerbot repo (presence of `SCHEMA.md` at the repo root is the proof-of-life check).

If any example template is missing, stop and tell the user to re-clone or fetch the missing template — the skill needs a known shape to copy from.

## Workflow

### 1. Survey

Walk every required path and report a checklist:

```
Folders:
  context/                          [exists / missing]
  answer-bank/identity/             [exists / missing]
  answer-bank/beliefs/              [exists / missing]
  answer-bank/stories/              [exists / missing]
  answer-bank/career/               [exists / missing]
  answer-bank/skills/               [exists / missing]
  answer-bank/voice/                [exists / missing]
  companies/in-review/              [exists / missing]
  companies/interested/             [exists / missing]
  companies/not-interested/         [exists / missing]
  applications/in-review/           [exists / missing]
  applications/applied/             [exists / missing]
  applications/interview/           [exists / missing]
  applications/rejected/            [exists / missing]
  applications/offered/             [exists / missing]
  applications/withdrawn/           [exists / missing]
  applications/not-interested/      [exists / missing]

Files:
  context/preferences.md            [exists (N/7 sections filled) / missing]
  context/index.md                  [exists / missing]
  context/resume.pdf                [exists / missing — user must supply]
  companies/ideas.md                [exists (N entries) / missing]
```

Ask the user: "Ready to proceed?" If yes, continue. If no, stop and let them prepare.

### 2. Create missing folders

For each missing folder above, `mkdir -p` it. This is purely scaffolding — empty directories don't affect anything else. Non-destructive.

The Answer Bank theme folders start empty. Stubs (the questions the user will eventually answer) are created lazily by `/find-roles` when it hits a context gap mid-essay — not by this skill. A user who never runs `/find-roles` ends up with an empty `answer-bank/`, which is fine: the bank only exists to feed essay synthesis.

### 3. Copy templates (never overwrite)

For each of:
- `context/index.md` ← `context/index.example.md`
- `companies/ideas.md` ← `companies/ideas.example.md`

If the target file does not exist, `cp` from the example. If it exists, leave it alone.

**Do NOT copy `preferences.example.md` to `preferences.md`.** `preferences.example.md` is a question-list reference the skill uses for prompts; the actual `preferences.md` is built by step 4 with YAML frontmatter + rendered body. Two different shapes.

### 4. Walk `preferences.md` section by section

`preferences.md` is the single source of truth for the user's preferences. It has YAML frontmatter (typed data the dashboard form binds to) + a markdown body (human-readable rendering consumer skills read). Both halves are produced from the same in-memory `Preferences` object.

**Schema** (matches `web/src/lib/preferences.ts` `Preferences` type):
```ts
{
  role: { titles: string[], track: "IC" | "Management", specialties: string[], exclude_titles: string[], title_synonyms: Record<string, string[]> },
  compensation: { base_min_usd: number | null, total_comp_target_usd: number | null, equity_open_to: string[] },
  location: { preferred_cities: string[], time_zones: string[], open_to_remote: boolean, open_to_hybrid: boolean, open_to_onsite: boolean, open_to_relocation: boolean, work_auth_us: boolean, needs_sponsorship: boolean },
  company: { stages: string[], size_range: string, industries_want: string[], industries_avoid: string[], excluded_companies: string[] },
  work: { design_tools: string[], tech_avoid: string[], domains: string[], problems: string },
  culture: { hours: string, travel_tolerance: string, async_sync: string, other: string },
  voice: { no_em_dashes: boolean, phrases_to_avoid: string[], tone_notes: string }
}
```

**Defaults** (a field is "filled" if it differs from these): every `string[]` and `string` defaults to `[]` / `""`, every `boolean` to `false`, every numeric to `null`, `role.track` to `"IC"`. Same as the dashboard's `DEFAULT_PREFERENCES` constant.

**Workflow:**

1. **Load existing state.** If `preferences.md` exists, Read it. The first chunk between `---` lines is YAML frontmatter — parse it as the current `Preferences` object. If the file doesn't exist, start from defaults (a fresh `Preferences` object with the values listed above).
2. **For each section** (`role`, `compensation`, `location`, `company`, `work`, `culture`, `voice`), check whether any field still equals the default. If yes, ask the section's questions (see prompts below). If every field is non-default, skip the section unless `--all` or `--section <name>` was passed.
3. **Save after each answer.** Update the in-memory object with the user's answer, then rewrite the whole file: YAML frontmatter (the object) followed by `---`, blank line, then the rendered body. The body template is below in step 4a.
4. **Map answers to typed fields.** "yes/no" → boolean. "$150k" or "150000" or "150,000" → number 150000. Comma-separated lists → string array (trim each). `skip` / `TBD` / empty → leave at default and move on.

The seven sections match the dashboard's Configuration page section-for-section, so a user who fills out preferences.md via this skill and then opens the dashboard sees the same fields populated.

#### 4a. Body template

After updating the in-memory Preferences object, the body of the file (everything after the closing `---` of the frontmatter) is rendered from that object using this template. This mirrors `renderPreferencesMarkdown` in `web/src/lib/preferences.ts:144-202`; if that function changes, update this template too.

```
# Job Preferences

> Auto-rendered from the YAML frontmatter at the top of this file. Edit via the Configuration page in the dashboard (writes both halves) or via `/onboard` in Claude Code.

## Role
- Titles I'm targeting: <role.titles.join(", ") or "TBD">
- Track: <role.track>
- Specialties: <role.specialties.join(", ") or "TBD">
- Titles to exclude: <role.exclude_titles.join(", ") or "(none)">
- Title synonyms: <Object.entries(role.title_synonyms).map(([k,v]) => `${k} → ${v.join(", ")}`).join("; ") or "(none)">

## Compensation
- Minimum base salary: <"$" + base_min_usd.toLocaleString() or "TBD">
- Total comp target: <"$" + total_comp_target_usd.toLocaleString() or "TBD">
- Equity preferences: <equity_open_to.join(", ") or "TBD">

## Location
- Preferred cities: <preferred_cities.join("; ") or "TBD">
- Time zones: <time_zones.join(", ") or "TBD">
- Remote: <yes/no> · Hybrid: <yes/no> · Onsite: <yes/no>
- Open to relocation: <yes/no>
- US work authorization: <yes/no>
- Needs visa sponsorship: <yes/no>

## Company
- Open stages: <stages.join(", ") or "TBD">
- Size range: <size_range or "TBD">
- Industries I want: <industries_want.join(", ") or "TBD">
- Industries to avoid: <industries_avoid.join(", ") or "(none)">
- Specific companies to exclude: <excluded_companies.join(", ") or "(none)">

## Work
- Design tools I use: <design_tools.join(", ") or "TBD">
- Tech stack to avoid: <tech_avoid.join(", ") or "(none)">
- Domains I'm excited about: <domains.join(", ") or "TBD">
- Problems I want to work on: <problems or "TBD">

## Culture & Schedule
- Hours / on-call expectations: <hours or "TBD">
- Travel tolerance: <travel_tolerance or "TBD">
- Async vs synchronous teams: <async_sync or "TBD">
- Anything else that matters: <other or "(none)">

## Voice
<if no_em_dashes: "- Never use em dashes (`—`) in any drafted prose (cover letters, \"Why us?\" essays, application answers). Substitute with commas, periods, parentheses, or rewrite. Hyphens (`-`) and en dashes (`–`) are fine.\n">- Phrases to avoid: <phrases_to_avoid.join(", ") or "(none)">
- Tone notes: <tone_notes or "(none)">
```

Question prompts to use:

**Role section:**
- "What job titles are you targeting? (comma-separated, e.g. `Senior Product Designer, Staff Product Designer`)"
- "IC track, management track, or both?"
- "Specialties? (comma-separated, e.g. `Product/UX, Visual/Brand, Design systems, Prototyping/motion`)"
- "Any role titles you want to NEVER surface, even if they otherwise match? (comma-separated, e.g. `Engineering Manager, Game Designer, Sales Engineer` — case-insensitive substring match; leave blank if none)"
- "Title synonyms? Most users can leave blank — the skill has a built-in registry for common cases (e.g. Design Engineer ↔ UX Engineer / Design Technologist). Add entries here only if your titles have non-obvious equivalents you want surfaced. Format: `Title 1: Synonym A, Synonym B; Title 2: Synonym C`"

Rewrite the five bullets as:
```
- Titles I'm targeting: <answer>
- <Individual contributor / Management / Both>
- Specialties: <answer>
- Titles to exclude: <answer or "(none)">
- Title synonyms: <answer or "(none)">
```

**Compensation section:**
- "Minimum base salary (USD)? (e.g. `$150k`)"
- "Total comp target, if any? (or `TBD`)"
- "Equity preferences? (public, late-stage private, early-stage, all)"

**Location section:**
- "Preferred cities, if any? (comma-separated; or `none`)"
- "Time zones you'll work in? (e.g. `US Pacific`, `US Eastern`, `Anywhere within 4h of PT`)"
- "Open to remote / hybrid / on-site?" — ask via `AskUserQuestion` with `multiSelect: true`. Options: `Remote` → sets `open_to_remote`, `Hybrid` → sets `open_to_hybrid`, `Onsite` → sets `open_to_onsite`. Any subset is valid (including all three or none).
- "Open to relocation? (yes/no)"
- "Visa / work authorization status? (e.g. `US citizen, no sponsorship needed`)"

**Company section:**
- "Stage preference? (any / seed-A / B-D / late / public)"
- "Size range? (e.g. `10-200`, or `open`)"
- "Industries you want? (comma-separated; e.g. `developer tools, climate, health`)"
- "Industries to avoid? (comma-separated; e.g. `crypto, defense, gambling`)"
- "Specific companies to exclude? (comma-separated; or `none`)"

**Work section:**
- "Design tools / tech stack you reach for? (comma-separated)"
- "Tech stack you'd prefer to avoid? (comma-separated; or `none`)"
- "Domains you're excited about?"
- "Problems you want to work on?"

**Culture & Schedule section:**
- "Hours / on-call expectations? (e.g. `standard hours, no on-call`)"
- "Travel tolerance? (e.g. `up to 2 trips/quarter`, or `none`)"
- "Async vs synchronous teams? (e.g. `async-first preferred`)"
- "Anything else that matters?"

**Voice section:**
- "Should drafts AVOID em dashes (`—`)? They read as a tell that AI wrote the text. (yes/no — default `yes`)" — if yes, the skill writes a bullet stating the rule (substitute with commas, periods, parens, or rewrite; hyphens and en dashes are fine). If no, the skill writes a bullet saying em dashes are allowed.
- "Phrases to avoid in drafted prose? (comma-separated, e.g. `I'm passionate about, synergize`; or `none`)"
- "Tone notes — how you want to come across? (e.g. `direct, occasionally self-deprecating, never gushing`)"

If the user types `skip`, `TBD`, or just presses through without an answer, write `TBD` or leave the placeholder — never invent an answer. For Voice's em-dash question, default to `yes` if the user skips (this matches the rule already in `AGENTS.md` at the repo root and in `find-roles/SKILL.md` Hard rules).

### 5. Walk `index.md`

Open `index.md`. If it still matches the example template verbatim (or close enough), replace it with the user's actual paths:

- "Path to your resume? (default: `context/resume.pdf`)"
- "Portfolio / personal site URL? (or `none`)"
- "Any other links or local paths to include? (writeups, projects, etc. — comma-separated, or `none`)"

Rewrite the file as a clean bullet list:

```
- <resume path> - My Resume
- <portfolio URL> - My portfolio
- <each additional link / path> - <short label if the user gave one>
```

If a line is missing a label, write the URL/path alone (no dash, no trailing label).

### 6. Optionally seed `companies/ideas.md`

If `ideas.md` was just copied from the example (still has the example URLs), ask:

- "Any companies you already want tracked? (comma-separated names or URLs; or `skip`)"

If the user gives entries, replace the example content with their list (one per line). If `skip`, leave the example content as a reference template — but flag that the user should clear it before running `/find-companies` so the skill doesn't try to research `example.com`.

### 7. Prompt for `context/resume.pdf` (last interactive step)

This is intentionally the final ask, so the user doesn't lose it in the middle of the flow. Most downstream skills (`/find-roles` especially) cannot do useful work without it, so the prompt is loud and the final report (step 8) flags it as a blocking action item if still missing.

If the file doesn't exist:

> "One last thing I can't do for you: drop your resume PDF at the absolute path below, then press enter.
>
> `<absolute path to repo>/context/resume.pdf`
>
> Press enter when done. Type `skip` to defer (but `/find-roles` will refuse to run until it's there)."

After the user presses enter, check if the file now exists.
- If yes, confirm: "Found it. Resume saved."
- If no (skipped or still missing), include an "ACTION REQUIRED" line in the step 8 report.

### 8. Report & hand off

Print a final checklist and the next-step menu:

```
Onboarding complete. State:
  context/preferences.md    [7/7 sections filled]
  context/index.md          [filled]
  context/resume.pdf        [present / MISSING — ACTION REQUIRED]
  companies/ideas.md        [N entries]
  answer-bank/              [empty — populated lazily by /find-roles]

<if resume.pdf missing:>
  ⚠ ACTION REQUIRED: drop your resume PDF at
    <absolute path>/context/resume.pdf
  before running /find-roles (it will refuse to draft applications without it).
</if>

Next steps (run each from inside Claude Code, in this repo):
  1. /find-companies        → Research the companies in ideas.md into companies/in-review/.
  2. Move profiles          → After review, mv companies/in-review/<slug>.md companies/interested/
                              for any you want to apply to.
  3. /find-roles            → Draft application markdown for each open role at your
                              interested companies. Will generate stubs in answer-bank/
                              whenever it hits a context gap mid-essay (e.g. "What kinds
                              of missions feel meaningful to you?"). Essays with unfilled
                              gaps are marked partial / TODO.
  4. /seed-answer-bank      → Walk every stub /find-roles generated, one at a time.
                              Your answers stay generic and reusable — never company-specific.
  5. /draft-missing-answers → After step 4, upgrades the partial / TODO essays in
                              applications/in-review/ using the newly-filled stubs.

Tip: `pnpm install && pnpm dev` from web/ opens the dashboard if you'd rather browse
than read markdown.
```

Do NOT auto-invoke any of those skills. The user decides when to run each.

Do NOT `git commit`. The user runs `/commitandpush` when they're ready.

## Resumability

Re-running `/onboard` after a partial onboarding:

- The survey in step 1 reports current state.
- The folder creation in step 2 only acts on missing folders. The Answer Bank theme folders stay empty until `/find-roles` populates them with gap-driven stubs.
- The template copies in step 3 are skipped for existing files.
- The interview in step 4 parses the YAML frontmatter of any existing `preferences.md` and only asks about sections whose fields still equal the defaults (empty arrays/strings, false booleans, null numerics, `track: IC`). Voice is one of those sections — its em-dash toggle, phrases-to-avoid, and tone-notes questions are skipped if already set.
- The index walk in step 5 is skipped if the file no longer matches the example template.
- The ideas seed in step 6 is skipped if `ideas.md` has been modified from the example.
- The resume prompt in step 7 is skipped if `resume.pdf` exists. If it's still missing, the prompt fires again — `/onboard` is the dedicated reminder loop for this until the file lands.

A fully-configured repo running `/onboard` shows the report in step 8 and exits.

If the user wants to re-do something, they can pass `--all` to force re-prompting every section, or `--section <name>` to re-prompt one section (e.g. `--section Compensation`).

## Hard rules

- **Never overwrite an existing `preferences.md`, `index.md`, `ideas.md`, or `resume.pdf`.** Always check existence first. If a file exists, parse it for already-filled sections and only ask about the rest. The only way to force a rewrite is `--all` or `--section <name>`.
- **Never invent answers.** If the user says `skip`, types nothing, or says `TBD`, write `TBD` and move on. Don't substitute the example's placeholder text as a "guess."
- **Never touch `answer-bank/`, `companies/<status>/`, or `applications/<status>/` markdown content.** This skill only creates empty status / theme folders. Generating Answer Bank questions (as stubs) is `/find-roles`' job — it does so when an essay it's drafting needs context it doesn't have. Filling stubs is `/seed-answer-bank`'s job. Researching companies is `/find-companies`'s; drafting applications is `/find-roles`'s.
- **Never auto-invoke other skills.** Only suggest them in the step-9 report.
- **Never use em dashes (`—`)** in any prose the skill writes into the user's files. Substitute with commas, periods, parentheses, or rewrite. Per the existing voice rules in `AGENTS.md` (repo root) and the Voice section the skill itself writes into `preferences.md`. Hyphens (`-`) and en dashes (`–`) are fine; only em dashes (`—`) are out.
- **Never modify the `.example.md` templates.** They're the canonical source the skill copies from on future first-runs (and for `--all` re-runs).
- **Never `git commit`** — the user runs `/commitandpush` when they're ready.
- **Idempotent.** Running `/onboard` twice in a row on a clean config must produce zero file writes the second time.

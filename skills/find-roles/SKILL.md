---
name: find-roles
description: Find matching open roles at the user's interested companies and prepare applications. Use whenever the user wants to look for new jobs, scan companies/interested/, fill the applications/in-review queue, prepare cover letters, or generate application responses. Walks every company in companies/interested/, fetches its careers page, filters open roles against context/preferences.md and the rest of context/, and writes one markdown application per match into applications/in-review/<company>/<ATS_ID>-<slug>.md — including drafted answers to ONLY the questions that specific posting actually asks. Never submits applications.
---

# Find Roles

Find open roles at the companies the user is already interested in, then pre-draft an application file for each match. The user reviews and submits manually — this skill never submits.

## Inputs

Before doing anything, load context in this order:

1. **`context/preferences.md`** — required filter. Defines target titles, comp floor, location, industries, must-avoid culture/ethics constraints. Treat the avoid list as a hard filter.
2. **`context/index.md`** — entry point. Follow its links to project folders, the resume, personal site, and any other supporting material the user has added.
3. **`context/resume.pdf`** — read it for concrete experience to draw on when drafting.
4. **`companies/interested/`** — each subfolder is a company the user wants to be considered for. The folder name is the company slug. The folder may contain notes (careers URL, team contacts, prior context) — read whatever is there before searching.

If `context/preferences.md` or `context/index.md` is missing, stop and tell the user — the skill cannot run without them.

## Workflow

For each company folder under `companies/interested/`:

### 1. Skip companies that are already covered

Before fetching anything, list `applications/in-review/<company>/` and `applications/applied/<company>/`. Track every `<ATS_ID>` already on disk so you don't re-prepare the same role. Companies with no open matches simply produce no new files — that's fine.

### 2. Locate the careers page

Check the company folder for an explicit careers URL first. If none, use WebSearch to find the official careers/jobs page (Greenhouse, Lever, Ashby, or in-house). Prefer the canonical job board over aggregators (LinkedIn, Indeed) — the canonical board has the real ATS IDs and application questions you'll need later.

### 3. Pull open roles and filter

Fetch the listing index. For each role, decide match vs. no-match against `preferences.md`:

- **Title** — match the role to the titles/levels listed in `preferences.md`. Reject obvious mismatches outside the user's domain (e.g. roles in functions they didn't list).
- **Location** — must be compatible with the locations/remote policy in `preferences.md`.
- **Comp** — if the posting lists comp, enforce any salary/total-comp floor from `preferences.md`. If the posting doesn't list comp, don't reject on that alone; flag it in the body.
- **Industry / culture** — apply the avoid list from `preferences.md` strictly. Treat it as a hard filter, not a tiebreaker.
- **Tech stack** — prefer roles using stacks the user wants to work in; deprioritize stacks they want to avoid, but don't auto-reject unless they've marked something as a hard avoid.

Be selective. A handful of strong matches beats a dump of weak ones.

### 4. For each match, fetch the actual posting

Open the role's individual page. Extract:

- Canonical job title and ATS ID (the numeric/slug ID in the URL).
- The full JD (responsibilities, requirements, team, location, comp if listed).
- **The application form's questions.** This is the part that's easy to miss. Look for: cover letter prompt, "why this company / why this role", referrals, work-authorization, location/relocation, prior compensation, demographic (skip those — user fills in), and any free-text custom questions ("tell us about a time…", "what's a project you're proud of", etc.).

If you can't reach the application form (gated behind login), note that in the body and draft only the cover letter — don't fabricate questions.

### 5. Write the application file

Path: `applications/in-review/<company>/<ATS_ID>-<job-title-slug>.md`. Create the company folder if it doesn't exist.

Frontmatter (per `applications/AGENTS.md`):

```yaml
---
title: "Exact Job Title From Posting"
id: "ATS_ID"
company: company-slug
url: https://canonical-url-to-the-job
---
```

Leave `date_applied` out — that field is set when the user moves the file to `applied/`.

Body: **only generate answers to questions the posting actually asks.** Don't add a "why this company" section if the form doesn't request one. Don't pad with sections the user will have to delete. Common shape:

```markdown
## Cover letter
<drafted cover letter, only if the posting takes one>

## Why <Company>?
<only if the form asks this specific question>

## <Other custom question, verbatim>
<answer>
```

Drafting guidance:

- Anchor every answer in concrete experience from `context/` — the resume, the project folders linked from `context/index.md`, and any writing the user has pointed to. Use real project names, real metrics, real outcomes.
- If `applications/applied/` already contains files, read a few to calibrate the user's voice, density, and sign-off conventions before drafting. Match that style.
- Tie the user's experience to the role's specific responsibilities. Quote the JD's language back where it fits naturally.
- Keep cover letters tight (≤ ~400 words unless the form asks for more): one opening hook, 2–4 specific points of overlap, one logistics line if relocation/travel is relevant, then sign-off.
- Avoid generic phrasing ("I'm passionate about…", "I'd love to contribute…"). Specifics from `context/` are always stronger than adjectives.
- If a question genuinely can't be answered from `context/` (e.g. "describe a time you used <obscure internal tool>"), leave a clearly marked `TODO: <question>` placeholder rather than inventing.

### 6. Report back

After processing all companies, give the user a short summary:

- Companies scanned, companies skipped (already covered or no matches).
- New files created, grouped by company, with the path and one-line "why this matched."
- Any roles that were borderline and worth a human eyeball.
- Any companies where you couldn't find a careers page or the ATS was gated.

## Hard rules

- **Never submit.** This skill only writes files into `applications/in-review/`. Never click apply, never fill external forms, never email recruiters.
- **Never invent ATS IDs or URLs.** If you can't find the canonical posting, skip the role and note it in the report.
- **Never write a question the form didn't ask.** The body should map 1:1 to the application form.
- **Don't re-prepare existing applications.** Check both `in-review/` and `applied/` before writing.
- **Respect `.agentsignore`** — don't read or write to ignored paths.

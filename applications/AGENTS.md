# Job Applications

This folder holds one markdown file per job application. Status is encoded by the parent folder; never repeat it in frontmatter. Full schema in `SCHEMA.md` at the repo root.

## Layout

`applications/<status>/<company-slug>/<ats-id>-<title-slug>.md`

Status folders (the enum):

- `in-review/` — AI-drafted, user hasn't decided yet
- `interested/` — user reviewed and wants to apply, but hasn't submitted yet
- `applied/` — submitted, awaiting response
- `interview/` — interview scheduled or in progress
- `rejected/` — rejected at any stage
- `offered/` — received an offer
- `archived/` — set aside (decided not to apply, or withdrew after applying)

Status changes are file moves between folders, performed by `/applicationstatus` (`git mv` under the hood).

## Frontmatter

```yaml
---
title: "Senior Software Engineer, Payments"
company: stripe                 # FK → companies.slug
ats_id: "1234567890"
url: "https://stripe.com/jobs/1234567890"
source: greenhouse              # greenhouse|lever|ashby|workday|careers-page|other
date_found: 2026-05-10          # when the role was discovered
salary_min: 180000
salary_max: 250000
location: "San Francisco, CA"
notes: ""
---
```

Body has two top-level sections: `## Job description` (verbatim JD from the posting, including any H3 subsections) followed by `## Application form responses` (one `### <question>` block per form field). The wrapper H2 is required — the web UI splits on it to put JD content in the JD tab and form questions in the Answers tab. See `SCHEMA.md` for the complete invariants.

## Rules

- Status changes are pure file moves between folders — no date stamping. Use `/applicationstatus` to keep history attached via `git mv`.
- Don't write a question the form didn't ask. The body maps 1:1 to the application form.
- The only date in the schema is `date_found` (when the role was discovered). Any post-discovery timeline (applied, interview, rejected, offered) lives implicitly in the folder location and git history; if you need ad-hoc notes, append them to `notes`.

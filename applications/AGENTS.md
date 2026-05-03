# Job Applications

This folder is organized into `applied` and `in-review`. Your job is to prepare applications for me based on all relevant context and then put them into `in-review`. Once I have applied for a job, your job is to put them into the `applied` folder.

## File layout

Each application is a markdown file at `<status>/<company>/<ATS_ID>-<job-title-slug>.md`, where `<status>` is `applied` or `in-review`.

## Frontmatter

Every application file must begin with YAML frontmatter in this format:

```yaml
---
title: "Job Title"
id: "ATS_ID"
company: company-name
date_applied: YYYY-MM-DD
url: https://example.com/jobs/ATS_ID
---
```

Notes:
- `title` and `id` should be quoted strings.
- `date_applied` is an ISO date (`YYYY-MM-DD`). Omit or leave blank for files in `in-review`.
- The body after the frontmatter contains the cover letter / application content.

See `applied/EXAMPLE.md` for a reference template.

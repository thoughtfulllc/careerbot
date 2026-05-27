---
name: applicationstatus
description: Change an application's status by moving its markdown file between status folders under applications/. Use whenever the user says they've applied, gotten an interview, been rejected, received an offer, or wants to archive an application (withdrew, decided not to apply, etc.) — or any phrasing that maps to one of the six lifecycle states. Accepts a job URL, a company+title pair, a filename, or a natural-language description; resolves to the unique matching application file before moving it.
---

# Application Status

Move an application through its lifecycle by relocating its markdown file between status folders. The six valid statuses (folder names) are:

- `in-review` — AI-drafted, user hasn't decided yet
- `applied` — submitted, awaiting response
- `interview` — interview scheduled or in progress
- `rejected` — rejected at any stage (post-application or post-interview)
- `offered` — received an offer
- `archived` — set aside (decided not to apply, or withdrew after applying)

Status changes are pure file moves — the frontmatter never gets a status-specific date stamp. The only date in the schema is `date_found` (when the role was discovered), and it's set once when the file is created. Any post-discovery timeline lives implicitly in the folder location and git history.

The full schema is in `SCHEMA.md` at the repo root.

## Workflow

### 1. Parse the request

The user's request will tell you (a) the new status and (b) which application. Resolve both before touching any files.

**Inferring the new status** from the user's phrasing:

- "I applied to X" / "submitted to X" / "sent off X" → `applied`
- "Got an interview at X" / "Phone screen with X" / "Onsite with X" → `interview`
- "X rejected me" / "Got the rejection email" / "Heard back from X — no" → `rejected`
- "Got the offer from X" / "X gave me an offer" → `offered`
- "Pulled out of X" / "Withdrew from X" → `archived` (post-application)
- "Not interested in X" / "Skip X" / "Don't want to apply to X" → `archived` (pre-application — never submitted)

If the phrasing is ambiguous, ask the user before guessing.

### 2. Resolve the target application file

Acceptable identifiers, in order of preference:

1. **Filename or path** — if the user pastes an explicit path like `applications/in-review/stripe/1234-senior-eng.md`, use it directly after confirming the file exists.
2. **Job URL** — grep across `applications/**/*.md` for a frontmatter line matching `url: "<url>"`. Use:
   ```bash
   grep -rl --include='*.md' "^url: \"<url>\"" applications/
   ```
3. **Company + title** — narrow to `applications/*/<company-slug>/` first, then fuzzy-match the title. The company segment of the path is the slug.
4. **Just the company** — list `applications/*/<company-slug>/*.md`. If there's exactly one application for that company in a non-terminal status (i.e. not in `rejected/`, `archived/`, or `offered/` — so `in-review/`, `applied/`, or `interview/` count), use it.

**If zero or multiple matches**, show the user the candidates (file paths + frontmatter title) and ask them to pick. Never guess silently.

### 3. Determine current status and validate the transition

Current status = the parent-of-parent folder name in the resolved path (`applications/<status>/<company>/<file>.md`).

Allowed transitions:

| From | To |
|---|---|
| `in-review` | `applied`, `archived` |
| `applied` | `interview`, `rejected`, `offered`, `archived` |
| `interview` | `rejected`, `offered`, `archived` |
| `offered` | `archived` (declined offer) |
| `rejected` | (terminal — re-open only with `--force`) |
| `archived` | (terminal — re-open only with `--force`) |

If the requested transition is not in the table, warn the user, explain the current status, and ask whether to proceed anyway. Allow the override but call it out in the report.

### 4. Move the file

Compute the new path: `applications/<new-status>/<company-slug>/<filename>.md` (same filename, same company folder, different status folder).

Use `git mv`:

```bash
mkdir -p applications/<new-status>/<company-slug>
git mv applications/<old-status>/<company-slug>/<filename>.md applications/<new-status>/<company-slug>/<filename>.md
```

If the company-slug subdirectory under the old-status folder becomes empty after the move, leave the empty directory alone — git won't track it and the next application for that company will reuse it.

### 5. (Optional) Update notes

For most transitions, do nothing to the frontmatter — the move itself is the record.

For **`archived`**, optionally prompt the user for a one-line reason and prepend it to `notes` with a date prefix, e.g. `"archived 2026-05-12: comp too low"`. If `notes` already has content, separate with `; `.

For repeat **`interview`** rounds (already in `interview/`), optionally append `"Round N: 2026-05-12"` to `notes`. There is no separate date field.

### 6. Report

Show the user:

- The file path (old → new).
- The transition: `<old-status>` → `<new-status>`.
- Any note appended to `notes`.
- Any flagged override (terminal-state re-open, off-table transition).

Do NOT commit. The user runs `/commitandpush` when they're ready.

## Hard rules

- **Never move a file without confirming the resolution.** If there's any ambiguity, ask before moving.
- **Never apply terminal-to-active transitions silently.** `rejected` and `archived` are intended to be final; only re-open with explicit `--force`.
- **Never touch any other application's file** during a status change. One file moves; nothing else changes.
- **Never `git commit`** from this skill — the user runs `/commitandpush` to batch commits.
- **Use `git mv`, not `mv`** — keeps git history attached to the file.

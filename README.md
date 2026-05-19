# Careerbot

An AI career assistant. It researches companies, finds matching open roles, drafts job applications, tracks their status through the full pipeline, and reuses your best answers across applications, so you stop re-writing the same "Why us?" essay every week.

![Careerbot dashboard](./docs/dashboard.png)

Careerbot stores **everything as local markdown files** under `applications/`, `companies/`, and `answer-bank/`. The schema is defined in [`SCHEMA.md`](./SCHEMA.md) and is designed to be loadable as-is into SQLite (one file = one row, typed YAML frontmatter, folder-encoded status, slug-based foreign keys).


## Two ways to use it

Both interfaces read and write the **same markdown files**. Use either, or both at the same time.

| | **CLI (AI agent)** | **Web dashboard** |
|---|---|---|
| What it's for | Heavy lifting: research companies, find roles, draft application answers | Browsing, editing, and status changes you'd rather click than type |
| How to run | Open the repo in Claude Code (or any agent that supports skills) and run `/find-companies`, `/find-roles`, etc. | `cd web && pnpm install && pnpm dev`, then open http://localhost:3000 |
| What it edits | Markdown files under `applications/`, `companies/`, `answer-bank/` | The same markdown files (via Server Actions) |

You don't have to pick one. Run `/find-roles` in the CLI to draft new applications, then flip to the dashboard to read them, tweak the wording, and move the file from `in-review/` to `applied/`.


## Setup

1. Fill in `context/`:
   - Copy `context/index.example.md` → `index.md` and link to your background material.
   - Copy `context/preferences.example.md` → `preferences.md` and edit (titles, comp floor, locations, deal-breakers).
   - Drop your `resume.pdf` in `context/`.
2. (Optional) Add companies you're curious about to `companies/ideas.md` (copy from `ideas.example.md`).
3. Pick how you want to drive it:
   - **CLI:** open the repo in Claude Code (or another agent that supports skills) and run `/onboard` for a guided first-run setup, then `/find-companies` to start populating `companies/in-review/`.
   - **Web:** `cd web && pnpm install && pnpm dev`, then open http://localhost:3000 to browse and edit the files in your browser.

First time? Run `/onboard` in the CLI; it walks you through everything in step 1 interactively.


## Skills (CLI)

These are the slash commands the AI agent exposes. Each one reads from and writes to the markdown tree.

- **`/onboard`** — first-run setup wizard. Walks you through `context/preferences.md` one section at a time and scaffolds anything missing.
- **`/find-companies`** — finds companies matching your preferences and writes one markdown profile per match to `companies/in-review/<slug>.md`. Bad matches go to `companies/not-interested/<slug>.md` so they never get re-surfaced.
- **`/add-company`** — lightweight single-target version: writes one file to `companies/interested/<slug>.md`.
- **`/add-application`** — single-target counterpart to `/find-roles`. Paste one job posting URL; the skill fetches the JD, drafts answers from your Answer Bank, and writes one draft to `applications/in-review/<company>/<ats-id>-<title-slug>.md`. Auto-adds the company if not already tracked.
- **`/find-roles`** — walks every company under `companies/interested/`, fetches its careers page, filters open roles against your preferences, and drafts one markdown file per match under `applications/in-review/<company>/<id>.md`, pre-filling form questions by reusing entries from `answer-bank/` where they exist.
- **`/seed-answer-bank`** — interactively fills in any empty answer-bank stubs that `/find-roles` flagged as gaps.
- **`/draft-missing-answers`** — re-synthesizes any application answers that were left as TODOs or `[partial — pending: ...]` placeholders, now that the underlying answer-bank stubs are filled.
- **`/applicationstatus`** — moves an application's markdown file between status folders (`in-review/` → `applied/` → `interview/` → `rejected/` / `offered/` / `withdrawn/`) and stamps the matching `date_*` field in its frontmatter.
- **`/commitandpush`** — commits and pushes the public parts of the repo (skills, docs, examples) while keeping every instance file under `applications/`, `companies/`, and `answer-bank/` private (auto-gitignored by `*.md` + whitelist rules).


## Dashboard (web)

A glassy Next.js dashboard that reads and writes the same markdown tree. See [`web/README.md`](./web/README.md) for details.

```bash
cd web
pnpm install
pnpm dev      # http://localhost:3000
```

What you can do from the dashboard:

- Browse applications, companies, and answer-bank entries as paginated, filterable lists.
- Open any item and edit its frontmatter or body inline; saves write back to the same markdown file.
- Change status by moving a file between folders (e.g. mark an application as `applied`).

By default the dashboard walks up from `process.cwd()` looking for `SCHEMA.md`. To point at a different repo, set `CAREERBOT_DATA_ROOT` to an absolute path in `web/.env.local`.


## Workflow

```
                /find-companies                    /add-company
                       │                                │
                       ▼                                ▼
        ┌──────────────────────────┐    companies/interested/<slug>.md
        │  companies/in-review/    │
        └──────────────────────────┘                    │
                  │                                     │
              (you decide; mv file                      │
               or click in dashboard)                   │
                  │                                     │
        ┌─────────┴──────────┐                          │
        ▼                    ▼                          │
   .../interested/      .../not-interested/             │
        │                                               │
        └────────────────┬──────────────────────────────┘
                         │
                         ▼
                    /find-roles
                         │
                         ▼
          applications/in-review/<co>/<id>.md
                         │
                /applicationstatus
              (or status change in dashboard)
                         │
                         ▼
    applied/ → interview/ → offered/  /  rejected/  /  withdrawn/
```

Every status change is a `git mv` between status folders. The folder layout *is* the status column, whether you trigger the move from the CLI or by clicking in the dashboard.


## What's in the repo (public vs. private)

| Public (tracked) | Private (gitignored) |
|---|---|
| `SCHEMA.md`, `README.md`, `AGENTS.md`, `CLAUDE.md` | `context/` (preferences, resume, projects) |
| `.agents/skills/**` (skill code) | `applications/<status>/<company>/*.md` |
| `web/` (Next.js dashboard) | `companies/<status>/*.md` (except `ideas.md`) |
| `*.example.md` files | `answer-bank/<theme>/*.md` |
| `.gitignore` whitelist rules | |

The root `.gitignore` rule `*.md` ignores all markdown by default, then whitelists `AGENTS.md`, `CLAUDE.md`, `README.md`, `*.example.md`, and `.agents/skills/**/*.md`. So any new instance file under the three data folders is automatically private.


## License

MIT — see [`LICENSE`](./LICENSE).

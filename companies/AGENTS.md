# Companies

This folder tracks companies through the research → decision pipeline. The user feeds in raw ideas; you research them; the user moves the dossiers into `interested/` or `rejected/`.

## Layout

- `ideas.md` — free-form list of companies and links the user wants considered. Read this as input when running `/find-companies`. Format is loose: bare URLs, bare company names, or either with a trailing `- note`. Markdown headings are used as informal groupings.
- `in-review/<slug>.md` — research dossiers written by `/find-companies` for candidates that meet the minimum match score. One file per company. The user reviews and decides where each goes next.
- `interested/<slug>/` — companies the user has confirmed they want to be considered for. `/find-roles` walks this folder to look for open roles.
- `rejected/<slug>.md` — companies the user has explicitly rejected, OR that `/find-companies` scored below the minimum match threshold (with the reason recorded in the file). Treat anything here as "do not surface again."

## Rules

- Before researching a company from `ideas.md`, check that it doesn't already exist under `in-review/`, `interested/`, or `rejected/`. Skip it if it does.
- Never move files between `in-review/`, `interested/`, and `rejected/` on your own — that's the user's decision.
- Never write to `rejected/` without the user telling you to, unless a skill explicitly produces a rejection note (in which case include the reason in the file).
- See `.agents/skills/find-companies/SKILL.md` for the dossier file format.

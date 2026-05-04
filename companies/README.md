# Companies

This folder tracks the companies Careerbot is considering for you, from raw idea to decision.

## The pipeline

```
ideas.md  →  /find-companies  →  in-review/<slug>.md  →  you decide  →  interested/<slug>/
                              ↘                                      ↘
                                rejected/<slug>.md  ←  below min score   rejected/<slug>.md
```

- **`ideas.md`** — your scratchpad. Drop in URLs, company names, or short notes about anywhere you'd consider working. `/find-companies` reads this alongside `context/preferences.md` to decide what to research.
- **`in-review/`** — `/find-companies` writes a deep dossier per company here when it scores at or above the minimum match threshold. You review.
- **`interested/`** — companies you've decided you want to be considered for. `/find-roles` walks this folder looking for matching open roles and drafts applications into `applications/in-review/`.
- **`rejected/`** — companies you've ruled out, OR that `/find-companies` scored below the minimum match threshold (with the reason recorded). Skills won't re-surface anything in here.

## Setup

Copy the example file to its real name:

```bash
cp ideas.example.md ideas.md
```

Then edit `ideas.md` freely. Format is loose — see the example for what works.

## Files

| Path | Purpose | Tracked? |
| --- | --- | --- |
| `AGENTS.md` | Instructions for AI agents reading this folder | yes |
| `README.md` | This file | yes |
| `ideas.example.md` | Template for `ideas.md` | yes |
| `ideas.md` | Your free-form list of companies to consider | no |
| `in-review/` | Researched dossiers awaiting your review | no |
| `interested/` | Companies you want to be considered for | no |
| `rejected/` | Companies you've ruled out | no |

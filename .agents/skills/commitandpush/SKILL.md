---
name: commitandpush
description: Commit and push all pending changes as one or more atomic, conventional-commit-style commits, then push to the remote. Before committing, classify each file as public (agent skills, examples, AGENTS.md / README.md / docs) or private (user content under context/, companies/, applications/). If any file looks private but is not already excluded by a .gitignore, stop and ask the user whether to update .gitignore before continuing.
---

# Commit and Push

Commit every pending change in the working tree as a series of atomic, conventional commits and push to the current branch's remote — without ever committing private user content that is not explicitly ignored.

## Project context

This repo is a hybrid: the agent **skills** and **scaffolding** are public and meant to be shared via the GitHub remote, but the user keeps **private career data** (resume notes, company research, application drafts, preferences) inside the same working tree. Privacy here is enforced by per-folder `.gitignore` files that ignore everything (`*`) and explicitly whitelist the public files (`AGENTS.md`, `README.md`, `*.example.md`, `EXAMPLE.md`, `.gitignore` itself).

Your job is to honor that boundary on every commit — never push the user's private content to the public remote.

## Workflow

### 1. Survey the working tree

Run these in parallel:

- `git status --short` — every modified, staged, and untracked path
- `git diff HEAD` — full diff of staged + unstaged changes
- `git log --oneline -10` — recent commit message style
- `git branch --show-current` and `git rev-parse --abbrev-ref @{u}` — current branch and its upstream (if any)
- `git remote -v` — confirm there is a remote to push to

If `git status` is clean, stop and tell the user there is nothing to commit.

### 2. Classify every changed path as public or private

For each path that would be committed (modified, staged, or untracked):

**Public — safe to commit:**

- `AGENTS.md`, `CLAUDE.md`, `README.md` at any depth
- `.agentsignore`, `.gitignore` at any depth
- Anything under `.agents/skills/**` or `skills/**` (skill definitions are public)
- Files matching `*.example.md` or named `EXAMPLE.md`
- Top-level config / scaffolding files that already exist in `git ls-tree -r HEAD --name-only`

**Private — must NOT be committed unless ignored:**

- Anything under `context/` that is not `AGENTS.md`, `README.md`, or `*.example.md` (e.g. `context/index.md`, `context/preferences.md`, `context/resume.pdf`, `context/<project>/...`)
- Anything under `companies/in-review/`, `companies/interested/`, `companies/applied/` (other than `.gitignore` and any `EXAMPLE.md`)
- Anything under `applications/in-review/` or `applications/applied/` (other than `.gitignore`, `AGENTS.md`, and `EXAMPLE.md`)
- Anything else that reads like personal narrative, resume content, cover-letter drafts, or named-company notes

When unsure, treat it as private.

### 3. Verify private paths are actually ignored

For every path classified as private in step 2, run:

```bash
git check-ignore -v -- <path>
```

- **Exit 0** with a matching rule → already ignored; safe to leave alone.
- **Exit 1** (no match) → the file is **not** ignored and would be committed by `git add .`. This is the danger case.

Collect every private-but-not-ignored path into a list.

### 4. If any private paths are unignored, stop and ask the user

Do **not** stage or commit anything yet. Show the user:

- The list of private paths that are not currently ignored
- The closest existing `.gitignore` for each (e.g. `context/.gitignore`, `applications/in-review/.gitignore`, or the repo root) and what rule would need to change
- A concrete proposed patch — usually either:
  - Extend an existing per-folder `.gitignore` (preferred — matches the project's existing pattern of `*` plus `!whitelist` entries), or
  - Add entries to a root `.gitignore`, creating it if it does not exist

Ask: **"Update .gitignore to exclude these files before committing? (yes / no / let me decide per-file)"**

- **yes** — apply the patch, re-run `git check-ignore` to confirm all private paths are now ignored, then continue.
- **no** — abort the skill without committing. Print a short reminder that the private files are still in the working tree but unignored.
- **per-file** — walk the list with the user and apply only the rules they approve; abort if any private file remains unignored at the end.

Never commit private files just because the user said "yes commit everything" earlier — the gitignore confirmation is a hard gate.

### 5. Group changes into atomic, conventional commits

Once every private path is either ignored or absent, plan the commits. Each commit must be:

- **Atomic** — one logical change. If a single working-tree state contains multiple unrelated changes (e.g. a new skill *and* a docs fix *and* a gitignore update), split them into separate commits using `git add <pathspec>` per commit.
- **Conventional** — `<type>(<optional scope>): <subject>` in the imperative mood, ≤72 chars on the subject line. Allowed types:
  - `feat` — new skill, new capability, new scaffolding
  - `fix` — bug fix in an existing skill or config
  - `docs` — changes to AGENTS.md / README.md / inline docs
  - `chore` — gitignore, tooling, file moves with no behavior change
  - `refactor` — restructuring without behavior change
  - `style` — formatting only

Typical groupings for this repo:

- New or edited skill under `.agents/skills/<name>/` → `feat(skills): add <name>` or `fix(skills): ...`
- Edits to `AGENTS.md` / `CLAUDE.md` / `README.md` → `docs: ...`
- New or updated `.gitignore` rules → `chore(gitignore): ignore <thing>`
- File moves (e.g. `skills/` → `.agents/skills/`) → `refactor: ...`

Show the user the proposed commit plan (one line per commit: type, scope, subject, and the paths it covers) **before** running any `git add` or `git commit`. Wait for confirmation, then execute.

### 6. Stage and commit each group

For each planned commit:

1. `git add -- <explicit paths>` — never `git add .` or `git add -A`, because those bypass the per-file classification.
2. `git commit -m "$(cat <<'EOF'
<type>(<scope>): <subject>

<optional body explaining the why, wrapped at ~72 chars>
EOF
)"`
3. Confirm the commit landed with `git log --oneline -1`.

If a pre-commit hook fails, fix the underlying issue and create a **new** commit — do not amend.

### 7. Push

After every commit lands locally:

- If the branch already has an upstream: `git push`
- If not: `git push -u origin <branch>` (only after confirming with the user that pushing this branch to `origin` is intended)

Never `git push --force` or `--force-with-lease` from this skill. If a normal push is rejected because the remote has new commits, stop and tell the user — let them decide whether to pull/rebase.

### 8. Report

Print a short summary:

- Each commit: SHA, type, subject
- Files that were *not* committed because they are private/ignored (so the user knows their working tree still has uncommitted private edits)
- The remote and branch that was pushed to

## Constraints

- **Never** commit a file you classified as private unless `git check-ignore` confirmed it is excluded — and even then, double-check it is actually absent from the staged diff before running `git commit`.
- **Never** use `git add .`, `git add -A`, or `git add -u`. Always pass explicit paths so a stray private file cannot sneak in.
- **Never** modify `.gitignore` without showing the user the diff and getting explicit approval first.
- **Never** skip hooks (`--no-verify`), bypass signing, or force-push.
- **Never** amend or rebase existing commits — only add new ones.
- If anything is ambiguous (a new top-level folder, an unfamiliar file extension, a path you cannot confidently classify), stop and ask the user rather than guessing.

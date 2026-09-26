---
description: Finish the current block of work and open a pull request
argument-hint: [short description]
---

Goal: $ARGUMENTS

1. If on `main`, create a branch `<type>/<short-kebab-name>` (type: feat, fix, refactor, test, docs, ci, chore).
2. Run `/check`; fix anything failing.
3. Run integration tests only if the change touches `infra/` or the API: `uv run pytest -m integration -q`.
4. Launch the `code-reviewer` agent on the branch; apply the fixes that are worth it.
5. If behaviour or setup changed, update README / `docs/` accordingly.
6. Commit with Conventional Commits (small, meaningful commits; no AI attribution trailers).
7. `git push -u origin HEAD` and `gh pr create` with a body: what, why, how it was tested.
8. Wait for CI (`gh pr checks --watch`); when green, `gh pr merge --squash --delete-branch`,
   then `git switch main && git pull`.

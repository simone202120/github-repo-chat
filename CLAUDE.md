# github-repo-chat

Chat with any public GitHub repository: README, docs and source code indexed with LlamaIndex into Qdrant, answered with citations that link back to the files.

Product scope and requirements: `docs/design.md` (read it before starting any work).

## Commands

```bash
uv sync                          # install deps (if uv is missing: pip install uv)
uv run pytest tests/unit -q      # fast unit tests (no keys, no network)
uv run pytest -m integration     # needs `docker compose up -d qdrant`
uv run pytest -m llm             # real LLM calls, manual only
uv run python scripts/code_map.py
docker compose up --build        # full stack
```

Slash commands: `/check` (pre-commit gate), `/pr` (finish work and open a PR), `/code-map`,
`/eval-rag` (run the golden-set evaluation).

## Architecture

```
src/github_repo_chat/
  config.py
  api/        FastAPI app, routers, schemas
  core/       ingestion (download, filter, split) and query logic
  llm/        LLM + embedding factories, prompts.py
  infra/      Qdrant and Langfuse adapters
  ui/         Streamlit app
tests/unit | tests/integration | tests/llm
```

- `core/` holds domain logic and never imports from `api/` or `ui/`.
- `config.py` holds the single `Settings` object; everything configurable comes from env vars.
- Prompts live in `llm/prompts.py`, never inline in business code.
- The LLM is reached through OpenRouter (OpenAI-compatible API) and created in one place only.
- Langfuse tracing is optional: when keys are missing the app runs without it.

## Code rules

- **Comments**: one short header docstring per file saying what it is for. Other comments only
  to explain non-obvious logic (the *why*). No comments restating code, no commented-out code,
  no leftover TODOs.
- **Simple and readable**: clarity over cleverness; small functions; files under ~300 lines.
- **Centralized**: each piece of logic lives in exactly one place. Before writing a helper, search
  for an existing one.
- **No premature abstraction**: introduce an abstraction only when 2–3 real call sites need it.
- **No dead code**: after a change or refactor, delete unused functions, imports, files, folders
  and dependencies. `vulture` and `deptry` run in CI.
- **Tidy structure**: every file in its proper folder, no empty or useless folders, temporary files
  deleted immediately.
- **Errors**: never swallow exceptions; raise domain exceptions, log with `logging` (no `print`
  in `src/`).
- **Types**: type hints everywhere; `mypy --strict` on `src/`.
- Code, comments, commits and docs in English.

## Development cycle

Keep it fast. Do not re-run whole suites to verify small changes.

1. Work on a branch `<type>/<name>`; never commit to `main` directly.
2. Domain logic (validators, parsers, graph nodes, tools): write the test first, then the code.
   Wiring (API routes, UI): test after.
3. While developing, run only the tests of the module you are touching.
4. Before committing: `/check`.
5. Before opening a PR: `code-reviewer` agent on the diff, integration tests if `infra/` or the API
   changed. Use `/pr`.
6. CI must be green before squash-merging.
7. At the end of the project: `security-auditor` once, `docs-writer` for README / architecture /
   code map.

## Agents

- `code-reviewer` — once per PR, reviews the diff and tries to break it.
- `test-engineer` — when a feature needs a real test suite.
- `docs-writer` — end of a significant feature / end of project.
- `security-auditor` — once, near the end.
- `rag-evaluator` — measures retrieval and answer quality on the golden set.

## Git

Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `ci:`, `chore:`), small and
meaningful. No AI attribution trailers in commits or PR descriptions. Squash merge.

## Never

- Read, print or commit `.env` or any secret; use `.env.example` for documentation.
- Commit `SPIEGAZIONE.md`, data dumps, indexes or caches.
- Push to `main` or force-push.

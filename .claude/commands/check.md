---
description: Pre-commit quality gate (format, lint, types, dead code, unit tests)
---

Run, stopping at the first failure and fixing it before moving on:

1. `uv run ruff format .`
2. `uv run ruff check --fix .`
3. `uv run mypy src`
4. `uv run vulture src`
5. `uv run deptry .`
6. `uv run pytest tests/unit -q`

Report a one-line result per step. Do not run integration or LLM tests here.

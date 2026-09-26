---
description: Regenerate docs/code-map.md and report orphan modules and dead code
---

1. Run `uv run python scripts/code_map.py` to regenerate `docs/code-map.md`.
2. Run `uv run vulture src`.
3. Report: modules nobody imports (excluding entry points), unused symbols, and any import that
   breaks the layering rule (`core/` importing `api/` or `ui/`). Propose deletions; delete only
   what is clearly dead.

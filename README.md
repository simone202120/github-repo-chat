# github-repo-chat

Chat with any public GitHub repository: README, docs and source code indexed with LlamaIndex into Qdrant, answered with citations that link back to the files.

> Status: work in progress. See [`docs/design.md`](docs/design.md) for scope and design.

## Development

This project is developed with an AI-assisted workflow using [Claude Code](https://claude.com/claude-code):
project context in [`CLAUDE.md`](CLAUDE.md), specialized agents, slash commands and hooks in
[`.claude/`](.claude/) (auto-formatting, secret protection, session context).

```bash
uv sync
uv run pytest
```

## License

MIT

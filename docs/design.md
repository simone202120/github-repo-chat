# github-repo-chat — Design

## Goal
Point the app at any public GitHub repository and ask questions about it: what it is for, how to
install and use it, where something is implemented, what a function does. Answers are grounded in the
repository content and cite the files they come from, with links to GitHub.

Demo story (2 minutes): index a repo chosen live by the interviewer, ask 3 questions, show citations
and the Langfuse trace with tokens and cost.

## Scope
### Ingestion
- Input: a GitHub URL or `owner/name`, optional branch (default: repo default branch).
- Download the repository as a zip archive (codeload), no git clone, no GitHub API pagination.
- Include: `README*`, `*.md`, `*.mdx`, `*.rst`, `*.txt` docs, and source files
  (`.py .js .ts .tsx .jsx .go .java .rs .rb .php .cs .kt .swift .c .cpp .h`).
- Exclude: tests/specs folders, `node_modules`, `vendor`, `dist`, `build`, lockfiles, minified,
  generated files, binaries, files > 200 KB. Cap at ~500 files (prefer docs and top-level source).
- Splitting: markdown by heading sections (MarkdownNodeParser); code by function/class
  (LlamaIndex `CodeSplitter` with tree-sitter); fallback to `SentenceSplitter` for unsupported types.
- Metadata per chunk: repo, file path, language, section/symbol name, start line, GitHub URL
  (`https://github.com/<owner>/<repo>/blob/<ref>/<path>#L<line>`).
- One Qdrant collection per repository. Incremental re-index: store a content hash per file;
  on re-ingest, skip unchanged files, re-embed changed ones, delete removed ones.
- Embeddings: local FastEmbed (dense, e.g. `BAAI/bge-small-en-v1.5`) + sparse BM25 for hybrid search.

### Query
- Hybrid retrieval (dense + sparse) in Qdrant, top-k configurable, optional lightweight reranking.
- Answer generation through OpenRouter with a prompt that: uses only the retrieved context,
  says "I don't know" when context is insufficient, cites sources as numbered references.
- Response: answer text + list of sources (path, symbol/section, URL, score).
- Conversation: short chat history per session (condense question + context).

### API (FastAPI)
- `POST /repos` `{url, branch?}` → starts background ingestion, returns job id; `GET /repos/{id}` status.
- `GET /repos` → indexed repos with file/chunk counts and last indexed time.
- `DELETE /repos/{id}`.
- `POST /chat` `{repo, question, history?}` → answer + sources.
- `GET /health`.

### UI (Streamlit)
Sidebar: add repo (URL) with progress, select indexed repo. Main: chat with expandable sources.

### Observability
Langfuse LlamaIndex instrumentation: one trace per chat request (retrieval + generation, tokens, cost).

## Non-goals
Private repos, authentication, multi-user, reranking models requiring GPUs.

## Testing
- Unit: file filter rules, URL parsing, splitter routing by file type, hash-based diffing,
  citation formatting, prompt building, API routes with a fake query engine (fake LLM + in-memory store).
- Integration: ingest a tiny fixture repo (zip in `tests/fixtures/`) into real Qdrant, query it.
- LLM: golden-set evaluation (see `rag-evaluator` agent).

## Deliverables
Docker compose (api, ui, qdrant), README with architecture diagram and demo GIF placeholder,
`docs/architecture.md`, `docs/code-map.md`, CI green, coverage >= 80%.

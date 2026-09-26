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

## UI and demo polish

The UI is what the interviewer sees first: it must look clean and deliberate, not like a default
Streamlit script.

- Custom theme in `.streamlit/config.toml` (`[theme]`: base, primaryColor, backgroundColor,
  secondaryBackgroundColor, textColor, font, baseRadius) using the palette below. No heavy CSS hacks;
  at most a few lines of `st.markdown(..., unsafe_allow_html=True)` for spacing.
- `st.set_page_config` with title, icon and `layout="wide"`; a short header with the project name and
  a one-line description; a sidebar for settings and state.
- Long operations show progress (`st.status` / `st.progress` / `st.spinner`) with human-readable steps.
- Every screen has a useful empty state: 3 clickable example inputs that run a real demo.
- Results are presented, not dumped: containers with borders, badges, metrics, expanders. Raw JSON
  only in a collapsed "Raw response" expander.
- Show cost and speed of each run (tokens, estimated cost, latency) as small metrics: it proves the
  observability story. Link to the Langfuse trace when tracing is enabled.
- Errors are friendly `st.error` messages that say what to do, never stack traces.
- The UI talks to the FastAPI backend over HTTP (backend URL from settings), never imports `core/`.
- Keep it one file per page under `ui/`, small helpers in one module; no duplicated rendering code.

Palette: dark base, background `#0D1117`, surface `#161B22`, text `#E6EDF3`, primary `#2F81F7`.
Layout: sidebar with "Add repository" (URL input + progress while indexing: downloading, filtering,
splitting, embedding) and the list of indexed repos with file/chunk counts. Main area: `st.chat_message`
chat; under each answer, source cards (file path, symbol/section, score, "Open on GitHub" link).
Examples in the empty state: `fastapi/fastapi`, `pallets/flask`, `langchain-ai/langgraph`.

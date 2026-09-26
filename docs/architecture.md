# Architecture

## Design decisions

Each decision lists the choice and the trade-off behind it.

### Ingestion

- **Default branch without the GitHub API.** A missing branch becomes the ref `HEAD`: codeload
  serves `zip/HEAD` and github.com resolves `blob/HEAD/<path>`, so no API call (and no token or
  rate limit) is needed. Trade-off: citation links follow the branch head, so they can drift if the
  repository changes after indexing.
- **Archive read in memory, never extracted.** The zip is streamed with a size cap
  (`MAX_ARCHIVE_BYTES`) and files are read straight from it. No temporary directory to clean and no
  path-traversal risk. Trade-off: peak memory is about the archive size (100 MB by default).
- **Two-phase filtering.** Path and size rules run on zip metadata first; content rules (binary,
  minified, generated markers) run only on the files that survive, in priority order, until the
  500-file cap is reached. Minified/generated checks apply only to source files, because Markdown
  often has very long lines. Priority: READMEs, other docs, then source files by depth.
- **Symbols and start lines computed after splitting.** LlamaIndex splitters do not report symbol
  names or reliable line numbers, so each chunk is located in its file (first line match, moving
  cursor) and named by a per-language regex outline of definitions / Markdown headings: the first
  definition inside the chunk, else the enclosing one. Trade-off: regexes miss some constructs
  (e.g. plain C functions), in which case the symbol is empty but the path and line are still right.
- **No NLTK / tiktoken at split time.** `SentenceSplitter` gets a regex sentence splitter and a
  word/punctuation token counter. This avoids runtime data downloads (and NLTK refusing the
  hard-linked data files that `uv` installs). Trade-off: token counts are approximate, which only
  shifts chunk boundaries slightly.
- **Incremental re-index by file hash.** A manifest `{path: sha256}` is stored per repository.
  Changed, added and removed files are deleted first (all chunks of a file share the path as
  document id), the manifest is saved with only the unchanged files, then new chunks are embedded
  and the final manifest is written. A crash halfway therefore leaves files marked as missing, and
  the next run re-embeds them instead of skipping them.

### Query

- **Condense + context.** With history, the follow-up is condensed into a standalone question for
  retrieval, and the recent turns are also passed to the answering prompt. Without history no
  extra LLM call is made.
- **No LLM call without context.** If retrieval returns nothing, the fixed "I don't know" answer is
  returned directly.
- **Prompt-injection hygiene.** Excerpts are wrapped in `<context>` / `<excerpt>` tags, the system
  prompt declares them untrusted, and closing tags inside repository content are neutralized.
- **Optional reranking** takes a larger candidate pool (3 x top-k) and keeps the best top-k.

### Storage and infrastructure

- **Manifest registry in Qdrant.** Per-repository manifests (file hashes, chunk count, branch,
  indexed time) are payload-only points in a `github_repo_chat_registry` collection, so Qdrant
  is the only stateful service. Trade-off: no relational queries, and the whole hash map is
  rewritten on each save (fine for ≤500 files).
- **One hybrid collection per repository** (`repo__<owner>--<name>`): dense FastEmbed vectors plus
  BM25 sparse vectors with Qdrant's IDF modifier, fused with relative-score fusion. Deleting a
  repository drops its collection, and a file's chunks are removed with a single `doc_id` filter.
  The sparse side retrieves 2 x top-k before fusion.
- **BM25 encoders built once** and passed to `QdrantVectorStore`: documents use `embed`, queries
  use `query_embed` (the library default uses `embed` for both and reloads the model on each
  store). Trade-off: a little glue code in `llm/factory.py`.
- **Tracing through OpenInference.** Langfuse v4 is OpenTelemetry-based: the LlamaIndex
  instrumentor emits retrieval / embedding / LLM spans with token usage, and the API opens one
  root span per chat request so they group into one trace. Without keys, `Tracer` is a no-op.
  Cost appears when Langfuse knows the model's price (custom prices can be added in Langfuse for
  OpenRouter model ids).
- **Qdrant client and server pinned together** (client 1.19, server `v1.19.1`): the client warns
  when minor versions differ by more than one.

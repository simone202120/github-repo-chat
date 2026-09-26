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

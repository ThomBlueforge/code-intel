# Phase 2 — Tree-sitter Parsing

## What was built

Deterministic symbol extraction. Every ingested file in a supported language is
parsed with Tree-sitter and yields `Symbol` rows matching the canonical schema,
persisted in SQLite and queryable by path. No LLM is involved.

### New modules

| Module | Responsibility |
|--------|----------------|
| `parsing/queries.py` | Validated per-language Tree-sitter queries; canonical-language → grammar mapping. |
| `parsing/extractor.py` | `SymbolExtractor`: runs queries, resolves parent nesting, classifies symbols. |

### Changed modules

- `models.py` — added the canonical `Symbol` dataclass plus `SYMBOL_TYPES` /
  `VISIBILITY_VALUES` vocabularies.
- `storage/database.py` — schema **v2**: new `symbols` table (FK-cascaded to
  `files` and `repositories`; self-referential `parent_id`), with indexes on
  repo, file, path, name, and type.
- `storage/repositories.py` — `SymbolStore` (insert/delete-per-file/count/
  list-by-path).
- `ingestion/indexer.py` — after a file is added or changed, it is parsed and
  its symbols are (re)written in the same transaction. Unchanged files are never
  re-parsed; removed files' symbols cascade-delete.
- `cli/main.py` — new `symbols` command; `index` now reports symbol counts.

## How to run

```bash
uv run code-intel index /path/to/repo
uv run code-intel symbols /path/to/repo                       # type breakdown
uv run code-intel symbols /path/to/repo --file src/app.py     # symbols in a file
```

## Extraction model

- **Types emitted** (canonical `SYMBOL_TYPES`): function, method, class,
  interface, struct, trait, enum, const, global, namespace.
- **Method detection** — a `function` lexically nested in a class/interface/
  struct/trait is reclassified as a `method` and linked via `parent_id`.
- **Parent linking** — resolved by smallest enclosing byte range among the
  file's own symbols; parents are always inserted before children so the
  self-referential FK holds.
- **Globals vs consts** — only module-level (parent-less) assignments are kept;
  UPPER_CASE names become `const`, others `global`. Class attributes and locals
  are dropped.
- **Visibility** — access-modifier keyword in the declaration when present;
  otherwise language heuristics (Python underscore, Go capitalization, Rust
  `pub`). Falls back to `unknown`.
- **`signature`** = the declaration line; **`code`** = the full unit source;
  **`hash`** = BLAKE2b of the unit source.

## Languages with symbol extraction

Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, C#, PHP.

Ingested but **not yet parsed** (recorded with zero symbols): Swift, Kotlin,
SQL, HTML, CSS, Markdown, YAML, JSON. Adding one is a matter of adding a query
to `queries.py`.

## Robustness

Extraction is best-effort and never breaks ingestion: an unsupported language,
an unreadable file, or a grammar/parse failure yields zero symbols while the
file remains in the manifest. Verified by `test_malformed_source_does_not_raise`.

## Known limitations

- TypeScript files with JSX (`.tsx`) are parsed with the TypeScript grammar and
  may under-extract; a dedicated `tsx` grammar hook is a later refinement.
- Rust `impl` methods and C++ out-of-line member definitions surface as
  `function` (their enclosing `impl`/namespace is not a symbol parent).
- Type aliases (TS `type X = …`) and imports/exports are intentionally **not**
  symbols — imports/exports become relationships in Phase 3/5.
- One extra file read per added/changed file (for parsing); acceptable because
  it only happens on the incremental delta.

## Definition of Done

- [x] Every ingested file in a supported language produces `Symbol` rows
      queryable by path (`code-intel symbols … --file …`).
- [x] Typed, `ruff`-clean, `mypy --strict`-clean.
- [x] Unit tests: extractor (10 languages' shapes, visibility, parents,
      robustness) and end-to-end symbol indexing (incremental, replace, cascade).
- [x] This doc; CLI exposes the capability.
- [x] Runs start-to-finish against a real repository (self-index: 26 files,
      156 symbols).

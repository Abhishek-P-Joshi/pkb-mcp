# PKB MCP — Personal Knowledge Base MCP Server

A locally-hosted [Model Context Protocol](https://modelcontextprotocol.io) server that turns your scattered notes, bookmarks, and YouTube watch history into a searchable, AI-queryable personal knowledge base. Built in Python, runs entirely on your Mac, connects to Claude Desktop.

```
Ask Claude: "What videos do I have saved about astrophysics?"
Claude:      Calls search_knowledge → hybrid FTS + vector search
             Returns: The Power of Neutron Stars (PBS Space Time),
             How Smooth is a Neutron Star? (Sixty Symbols),
             Neutron Stars Explained (Kurzgesagt)...
```

> **Current state:** 1,430+ YouTube videos ingested with full metadata, Obsidian vault connected, 10 MCP tools live, full test suite passing.

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Data flow](#data-flow)
- [Storage layer](#storage-layer)
- [MCP tools](#mcp-tools)
- [Project structure](#project-structure)
- [Test suite](#test-suite)
- [Setup](#setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Roadmap](#roadmap)
- [Privacy](#privacy)
- [Tech stack](#tech-stack)

---

## Features

- **Hybrid search** — combines keyword (FTS5) and semantic (vector) search using Reciprocal Rank Fusion for best-of-both results. Keyword search handles exact names, URLs, and IDs; vector search handles concepts and meaning.
- **Structured browse** — filter by channel, duration, upload date, view count, language, category — all via direct SQL, no embeddings needed
- **RAG answers** — ask questions in plain English, get cited answers synthesised from your own notes with source attribution
- **Auto-enrichment** — YouTube URLs automatically enriched with title, channel, channel ID, description, tags, duration, view count, like count, upload date, language, categories, and thumbnail URL via YouTube Data API v3
- **Hybrid YouTube sync** — Watch Later playlist fetched via yt-dlp (`extract_flat=True`, single page request) for video IDs; full metadata fetched via authenticated YouTube Data API. Custom playlists use API only — no cookies needed.
- **Multi-playlist support** — sync Watch Later and any number of custom playlists independently, each with a friendly source name
- **Two-tier deletion** — soft delete marks notes as inactive (recoverable, full audit trail) while hard delete permanently removes from both SQLite and ChromaDB. Delta sync uses soft delete for playlist and vault removals.
- **Real-time ingestion** — drop a `.md`, `.txt`, or `.docx` file into the inbox folder and it's chunked, embedded, and searchable within seconds via `watchdog` file watcher
- **Deduplication** — MD5 hash scoped to note ID — same content with different filenames both ingest correctly; unchanged files are skipped
- **Obsidian integration** — watches your vault, ingests on every save, delta sync removes notes for deleted files
- **Local-first** — embedding model, FTS, and vector store all run on your machine. Only `answer_question` calls the Anthropic API (swappable with local Ollama in Phase 5)
- **Remote-ready** — `NOTE[remote]` swap points throughout the codebase for future HTTP/cloud deployment with one config change
- **Test suite** — unit, integration, and smoke tests with pytest. Session-scoped embedding model fixture keeps integration test runtime under 5 seconds.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          MCP clients                                │
│              Claude Desktop · Claude iOS · Claude Web               │
└─────────────────────────────┬───────────────────────────────────────┘
                              │  MCP protocol (stdio locally,
                              │  HTTP when remote — NOTE[remote])
┌─────────────────────────────▼───────────────────────────────────────┐
│                       PKB MCP server                                │
│                      (Python · FastAPI stub)                        │
│                                                                     │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐ │
│  │ health_check   │  │ ingest_content │  │  sync_knowledge_base   │ │
│  │ search_knowl-  │  │ browse_knowl-  │  │  sync_youtube_playlist │ │
│  │ edge           │  │ edge           │  │  list_items            │ │
│  │ answer_        │  │ delete_item    │  │  restore_item          │ │
│  │ question       │  │ list_deleted   │  │                        │ │
│  └────────────────┘  └────────────────┘  └────────────────────────┘ │
└──────┬──────────────────────┬────────────────────────┬──────────────┘
       │                      │                        │
┌──────▼──────┐   ┌───────────▼──────────┐  ┌─────────▼───────────┐
│  Ingestion  │   │    Query layer        │  │  Connector layer     │
│  pipeline   │   │                       │  │                      │
│             │   │  Hybrid search        │  │  File watcher        │
│  Classifier │   │  (FTS + vector        │  │  Obsidian connector  │
│  Chunker    │   │   + RRF merge)        │  │  YouTube API v3      │
│  Embedder   │   │                       │  │  yt-dlp (WL index)   │
│  Enricher   │   │  SQL filter browse    │  │  [Gmail — Phase 4]   │
│             │   │                       │  │  [OneDrive — Phase 4]│
└──────┬──────┘   └───────────┬───────────┘  └──────────────────────┘
       │                      │
┌──────▼──────────────────────▼──────────────────────────────────────┐
│                        Storage layer                                │
│                                                                     │
│  ┌───────────────────────────┐  ┌───────────────────────────────┐  │
│  │   SQLite + FTS5           │  │   ChromaDB                    │  │
│  │   (data/sqlite/pkb.db)    │  │   (data/chroma/)              │  │
│  │                           │  │                               │  │
│  │  notes table (22 cols)    │  │  pkb_notes collection         │  │
│  │  notes_fts virtual table  │  │  384-dim vectors              │  │
│  │  Inverted word index      │  │  all-MiniLM-L6-v2 (local)    │  │
│  │  Structured SQL filters   │  │  Cosine similarity            │  │
│  │  Soft delete status col   │  │                               │  │
│  └───────────────────────────┘  └───────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## Data flow

### Ingestion flow (file dropped into inbox)

```
File saved to data/watched/inbox/
         │
         ▼
   File watcher (watchdog)
   detects create/modify event
         │
         ▼
   FileParser
   ├── .md   → strip YAML frontmatter, extract body + tags
   ├── .txt  → UTF-8 read with latin-1 fallback
   └── .docx → python-docx, paragraphs + tables
         │
         ▼
   hash_file() → MD5 fingerprint (chunked 8KB reads, memory-efficient)
         │
         ▼
   storage.fts.get_by_hash(hash, note_id)
   ├── Match found AND status='active' → SKIP (file unchanged)
   └── No match (new or soft-deleted)  → continue
         │
         ▼
   detect_urls() → extract all http/https URLs
         │
         ▼
   classify_content() → video / article / note / list / doc
         │
         ▼
   URLEnricher (if URL found)
   ├── YouTube URL → YouTube Data API v3
   │     title, channel, channel_id, description, tags,
   │     duration_seconds, duration_string, view_count,
   │     like_count, language, categories, uploaded_at,
   │     thumbnail_url
   └── Other URL  → httpx fetch → title + meta description
         │
         ▼
   Build enriched text for embedding:
   original_text + Title + Channel + Description
   + Tags + Duration + Uploaded + Categories + Language
   (view_count, like_count, thumbnail_url stored but NOT embedded)
         │
         ▼
   TextChunker → 512-token chunks (~384 words), 50-word overlap
         │
         ▼
   Embedder (all-MiniLM-L6-v2, runs locally, ~90MB)
   → list of 384-dim float vectors, one per chunk
         │
         ├──────────────────────────────────────────┐
         ▼                                          ▼
   FTSStore.upsert()                    VectorStore.upsert()
   notes table (SQLite)                 pkb_notes (ChromaDB)
   ├── id, title, source                ├── chunk_id
   ├── content_type, url, tags          ├── text (chunk)
   ├── channel, channel_id              ├── embedding vector
   ├── duration_seconds/string          └── metadata
   ├── view_count, like_count                (note_id, source,
   ├── language, categories                   content_type, title)
   ├── uploaded_at, thumbnail_url
   ├── file_hash, raw_text
   ├── status ('active')
   └── created_at, updated_at
```

### Query flow — search_knowledge (hybrid)

```
User: "show me videos about astrophysics"
         │
         ▼
   search_knowledge tool
   ├── query = "astrophysics"
   ├── content_type = "video"
   └── fts_only = false
         │
         ├──────────────────────────────────────────┐
         ▼                                          ▼
   FTSStore.search()                    VectorStore.search()
   SQLite FTS5 MATCH 'astrophysics'     embed query → cosine sim
   WHERE status = 'active'              top-N nearest vectors
   AND content_type = 'video'
         │                                          │
         ▼                                          ▼
   FTS results (ranked by BM25)         Vector results (by similarity)
   [note_A rank=0]                      [note_B rank=0]
   [note_B rank=1]                      [note_A rank=1]
   [note_C rank=2]                      [note_D rank=2]
         │                                          │
         └──────────────────┬────────────────────────┘
                            ▼
            Reciprocal Rank Fusion (k=60)
            score = 1/(60+rank_fts+1) + 1/(60+rank_vec+1)
            notes in BOTH lists score highest
                            │
                            ▼
            Filter by min_score threshold
            Deduplicate by note_id
            Return top N results with excerpts
```

### Query flow — answer_question (RAG)

```
User: "what space documentaries have I saved?"
         │
         ▼
   answer_question tool
         │
         ▼
   hybrid_search(question, limit=5)
   [same flow as search_knowledge above]
         │
         ▼
   Build context string from top results:
   "[Source: Travel INSIDE a Black Hole (youtube_watch_later)]
    Title: Travel INSIDE a Black Hole
    Channel: minutephysics
    Description: What would it look like to travel..."
   ---
   "[Source: What are black holes? (youtube_watch_later)]..."
         │
         ▼
   Anthropic API (claude-3-5-haiku)        ← only external call
   system: "Answer using ONLY the provided context from
            the user's notes. Cite sources as [Source: title]."
   user:   context + question
         │
         ▼
   Formatted answer with inline citations
   + Sources used section with RRF scores
```

### Browse flow — browse_knowledge (SQL filter)

```
User: "show me Kurzgesagt videos shorter than 15 minutes"
         │
         ▼
   browse_knowledge tool
   ├── channel = "Kurzgesagt"
   ├── max_duration_seconds = 900
   └── content_type = "video"
         │
         ▼
   FTSStore.filter_by_date()
   SELECT id, title, channel, duration_string,
          view_count, uploaded_at, created_at
   FROM notes
   WHERE status = 'active'
     AND content_type = 'video'
     AND channel LIKE '%Kurzgesagt%'
     AND duration_seconds <= 900
   ORDER BY created_at DESC
         │
         ▼
   Formatted results:
   title · channel · duration · view count · upload date
```

### YouTube sync flow (hybrid: yt-dlp + API)

```
sync_youtube_playlist called
         │
         ▼
   Is playlist_id == "WL" (Watch Later)?
   ├── YES → yt-dlp + Chrome cookies
   │         extract_flat=True (SINGLE page request)
   │         → list of {video_id, title}
   │         (Watch Later blocked by YouTube Data API by design)
   └── NO  → YouTube Data API v3
             playlistItems.list with pagination
             → list of {video_id, title, added_at}
         │
         ▼
   For each video_id:
   check storage.fts.get_by_id(note_id)
   ├── exists + fully enriched → SKIP
   └── new or partial          → continue
         │
         ▼
   YouTube Data API v3 — videos.list
   part = "snippet, contentDetails, statistics"
   → full metadata (1 API unit per video, 10k units/day free)
         │
         ▼
   Ingest pipeline (same as file flow above)
   note_id = "youtube_{playlist_id}_{video_id}"
   source  = "youtube_{playlist_name}"
         │
         ▼
   Delta reconciliation (delete_removed=True)
   existing_ids = all notes for this source in DB
   current_ids  = all video IDs in current playlist
   removed      = existing_ids - current_ids
   → soft_delete(removed_id, deleted_from='playlist_removed')
   → vector.delete_by_note_id(removed_id)
```

### Deletion flow — soft delete and hard delete

```
delete_item(note_id, hard=False)         delete_item(note_id, hard=True)
         │                                        │
         ▼                                        ▼
   FTSStore.soft_delete()              FTSStore.hard_delete()
   UPDATE notes SET                    DELETE FROM notes WHERE id=?
     status='deleted',                          │
     deleted_at=NOW(),                          ▼
     deleted_from='user'              DELETE trigger fires →
   WHERE id=?                         notes_fts index cleaned up
         │                                      │
         ▼                                      ▼
   VectorStore.delete_by_note_id()    VectorStore.delete_by_note_id()
   ChromaDB chunks removed            ChromaDB chunks removed
         │
         ▼
   Note hidden from all active queries
   (AND status='active' on every read)
   Visible only via list_deleted()
         │
         ▼ restore_item(note_id)
   FTSStore.restore()
   UPDATE notes SET status='active',
     deleted_at=NULL, deleted_from=NULL
         │
         ▼
   pipeline.ingest(raw_text, file_hash=None)
   Re-embed from preserved raw_text
   → chunks restored in ChromaDB
   Note fully searchable again
```

---

## Storage layer

### SQLite schema — notes table (22 columns)

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Stable note identifier |
| `source` | TEXT | Origin: obsidian, inbox, youtube_watch_later, manual |
| `content_type` | TEXT | video, article, note, list, doc |
| `title` | TEXT | Note title or enriched video title |
| `url` | TEXT | Primary URL if present |
| `tags` | TEXT | Comma-separated tags |
| `file_hash` | TEXT | MD5 fingerprint for deduplication |
| `raw_text` | TEXT | Full text including all enriched metadata |
| `channel` | TEXT | YouTube channel name |
| `channel_id` | TEXT | Stable YouTube channel ID |
| `uploaded_at` | TEXT | YouTube upload date (YYYY-MM-DD) |
| `duration_seconds` | INTEGER | Video duration in seconds |
| `duration_string` | TEXT | Human readable duration (MM:SS or HH:MM:SS) |
| `view_count` | INTEGER | YouTube view count at ingest time |
| `like_count` | INTEGER | YouTube like count at ingest time |
| `categories` | TEXT | YouTube categories (comma-separated) |
| `language` | TEXT | ISO language code (en, hi, es...) |
| `thumbnail_url` | TEXT | YouTube thumbnail URL |
| `status` | TEXT | `active` (default) or `deleted` |
| `deleted_at` | TIMESTAMP | When soft-deleted (NULL if active) |
| `deleted_from` | TEXT | `user`, `playlist_removed`, `file_deleted` |
| `created_at` | TIMESTAMP | When note was ingested |
| `updated_at` | TIMESTAMP | Last update time |

**FTS5 virtual table** — `notes_fts` mirrors `notes` and is kept in sync via three SQLite triggers: `notes_ai` (after insert), `notes_au` (after update), `notes_ad` (after delete). The delete trigger prevents FTS index corruption on hard deletes — without it, FTS5 retains stale row references that cause `missing row` errors on subsequent queries. All read queries include `AND status = 'active'` to filter soft-deleted rows.

**Index** — `CREATE INDEX idx_notes_status ON notes(status)` keeps status filtering fast at scale.

### ChromaDB — vector store

One collection: `pkb_notes`. Each chunk stored with:
- `id` — `{note_id}_chunk_{index}`
- `embedding` — 384-dimensional float vector from `all-MiniLM-L6-v2`
- `document` — the chunk text (up to ~384 words)
- `metadata` — `{note_id, source, content_type, title, url}`

Chunks are retrieved by cosine similarity. Multiple chunks from the same note are deduplicated to note level in the RRF merger. On soft or hard delete, all chunks for a note are removed from ChromaDB immediately. On restore, chunks are re-generated from the preserved `raw_text` in SQLite — ensuring restoration is always possible without the original file.

---

## MCP tools

10 tools registered. Claude selects the appropriate tool automatically based on query intent.

| Tool | Type | Description |
|---|---|---|
| `health_check` | Status | Server uptime, env, storage path, timestamp |
| `ingest_content` | Write | Add any text/URL — auto-classifies, enriches, chunks, embeds |
| `sync_knowledge_base` | Write | Sync inbox / Obsidian / YouTube by source |
| `sync_youtube_playlist` | Write | Sync a specific YouTube playlist by ID with full metadata |
| `search_knowledge` | Read | Hybrid FTS + vector search with RRF. `fts_only` mode for exact lookups |
| `browse_knowledge` | Read | SQL filters: channel, date range, duration, views, language, category, count |
| `list_items` | Read | Paginated browse by type or source (up to 200 per page) |
| `answer_question` | Read | RAG — retrieves top chunks, synthesises cited answer via Claude API |
| `delete_item` | Write | Soft delete (recoverable) or hard delete (permanent). Bulk delete by source with confirmation guard |
| `restore_item` | Write | Restore soft-deleted note — re-embeds from preserved raw_text |
| `list_deleted` | Read | Browse soft-deleted notes filterable by type, source, date |

### When Claude uses which tool

```
"find videos about machine learning"       → search_knowledge  (semantic intent)
"show me Kurzgesagt videos"                → browse_knowledge  (channel filter)
"chess videos shorter than 10 minutes"     → browse_knowledge  (duration filter)
"videos uploaded in 2023"                  → browse_knowledge  (date filter)
"how many videos do I have?"               → browse_knowledge  (count_only=true)
"find note with URL youtube.com/watch?v=…" → search_knowledge  (fts_only=true)
"what did I save about astrophysics?"      → answer_question   (RAG)
"show me all my videos"                    → list_items        (paginated browse)
"delete this video from my KB"             → delete_item       (soft delete)
"restore the note I just deleted"          → restore_item      (re-embeds)
"what have I deleted recently?"            → list_deleted      (audit trail)
```

---

## Project structure

```
pkb-mcp/
├── main.py                            # Entry point — asyncio.run(server.run())
├── Makefile                           # run-local, run-remote, health, test,
│                                      # test-integration, test-smoke, test-all,
│                                      # test-coverage, purge-deleted
├── pytest.ini                         # asyncio_mode=auto, test markers
├── config/
│   ├── config.local.yaml              # Local: stdio transport, auth off
│   ├── config.remote.yaml             # Remote: http transport, auth on
│   ├── youtube_oauth_client.json      # gitignored — Google OAuth credentials
│   └── youtube_token.json             # gitignored — OAuth refresh token
├── src/
│   ├── server.py                      # MCP server, tool registration, watcher init
│   ├── config.py                      # Config dataclass, env-driven loader
│   ├── auth.py                        # API key middleware (no-op locally)
│   ├── tools/
│   │   ├── health.py                  # health_check
│   │   ├── ingest.py                  # ingest_content — pipeline singleton
│   │   ├── sync.py                    # sync_knowledge_base
│   │   ├── search.py                  # search_knowledge — hybrid + RRF
│   │   ├── browse.py                  # browse_knowledge — SQL filters
│   │   ├── list_items.py              # list_items — paginated browse
│   │   ├── answer.py                  # answer_question — RAG via Anthropic
│   │   └── delete.py                  # delete_item, restore_item, list_deleted
│   ├── pipeline/
│   │   ├── ingest.py                  # Orchestrates full ingest flow
│   │   ├── chunker.py                 # 512-token chunks, 50-word overlap
│   │   ├── embedder.py                # sentence-transformers singleton
│   │   ├── classifier.py              # URL detection, content type routing
│   │   └── enricher.py                # YouTube API + web page metadata
│   ├── store/
│   │   ├── __init__.py                # StorageManager singleton
│   │   ├── fts.py                     # SQLite FTS5: CRUD, search, filter,
│   │   │                              # soft_delete, hard_delete, restore,
│   │   │                              # list_deleted, purge
│   │   ├── vector.py                  # ChromaDB: upsert, search, delete
│   │   └── search.py                  # Hybrid search + RRF merger
│   └── connectors/
│       ├── file_parser.py             # .md / .txt / .docx parsers
│       ├── hasher.py                  # MD5 fingerprinting (chunked 8KB reads)
│       ├── watcher.py                 # watchdog real-time folder watcher
│       ├── obsidian.py                # Vault scan, delta sync, file removal
│       └── youtube_api.py             # OAuth2, videos.list API,
│                                      # get_watch_later_ids (yt-dlp),
│                                      # sync_playlist with delta reconciliation
├── scripts/
│   ├── import_youtube_playlist.py     # One-time CSV import (Google Takeout)
│   ├── backfill_via_api.py            # Enrich existing videos via YouTube API
│   └── inspect_chroma.py              # Debug ChromaDB contents
├── tests/
│   ├── conftest.py                    # shared_embedder (session-scoped),
│   │                                  # temp_fts_store, test_config,
│   │                                  # mock_embedder (instant fake vectors),
│   │                                  # sample_note, sample_video_note,
│   │                                  # block_anthropic_api_in_tests
│   ├── unit/
│   │   ├── test_chunker.py            # 7 tests — splitting, overlap, limits
│   │   ├── test_classifier.py         # 11 tests — URL detection, types
│   │   ├── test_hasher.py             # 8 tests — MD5, large files, dedup
│   │   ├── test_file_parser.py        # 6 tests — frontmatter, txt, errors
│   │   └── test_fts_store.py          # 25 tests — CRUD, search, filters,
│   │                                  # pagination, soft/hard delete, restore,
│   │                                  # purge, reingestion after restore
│   ├── integration/
│   │   └── test_ingest_pipeline.py    # 8 tests — full pipeline with temp db,
│   │                                  # mock embedder (instant fake vectors)
│   └── smoke/
│       └── test_mcp_tools.py          # 5 tests — live tool handlers,
│                                      # loose assertions, no prod data written
└── data/                              # gitignored
    ├── sqlite/pkb.db
    ├── chroma/
    └── watched/inbox/
```

---

## Test suite

Three-layer test strategy matching the architecture:

| Layer | Command | Speed | What it tests |
|---|---|---|---|
| Unit | `make test` | ~5s | Individual functions in isolation, no DB, no network |
| Integration | `make test-integration` | ~5s | Full pipeline with temp DB, mocked embedder |
| Smoke | `make test-smoke` | ~10s | Live tool handlers against production server |

```bash
make test              # unit tests only — run after every code change
make test-integration  # with temp SQLite + ChromaDB
make test-smoke        # against live MCP server (Claude Desktop running)
make test-all          # everything
make test-coverage     # with HTML coverage report in htmlcov/
```

**Key design decisions:**

- **`shared_embedder` fixture is session-scoped** — the `all-MiniLM-L6-v2` model loads once per `pytest` session. Without this, each integration test fixture would reload the 90MB model, taking ~100s total. With it, the integration suite runs in ~5s.
- **`mock_embedder` for integration tests** — returns deterministic fake 384-dim vectors instantly. Pipeline logic (dedup, storage routing, classification, metadata handling) is tested correctly without any neural network inference. Real embedding quality is validated by the smoke tests against the live server.
- **Smoke tests use loose assertions** — `isinstance(result, str)` and format-invariant strings (`"Total:"` always appears in count responses). Tests pass on any database state including empty, avoiding fragile assertions that would break after a wipe.
- **Anthropic API is blocked in all tests** — a session-scoped `autouse` fixture raises `RuntimeError` if any test accidentally calls the Anthropic API. Tests requiring `answer_question` must use an explicit mock.
- **No production data written by smoke tests** — a cleanup fixture removes any rows written during the smoke suite using stable test IDs.
- **FTS5 patching approach** — integration tests patch `src.pipeline.ingest.storage` (the module-level singleton) rather than `config`, because `IngestPipeline` imports `storage` at module load time. Patching config after import has no effect on the already-constructed singleton.

---

## Setup

### Prerequisites

- Python 3.11+
- Chrome (for YouTube Watch Later sync via yt-dlp)
- Claude Desktop (to connect as MCP client)
- Node.js 18+ (optional — for Claude Code CLI)

### Install

```bash
# Clone and enter project
git clone https://github.com/yourusername/pkb-mcp
cd pkb-mcp

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install mcp fastapi uvicorn sentence-transformers chromadb \
  pyyaml python-dotenv watchdog apscheduler rich yt-dlp \
  httpx python-docx google-auth google-auth-oauthlib \
  google-api-python-client anthropic pytest pytest-asyncio pytest-mock
```

### Environment

```bash
cat > .env << 'EOF'
PKB_ENV=local
ANTHROPIC_API_KEY=sk-ant-your-key-here
EOF
```

### Verify setup

```bash
# Config loads correctly
python3 -c "from src.config import config; print(config.env)"

# Storage initialises (downloads embedding model ~90MB on first run)
make health

# Run unit tests
make test

# Start server
make run-local
```

### Connect to Claude Desktop

Open `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pkb-mcp": {
      "command": "/path/to/pkb-mcp/.venv/bin/python3",
      "args": ["/path/to/pkb-mcp/main.py"],
      "env": {
        "PKB_ENV": "local",
        "ANTHROPIC_API_KEY": "sk-ant-your-key-here"
      }
    }
  }
}
```

Restart Claude Desktop. You should see **10 tools** available. All server stdout is redirected to stderr — Claude Desktop reads stdout exclusively for JSON MCP messages, so any print leaking to stdout will break the connection.

### YouTube API setup (required for Watch Later and custom playlist sync)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create project → enable **YouTube Data API v3**
3. Create OAuth consent screen (External) → add your Gmail as test user
4. Create credentials → OAuth Client ID → Desktop app → download JSON
5. Save as `config/youtube_oauth_client.json`
6. Run the one-time auth flow (opens browser):

```bash
python3 -c "
from src.connectors.youtube_api import get_authenticated_service
service = get_authenticated_service()
print('Auth successful — token saved to config/youtube_token.json')
"
```

The refresh token is saved to `config/youtube_token.json` (gitignored). Future syncs re-authenticate silently. Free quota: 10,000 units/day — `videos.list` costs 1 unit per video, so 1,400 videos uses 14% of daily quota.

**Watch Later note:** Google intentionally blocks Watch Later (`WL`) from the YouTube Data API — it returns 0 results even with valid OAuth. Video IDs are fetched via yt-dlp with `extract_flat=True` (a single playlist page request, not per-video scraping). Full metadata is then fetched for each ID via the API. Custom playlists use the API exclusively — no browser cookies needed.

---

## Configuration

`config/config.local.yaml`:

```yaml
env: local
transport: stdio              # NOTE[remote]: change to "http"
host: localhost               # NOTE[remote]: change to "0.0.0.0"
port: 8000
auth_enabled: false           # NOTE[remote]: change to true, set PKB_API_KEY in .env
storage_path: ./data          # NOTE[remote]: change to absolute path e.g. /var/pkb/data
embedding_model: all-MiniLM-L6-v2
sync_interval_minutes: 60
youtube_sync_enabled: false
obsidian_vault_path: ""       # Set to absolute path of your Obsidian vault
youtube_playlists: []         # List of {id, name, method} for multi-playlist sync
```

All `NOTE[remote]` markers indicate swap points for cloud deployment. Remote hosting requires uncommenting the FastAPI + uvicorn block in `src/server.py` and activating the auth middleware in `src/auth.py` — both are already written and stubbed, requiring no new code.

---

## Usage

### Drop files into inbox

```bash
# Any .md, .txt, or .docx file dropped here is ingested automatically
cp my-notes.md data/watched/inbox/
# → watchdog detects → parse → hash check → classify → enrich → chunk → embed → store
```

### Ask Claude

```
# Semantic search — concept and topic based
"What videos do I have saved about black holes?"
"Find my notes about machine learning transformers"

# Structured browse — channel, date, duration, popularity
"Show me all Kurzgesagt videos"
"Find chess videos shorter than 10 minutes uploaded in 2023"
"What are the most viewed videos I've saved?"
"Show me Hindi language videos"
"How many videos do I have in total?"

# RAG answers — synthesised from your notes with citations
"What do my saved notes say about neutron stars?"
"Summarise what I know about personal finance from my notes"

# Exact lookup — URL, channel name, video ID
"Find the note with this URL: youtube.com/watch?v=dQw4w9WgXcQ"
"Show me all agadmator chess videos"
```

### Sync sources

```
"Sync my inbox"
"Sync my Obsidian vault"
"Sync my YouTube Watch Later playlist"   ← yt-dlp + API, needs Chrome logged in
"Sync my YouTube playlist"               ← custom playlist, API only, no cookies
```

### Delete and restore

```
# Soft delete — recoverable, chunks removed from ChromaDB
"Delete the video 'Chess Traps: Halosar Trap' from my knowledge base"

# Review deleted items (audit trail)
"What have I deleted recently?"
"Show me deleted videos from last week"

# Restore — re-embeds from preserved raw_text
"Restore the note I just deleted"

# Bulk delete by source — prompts for confirmation first
"Permanently remove all manual test notes"
  → confirms count, requires confirm_bulk=true

# Periodic purge — keep DB clean
make purge-deleted        # hard-delete rows soft-deleted > 90 days ago
make purge-deleted-30     # hard-delete rows soft-deleted > 30 days ago
```

### Import YouTube playlist from Google Takeout

```bash
# Export from takeout.google.com → YouTube → Playlists, then:
python3 scripts/import_youtube_playlist.py "Watch later videos.csv"
```

---

## Roadmap

### Phase 4 — Cloud connectors
- Apple Notes via AppleScript (Mac-local, `NOTE[remote]` for iCloud API alternative)
- OneDrive via Microsoft Graph API + OAuth2
- Gmail via Google API + OAuth2
- Google Keep export watcher

### Phase 5 — Intelligence + polish
- **Local LLM** — Ollama integration for `answer_question`. Sensitive sources (journal, health, finance) routed to local model automatically; public content continues using Anthropic API. Configurable per source in `config.yaml`.
- **Auto-tagging** — extract 3–5 topic tags per note automatically
- **Entity extraction** — people, organisations, dates
- **Inbox processing tool** — Claude helps batch-organise Obsidian inbox conversationally
- **APScheduler** — periodic background syncs (Obsidian every 30min, YouTube every 6h)
- **CLI** — `pkb sync`, `pkb search`, `pkb status` standalone commands
- **Remote hosting** — activate FastAPI HTTP transport + API key auth + Tailscale or Cloudflare Tunnel. All swap points already stubbed throughout the codebase.

---

## Privacy

| Component | Where it runs | Data exposure |
|---|---|---|
| Embedding model (`all-MiniLM-L6-v2`) | Local (your Mac) | None — text never leaves |
| SQLite + ChromaDB | Local (your Mac) | None |
| File watcher | Local (your Mac) | None |
| YouTube Data API | Google servers | Video IDs only (public metadata) |
| yt-dlp Watch Later | YouTube (Chrome cookies) | Your Watch Later playlist list |
| `answer_question` | Anthropic API | Top 5 matching note chunks |

Only `answer_question` sends data to an external API — the top 5 retrieved chunks used to synthesise the answer. This is swappable with a local Ollama model in Phase 5 for fully air-gapped operation on sensitive content.

---

## Tech stack

| Layer | Technology |
|---|---|
| MCP framework | `mcp` Python SDK (official Anthropic SDK) |
| Embedding model | `sentence-transformers` — `all-MiniLM-L6-v2` (local, ~90MB) |
| Vector store | ChromaDB (persistent, local) |
| Full-text search | SQLite FTS5 with BM25 ranking |
| File parsing | `python-docx`, `pyyaml` |
| File watching | `watchdog` |
| YouTube metadata | YouTube Data API v3 + `yt-dlp` (hybrid approach) |
| Web enrichment | `httpx` |
| LLM (answers) | Anthropic API — `claude-3-5-haiku-20241022` |
| HTTP transport | FastAPI + uvicorn (stubbed, activates for remote hosting) |
| Testing | `pytest`, `pytest-asyncio`, `pytest-mock` |
| Scheduler | APScheduler (Phase 5) |

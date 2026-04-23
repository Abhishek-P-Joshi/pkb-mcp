# PKB MCP — Personal Knowledge Base MCP Server

A locally-hosted [Model Context Protocol](https://modelcontextprotocol.io) server that turns your scattered notes, bookmarks, and YouTube watch history into a searchable, AI-queryable personal knowledge base. Built in Python, runs entirely on your Mac, connects to Claude Desktop.

```
Ask Claude: "What videos do I have saved about astrophysics?"
Claude:      Calls search_knowledge → hybrid FTS + vector search
             Returns: The Power of Neutron Stars (SEA), The Life and Death
             of Stars (PBS Space Time), How Smooth is a Neutron Star? (Sixty Symbols)...
```

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Data flow](#data-flow)
- [Storage layer](#storage-layer)
- [MCP tools](#mcp-tools)
- [Project structure](#project-structure)
- [Setup](#setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Roadmap](#roadmap)

---

## Features

- **Hybrid search** — combines keyword (FTS5) and semantic (vector) search using Reciprocal Rank Fusion for best-of-both results
- **Structured browse** — filter by channel, duration, upload date, view count, language, category
- **RAG answers** — ask questions, get cited answers synthesised from your own notes
- **Auto-enrichment** — YouTube URLs automatically enriched with title, channel, description, duration, view count, upload date via YouTube Data API v3
- **Real-time ingestion** — drop a file into the inbox folder and it's searchable within seconds
- **Deduplication** — MD5 hash per note, scoped to note ID — same content, different filenames both ingest correctly
- **Obsidian integration** — watches your vault, ingests on every save
- **Local-first** — embeddings, storage, and FTS all run on your machine. Only `answer_question` calls the Anthropic API (optional, swappable with local LLM in v2)
- **Remote-ready** — swap points documented throughout for future HTTP/cloud deployment

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP clients                              │
│              Claude Desktop · Claude iOS · Claude Web           │
└───────────────────────────┬─────────────────────────────────────┘
                            │  MCP protocol (stdio locally,
                            │  HTTP when remote)
┌───────────────────────────▼─────────────────────────────────────┐
│                     PKB MCP server                              │
│                    (Python · FastAPI stub)                       │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │health_check  │  │ingest_content│  │  sync_knowledge_base │  │
│  ├──────────────┤  ├──────────────┤  ├──────────────────────┤  │
│  │search_knowl- │  │list_items    │  │  answer_question     │  │
│  │edge          │  │              │  │                      │  │
│  ├──────────────┤  ├──────────────┤  ├──────────────────────┤  │
│  │browse_knowl- │  │              │  │                      │  │
│  │edge          │  │              │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└──────┬──────────────────┬──────────────────────┬───────────────┘
       │                  │                      │
┌──────▼──────┐  ┌────────▼────────┐  ┌──────────▼──────────┐
│  Ingestion  │  │  Query layer    │  │  Connector layer     │
│  pipeline   │  │                 │  │                      │
│             │  │ Hybrid search   │  │ File watcher         │
│ Classifier  │  │ (FTS + vector   │  │ Obsidian connector   │
│ Chunker     │  │  + RRF merge)   │  │ YouTube API          │
│ Embedder    │  │                 │  │ yt-dlp (WL index)    │
│ Enricher    │  │ SQL filter      │  │ [Gmail - Phase 4]    │
│             │  │ browse          │  │ [OneDrive - Phase 4] │
└──────┬──────┘  └────────┬────────┘  └──────────────────────┘
       │                  │
┌──────▼──────────────────▼──────────────────────────────────────┐
│                      Storage layer                              │
│                                                                 │
│  ┌─────────────────────────┐  ┌─────────────────────────────┐  │
│  │   SQLite + FTS5         │  │   ChromaDB                  │  │
│  │   (data/sqlite/pkb.db)  │  │   (data/chroma/)            │  │
│  │                         │  │                             │  │
│  │  notes table            │  │  pkb_notes collection       │  │
│  │  notes_fts virtual      │  │  384-dim vectors            │  │
│  │  Inverted word index    │  │  all-MiniLM-L6-v2           │  │
│  │  Structured filters     │  │  Cosine similarity          │  │
│  └─────────────────────────┘  └─────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
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
   ├── .md  → strip YAML frontmatter, extract body + tags
   ├── .txt → UTF-8 read with latin-1 fallback
   └── .docx → python-docx, paragraphs + tables
         │
         ▼
   hash_file() → MD5 fingerprint
         │
         ▼
   storage.fts.get_by_hash(hash, note_id)
   ├── Match found → SKIP (file unchanged)
   └── No match   → continue
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
   │     title, channel, channel_id, description,
   │     tags, duration, view_count, like_count,
   │     language, categories, uploaded_at,
   │     thumbnail_url
   └── Other URL  → httpx fetch → title + meta description
         │
         ▼
   Build enriched text:
   original_text + Title + Channel + Description
   + Tags + Duration + Uploaded + Categories
         │
         ▼
   TextChunker → 512-token chunks, 50-word overlap
         │
         ▼
   Embedder (all-MiniLM-L6-v2, local)
   → list of 384-dim vectors, one per chunk
         │
         ├──────────────────────────────────────┐
         ▼                                      ▼
   FTSStore.upsert()                  VectorStore.upsert()
   notes table (SQLite)               pkb_notes (ChromaDB)
   ├── id, title, source              ├── chunk_id
   ├── content_type, url, tags        ├── text (chunk)
   ├── channel, channel_id            ├── embedding vector
   ├── duration_seconds/string        └── metadata
   ├── view_count, like_count              (note_id, source,
   ├── language, categories                 content_type, title)
   ├── uploaded_at, thumbnail_url
   ├── file_hash, raw_text
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
         ├──────────────────────────────────────┐
         ▼                                      ▼
   FTSStore.search()                  VectorStore.search()
   SQLite FTS5 MATCH                  embed query → cosine sim
   "astrophysics"                     top-N nearest vectors
   + WHERE content_type='video'       + filter content_type
         │                                      │
         ▼                                      ▼
   FTS results (ranked by BM25)       Vector results (ranked by score)
   [note_A rank=0]                    [note_B rank=0]
   [note_B rank=1]                    [note_A rank=1]
   [note_C rank=2]                    [note_D rank=2]
         │                                      │
         └──────────────┬───────────────────────┘
                        ▼
          Reciprocal Rank Fusion (k=60)
          score = 1/(60+rank_fts+1) + 1/(60+rank_vec+1)
          notes appearing in BOTH lists score highest
                        │
                        ▼
          Filter by min_score (default 0.015)
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
   Build context string:
   "[Source: Travel INSIDE a Black Hole (youtube_watch_later)]
    Title: Travel INSIDE a Black Hole
    Channel: minutephysics
    Description: What would it look like to travel..."
   ---
   "[Source: What are black holes? (youtube_watch_later)]
    ..."
         │
         ▼
   Anthropic API (claude-3-5-haiku)        ← only external call
   system: "Answer using ONLY the provided context.
            Cite sources using [Source: title]."
   user:   context + question
         │
         ▼
   Formatted answer with citations
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
   WHERE content_type = 'video'
     AND channel LIKE '%Kurzgesagt%'
     AND duration_seconds <= 900
   ORDER BY created_at DESC
         │
         ▼
   Formatted results with:
   title · channel · duration · view count · upload date
```

### YouTube Watch Later sync flow

```
sync_youtube_playlist called (or scheduled every 6h)
         │
         ▼
   yt-dlp + Chrome cookies
   extract_flat=True (single page request)
   → list of {video_id, title}
   (Watch Later is not accessible via YouTube Data API)
         │
         ▼
   For each video_id:
   check storage.fts.get_by_id(note_id)
   ├── exists + enriched → SKIP
   └── new or partial   → continue
         │
         ▼
   YouTube Data API v3 — videos.list
   part = "snippet, contentDetails, statistics"
   → full metadata (1 API unit per video)
         │
         ▼
   Ingest pipeline (same as file flow above)
   note_id = "youtube_WL_{video_id}"
   source  = "youtube_watch_later"
```

---

## Storage layer

### SQLite schema — notes table

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Stable note identifier |
| `source` | TEXT | Origin: obsidian, inbox, youtube_watch_later, manual |
| `content_type` | TEXT | video, article, note, list, doc |
| `title` | TEXT | Note title or enriched video title |
| `url` | TEXT | Primary URL if present |
| `tags` | TEXT | Comma-separated tags |
| `file_hash` | TEXT | MD5 fingerprint for deduplication |
| `raw_text` | TEXT | Full text including enriched metadata |
| `channel` | TEXT | YouTube channel name |
| `channel_id` | TEXT | Stable YouTube channel ID |
| `uploaded_at` | TEXT | YouTube upload date (YYYY-MM-DD) |
| `duration_seconds` | INTEGER | Video duration in seconds |
| `duration_string` | TEXT | Human readable duration (MM:SS) |
| `view_count` | INTEGER | YouTube view count at ingest time |
| `like_count` | INTEGER | YouTube like count at ingest time |
| `categories` | TEXT | YouTube categories (comma-separated) |
| `language` | TEXT | ISO language code |
| `thumbnail_url` | TEXT | YouTube thumbnail URL |
| `created_at` | TIMESTAMP | When note was ingested |
| `updated_at` | TIMESTAMP | Last update time |

The `notes_fts` virtual table (FTS5) mirrors `notes` and is kept in sync via SQLite triggers on INSERT and UPDATE. Enables full-text search across title, raw_text, and tags.

### ChromaDB — vector store

One collection: `pkb_notes`. Each chunk stored with:
- `id` — `{note_id}_chunk_{index}`
- `embedding` — 384-dimensional float vector from `all-MiniLM-L6-v2`
- `document` — the chunk text (up to ~384 words)
- `metadata` — `{note_id, source, content_type, title, url}`

Chunks are retrieved by cosine similarity. Multiple chunks from the same note are deduplicated to note level in the RRF merger.

---

## MCP tools

| Tool | Type | Description |
|---|---|---|
| `health_check` | Status | Server uptime, env, storage path |
| `ingest_content` | Write | Add any text/URL to the knowledge base |
| `sync_knowledge_base` | Write | Trigger sync: inbox / obsidian / youtube |
| `search_knowledge` | Read | Hybrid FTS + vector search with RRF |
| `browse_knowledge` | Read | SQL filter by channel, date, duration, views |
| `list_items` | Read | Paginated browse by type or source |
| `answer_question` | Read | RAG — retrieve chunks, synthesise answer |

### When Claude uses which tool

```
"find videos about machine learning"   → search_knowledge (semantic)
"show me Kurzgesagt videos"            → browse_knowledge (channel filter)
"videos shorter than 10 minutes"       → browse_knowledge (duration filter)
"videos uploaded in 2023"              → browse_knowledge (date filter)
"how many chess videos do I have?"     → browse_knowledge (count_only)
"find note with URL youtube.com/..."   → search_knowledge (fts_only=true)
"what did I save about astrophysics?"  → answer_question (RAG)
"show me all my videos"                → list_items (paginated browse)
```

---

## Project structure

```
pkb-mcp/
├── main.py                        # Entry point
├── Makefile                       # make run-local / run-remote / health
├── config/
│   ├── config.local.yaml          # Local config (transport: stdio)
│   ├── config.remote.yaml         # Remote config (transport: http)
│   └── .gitkeep
├── src/
│   ├── server.py                  # MCP server, tool registration
│   ├── config.py                  # Config loader (env-driven)
│   ├── auth.py                    # Auth middleware (no-op locally)
│   ├── tools/
│   │   ├── health.py              # health_check
│   │   ├── ingest.py              # ingest_content
│   │   ├── sync.py                # sync_knowledge_base
│   │   ├── search.py              # search_knowledge
│   │   ├── browse.py              # browse_knowledge
│   │   ├── list_items.py          # list_items
│   │   └── answer.py              # answer_question (RAG)
│   ├── pipeline/
│   │   ├── ingest.py              # Orchestrates full ingest flow
│   │   ├── chunker.py             # 512-token chunks, 50-word overlap
│   │   ├── embedder.py            # sentence-transformers wrapper
│   │   ├── classifier.py          # URL detection, content type
│   │   └── enricher.py            # YouTube API + web page metadata
│   ├── store/
│   │   ├── __init__.py            # StorageManager singleton
│   │   ├── fts.py                 # SQLite FTS5 store
│   │   ├── vector.py              # ChromaDB vector store
│   │   └── search.py              # Hybrid search + RRF merger
│   └── connectors/
│       ├── file_parser.py         # .md / .txt / .docx parsers
│       ├── hasher.py              # MD5 file fingerprinting
│       ├── watcher.py             # watchdog file watcher
│       ├── obsidian.py            # Obsidian vault connector
│       └── youtube_api.py         # YouTube Data API v3 + yt-dlp
├── scripts/
│   ├── import_youtube_playlist.py # One-time playlist import
│   ├── backfill_via_api.py        # Enrich existing videos via API
│   └── inspect_chroma.py          # Debug ChromaDB contents
└── data/                          # gitignored
    ├── sqlite/pkb.db
    ├── chroma/
    └── watched/inbox/
```

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for Claude Code CLI, optional)
- Chrome (for YouTube Watch Later sync via yt-dlp)
- Claude Desktop (to connect as MCP client)

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
  google-api-python-client anthropic
```

### Environment

```bash
# Create .env (never commit this)
cat > .env << 'EOF'
PKB_ENV=local
ANTHROPIC_API_KEY=sk-ant-your-key-here
EOF
```

### Verify setup

```bash
# Check config loads
python3 -c "from src.config import config; print(config.env)"

# Check storage initialises (downloads embedding model ~90MB first run)
make health

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

Restart Claude Desktop. You should see 7 tools available under the hammer icon.

### YouTube API setup (optional — for Watch Later sync)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create project → enable **YouTube Data API v3**
3. Create OAuth consent screen (External) → add your Gmail as test user
4. Create credentials → OAuth Client ID → Desktop app → download JSON
5. Save as `config/youtube_oauth_client.json`
6. Run auth flow:

```bash
python3 -c "
from src.connectors.youtube_api import get_authenticated_service
service = get_authenticated_service()
print('Auth successful')
"
```

---

## Configuration

`config/config.local.yaml`:

```yaml
env: local
transport: stdio          # NOTE[remote]: change to "http"
host: localhost           # NOTE[remote]: change to "0.0.0.0"
port: 8000
auth_enabled: false       # NOTE[remote]: change to true
storage_path: ./data      # NOTE[remote]: change to absolute path
embedding_model: all-MiniLM-L6-v2
sync_interval_minutes: 60
youtube_sync_enabled: false
obsidian_vault_path: ""   # Set to your vault path to enable
```

All `NOTE[remote]` markers indicate swap points for cloud deployment. Switch to HTTP transport by setting `PKB_ENV=remote` and updating `config/config.remote.yaml`.

---

## Usage

### Drop files into inbox

```bash
# Any .md, .txt, or .docx file dropped here is ingested automatically
cp my-notes.md data/watched/inbox/
# → within 2 seconds: chunked, embedded, searchable
```

### Ask Claude

```
# Semantic search
"What videos do I have saved about black holes?"
"Find my notes about machine learning transformers"

# Structured browse
"Show me all Kurzgesagt videos"
"Find chess videos shorter than 10 minutes"
"What did I save in 2023?"
"How many videos do I have in total?"

# RAG answers
"What do my saved notes say about neutron stars?"
"Summarise what I know about personal finance from my notes"

# Exact lookup
"Find the note with this URL: youtube.com/watch?v=..."
```

### Sync sources

```
"Sync my inbox"
"Sync my Obsidian vault"
"Sync my YouTube Watch Later playlist"
```

### Import YouTube playlist

```bash
# Import from CSV (Google Takeout export)
python3 scripts/import_youtube_playlist.py "Watch later videos.csv"
```

---

## Roadmap

### Phase 4 — Cloud connectors
- Apple Notes via AppleScript
- OneDrive via Microsoft Graph API + OAuth2
- Gmail via Google API + OAuth2
- Google Keep export watcher

### Phase 5 — Intelligence + polish
- Local LLM support (Ollama) for `answer_question` — sensitive notes never leave your machine
- Auto-tagging — extract topic tags per note automatically
- Entity extraction — people, organisations, dates
- Inbox processing tool — Claude helps batch-organise your inbox
- APScheduler — periodic background syncs
- CLI — `pkb sync`, `pkb search`, `pkb status`
- Remote hosting — FastAPI + API key auth + Tailscale/Cloudflare Tunnel

---

## Privacy

| Component | Where it runs | Data exposure |
|---|---|---|
| Embedding model | Local (your Mac) | None — text never leaves |
| SQLite + ChromaDB | Local (your Mac) | None |
| File watcher | Local (your Mac) | None |
| YouTube Data API | Google servers | Only video IDs (public metadata) |
| yt-dlp Watch Later | YouTube (authenticated) | Your playlist list |
| `answer_question` | Anthropic API | Top 5 matching note chunks |

The only data that leaves your machine during normal use is the context passed to the Anthropic API for `answer_question`. This can be replaced with a local Ollama model (planned Phase 5) for fully air-gapped operation.

---

## Tech stack

| Layer | Technology |
|---|---|
| MCP framework | `mcp` Python SDK |
| Embedding model | `sentence-transformers` — `all-MiniLM-L6-v2` (local) |
| Vector store | ChromaDB (persistent, local) |
| Full-text search | SQLite FTS5 |
| File parsing | `python-docx`, `pyyaml` |
| File watching | `watchdog` |
| YouTube metadata | YouTube Data API v3 + `yt-dlp` |
| Web enrichment | `httpx` |
| LLM (answers) | Anthropic API — `claude-3-5-haiku` |
| Scheduler | APScheduler (Phase 5) |
| HTTP transport | FastAPI + uvicorn (remote, stubbed) |

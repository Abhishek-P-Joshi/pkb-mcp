import sqlite3
from pathlib import Path
from src.config import config

class FTSStore:
    """
    Full-text search over note metadata using SQLite FTS5.
    NOTE[remote]: No code changes needed — only config.sqlite_path changes.
    """

    def __init__(self):
        self.db_path = config.sqlite_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS notes (
                    id          TEXT PRIMARY KEY,
                    source      TEXT NOT NULL,
                    content_type TEXT DEFAULT 'note',
                    title       TEXT,
                    url         TEXT,
                    tags        TEXT,
                    file_hash   TEXT,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    raw_text    TEXT
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
                USING fts5(
                    id UNINDEXED,
                    title,
                    raw_text,
                    tags,
                    content=notes,
                    content_rowid=rowid
                );

                CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                    INSERT INTO notes_fts(rowid, id, title, raw_text, tags)
                    VALUES (new.rowid, new.id, new.title, new.raw_text, new.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, id, title, raw_text, tags)
                    VALUES ('delete', old.rowid, old.id, old.title, old.raw_text, old.tags);
                    INSERT INTO notes_fts(rowid, id, title, raw_text, tags)
                    VALUES (new.rowid, new.id, new.title, new.raw_text, new.tags);
                END;
            """)

    def upsert(self, note: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO notes (id, source, content_type, title, url, tags, file_hash, raw_text, updated_at)
                VALUES (:id, :source, :content_type, :title, :url, :tags, :file_hash, :raw_text, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, raw_text=excluded.raw_text,
                    tags=excluded.tags, file_hash=excluded.file_hash,
                    updated_at=CURRENT_TIMESTAMP
            """, note)

    def _sanitize_fts_query(self, query: str) -> str:
        """Strip characters that have special meaning in FTS5 MATCH syntax."""
        import re
        sanitized = re.sub(r'[^\w\s]', ' ', query)
        sanitized = ' '.join(sanitized.split())
        return sanitized if sanitized else 'the'

    def search(self, query: str, content_type: str = None, limit: int = 20) -> list[dict]:
        query = self._sanitize_fts_query(query)
        with self._connect() as conn:
            if content_type:
                rows = conn.execute("""
                    SELECT n.* FROM notes n
                    JOIN notes_fts f ON n.id = f.id
                    WHERE notes_fts MATCH ? AND n.content_type = ?
                    ORDER BY rank LIMIT ?
                """, (query, content_type, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT n.* FROM notes n
                    JOIN notes_fts f ON n.id = f.id
                    WHERE notes_fts MATCH ?
                    ORDER BY rank LIMIT ?
                """, (query, limit)).fetchall()
            return [dict(r) for r in rows]

    def list_notes(
        self,
        content_type: str = None,
        source: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["1=1"]
        params = []
        if content_type:
            conditions.append("content_type = ?")
            params.append(content_type)
        if source:
            conditions.append("source = ?")
            params.append(source)
        params.extend([limit, offset])
        where = " AND ".join(conditions)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, title, content_type, source, url, tags, created_at "
                f"FROM notes WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def count_notes(self, content_type: str = None, source: str = None) -> int:
        conditions = ["1=1"]
        params = []
        if content_type:
            conditions.append("content_type = ?")
            params.append(content_type)
        if source:
            conditions.append("source = ?")
            params.append(source)
        where = " AND ".join(conditions)
        with self._connect() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM notes WHERE {where}", params
            ).fetchone()[0]

    def get_by_hash(self, file_hash: str, note_id: str = None) -> dict | None:
        with self._connect() as conn:
            if note_id is not None:
                row = conn.execute(
                    "SELECT * FROM notes WHERE file_hash = ? AND id = ?",
                    (file_hash, note_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM notes WHERE file_hash = ?", (file_hash,)
                ).fetchone()
            return dict(row) if row else None

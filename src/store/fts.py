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

                CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, id, title, raw_text, tags)
                    VALUES ('delete', old.rowid, old.id, old.title, old.raw_text, old.tags);
                END;
            """)

            new_columns = [
                "ALTER TABLE notes ADD COLUMN uploaded_at TEXT",
                "ALTER TABLE notes ADD COLUMN channel TEXT",
                "ALTER TABLE notes ADD COLUMN channel_id TEXT",
                "ALTER TABLE notes ADD COLUMN duration_seconds INTEGER",
                "ALTER TABLE notes ADD COLUMN duration_string TEXT",
                "ALTER TABLE notes ADD COLUMN view_count INTEGER",
                "ALTER TABLE notes ADD COLUMN like_count INTEGER",
                "ALTER TABLE notes ADD COLUMN categories TEXT",
                "ALTER TABLE notes ADD COLUMN language TEXT",
                "ALTER TABLE notes ADD COLUMN thumbnail_url TEXT",
                "ALTER TABLE notes ADD COLUMN status TEXT DEFAULT 'active'",
                "ALTER TABLE notes ADD COLUMN deleted_at TIMESTAMP",
                "ALTER TABLE notes ADD COLUMN deleted_from TEXT",
            ]
            for sql in new_columns:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notes_status
                ON notes(status)
            """)
            conn.commit()

    def upsert(self, note: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO notes (
                    id, source, content_type, title, url, tags, file_hash, raw_text,
                    uploaded_at, channel, channel_id, duration_seconds, duration_string,
                    view_count, like_count, categories, language, thumbnail_url,
                    updated_at
                )
                VALUES (
                    :id, :source, :content_type, :title, :url, :tags, :file_hash, :raw_text,
                    :uploaded_at, :channel, :channel_id, :duration_seconds, :duration_string,
                    :view_count, :like_count, :categories, :language, :thumbnail_url,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, raw_text=excluded.raw_text,
                    tags=excluded.tags, file_hash=excluded.file_hash,
                    uploaded_at=excluded.uploaded_at, channel=excluded.channel,
                    channel_id=excluded.channel_id, duration_seconds=excluded.duration_seconds,
                    duration_string=excluded.duration_string, view_count=excluded.view_count,
                    like_count=excluded.like_count, categories=excluded.categories,
                    language=excluded.language, thumbnail_url=excluded.thumbnail_url,
                    updated_at=CURRENT_TIMESTAMP
            """, {
                "id": note.get("id"),
                "source": note.get("source"),
                "content_type": note.get("content_type"),
                "title": note.get("title"),
                "url": note.get("url"),
                "tags": note.get("tags"),
                "file_hash": note.get("file_hash"),
                "raw_text": note.get("raw_text"),
                "uploaded_at": note.get("uploaded_at"),
                "channel": note.get("channel"),
                "channel_id": note.get("channel_id"),
                "duration_seconds": note.get("duration_seconds"),
                "duration_string": note.get("duration_string"),
                "view_count": note.get("view_count"),
                "like_count": note.get("like_count"),
                "categories": note.get("categories"),
                "language": note.get("language"),
                "thumbnail_url": note.get("thumbnail_url"),
            })

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
                    AND n.status = 'active'
                    ORDER BY rank LIMIT ?
                """, (query, content_type, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT n.* FROM notes n
                    JOIN notes_fts f ON n.id = f.id
                    WHERE notes_fts MATCH ?
                    AND n.status = 'active'
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
        conditions = ["1=1", "status = 'active'"]
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

    def list_ids_by_source(self, source: str) -> set:
        """
        Returns a set of all active note IDs for a given source.
        Used by delta reconciliation to find removed items.
        Fetches IDs only — no text columns — for efficiency.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM notes WHERE source = ? AND status = 'active'",
                (source,)
            ).fetchall()
            return {row[0] for row in rows}

    def filter_by_date(
        self,
        content_type: str = None,
        source: str = None,
        channel: str = None,
        language: str = None,
        categories: str = None,
        uploaded_after: str = None,
        uploaded_before: str = None,
        ingested_after: str = None,
        ingested_before: str = None,
        min_duration_seconds: int = None,
        max_duration_seconds: int = None,
        order_by: str = "ingested",
        order_dir: str = "DESC",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["1=1", "status = 'active'"]
        params = []
        if content_type:
            conditions.append("content_type = ?")
            params.append(content_type)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if channel:
            conditions.append("channel LIKE ?")
            params.append(f"%{channel}%")
        if language:
            conditions.append("language = ?")
            params.append(language)
        if categories:
            conditions.append("categories LIKE ?")
            params.append(f"%{categories}%")
        if uploaded_after:
            conditions.append("uploaded_at >= ?")
            params.append(uploaded_after)
        if uploaded_before:
            conditions.append("uploaded_at <= ?")
            params.append(uploaded_before)
        if ingested_after:
            conditions.append("created_at >= ?")
            params.append(ingested_after)
        if ingested_before:
            conditions.append("created_at <= ?")
            params.append(ingested_before)
        if min_duration_seconds is not None:
            conditions.append("duration_seconds >= ?")
            params.append(min_duration_seconds)
        if max_duration_seconds is not None:
            conditions.append("duration_seconds <= ?")
            params.append(max_duration_seconds)

        order_dir = "DESC" if order_dir.upper() == "DESC" else "ASC"
        order_expr = (
            "CASE WHEN ? = 'uploaded' THEN uploaded_at "
            "     WHEN ? = 'views'    THEN CAST(view_count AS TEXT) "
            "     ELSE created_at END"
        )

        where = " AND ".join(conditions)
        params_with_order = params + [order_by, order_by, limit, offset]

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, title, content_type, source, url, tags, "
                f"       channel, channel_id, uploaded_at, created_at, "
                f"       duration_string, view_count, like_count, "
                f"       categories, language, thumbnail_url "
                f"FROM notes WHERE {where} "
                f"ORDER BY {order_expr} {order_dir} "
                f"LIMIT ? OFFSET ?",
                params_with_order,
            ).fetchall()
        return [dict(r) for r in rows]

    def count_filtered(
        self,
        content_type: str = None,
        source: str = None,
        channel: str = None,
        language: str = None,
        categories: str = None,
        uploaded_after: str = None,
        uploaded_before: str = None,
        ingested_after: str = None,
        ingested_before: str = None,
        min_duration_seconds: int = None,
        max_duration_seconds: int = None,
    ) -> int:
        conditions = ["1=1", "status = 'active'"]
        params = []
        if content_type:
            conditions.append("content_type = ?")
            params.append(content_type)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if channel:
            conditions.append("channel LIKE ?")
            params.append(f"%{channel}%")
        if language:
            conditions.append("language = ?")
            params.append(language)
        if categories:
            conditions.append("categories LIKE ?")
            params.append(f"%{categories}%")
        if uploaded_after:
            conditions.append("uploaded_at >= ?")
            params.append(uploaded_after)
        if uploaded_before:
            conditions.append("uploaded_at <= ?")
            params.append(uploaded_before)
        if ingested_after:
            conditions.append("created_at >= ?")
            params.append(ingested_after)
        if ingested_before:
            conditions.append("created_at <= ?")
            params.append(ingested_before)
        if min_duration_seconds is not None:
            conditions.append("duration_seconds >= ?")
            params.append(min_duration_seconds)
        if max_duration_seconds is not None:
            conditions.append("duration_seconds <= ?")
            params.append(max_duration_seconds)

        where = " AND ".join(conditions)
        with self._connect() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM notes WHERE {where}", params
            ).fetchone()[0]

    def count_notes(self, content_type: str = None, source: str = None) -> int:
        conditions = ["1=1", "status = 'active'"]
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

    def get_by_id(self, note_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM notes WHERE id = ? AND status = 'active'", (note_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_by_id_any_status(self, note_id: str) -> dict | None:
        """Fetch a note by ID regardless of active/deleted status.
        Used by hard_delete to find notes that may be soft-deleted."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
            return dict(row) if row else None

    def soft_delete(self, note_id: str, deleted_from: str = 'user'):
        """
        Marks a note as deleted without removing it from the database.
        deleted_from: 'user' | 'playlist_removed' | 'file_deleted'
        """
        with self._connect() as conn:
            conn.execute("""
                UPDATE notes
                SET status = 'deleted',
                    deleted_at = CURRENT_TIMESTAMP,
                    deleted_from = ?
                WHERE id = ?
            """, (deleted_from, note_id))

    def hard_delete(self, note_id: str):
        """Permanently removes a note from the database."""
        with self._connect() as conn:
            conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    def restore(self, note_id: str):
        """Reverses a soft delete, making the note active again."""
        with self._connect() as conn:
            conn.execute("""
                UPDATE notes
                SET status = 'active',
                    deleted_at = NULL,
                    deleted_from = NULL
                WHERE id = ?
            """, (note_id,))

    def list_deleted(
        self,
        content_type: str = None,
        source: str = None,
        deleted_after: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Lists soft-deleted notes for review or restoration."""
        query = """
            SELECT id, title, content_type, source, url,
                   deleted_at, deleted_from, channel
            FROM notes
            WHERE status = 'deleted'
        """
        params = []
        if content_type:
            query += " AND content_type = ?"
            params.append(content_type)
        if source:
            query += " AND source = ?"
            params.append(source)
        if deleted_after:
            query += " AND deleted_at >= ?"
            params.append(deleted_after)
        query += " ORDER BY deleted_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def purge(self, older_than_days: int = 90) -> int:
        """
        Hard-deletes notes that have been soft-deleted for longer
        than older_than_days. Returns the number of rows purged.
        Run this periodically to keep the database from growing.
        """
        with self._connect() as conn:
            result = conn.execute("""
                DELETE FROM notes
                WHERE status = 'deleted'
                AND deleted_at < datetime('now', ? || ' days')
            """, (f"-{older_than_days}",))
            return result.rowcount

    def get_by_hash(self, file_hash: str, note_id: str = None) -> dict | None:
        with self._connect() as conn:
            if note_id is not None:
                row = conn.execute(
                    "SELECT * FROM notes WHERE file_hash = ? AND id = ? AND status = 'active'",
                    (file_hash, note_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM notes WHERE file_hash = ? AND status = 'active'",
                    (file_hash,),
                ).fetchone()
            return dict(row) if row else None

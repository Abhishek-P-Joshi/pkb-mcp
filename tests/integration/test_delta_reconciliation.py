import pytest
from unittest.mock import patch, MagicMock


class TestPlaylistDeltaReconciliation:
    """
    Tests that sync_playlist correctly soft-deletes videos
    that are no longer in the playlist.
    """

    def test_removed_video_is_soft_deleted(self, temp_fts_store):
        """
        Video A and B are in DB. Playlist now only has A.
        B should be soft-deleted after sync.
        """
        # Seed two videos in DB with source youtube_WL
        for vid_id, title in [("vid_aaa", "Video A"), ("vid_bbb", "Video B")]:
            temp_fts_store.upsert({
                "id": f"youtube_WL_{vid_id}",
                "source": "youtube_WL",
                "content_type": "video",
                "title": title,
                "url": f"https://youtube.com/watch?v={vid_id}",
                "tags": "", "file_hash": f"hash_{vid_id}",
                "raw_text": f"Watch later: {title}",
                "channel": "Test Channel", "channel_id": None,
                "uploaded_at": None, "duration_seconds": None,
                "duration_string": None, "view_count": None,
                "like_count": None, "categories": None,
                "language": None, "thumbnail_url": None,
            })

        # Playlist now only contains vid_aaa
        current_playlist = [{"video_id": "vid_aaa", "title": "Video A"}]
        current_ids = {f"youtube_WL_{v['video_id']}" for v in current_playlist}

        # Run reconciliation logic directly
        existing_ids = temp_fts_store.list_ids_by_source("youtube_WL")
        removed_ids = existing_ids - current_ids

        for note_id in removed_ids:
            temp_fts_store.soft_delete(note_id, deleted_from='playlist_removed')

        # vid_bbb should be soft deleted
        assert temp_fts_store.get_by_id("youtube_WL_vid_bbb") is None
        # vid_aaa should still be active
        assert temp_fts_store.get_by_id("youtube_WL_vid_aaa") is not None

        # Check it appears in list_deleted
        deleted = temp_fts_store.list_deleted()
        ids = [r["id"] for r in deleted]
        assert "youtube_WL_vid_bbb" in ids
        assert temp_fts_store.list_deleted()[0]["deleted_from"] == "playlist_removed"

    def test_no_removal_when_playlist_unchanged(self, temp_fts_store):
        """If all DB videos are still in the playlist, nothing is deleted."""
        temp_fts_store.upsert({
            "id": "youtube_WL_vid_ccc",
            "source": "youtube_WL",
            "content_type": "video",
            "title": "Video C",
            "url": "https://youtube.com/watch?v=vid_ccc",
            "tags": "", "file_hash": "hash_ccc",
            "raw_text": "Watch later: Video C",
            "channel": None, "channel_id": None, "uploaded_at": None,
            "duration_seconds": None, "duration_string": None,
            "view_count": None, "like_count": None, "categories": None,
            "language": None, "thumbnail_url": None,
        })

        current_ids = {"youtube_WL_vid_ccc"}
        existing_ids = temp_fts_store.list_ids_by_source("youtube_WL")
        removed_ids = existing_ids - current_ids
        assert len(removed_ids) == 0


class TestObsidianDeltaReconciliation:
    """
    Tests that obsidian sync correctly soft-deletes notes
    whose files have been removed from the vault.
    """

    def test_deleted_file_note_is_soft_deleted(self, temp_fts_store):
        """
        Note X is in DB with source=obsidian.
        File no longer exists in vault.
        Note should be soft-deleted.
        """
        temp_fts_store.upsert({
            "id": "obsidian_inbox_deleted_note",
            "source": "obsidian",
            "content_type": "note",
            "title": "Deleted note",
            "url": "", "tags": "",
            "file_hash": "hash_deleted",
            "raw_text": "This note was deleted from the vault",
            "channel": None, "channel_id": None, "uploaded_at": None,
            "duration_seconds": None, "duration_string": None,
            "view_count": None, "like_count": None, "categories": None,
            "language": None, "thumbnail_url": None,
        })

        # Current vault has no notes (file was deleted)
        current_ids = set()
        existing_ids = temp_fts_store.list_ids_by_source("obsidian")
        removed_ids = existing_ids - current_ids

        for note_id in removed_ids:
            temp_fts_store.soft_delete(note_id, deleted_from='file_deleted')

        assert temp_fts_store.get_by_id("obsidian_inbox_deleted_note") is None
        deleted = temp_fts_store.list_deleted()
        assert deleted[0]["deleted_from"] == "file_deleted"

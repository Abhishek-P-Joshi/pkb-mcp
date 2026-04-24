from pathlib import Path
from src.connectors.file_parser import FileParser
from src.connectors.hasher import hash_file
from src.store import storage
from src.pipeline.ingest import IngestPipeline

_parser = FileParser()


class ObsidianConnector:
    """Scans an Obsidian vault for Markdown notes and syncs them into the PKB."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        if not self.vault_path.exists():
            raise FileNotFoundError(f"Vault path not found: {self.vault_path}")

    def get_all_notes(self) -> list[dict]:
        notes = []
        for md_file in self.vault_path.rglob("*.md"):
            # Skip files inside hidden folders (e.g. .obsidian/, .trash/)
            if any(part.startswith(".") for part in md_file.relative_to(self.vault_path).parts[:-1]):
                continue

            result = _parser.parse(str(md_file))

            # Build a stable ID from the relative path
            rel = md_file.relative_to(self.vault_path).with_suffix("")
            note_id = "obsidian_" + str(rel).replace("/", "_").replace(" ", "_")

            result["source"] = "obsidian"
            result["note_id"] = note_id
            result["file_hash"] = hash_file(str(md_file))

            notes.append(result)
        return notes

    def get_changed_notes(self) -> list[dict]:
        all_notes = self.get_all_notes()
        return [
            note for note in all_notes
            if storage.fts.get_by_hash(note["file_hash"]) is None
        ]

    def sync(self) -> dict:
        changed = self.get_changed_notes()
        pipeline = IngestPipeline()
        synced = 0
        skipped = 0
        removed = 0
        errors = []

        # Delta removal — soft-delete notes no longer present in the vault
        current_note_ids = {n["note_id"] for n in self.get_all_notes()}
        db_notes = storage.fts.list_notes(source="obsidian", limit=100000)
        for db_note in db_notes:
            if db_note["id"] not in current_note_ids:
                storage.fts.soft_delete(db_note["id"], deleted_from="file_deleted")
                storage.vector.delete_by_note_id(db_note["id"])
                removed += 1

        for note in changed:
            if note.get("error"):
                errors.append({"note_id": note["note_id"], "error": note["error"]})
                continue
            try:
                result = pipeline.ingest(
                    text=note["text"],
                    source=note["source"],
                    note_id=note["note_id"],
                    file_hash=note["file_hash"],
                )
                if result["status"] == "skipped":
                    skipped += 1
                else:
                    synced += 1
            except Exception as e:
                errors.append({"note_id": note["note_id"], "error": str(e)})

        return {"synced": synced, "skipped": skipped, "removed": removed, "errors": errors}


if __name__ == "__main__":
    import tempfile
    import shutil
    import os

    # Create a temporary vault
    vault_dir = tempfile.mkdtemp(prefix="obsidian_vault_")

    # Note 1: with frontmatter
    (Path(vault_dir) / "welcome.md").write_text(
        "---\ntitle: Welcome Note\ntags:\n  - intro\n  - setup\n---\n\n"
        "# Welcome\n\nThis is the first note in the vault.",
        encoding="utf-8",
    )

    # Note 2: plain markdown, no frontmatter
    projects_dir = Path(vault_dir) / "projects"
    projects_dir.mkdir()
    (projects_dir / "my_project.md").write_text(
        "# My Project\n\nThis project tracks all PKB development tasks.",
        encoding="utf-8",
    )

    # Hidden folder — should be skipped
    hidden_dir = Path(vault_dir) / ".obsidian"
    hidden_dir.mkdir()
    (hidden_dir / "config.md").write_text("internal obsidian config", encoding="utf-8")

    connector = ObsidianConnector(vault_dir)
    notes = connector.get_all_notes()

    print(f"Found {len(notes)} notes (hidden folder correctly skipped)\n")
    for note in notes:
        print(f"  note_id:     {note['note_id']}")
        print(f"  title:       {note['title']}")
        print(f"  source:      {note['source']}")
        print(f"  file_hash:   {note['file_hash']}")
        print(f"  frontmatter: {note['frontmatter']}")
        print(f"  text[:80]:   {note['text'][:80]!r}")
        print()

    shutil.rmtree(vault_dir)
    print("Temp vault cleaned up.")

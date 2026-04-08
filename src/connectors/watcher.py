import sys
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.connectors.file_parser import FileParser
from src.connectors.hasher import hash_file
from src.pipeline.ingest import pipeline


class PKBEventHandler(FileSystemEventHandler):
    """Handles file system events and ingests new/modified files."""

    def __init__(self, supported_extensions=None):
        super().__init__()
        self.supported_extensions = supported_extensions or [".md", ".txt", ".docx"]
        self._parser = FileParser()
        self._pipeline = pipeline  # shared singleton — model loaded only once
        self._processing = set()

    def on_created(self, event):
        self._handle(event)

    def on_modified(self, event):
        self._handle(event)

    def _handle(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.suffix.lower() not in self.supported_extensions:
            return

        if str(path) in self._processing:
            return

        self._processing.add(str(path))
        try:
            result = self._parser.parse(str(path))
            if result.get("error"):
                print(f"[watcher] Parse error for {path.name}: {result['error']}", file=sys.stderr)
                return

            file_hash = hash_file(str(path))
            note_id = "inbox_" + path.stem

            ingest_result = self._pipeline.ingest(
                text=result["text"],
                source="inbox",
                file_hash=file_hash,
                note_id=note_id,
            )

            if ingest_result["status"] == "skipped":
                print(f"[watcher] Skipped (unchanged): {path.name}", file=sys.stderr)
            else:
                print(
                    f"Ingested: {path.name} "
                    f"({ingest_result['content_type']}, {ingest_result['chunks']} chunks)",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"[watcher] Error processing {path.name}: {e}", file=sys.stderr)
        finally:
            self._processing.discard(str(path))


class FolderWatcher:
    """Watches a folder and ingests any supported files that appear or change."""

    def __init__(self, watch_path: str):
        self.watch_path = Path(watch_path)
        self._handler = PKBEventHandler()
        self._observer = Observer()

    def start(self):
        self._observer.schedule(self._handler, str(self.watch_path), recursive=True)
        self._observer.start()
        print(f"Watching {self.watch_path} for changes...", file=sys.stderr)

    def stop(self):
        self._observer.stop()
        self._observer.join()


if __name__ == "__main__":
    watch_path = sys.argv[1] if len(sys.argv) > 1 else "data/watched/inbox"
    watcher = FolderWatcher(watch_path)
    watcher.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    watcher.stop()
    print("Watcher stopped.", file=sys.stderr)

import uuid
from src.pipeline.chunker import TextChunker
from src.pipeline.embedder import Embedder
from src.pipeline.enricher import URLEnricher
from src.pipeline.classifier import detect_urls, classify_content
from src.store import storage


class IngestPipeline:
    """
    Central pipeline: text → chunk → embed → classify → store.
    Ties together chunker, embedder, enricher, classifier, and StorageManager.
    """

    def __init__(self):
        self.chunker = TextChunker()
        self.embedder = Embedder()
        self.enricher = URLEnricher()

    def ingest(
        self,
        text: str,
        source: str,
        note_id: str = None,
        file_hash: str = None,
    ) -> dict:
        # 1. Skip if file unchanged
        if file_hash and storage.fts.get_by_hash(file_hash, note_id):
            return {"status": "skipped", "reason": "unchanged"}

        # 2. Detect URLs
        urls = detect_urls(text)

        # 3. Enrich first URL if present
        title = ""
        description = ""
        channel = ""
        tags = ""
        first_url = urls[0] if urls else ""
        if first_url:
            meta = self.enricher.enrich(first_url)
            title = meta.get("title", "")
            description = meta.get("description", "")
            channel = meta.get("channel", "")
            tags = meta.get("tags", "")

        # 4. Classify content type
        content_type = classify_content(text, urls)

        # 5. Build enriched text for embedding (and FTS storage)
        enriched_suffix = ""
        if title:
            enriched_suffix += f"\n\nTitle: {title}"
        if channel:
            enriched_suffix += f"\nChannel: {channel}"
        if description:
            enriched_suffix += f"\nDescription: {description}"
        if tags:
            enriched_suffix += f"\nTags: {tags}"
        text_to_embed = text + enriched_suffix

        # 6. Chunk
        chunks = self.chunker.chunk(text_to_embed)

        # 7. Batch embed all chunks
        chunk_texts = [c["text"] for c in chunks]
        embeddings = self.embedder.embed_texts(chunk_texts)

        # 8. Upsert parent note into FTS
        if not note_id:
            note_id = str(uuid.uuid4())

        storage.fts.upsert({
            "id": note_id,
            "source": source,
            "content_type": content_type,
            "title": title or text[:60],
            "url": first_url,
            "tags": "",
            "file_hash": file_hash or "",
            "raw_text": text_to_embed,
        })

        # 9. Upsert chunks into vector store
        vector_chunks = [
            {
                "id": f"{note_id}_chunk_{i}",
                "text": chunk_texts[i],
                "metadata": {
                    "note_id": note_id,
                    "source": source,
                    "content_type": content_type,
                    "title": title or text[:60],
                    "url": first_url,
                },
            }
            for i in range(len(chunks))
        ]
        # Attach pre-computed embeddings directly to avoid re-embedding
        storage.vector._get_collection().upsert(
            ids=[c["id"] for c in vector_chunks],
            embeddings=embeddings,
            documents=chunk_texts,
            metadatas=[c["metadata"] for c in vector_chunks],
        )

        # 10. Return summary
        return {
            "status": "ok",
            "note_id": note_id,
            "chunks": len(chunks),
            "content_type": content_type,
            "title": title or text[:60],
        }


# Shared singleton — import this from both tools and connectors
pipeline = IngestPipeline()

if __name__ == "__main__":
    _pipeline = IngestPipeline()

    test_text = (
        "Just watched this classic: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        "An absolute banger that never gets old. The 80s production is timeless."
    )

    print("Ingesting test note...\n")
    result = _pipeline.ingest(
        text=test_text,
        source="test",
        note_id="test-note-001",
    )
    print(result)

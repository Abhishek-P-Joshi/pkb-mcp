import chromadb
from sentence_transformers import SentenceTransformer
from src.config import config

class VectorStore:
    """
    Semantic search using ChromaDB + sentence-transformers.
    NOTE[remote]: No code changes needed — only config.chroma_path changes.
    """

    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(config.chroma_path))
        self.collection = self.client.get_or_create_collection(
            name="pkb_notes",
            metadata={"hnsw:space": "cosine"},
        )
        # Loaded once at startup — ~90MB, runs fully locally
        self._model = SentenceTransformer(config.embedding_model)

    def _get_collection(self):
        try:
            return self.collection
        except Exception:
            self.collection = self.client.get_or_create_collection(
                name="pkb_notes",
                metadata={"hnsw:space": "cosine"},
            )
            return self.collection

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, show_progress_bar=False).tolist()

    def upsert(self, chunks: list[dict]):
        """
        chunks: list of {id, text, metadata}
        metadata should include: source, content_type, note_id, title
        """
        ids = [c["id"] for c in chunks]
        texts = [c["text"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]
        embeddings = self.embed(texts)

        self._get_collection().upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    def search(self, query: str, content_type: str = None, n_results: int = 10) -> list[dict]:
        where = {"content_type": content_type} if content_type else None
        query_embedding = self.embed([query])[0]

        results = self._get_collection().query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        for i, doc_id in enumerate(results["ids"][0]):
            hits.append({
                "id": doc_id,
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": round(1 - results["distances"][0][i], 3),
            })
        return hits

    def delete_by_note_id(self, note_id: str):
        """
        Removes all chunks belonging to a note from ChromaDB.
        Called alongside FTSStore.hard_delete() for full removal.
        For soft deletes this is NOT called — chunks stay in ChromaDB
        but are never returned because the SQLite row is filtered out
        at the application layer.
        """
        try:
            self._get_collection().delete(
                where={"note_id": {"$eq": note_id}}
            )
        except Exception as e:
            import sys
            print(f"[vector] Could not delete chunks for {note_id}: {e}",
                  file=sys.stderr)

from sentence_transformers import SentenceTransformer
from src.config import config


class Embedder:
    """
    Wraps sentence-transformers for batch and single-text embedding.
    Model is loaded once at init and reused for all subsequent calls.
    """

    def __init__(self):
        print(f"Loading embedding model: {config.embedding_model}...")
        self._model = SentenceTransformer(config.embedding_model)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, show_progress_bar=False).tolist()

    def embed_one(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


if __name__ == "__main__":
    import math

    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b)

    embedder = Embedder()

    similar_1 = "The cat sat on the mat."
    similar_2 = "A cat was sitting on a mat."
    unrelated_1 = "The stock market crashed yesterday."
    unrelated_2 = "She baked a chocolate cake for the party."

    sentences = [similar_1, similar_2, unrelated_1, unrelated_2]
    vectors = embedder.embed_texts(sentences)

    sim_similar = cosine_similarity(vectors[0], vectors[1])
    sim_unrelated = cosine_similarity(vectors[2], vectors[3])
    sim_cross = cosine_similarity(vectors[0], vectors[2])

    print(f"\nSimilar pair:   {sim_similar:.4f}  ← should be > 0.8")
    print(f"  '{similar_1}'")
    print(f"  '{similar_2}'")

    print(f"\nUnrelated pair: {sim_unrelated:.4f}  ← should be < 0.3")
    print(f"  '{unrelated_1}'")
    print(f"  '{unrelated_2}'")

    print(f"\nCross pair:     {sim_cross:.4f}  ← should be low")
    print(f"  '{similar_1}'")
    print(f"  '{unrelated_1}'")

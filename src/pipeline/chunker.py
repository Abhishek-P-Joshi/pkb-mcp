import re


class TextChunker:
    """
    Splits long text into overlapping chunks suitable for embedding.

    Chunk size is specified in approximate tokens (1 token ≈ 0.75 words).
    Overlap ensures context is not lost at chunk boundaries.
    """

    def __init__(self, chunk_size_tokens: int = 512, overlap_words: int = 50):
        # 1 token ≈ 0.75 words → 512 tokens ≈ 384 words
        self.chunk_size_words = int(chunk_size_tokens * 0.75)
        self.overlap_words = overlap_words

    def _clean(self, text: str) -> str:
        # Collapse multiple blank lines and strip leading/trailing whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    def chunk(self, text: str) -> list[dict]:
        text = self._clean(text)
        words = text.split()

        if len(words) <= self.chunk_size_words:
            return [{"text": text, "index": 0, "total": 1}]

        chunks = []
        start = 0
        step = self.chunk_size_words - self.overlap_words

        while start < len(words):
            end = start + self.chunk_size_words
            chunk_words = words[start:end]
            chunks.append(" ".join(chunk_words))
            if end >= len(words):
                break
            start += step

        total = len(chunks)
        return [
            {"text": chunk, "index": i, "total": total}
            for i, chunk in enumerate(chunks)
        ]


if __name__ == "__main__":
    # Quick test: 1000-word string
    word = "knowledge"
    long_text = " ".join([f"{word}{i}" for i in range(1000)])

    chunker = TextChunker()
    results = chunker.chunk(long_text)

    print(f"Input: 1000 words → {len(results)} chunks\n")
    for c in results:
        print(f"Chunk {c['index']}: {len(c['text'].split())} words")

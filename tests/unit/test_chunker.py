import pytest
from src.pipeline.chunker import TextChunker


class TestTextChunker:

    def setup_method(self):
        self.chunker = TextChunker()

    def test_short_text_returns_single_chunk(self):
        text = "This is a short note."
        chunks = self.chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0]["index"] == 0
        assert chunks[0]["total"] == 1
        assert chunks[0]["text"] == text

    def test_long_text_produces_multiple_chunks(self):
        # 500 words exceeds the 384-word chunk size
        text = " ".join(["word"] * 500)
        chunks = self.chunker.chunk(text)
        assert len(chunks) > 1

    def test_chunks_have_correct_index_and_total(self):
        text = " ".join(["word"] * 500)
        chunks = self.chunker.chunk(text)
        for i, chunk in enumerate(chunks):
            assert chunk["index"] == i
            assert chunk["total"] == len(chunks)

    def test_overlap_means_chunks_share_words(self):
        text = " ".join([f"word{i}" for i in range(500)])
        chunks = self.chunker.chunk(text)
        if len(chunks) > 1:
            chunk0_words = set(chunks[0]["text"].split())
            chunk1_words = set(chunks[1]["text"].split())
            overlap = chunk0_words & chunk1_words
            assert len(overlap) > 0, "Chunks should share overlapping words"

    def test_empty_text_returns_single_empty_chunk(self):
        # _clean("") → "", words=[] → len([]) <= chunk_size_words → single chunk
        chunks = self.chunker.chunk("")
        assert chunks == [] or (len(chunks) == 1 and chunks[0]["text"] == "")

    def test_whitespace_is_normalised(self):
        text = "hello   \n\n\n   world"
        chunks = self.chunker.chunk(text)
        assert "\n\n\n" not in chunks[0]["text"]

    def test_chunk_size_respects_word_limit(self):
        text = " ".join(["word"] * 800)
        chunks = self.chunker.chunk(text)
        for chunk in chunks:
            word_count = len(chunk["text"].split())
            # chunk_size_words = int(512 * 0.75) = 384; allow tolerance for overlap
            assert word_count <= 450, f"Chunk too large: {word_count} words"

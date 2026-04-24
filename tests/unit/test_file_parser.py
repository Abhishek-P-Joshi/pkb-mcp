import pytest
from pathlib import Path
from src.connectors.file_parser import FileParser


class TestFileParser:

    def setup_method(self):
        self.parser = FileParser()

    def test_parses_txt_file(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_text("Hello world this is a plain text note.")
        result = self.parser.parse(str(f))
        assert result["error"] is None
        assert "Hello world" in result["text"]
        assert result["extension"] == ".txt"
        assert result["title"] == "note"

    def test_parses_markdown_without_frontmatter(self, tmp_path):
        f = tmp_path / "my_note.md"
        f.write_text("# My Note\n\nSome content here.")
        result = self.parser.parse(str(f))
        assert result["error"] is None
        assert "Some content" in result["text"]
        assert result["extension"] == ".md"

    def test_parses_markdown_with_frontmatter(self, tmp_path):
        content = "---\ntitle: My Custom Title\ntags: chess, science\n---\n\nBody content here."
        f = tmp_path / "note.md"
        f.write_text(content)
        result = self.parser.parse(str(f))
        assert result["error"] is None
        assert result["title"] == "My Custom Title"
        assert "chess" in result["frontmatter"].get("tags", "")
        assert "Body content" in result["text"]
        assert "---" not in result["text"]

    def test_title_falls_back_to_filename(self, tmp_path):
        f = tmp_path / "my_note_file.md"
        f.write_text("Some content")
        result = self.parser.parse(str(f))
        assert result["title"] == "my note file"

    def test_unsupported_extension_raises_error(self, tmp_path):
        f = tmp_path / "file.pdf"
        f.write_text("content")
        with pytest.raises(ValueError):
            self.parser.parse(str(f))

    def test_underscores_hyphens_in_filename_replaced_with_spaces(self, tmp_path):
        f = tmp_path / "my-note_file.md"
        f.write_text("Content")
        result = self.parser.parse(str(f))
        assert result["title"] == "my note file"

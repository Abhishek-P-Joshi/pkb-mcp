import hashlib


def hash_file(file_path: str) -> str:
    """Compute MD5 hex digest of a file, reading in 8KB chunks."""
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            md5.update(chunk)
    return md5.hexdigest()


def hash_text(text: str) -> str:
    """Compute MD5 hex digest of a UTF-8 encoded string."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("Hello, PKB!")
        tmp_path = f.name

    hash1 = hash_file(tmp_path)
    hash2 = hash_file(tmp_path)
    print(f"Hash 1:       {hash1}")
    print(f"Hash 2:       {hash2}")
    print(f"Same result:  {hash1 == hash2}")

    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("Hello, PKB! (modified)")

    hash3 = hash_file(tmp_path)
    print(f"\nAfter change: {hash3}")
    print(f"Hash changed: {hash1 != hash3}")

    os.unlink(tmp_path)
    print("\nTemp file cleaned up.")

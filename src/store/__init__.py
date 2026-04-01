from src.store.fts import FTSStore
from src.store.vector import VectorStore

class StorageManager:
    """Single entry point for all storage. Import this, not FTSStore/VectorStore directly."""
    def __init__(self):
        self.fts = FTSStore()
        self.vector = VectorStore()

# Shared singleton — import storage from src.store
storage = StorageManager()

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

@dataclass
class Config:
    env: str
    transport: str
    host: str
    port: int
    auth_enabled: bool
    storage_path: Path
    embedding_model: str
    sync_interval_minutes: int

    @property
    def chroma_path(self) -> Path:
        return self.storage_path / "chroma"

    @property
    def sqlite_path(self) -> Path:
        return self.storage_path / "sqlite" / "pkb.db"

def load_config() -> Config:
    env = os.getenv("PKB_ENV", "local")
    config_file = ROOT / "config" / f"config.{env}.yaml"

    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")

    with open(config_file) as f:
        raw = yaml.safe_load(f)

    storage_path = (ROOT / raw["storage_path"]).resolve() if not Path(raw["storage_path"]).is_absolute() else Path(raw["storage_path"])
    storage_path.mkdir(parents=True, exist_ok=True)
    (storage_path / "chroma").mkdir(exist_ok=True)
    (storage_path / "sqlite").mkdir(exist_ok=True)

    return Config(
        env=raw["env"],
        transport=raw["transport"],
        host=raw["host"],
        port=raw["port"],
        auth_enabled=raw["auth_enabled"],
        storage_path=storage_path,
        embedding_model=raw["embedding_model"],
        sync_interval_minutes=raw["sync_interval_minutes"],
    )

# Single shared instance — import this everywhere
config = load_config()

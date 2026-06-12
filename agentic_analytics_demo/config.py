from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
KEY_FILE = ROOT_DIR / "key.txt"


def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path
    db_path: Path
    chroma_dir: Path
    gemini_api_key: str
    gemini_key_source: str
    gemini_model: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        data_dir = Path(os.getenv("DEMO_DATA_DIR", ROOT_DIR / "data"))
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        gemini_key_source = "environment/.env" if gemini_api_key else "missing"
        if not gemini_api_key and KEY_FILE.exists():
            key_text = KEY_FILE.read_text(encoding="utf-8").strip()
            gemini_api_key = key_text.removeprefix("GEMINI_API_KEY=").strip()
            gemini_key_source = "key.txt" if gemini_api_key else "missing"
        return cls(
            data_dir=data_dir,
            db_path=Path(os.getenv("DEMO_DB_PATH", data_dir / "analytics_demo.sqlite")),
            chroma_dir=Path(os.getenv("DEMO_CHROMA_DIR", data_dir / "chroma")),
            gemini_api_key=gemini_api_key,
            gemini_key_source=gemini_key_source,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        )

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
KEY_FILE = ROOT_DIR / "key.txt"
GVMZ_KEY_FILE = ROOT_DIR / "key2.txt"


def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path
    dataset_dir: Path
    db_path: Path
    chroma_dir: Path
    gemini_api_key: str
    gemini_key_source: str
    gemini_model: str
    gvmz_api_key: str
    gvmz_key_source: str
    gvmz_base_url: str
    gvmz_model: str
    llm_provider: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        data_dir = Path(os.getenv("DEMO_DATA_DIR", ROOT_DIR / "data"))
        dataset_dir = Path(os.getenv("DEMO_DATASET_DIR", ROOT_DIR / "dataset"))
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        gemini_key_source = "environment/.env" if gemini_api_key else "missing"
        if not gemini_api_key and KEY_FILE.exists():
            key_text = KEY_FILE.read_text(encoding="utf-8").strip()
            gemini_api_key = key_text.removeprefix("GEMINI_API_KEY=").strip()
            gemini_key_source = "key.txt" if gemini_api_key else "missing"

        gvmz_api_key = os.getenv("GVMZ_API_KEY", "").strip()
        gvmz_key_source = "environment/.env" if gvmz_api_key else "missing"
        if not gvmz_api_key and GVMZ_KEY_FILE.exists():
            key_text = GVMZ_KEY_FILE.read_text(encoding="utf-8").strip()
            gvmz_api_key = key_text.removeprefix("GVMZ_API_KEY=").strip()
            gvmz_key_source = "key2.txt" if gvmz_api_key else "missing"

        requested_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        if requested_provider in {"gvmz", "gemini", "fallback"}:
            llm_provider = requested_provider
        else:
            llm_provider = "gvmz" if gvmz_api_key else "gemini"

        return cls(
            data_dir=data_dir,
            dataset_dir=dataset_dir,
            db_path=Path(os.getenv("DEMO_DB_PATH", data_dir / "retailrocket.sqlite")),
            chroma_dir=Path(os.getenv("DEMO_CHROMA_DIR", data_dir / "chroma")),
            gemini_api_key=gemini_api_key,
            gemini_key_source=gemini_key_source,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            gvmz_api_key=gvmz_api_key,
            gvmz_key_source=gvmz_key_source,
            gvmz_base_url=os.getenv("GVMZ_BASE_URL", "https://gvmz.systems/v1").strip().rstrip("/"),
            gvmz_model=os.getenv("GVMZ_MODEL", "gemini-3-flash-preview").strip(),
            llm_provider=llm_provider,
        )

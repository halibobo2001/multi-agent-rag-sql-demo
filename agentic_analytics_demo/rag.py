from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from pathlib import Path

from .schema_docs import SCHEMA_DOCUMENTS, SchemaDocument


@dataclass(frozen=True)
class RetrievedContext:
    title: str
    text: str
    score: float


class HashEmbeddingFunction:
    """Small deterministic embedding function for Chroma without external model downloads."""

    def __init__(self, dimensions: int = 64):
        self.dimensions = dimensions

    @staticmethod
    def name() -> str:
        return "demo-hash-embedding"

    def __call__(self, input):  # Chroma calls this exact signature.
        return [self._embed(text) for text in input]

    def embed_query(self, input):
        return self(input)

    def embed_documents(self, input):
        return self(input)

    def is_legacy(self) -> bool:
        return False

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> dict[str, int]:
        return {"dimensions": self.dimensions}

    @staticmethod
    def build_from_config(config: dict[str, int]) -> "HashEmbeddingFunction":
        return HashEmbeddingFunction(dimensions=int(config.get("dimensions", 64)))

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _tokenize(text)
        for token in tokens:
            vector[zlib.crc32(token.encode("utf-8")) % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class SchemaRAG:
    def __init__(self, persist_dir: Path):
        self.persist_dir = persist_dir
        self._collection = None
        self.backend = "keyword"

    def ensure_index(self) -> None:
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = client.get_or_create_collection(
                name="schema_knowledge",
                embedding_function=HashEmbeddingFunction(),
            )
            self._collection.upsert(
                ids=[doc.doc_id for doc in SCHEMA_DOCUMENTS],
                documents=[f"{doc.title}\n{doc.text}" for doc in SCHEMA_DOCUMENTS],
                metadatas=[{"title": doc.title} for doc in SCHEMA_DOCUMENTS],
            )
            self.backend = "chromadb"
        except Exception:
            self._collection = None
            self.backend = "keyword"

    def retrieve(self, question: str, top_k: int = 5) -> list[RetrievedContext]:
        if self._collection is not None:
            try:
                result = self._collection.query(query_texts=[question], n_results=top_k)
                documents = result.get("documents", [[]])[0]
                metadatas = result.get("metadatas", [[]])[0]
                distances = result.get("distances", [[]])[0]
                contexts = []
                for index, document in enumerate(documents):
                    title = metadatas[index].get("title", "Schema") if index < len(metadatas) else "Schema"
                    distance = distances[index] if index < len(distances) else 1.0
                    contexts.append(RetrievedContext(title=title, text=document, score=1.0 / (1.0 + distance)))
                return contexts
            except Exception:
                self.backend = "keyword"
                self._collection = None
        return self._keyword_retrieve(question, top_k)

    def _keyword_retrieve(self, question: str, top_k: int) -> list[RetrievedContext]:
        query_tokens = set(_tokenize(question))
        scored: list[tuple[float, SchemaDocument]] = []
        for doc in SCHEMA_DOCUMENTS:
            doc_tokens = set(_tokenize(f"{doc.title} {doc.text}"))
            score = len(query_tokens & doc_tokens) / max(1, len(query_tokens))
            if any(keyword in question.lower() for keyword in ["转化", "conversion", "funnel"]):
                score += 0.25 if "conversion" in doc.doc_id or "conversions" in doc.text else 0
            if any(keyword in question.lower() for keyword in ["实验", "variant", "a/b", "ab"]):
                score += 0.25 if "experiment" in doc.doc_id or "experiments" in doc.text else 0
            if any(keyword in question.lower() for keyword in ["国家", "country", "德国", "germany"]):
                score += 0.2 if "country" in doc.text or doc.doc_id == "users" else 0
            scored.append((score, doc))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedContext(title=doc.title, text=doc.text, score=round(score, 3))
            for score, doc in scored[:top_k]
        ]


def _tokenize(text: str) -> list[str]:
    normalized = text.lower()
    for char in "()[],.;:_/+-":
        normalized = normalized.replace(char, " ")
    tokens = [token for token in normalized.split() if token]
    chinese_hints = ["国家", "德国", "转化", "漏斗", "实验", "收入", "设备", "活跃", "会话", "功能"]
    tokens.extend(hint for hint in chinese_hints if hint in text)
    return tokens

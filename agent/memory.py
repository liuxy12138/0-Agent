import json
import math
import hashlib
from pathlib import Path
from typing import Any


class LongTermMemory:
    """Small persistent vector memory. Uses FAISS if installed, otherwise pure Python cosine search."""

    def __init__(self, path: str = "data/memory/memory.json", dim: int = 128) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.dim = dim
        self.items: list[dict[str, Any]] = []
        self.faiss = None
        self.index = None
        self._load()
        self._try_build_faiss()

    def add(self, session_id: str, role: str, text: str) -> None:
        if not text.strip():
            return
        item = {
            "session_id": session_id,
            "role": role,
            "text": text.strip()[:1200],
            "embedding": self._embed(text),
        }
        self.items.append(item)
        if self.index is not None:
            self.index.add(self._as_faiss_matrix([item["embedding"]]))
        self._save()

    def search(self, query: str, session_id: str | None = None, top_k: int = 3) -> list[dict[str, Any]]:
        if not self.items:
            return []
        query_vec = self._embed(query)
        if self.index is not None:
            scores, indices = self.index.search(self._as_faiss_matrix([query_vec]), min(len(self.items), max(top_k * 4, top_k)))
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0:
                    continue
                item = self.items[int(idx)]
                if session_id and item["session_id"] != session_id:
                    continue
                results.append({**item, "score": float(score)})
                if len(results) >= top_k:
                    break
            return results

        candidates = self.items
        if session_id:
            candidates = [item for item in self.items if item["session_id"] == session_id]
        scored = [
            {**item, "score": self._cosine(query_vec, item["embedding"])}
            for item in candidates
        ]
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:top_k]

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in self._tokens(text):
            idx = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self.dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(value * value for value in vec)) or 1.0
        return [value / norm for value in vec]

    def _tokens(self, text: str) -> list[str]:
        text = text.lower()
        tokens: list[str] = []
        buff = ""
        for ch in text:
            if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
                buff += ch
            elif buff:
                tokens.append(buff)
                buff = ""
        if buff:
            tokens.append(buff)
        return tokens

    def _cosine(self, left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right))

    def _load(self) -> None:
        if self.path.exists():
            self.items = json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        serializable = [
            {"session_id": item["session_id"], "role": item["role"], "text": item["text"], "embedding": item["embedding"]}
            for item in self.items
        ]
        self.path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")

    def _try_build_faiss(self) -> None:
        try:
            import faiss  # type: ignore
        except Exception:
            return
        self.faiss = faiss
        self.index = faiss.IndexFlatIP(self.dim)
        if self.items:
            self.index.add(self._as_faiss_matrix([item["embedding"] for item in self.items]))

    def _as_faiss_matrix(self, rows: list[list[float]]) -> Any:
        import numpy as np

        return np.array(rows, dtype="float32")

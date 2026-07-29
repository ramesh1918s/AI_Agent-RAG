"""
Embedding generation for infra-ai-agent.

Primary path: sentence-transformers (BAAI/bge-small-en-v1.5 by default,
384-dim, matches configs.settings.embedding_dim and Qdrant collection
config in Part-5).

Fallback path: if sentence-transformers isn't installed, or the model
can't be downloaded (locked-down network / no egress to huggingface.co —
the same class of problem Part-3 hit with tiktoken's Azure blob), we
degrade to a deterministic hashing embedder so the *pipeline* (chunking ->
caching -> Qdrant upsert -> retrieval wiring) stays testable end-to-end.
Records produced this way are tagged `degraded=True` and must never be
treated as semantically meaningful — CI and local dev only, never prod.
"""
from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from configs.logging_config import get_logger
from configs.settings import settings

log = get_logger("embeddings")

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class BaseEmbedder(ABC):
    model_name: str
    embedding_dim: int
    degraded: bool = False

    @abstractmethod
    def encode(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, same order."""


class SentenceTransformerEmbedder(BaseEmbedder):
    """Real embedder. Requires `sentence-transformers` and model weights
    (downloaded from huggingface.co on first run, then cached locally)."""

    def __init__(self, model_name: str | None = None, batch_size: int | None = None):
        from sentence_transformers import SentenceTransformer  # deferred import

        self.model_name = model_name or settings.embedding_model
        self.batch_size = batch_size or settings.embedding_batch_size
        self._model = SentenceTransformer(self.model_name)
        self.embedding_dim = self._model.get_sentence_embedding_dimension()
        self.degraded = False

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,  # cosine similarity == dot product in Qdrant
        )
        return [v.tolist() for v in vectors]


class HashingFallbackEmbedder(BaseEmbedder):
    """Deterministic, dependency-free stand-in used only when the real
    model can't be loaded. Hashes token n-grams into a fixed-width vector
    (feature hashing / "hashing trick"), L2-normalized. Good enough to
    exercise caching, batching, and Qdrant upsert logic end-to-end; not a
    real semantic embedding — never route production traffic through it.
    """

    def __init__(self, embedding_dim: int | None = None):
        self.model_name = "hashing-fallback-v1"
        self.embedding_dim = embedding_dim or settings.embedding_dim
        self.degraded = True

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.embedding_dim
        tokens = _TOKEN_RE.findall(text.lower())
        for tok in tokens:
            h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.embedding_dim
            sign = 1.0 if (h // self.embedding_dim) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


def get_embedder(model_name: str | None = None, batch_size: int | None = None) -> BaseEmbedder:
    """Factory: real embedder if available, hashing fallback otherwise.
    Mirrors Part-3's tiktoken degrade-gracefully-don't-crash pattern.
    """
    try:
        embedder = SentenceTransformerEmbedder(model_name=model_name, batch_size=batch_size)
        log.info(f"Loaded real embedder: {embedder.model_name} (dim={embedder.embedding_dim})")
        return embedder
    except Exception as exc:  # noqa: BLE001 — deliberately broad, this is a fallback boundary
        log.warning(
            f"Falling back to hashing embedder — sentence-transformers unavailable ({exc}). "
            "This is fine for CI/dev pipeline testing; do NOT use for real retrieval."
        )
        return HashingFallbackEmbedder(embedding_dim=settings.embedding_dim)

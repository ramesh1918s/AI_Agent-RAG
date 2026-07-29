"""
Embedding schema for infra-ai-agent.

This is the contract between Part-3 (chunks.json) and Part-5 (Qdrant
upsert): one EmbeddingRecord per chunk, keyed by `chunk_id`, carrying the
vector plus just enough metadata to re-verify freshness without re-reading
chunks.json.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ChunkIn(BaseModel):
    """Minimal shape we require from a chunks.json record.

    Deliberately permissive (`extra='ignore'` behavior via ignoring unknown
    keys at parse time) so Part-3's exact field set can grow without
    breaking Part-4 — we only pull what embedding actually needs.
    """

    chunk_id: str
    doc_id: str
    parent_id: str | None = None
    level: str = Field(..., description="'parent' or 'child'")
    text: str
    token_count: int
    service: str | None = None
    resource_name: str | None = None
    section: str | None = None
    source_url: str | None = None

    model_config = {"extra": "ignore"}


class EmbeddingRecord(BaseModel):
    chunk_id: str
    doc_id: str
    parent_id: str | None
    level: str
    embedding: list[float]
    embedding_dim: int
    model_name: str
    content_hash: str = Field(..., description="sha256(text + model_name), used as the cache key")
    degraded: bool = Field(
        default=False,
        description="True if produced by the hashing fallback embedder, not a real model",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Passed through unchanged so Part-5 can build Qdrant payloads without
    # re-reading chunks.json.
    service: str | None = None
    resource_name: str | None = None
    section: str | None = None
    source_url: str | None = None
    text: str


class EmbeddingRunStats(BaseModel):
    total_chunks: int
    cache_hits: int
    newly_embedded: int
    degraded_count: int
    model_name: str
    embedding_dim: int
    output_path: str

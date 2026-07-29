"""
Part-4 tests. The real SentenceTransformerEmbedder needs a model download
(network to huggingface.co) so it's exercised manually/in an integration
job, same pattern as Part-2's live GitHub fetch. Here we test everything
that's pure logic: hashing, caching, batching, and the fallback embedder.
"""
from __future__ import annotations

import json

import pytest

from embeddings.cache import EmbeddingCache, content_hash
from embeddings.embedder import HashingFallbackEmbedder
from embeddings.models import ChunkIn, EmbeddingRecord


def make_chunk(chunk_id: str, text: str, level: str = "child") -> ChunkIn:
    return ChunkIn(
        chunk_id=chunk_id,
        doc_id="aws_resource:aws_eks_cluster",
        parent_id=None if level == "parent" else "aws_resource:aws_eks_cluster::0",
        level=level,
        text=text,
        token_count=len(text.split()),
        service="eks",
        resource_name="aws_eks_cluster",
        section="Example Usage",
        source_url="https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/eks_cluster",
    )


def test_content_hash_changes_with_text():
    h1 = content_hash("hello world", "model-a")
    h2 = content_hash("hello there", "model-a")
    assert h1 != h2


def test_content_hash_changes_with_model():
    h1 = content_hash("hello world", "model-a")
    h2 = content_hash("hello world", "model-b")
    assert h1 != h2, "switching models must invalidate cache — different vector space"


def test_hashing_embedder_deterministic():
    embedder = HashingFallbackEmbedder(embedding_dim=32)
    v1 = embedder.encode(["aws_eks_cluster resource"])[0]
    v2 = embedder.encode(["aws_eks_cluster resource"])[0]
    assert v1 == v2
    assert len(v1) == 32
    assert embedder.degraded is True


def test_hashing_embedder_differs_by_content():
    embedder = HashingFallbackEmbedder(embedding_dim=32)
    v1 = embedder.encode(["aws_eks_cluster"])[0]
    v2 = embedder.encode(["aws_lambda_function"])[0]
    assert v1 != v2


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("embeddings.cache.CACHE_DIR", tmp_path)
    cache = EmbeddingCache(model_name="test-model")
    assert len(cache) == 0

    record = EmbeddingRecord(
        chunk_id="c1",
        doc_id="d1",
        parent_id=None,
        level="child",
        embedding=[0.1, 0.2, 0.3],
        embedding_dim=3,
        model_name="test-model",
        content_hash=content_hash("some text", "test-model"),
        text="some text",
    )
    cache.put_many([record])
    assert len(cache) == 1

    # simulate a fresh process re-reading the cache file
    reloaded = EmbeddingCache(model_name="test-model")
    fetched = reloaded.get(record.content_hash)
    assert fetched is not None
    assert fetched.chunk_id == "c1"
    assert fetched.embedding == [0.1, 0.2, 0.3]


def test_cache_miss_for_unseen_hash(tmp_path, monkeypatch):
    monkeypatch.setattr("embeddings.cache.CACHE_DIR", tmp_path)
    cache = EmbeddingCache(model_name="test-model")
    assert cache.get("nonexistent-hash") is None


def test_chunk_in_ignores_unknown_fields():
    # Part-3's chunks.json may carry extra fields (e.g. char_count) that
    # Part-4 doesn't need — must not break parsing.
    payload = make_chunk("c1", "some terraform docs").model_dump()
    payload["some_future_field"] = "should be ignored"
    chunk = ChunkIn.model_validate(payload)
    assert chunk.chunk_id == "c1"


@pytest.mark.parametrize("level", ["parent", "child"])
def test_chunk_in_accepts_both_levels(level):
    chunk = make_chunk("c1", "text", level=level)
    assert chunk.level == level

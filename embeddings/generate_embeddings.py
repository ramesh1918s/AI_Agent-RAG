"""
Part-4 orchestrator: chunks.json -> embeddings.jsonl

Usage:
    python scripts/generate_embeddings.py \
        --chunks docs/processed/chunks.json \
        --output embeddings/output/embeddings.jsonl \
        [--model BAAI/bge-small-en-v1.5] [--batch-size 64] [--limit 500]

Reads every chunk (both `parent` and `child` level — parents get embedded
too, so a future "parent-only" retrieval mode is possible without re-running
this step), checks the hash-cache, embeds only what's new/changed in
batches, and appends results to both the cache and the output file.

Idempotent and resumable: interrupt it anytime, re-run, only the remaining
chunks get embedded.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from configs.logging_config import configure_logging, get_logger
from embeddings.cache import EmbeddingCache, content_hash
from embeddings.embedder import get_embedder
from embeddings.models import ChunkIn, EmbeddingRecord, EmbeddingRunStats

log = get_logger("embeddings.generate")


def load_chunks(path: Path, limit: int | None = None) -> list[ChunkIn]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    # chunks.json is a flat list per Part-3's output contract
    if limit:
        raw = raw[:limit]
    chunks = [ChunkIn.model_validate(item) for item in raw]
    return chunks


def run(
    chunks_path: Path,
    output_path: Path,
    model_name: str | None,
    batch_size: int | None,
    limit: int | None,
) -> EmbeddingRunStats:
    chunks = load_chunks(chunks_path, limit=limit)
    log.info(f"Loaded {len(chunks)} chunks from {chunks_path}")

    embedder = get_embedder(model_name=model_name, batch_size=batch_size)
    cache = EmbeddingCache(model_name=embedder.model_name)
    log.info(f"Cache loaded: {len(cache)} existing entries for {embedder.model_name}")

    to_embed: list[ChunkIn] = []
    hashes: dict[str, str] = {}
    cache_hits = 0
    reused_records: list[EmbeddingRecord] = []

    for chunk in chunks:
        h = content_hash(chunk.text, embedder.model_name)
        hashes[chunk.chunk_id] = h
        cached = cache.get(h)
        if cached is not None:
            cache_hits += 1
            reused_records.append(cached)
        else:
            to_embed.append(chunk)

    log.info(f"{cache_hits} cache hits, {len(to_embed)} chunks need embedding")

    new_records: list[EmbeddingRecord] = []
    batch_size = batch_size or embedder.__dict__.get("batch_size", 64)
    start = time.perf_counter()

    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i : i + batch_size]
        vectors = embedder.encode([c.text for c in batch])
        for chunk, vector in zip(batch, vectors):
            new_records.append(
                EmbeddingRecord(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    parent_id=chunk.parent_id,
                    level=chunk.level,
                    embedding=vector,
                    embedding_dim=embedder.embedding_dim,
                    model_name=embedder.model_name,
                    content_hash=hashes[chunk.chunk_id],
                    degraded=embedder.degraded,
                    service=chunk.service,
                    resource_name=chunk.resource_name,
                    section=chunk.section,
                    source_url=chunk.source_url,
                    text=chunk.text,
                )
            )
        if to_embed:
            log.info(f"Embedded {min(i + batch_size, len(to_embed))}/{len(to_embed)}")

    elapsed = time.perf_counter() - start
    cache.put_many(new_records)

    all_records = reused_records + new_records
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for record in all_records:
            f.write(record.model_dump_json() + "\n")

    degraded_count = sum(1 for r in all_records if r.degraded)
    stats = EmbeddingRunStats(
        total_chunks=len(chunks),
        cache_hits=cache_hits,
        newly_embedded=len(new_records),
        degraded_count=degraded_count,
        model_name=embedder.model_name,
        embedding_dim=embedder.embedding_dim,
        output_path=str(output_path),
    )

    log.info(
        f"Done in {elapsed:.1f}s — {stats.newly_embedded} embedded, "
        f"{stats.cache_hits} from cache, {stats.degraded_count} degraded, "
        f"written to {output_path}"
    )
    if degraded_count:
        log.warning(
            f"{degraded_count} records used the hashing FALLBACK embedder — "
            "not real embeddings. Fine for pipeline testing only."
        )
    return stats


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Part-4: generate embeddings for chunks.json")
    parser.add_argument("--chunks", type=Path, default=Path("docs/processed/chunks.json"))
    parser.add_argument("--output", type=Path, default=Path("embeddings/output/embeddings.jsonl"))
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None, help="Debug: only embed first N chunks")
    args = parser.parse_args()

    stats = run(
        chunks_path=args.chunks,
        output_path=args.output,
        model_name=args.model,
        batch_size=args.batch_size,
        limit=args.limit,
    )
    print(stats.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

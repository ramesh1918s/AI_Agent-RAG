"""
Hash-based embedding cache.

Keyed on sha256(chunk_text + model_name) so:
  - editing a chunk's text invalidates only that chunk's cache entry
  - switching embedding models invalidates everything (different vector
    space, must not mix)
  - re-running Part-4 after a re-chunk only embeds what actually changed

Storage is a flat JSONL file (embeddings/cache/<model_slug>.jsonl) — no
extra service to run, appendable, and trivially inspectable/diffable.
Gitignored (see .gitignore: `embeddings/cache/`).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from embeddings.models import EmbeddingRecord

CACHE_DIR = Path(__file__).parent / "cache"


def content_hash(text: str, model_name: str) -> str:
    return hashlib.sha256(f"{model_name}::{text}".encode("utf-8")).hexdigest()


def _cache_path(model_name: str) -> Path:
    slug = model_name.replace("/", "__")
    return CACHE_DIR / f"{slug}.jsonl"


class EmbeddingCache:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.path = _cache_path(model_name)
        self._entries: dict[str, EmbeddingRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = EmbeddingRecord.model_validate_json(line)
                self._entries[record.content_hash] = record

    def get(self, chunk_hash: str) -> EmbeddingRecord | None:
        return self._entries.get(chunk_hash)

    def put_many(self, records: list[EmbeddingRecord]) -> None:
        if not records:
            return
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for record in records:
                self._entries[record.content_hash] = record
                f.write(record.model_dump_json() + "\n")

    def __len__(self) -> int:
        return len(self._entries)

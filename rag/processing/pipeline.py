"""
Document processing pipeline (Part-3).

Reads docs/raw/manifest.jsonl (written by Part-2), cleans + section-splits
+ chunks every document, and writes docs/processed/chunks.json — the sole
input Part-4 (embedding) reads from.

Usage:
    poetry run python scripts/process_documents.py
"""
from __future__ import annotations

import json
from pathlib import Path

from configs.logging_config import configure_logging, get_logger
from rag.ingestion.models import DocumentMetadata
from rag.processing.chunker import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS, chunk_section
from rag.processing.cleaner import clean_and_split
from rag.processing.models import Chunk

log = get_logger("processing.chunker")


def load_manifest(manifest_path: Path) -> list[DocumentMetadata]:
    records: list[DocumentMetadata] = []
    with manifest_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(DocumentMetadata.model_validate_json(line))
    return records


def process_document(doc: DocumentMetadata, docs_root: Path, max_tokens: int, overlap_tokens: int) -> list[Chunk]:
    # doc.local_path is stored relative to the `docs/` directory (see
    # downloader.py: local_path = path.relative_to(output_root.parent)),
    # e.g. "raw/aws-provider/resource/eks_cluster.html.markdown".
    file_path = docs_root / doc.local_path
    raw_text = file_path.read_text(encoding="utf-8", errors="replace")

    sections = clean_and_split(raw_text, doc_title=doc.title)

    chunks: list[Chunk] = []
    for section in sections:
        chunks.extend(
            chunk_section(
                section=section,
                doc_id=doc.doc_id,
                doc_type=doc.doc_type,
                service=doc.service,
                resource_name=doc.resource_name,
                source_url=doc.source_url,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            )
        )
    return chunks


def run(
    manifest_path: Path = Path("docs/raw/manifest.jsonl"),
    output_path: Path = Path("docs/processed/chunks.json"),
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> Path:
    configure_logging()

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"{manifest_path} not found — run scripts/download_terraform_docs.py first (Part-2)."
        )

    documents = load_manifest(manifest_path)
    log.info("Loaded {} documents from manifest", len(documents))

    docs_root = manifest_path.parent.parent  # docs/raw/manifest.jsonl -> docs/
    all_chunks: list[Chunk] = []
    failed = 0
    for doc in documents:
        try:
            all_chunks.extend(
                process_document(doc, docs_root, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
            )
        except Exception as exc:  # noqa: BLE001 — one bad doc must not kill the run
            failed += 1
            log.warning("Failed to process {}: {}", doc.doc_id, exc)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump([c.model_dump() for c in all_chunks], f, ensure_ascii=False)

    parents = sum(1 for c in all_chunks if c.chunk_type == "parent")
    children = sum(1 for c in all_chunks if c.chunk_type == "child")
    avg_tokens = sum(c.token_count for c in all_chunks) / len(all_chunks) if all_chunks else 0

    log.info(
        "Chunked {} documents ({} failed) into {} chunks ({} parent, {} child, avg {:.0f} tokens/chunk)",
        len(documents), failed, len(all_chunks), parents, children, avg_tokens,
    )
    log.info("Written to {}", output_path)
    return output_path


if __name__ == "__main__":
    run()

"""
Parent → child chunking.

Token counting: cl100k_base (tiktoken) — model-agnostic enough to be a
good proxy for both the embedding model's tokenizer and the LLM's, and
it's what OpenAI/Anthropic-family tokenizers roughly track for English +
code text like Terraform HCL.

Splitting unit: a "block" is either one fenced code block (```...```,
kept atomic — HCL must never be split mid-block) or one paragraph
(text between blank lines). Blocks are packed greedily into a chunk
until adding the next block would exceed `max_tokens`.

Overlap: after closing a chunk, the last `overlap_tokens` worth of the
_previous_ chunk's trailing block(s) are prepended to the next chunk.
This is a block-level sliding window, not a token-level one — it never
splits a code fence or paragraph mid-way, at the cost of overlap being
approximate rather than exact.

    target_chunk_tokens ≈ max_tokens
    step_size = max_tokens - overlap_tokens          (new tokens per chunk)
    num_chunks(N) ≈ ceil((N - overlap_tokens) / step_size)   for N total tokens

Defaults: max_tokens=450, overlap_tokens=60 (~13% overlap) — small enough
to avoid redundant embeddings, large enough that a sentence split across
a chunk boundary still has its full context in at least one chunk.
"""
from __future__ import annotations

import re

import tiktoken

from rag.processing.cleaner import CODE_FENCE_RE, Section
from rag.processing.models import Chunk, ChunkType
from configs.logging_config import get_logger

log = get_logger("processing.chunker")

DEFAULT_MAX_TOKENS = 450
DEFAULT_OVERLAP_TOKENS = 60

# tiktoken downloads its BPE merge table from a remote blob on first use.
# In locked-down networks (corporate proxies, restricted VPCs, this sandbox)
# that fetch is blocked — degrade to a char-based approximation (~4 chars/
# token for English + code, the same rule of thumb OpenAI's own docs use)
# rather than crashing the whole pipeline on import.
try:
    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception as exc:  # noqa: BLE001
    log.warning(
        "tiktoken BPE file unavailable ({}) — falling back to char-based token "
        "approximation. Chunk boundaries will be slightly less precise.",
        exc,
    )
    _ENCODING = None


def count_tokens(text: str) -> int:
    if not text:
        return 0
    if _ENCODING is not None:
        return len(_ENCODING.encode(text, disallowed_special=()))
    return max(1, len(text) // 4)


def _split_into_blocks(text: str) -> list[str]:
    """Split section body into atomic blocks: fenced code stays whole,
    everything else is split on blank lines into paragraphs."""
    blocks: list[str] = []
    pos = 0
    for match in CODE_FENCE_RE.finditer(text):
        before = text[pos : match.start()]
        blocks.extend(p.strip() for p in re.split(r"\n\s*\n", before) if p.strip())
        blocks.append(match.group(0))
        pos = match.end()
    tail = text[pos:]
    blocks.extend(p.strip() for p in re.split(r"\n\s*\n", tail) if p.strip())
    return blocks


def _pack_blocks(
    blocks: list[str], max_tokens: int, overlap_tokens: int
) -> list[str]:
    """Greedily pack blocks into token-bounded chunks with block-level overlap."""
    if not blocks:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for block in blocks:
        block_tokens = count_tokens(block)

        if current and current_tokens + block_tokens > max_tokens:
            chunks.append("\n\n".join(current))

            # Carry trailing blocks worth ~overlap_tokens into the next chunk.
            carry: list[str] = []
            carry_tokens = 0
            for prev_block in reversed(current):
                prev_tokens = count_tokens(prev_block)
                if carry_tokens + prev_tokens > overlap_tokens and carry:
                    break
                carry.insert(0, prev_block)
                carry_tokens += prev_tokens
            current = carry
            current_tokens = carry_tokens

        current.append(block)
        current_tokens += block_tokens

        # A single oversized block (huge code sample) becomes its own chunk
        # rather than being force-split and corrupting the HCL syntax.
        if block_tokens > max_tokens:
            chunks.append("\n\n".join(current))
            current = []
            current_tokens = 0

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def chunk_section(
    section: Section,
    doc_id: str,
    doc_type: str,
    service: str,
    resource_name: str | None,
    source_url: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Chunk one section into a parent row (if it had to be split) plus
    one or more child rows. If the section already fits in one chunk,
    the single child IS the parent (parent_id == its own chunk_id)."""
    section_slug = re.sub(r"[^a-z0-9]+", "-", section.title.lower()).strip("-") or "section"
    parent_id = f"{doc_id}::{section_slug}"

    section_tokens = count_tokens(section.body)
    chunks: list[Chunk] = []

    if section_tokens <= max_tokens:
        child_id = parent_id
        chunks.append(
            Chunk(
                chunk_id=child_id,
                parent_id=parent_id,
                chunk_type=ChunkType.CHILD,
                doc_id=doc_id,
                doc_type=doc_type,
                service=service,
                resource_name=resource_name,
                source_url=source_url,
                section_title=section.title,
                chunk_index=0,
                content=section.body,
                token_count=section_tokens,
                contains_code="```" in section.body,
            )
        )
        return chunks

    # Oversized section: store the full section as a parent row (for
    # parent-document retrieval) plus token-bounded child rows for search.
    chunks.append(
        Chunk(
            chunk_id=parent_id,
            parent_id=parent_id,
            chunk_type=ChunkType.PARENT,
            doc_id=doc_id,
            doc_type=doc_type,
            service=service,
            resource_name=resource_name,
            source_url=source_url,
            section_title=section.title,
            chunk_index=0,
            content=section.body,
            token_count=section_tokens,
            contains_code="```" in section.body,
        )
    )

    blocks = _split_into_blocks(section.body)
    piece_texts = _pack_blocks(blocks, max_tokens, overlap_tokens)
    for i, piece in enumerate(piece_texts):
        chunks.append(
            Chunk(
                chunk_id=f"{parent_id}::child-{i}",
                parent_id=parent_id,
                chunk_type=ChunkType.CHILD,
                doc_id=doc_id,
                doc_type=doc_type,
                service=service,
                resource_name=resource_name,
                source_url=source_url,
                section_title=section.title,
                chunk_index=i,
                content=piece,
                token_count=count_tokens(piece),
                contains_code="```" in piece,
            )
        )

    return chunks

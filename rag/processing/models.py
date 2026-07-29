"""
Chunk schema — the contract between Part-3 (chunking) and Part-4 (embedding).

Two-level hierarchy:
  * "parent" chunks = one markdown section (everything under one H1/H2),
    kept whole and used at answer-time to give the LLM full section
    context once a relevant child chunk is found (parent-document
    retrieval pattern).
  * "child" chunks = token-bounded pieces of a parent, small enough to
    embed precisely — these are what actually get vector-searched.

A parent with a short section becomes its own single child (parent_id ==
its own chunk_id), so every retrievable unit is always a "child" row.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ChunkType(str, Enum):
    PARENT = "parent"
    CHILD = "child"


class Chunk(BaseModel):
    chunk_id: str
    parent_id: str = Field(..., description="Section-level id; equals chunk_id for parent rows")
    chunk_type: ChunkType

    doc_id: str
    doc_type: str
    service: str
    resource_name: str | None
    source_url: str

    section_title: str
    chunk_index: int = Field(..., description="Position of this chunk within its parent section")
    content: str
    token_count: int
    contains_code: bool

    model_config = {"use_enum_values": True}

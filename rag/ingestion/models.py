"""
Metadata schema for every document the ingestion pipeline pulls down.

This is the contract between Part-2 (download) and Part-3 (chunking) —
each raw file on disk has exactly one DocumentMetadata entry in
docs/raw/manifest.jsonl, keyed by `doc_id`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class DocType(str, Enum):
    AWS_RESOURCE = "aws_resource"
    AWS_DATA_SOURCE = "aws_data_source"
    TERRAFORM_LANGUAGE = "terraform_language"


class DocumentMetadata(BaseModel):
    doc_id: str = Field(..., description="Stable id, e.g. aws_resource:aws_eks_cluster")
    doc_type: DocType
    title: str
    service: str = Field(..., description="AWS service slug, e.g. 'eks', or 'core' for language docs")
    resource_name: str | None = Field(
        default=None, description="e.g. aws_eks_cluster — null for language docs"
    )
    source_repo: str
    source_path: str
    source_ref: str = Field(..., description="git commit SHA or branch/tag the content was pulled at")
    source_url: str
    local_path: str
    content_hash: str = Field(..., description="sha256 of the raw file content, for change detection")
    downloaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    char_count: int

    model_config = {"use_enum_values": True}

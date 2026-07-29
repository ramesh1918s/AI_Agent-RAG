"""Part-2 tests: metadata parsing is pure logic and network-free, so it's
fully unit-testable in CI. The actual GitHub fetch functions are exercised
manually / in an integration job, not here, to avoid CI flakiness on
GitHub's rate limits.
"""
from rag.ingestion.downloader import _parse_frontmatter, _slugify
from rag.ingestion.models import DocType, DocumentMetadata

SAMPLE_RESOURCE_DOC = """---
subcategory: "EKS (Elastic Kubernetes)"
layout: "aws"
page_title: "AWS: aws_eks_cluster"
description: |-
  Manages an EKS Cluster
---

# Resource: aws_eks_cluster

Manages an EKS Cluster.
"""

SAMPLE_LANGUAGE_DOC = """---
page_title: Variables - Configuration Language
description: >-
  Input variables allow you to customize modules.
---

# Input Variables
"""


def test_parse_frontmatter_resource_doc():
    title, subcategory = _parse_frontmatter(SAMPLE_RESOURCE_DOC)
    assert title == "AWS: aws_eks_cluster"
    assert subcategory == "EKS (Elastic Kubernetes)"


def test_parse_frontmatter_language_doc():
    title, subcategory = _parse_frontmatter(SAMPLE_LANGUAGE_DOC)
    assert title == "Variables - Configuration Language"
    assert subcategory is None


def test_parse_frontmatter_missing():
    title, subcategory = _parse_frontmatter("# Just a heading, no frontmatter")
    assert title is None
    assert subcategory is None


def test_slugify():
    assert _slugify("EKS (Elastic Kubernetes)") == "eks-elastic-kubernetes"
    assert _slugify("Route53") == "route53"


def test_document_metadata_roundtrip():
    doc = DocumentMetadata(
        doc_id="aws_resource:aws_eks_cluster",
        doc_type=DocType.AWS_RESOURCE,
        title="AWS: aws_eks_cluster",
        service="eks",
        resource_name="aws_eks_cluster",
        source_repo="hashicorp/terraform-provider-aws",
        source_path="website/docs/r/eks_cluster.html.markdown",
        source_ref="abc123",
        source_url="https://github.com/hashicorp/terraform-provider-aws/blob/abc123/website/docs/r/eks_cluster.html.markdown",
        local_path="docs/raw/aws-provider/resource/eks_cluster.html.markdown",
        content_hash="deadbeef",
        char_count=42,
    )
    parsed = DocumentMetadata.model_validate_json(doc.model_dump_json())
    assert parsed.doc_id == "aws_resource:aws_eks_cluster"
    assert parsed.doc_type == "aws_resource"

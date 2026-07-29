"""Part-3 tests: cleaning and chunking are pure logic, fully unit-testable
without network access."""
from rag.processing.chunker import chunk_section, count_tokens
from rag.processing.cleaner import clean_and_split, normalize_whitespace, strip_frontmatter

SAMPLE_DOC = """---
subcategory: "EKS"
page_title: "AWS: aws_eks_cluster"
---

# Resource: aws_eks_cluster

Manages an EKS Cluster.



## Example Usage

```terraform
resource "aws_eks_cluster" "example" {
  name     = "example"
  role_arn = aws_iam_role.example.arn
}
```

## Argument Reference

The following arguments are supported.

* `name` - (Required) Name of the cluster.
* `role_arn` - (Required) ARN of the IAM role.
"""


def test_strip_frontmatter():
    body = strip_frontmatter(SAMPLE_DOC)
    assert not body.startswith("---")
    assert "# Resource: aws_eks_cluster" in body


def test_normalize_whitespace_collapses_blank_lines_outside_code():
    text = "para one\n\n\n\npara two"
    assert normalize_whitespace(text) == "para one\n\npara two"


def test_normalize_whitespace_preserves_code_fence_internals():
    text = "```\nline1\n\n\n\nline2\n```"
    result = normalize_whitespace(text)
    assert "\n\n\n\n" in result  # untouched inside the fence


def test_clean_and_split_sections():
    sections = clean_and_split(SAMPLE_DOC, doc_title="aws_eks_cluster")
    titles = [s.title for s in sections]
    assert "Resource: aws_eks_cluster" in titles
    assert "Example Usage" in titles
    assert "Argument Reference" in titles


def test_chunk_section_small_section_is_single_child():
    sections = clean_and_split(SAMPLE_DOC, doc_title="aws_eks_cluster")
    example_section = next(s for s in sections if s.title == "Example Usage")
    chunks = chunk_section(
        example_section,
        doc_id="aws_resource:aws_eks_cluster",
        doc_type="aws_resource",
        service="eks",
        resource_name="aws_eks_cluster",
        source_url="https://example.com",
    )
    assert len(chunks) == 1
    assert chunks[0].chunk_id == chunks[0].parent_id
    assert chunks[0].contains_code is True


def test_chunk_section_oversized_produces_parent_and_children():
    big_section_body = "# Argument Reference\n\n" + "\n\n".join(
        f"* `arg_{i}` - (Optional) Some long-ish description of argument number {i}."
        for i in range(200)
    )
    from rag.processing.cleaner import Section

    section = Section(title="Argument Reference", level=2, body=big_section_body)
    chunks = chunk_section(
        section,
        doc_id="aws_resource:aws_giant",
        doc_type="aws_resource",
        service="giant",
        resource_name="aws_giant",
        source_url="https://example.com",
        max_tokens=100,
        overlap_tokens=20,
    )
    parents = [c for c in chunks if c.chunk_type == "parent"]
    children = [c for c in chunks if c.chunk_type == "child"]
    assert len(parents) == 1
    assert len(children) > 1
    assert all(c.parent_id == parents[0].chunk_id for c in children)
    # every child stays under budget except an unavoidable oversized single block
    assert all(c.token_count <= 120 for c in children)


def test_count_tokens_reasonable():
    assert count_tokens("hello world") < 10
    assert count_tokens("") == 0

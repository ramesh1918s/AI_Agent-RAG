"""
Markdown cleaning + section splitting.

Terraform provider docs and language docs are Markdown/MDX with YAML
frontmatter. Before chunking we:

  1. Strip the frontmatter block (already parsed separately by Part-2).
  2. Normalize whitespace (collapse 3+ blank lines, strip trailing
     whitespace) without touching fenced code blocks — Terraform HCL
     indentation inside ``` blocks is semantically meaningful.
  3. Split the body into sections on H1 (`# `) / H2 (`## `) headers —
     these become "parent" chunks. A provider resource doc is naturally
     structured this way: Resource, Example Usage, Argument Reference,
     Attribute Reference, Import — each becomes its own retrievable unit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
HEADER_RE = re.compile(r"^(#{1,2})\s+(.+?)\s*$", re.MULTILINE)
BLANK_LINES_RE = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class Section:
    title: str
    level: int
    body: str  # includes the header line itself


def strip_frontmatter(raw_text: str) -> str:
    return FRONTMATTER_RE.sub("", raw_text, count=1).strip()


def normalize_whitespace(text: str) -> str:
    """Collapse excess blank lines everywhere EXCEPT inside fenced code
    blocks, by temporarily masking code fences before the regex pass."""
    fences: list[str] = []

    def _mask(match: re.Match) -> str:
        fences.append(match.group(0))
        return f"\x00FENCE{len(fences) - 1}\x00"

    masked = CODE_FENCE_RE.sub(_mask, text)
    masked = BLANK_LINES_RE.sub("\n\n", masked)
    masked = "\n".join(line.rstrip() for line in masked.split("\n"))

    for i, fence in enumerate(fences):
        masked = masked.replace(f"\x00FENCE{i}\x00", fence)
    return masked.strip()


def split_into_sections(body: str, doc_title: str) -> list[Section]:
    """Split on H1/H2 headers. Content before the first header (if any)
    becomes an implicit "Overview" section so nothing is dropped."""
    matches = list(HEADER_RE.finditer(body))
    if not matches:
        return [Section(title=doc_title, level=1, body=body)] if body.strip() else []

    sections: list[Section] = []
    if matches[0].start() > 0:
        preamble = body[: matches[0].start()].strip()
        if preamble:
            sections.append(Section(title="Overview", level=1, body=preamble))

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_body = body[start:end].strip()
        title = match.group(2).strip()
        level = len(match.group(1))
        sections.append(Section(title=title, level=level, body=section_body))

    return sections


def clean_and_split(raw_text: str, doc_title: str) -> list[Section]:
    body = strip_frontmatter(raw_text)
    body = normalize_whitespace(body)
    return split_into_sections(body, doc_title)

"""
Terraform documentation downloader (Part-2).

Sources (both official HashiCorp repos, not scraped HTML):

  1. hashicorp/terraform-provider-aws  -> website/docs/r/*.markdown  (resources)
                                          website/docs/d/*.markdown  (data sources)
     Pulled via tarball (whole repo is ~110MB, one download, no API rate-limit cost).

  2. hashicorp/web-unified-docs        -> content/terraform/<version>/docs/language/**
     Pulled via the Git Trees API + raw.githubusercontent.com per-file fetch,
     since the repo itself is 1GB+ and we only want one product's docs.

Every file written to docs/raw/ gets one line in docs/raw/manifest.jsonl —
that manifest is the sole input Part-3 (chunking) reads from.

Usage:
    poetry run python scripts/download_terraform_docs.py
    poetry run python scripts/download_terraform_docs.py --terraform-version v1.9.x
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from configs.logging_config import configure_logging, get_logger
from rag.ingestion.github_source import (
    download_tarball,
    fetch_raw_file,
    get_latest_commit_sha,
    list_tree,
    sha256_of,
)
from rag.ingestion.models import DocumentMetadata, DocType

log = get_logger("ingestion.downloader")

AWS_PROVIDER_OWNER, AWS_PROVIDER_REPO = "hashicorp", "terraform-provider-aws"
UNIFIED_DOCS_OWNER, UNIFIED_DOCS_REPO = "hashicorp", "web-unified-docs"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
PAGE_TITLE_RE = re.compile(r'^page_title:\s*"?(.+?)"?\s*$', re.MULTILINE)
SUBCATEGORY_RE = re.compile(r'^subcategory:\s*"?(.+?)"?\s*$', re.MULTILINE)


def _parse_frontmatter(raw_text: str) -> tuple[str | None, str | None]:
    """Return (page_title, subcategory) parsed out of the doc's YAML frontmatter."""
    match = FRONTMATTER_RE.match(raw_text)
    if not match:
        return None, None
    block = match.group(1)
    title_match = PAGE_TITLE_RE.search(block)
    sub_match = SUBCATEGORY_RE.search(block)
    return (
        title_match.group(1).strip() if title_match else None,
        sub_match.group(1).strip() if sub_match else None,
    )


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def download_aws_provider_docs(output_root: Path, work_dir: Path) -> list[DocumentMetadata]:
    log.info("Resolving latest commit for {}/{}", AWS_PROVIDER_OWNER, AWS_PROVIDER_REPO)
    ref = get_latest_commit_sha(AWS_PROVIDER_OWNER, AWS_PROVIDER_REPO)
    repo_root = download_tarball(AWS_PROVIDER_OWNER, AWS_PROVIDER_REPO, ref, work_dir)

    doc_specs = [
        (repo_root / "website" / "docs" / "r", DocType.AWS_RESOURCE, "resource"),
        (repo_root / "website" / "docs" / "d", DocType.AWS_DATA_SOURCE, "data-source"),
    ]

    records: list[DocumentMetadata] = []
    for source_dir, doc_type, subfolder in doc_specs:
        if not source_dir.is_dir():
            log.warning("Expected doc dir missing: {}", source_dir)
            continue

        dest_dir = output_root / "aws-provider" / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)

        files = sorted(source_dir.glob("*.markdown")) + sorted(source_dir.glob("*.md"))
        log.info("Found {} {} docs", len(files), subfolder)

        for src_file in files:
            raw_text = src_file.read_text(encoding="utf-8", errors="replace")
            page_title, subcategory = _parse_frontmatter(raw_text)

            base_name = src_file.name
            for ext in (".html.markdown", ".html.md", ".markdown", ".md"):
                if base_name.endswith(ext):
                    base_name = base_name[: -len(ext)]
                    break
            resource_name = f"aws_{base_name}"
            title = page_title or resource_name
            service = _slugify(subcategory) if subcategory else src_file.stem.split("_")[0]

            dest_file = dest_dir / src_file.name
            dest_file.write_text(raw_text, encoding="utf-8")

            relative_source = f"website/docs/{'r' if doc_type == DocType.AWS_RESOURCE else 'd'}/{src_file.name}"
            records.append(
                DocumentMetadata(
                    doc_id=f"{doc_type.value}:{resource_name}",
                    doc_type=doc_type,
                    title=title,
                    service=service,
                    resource_name=resource_name,
                    source_repo=f"{AWS_PROVIDER_OWNER}/{AWS_PROVIDER_REPO}",
                    source_path=relative_source,
                    source_ref=ref,
                    source_url=(
                        f"https://github.com/{AWS_PROVIDER_OWNER}/{AWS_PROVIDER_REPO}"
                        f"/blob/{ref}/{relative_source}"
                    ),
                    local_path=str(dest_file.relative_to(output_root.parent)),
                    content_hash=sha256_of(raw_text.encode("utf-8")),
                    char_count=len(raw_text),
                )
            )

    return records


def download_terraform_language_docs(
    output_root: Path, terraform_version: str = "v1.9.x"
) -> list[DocumentMetadata]:
    path_prefix = f"content/terraform/{terraform_version}/docs/language/"
    log.info("Resolving latest commit for {}/{}", UNIFIED_DOCS_OWNER, UNIFIED_DOCS_REPO)
    ref = get_latest_commit_sha(UNIFIED_DOCS_OWNER, UNIFIED_DOCS_REPO)

    log.info("Listing tree under {}", path_prefix)
    entries = list_tree(UNIFIED_DOCS_OWNER, UNIFIED_DOCS_REPO, ref, path_prefix)
    entries = [e for e in entries if e.path.endswith((".mdx", ".md"))]
    log.info("Found {} language doc files", len(entries))

    dest_dir = output_root / "terraform-language"
    dest_dir.mkdir(parents=True, exist_ok=True)

    records: list[DocumentMetadata] = []
    for entry in entries:
        content = fetch_raw_file(UNIFIED_DOCS_OWNER, UNIFIED_DOCS_REPO, ref, entry.path)
        raw_text = content.decode("utf-8", errors="replace")
        page_title, _ = _parse_frontmatter(raw_text)

        rel_name = entry.path[len(path_prefix):]
        dest_file = dest_dir / rel_name
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(raw_text, encoding="utf-8")

        doc_id_stub = _slugify(rel_name.rsplit(".", 1)[0])
        records.append(
            DocumentMetadata(
                doc_id=f"{DocType.TERRAFORM_LANGUAGE.value}:{doc_id_stub}",
                doc_type=DocType.TERRAFORM_LANGUAGE,
                title=page_title or rel_name,
                service="core",
                resource_name=None,
                source_repo=f"{UNIFIED_DOCS_OWNER}/{UNIFIED_DOCS_REPO}",
                source_path=entry.path,
                source_ref=ref,
                source_url=f"https://github.com/{UNIFIED_DOCS_OWNER}/{UNIFIED_DOCS_REPO}/blob/{ref}/{entry.path}",
                local_path=str(dest_file.relative_to(output_root.parent)),
                content_hash=sha256_of(content),
                char_count=len(raw_text),
            )
        )

    return records


def write_manifest(records: list[DocumentMetadata], output_root: Path) -> Path:
    manifest_path = output_root / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")
    return manifest_path


def run(
    output_root: Path = Path("docs/raw"),
    work_dir: Path = Path(".cache/ingestion"),
    terraform_version: str = "v1.9.x",
    keep_tarball_cache: bool = False,
) -> Path:
    configure_logging()
    output_root.mkdir(parents=True, exist_ok=True)

    records: list[DocumentMetadata] = []
    records += download_aws_provider_docs(output_root, work_dir)
    records += download_terraform_language_docs(output_root, terraform_version)

    manifest_path = write_manifest(records, output_root)

    by_type: dict[str, int] = {}
    for r in records:
        by_type[r.doc_type] = by_type.get(r.doc_type, 0) + 1

    log.info("Downloaded {} documents total: {}", len(records), by_type)
    log.info("Manifest written to {}", manifest_path)

    if not keep_tarball_cache and work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)

    return manifest_path


if __name__ == "__main__":
    run()

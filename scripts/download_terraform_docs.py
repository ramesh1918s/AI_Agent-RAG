#files are completed
#this files python 
#!/usr/bin/env python
"""CLI entrypoint for Part-2: Terraform documentation downloader.

    poetry run python scripts/download_terraform_docs.py
    poetry run python scripts/download_terraform_docs.py --terraform-version v1.8.x --keep-tarball-cache
"""
from __future__ import annotations

from pathlib import Path

import typer

from rag.ingestion.downloader import run

app = typer.Typer(add_completion=False)


@app.command()
def main(
    output_root: Path = typer.Option(Path("docs/raw"), help="Where cleaned docs + manifest.jsonl land"),
    work_dir: Path = typer.Option(Path(".cache/ingestion"), help="Scratch dir for tarball download/extract"),
    terraform_version: str = typer.Option("v1.9.x", help="Terraform version folder in web-unified-docs"),
    keep_tarball_cache: bool = typer.Option(
        False, help="Keep the downloaded tarball cache (skips re-download on next run)"
    ),
) -> None:
    manifest_path = run(
        output_root=output_root,
        work_dir=work_dir,
        terraform_version=terraform_version,
        keep_tarball_cache=keep_tarball_cache,
    )
    typer.echo(f"Done. Manifest: {manifest_path}")


if __name__ == "__main__":
    app()

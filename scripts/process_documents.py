#!/usr/bin/env python
"""CLI entrypoint for Part-3: Document processing (clean, split, chunk).

    poetry run python scripts/process_documents.py
    poetry run python scripts/process_documents.py --max-tokens 400 --overlap-tokens 50
"""
from __future__ import annotations

from pathlib import Path

import typer

from rag.processing.chunker import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS
from rag.processing.pipeline import run

app = typer.Typer(add_completion=False)


@app.command()
def main(
    manifest_path: Path = typer.Option(Path("docs/raw/manifest.jsonl"), help="Part-2 output manifest"),
    output_path: Path = typer.Option(Path("docs/processed/chunks.json"), help="Where chunks.json is written"),
    max_tokens: int = typer.Option(DEFAULT_MAX_TOKENS, help="Max tokens per child chunk"),
    overlap_tokens: int = typer.Option(DEFAULT_OVERLAP_TOKENS, help="Token overlap between adjacent chunks"),
) -> None:
    output = run(manifest_path=manifest_path, output_path=output_path,
                 max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    typer.echo(f"Done. Chunks: {output}")


if __name__ == "__main__":
    app()

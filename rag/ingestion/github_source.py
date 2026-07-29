"""
GitHub-backed document sources.

Terraform's official docs (language docs + every provider resource/data
source page) live as Markdown/MDX in public HashiCorp repos. Pulling from
there instead of scraping developer.hashicorp.com / registry.terraform.io
gives us: versioned content (pin to a commit SHA), no HTML-to-markdown
cleanup, and no scraping-ban risk.

Two fetch strategies, used depending on repo size:

  * `download_tarball` — pull the whole repo as a .tar.gz via codeload.
    Cheap on GitHub's API rate limit (one HTTP GET, not counted against
    the REST API quota). Good for small/medium repos like
    terraform-provider-aws (~110MB).

  * `list_tree` + `fetch_raw_file` — use the Git Trees API to list a
    subtree, then pull just the files under it via raw.githubusercontent.com.
    Good for huge repos (hashicorp/web-unified-docs is 1GB+) where we only
    want one product's docs out of dozens.
"""
from __future__ import annotations

import hashlib
import os
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from configs.logging_config import get_logger

log = get_logger("ingestion.github")

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"
GITHUB_CODELOAD = "https://codeload.github.com"

_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 2.0


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "infra-ai-agent-ingestion"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_with_retry(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.get(url, timeout=60.0, **kwargs)
            if response.status_code == 403 and "rate limit" in response.text.lower():
                reset = response.headers.get("x-ratelimit-reset")
                wait = max(int(reset) - int(time.time()), 1) if reset else _BACKOFF_BASE_SECONDS * attempt
                log.warning("GitHub rate limit hit, sleeping {}s (attempt {})", wait, attempt)
                time.sleep(min(wait, 120))
                continue
            response.raise_for_status()
            return response
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            sleep_for = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            log.warning("GET {} failed (attempt {}/{}): {} — retrying in {:.1f}s",
                        url, attempt, _MAX_RETRIES, exc, sleep_for)
            time.sleep(sleep_for)
    assert last_exc is not None
    raise last_exc


def get_latest_commit_sha(owner: str, repo: str, branch: str = "main") -> str:
    """Resolve `branch` to a commit SHA so every downloaded doc can be
    traced back to an exact, reproducible source version."""
    with httpx.Client(headers=_headers()) as client:
        resp = _get_with_retry(client, f"{GITHUB_API}/repos/{owner}/{repo}/commits/{branch}")
        return resp.json()["sha"]


def download_tarball(owner: str, repo: str, ref: str, dest_dir: Path) -> Path:
    """Download+extract a repo tarball at `ref`. Returns the extracted root dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    tarball_path = dest_dir / f"{repo}-{ref[:12]}.tar.gz"

    if not tarball_path.exists():
        log.info("Downloading {}/{}@{}", owner, repo, ref[:12])
        with httpx.Client(follow_redirects=True) as client:
            resp = _get_with_retry(
                client, f"{GITHUB_CODELOAD}/{owner}/{repo}/tar.gz/{ref}"
            )
            tarball_path.write_bytes(resp.content)

    extract_dir = dest_dir / f"{repo}-{ref[:12]}-extracted"
    if not extract_dir.exists():
        log.info("Extracting {}", tarball_path.name)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tarball_path) as tar:
            tar.extractall(extract_dir, filter="data")

    # GitHub tarballs unpack into a single "<repo>-<sha>/" root folder.
    roots = list(extract_dir.iterdir())
    if len(roots) != 1:
        raise RuntimeError(f"Unexpected tarball layout for {repo}: {roots}")
    return roots[0]


@dataclass(frozen=True)
class TreeEntry:
    path: str
    sha: str
    size: int


def list_tree(owner: str, repo: str, ref: str, path_prefix: str) -> list[TreeEntry]:
    """List every blob under `path_prefix` at `ref` using the Git Trees API
    (one recursive call, cheap on rate limit) instead of cloning the repo."""
    with httpx.Client(headers=_headers()) as client:
        resp = _get_with_retry(
            client, f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
        )
        tree = resp.json()["tree"]

    return [
        TreeEntry(path=item["path"], sha=item["sha"], size=item.get("size", 0))
        for item in tree
        if item["type"] == "blob" and item["path"].startswith(path_prefix)
    ]


def fetch_raw_file(owner: str, repo: str, ref: str, path: str) -> bytes:
    with httpx.Client(follow_redirects=True) as client:
        resp = _get_with_retry(client, f"{GITHUB_RAW}/{owner}/{repo}/{ref}/{path}")
        return resp.content


def sha256_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

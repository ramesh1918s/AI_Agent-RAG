"""
Centralized configuration for infra-ai-agent.

Every module (rag, agent, terraform-engine, aws, api) imports `settings`
from here instead of reading environment variables directly. This keeps
config validation, defaults, and secrets handling in one place.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class LLMProvider(str, Enum):
    BEDROCK = "bedrock"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "infra-ai-agent"
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"
    log_json: bool = False

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    jwt_secret: SecretStr = Field(default=SecretStr("change-me-in-.env"))
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60

    # --- AWS ---
    aws_region: str = "ap-south-1"
    aws_profile: str | None = None  # never store static keys here; use IAM role/STS

    # --- Vector DB (Qdrant) ---
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "terraform_docs"
    embedding_dim: int = 384  # matches all-MiniLM-L6-v2 / bge-small

    # --- Embeddings ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = 64

    # --- LLM / Agent ---
    llm_provider: LLMProvider = LLMProvider.BEDROCK
    llm_model_id: str = "anthropic.claude-sonnet-4-6-v1:0"
    llm_temperature: float = 0.1
    agent_max_iterations: int = 15
    require_human_approval_for_apply: bool = True
    require_human_approval_for_destroy: bool = True

    # --- Terraform Engine ---
    terraform_workspace_root: Path = Path("./terraform-engine/workspaces")
    terraform_binary: str = "terraform"
    terraform_default_workspace: str = "default"

    # --- Notifications ---
    sns_topic_arn: str | None = None
    slack_webhook_url: SecretStr | None = None

    # --- Observability ---
    otel_exporter_endpoint: str | None = None
    enable_prometheus_metrics: bool = True


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — import this, not Settings() directly."""
    return Settings()


settings = get_settings()

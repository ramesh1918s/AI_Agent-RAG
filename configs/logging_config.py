"""
Structured logging setup for infra-ai-agent.

Local/dev -> human-readable colored logs.
Staging/prod -> JSON logs (consumed by Loki/CloudWatch).
Every log line carries a `component` field so Grafana/Loki queries can
filter by agent / rag / terraform-engine / api etc.
"""
from __future__ import annotations

import sys

from loguru import logger

from configs.settings import Environment, settings


def configure_logging() -> None:
    logger.remove()  # drop default handler

    if settings.log_json or settings.environment in (Environment.STAGING, Environment.PROD):
        logger.add(
            sys.stdout,
            level=settings.log_level,
            serialize=True,  # JSON output
            backtrace=False,
            diagnose=False,
        )
    else:
        logger.add(
            sys.stdout,
            level=settings.log_level,
            colorize=True,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{extra[component]: <16}</cyan> | "
                "<level>{message}</level>"
            ),
            backtrace=True,
            diagnose=True,
        )

    logger.configure(extra={"component": "core"})


def get_logger(component: str):
    """Return a logger pre-bound with a component name.

    Usage:
        log = get_logger("terraform-engine")
        log.info("plan generated")
    """
    return logger.bind(component=component)

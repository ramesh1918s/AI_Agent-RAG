# syntax=docker/dockerfile:1.7
# ---------- Stage 1: build dependencies ----------
FROM python:3.11-slim AS builder

ENV POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

WORKDIR /build
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root --only main --no-ansi

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim AS runtime

# Terraform + AWS CLI so the agent can shell out to them at runtime.
ARG TERRAFORM_VERSION=1.9.5
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl unzip ca-certificates \
    && curl -sSLo /tmp/tf.zip \
        "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    && unzip /tmp/tf.zip -d /usr/local/bin \
    && rm /tmp/tf.zip \
    && curl -sSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws /tmp/awscliv2.zip \
    && apt-get purge -y unzip \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 agent && useradd --uid 1000 --gid agent --shell /bin/bash --create-home agent

WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --chown=agent:agent . .

USER agent

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

#!/usr/bin/env bash
# Installs every tool infra-ai-agent needs on a fresh Ubuntu box / EC2 instance.
# Idempotent: safe to re-run.
set -euo pipefail

TERRAFORM_VERSION="1.9.5"
PYTHON_VERSION="3.11"

echo "==> Updating apt"
sudo apt-get update -y

echo "==> Installing base packages"
sudo apt-get install -y --no-install-recommends \
    curl unzip git build-essential ca-certificates gnupg lsb-release software-properties-common

# --- Python ---
if ! command -v python3.11 &>/dev/null; then
    echo "==> Installing Python ${PYTHON_VERSION}"
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update -y
    sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
fi

# --- Poetry ---
if ! command -v poetry &>/dev/null; then
    echo "==> Installing Poetry"
    curl -sSL https://install.python-poetry.org | python3.11 -
    export PATH="$HOME/.local/bin:$PATH"
fi

# --- uv (fast alt resolver, optional but supported) ---
if ! command -v uv &>/dev/null; then
    echo "==> Installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# --- Terraform ---
if ! command -v terraform &>/dev/null; then
    echo "==> Installing Terraform ${TERRAFORM_VERSION}"
    curl -sSLo /tmp/terraform.zip \
        "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip"
    sudo unzip -o /tmp/terraform.zip -d /usr/local/bin
    rm /tmp/terraform.zip
fi

# --- AWS CLI v2 ---
if ! command -v aws &>/dev/null; then
    echo "==> Installing AWS CLI v2"
    curl -sSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    unzip -q -o /tmp/awscliv2.zip -d /tmp
    sudo /tmp/aws/install
    rm -rf /tmp/aws /tmp/awscliv2.zip
fi

# --- Docker + Compose plugin ---
if ! command -v docker &>/dev/null; then
    echo "==> Installing Docker"
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
fi

# --- kubectl ---
if ! command -v kubectl &>/dev/null; then
    echo "==> Installing kubectl"
    curl -LO "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
    sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
    rm kubectl
fi

# --- Helm ---
if ! command -v helm &>/dev/null; then
    echo "==> Installing Helm"
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

echo "==> Versions installed"
python3.11 --version
poetry --version
terraform -version | head -n1
aws --version
docker --version
kubectl version --client --short 2>/dev/null || kubectl version --client
helm version --short

echo "==> Done. Log out/in (or 'newgrp docker') for the docker group change to take effect."

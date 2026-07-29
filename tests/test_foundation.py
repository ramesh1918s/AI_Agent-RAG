"""Part-1 smoke tests: prove the foundation actually runs."""
from fastapi.testclient import TestClient

from api.main import app
from configs.settings import get_settings


def test_settings_load():
    settings = get_settings()
    assert settings.app_name == "infra-ai-agent"
    assert settings.embedding_dim > 0


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "infra-ai-agent"


def test_root_endpoint():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "infra-ai-agent" in response.json()["service"]

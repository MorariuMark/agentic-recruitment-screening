"""
tests/test_local_model_scanner.py
Unit and integration tests for autonomous local model discovery across
Ollama, LM Studio, Jan, and local storage locations.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.local_model_scanner import LocalModelScanner, get_local_model_scanner
from backend.schemas.models_catalog import (
    CATALOG_PROVIDERS,
    get_models_for_provider,
    get_providers_catalog,
    sync_all_local_models,
)
from backend.agents.llm_factory import LMStudioClient, create_llm_client


@pytest.fixture
def client():
    return TestClient(app)


def test_scanner_clean_model_tag():
    scanner = LocalModelScanner()
    assert scanner._clean_model_tag("minicpm5-2b-q4_k_m.gguf") == "minicpm5-2b-q4-k-m"
    assert scanner._clean_model_tag("path/to/Llama-3.1-8B-Instruct.GGUF") == "llama-3.1-8b-instruct"


def test_scanner_extract_quantization():
    scanner = LocalModelScanner()
    assert scanner._extract_quantization("model-q4_k_m.gguf") == "Q4_K_M"
    assert scanner._extract_quantization("model-Q8_0.gguf") == "Q8_0"
    assert scanner._extract_quantization("model-f16.gguf") == "F16"


def test_scan_all_mocked():
    scanner = LocalModelScanner()

    mock_ollama = {
        "status": {"running": True, "version": "0.5.1"},
        "installed_count": 1,
        "installed_models": [
            {
                "id": "qwen2.5:7b",
                "name": "qwen2.5:7b",
                "provider": "ollama",
                "source": "Ollama Library",
                "size_gb": 4.5,
                "parameter_size": "7B",
                "format": "gguf",
                "status": "ready",
                "is_running": False,
                "can_activate": True,
            }
        ],
        "running_models": [],
    }

    mock_lmstudio = {
        "server_running": True,
        "base_url": "http://localhost:1234/v1",
        "live_models": [
            {
                "id": "meta-llama-3.1-8b-instruct",
                "name": "meta-llama-3.1-8b-instruct",
                "provider": "lmstudio",
                "source": "LM Studio (Live API)",
                "size_gb": 0.0,
                "format": "gguf",
                "status": "running_in_vram",
                "is_running": True,
                "can_activate": True,
            }
        ],
        "disk_models": [
            {
                "id": "phi-3-mini-4k-instruct-q4",
                "name": "phi-3-mini-4k-instruct-q4 (Q4_K_M)",
                "file_name": "phi-3-mini-4k-instruct-q4_k_m.gguf",
                "provider": "lmstudio",
                "source": "LM Studio (Disk GGUF)",
                "size_gb": 2.3,
                "quantization": "Q4_K_M",
                "format": "gguf",
                "status": "ready",
                "is_running": False,
                "can_activate": True,
            }
        ],
        "total_count": 2,
    }

    with patch.object(scanner, "scan_ollama", return_value=mock_ollama), \
         patch.object(scanner, "scan_lm_studio", return_value=mock_lmstudio), \
         patch.object(scanner, "scan_jan_and_local_servers", return_value={"detected_servers": []}), \
         patch.object(scanner, "scan_common_directories", return_value=[]):

        result = scanner.scan_all(force=True)

        assert result["success"] is True
        assert result["total_found"] == 3
        assert len(result["all_models"]) == 3

        # Verify providers catalog was automatically updated
        catalog = get_providers_catalog()
        assert "lmstudio" in catalog
        assert any(m.id == "meta-llama-3.1-8b-instruct" for m in catalog["lmstudio"].models)
        assert any(m.id == "qwen2.5:7b" for m in catalog["ollama"].models)


def test_api_local_models_endpoints(client):
    """Test GET and POST local models discovery endpoints."""
    res_get = client.get("/api/v1/settings/local-models")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert "success" in data_get
    assert "total_found" in data_get
    assert "providers_detected" in data_get
    assert "all_models" in data_get

    res_scan = client.post("/api/v1/settings/local-models/scan", json={"force": True})
    assert res_scan.status_code == 200
    data_scan = res_scan.json()
    assert data_scan["success"] is True
    assert "ollama" in data_scan["providers_detected"]
    assert "lmstudio" in data_scan["providers_detected"]


def test_api_update_llm_settings_lmstudio(client):
    """Test switching active LLM provider to LM Studio."""
    payload = {
        "provider": "lmstudio",
        "model": "default",
        "compatibility_mode": "auto",
        "base_url": "http://localhost:1234/v1",
    }
    res = client.post("/api/v1/settings/llm", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["active_provider"] == "lmstudio"
    assert data["active_model"] == "default"
    assert "lmstudio" in data["providers_catalog"]


def test_create_lmstudio_client():
    """Verify factory properly creates LMStudioClient instance."""
    cli = create_llm_client(
        provider="lmstudio",
        model="custom-local-model",
        base_url="http://localhost:1234/v1",
    )
    assert isinstance(cli, LMStudioClient)
    assert cli.model == "custom-local-model"
    assert cli.base_url == "http://localhost:1234/v1"

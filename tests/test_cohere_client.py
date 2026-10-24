import pytest
from unittest.mock import MagicMock, patch
from pydantic import BaseModel
from backend.agents.llm_factory import CohereClient, create_llm_client, DynamicLLMClient


class SampleResponse(BaseModel):
    summary: str
    confidence: float


def test_cohere_client_init_and_create():
    client = create_llm_client("cohere", api_key="dummy_key", model="command-r-08-2024")
    assert isinstance(client, CohereClient)
    assert client.api_key == "dummy_key"
    assert client.model == "command-r-08-2024"
    assert client.base_url == "https://api.cohere.com/v2"


def test_cohere_generate_text_mocked():
    client = CohereClient(api_key="test_key", model="command-r-08-2024")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello world from Cohere"}],
        },
        "usage": {
            "tokens": {
                "input_tokens": 15,
                "output_tokens": 6,
            }
        },
    }

    with patch.object(client.client, "post", return_value=mock_resp) as mock_post:
        res = client.generate_text("Say hello")
        assert res == "Hello world from Cohere"
        assert client.last_usage["prompt_tokens"] == 15
        assert client.last_usage["completion_tokens"] == 6
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["model"] == "command-r-08-2024"


def test_cohere_generate_structured_mocked():
    client = CohereClient(api_key="test_key", model="command-r-08-2024")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": '{"summary": "Strong candidate match", "confidence": 0.95}',
                }
            ],
        },
        "usage": {
            "tokens": {
                "input_tokens": 40,
                "output_tokens": 18,
            }
        },
    }

    with patch.object(client.client, "post", return_value=mock_resp):
        structured = client.generate_structured("Evaluate", SampleResponse)
        assert isinstance(structured, SampleResponse)
        assert structured.summary == "Strong candidate match"
        assert structured.confidence == 0.95


def test_cohere_secondary_key_failover():
    client = CohereClient(
        api_key="primary_key",
        secondary_api_key="secondary_key",
        model="command-r-08-2024",
    )

    primary_resp_429 = MagicMock()
    primary_resp_429.status_code = 429

    secondary_resp_200 = MagicMock()
    secondary_resp_200.status_code = 200
    secondary_resp_200.json.return_value = {
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Recovered with secondary key"}],
        },
        "usage": {"tokens": {"input_tokens": 10, "output_tokens": 5}},
    }

    with patch.object(client.client, "post", return_value=primary_resp_429), \
         patch.object(client.secondary_client, "post", return_value=secondary_resp_200):
        out = client.generate_text("Testing dual key")
        assert out == "Recovered with secondary key"
        assert client.last_key_used == "secondary"

import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.llm_client import LLMClient


def test_llm_client_builds_correct_request_body():
    client = LLMClient(api_key="sk-test", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash")
    body = client._build_body([{"role": "user", "content": "Hello"}])

    assert body["model"] == "deepseek-v4-flash"
    assert body["messages"] == [{"role": "user", "content": "Hello"}]
    assert body["temperature"] == 0.1
    assert body["stream"] is False


def test_llm_client_includes_system_prompt_when_provided():
    client = LLMClient(api_key="sk-test", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash")
    body = client._build_body(
        [{"role": "user", "content": "Hello"}],
        system="You are an auditor.",
    )

    assert body["messages"][0] == {"role": "system", "content": "You are an auditor."}
    assert body["messages"][1] == {"role": "user", "content": "Hello"}


def test_llm_client_uses_custom_temperature():
    client = LLMClient(api_key="sk-test", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash", temperature=0.7)
    body = client._build_body([{"role": "user", "content": "Hello"}])

    assert body["temperature"] == 0.7


@patch.object(urllib.request, "urlopen")
def test_chat_returns_content_on_success(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(
        {"choices": [{"message": {"content": "Hello from API"}}]}
    ).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    client = LLMClient(api_key="sk-test", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash")
    result = client.chat([{"role": "user", "content": "Hi"}])

    assert result == "Hello from API"


@patch.object(urllib.request, "urlopen")
def test_chat_raises_runtime_error_on_http_error(mock_urlopen):
    # HTTPError with a real file-like body
    fp_body = io.BytesIO(b'{"error": "invalid api key"}')
    http_error = urllib.error.HTTPError(
        url="https://api.deepseek.com/v1/chat/completions",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=fp_body,
    )
    mock_urlopen.side_effect = http_error

    client = LLMClient(api_key="sk-bad", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash")

    import pytest
    with pytest.raises(RuntimeError) as excinfo:
        client.chat([{"role": "user", "content": "Hi"}])

    assert "401" in str(excinfo.value)
    assert "invalid api key" in str(excinfo.value)


@patch.object(urllib.request, "urlopen")
def test_chat_raises_runtime_error_on_network_error(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

    client = LLMClient(api_key="sk-test", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash")

    import pytest
    with pytest.raises(RuntimeError) as excinfo:
        client.chat([{"role": "user", "content": "Hi"}])

    assert "network error" in str(excinfo.value).lower()
    assert "Connection refused" in str(excinfo.value)


@patch.object(urllib.request, "urlopen")
def test_chat_raises_runtime_error_on_malformed_json(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"This is not JSON"
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    client = LLMClient(api_key="sk-test", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash")

    import pytest
    with pytest.raises(RuntimeError) as excinfo:
        client.chat([{"role": "user", "content": "Hi"}])

    assert "malformed JSON" in str(excinfo.value)

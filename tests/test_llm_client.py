import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.llm_client import LlmClient


def test_llm_client_builds_correct_request_body():
    client = LlmClient(api_key="sk-test", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash")
    body = client._build_body([{"role": "user", "content": "Hello"}])

    assert body["model"] == "deepseek-v4-flash"
    assert body["messages"] == [{"role": "user", "content": "Hello"}]
    assert body["temperature"] == 0.1
    assert body["stream"] is False


def test_llm_client_includes_system_prompt_when_provided():
    client = LlmClient(api_key="sk-test", api_base="https://api.deepseek.com/v1", model="deepseek-v4-flash")
    body = client._build_body(
        [{"role": "user", "content": "Hello"}],
        system="You are an auditor.",
    )

    assert body["messages"][0] == {"role": "system", "content": "You are an auditor."}
    assert body["messages"][1] == {"role": "user", "content": "Hello"}

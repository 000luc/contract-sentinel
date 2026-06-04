from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
DEFAULT_APPROVAL_OUTPUT_ROOT = Path(r"D:\BaiduSyncdisk\claude\contract-approval")
DEFAULT_CONTRACT_KEYWORDS = ["付款合同评审", "合同评审", "付款合同", "合同"]


@dataclass(frozen=True)
class Settings:
    config_path: Path
    oa_url: str
    cookie_path: Path
    approval_output_root: Path
    poll_interval_seconds: int
    contract_keywords: list[str]
    audit_backend: str
    direct_llm_model: str
    claude_cli_command: str
    deepseek_api_key: str
    deepseek_api_base: str


def _poll_interval_seconds(value: object) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return 300
    return interval if interval >= 1 else 300


def _contract_keywords(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return DEFAULT_CONTRACT_KEYWORDS
    if not all(isinstance(item, str) for item in value):
        return DEFAULT_CONTRACT_KEYWORDS
    return list(value)


def load_settings(config_path: Path = DEFAULT_CONFIG_PATH) -> Settings:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    approval_root = Path(data.get("approval_output_root") or DEFAULT_APPROVAL_OUTPUT_ROOT)
    return Settings(
        config_path=config_path,
        oa_url=data.get("oa_url", "https://oa.grgt.cn/"),
        cookie_path=PROJECT_ROOT / "data" / "oa_cookies.json",
        approval_output_root=approval_root,
        poll_interval_seconds=_poll_interval_seconds(data.get("poll_interval_seconds", 300)),
        contract_keywords=_contract_keywords(data.get("contract_keywords", DEFAULT_CONTRACT_KEYWORDS)),
        audit_backend=data.get("audit_backend", "skill_request"),
        direct_llm_model=data.get("direct_llm_model", "deepseek-chat"),
        claude_cli_command=data.get("claude_cli_command", "claude"),
        deepseek_api_key=data.get("deepseek_api_key", ""),
        deepseek_api_base=data.get("deepseek_api_base", "https://api.deepseek.com/v1"),
    )

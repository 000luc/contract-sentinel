import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.settings import DEFAULT_CONTRACT_KEYWORDS, load_settings
from src.contract_sentinel.state_store import StateStore


def test_state_store_marks_workflow_processed(tmp_path):
    store = StateStore(tmp_path / ".state")
    assert not store.is_processed("11-B-SH2026-30360")

    store.mark_processed("11-B-SH2026-30360", {"title": "场地租赁"})

    assert store.is_processed("11-B-SH2026-30360")


def test_state_store_records_status(tmp_path):
    store = StateStore(tmp_path / ".state")
    store.mark_failed("11-B-SH2026-30360", "download failed")

    record = store.get("11-B-SH2026-30360")
    assert record["status"] == "failed"
    assert record["error"] == "download failed"


def test_state_store_uses_unique_temp_files(tmp_path, monkeypatch):
    store = StateStore(tmp_path / ".state")
    tmp_names = []
    original_replace = Path.replace

    def capture_replace(self, target):
        tmp_names.append(self.name)
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", capture_replace)

    store._save({"one": {"status": "processed"}})
    store._save({"two": {"status": "processed"}})

    assert len(set(tmp_names)) == 2
    assert "processed_workflows.tmp" not in tmp_names


def test_load_settings_falls_back_for_invalid_poll_interval_and_keywords(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "oa_url": "https://example.test/",
                "poll_interval_seconds": 0,
                "contract_keywords": "合同",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.poll_interval_seconds == 300
    assert settings.contract_keywords == DEFAULT_CONTRACT_KEYWORDS


def test_load_settings_falls_back_for_empty_contract_keywords(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"contract_keywords": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.contract_keywords == DEFAULT_CONTRACT_KEYWORDS


def test_load_settings_falls_back_for_non_string_contract_keywords(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"contract_keywords": ["合同", 123]}, ensure_ascii=False),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.contract_keywords == DEFAULT_CONTRACT_KEYWORDS

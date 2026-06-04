import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.attachment_reader import AttachmentReader


def test_read_text_file_returns_content(tmp_path):
    file_path = tmp_path / "contract.txt"
    file_path.write_text("合同金额：100万元", encoding="utf-8")

    assert AttachmentReader.read_text(file_path) == "合同金额：100万元"


def test_read_text_file_truncates_long_content(tmp_path):
    file_path = tmp_path / "long.txt"
    file_path.write_text("A" * 6000, encoding="utf-8")

    result = AttachmentReader.read_text(file_path, max_chars=3000)
    assert len(result) <= 3100  # truncated + suffix message


def test_read_text_skips_unsupported_format(tmp_path):
    file_path = tmp_path / "image.png"
    file_path.write_text("binary", encoding="utf-8")

    result = AttachmentReader.read_text(file_path)
    assert result == ""


def test_summarize_attachments(tmp_path):
    reader = AttachmentReader()
    d = tmp_path
    (d / "a.txt").write_text("aaa", encoding="utf-8")
    (d / "b.txt").write_text("bbb", encoding="utf-8")

    result = reader.summarize(d, max_files=5, max_chars_per_file=2000)
    assert "a.txt" in result
    assert "bbb" in result

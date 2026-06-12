from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.oa_client import OAClient
from src.contract_sentinel.workflow_models import WorkflowItem


def make_client() -> OAClient:
    return OAClient(
        oa_url="https://oa.example.com/base/",
        cookie_path=Path("cookies.json"),
        contract_keywords=["合同"],
    )


def test_absolute_url_joins_relative_paths():
    client = make_client()

    assert client._absolute_url("/workflow/detail") == "https://oa.example.com/workflow/detail"
    assert client._absolute_url("todo/1") == "https://oa.example.com/base/todo/1"
    assert client._absolute_url("https://other.example.com/a") == "https://other.example.com/a"


def test_looks_like_attachment_uses_known_suffixes_case_insensitively():
    assert OAClient._looks_like_attachment("https://oa.example.com/files/合同.DOCX")
    assert OAClient._looks_like_attachment("/download/report.pdf?token=abc")
    assert not OAClient._looks_like_attachment("/workflow/detail?id=1")


def test_filename_from_url_decodes_and_sanitizes_name():
    assert OAClient._filename_from_url("https://oa.example.com/files/%E5%90%88%E5%90%8C.docx") == "合同.docx"
    assert OAClient._filename_from_url("https://oa.example.com/files/CON") == "CON_"


def test_unique_target_path_adds_numeric_suffix(tmp_path):
    output_dir = tmp_path
    (output_dir / "合同.docx").write_text("first", encoding="utf-8")
    (output_dir / "合同_2.docx").write_text("second", encoding="utf-8")

    assert OAClient._unique_target_path(output_dir, "合同.docx") == output_dir / "合同_3.docx"
    assert OAClient._unique_target_path(output_dir, "new.docx") == output_dir / "new.docx"


def test_download_attachments_requires_detail_url(tmp_path):
    client = make_client()
    item = WorkflowItem(workflow_id="11-A-AA2026-1", title="合同评审", detail_url="")

    with pytest.raises(ValueError, match="Workflow detail_url is required for attachment download"):
        client.download_attachments(page=object(), item=item, output_dir=tmp_path)


def test_extract_attachment_links_dedupes_same_href():
    class FakePage:
        def evaluate(self, _script):
            return [
                {"text": "合同", "href": "/files/a.docx", "absoluteHref": "https://oa.example.com/files/a.docx"},
                {"text": "合同副本", "href": "/files/a.docx", "absoluteHref": "https://oa.example.com/files/a.docx"},
            ]

    attachments = make_client()._extract_attachment_links(FakePage())

    assert len(attachments) == 1
    assert attachments[0].href == "https://oa.example.com/files/a.docx"


def test_download_attachments_downloads_regular_attachment_links(tmp_path):
    class FakeResponse:
        ok = True
        status = 200

        def body(self):
            return b"PK\x03\x04" + b"a" * 200

    class FakeRequest:
        def __init__(self):
            self.urls = []

        def get(self, url):
            self.urls.append(url)
            return FakeResponse()

    class FakeContext:
        def __init__(self):
            self.request = FakeRequest()

    class FakeButtons:
        def count(self):
            return 0

    class FakePage:
        def __init__(self):
            self.context = FakeContext()

        def goto(self, url, wait_until, timeout):
            self.url = url

        def wait_for_timeout(self, timeout):
            self.timeout = timeout

        def inner_text(self, selector):
            return ""

        def evaluate(self, _script):
            if "wea-upload-list-item" in _script:
                return []
            return [
                {
                    "text": "合同.docx",
                    "href": "/files/a.docx",
                    "absoluteHref": "https://oa.example.com/files/a.docx",
                }
            ]

        def locator(self, selector):
            assert selector == ".icon-coms-download"
            return FakeButtons()

    item = WorkflowItem(workflow_id="11-A-AA2026-1", title="合同评审", detail_url="/detail")
    page = FakePage()

    attachments = make_client().download_attachments(page, item, tmp_path)

    assert len(attachments) == 1
    assert attachments[0].local_path == tmp_path / "合同.docx"
    assert (tmp_path / "合同.docx").read_bytes() == b"PK\x03\x04" + b"a" * 200
    assert page.context.request.urls == ["https://oa.example.com/files/a.docx"]


def test_download_attachments_returns_empty_when_attachment_link_fails(tmp_path):
    class FakeResponse:
        ok = False
        status = 403

        def body(self):
            return b""

    class FakeRequest:
        def get(self, url):
            return FakeResponse()

    class FakeContext:
        request = FakeRequest()

    class FakeButtons:
        def count(self):
            return 0

    class FakePage:
        context = FakeContext()

        def goto(self, url, wait_until, timeout):
            self.url = url

        def wait_for_timeout(self, timeout):
            self.timeout = timeout

        def inner_text(self, selector):
            return ""

        def evaluate(self, _script):
            if "wea-upload-list-item" in _script:
                return []
            return [
                {
                    "text": "合同.docx",
                    "href": "/files/a.docx",
                    "absoluteHref": "https://oa.example.com/files/a.docx",
                }
            ]

        def locator(self, selector):
            assert selector == ".icon-coms-download"
            return FakeButtons()

    item = WorkflowItem(workflow_id="11-A-AA2026-1", title="合同评审", detail_url="/detail")

    attachments = make_client().download_attachments(FakePage(), item, tmp_path)
    assert attachments == []


def test_download_button_failure_returns_empty_attachments(tmp_path):
    class FakeDownloadContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeButton:
        def click(self, force):
            raise ValueError("click failed")

    class FakeButtons:
        def count(self):
            return 1

        def nth(self, index):
            return FakeButton()

    class FakePage:
        def goto(self, url, wait_until, timeout):
            self.url = url

        def wait_for_timeout(self, timeout):
            self.timeout = timeout

        def evaluate(self, _script):
            return []

        def locator(self, selector):
            assert selector == ".icon-coms-download"
            return FakeButtons()

        def expect_download(self, timeout):
            return FakeDownloadContext()

    item = WorkflowItem(workflow_id="11-A-AA2026-1", title="合同评审", detail_url="/detail")

    attachments = make_client().download_attachments(FakePage(), item, tmp_path)
    assert attachments == []

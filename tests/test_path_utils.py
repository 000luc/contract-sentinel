import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.contract_sentinel.path_utils import build_workflow_dir_name, safe_filename


def test_safe_filename_removes_windows_forbidden_chars():
    assert safe_filename('11/B:合同*评审?') == '11_B_合同_评审_'


def test_safe_filename_limits_length():
    value = safe_filename('A' * 200, max_length=20)
    assert len(value) == 20


def test_safe_filename_strips_space_and_dot_after_truncation():
    assert safe_filename("A" * 19 + ".BBBB", max_length=20) == "A" * 19


def test_safe_filename_appends_suffix_for_windows_reserved_names():
    assert safe_filename("CON") == "CON_"
    assert safe_filename("com1.txt") == "com1_.txt"


def test_build_workflow_dir_name_contains_id_and_title():
    assert build_workflow_dir_name('11-B-SH2026-30360', '场地租赁合同评审') == '11-B-SH2026-30360_场地租赁合同评审'

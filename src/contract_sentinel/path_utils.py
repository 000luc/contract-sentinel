from __future__ import annotations

import re


WINDOWS_FORBIDDEN_CHARS = r'[<>:"/\\|?*\r\n\t]'
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 10)},
}


def _avoid_windows_reserved_name(value: str) -> str:
    stem, separator, suffix = value.partition(".")
    if stem.upper() not in WINDOWS_RESERVED_NAMES:
        return value
    return f"{stem}_{separator}{suffix}" if separator else f"{stem}_"


def safe_filename(value: str, max_length: int = 120) -> str:
    cleaned = re.sub(WINDOWS_FORBIDDEN_CHARS, "_", str(value)).strip(" .")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = "untitled"
    cleaned = cleaned[:max_length].strip(" .")
    if not cleaned:
        cleaned = "untitled"
    return _avoid_windows_reserved_name(cleaned)


def build_workflow_dir_name(workflow_id: str, title: str) -> str:
    return safe_filename(f"{workflow_id}_{title}", max_length=160)

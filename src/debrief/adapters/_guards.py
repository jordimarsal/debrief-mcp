"""Boundary guards shared by the evidence adapters: hostile input dies here (ADR-0004).

Adapter string fields reach the routing.propose text verbatim, so a newline in a
poisoned value could forge proposal lines. Identifier-like fields must be single-line
whitespace-free tokens; free-text fields single-line control-char-free. Containment
checks live here too, so every adapter refuses paths that escape its evidence root
with one implementation instead of two copies that can drift apart.
"""

from __future__ import annotations

import math
import re
import stat
from pathlib import Path
from typing import Any

MISSING_PATH_ERRORS = (FileNotFoundError, NotADirectoryError)

_TOKEN_RE = re.compile(r"\S+")


class Unparseable(Exception):
    """Evidence did not match the format the adapter knows."""


def is_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.stat().st_mode)
    except MISSING_PATH_ERRORS:
        return False


def contained_file(root: Path, candidate: Path, root_label: str = "artifact") -> Path | None:
    """Resolve `candidate` and return it only when it stays under `root` and is a file.

    Without this check an artifact could name any file on the host and its bytes
    would enter findings, bypassing the root boundary every agent-controlled path
    respects. An escaping candidate refuses the whole scan: an evidence tool never
    silently drops a file, nor silently reads past its boundary.
    """
    try:
        resolved = candidate.resolve()
    except OSError as err:
        raise Unparseable(f"{candidate} could not be resolved") from err
    if not resolved.is_relative_to(root):
        raise Unparseable(f"{candidate} resolves outside the {root_label} root")
    return resolved if is_regular_file(resolved) else None


def required_str(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise Unparseable(f"{key} is not a non-empty string")
    return value


def required_token(document: dict[str, Any], key: str) -> str:
    """Identifier-like field: one non-empty, whitespace-free line (no newline forgery)."""
    value = required_str(document, key)
    if _TOKEN_RE.fullmatch(value) is None:
        raise Unparseable(f"{key} is not a single-line whitespace-free token: {value!r}")
    refuse_control_chars(key, value)
    return value


def required_line(document: dict[str, Any], key: str) -> str:
    """Free-text field: one non-empty line with no control characters (incl. newlines).

    The single-line rule is str.splitlines(), not just ``ord(ch) < 0x20``: Unicode
    line separators (U+0085 NEL, U+2028, U+2029) sit above that range but still
    split the value everywhere Python splits text, so a poisoned value could smuggle
    a forged proposal line past a pure control-character check.
    """
    value = required_str(document, key)
    refuse_control_chars(key, value)
    if value.splitlines() != [value]:
        raise Unparseable(f"{key} is not a single line: {value!r}")
    return value


def required_int(document: dict[str, Any], key: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise Unparseable(f"{key} is not an integer")
    if value < 0:
        raise Unparseable(f"{key} is negative: {value}")
    return value


def required_bool(document: dict[str, Any], key: str) -> bool:
    value = document.get(key)
    if not isinstance(value, bool):
        raise Unparseable(f"{key} is not a boolean")
    return value


def required_measure(document: dict[str, Any], key: str) -> float:
    """A finite float; NaN/Infinity/huge-int would fabricate a comparison winner."""
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Unparseable(f"{key} is not a number")
    try:
        measure = float(value)
    except OverflowError as err:
        raise Unparseable(f"{key} overflows a float: {value}") from err
    if not math.isfinite(measure):
        raise Unparseable(f"{key} is not a finite number: {measure!r}")
    return measure


def required_counts(document: dict[str, Any], key: str) -> dict[str, int]:
    """Graded counts per dimension; names join the signature, so they are tokens too."""
    counts = document.get(key)
    if not isinstance(counts, dict):
        raise Unparseable(f"{key} is not an object of counts")
    mapped: dict[str, int] = {}
    for dimension, count in counts.items():
        if not isinstance(dimension, str):
            raise Unparseable(f"{key} dimension is not a name: {dimension!r}")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise Unparseable(f"{key} count is not a non-negative integer: {count!r}")
        if _TOKEN_RE.fullmatch(dimension) is None:
            raise Unparseable(f"{key} dimension is not a single-line token: {dimension!r}")
        mapped[dimension] = count
    return mapped


def required_str_list(document: dict[str, Any], key: str) -> list[str]:
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise Unparseable(f"{key} is not a list of strings")
    for item in value:
        refuse_control_chars(key, item)
    return list(value)


def refuse_control_chars(key: str, value: str) -> None:
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise Unparseable(f"{key} contains control characters: {value!r}")

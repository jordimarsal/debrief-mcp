"""ggufbench artifacts adapter: read-only mapping of artifact rows to Findings (R3).

Layout: one ``<run-id>/results.json`` per ggufbench run under the artifact root.
The adapter is the only place that knows this format (ADR-0002).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from debrief.adapters._guards import (
    Unparseable,
    contained_file,
    required_counts,
    required_line,
    required_measure,
    required_str,
    required_token,
)
from debrief.domain import OUTCOMES, Finding, TaskSignature
from debrief.errors import BENCH_SOURCE_MISSING, SOURCE_UNPARSEABLE, DebriefError

log = logging.getLogger(__name__)

RESULTS_FILE = "results.json"


class GgufbenchStore:
    """BenchStore over ggufbench artifacts; opens files for reading only (R2, R3)."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root

    def findings(self) -> list[Finding] | DebriefError:
        try:
            results_files = self._results_files()
        except OSError as err:
            return DebriefError(
                code=SOURCE_UNPARSEABLE,
                message=f"{self._artifact_root} could not be scanned for {RESULTS_FILE}",
                detail=str(err),
            )
        except Unparseable as err:
            # A symlink below the requested path must not turn the store into a
            # read primitive for files outside the evidence root (conventions:
            # resolve against an explicit allowed root — security-audit A03).
            return DebriefError(
                code=SOURCE_UNPARSEABLE,
                message=f"a run's {RESULTS_FILE} escapes the ggufbench artifact root",
                detail=str(err),
            )
        if results_files is None:
            return DebriefError(
                code=BENCH_SOURCE_MISSING,
                message="no ggufbench artifacts at the requested path",
                detail=str(self._artifact_root),
            )
        if not results_files:
            return DebriefError(
                code=BENCH_SOURCE_MISSING,
                message=f"no {RESULTS_FILE} under any run directory",
                detail=str(self._artifact_root),
            )
        findings: list[Finding] = []
        for results_file in results_files:
            mapped = _read_run(results_file)
            if isinstance(mapped, DebriefError):
                return mapped
            findings.extend(mapped)
        log.info("read %d ggufbench row(s) from %d run(s)", len(findings), len(results_files))
        return findings

    def _results_files(self) -> list[Path] | None:
        """One results.json per run under the root; None when the root itself is absent.

        Scans with stat(), not is_file(): pathlib's is_*() answer False for
        unreadable directories, which would silently drop a run the tool must
        report; stat() raises, and findings() maps that to a structured error.
        Every candidate is resolved and required to stay under the resolved
        root before anything is read, so symlink indirection below the
        requested path cannot escape the evidence root (A03).
        """
        root = self._artifact_root.resolve()
        if not root.is_dir():
            return None
        own = _contained_results(root, root / RESULTS_FILE)
        if own is not None:
            return [own]
        found: list[Path] = []
        for path in root.iterdir():
            contained = _contained_results(root, path / RESULTS_FILE)
            if contained is not None:
                found.append(contained)
        return sorted(found)


def _contained_results(root: Path, candidate: Path) -> Path | None:
    """Resolve `candidate` and return it only when it stays under `root` and is a file.

    A `<run>/results.json` may be a symlink: without this check an artifact could
    name any file on the host and its bytes would enter findings. An escaping
    candidate refuses the whole scan (see `_guards.contained_file`).
    """
    return contained_file(root, candidate)


def _read_run(results_file: Path) -> list[Finding] | DebriefError:
    try:
        document: Any = json.loads(results_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as err:
        # ValueError covers JSONDecodeError and undecodable bytes; RecursionError
        # covers nesting-bomb JSON, which no legitimate artifact carries.
        return DebriefError(
            code=SOURCE_UNPARSEABLE,
            message=f"{results_file} could not be read as JSON",
            detail=str(err),
        )
    try:
        return _map_document(document)
    except Unparseable as err:
        return DebriefError(
            code=SOURCE_UNPARSEABLE,
            message=f"{results_file} is not a ggufbench results document",
            detail=str(err),
        )


def _map_document(document: Any) -> list[Finding]:
    if not isinstance(document, dict):
        raise Unparseable("document is not an object")
    engine_build = required_token(document, "engine_build")
    baseline = required_token(document, "baseline")
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise Unparseable("rows is not an array")
    return [_map_row(row, baseline, engine_build) for row in rows]


def _map_row(row: Any, baseline: str, engine_build: str) -> Finding:
    if not isinstance(row, dict):
        raise Unparseable("row is not an object")
    graded = required_counts(row, "graded")
    measure = required_measure(row, "score")
    outcome = required_str(row, "outcome")
    if outcome not in OUTCOMES:
        raise Unparseable(f"outcome is not one of {sorted(OUTCOMES)}: {outcome!r}")
    return Finding(
        model=required_token(row, "model"),
        task=required_token(row, "task"),
        outcome=outcome,
        reason=required_line(row, "reason"),
        evidence=required_line(row, "artifact"),
        signature=TaskSignature.of(graded, baseline, engine_build),
        measure=measure,
    )

"""fleet-eval results adapter: read-only mapping of graded answers to Findings (R12).

Layout: ``<root>/answers/<model>/grade.json`` carries tasks A–D for that model,
``grade_E.json`` plus ``grade_E_func.json`` carry task E, and the delivered answer is
``answers/<model>/<task>.md``. The battery itself (prompts, graders, task fixtures) and
the engine logs next to ``answers/`` provide the task signature (R13). The adapter is
the only place that knows this format (ADR-0002).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from debrief.adapters._guards import (
    MISSING_PATH_ERRORS,
    Unparseable,
    contained_file,
    is_regular_file,
    required_bool,
    required_int,
    required_measure,
    required_str_list,
    required_token,
)
from debrief.domain import PASS, Finding, TaskSignature
from debrief.errors import EVAL_SOURCE_MISSING, SOURCE_UNPARSEABLE, DebriefError

log = logging.getLogger(__name__)

ANSWERS_DIR = "answers"
LOGS_DIR = "logs"
GRADE_FILE = "grade.json"
GRADE_E_FILE = "grade_E.json"
GRADE_E_FUNC_FILE = "grade_E_func.json"

BATTERY_FILES = ("grade.py", "grade_E.py", "check_E.py")
BATTERY_DIRS = ("prompts", "task_a", "task_b", "task_c", "task_d")

TASK_NAMES = {
    "A": "A_implement",
    "B": "B_fix",
    "C": "C_review",
    "D": "D_diagnose",
    "E": "E_largefile",
}

C_RECALL_MIN = 0.85
E_LINE_RATIO_MIN = 0.90

DELIVERY_FAILURE_REASON = "delivery failure: no code block in the answer"


@dataclass(frozen=True)
class _Model:
    """One model's parsed result files; the battery pre-pass reads these once."""

    name: str
    model_dir: Path
    graded: dict[str, Any]
    grade_e: dict[str, Any] | None
    probes: dict[str, Any] | None


class FleetEvalStore:
    """EvalStore over fleet-eval results; opens files for reading only (R2, R12)."""

    def __init__(self, results_root: Path) -> None:
        self._results_root = results_root

    def findings(self) -> list[Finding] | DebriefError:
        try:
            model_dirs = self._model_dirs()
        except OSError as err:
            return DebriefError(
                code=SOURCE_UNPARSEABLE,
                message=f"{self._results_root} could not be scanned for fleet-eval results",
                detail=str(err),
            )
        except Unparseable as err:
            return DebriefError(
                code=SOURCE_UNPARSEABLE,
                message="a fleet-eval result escapes the evidence root",
                detail=str(err),
            )
        if model_dirs is None:
            return DebriefError(
                code=EVAL_SOURCE_MISSING,
                message="no fleet-eval results at the requested path",
                detail=str(self._results_root),
            )
        if not model_dirs:
            return DebriefError(
                code=EVAL_SOURCE_MISSING,
                message=f"no {ANSWERS_DIR}/<model>/{GRADE_FILE} under the requested path",
                detail=str(self._results_root),
            )
        root = self._results_root.resolve()
        models: list[_Model] = []
        for model_dir in model_dirs:
            loaded = _load_model(root, model_dir)
            if isinstance(loaded, DebriefError):
                return loaded
            models.append(loaded)
        signature = _signature(root, models)
        if isinstance(signature, DebriefError):
            return signature
        findings: list[Finding] = []
        for model in models:
            mapped = _map_model(root, model, signature)
            if isinstance(mapped, DebriefError):
                return mapped
            findings.extend(mapped)
        log.info("read %d fleet-eval finding(s) from %d model(s)", len(findings), len(models))
        return findings

    def _model_dirs(self) -> list[Path] | None:
        """Model directories carrying a graded result; None when the root itself is absent.

        iterdir(), not is_dir(): pathlib's predicates answer False for unreadable
        directories, which would report a locked checkout as an empty one. Every
        candidate is resolved and required to stay under the resolved root before
        anything is read, so symlink indirection cannot escape the evidence root.
        """
        root = self._results_root.resolve()
        try:
            entries = sorted((root / ANSWERS_DIR).iterdir())
        except MISSING_PATH_ERRORS:
            return None
        found: list[Path] = []
        for entry in entries:
            if contained_file(root, entry / GRADE_FILE, "fleet-eval") is not None:
                found.append(entry)
        return found


def _load_model(root: Path, model_dir: Path) -> _Model | DebriefError:
    name = model_dir.name
    grade_path = model_dir / GRADE_FILE
    graded = _read_json(grade_path)
    if isinstance(graded, DebriefError):
        return graded
    try:
        if required_token(graded, "model") != name:
            raise Unparseable(f"graded model name does not match its directory: {name!r}")
    except Unparseable as err:
        return _model_error(grade_path, err)
    grade_e_path = contained_file(root, model_dir / GRADE_E_FILE, "fleet-eval")
    if grade_e_path is None:
        return _Model(name=name, model_dir=model_dir, graded=graded, grade_e=None, probes=None)
    grade_e = _read_json(grade_e_path)
    if isinstance(grade_e, DebriefError):
        return grade_e
    probes_path = contained_file(root, model_dir / GRADE_E_FUNC_FILE, "fleet-eval")
    if probes_path is None:
        return DebriefError(
            code=SOURCE_UNPARSEABLE,
            message=f"{name}/{GRADE_E_FILE} has no {GRADE_E_FUNC_FILE}",
            detail=str(grade_e_path),
        )
    probes = _read_json(probes_path)
    if isinstance(probes, DebriefError):
        return probes
    return _Model(name=name, model_dir=model_dir, graded=graded, grade_e=grade_e, probes=probes)


def _read_json(path: Path) -> dict[str, Any] | DebriefError:
    try:
        document: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as err:
        return DebriefError(
            code=SOURCE_UNPARSEABLE,
            message=f"{path} could not be read as JSON",
            detail=str(err),
        )
    if not isinstance(document, dict):
        return DebriefError(
            code=SOURCE_UNPARSEABLE,
            message=f"{path} is not a JSON object",
            detail=f"got {type(document).__name__}",
        )
    return document


def _signature(root: Path, models: list[_Model]) -> TaskSignature | DebriefError:
    try:
        counts = _battery_counts(models)
        baseline = _battery_digest(root)
        engine_build = _engine_family(root)
    except Unparseable as err:
        return DebriefError(
            code=SOURCE_UNPARSEABLE,
            message="the fleet-eval battery cannot be established from these results",
            detail=str(err),
        )
    except OSError as err:
        return DebriefError(
            code=SOURCE_UNPARSEABLE,
            message="the fleet-eval battery files could not be read",
            detail=str(err),
        )
    return TaskSignature.of(counts, baseline, engine_build)


def _battery_counts(models: list[_Model]) -> dict[str, int]:
    """Graded dimensions of the battery, not of one model's coverage (R13).

    A model can be missing a task (the variant runs skipped E); the battery still asks
    it, so the signature keeps the dimension and the missing task simply yields no row.
    A zero records "nothing ran" (a delivery failure), not another battery, so it never
    lowers the dimension; two different non-zero counts do refuse, because that is a
    different battery under the same root.
    """
    counts: dict[str, int] = {}
    for model in models:
        for dimension, count in _model_counts(model).items():
            known = counts.setdefault(dimension, 0)
            if count == 0:
                continue
            if known not in (0, count):
                raise Unparseable(
                    f"battery mismatch on {dimension}: {model.name} graded {count}, "
                    f"another model graded {known}"
                )
            counts[dimension] = count
    return counts


def _model_counts(model: _Model) -> dict[str, int]:
    counts = {
        task: required_int(_task_block(model.graded, task), "passed")
        + required_int(_task_block(model.graded, task), "failed")
        for task in ("A", "B")
    }
    counts["C"] = len(required_str_list(_task_block(model.graded, "C"), "found")) + len(
        required_str_list(_task_block(model.graded, "C"), "missing")
    )
    counts["D"] = required_int(_task_block(model.graded, "D"), "max")
    if model.probes is not None:
        counts["E"] = len(required_str_list(model.probes, "ok")) + len(
            required_str_list(model.probes, "fail")
        )
    return counts


def _battery_digest(root: Path) -> str:
    """sha256 over the battery's prompts, graders and task fixtures (first 12 hex)."""
    paths = _battery_paths(root)
    if not paths:
        raise Unparseable(f"no battery files under {root}")
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def _battery_paths(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for name in BATTERY_FILES:
        path = contained_file(root, root / name, "fleet-eval")
        if path is not None:
            candidates.append(path)
    for name in BATTERY_DIRS:
        directory = root / name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if "__pycache__" in path.parts:
                continue
            contained = contained_file(root, path, "fleet-eval")
            if contained is not None:
                candidates.append(contained)
    return sorted(candidates)


def _engine_family(root: Path) -> str:
    """Engine families present in the run logs, e.g. ``llama.cpp`` or ``llama.cpp+strata``.

    Derived from the artifacts (a ``.cmd`` log vs a ``.strata.out`` log), never from a
    label the results carry. The model is the variable under test, so per-model engine
    flags stay out of the signature; the family is a property of the whole cohort.
    """
    families: set[str] = set()
    logs = root / LOGS_DIR
    if logs.is_dir():
        for entry in sorted(logs.iterdir()):
            if not is_regular_file(entry):
                continue
            if entry.suffix == ".cmd":
                families.add("llama.cpp")
            elif entry.name.endswith(".strata.out"):
                families.add("strata")
    return "+".join(sorted(families)) if families else "unrecorded"


def _map_model(
    root: Path, model: _Model, signature: TaskSignature
) -> list[Finding] | DebriefError:
    grade_path = model.model_dir / GRADE_FILE
    try:
        findings = [
            _map_task_a_b(root, model, "A", signature),
            _map_task_a_b(root, model, "B", signature),
            _map_task_c(root, model, signature),
            _map_task_d(root, model, signature),
        ]
        delivered = _map_task_e(root, model, signature)
    except Unparseable as err:
        return _model_error(grade_path, err)
    return findings + delivered


def _model_error(path: Path, err: Unparseable) -> DebriefError:
    return DebriefError(
        code=SOURCE_UNPARSEABLE,
        message=f"{path} is not a fleet-eval graded result",
        detail=str(err),
    )


def _task_block(document: dict[str, Any], task: str) -> dict[str, Any]:
    block = document.get(task)
    if not isinstance(block, dict):
        raise Unparseable(f"{task} is not a graded task object")
    return block


def _evidence(root: Path, model: str, task: str) -> str:
    relative = f"{ANSWERS_DIR}/{model}/{TASK_NAMES[task]}.md"
    if contained_file(root, root / relative, "fleet-eval") is None:
        raise Unparseable(f"the answer file {relative} is missing")
    return relative


def _map_task_a_b(
    root: Path, model: _Model, task: str, signature: TaskSignature
) -> Finding:
    block = _task_block(model.graded, task)
    evidence = _evidence(root, model.name, task)
    if required_int(block, "blocks") == 0:
        return _delivery_failure(model.name, task, evidence, signature)
    passed = required_int(block, "passed")
    failed = required_int(block, "failed")
    total = passed + failed
    if total == 0:
        raise Unparseable(f"{task} graded zero tests")
    syntax_ok = required_bool(block, "syntax_ok")
    applied = required_bool(block, "applied")
    return Finding(
        model=model.name,
        task=TASK_NAMES[task],
        outcome=PASS if failed == 0 and syntax_ok and applied else "fail",
        reason=f"{passed}/{total} test(s) passed",
        evidence=evidence,
        signature=signature,
        measure=passed / total,
    )


def _map_task_c(root: Path, model: _Model, signature: TaskSignature) -> Finding:
    block = _task_block(model.graded, "C")
    recall = required_measure(block, "recall")
    if not 0.0 <= recall <= 1.0:
        raise Unparseable(f"recall is outside [0, 1]: {recall}")
    seeded = len(required_str_list(block, "found")) + len(required_str_list(block, "missing"))
    if seeded == 0:
        raise Unparseable("C graded zero seeded defects")
    false_positives = required_int(block, "false_positives_est")
    return Finding(
        model=model.name,
        task=TASK_NAMES["C"],
        outcome=PASS if recall >= C_RECALL_MIN and false_positives == 0 else "fail",
        reason=(
            f"recall {recall:.2f} over {seeded} seeded defect(s); "
            f"{false_positives} estimated false positive(s)"
        ),
        evidence=_evidence(root, model.name, "C"),
        signature=signature,
        measure=recall,
    )


def _map_task_d(root: Path, model: _Model, signature: TaskSignature) -> Finding:
    block = _task_block(model.graded, "D")
    total = required_int(block, "total")
    maximum = required_int(block, "max")
    if maximum == 0:
        raise Unparseable("D graded zero root causes")
    if total > maximum:
        raise Unparseable(f"D scored {total} above its maximum {maximum}")
    return Finding(
        model=model.name,
        task=TASK_NAMES["D"],
        outcome=PASS if total == maximum else "fail",
        reason=f"{total}/{maximum} root cause(s) and fix(es) named",
        evidence=_evidence(root, model.name, "D"),
        signature=signature,
        measure=total / maximum,
    )


def _map_task_e(root: Path, model: _Model, signature: TaskSignature) -> list[Finding]:
    if model.grade_e is None or model.probes is None:
        return []
    evidence = _evidence(root, model.name, "E")
    if required_int(model.grade_e, "blocks") == 0:
        return [_delivery_failure(model.name, "E", evidence, signature)]
    ratio = required_measure(model.grade_e, "line_ratio")
    if ratio < 0.0:
        raise Unparseable(f"line_ratio is negative: {ratio}")
    missing = required_str_list(model.grade_e, "symbols_missing")
    placeholder = required_bool(model.grade_e, "placeholder")
    failed_probes = required_str_list(model.probes, "fail")
    required_str_list(model.probes, "ok")
    complete = not missing and not placeholder and not failed_probes
    return [
        Finding(
            model=model.name,
            task=TASK_NAMES["E"],
            outcome=PASS if complete and ratio >= E_LINE_RATIO_MIN else "fail",
            reason=(
                f"line ratio {ratio:.2f}; {len(missing)} symbol(s) missing; "
                f"{len(failed_probes)} probe(s) failing"
            ),
            evidence=evidence,
            signature=signature,
            measure=ratio,
        )
    ]


def _delivery_failure(
    model: str, task: str, evidence: str, signature: TaskSignature
) -> Finding:
    return Finding(
        model=model,
        task=TASK_NAMES[task],
        outcome="fail",
        reason=DELIVERY_FAILURE_REASON,
        evidence=evidence,
        signature=signature,
        measure=0.0,
    )

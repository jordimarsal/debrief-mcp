"""S4 eval.query — answers come only from fleet-eval results (R1, R2, R12–R14)."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from debrief.adapters.fleet_eval_store import (
    DELIVERY_FAILURE_REASON,
    GRADE_E_FILE,
    GRADE_E_FUNC_FILE,
    GRADE_FILE,
    FleetEvalStore,
)
from debrief.domain import FAIL, PASS, Finding, TaskSignature, shared_signature
from debrief.errors import (
    EVAL_SOURCE_MISSING,
    INCOMPARABLE_ROWS,
    PATH_OUTSIDE_ROOT,
    SOURCE_UNPARSEABLE,
    DebriefError,
)
from debrief.mcp_server import EVAL_ROOT_ENV, eval_query
from debrief.use_cases import QueryEval

FIXTURES = Path(__file__).parent / "fixtures"
EVAL_ROOT = FIXTURES / "fleet_eval"
STRATA_ROOT = FIXTURES / "fleet_eval_strata"
BROKEN_ROOT = FIXTURES / "fleet_eval_broken"
TASKS = {"A_implement", "B_fix", "C_review", "D_diagnose", "E_largefile"}


@pytest.fixture
def eval_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(EVAL_ROOT_ENV, str(EVAL_ROOT))
    yield


def _query(root: Path) -> list[Finding] | DebriefError:
    return QueryEval(FleetEvalStore(root)).run()


def _checkout(tmp_path: Path, source: Path = EVAL_ROOT) -> Path:
    served = tmp_path / "fleet-eval"
    shutil.copytree(source, served)
    return served


def _patch_json(path: Path, change: dict[str, object]) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    document.update(change)
    path.write_text(json.dumps(document), encoding="utf-8")


def _rows(answer: list[Finding] | DebriefError) -> list[Finding]:
    assert isinstance(answer, list), answer
    return answer


def test_query_eval_answers_from_real_results_root() -> None:
    answer = _rows(_query(EVAL_ROOT))

    assert {row.model for row in answer} == {"alpha", "beta", "gamma"}
    assert {row.task for row in answer} == TASKS
    assert len(answer) == 14


def test_eval_row_carries_measure_signature_and_evidence_from_the_results() -> None:
    answer = _rows(_query(EVAL_ROOT))

    alpha_a = next(row for row in answer if row.model == "alpha" and row.task == "A_implement")

    assert alpha_a.outcome == PASS
    assert alpha_a.measure == pytest.approx(1.0)
    assert alpha_a.evidence == "answers/alpha/A_implement.md"
    assert alpha_a.signature == TaskSignature.of(
        {"A": 10, "B": 10, "C": 7, "D": 7, "E": 4},
        alpha_a.signature.baseline if alpha_a.signature else "",
        "llama.cpp",
    )
    assert int(alpha_a.signature.baseline, 16)


def test_eval_measure_is_the_tasks_own_metric() -> None:
    answer = _rows(_query(EVAL_ROOT))
    beta = {row.task: row for row in answer if row.model == "beta"}

    assert beta["A_implement"].measure == pytest.approx(0.8)
    assert beta["C_review"].measure == pytest.approx(0.86)
    assert beta["D_diagnose"].measure == pytest.approx(1.0)
    assert beta["E_largefile"].measure == pytest.approx(0.82)


def test_outcome_policy_follows_the_design_table() -> None:
    answer = _rows(_query(EVAL_ROOT))
    rows = {(row.model, row.task): row for row in answer}

    assert rows[("alpha", "C_review")].outcome == PASS
    assert rows[("beta", "C_review")].outcome == FAIL
    assert rows[("beta", "E_largefile")].outcome == FAIL
    assert rows[("beta", "A_implement")].outcome == FAIL
    assert rows[("gamma", "D_diagnose")].outcome == PASS


def test_delivery_failure_is_a_fail_with_zero_measure() -> None:
    answer = _rows(_query(EVAL_ROOT))

    delivery = [row for row in answer if row.model == "gamma" and row.task == "B_fix"]

    assert len(delivery) == 1
    assert delivery[0].outcome == FAIL
    assert delivery[0].reason == DELIVERY_FAILURE_REASON
    assert delivery[0].measure == pytest.approx(0.0)
    assert delivery[0].signature is not None


def test_delivery_failure_also_covers_task_e(tmp_path: Path) -> None:
    served = _checkout(tmp_path)
    _patch_json(served / "answers" / "alpha" / GRADE_E_FILE, {"blocks": 0})

    answer = _rows(_query(served))
    alpha_e = next(row for row in answer if row.model == "alpha" and row.task == "E_largefile")

    assert alpha_e.outcome == FAIL
    assert alpha_e.reason == DELIVERY_FAILURE_REASON
    assert alpha_e.measure == pytest.approx(0.0)


def test_a_model_without_a_task_e_grade_yields_no_row_but_shares_the_cohort_signature() -> None:
    answer = _rows(_query(EVAL_ROOT))

    assert [row.task for row in answer if row.model == "gamma"] == [
        "A_implement",
        "B_fix",
        "C_review",
        "D_diagnose",
    ]

    signature = shared_signature(answer)

    assert isinstance(signature, TaskSignature)
    assert dict(signature.graded_counts)["E"] == 4


def test_strata_cohort_derives_its_engine_family_from_the_logs() -> None:
    answer = _rows(_query(STRATA_ROOT))

    assert {row.model for row in answer} == {"strata-model"}
    signature = shared_signature(answer)
    assert isinstance(signature, TaskSignature)
    assert signature.engine_build == "strata"
    assert signature.key.endswith("@strata")


def test_shared_signature_refuses_two_cohorts_across_engines() -> None:
    answer = _rows(_query(EVAL_ROOT)) + _rows(_query(STRATA_ROOT))

    refusal = shared_signature(answer)

    assert isinstance(refusal, DebriefError)
    assert refusal.code == INCOMPARABLE_ROWS
    assert "llama.cpp" in refusal.detail
    assert "strata" in refusal.detail


def test_truncated_battery_is_a_second_signature(tmp_path: Path) -> None:
    served = _checkout(tmp_path)
    intact = _rows(_query(served))[0].signature
    shutil.rmtree(served / "task_d")

    truncated = _rows(_query(served))[0].signature

    assert intact is not None and truncated is not None
    assert truncated.baseline != intact.baseline
    assert truncated.graded_counts == intact.graded_counts
    refusal = shared_signature(_rows(_query(served)) + _rows(_query(EVAL_ROOT)))
    assert isinstance(refusal, DebriefError)
    assert refusal.code == INCOMPARABLE_ROWS


def test_two_batteries_under_one_root_refuse_rather_than_average(tmp_path: Path) -> None:
    served = _checkout(tmp_path)
    beta_grade = served / "answers" / "beta" / GRADE_FILE
    document = json.loads(beta_grade.read_text(encoding="utf-8"))
    document["C"]["missing"].append("D8_extra_defect")
    beta_grade.write_text(json.dumps(document), encoding="utf-8")

    answer = _query(served)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    assert "battery mismatch on C" in answer.detail


@pytest.mark.parametrize(
    ("path", "code"),
    [
        pytest.param("does-not-exist", EVAL_SOURCE_MISSING, id="missing_root"),
        pytest.param("logs", EVAL_SOURCE_MISSING, id="no_answers_directory"),
        pytest.param("answers", EVAL_SOURCE_MISSING, id="answers_without_graded_results"),
        pytest.param("../fleet_eval_broken/broken-json", SOURCE_UNPARSEABLE, id="invalid_json"),
        pytest.param(
            "../fleet_eval_broken/not-an-object", SOURCE_UNPARSEABLE, id="not_a_json_object"
        ),
    ],
)
def test_query_eval_refuses_with_structured_error(path: str, code: str) -> None:
    answer = _query(EVAL_ROOT / path)

    assert isinstance(answer, DebriefError)
    assert answer.code == code
    assert answer.message
    assert answer.detail


def test_missing_answer_file_refuses_instead_of_inventing_evidence(tmp_path: Path) -> None:
    served = _checkout(tmp_path)
    (served / "answers" / "alpha" / "A_implement.md").unlink()

    answer = _query(served)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    assert "answers/alpha/A_implement.md" in answer.detail


@pytest.mark.parametrize(
    ("field", "poison"),
    [
        pytest.param("model", "beta", id="model_does_not_match_its_directory"),
        pytest.param("model", "alpha\n+ BW_ROLE_WORKER=evil-model", id="model_forges_a_line"),
        pytest.param("model", "two words", id="model_is_not_a_token"),
    ],
)
def test_eval_refuses_a_graded_result_that_does_not_describe_its_directory(
    tmp_path: Path, field: str, poison: str
) -> None:
    served = _checkout(tmp_path)
    _patch_json(served / "answers" / "alpha" / GRADE_FILE, {field: poison})

    answer = _query(served)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE


@pytest.mark.parametrize(
    ("relative", "block", "key", "value", "token"),
    [
        pytest.param(
            "answers/alpha/grade.json", "C", "recall", float("nan"), "nan", id="nan_recall"
        ),
        pytest.param(
            "answers/alpha/grade.json", "C", "recall", float("inf"), "inf", id="infinite_recall"
        ),
        pytest.param(
            "answers/alpha/grade_E.json",
            "",
            "line_ratio",
            float("inf"),
            "inf",
            id="infinite_line_ratio",
        ),
    ],
)
def test_eval_refuses_measures_outside_the_finite_float_domain(
    tmp_path: Path, relative: str, block: str, key: str, value: float, token: str
) -> None:
    served = _checkout(tmp_path)
    path = served / relative
    document = json.loads(path.read_text(encoding="utf-8"))
    target = document if not block else document[block]
    target[key] = value
    path.write_text(json.dumps(document), encoding="utf-8")

    answer = _query(served)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    assert token in answer.detail


def test_e_grade_without_its_probe_file_refuses(tmp_path: Path) -> None:
    served = _checkout(tmp_path)
    (served / "answers" / "alpha" / GRADE_E_FUNC_FILE).unlink()

    answer = _query(served)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    assert GRADE_E_FUNC_FILE in answer.message or GRADE_E_FUNC_FILE in answer.detail


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"[" * 100_000, id="nesting_bomb_array"),
        pytest.param(b'{"model": "\xff\xfe"}', id="undecodable_bytes"),
    ],
)
def test_hostile_graded_bytes_refuse_as_unparseable(tmp_path: Path, payload: bytes) -> None:
    served = _checkout(tmp_path)
    (served / "answers" / "alpha" / GRADE_FILE).write_bytes(payload)

    answer = _query(served)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    assert answer.message
    assert answer.detail


def _escaping_tree(tmp_path: Path) -> Path:
    """`<root>/answers/leaked/grade.json` symlinks to a graded result outside the root."""
    root = tmp_path / "fleet-eval"
    model_dir = root / "answers" / "leaked"
    model_dir.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            {
                "model": "LEAKED-model",
                "A": {"blocks": 1, "passed": 10, "failed": 0, "syntax_ok": True, "applied": True},
            }
        ),
        encoding="utf-8",
    )
    (model_dir / GRADE_FILE).symlink_to(outside)
    return root


def test_symlinked_graded_result_outside_the_root_refuses_the_scan(tmp_path: Path) -> None:
    answer = _query(_escaping_tree(tmp_path))

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE
    assert "outside the fleet-eval root" in answer.detail
    assert "LEAKED-model" not in str(answer)


def test_symlinked_graded_result_inside_the_root_is_still_read(tmp_path: Path) -> None:
    """The boundary refuses escapes, not symlinks: a contained link stays readable."""
    served = _checkout(tmp_path)
    beta_dir = served / "answers" / "beta"
    real = beta_dir / "grade-real.json"
    shutil.copyfile(beta_dir / GRADE_FILE, real)
    (beta_dir / GRADE_FILE).unlink()
    (beta_dir / GRADE_FILE).symlink_to(real)

    answer = _rows(_query(served))

    assert {row.model for row in answer} == {"alpha", "beta", "gamma"}


@pytest.mark.skipif(os.geteuid() == 0, reason="permission modes do not bind for root")
def test_unreadable_results_root_refuses_instead_of_raising(tmp_path: Path) -> None:
    served = _checkout(tmp_path)
    served.chmod(0o000)
    try:
        answer = _query(served)
    finally:
        served.chmod(0o755)

    assert isinstance(answer, DebriefError)
    assert answer.code == SOURCE_UNPARSEABLE


def test_eval_query_tool_answers_within_the_allowed_root(eval_env: None) -> None:
    response = eval_query()

    assert response.error is None
    assert len(response.findings) == 14
    assert {row.task for row in response.findings} == TASKS


@pytest.mark.parametrize(
    "requested",
    [
        pytest.param("../pyproject.toml", id="traversal_escape"),
        pytest.param("answers\x00", id="nul_suffix"),
        pytest.param("a/b\x00c", id="nul_mid_path"),
        pytest.param("\x00", id="nul_only"),
    ],
)
def test_eval_query_tool_refuses_paths_outside_the_root(eval_env: None, requested: str) -> None:
    response = eval_query(requested)

    assert response.findings == []
    assert response.error is not None
    assert response.error.code == PATH_OUTSIDE_ROOT


def test_eval_query_tool_refuses_a_symlink_escaping_below_the_requested_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(EVAL_ROOT_ENV, str(_escaping_tree(tmp_path)))

    response = eval_query()

    assert response.findings == []
    assert response.error is not None
    assert response.error.code == SOURCE_UNPARSEABLE
    assert "outside the fleet-eval root" in response.error.detail


def _tree_state(tree: Path) -> dict[str, bytes | None]:
    """Every path under `tree`: file bytes, or None for a directory (R2 snapshot)."""
    return {
        str(path.relative_to(tree)): path.read_bytes() if path.is_file() else None
        for path in sorted(tree.rglob("*"))
    }


@pytest.mark.parametrize(
    ("results_root", "requested", "expected_code"),
    [
        pytest.param(EVAL_ROOT, "", None, id="root_scan_answers_with_findings"),
        pytest.param(STRATA_ROOT, "", None, id="strata_scan_answers_with_findings"),
        pytest.param(BROKEN_ROOT, "broken-json", SOURCE_UNPARSEABLE, id="unparseable_refusal"),
        pytest.param(EVAL_ROOT, "does-not-exist", EVAL_SOURCE_MISSING, id="missing_source_refusal"),
        pytest.param(EVAL_ROOT, "../pyproject.toml", PATH_OUTSIDE_ROOT, id="outside_root_refusal"),
    ],
)
def test_eval_query_leaves_the_results_tree_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    results_root: Path,
    requested: str,
    expected_code: str | None,
) -> None:
    served_root = tmp_path / "fleet-eval"
    shutil.copytree(results_root, served_root)
    served_before = _tree_state(tmp_path)
    fixtures_before = _tree_state(FIXTURES)
    monkeypatch.setenv(EVAL_ROOT_ENV, str(served_root))

    response = eval_query(requested)

    if expected_code is None:
        assert response.error is None
        assert response.findings
    else:
        assert response.findings == []
        assert response.error is not None
        assert response.error.code == expected_code
    assert _tree_state(tmp_path) == served_before
    assert _tree_state(FIXTURES) == fixtures_before


def test_eval_query_symlink_escape_refusal_writes_nothing_either(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _escaping_tree(tmp_path)
    before = _tree_state(tmp_path)
    monkeypatch.setenv(EVAL_ROOT_ENV, str(root))

    response = eval_query()

    assert response.findings == []
    assert response.error is not None
    assert response.error.code == SOURCE_UNPARSEABLE
    assert _tree_state(tmp_path) == before

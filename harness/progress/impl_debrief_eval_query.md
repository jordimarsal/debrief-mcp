# Implementation progress — debrief_eval_query

feature: debrief_eval_query

## Batch 1 (T1–T6): port, adapter, signature, tool, fixtures + tests

**Situation found:** the spec trio was approved at the human Spec Gate (2026-11-16).
No S4 code existed yet; `src/debrief/adapters/ggufbench_store.py` carried the
boundary guards inline. The adapter was smoke-tested against the real checkout at
`/Users/jmarsalp-local/works/fleet-eval` (10 model dirs) before fixtures existed.

### T1 — errors.py + ports.py
- `EVAL_SOURCE_MISSING = "eval_source_missing"` in `src/debrief/errors.py` (same
  frozen `DebriefError` shape as the parent codes).
- `EvalStore` protocol in `src/debrief/ports.py` (`findings() -> list[Finding] |
  DebriefError`), docstring names R12; module docstring no longer says "two" sources.

### T2 — adapters/fleet_eval_store.py (format knowledge stays here, ADR-0002)
- Enumerates `answers/*/` via `iterdir()` (never `is_dir()`: pathlib's predicates
  answer False for unreadable dirs, which would report a locked checkout as empty);
  `FileNotFoundError`/`NotADirectoryError` → `eval_source_missing`.
- Parses `grade.json` (A–D), `grade_E.json` + `grade_E_func.json` (E); one Finding
  per (model, task): `A_implement`, `B_fix`, `C_review`, `D_diagnose`, `E_largefile`;
  evidence = the answer file path relative to the root, containment-checked with
  `contained_file(root, …, "fleet-eval")` before any read.
- `results.json` and `final_table.json` are deliberately not read (design.md: a
  derived aggregate / published summary is not provenance).
- Every refusal is a returned `DebriefError`, never a raise: bad JSON, JSON array
  where the object belongs, model name mismatch with its directory, non-token or
  multi-line model names (newline forgery), missing answer file, missing probe file
  when `grade_E.json` exists.

### T3 — outcome policy + delivery failure (R14, exactly as design.md)
- A/B: pass iff `failed == 0` and `syntax_ok` and `applied`; measure = passed/total.
- C: pass iff `recall >= 0.85` and `false_positives_est == 0`; measure = recall,
  refused outside [0, 1] and outside the finite float domain.
- D: pass iff `total == max`; measure = total/max.
- E: pass iff `line_ratio >= 0.90` and no `symbols_missing` and not `placeholder`
  and probes `fail == []`; measure = line_ratio.
- `blocks == 0` (A/B/E) → outcome `fail`, reason
  `delivery failure: no code block in the answer`, measure 0.0 — never "no bugs".
  Real case pinned by the smoke test: `qwen38`/`B_fix`.

### T4 — signature (R13)
- baseline = sha256 over `prompts/`, `grade.py`, `grade_E.py`, `check_E.py` and
  `task_[a-d]/` contents (path-relative, NUL-separated, `__pycache__` skipped),
  first 12 hex; no battery files → refusal.
- engine_build = engine family from the artifacts: `logs/*.cmd` → `llama.cpp`,
  `logs/*.strata.out` → `strata`, joined with `+`, else `unrecorded`. Root-level
  union: the model is the variable under test, so per-model engine flags stay out.
- graded_counts = the battery's dimensions (max over models, zero = "nothing ran"
  from a delivery failure; two different non-zero counts refuse as a battery
  mismatch). A model without task E yields no E row but keeps the shared signature.
- Real checkout signature: `A:10,B:10,C:7,D:7,E:5@8629fb951172@llama.cpp+strata`,
  48 findings, one delivery failure.

### T5 — use case + tool
- `QueryEval` in `src/debrief/use_cases.py` (logs refusals, returns them unchanged).
- `eval.query` tool + `DEBRIEF_EVAL_ROOT` (default `artifacts/fleet-eval`) in
  `src/debrief/mcp_server.py`, reusing `_resolve_within` (`path_outside_root`, NUL,
  traversal); read-only annotations like the other three tools; help + server
  instructions updated.

### Shared guards (extraction, behaviour unchanged)
- `adapters/_guards.py` now owns `contained_file(root, candidate, root_label)`,
  `Unparseable`, `required_str/token/line/int/bool/measure/counts/str_list`,
  `is_regular_file`, `MISSING_PATH_ERRORS`; `ggufbench_store.py` refactored onto
  them (the bench tests pin `outside the artifact root` via `root_label`).

### T6 — fixtures + tests
- `tests/fixtures/fleet_eval/` (battery "dispatch", llama.cpp logs; alpha mostly
  passing, beta failing C and E, gamma B delivery failure and no task-E grade —
  mirroring the real qwen38 / qwen38-think variants),
  `fleet_eval_strata/` (strata-only log, own battery), `fleet_eval_broken/`
  (truncated JSON, JSON array).
- `tests/test_eval.py` — 41 tests: answers from the real fixture root; row carries
  measure/signature/evidence; per-task measures; outcome policy; delivery failure
  (A/B and E) with zero measure; missing-E model shares the cohort signature;
  strata family from the logs; two cohorts and a truncated battery both refuse as
  `incomparable_rows`; battery-count mismatch refuses; structured refusals
  (missing root, no answers dir, answers without grades, bad JSON, non-object);
  missing answer file; model/directory mismatch and newline-forging model names;
  non-finite recall and line_ratio; E grade without probes; hostile bytes
  (nesting bombs, undecodable); symlink escape refuses with no leak, contained
  symlink stays readable; unreadable root refuses; tool answers inside the root,
  refuses traversal/NUL and a symlink escaping below the requested path;
  byte-identical tree after a query (five scenarios + escape refusal).
- Suite 155 → 196; battery green: `harness/logs/debrief_eval_query/batch-1.log`.

Batching note: T1–T5 have no observable behaviour until fixtures exist, so the
first executable gate ran after T6; `tasks.md` records T1–T6 as one batch citing
that single log.

## Batch 2 (T7–T9): docs, traceability, gate battery

### T7 — docs
Already delivered with the spec commit (`a130043`): `docs/architecture.md` slice
map gains S4 and the ports table gains `EvalStore`; parent
`harness/specs/debrief/requirements.md` gains R12–R14, the R9 rewording and the
slice-ownership row; `AGENTS.md` slice order gains S4. No log needed (tasks.md).

### T8 — traceability
The tool-readable table lives below (`feature: debrief_eval_query` above); the
human-readable copy is in `harness/specs/debrief_eval_query/requirements.md`.
Verdict saved to `harness/specs/debrief_eval_query/review.md`.

### T9 — demo + full battery
Demo against the real checkout recorded in `harness/logs/debrief_eval_query/demo.log`;
full gate battery transcript in `harness/logs/debrief_eval_query/batch-2.log`.

## Traceability table (tool-readable)

| Requirement | Test(s) | Implementation file(s) | Status |
|-------------|---------|------------------------|--------|
| R1 | test_query_eval_refuses_with_structured_error, test_eval_query_tool_answers_within_the_allowed_root, test_eval_query_tool_refuses_paths_outside_the_root | src/debrief/errors.py, src/debrief/use_cases.py, src/debrief/mcp_server.py | done |
| R2 | test_no_debrief_module_contains_a_write_path, test_eval_query_leaves_the_results_tree_byte_identical, test_eval_query_symlink_escape_refusal_writes_nothing_either | src/debrief/mcp_server.py, src/debrief/adapters/fleet_eval_store.py | done |
| R12 | test_query_eval_answers_from_real_results_root, test_eval_row_carries_measure_signature_and_evidence_from_the_results, test_symlinked_graded_result_outside_the_root_refuses_the_scan, test_symlinked_graded_result_inside_the_root_is_still_read, test_missing_answer_file_refuses_instead_of_inventing_evidence, test_query_eval_refuses_with_structured_error | src/debrief/ports.py, src/debrief/adapters/fleet_eval_store.py | done |
| R13 | test_eval_row_carries_measure_signature_and_evidence_from_the_results, test_a_model_without_a_task_e_grade_yields_no_row_but_shares_the_cohort_signature, test_strata_cohort_derives_its_engine_family_from_the_logs, test_shared_signature_refuses_two_cohorts_across_engines, test_truncated_battery_is_a_second_signature, test_two_batteries_under_one_root_refuse_rather_than_average | src/debrief/domain.py, src/debrief/adapters/fleet_eval_store.py, src/debrief/use_cases.py | done |
| R14 | test_delivery_failure_is_a_fail_with_zero_measure, test_delivery_failure_also_covers_task_e | src/debrief/adapters/fleet_eval_store.py | done |

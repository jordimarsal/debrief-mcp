# Requirements: debrief_eval_query

Slice S4 of parent `debrief`: the `eval.query` MCP tool answers "what did fleet-eval
measure?" from real fleet-eval results. Requirement IDs R12–R14 are parent requirements
this slice owns; R1 and R2 are the parent's cross-cutting contracts.

## R1
When the agent invokes the `eval.query` tool, the system shall return either findings or
a structured error carrying a stable code.

## R2
While serving an `eval.query` call, the system shall not write to the filesystem.

## R12
When `eval.query` returns findings, the system shall have derived every finding solely
from fleet-eval result files read through the EvalStore port, resolved inside
`DEBRIEF_EVAL_ROOT`.

## R13
When `eval.query` returns findings, every finding shall carry a task signature composed
of the battery digest (task prompts, graders and task fixtures) and the engine family
derived from the run artifacts; when rows carry more than one signature the system shall
refuse the comparison as incomparable instead of averaging or ranking them.

## R14
When a model answer is a delivery failure (empty content, or prose instead of the
required file), the system shall report the finding with outcome `fail` and a reason
that names the delivery failure, and shall never reinterpret it as a capability result.

## Traceability

| Requirement | Test(s) | Implementation file(s) | Status |
|-------------|---------|------------------------|--------|
| R1 | test_query_eval_refuses_with_structured_error, test_eval_query_tool_answers_within_the_allowed_root, test_eval_query_tool_refuses_paths_outside_the_root | src/debrief/errors.py, src/debrief/use_cases.py, src/debrief/mcp_server.py | done |
| R2 | test_no_debrief_module_contains_a_write_path, test_eval_query_leaves_the_results_tree_byte_identical, test_eval_query_symlink_escape_refusal_writes_nothing_either | src/debrief/mcp_server.py, src/debrief/adapters/fleet_eval_store.py | done |
| R12 | test_query_eval_answers_from_real_results_root, test_eval_row_carries_measure_signature_and_evidence_from_the_results, test_symlinked_graded_result_outside_the_root_refuses_the_scan, test_symlinked_graded_result_inside_the_root_is_still_read, test_missing_answer_file_refuses_instead_of_inventing_evidence, test_query_eval_refuses_with_structured_error | src/debrief/ports.py, src/debrief/adapters/fleet_eval_store.py | done |
| R13 | test_eval_row_carries_measure_signature_and_evidence_from_the_results, test_a_model_without_a_task_e_grade_yields_no_row_but_shares_the_cohort_signature, test_strata_cohort_derives_its_engine_family_from_the_logs, test_shared_signature_refuses_two_cohorts_across_engines, test_truncated_battery_is_a_second_signature, test_two_batteries_under_one_root_refuse_rather_than_average | src/debrief/domain.py, src/debrief/adapters/fleet_eval_store.py, src/debrief/use_cases.py | done |
| R14 | test_delivery_failure_is_a_fail_with_zero_measure, test_delivery_failure_also_covers_task_e | src/debrief/adapters/fleet_eval_store.py | done |

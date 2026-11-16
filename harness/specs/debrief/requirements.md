# Requirements: debrief (parent)

Parent feature for 4 vertical slices (S1 bench_query, S2 run_inspect, S3 role_propose,
S4 eval_query). Each slice refines its subset in its lite trio.

## R1
Tool calls return findings or a structured error.

## R2
No file writes while serving.

## R3
Bench findings come only from ggufbench artifacts.

## R4
Run findings come only from a buildwright run log.

## R5
Role proposal is a BW_ROLE_* diff as text from both ports' findings.

## R6
Proposals target BW_ROLE_* roles, never models.yaml.

## R7
Incomparable rows -> structured error, never averaged.

## R8
Before each slice Completion Gate: init.sh, pytest, ruff, mypy --strict, audit-security, gauntlet green.

## R9
Parent done only after S4 Completion Gate with recorded demo.

## R10
Installs with uv sync / uv tool install; smoke call works.

## R11
Each slice approval record has a demo note (command + output).

## R12
Eval findings come only from fleet-eval results, resolved inside `DEBRIEF_EVAL_ROOT`.

## R13
Every eval finding carries a task signature (battery digest + engine family); rows across
signatures are refused, never averaged.

## R14
A delivery failure (no code block where a file was required) is reported as `fail` with a
reason naming it, never reinterpreted as a capability result.

## Slice ownership

- S1 debrief_bench_query — R1, R2, R3
- S2 debrief_run_inspect — R1, R2, R4
- S3 debrief_role_propose — R1, R2, R5, R6, R7
- S4 debrief_eval_query — R1, R2, R12, R13, R14
- Parent — R8, R9, R10, R11

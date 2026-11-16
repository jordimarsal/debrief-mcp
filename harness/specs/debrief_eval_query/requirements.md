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
| R1 | pending | src/debrief/errors.py, src/debrief/use_cases.py, src/debrief/mcp_server.py | pending |
| R2 | pending | src/debrief/mcp_server.py, src/debrief/adapters/fleet_eval_store.py | pending |
| R12 | pending | src/debrief/ports.py, src/debrief/adapters/fleet_eval_store.py | pending |
| R13 | pending | src/debrief/domain.py, src/debrief/adapters/fleet_eval_store.py, src/debrief/use_cases.py | pending |
| R14 | pending | src/debrief/adapters/fleet_eval_store.py | pending |

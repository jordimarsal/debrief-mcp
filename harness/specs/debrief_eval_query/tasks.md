# Tasks: debrief_eval_query

Batches end with `harness/init.sh` green and its log saved to
`harness/logs/debrief_eval_query/batch-<n>.log`. A task is `[x]` only with that log in
place.

## Batch 1 — port, adapter, signature, tool and tests

T1–T6 ran as one batch: T1–T5 add no observable behaviour until a fixture exists, so the
first executable gate after T6 is the earliest honest evidence for all six. Log:
`batch-1.log`.

- [x] T1: Add `EVAL_SOURCE_MISSING` to `src/debrief/errors.py` and the `EvalStore`
      protocol to `src/debrief/ports.py`. Log: `batch-1.log`.
- [x] T2: Implement `adapters/fleet_eval_store.py`: enumerate `answers/*/`, parse
      `grade.json`, `grade_E.json`, `grade_E_func.json`, build one `Finding` per
      (model, task) with evidence path; validate identifier and free-text fields at the
      boundary. Log: `batch-1.log`.
- [x] T3: Implement the outcome policy and the delivery-failure rule (R14) exactly as
      written in `design.md`; `measure` carries the task's own metric. Log: `batch-1.log`.
- [x] T4: Implement the battery digest (sha256 over `prompts/`, graders and
      `task_[a-d]/`) and the derived engine family; attach a `TaskSignature` to every
      finding (R13). Log: `batch-1.log`.
- [x] T5: Add `QueryEval` to `use_cases.py`, `DEBRIEF_EVAL_ROOT` and the `eval.query`
      tool to `mcp_server.py`, reusing the containment rules (`path_outside_root`, NUL,
      symlink escape). Log: `batch-1.log`.
- [x] T6: Fixtures + `tests/test_eval.py`: normal run, Strata model, delivery-failure
      row, truncated battery, second signature → incomparable refusal, symlink escape,
      unparseable JSON, non-finite measure, byte-identical tree after a query.
      Log: `batch-1.log`.

## Batch 2 — docs, tests manifest, gate battery

- [x] T7: Update `docs/architecture.md` (slice map S4, ports table) and the parent
      `harness/specs/debrief/requirements.md` (R12–R14, R9 wording, ownership). No log
      needed; reviewed at the gate.
- [x] T8: Fill the traceability table in `requirements.md` with real test names and
      files; run `python3 harness/tools/check-traceability.py --feature debrief_eval_query`
      and save the verdict to `harness/specs/debrief_eval_query/review.md`.
- [x] T9: Record the demo (command + output) for the Completion Gate, run the full
      battery (`init.sh`, pytest, ruff, mypy --strict, audit-security, gauntlet) and save
      `harness/logs/debrief_eval_query/batch-2.log`.

# Historical log (append-only)

> Each time a session closes, its summary is appended here.
> Do not edit previous entries. Only append.

Entry shape — the `retro:` line is the per-feature efficiency record
(inspect it to see where process friction accumulates):

    ## <date> — <feature>

    <3-5 line summary>

    retro: <n> dispatches · <s> stalls · <r> restarts

### debrief — debrief — answer agent questions from receipts (bench · run · propose) (2026-11-03)

- approved by jordi · reviewer: APPROVED · batches: 8
retro: 40 dispatches · 32 stalls · 16 restarts

### debrief_run_inspect — debrief S2 run_inspect — agent asks where a run broke -> structured findings (2026-11-03)

- approved by jordi · reviewer: APPROVED · batches: 2
retro: 2 dispatches · 0 stalls · 0 restarts

### debrief_role_propose — debrief S3 role_propose — agent gets a BW_ROLE_* proposal citing both ports, text only (2026-11-03)

- approved by jordi · reviewer: APPROVED · batches: 2
retro: 2 dispatches · 0 stalls · 0 restarts

### debrief_bench_query — debrief S1 bench_query — agent asks what ggufbench measured -> findings from real artifacts (2026-11-04)

- approved by jordi · reviewer: APPROVED · batches: 6
retro: 6 dispatches · 0 stalls · 0 restarts

### debrief_eval_query — debrief S4 eval_query — agent asks what fleet-eval measured, findings only (2026-11-16)

- approved by jordi · reviewer: APPROVED (completion gate, in-session) · batches: 2
retro: 2 dispatches · 0 stalls · 0 restarts

- S4 delivered in two batches: spec trio + parent amendments (a130043); port
  `EvalStore` + adapter + `eval.query` + fixtures/tests (b65762f, suite 155 -> 196);
  traceability/demo/battery (eb2f0a2). No shim: fleet-eval keeps its own schema and
  its own task signature (battery digest + engine family from the logs); delivery
  failures (`blocks == 0`, real case qwen38/B) are first-class fails. Battery green:
  196 passed, ruff/format/mypy --strict, audit-security no HIGH, gauntlet G1 PASS,
  traceability 5/5 (`harness/logs/debrief_eval_query/batch-2.log`). Batch-1 note:
  T1–T5 have no observable behaviour until fixtures exist, so tasks.md records
  T1–T6 as one batch citing the single first-green log (`batch-1.log`).

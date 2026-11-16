# Design: debrief_eval_query

## Context

Slice S4 of `debrief` (part_of: parent feature 1). It adds a third evidence port —
fleet-eval results — next to `bench` (ggufbench) and `run` (buildwright log), without
touching either. fleet-eval answers a different question than ggufbench: not "how good
or how fast is this model in isolation" but "does it deliver the file it was asked for,
in the format asked for, in a dispatch role". Sharing the bench port would make
`bench.query` lie about provenance, which ADR-0002 exists to prevent, and would mix two
schemas under one root, turning every combined query into `incomparable_rows`.

ADR-0001 (never writes), ADR-0002 (one `Finding` currency; format knowledge stays in the
adapter), ADR-0004 (task signatures, not version labels) all apply unchanged.

## Approach

- **Source contract** (known only in `adapters/fleet_eval_store.py`). Root =
  `DEBRIEF_EVAL_ROOT`, default `artifacts/fleet-eval`; layout is a fleet-eval checkout:

  ```
  <root>/results.json                 aggregate A–D, 7 base models (informational)
  <root>/answers/<model>/grade.json   A–D graded per model (all 10 model dirs)
  <root>/answers/<model>/grade_E.json E delivery metrics
  <root>/answers/<model>/grade_E_func.json E behavioural probes (ok[], fail[])
  <root>/answers/<model>/<T>_*.md     the delivered answer (evidence pointer)
  <root>/logs/<model>.cmd             llama.cpp server command (engine family)
  <root>/logs/<model>.strata.out      Strata engine log (engine family)
  <root>/prompts/*.md, grade*.py, check_E.py, task_[a-d]/   the battery
  ```

  Per-model `answers/<model>/grade*.json` is the source of truth; `results.json` is a
  derived aggregate and is not read. `final_table.json` is a published summary and is not
  read either — a number without provenance is worse than a gap (spec §4 of the ADR set).

- **One finding per (model, task)**: model = directory name, task = `A_implement`,
  `B_fix`, `C_review`, `D_diagnose`, `E_largefile`, evidence = path of the answer file
  relative to the root (validated: no NUL, no control characters, single line).

- **Outcome policy** (documented here, approved at the Spec Gate, never hidden in code):

  | Task | measure | pass when |
  |---|---|---|
  | A, B | `passed / (passed + failed)` | `failed == 0` and `passed > 0` and `syntax_ok` and `applied` |
  | C | `recall` | `recall >= 0.85` and `false_positives_est == 0` |
  | D | `total / max` | `total == max` |
  | E | `line_ratio` | `line_ratio >= 0.90` and `symbols_missing == []` and no placeholder and `fail == []` in the probes |

- **Delivery failure is a first-class outcome** (R14). `blocks == 0` in A/B/E means the
  model returned prose where a file was required; qwen38's B is the real case (0 blocks,
  `passed == 0`, `failed == 0`). The finding is `fail` with reason
  `delivery failure: no code block in the answer` and `measure = 0.0`; it is never
  counted as "no bugs to fix" and never enters a pass ratio.

- **Signature** (R13): `baseline` = battery digest, a sha256 over the contents of
  `prompts/`, `grade.py`, `grade_E.py`, `check_E.py` and `task_[a-d]/` (first 12 hex);
  `engine_build` = engine family derived from the artifacts (`llama.cpp` when
  `logs/<model>.cmd` exists, `strata` when `logs/<model>.strata.out` exists, else
  `unrecorded`); `graded_counts` derived per task from the graded data itself
  (`A`/`B` = passed + failed, `C` = found + missing, `D` = max, `E` = probe count).
  Two runs of different batteries or different engines therefore land in different
  signatures, and `shared_signature` refuses to rank across them. The engine *file* and
  flags are deliberately out of the signature: the model is the variable under test, so
  including them would make every row incomparable.

- **Refusals are returned, never raised** (R1): `eval_source_missing` (no
  `answers/` or no graded file), `source_unparseable` (bad JSON, missing keys, wrong
  types, non-finite measures, nesting bombs), `path_outside_root` (escape, symlink
  escape, NUL) — same shape and code set as bench, plus `EVAL_SOURCE_MISSING`.

- **Boundary validation**: reuses `mcp_server._resolve_within` semantics for
  `DEBRIEF_EVAL_ROOT`; the adapter re-checks containment for every file it opens, so a
  symlinked `grade.json` cannot read outside the root. Identifier-like fields (model,
  task, engine_build, baseline, graded dimensions) must be single-line whitespace-free
  tokens; free-text fields (reason, evidence) single-line and control-character-free,
  because they reach `routing.propose` text verbatim.

## Files to create or modify

| Path | Change |
|---|---|
| `src/debrief/errors.py` | add `EVAL_SOURCE_MISSING` code |
| `src/debrief/ports.py` | add `EvalStore` protocol |
| `src/debrief/use_cases.py` | add `QueryEval` |
| `src/debrief/adapters/fleet_eval_store.py` | new read-only adapter |
| `src/debrief/mcp_server.py` | `eval_query` tool, `DEBRIEF_EVAL_ROOT`, wiring |
| `docs/architecture.md` | slice map row S4, ports table row `EvalStore` |
| `harness/specs/debrief/requirements.md` | R12–R14 + slice ownership + R9 wording |
| `harness/feature_list.json` | feature 5 `debrief_eval_query` |
| `tests/test_eval.py`, `tests/fixtures/fleet_eval*` | real-fixture tests |

## Public signatures

```python
class EvalStore(Protocol):
    def findings(self) -> list[Finding] | DebriefError: ...


class QueryEval:
    def __init__(self, store: EvalStore) -> None: ...
    def run(self) -> list[Finding] | DebriefError: ...
```

The MCP tool is `eval.query` with one optional argument `path` (default `.`), resolved
inside `DEBRIEF_EVAL_ROOT`.

## Test strategy

Real fixture checkouts, no mocks: a normal run (llama.cpp), a Strata-only model, a
delivery-failure row (0 blocks), a truncated battery (missing `task_d/`) so the digest
differs, a second signature so `shared_signature` refuses, a symlink escaping the root,
unparseable JSON, a non-finite measure, and a mixed-battery root. Write-path test stays
global (`test_no_debrief_module_contains_a_write_path`), plus a byte-identical tree check
after a query.

## Out of scope

- Exporting or mutating fleet-eval results (debrief never writes; fleet-eval owns its
  format).
- Feeding eval rows into `routing.propose` (S3 composes bench + run; extending it to a
  third source is a separate slice, and it must keep refusing cross-signature mixes).
- Ranking models across engines or batteries.

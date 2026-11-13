# debrief-mcp

[![M8ven Score](https://m8ven.ai/badge/mcp/jordimarsal-debrief-mcp-1qz300?v=208d2c524782430e0be7a2d132beb2b3)](https://m8ven.ai/mcp/jordimarsal-debrief-mcp-1qz300?s=readme)
[![M8ven Score](https://m8ven.ai/badge/mcp/jordimarsal/debrief-mcp)](https://m8ven.ai/mcp/jordimarsal/debrief-mcp?s=readme)

The evidence MCP: answers agent questions from receipts — what
[ggufbench](https://github.com/jordimarsal/ggufbench) measured, and where the
last [buildwright](https://github.com/jordimarsal/buildwright) run broke — and
proposes role changes **as text**. It never writes.

> Status: **implemented and gated.** The spec (`harness/specs/debrief/`) was
> approved at the Completion Gate (2026-11-03; 11/11 requirements traced) and
> the three slices — S1 `bench.query`, S2 `run.inspect`, S3 `routing.propose` —
> are `done`. The tool table below is the shipped surface.

## The idea

- `ggufbench` owns the **catalog**: what a model measured, under which task
  signature, and why rows were excluded.
- `buildwright` owns the **episode**: one run, its gates, its failures.
- `debrief` is the reader. One query surface, one shared finding type, and a
  proposal that cites both. Two ports that answer different questions:

| Port | Question | Reads | Tools |
| --- | --- | --- | --- |
| `bench` | What did we measure? | ggufbench artifacts | `bench.query` |
| `run` | Where did this run break? | a buildwright run log | `run.inspect` |
| `routing` | What would you change? | findings from both | `routing.propose` — returns a `BW_ROLE_*` diff as text |

## Product rules (the gates that matter in code)

1. **debrief never writes.** Every tool is read-only or returns a proposal as
   text. No tool touches `.env`, `BW_ROLE_*`, `models.yaml`, or any other file.
2. **Proposals target roles, not the registry.** A proposed change is a
   `BW_ROLE_<ROLE>` diff. `models.yaml` is the registry of what exists — not
   debrief's to edit.
3. **bench and run answer from their own source.** `run` may cite `bench`
   findings; `bench` never reads runs.
4. **Rows never cross a task signature.** Incomparable rows are refused with a
   reason — never averaged.

## The gates (process)

The repo runs the [harness](https://github.com/jordimarsal/harness) SDD
workflow in **hybrid** mode: one in-session agent plays the roles, the human
gates stay mandatory. Architecture is **hexagonal** (`docs/architecture.md`);
features are cut into **vertical slices** (`docs/slicing-protocol.md`) —
S1 `bench_query` → S2 `run_inspect` → S3 `role_propose`, each demoable
end-to-end.

| Gate | What it checks | Command / artefact |
| --- | --- | --- |
| **Spec Gate** (human) | EARS trio in `harness/specs/<name>/`, slice map approved before any slice starts | review + explicit approval |
| **Batch gates** (every 2–4 tasks) | tests + lint + types, evidence saved | `uv run pytest tests`, `ruff check`, `mypy --strict` — full output to `harness/logs/<feature>/batch-<n>.log` |
| **Security audit** (`audit_level: standard`) | path traversal, input validation, secrets — run at review time | `bash harness/tools/audit-security.sh` |
| **Gauntlet G1–G4** (before Completion) | correctness, adversarial input, maintainability, evidence | `bash harness/tools/gauntlet.sh --feature <name>` + report in `harness/progress/gauntlet_<name>.md` |
| **Completion Gate** (human) | traceability `R<n>` ↔ test, plus a **recorded end-to-end demo** per slice | `python3 harness/tools/check-traceability.py --feature <name>` → `harness/specs/<name>/review.md` |
| **Session verify** | harness files, docs, tests, state coherence | `harness/init.sh` |

Two gates are non-negotiable and human: the **Spec Gate** and the **Completion
Gate**. The gauntlet filters what reaches them; it never replaces them.

## Development

```bash
uv sync
uv run pytest tests
```

Requires Python ≥ 3.14 ([uv](https://docs.astral.sh/uv/)).

## Another machine

The evidence tree (`artifacts/`) ships with this clone — `bench.query`,
`run.inspect` and `routing.propose` work from receipts without re-running
anything. To make a machine a *publisher* (its buildwright runs and ggufbench
runs land here), wire it once:

```bash
scripts/setup-machine.sh [path-to-this-checkout]
```

It appends `DEBRIEF_HOME` + the two writer env vars to your shell rc and prints
the MCP registration block for `opencode.json`. Unset vars degrade gracefully:
writers stay in-repo (self-contained mode), nothing breaks.

## Repository map

See [`AGENTS.md`](AGENTS.md) — it is the navigation map for agents (and humans).
Architecture: [`docs/architecture.md`](docs/architecture.md). Decisions worth
remembering: [`harness/decisions/`](harness/decisions/).

[![built with harness](https://raw.githubusercontent.com/jordimarsal/harness/main/assets/badge.svg)](https://github.com/jordimarsal/harness)

#!/usr/bin/env bash
# setup-machine.sh — wire one machine to the central debrief evidence tree.
#
# The mechanism is fully in the repos (buildwright's BW_DEBRIEF_ROOT, ggufbench's
# GGUFBENCH_DEBRIEF_DIR, this checkout's artifacts/); what a new machine needs is
# that every writer AND the MCP registration point at the same checkout. This
# script wires the shell side and prints the MCP registration with your absolute
# paths (JSON cannot expand $DEBRIEF_HOME, so that part is copy-paste).
#
# Usage:
#   scripts/setup-machine.sh [DEBRIEF_HOME]     # default: ~/works/debrief-mcp
#
# What it does:
#   1. verifies DEBRIEF_HOME is this checkout (src/debrief must exist)
#   2. appends the exports to ~/.zshrc / ~/.bashrc (idempotent — no duplicates)
#   3. prints the opencode.json "debrief" server block for this machine
#
# Anything NOT covered here is standard per-machine setup: cloning the repos
# (debrief-mcp, ggufbench, buildwright), uv sync per repo, and a model key
# (ZAI_API_KEY or local llama-server) — the writers degrade to the self-contained
# in-repo mode when the env vars are unset, so nothing breaks without them.

set -euo pipefail

DEBRIEF_HOME="${1:-$HOME/works/debrief-mcp}"
DEBRIEF_HOME="${DEBRIEF_HOME/#\~/$HOME}"

if [[ ! -d "$DEBRIEF_HOME/src/debrief" ]]; then
  echo "✗ $DEBRIEF_HOME does not look like the debrief checkout (no src/debrief)" >&2
  echo "  clone it first: git clone <debrief-mcp-url> $DEBRIEF_HOME" >&2
  exit 1
fi
echo "✓ debrief checkout: $DEBRIEF_HOME"

# 2. shell exports — idempotent: skip when the marker is already present
MARKER="# debrief evidence tree"
if grep -q '^export DEBRIEF_HOME=' ~/.zshrc ~/.bashrc 2>/dev/null; then
  echo "✓ exports already present in your rc file(s) — nothing written"
else
  RC="$HOME/.zshrc"; [[ -f "$RC" ]] || RC="$HOME/.bashrc"
  cat >> "$RC" <<EOF

$MARKER: writers publish to the central git-tracked checkout.
# Single source of truth for the path: point DEBRIEF_HOME at your checkout.
export DEBRIEF_HOME="$DEBRIEF_HOME"
export GGUFBENCH_DEBRIEF_DIR="$DEBRIEF_HOME/artifacts/ggufbench"
export BW_DEBRIEF_ROOT="$DEBRIEF_HOME/artifacts"
EOF
  echo "✓ exports appended to $RC (open a new shell or: source $RC)"
fi

# 3. MCP registration for THIS machine (paths are absolute by necessity)
cat <<EOF

Paste into ~/.config/opencode/opencode.json → mcp.servers (then restart the session):

  "debrief": {
    "type": "local",
    "command": ["uv", "--directory", "$DEBRIEF_HOME", "run", "debrief-mcp"],
    "environment": {
      "DEBRIEF_BENCH_ROOT": "$DEBRIEF_HOME/artifacts/ggufbench",
      "DEBRIEF_RUN_ROOT": "$DEBRIEF_HOME/artifacts"
    }
  }
EOF

for repo in ggufbench buildwright; do
  if [[ -d "$DEBRIEF_HOME/../$repo" || -d "$HOME/works/$repo" ]]; then
    echo "✓ sibling repo found: $repo"
  else
    echo "⚠ sibling repo not found: $repo (clone it — its writers publish here)"
  fi
done

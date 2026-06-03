#!/usr/bin/env bash
# One-button runner (brief §5/§8): set up the environment, run the full
# backend×condition×seed matrix, and leave a complete report package behind.
#
#   ./run_all.sh            # full run (uses configs/pipeline.yaml + .env)
#   ./run_all.sh --smoke    # fast, offline, free proof of the whole pipeline
#   ./run_all.sh --run-id myrun   # resume/label a specific run (idempotent)
#
# Every flag is passed straight through to `python -m emergent_divergence pipeline`,
# which is itself resumable: Ctrl-C and re-run with the same --run-id to continue
# without losing work or double-counting spend.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="${VENV:-.venv}"
PY="$VENV/bin/python"

# 1. Load .env (ANTHROPIC_API_KEY and any optional matrix overrides).
if [[ -f .env ]]; then
  set -a; . ./.env; set +a
fi

# 2. Ensure a virtualenv exists.
if [[ ! -x "$PY" ]]; then
  echo "[run_all] creating virtualenv at $VENV"
  if command -v uv >/dev/null 2>&1; then
    uv venv "$VENV"
  else
    python3 -m venv "$VENV"
  fi
fi

# 3. Ensure runtime dependencies are importable; install on first run only.
if ! "$PY" - <<'PYEOF' >/dev/null 2>&1
import numpy, scipy, yaml  # noqa: F401
PYEOF
then
  echo "[run_all] installing dependencies (first run)"
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$PY" -e ".[dev]"
  else
    "$PY" -m pip install --upgrade pip >/dev/null
    "$PY" -m pip install -e ".[dev]"
  fi
fi

# 4. Run the pipeline. src/ layout is importable without a build step.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
echo "[run_all] launching pipeline ${*:-(full run)}"
exec "$PY" -m emergent_divergence pipeline "$@"

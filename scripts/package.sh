#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[nano-ant] Cleaning old build artifacts"
rm -rf build dist ./*.egg-info

echo "[nano-ant] Running unit tests"
PYTHONPYCACHEPREFIX=/tmp/nano_ant_pycache python3 -m unittest discover -s tests -v

if python3 -c "import build" >/dev/null 2>&1; then
  echo "[nano-ant] Building wheel and sdist via python -m build"
  python3 -m build
elif python3 -c "import wheel" >/dev/null 2>&1; then
  echo "[nano-ant] 'build' not available, falling back to setup.py"
  python3 setup.py sdist bdist_wheel
else
  echo "[nano-ant] Neither 'build' nor 'wheel' is available. Install one of them and rerun."
  exit 1
fi

echo "[nano-ant] Build complete"
ls -lh dist

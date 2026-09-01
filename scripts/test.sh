#!/bin/bash
# 冒烟测试：引擎 unittest + CLI + 密钥检查
# 用法: scripts/test.sh [应用名]
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/resolve_app.sh
. "$ROOT/scripts/lib/resolve_app.sh"
APP="$(resolve_app_name "${1:-zr-workbuddy}")"
ENG="$ROOT/apps/$APP/engine"
export MPLBACKEND="${MPLBACKEND:-Agg}"

echo "== secrets check =="
"$ROOT/scripts/check-secrets.sh"

echo "== vendor vs host (dsh-tools realpath) =="
"$ROOT/scripts/check-vendor.sh"

if [ -d "$ENG/tests" ]; then
  echo "== unittest ($APP) =="
  cd "$ENG"
  PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' -q
fi

if [ -f "$ENG/engine_cli.py" ]; then
  echo "== engine_cli status =="
  cd "$ENG"
  python3 engine_cli.py status | head -c 400
  echo
fi

echo "✅ test.sh 完成 ($APP)"

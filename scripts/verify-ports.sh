#!/bin/bash
# 验证 WorkBuddy :3081（~/.dsh + mes-bridge + 工作区）
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/workbuddy_web_env.sh
. "$ROOT/scripts/lib/workbuddy_web_env.sh"
apply_workbuddy_dsh_home
exec python3 "$ROOT/scripts/lib/verify_workbuddy_web.py"

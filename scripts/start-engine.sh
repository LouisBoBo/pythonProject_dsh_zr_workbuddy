#!/bin/bash
# 兼容入口 → scripts/engine.sh
# 用法: scripts/start-engine.sh <应用名> [端口]
# 后台: scripts/start-engine.sh <应用名> -d
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/resolve_app.sh
. "$ROOT/scripts/lib/resolve_app.sh"
APP="${1:?用法: start-engine.sh <应用名> [端口|-d]}"
APP="$(resolve_app_name "$APP")"
shift || true
DETACH_ARGS=()
PORT_ARGS=()
for a in "$@"; do
  case "$a" in
    -d|--detach) DETACH_ARGS+=(-d) ;;
    *) PORT_ARGS+=("$a") ;;
  esac
done
if [ ${#DETACH_ARGS[@]} -gt 0 ]; then
  exec "$ROOT/scripts/engine.sh" "$APP" start -d "${PORT_ARGS[@]}"
fi
# 无 -d：若已有监听则 status；否则前台 start（保持旧行为）
if "$ROOT/scripts/engine.sh" "$APP" status >/dev/null 2>&1; then
  exec "$ROOT/scripts/engine.sh" "$APP" status
fi
exec "$ROOT/scripts/engine.sh" "$APP" start "${PORT_ARGS[@]}"

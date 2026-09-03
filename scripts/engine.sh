#!/bin/bash
# 框架：应用引擎进程生命周期（业务端口读 runtime.yaml）
# 用法:
#   scripts/engine.sh <应用名> status
#   scripts/engine.sh <应用名> ensure    # 未监听则后台启动
#   scripts/engine.sh <应用名> start     # 前台（或已在跑则退出）
#   scripts/engine.sh <应用名> start -d  # 后台
#   scripts/engine.sh <应用名> stop
#   scripts/engine.sh <应用名> restart
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/resolve_app.sh
. "$ROOT/scripts/lib/resolve_app.sh"
APP="${1:?用法: engine.sh <应用名> status|ensure|start|stop|restart}"
APP="$(resolve_app_name "$APP")"
CMD="${2:?}"
shift 2 || true

ENGINE="$ROOT/apps/$APP/engine"
RUNTIME="$ENGINE/config/runtime.yaml"
PID_FILE="$ENGINE/data/engine.pid"
LOG_FILE="$ENGINE/data/engine.log"
READ_RUNTIME="$ROOT/scripts/lib/read_runtime.py"
[ -d "$ENGINE" ] || { echo "找不到引擎: $ENGINE"; exit 1; }

load_runtime_json() {
  python3 "$READ_RUNTIME" "$ENGINE"
}

_RT_JSON="$(load_runtime_json)"
HOST="$(printf '%s' "$_RT_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["host"])')"
PORT="$(printf '%s' "$_RT_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["port"])')"
PYTHON="$(printf '%s' "$_RT_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["python"])')"
# 允许: engine.sh app start 9000 / engine.sh app start -d
DETACH=0
for a in "$@"; do
  case "$a" in
    -d|--detach) DETACH=1 ;;
    [0-9]*) PORT="$a" ;;
  esac
done

listening_pid() {
  lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true
}

sync_bridge_client() {
  local CLIENT="$ROOT/apps/$APP/plugins/mes-bridge/lib/client.js"
  [ -f "$CLIENT" ] || CLIENT="$ROOT/apps/$APP/plugins/${APP}-bridge/lib/client.js"
  [ -f "$CLIENT" ] || return 0
  python3 - "$CLIENT" "$HOST" "$PORT" <<'PY'
import re, sys
path, host, port = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()
block = (
    "/*RUNTIME_BEGIN*/\n"
    f'window.__APP_ENGINE__ = {{ host: "{host}", port: {port} }};\n'
    "/*RUNTIME_END*/"
)
text2, n = re.subn(r"/\*RUNTIME_BEGIN\*/.*?/\*RUNTIME_END\*/", block, text, count=1, flags=re.S)
if n:
    open(path, "w", encoding="utf-8").write(text2)
    print(f"已同步 bridge 面板地址 → {host}:{port}")
PY
}

health_ok() {
  curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 1 \
    "http://$HOST:$PORT/api/runtime" 2>/dev/null | grep -q '^200$'
}

do_status() {
  local pid
  pid="$(listening_pid)"
  if [ -n "$pid" ] && health_ok; then
    echo "引擎运行中 PID=$pid → http://$HOST:$PORT （/api/runtime OK）"
    return 0
  fi
  if [ -n "$pid" ]; then
    echo "端口 $PORT 有进程 PID=$pid，但 /api/runtime 未就绪"
    return 1
  fi
  echo "引擎未运行（$HOST:$PORT）"
  return 1
}

do_stop() {
  local pid left
  pid="$(listening_pid)"
  if [ -z "$pid" ]; then
    echo "引擎未在监听 :$PORT"
    rm -f "$PID_FILE"
    return 0
  fi
  echo "停止引擎 PID=$pid (:$PORT)…"
  kill $pid 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    sleep 0.4
    [ -z "$(listening_pid)" ] && break
  done
  left="$(listening_pid)"
  if [ -n "$left" ]; then
    echo "优雅退出失败，强制 kill -9 PID=$left…"
    kill -9 $left 2>/dev/null || true
    sleep 0.5
  fi
  left="$(listening_pid)"
  rm -f "$PID_FILE"
  if [ -n "$left" ]; then
    echo "停止失败：端口 $PORT 仍被 PID=$left 占用（可能无权限杀进程）" >&2
    return 1
  fi
  echo "已停止"
}

do_start_fg() {
  sync_bridge_client
  if [ -n "$(listening_pid)" ]; then
    echo "端口 $PORT 已在监听 → http://$HOST:$PORT"
    exit 0
  fi
  mkdir -p "$ENGINE/data"
  cd "$ENGINE"
  echo "启动 $APP 引擎（前台）→ http://$HOST:$PORT"
  exec "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
}

do_start_bg() {
  sync_bridge_client
  if health_ok; then
    echo "引擎已就绪 → http://$HOST:$PORT"
    return 0
  fi
  if [ -n "$(listening_pid)" ]; then
    echo "端口占用但健康检查失败，尝试重启…"
    do_stop
  fi
  mkdir -p "$ENGINE/data"
  cd "$ENGINE"
  echo "后台启动 $APP 引擎 → http://$HOST:$PORT （日志 $LOG_FILE）"
  nohup "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT" \
    >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 0.4
    if health_ok; then
      echo "引擎就绪 PID=$(listening_pid)"
      return 0
    fi
  done
  echo "启动超时，见 $LOG_FILE" >&2
  return 1
}

case "$CMD" in
  status) do_status ;;
  stop) do_stop ;;
  ensure) do_start_bg ;;
  restart) do_stop; do_start_bg ;;
  start)
    if [ "$DETACH" = "1" ]; then do_start_bg; else do_start_fg; fi
    ;;
  *)
    echo "未知命令: $CMD（status|ensure|start|stop|restart）"; exit 1
    ;;
esac

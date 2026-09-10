# WorkBuddy / 官方 DSH 端口自检（host.sh / verify-ports.sh 共用）
# shellcheck shell=bash

WORKBUDDY_WEB_PORT="${WORKBUDDY_WEB_PORT:-3081}"
OFFICIAL_WEB_PORT="${OFFICIAL_WEB_PORT:-3080}"
WORKBUDDY_HOME="${WORKBUDDY_HOME:-$HOME/.dsh}"
OFFICIAL_HOME="${OFFICIAL_HOME:-$HOME/.dsh-workbuddy}"

web_port_listen_pid() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1
}

web_port_log_file() {
  local root="$1"
  local port="$2"
  printf '%s/tmp/host-web-%s.log' "$root" "$port"
}

web_port_has_mes_bridge() {
  local log="$1"
  [ -f "$log" ] || return 1
  grep -q '\[mes-bridge\]' "$log" 2>/dev/null
}

web_port_http_code() {
  local port="$1"
  curl -sS -o /dev/null -w '%{http_code}' --max-time 4 "http://127.0.0.1:$port/" 2>/dev/null || echo 000
}

dsh_home_workspace_count() {
  local home="$1"
  python3 - "$home/storages/workspace.json" <<'PY' 2>/dev/null || echo 0
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file():
    print(0); raise SystemExit
d = json.loads(p.read_text(encoding="utf-8"))
print(len((d.get("global") or {}).get("workspaceIds") or []))
PY
}

profile_has_mes_bridge() {
  local profile="$1"
  python3 - "$profile/package.json" <<'PY' 2>/dev/null
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file():
    raise SystemExit(1)
deps = (json.loads(p.read_text(encoding="utf-8")).get("dependencies") or {})
print("yes" if any("dsh-mes-bridge" in k for k in deps) else "no")
PY
}

verify_workbuddy_ports() {
  local root="$1"
  local ok=1
  local wb_pid wb_code wb_log ws_n bridge_pkg

  wb_pid="$(web_port_listen_pid "$WORKBUDDY_WEB_PORT")"
  wb_log="$(web_port_log_file "$root" "$WORKBUDDY_WEB_PORT")"
  ws_n="$(dsh_home_workspace_count "$WORKBUDDY_HOME")"
  bridge_pkg="$(profile_has_mes_bridge "$WORKBUDDY_HOME/profiles/web" 2>/dev/null || echo no)"

  echo "=== 端口自检（WorkBuddy :$WORKBUDDY_WEB_PORT / DSH_HOME=$WORKBUDDY_HOME）==="

  if [ "$bridge_pkg" = "yes" ]; then
    echo "profile: mes-bridge 已接线"
  else
    echo "错误: $WORKBUDDY_HOME/profiles/web 未安装 mes-bridge" >&2
    ok=0
  fi

  if [ "${ws_n:-0}" -ge 1 ] 2>/dev/null; then
    echo "工作区: $ws_n 个（会话库 $WORKBUDDY_HOME）"
  else
    echo "错误: $WORKBUDDY_HOME 工作区为空，界面会像全新官方壳" >&2
    ok=0
  fi

  if [ -n "$wb_pid" ]; then
    wb_code="$(web_port_http_code "$WORKBUDDY_WEB_PORT")"
    echo "WorkBuddy :$WORKBUDDY_WEB_PORT → PID $wb_pid HTTP $wb_code"
    if web_port_has_mes_bridge "$wb_log"; then
      echo "  mes-bridge: 已在日志确认"
    else
      echo "警告: :$WORKBUDDY_WEB_PORT 日志未见 [mes-bridge]（$wb_log）" >&2
      ok=0
    fi
  else
    echo "错误: WorkBuddy :$WORKBUDDY_WEB_PORT 未监听" >&2
    ok=0
  fi

  if [ "$ok" -eq 1 ]; then
    echo "通过：http://127.0.0.1:$WORKBUDDY_WEB_PORT（设置里应有 WorkBuddy 页）"
  else
    echo "未通过：scripts/host.sh fix-ports" >&2
  fi
  return "$((1 - ok))"
}

stop_web_port() {
  local port="$1"
  local pid
  pid="$(web_port_listen_pid "$port")"
  [ -n "$pid" ] || return 0
  echo "停止 :$port (PID $pid)..."
  kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
  sleep 1
  pid="$(web_port_listen_pid "$port")"
  if [ -n "$pid" ]; then
    kill -9 -- -"$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    sleep 1
  fi
}

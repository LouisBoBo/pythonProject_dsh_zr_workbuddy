#!/bin/bash
# 宿主（host/）辅助：P1 状态检查 + P2 接线/启停（显式子命令，默认不乱启）
#
#   scripts/host.sh status|where|hint
#   scripts/host.sh verify              # 检查 link / profile Bridge / 引擎探活
#   scripts/host.sh wire                # 复用 plugin.sh install bridge（默认不 --restart）
#   scripts/host.sh wire --restart      # 接线后重启宿主（走 restart-dsh.sh）
#   scripts/host.sh ensure-engine       # 仅 ensure 业务引擎
#   scripts/host.sh ensure-web          # :3080 未监听则后台拉起（脱离 IDE 进程组）
#   scripts/host.sh up                  # ensure-engine + ensure-web（推荐日常入口）
#   scripts/host.sh start-web [--from-host]  # 强制启动（已在跑则报错）
#   scripts/host.sh restart-web         # stop-web + start-web（守护式）
#   scripts/host.sh stop-web            # 停掉监听 :3080 的进程（若有）
#
# 拒绝裸 install|start|dev，防误伤。不改 code_deploy / 不焊业务进 host/。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="$ROOT/host"
PROFILE="${DSH_PROFILE:-$HOME/.dsh/profiles/web}"
LINK_REPO="$HOME/.dsh/link/DSH-ZR-WorkBuddy"
PORT="${DSH_WEB_PORT:-3080}"
DAEMONIZE="$ROOT/scripts/lib/daemonize.py"
# 公网 IP/域名访问时需加入浏览器信任名单（逗号分隔），例：DSH_TRUSTED_HOSTS=175.178.238.31
TRUSTED_HOSTS="${DSH_TRUSTED_HOSTS:-}"
CMD="${1:-status}"
shift || true

if [ ! -d "$HOST" ] || [ ! -f "$HOST/package.json" ]; then
  echo "未找到 host/ 工程，请先按 docs/宿主二次开发-同仓host与部署方案.md 导入源码。" >&2
  exit 1
fi

# host_dsh kept for future --from-host helpers; start-web 默认走 PATH dsh
host_dsh() {
  if [ -d "$HOST/node_modules" ] && [ -f "$HOST/apps/cli/src/bin.ts" ]; then
    (cd "$HOST" && pnpm run dsh -- "$@")
    return
  fi
  if command -v dsh >/dev/null 2>&1; then
    dsh "$@"
    return
  fi
  echo "找不到 host CLI 且 PATH 无 dsh。请先: cd host && pnpm install" >&2
  exit 1
}

resolve_dsh_bin() {
  local dsh_bin
  dsh_bin="$(command -v dsh || true)"
  if [ -z "$dsh_bin" ]; then
    for c in \
      "$HOME/.nvm/versions/node/v22.23.1/bin/dsh" \
      "$HOME/.nvm/versions/node/current/bin/dsh" \
      /usr/local/bin/dsh; do
      [ -x "$c" ] && dsh_bin="$c" && break
    done
  fi
  printf '%s' "$dsh_bin"
}

cmd_status() {
  echo "host 目录: $HOST"
  python3 - <<'PY' "$HOST/package.json"
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
print("name:", d.get("name"))
print("version:", d.get("version"))
print("packageManager:", d.get("packageManager"))
print("engines.node:", (d.get("engines") or {}).get("node"))
PY
  if [ -d "$HOST/node_modules" ]; then
    echo "依赖: 已存在 host/node_modules"
  else
    echo "依赖: 尚未 pnpm install"
  fi
  echo "说明文档: host/WORKBUDDY.md 、 host/UPSTREAM.md"
  echo "业务目录: apps/zr-workbuddy/"
  local pid
  pid="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pid" ]; then
    echo "宿主 web: :$PORT 监听中 (PID $pid)"
  else
    echo "宿主 web: :$PORT 未监听"
  fi
}

cmd_hint() {
  cat <<EOF
【宿主操作提示】
1. 装依赖:           cd host && pnpm install
2. 接线 Bridge:      scripts/host.sh wire
3. 检查接线:         scripts/host.sh verify
4. 日常一键保活:     scripts/host.sh up          # 引擎 + :3080（守护进程，不被 IDE 关掉）
5. 仅确保引擎:       scripts/host.sh ensure-engine
6. 仅确保聊天壳:     scripts/host.sh ensure-web
7. 重启聊天壳:       scripts/host.sh restart-web
8. 停 Web 宿主:      scripts/host.sh stop-web
9. 生态插件: 宿主跑起来后用插件中心 / \`dsh plugin add\`——勿往引擎功能页硬塞整仓 zip
10. 版本注意: 本仓 host/ 为 0.1.0-rc.8；若本机全局 dsh 更高，日常用 PATH dsh（start-web 默认）
EOF
}

cmd_verify() {
  local ok=1
  echo "=== P2 接线检查 ==="
  if [ -L "$LINK_REPO" ] || [ -e "$LINK_REPO" ]; then
    echo "link: $LINK_REPO -> $(readlink "$LINK_REPO" 2>/dev/null || echo '?')"
    case "$(readlink "$LINK_REPO" 2>/dev/null || true)" in
      "$ROOT") ;;
      *) echo "警告: link 目标不是本仓库 $ROOT" >&2; ok=0 ;;
    esac
  else
    echo "缺失: $LINK_REPO（请 scripts/host.sh wire）" >&2
    ok=0
  fi

  if [ ! -f "$PROFILE/package.json" ]; then
    echo "缺失: $PROFILE/package.json（请先按上游文档初始化 profiles/web）" >&2
    ok=0
  else
    python3 - <<'PY' "$PROFILE/package.json" "$ROOT" || ok=0
import json,sys
pj, root = sys.argv[1], sys.argv[2]
deps=(json.load(open(pj)).get("dependencies") or {})
spec=deps.get("@dsh-external/dsh-mes-bridge")
print("profile bridge dep:", spec or "<missing>")
if not spec or "DSH-ZR-WorkBuddy/apps/zr-workbuddy/plugins/mes-bridge" not in str(spec):
    print("错误: profile 未指向本仓 apps/zr-workbuddy/plugins/mes-bridge", file=sys.stderr)
    raise SystemExit(1)
PY
  fi

  if [ -f "$PROFILE/cordis.patch.yml" ]; then
    if grep -q "id: dsh-mes-bridge" "$PROFILE/cordis.patch.yml"; then
      echo "cordis.patch: 含 id dsh-mes-bridge"
    else
      echo "错误: cordis.patch.yml 缺少 dsh-mes-bridge insert" >&2
      ok=0
    fi
  else
    echo "缺失: $PROFILE/cordis.patch.yml" >&2
    ok=0
  fi

  if "$ROOT/scripts/engine.sh" zr-workbuddy status >/tmp/wb-engine-status.$$ 2>&1; then
    head -5 /tmp/wb-engine-status.$$
  else
    echo "引擎未就绪（可用 scripts/host.sh ensure-engine）:" >&2
    cat /tmp/wb-engine-status.$$ >&2 || true
    ok=0
  fi
  rm -f /tmp/wb-engine-status.$$

  PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$PID" ]; then
    echo "宿主 web: 监听 :$PORT (PID $PID) → http://127.0.0.1:$PORT"
  else
    echo "宿主 web: :$PORT 未监听（可用 scripts/host.sh ensure-web / up）"
  fi

  if [ "$ok" -eq 1 ]; then
    echo "=== verify OK ==="
    return 0
  fi
  echo "=== verify 有问题（见上）===" >&2
  return 1
}

cmd_wire() {
  local do_restart=0
  for a in "$@"; do
    case "$a" in --restart) do_restart=1 ;; esac
  done
  if [ ! -f "$PROFILE/package.json" ]; then
    echo "本机尚无 $PROFILE/package.json。" >&2
    echo "请先按 DeepSeek Harness / host README 初始化 profiles/web，再重跑 wire。" >&2
    exit 1
  fi
  if [ ! -d "$HOST/node_modules" ]; then
    echo "警告: host/node_modules 不存在；接线仍可写 profile，但 start-web 需先 pnpm install。" >&2
  fi
  if [ "$do_restart" -eq 1 ]; then
    echo "执行: plugin.sh --app zr-workbuddy install bridge --restart"
    echo "提示: --restart 走 scripts/restart-dsh.sh（守护启动，脚本会返回）。" >&2
    echo "      若要用本仓 host CLI，请改用: wire（无 restart）+ restart-web --from-host" >&2
    "$ROOT/scripts/plugin.sh" --app zr-workbuddy install bridge --restart
  else
    echo "执行: plugin.sh --app zr-workbuddy install bridge（不重启宿主）"
    "$ROOT/scripts/plugin.sh" --app zr-workbuddy install bridge
  fi
  cmd_verify || true
}

cmd_ensure_engine() {
  "$ROOT/scripts/engine.sh" zr-workbuddy ensure
}

cmd_stop_web() {
  local PID
  PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -z "$PID" ]; then
    echo ":$PORT 无监听进程"
    rm -f "$ROOT/tmp/host-web.pid"
    return 0
  fi
  echo "停止 :$PORT (PID $PID)..."
  # 尽量带进程组；失败再杀单进程
  kill -- -"$PID" 2>/dev/null || kill "$PID" || true
  sleep 1
  PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$PID" ]; then
    echo "仍在运行，发送 SIGKILL..." >&2
    kill -9 -- -"$PID" 2>/dev/null || kill -9 "$PID" || true
  fi
  rm -f "$ROOT/tmp/host-web.pid"
  echo "已停止"
}

_launch_web_daemon() {
  local from_host="$1"
  mkdir -p "$ROOT/tmp"
  local log="$ROOT/tmp/host-web.log"
  local pidf="$ROOT/tmp/host-web.pid"
  : >"$log"

  # shellcheck disable=SC2207
  local web_args=(web --no-open)
  if [ -n "$TRUSTED_HOSTS" ]; then
    local IFS=',' h
    for h in $TRUSTED_HOSTS; do
      h="$(printf '%s' "$h" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      [ -n "$h" ] && web_args+=(--trusted-host "$h")
    done
  fi

  if [ "$from_host" = "1" ]; then
    if [ ! -d "$HOST/node_modules" ]; then
      echo "缺少 host/node_modules。请先: cd host && pnpm install" >&2
      exit 1
    fi
    echo "警告: --from-host 使用 host/ 源码 CLI（常落后于全局 dsh）。" >&2
    echo "启动本仓 host CLI（守护）: dsh ${web_args[*]} （:$PORT）"
    echo "日志: $log"
    local quoted=""
    local a
    for a in "${web_args[@]}"; do
      quoted="$quoted $(printf '%q' "$a")"
    done
    python3 "$DAEMONIZE" --cwd "$HOST" --log "$log" --pid "$pidf" -- \
      bash -lc "exec pnpm run dsh --$quoted"
  else
    local dsh_bin
    dsh_bin="$(resolve_dsh_bin)"
    if [ -z "$dsh_bin" ]; then
      echo "PATH 无 dsh。可装全局 CLI，或: scripts/host.sh start-web --from-host" >&2
      exit 1
    fi
    echo "启动全局 dsh（守护、脱离 IDE 进程组）: $dsh_bin ${web_args[*]} （:$PORT）"
    echo "日志: $log"
    # cwd=HOME：与 restart-dsh.sh 一致，credentials/profile 可解析
    python3 "$DAEMONIZE" --cwd "$HOME" --log "$log" --pid "$pidf" -- \
      "$dsh_bin" "${web_args[@]}"
  fi
}

_wait_web() {
  local i code
  for i in $(seq 1 25); do
    sleep 1
    if lsof -tiTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
      code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$PORT/" 2>/dev/null || echo 000)"
      echo "宿主 web 已监听 http://127.0.0.1:$PORT （HTTP $code）"
      echo "业务引擎请另看: scripts/engine.sh zr-workbuddy status"
      return 0
    fi
  done
  echo "25s 内未听到 :$PORT，请查看日志: $ROOT/tmp/host-web.log" >&2
  tail -40 "$ROOT/tmp/host-web.log" >&2 || true
  return 1
}

cmd_start_web() {
  local from_host=0
  for a in "$@"; do
    case "$a" in --from-host) from_host=1 ;; esac
  done

  if [ ! -f "$PROFILE/package.json" ]; then
    echo "缺少 profile: $PROFILE —— 请先初始化并 scripts/host.sh wire" >&2
    exit 1
  fi
  local PID
  PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$PID" ]; then
    echo ":$PORT 已有进程 PID $PID。若要重启请先: scripts/host.sh restart-web" >&2
    exit 2
  fi

  _launch_web_daemon "$from_host"
  _wait_web
}

cmd_ensure_web() {
  if [ ! -f "$PROFILE/package.json" ]; then
    echo "缺少 profile: $PROFILE —— 请先 scripts/host.sh wire" >&2
    exit 1
  fi
  local PID code
  PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$PID" ]; then
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$PORT/" 2>/dev/null || echo 000)"
    if [ "$code" = "200" ] || [ "$code" = "304" ]; then
      echo "宿主 web 已就绪 → http://127.0.0.1:$PORT （PID $PID，HTTP $code）"
      return 0
    fi
    echo "端口占用但 HTTP 异常（$code），重启聊天壳…" >&2
    cmd_stop_web || true
  fi
  _launch_web_daemon 0
  _wait_web
}

cmd_restart_web() {
  cmd_stop_web || true
  sleep 1
  cmd_start_web "$@"
}

cmd_up() {
  echo "=== WorkBuddy up：引擎 + 聊天壳（守护）==="
  # 引擎失败不阻断聊天壳；两边各自 ensure
  if ! cmd_ensure_engine; then
    echo "警告: 引擎 ensure 未成功，继续尝试聊天壳…" >&2
  fi
  cmd_ensure_web
  cmd_verify || true
  echo "打开: http://127.0.0.1:$PORT"
}

case "$CMD" in
  where) echo "$HOST" ;;
  status) cmd_status ;;
  hint) cmd_hint ;;
  verify) cmd_verify ;;
  wire) cmd_wire "$@" ;;
  ensure-engine) cmd_ensure_engine ;;
  ensure-web) cmd_ensure_web ;;
  up) cmd_up ;;
  start-web) cmd_start_web "$@" ;;
  restart-web) cmd_restart_web "$@" ;;
  stop-web) cmd_stop_web ;;
  install|start|dev)
    echo "已拒绝自动执行「$CMD」。请用: up | ensure-web | ensure-engine | wire | hint" >&2
    exit 2
    ;;
  *)
    echo "用法: scripts/host.sh status|where|hint|verify|wire [--restart]|up|ensure-engine|ensure-web|start-web [--from-host]|restart-web|stop-web" >&2
    exit 1
    ;;
esac

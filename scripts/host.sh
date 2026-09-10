#!/bin/bash
# 宿主（host/）辅助：P1 状态检查 + P2 接线/启停（显式子命令，默认不乱启）
#
#   scripts/host.sh status|where|hint
#   scripts/host.sh verify              # 检查 link / profile Bridge / 引擎探活
#   scripts/host.sh wire                # 复用 plugin.sh install bridge（默认不 --restart）
#   scripts/host.sh wire --restart      # 接线后重启宿主（走 restart-dsh.sh）
#   scripts/host.sh ensure-engine       # 仅 ensure 业务引擎
#   scripts/host.sh ensure-web          # :3081 未监听则后台拉起（脱离 IDE 进程组）
#   scripts/host.sh up                  # ensure-engine + ensure-web（推荐日常入口）
#   scripts/host.sh start-web [--from-host]  # 强制启动（已在跑则报错）
#   scripts/host.sh restart-web         # stop-web + start-web（守护式）
#   scripts/host.sh fix-ports           # 纠正端口错位 + 自检
#   scripts/host.sh verify-ports        # 仅检查 :3081 WorkBuddy / :3080 官方
#   scripts/host.sh stop-web            # 停掉监听 :3081 的进程（若有）
#
# 端口约定（勿混）：
#   - WorkBuddy 开发壳 :3081（DSH_HOME=~/.dsh，profile 含 mes-bridge，工作区在此）
#   - 干净官方 Harness 可选 :3080（DSH_HOME=~/.dsh-workbuddy，无 bridge）
#   - 桌面一体包默认 :13080（Application Support/.../dsh-home，另一套会话）
#   - 可用 DSH_WEB_PORT=… / DSH_HOME=… / DSH_PROFILE=… 覆盖
#
# 拒绝裸 install|start|dev，防误伤。不改 code_deploy / 不焊业务进 host/。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/workbuddy_web_env.sh
. "$ROOT/scripts/lib/workbuddy_web_env.sh"
prepend_workbuddy_node_path
# shellcheck source=lib/web_port_verify.sh
. "$ROOT/scripts/lib/web_port_verify.sh"
HOST="$ROOT/host"
WORKBUDDY_WEB_PORT="${WORKBUDDY_WEB_PORT:-3081}"
OFFICIAL_WEB_PORT="${OFFICIAL_WEB_PORT:-3080}"
# DSH_HOME 决定会话库；DSH_PROFILE 可为绝对路径，或相对 profiles 下的名字
# 与会话/工作区共用 ~/.dsh；勿再用空的 ~/.dsh-workbuddy 当主开发壳
DSH_HOME_DIR="${DSH_HOME:-$HOME/.dsh}"
export DSH_HOME="$DSH_HOME_DIR"
if [ -n "${DSH_PROFILE:-}" ]; then
  case "$DSH_PROFILE" in
    /*|~*) PROFILE="$DSH_PROFILE" ;;
    *) PROFILE="$DSH_HOME_DIR/profiles/$DSH_PROFILE" ;;
  esac
else
  PROFILE="$DSH_HOME_DIR/profiles/web"
fi
# 展开 ~
PROFILE="${PROFILE/#\~/$HOME}"
LINK_DIR="$DSH_HOME_DIR/link"
LINK_REPO="$LINK_DIR/DSH-ZR-WorkBuddy"
PORT="${DSH_WEB_PORT:-3081}"
DAEMONIZE="$ROOT/scripts/lib/daemonize.py"
# 公网 IP/域名访问时需加入浏览器信任名单（逗号分隔），例：DSH_TRUSTED_HOSTS=175.178.238.31
TRUSTED_HOSTS="${DSH_TRUSTED_HOSTS:-}"
CMD="${1:-status}"
shift || true

if [ ! -d "$HOST" ] || [ ! -f "$HOST/package.json" ]; then
  echo "未找到 host/ 工程，请先按 docs/架构与选型/宿主二次开发-同仓host与部署方案.md 导入源码。" >&2
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

# dsh 脚本为 #!/usr/bin/env node；须把同目录 node 置于 PATH 前，避免误用 /usr/local 的 Node 20
prepend_dsh_node_path() {
  prepend_workbuddy_node_path
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
  echo "DSH_HOME: $DSH_HOME_DIR（工作区 $(dsh_home_workspace_count "$DSH_HOME_DIR") 个）"
  local wb_pid
  wb_pid="$(web_port_listen_pid "$WORKBUDDY_WEB_PORT")"
  if [ -n "$wb_pid" ]; then
    echo "WorkBuddy web: :$WORKBUDDY_WEB_PORT 监听中 (PID $wb_pid)"
  else
    echo "WorkBuddy web: :$WORKBUDDY_WEB_PORT 未监听 → scripts/host.sh fix-ports"
  fi
  echo "开发请开: http://127.0.0.1:$WORKBUDDY_WEB_PORT"
}

cmd_hint() {
  cat <<EOF
【宿主操作提示】
1. 装依赖:           cd host && pnpm install
2. 接线 Bridge:      scripts/host.sh wire
3. 检查接线:         scripts/host.sh verify
4. 日常一键保活:     scripts/host.sh up          # 引擎 + :3081（守护进程，不被 IDE 关掉）
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
    echo "提示: --restart 走 scripts/host.sh restart-web（DSH_HOME=~/.dsh-workbuddy，:3081）。" >&2
    echo "      若要用本仓 host CLI，请改用: wire（无 restart）+ restart-web --from-host" >&2
    "$ROOT/scripts/plugin.sh" --app zr-workbuddy install bridge --restart
  else
    echo "执行: plugin.sh --app zr-workbuddy install bridge（不重启宿主）"
    "$ROOT/scripts/plugin.sh" --app zr-workbuddy install bridge
  fi
  # 接线时同步写入公司市场 npmrc（不启动 web 也会准备好）
  # shellcheck source=lib/company_dsh_market.sh
  . "$ROOT/scripts/lib/company_dsh_market.sh"
  apply_company_dsh_market
  cmd_verify || true
}

cmd_ensure_engine() {
  sync_dev_engine_env
  "$ROOT/scripts/engine.sh" zr-workbuddy ensure
}

cmd_stop_web() {
  stop_web_port "$PORT"
  rm -f "$ROOT/tmp/host-web-${PORT}.pid" "$ROOT/tmp/host-web.pid"
  echo "已停止 :$PORT"
}

ensure_workbuddy_webserver_patch() {
  if [ ! -f "$PROFILE/cordis.patch.yml" ]; then
    echo "跳过 webserver patch：缺少 $PROFILE/cordis.patch.yml" >&2
    return 0
  fi
  python3 "$ROOT/scripts/lib/ensure_web_port_patch.py" "$PROFILE" "$WORKBUDDY_WEB_PORT"
}

_launch_web_daemon() {
  local from_host="$1"
  sync_dev_engine_env
  # 强制会话库落到本脚本解析出的家目录（daemon 子进程也继承）
  export DSH_HOME="$DSH_HOME_DIR"
  echo "DSH_HOME=$DSH_HOME  PROFILE=$PROFILE  port=$PORT"
  # 公司插件市场：仅注入 DSHM_REGISTRY_URL + @zhongruan npmrc（可被环境变量覆盖）
  # shellcheck source=lib/company_dsh_market.sh
  . "$ROOT/scripts/lib/company_dsh_market.sh"
  apply_company_dsh_market
  mkdir -p "$ROOT/tmp"
  local log pidf
  log="$(web_port_log_file "$ROOT" "$PORT")"
  pidf="$ROOT/tmp/host-web-${PORT}.pid"
  : >"$log"

  # shellcheck disable=SC2207
  local web_args=(web --no-open --host 127.0.0.1 --port "$PORT")
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
    prepend_dsh_node_path "$dsh_bin"
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
  echo "25s 内未听到 :$PORT，请查看日志: $(web_port_log_file "$ROOT" "$PORT")" >&2
  tail -40 "$(web_port_log_file "$ROOT" "$PORT")" 2>/dev/null || true
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
  # 重启前对齐 profile 内 dsh-tools，避免「本轮运行失败 reading prepare」
  if [ -x "$ROOT/scripts/check-vendor.sh" ]; then
    "$ROOT/scripts/check-vendor.sh" --fix || true
  fi
  ensure_workbuddy_webserver_patch
  cmd_stop_web || true
  sleep 1
  cmd_start_web "$@"
  verify_workbuddy_ports "$ROOT" || true
}

cmd_fix_ports() {
  echo "=== WorkBuddy :$WORKBUDDY_WEB_PORT（DSH_HOME=$DSH_HOME_DIR，含工作区 + mes-bridge）==="
  stop_web_port "$WORKBUDDY_WEB_PORT" || true
  stop_web_port "$OFFICIAL_WEB_PORT" || true
  sleep 1

  echo "接线 mes-bridge → $PROFILE"
  "$ROOT/scripts/plugin.sh" --app zr-workbuddy install bridge
  ensure_workbuddy_webserver_patch

  sync_dev_engine_env
  export DSH_HOME="$DSH_HOME_DIR"
  export DSH_WEB_PORT="$WORKBUDDY_WEB_PORT"
  PORT="$WORKBUDDY_WEB_PORT"

  if ! cmd_ensure_engine; then
    echo "警告: 引擎 ensure 未成功，继续拉起聊天壳…" >&2
  fi
  _launch_web_daemon 0
  _wait_web || true
  local i wb_log
  wb_log="$(web_port_log_file "$ROOT" "$WORKBUDDY_WEB_PORT")"
  for i in $(seq 1 45); do
    if web_port_has_mes_bridge "$wb_log"; then
      break
    fi
    sleep 1
  done

  if DSH_HOME="$DSH_HOME_DIR" python3 "$ROOT/scripts/lib/verify_workbuddy_web.py"; then
    echo "打开 WorkBuddy: http://127.0.0.1:$WORKBUDDY_WEB_PORT"
  else
    return 1
  fi
}

cmd_verify_ports() {
  verify_workbuddy_ports "$ROOT"
}

cmd_up() {
  echo "=== WorkBuddy up：引擎 + 聊天壳（守护）==="
  local desk_pid
  desk_pid="$(lsof -tiTCP:13080 -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$desk_pid" ]; then
    echo "警告: 桌面 App 仍在 :13080 (PID $desk_pid)，会注入 APP_ENGINE_PORT=18000 污染环境。" >&2
    echo "      开发请完全退出桌面 App，只用 http://127.0.0.1:$PORT （浏览器壳，勿开桌面 :13080 混看会话）。" >&2
  fi
  # 引擎失败不阻断聊天壳；两边各自 ensure
  if ! cmd_ensure_engine; then
    echo "警告: 引擎 ensure 未成功，继续尝试聊天壳…" >&2
  fi
  cmd_ensure_web
  cmd_verify || true
  verify_workbuddy_ports "$ROOT" || true
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
  fix-ports) cmd_fix_ports ;;
  verify-ports) cmd_verify_ports ;;
  stop-web) cmd_stop_web ;;
  install|start|dev)
    echo "已拒绝自动执行「$CMD」。请用: up | ensure-web | ensure-engine | wire | hint" >&2
    exit 2
    ;;
  *)
    echo "用法: scripts/host.sh status|where|hint|verify|wire [--restart]|up|ensure-engine|ensure-web|start-web [--from-host]|restart-web|fix-ports|verify-ports|stop-web" >&2
    exit 1
    ;;
esac

#!/bin/bash
# 重启 dsh web（守护启动后脚本返回；不被 Cursor/IDE 进程组带走）
# 环境变量可选：DSH_BIN、DSH_WEB_PORT、DSH_CWD、DSH_TRUSTED_HOSTS（逗号分隔）
# 可选：--fg 前台运行（本机终端调试用）
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${DSH_WEB_PORT:-3080}"
FG=0
for a in "$@"; do
  case "$a" in --fg|--foreground) FG=1 ;; esac
done

DSH_BIN="${DSH_BIN:-$(command -v dsh || true)}"
if [ -z "$DSH_BIN" ]; then
  for c in \
    "$HOME/.nvm/versions/node/v22.23.1/bin/dsh" \
    "$HOME/.nvm/versions/node/current/bin/dsh" \
    /usr/local/bin/dsh; do
    [ -x "$c" ] && DSH_BIN="$c" && break
  done
fi
[ -n "$DSH_BIN" ] || { echo "找不到 dsh 可执行文件，请设置 DSH_BIN"; exit 1; }

WEB_ARGS=(web --no-open)
if [ -n "${DSH_TRUSTED_HOSTS:-}" ]; then
  old_ifs=$IFS
  IFS=','
  # shellcheck disable=SC2086
  set -- $DSH_TRUSTED_HOSTS
  IFS=$old_ifs
  for h in "$@"; do
    h="$(printf '%s' "$h" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -n "$h" ] && WEB_ARGS+=(--trusted-host "$h")
  done
fi

PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$PID" ]; then
  echo "停止旧 dsh web (PID $PID, :$PORT)..."
  kill -- -"$PID" 2>/dev/null || kill "$PID" || true
  sleep 2
  PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$PID" ]; then
    kill -9 -- -"$PID" 2>/dev/null || kill -9 "$PID" || true
    sleep 1
  fi
fi

CWD="${DSH_CWD:-$HOME}"
# 公司插件市场（与 host.sh 一致；不覆盖已有 DSHM_REGISTRY_URL）
# shellcheck source=lib/company_dsh_market.sh
. "$ROOT/scripts/lib/company_dsh_market.sh"
apply_company_dsh_market

if [ "$FG" = "1" ]; then
  cd "$CWD"
  echo "前台启动 dsh web（$DSH_BIN ${WEB_ARGS[*]}）..."
  exec "$DSH_BIN" "${WEB_ARGS[@]}"
fi

mkdir -p "$ROOT/tmp"
LOG="$ROOT/tmp/host-web.log"
PIDF="$ROOT/tmp/host-web.pid"
: >"$LOG"
echo "守护启动 dsh web（$DSH_BIN ${WEB_ARGS[*]}，脱离 IDE 进程组）→ :$PORT"
echo "日志: $LOG"
python3 "$ROOT/scripts/lib/daemonize.py" --cwd "$CWD" --log "$LOG" --pid "$PIDF" -- \
  "$DSH_BIN" "${WEB_ARGS[@]}"

for i in $(seq 1 25); do
  sleep 1
  if lsof -tiTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$PORT/" 2>/dev/null || echo 000)"
    echo "dsh web 已监听 http://127.0.0.1:$PORT （HTTP $code）"
    exit 0
  fi
done
echo "25s 内未听到 :$PORT，见 $LOG" >&2
tail -40 "$LOG" >&2 || true
exit 1

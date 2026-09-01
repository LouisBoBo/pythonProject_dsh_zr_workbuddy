#!/bin/bash
# 重启 dsh web（请在本机终端运行）
# 环境变量可选：DSH_BIN、DSH_WEB_PORT、DSH_CWD
set -e
PORT="${DSH_WEB_PORT:-3080}"
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

PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$PID" ]; then
  echo "停止旧 dsh web (PID $PID, :$PORT)..."
  kill "$PID" || true
  sleep 2
fi

CWD="${DSH_CWD:-$HOME}"
cd "$CWD"
echo "启动 dsh web（$DSH_BIN）..."
exec "$DSH_BIN" web --no-open

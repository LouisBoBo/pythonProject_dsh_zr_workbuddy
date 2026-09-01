#!/bin/bash
# 核对（并可修复）vendor 与宿主 dsh-tools 是否同一 realpath。
# 不同路径 → Node ESM 双实例 → TOOL_RUNTIME_SCHEDULER Symbol 不一致
# → agent-loop 调用 ctx.tools[SYMBOL].prepare 报
#   Cannot read properties of undefined (reading 'prepare')
#
# 用法:
#   scripts/check-vendor.sh           # 只检查
#   scripts/check-vendor.sh --fix    # 把 vendor 链到宿主同包
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="@deepseek-ai/dsh-tools"
VENDOR_DIR="$ROOT/vendor/$PKG"
DO_FIX=0
[ "${1:-}" = "--fix" ] && DO_FIX=1

find_host_tools() {
  local dsh_bin c
  dsh_bin="$(command -v dsh 2>/dev/null || true)"
  local candidates=()
  if [ -n "$dsh_bin" ]; then
    candidates+=(
      "$(cd "$(dirname "$dsh_bin")/.." && pwd)/lib/node_modules/@deepseek-ai/dsh/node_modules/$PKG"
    )
  fi
  candidates+=(
    "$HOME/.nvm/versions/node/v22.23.1/lib/node_modules/@deepseek-ai/dsh/node_modules/$PKG"
  )
  for c in "${candidates[@]}"; do
    [ -f "$c/package.json" ] && { echo "$c"; return 0; }
  done
  return 1
}

HOST_DIR="$(find_host_tools || true)"
if [ -z "$HOST_DIR" ]; then
  echo "⚠️ 未找到宿主 $PKG，跳过"
  exit 0
fi

V_VER="?"
[ -f "$VENDOR_DIR/package.json" ] && V_VER="$(python3 -c "import json;print(json.load(open('$VENDOR_DIR/package.json'))['version'])")"
H_VER="$(python3 -c "import json;print(json.load(open('$HOST_DIR/package.json'))['version'])")"
V_REAL="$(python3 -c "import os;print(os.path.realpath('$VENDOR_DIR') if os.path.exists('$VENDOR_DIR') else '')")"
H_REAL="$(python3 -c "import os;print(os.path.realpath('$HOST_DIR'))")"

echo "vendor $PKG ver=$V_VER"
echo "       path=$VENDOR_DIR"
echo "       real=$V_REAL"
echo "host   $PKG ver=$H_VER"
echo "       path=$HOST_DIR"
echo "       real=$H_REAL"

if [ "$V_REAL" = "$H_REAL" ]; then
  echo "✅ realpath 一致（ESM / Symbol 同源）"
  exit 0
fi

echo "❌ realpath 不一致 → 会导致 tool prepare 失败"
if [ "$DO_FIX" != "1" ]; then
  echo "修复: scripts/check-vendor.sh --fix"
  exit 1
fi

mkdir -p "$(dirname "$VENDOR_DIR")"
if [ -e "$VENDOR_DIR" ] || [ -L "$VENDOR_DIR" ]; then
  if [ -d "$VENDOR_DIR" ] && [ ! -L "$VENDOR_DIR" ]; then
    rm -rf "${VENDOR_DIR}.bak-copy"
    mv "$VENDOR_DIR" "${VENDOR_DIR}.bak-copy"
    echo "已备份原 vendor 目录 → ${VENDOR_DIR}.bak-copy"
  else
    rm -f "$VENDOR_DIR"
  fi
fi
ln -sfn "$HOST_DIR" "$VENDOR_DIR"
echo "已链接 vendor → 宿主: $VENDOR_DIR → $HOST_DIR"
echo "✅ 请重启 DSH：scripts/plugin.sh --app zr-workbuddy install bridge --restart"

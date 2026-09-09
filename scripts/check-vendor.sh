#!/bin/bash
# 核对（并可修复）dsh-tools 是否与宿主同一 realpath。
# 不同路径 → Node ESM 双实例 → TOOL_RUNTIME_SCHEDULER 用 Symbol() 时不一致
# → agent-loop 调用 ctx.tools[SYMBOL].prepare 报
#   Cannot read properties of undefined (reading 'prepare')
#
# 检查范围：
#   1) 仓库 vendor/@deepseek-ai/dsh-tools
#   2) 当前 DSH profile（默认 ~/.dsh/profiles/web）下的 node_modules 副本
#      （市场插件如 pcb-helper 硬依赖常会再装一份，把宿主 Symbol 盖掉）
#
# 用法:
#   scripts/check-vendor.sh           # 只检查
#   scripts/check-vendor.sh --fix    # 把 vendor / profile 副本链到宿主同包
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="@deepseek-ai/dsh-tools"
VENDOR_DIR="$ROOT/vendor/$PKG"
PROFILE_NAME="${DSH_PROFILE:-web}"
PROFILE_DIR="${DSH_PROFILE_DIR:-$HOME/.dsh/profiles/$PROFILE_NAME}"
PROFILE_TOOLS="$PROFILE_DIR/node_modules/$PKG"
DO_FIX=0
[ "${1:-}" = "--fix" ] && DO_FIX=1
FAILED=0

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

link_to_host() {
  local target="$1"
  local host="$2"
  local label="$3"
  mkdir -p "$(dirname "$target")"
  if [ -e "$target" ] || [ -L "$target" ]; then
    if [ -d "$target" ] && [ ! -L "$target" ]; then
      rm -rf "${target}.bak-copy"
      mv "$target" "${target}.bak-copy"
      echo "已备份原 ${label} 目录 → ${target}.bak-copy"
    else
      rm -f "$target"
    fi
  fi
  ln -sfn "$host" "$target"
  echo "已链接 ${label} → 宿主: $target → $host"
}

check_one() {
  local label="$1"
  local path="$2"
  local host="$3"
  local h_real="$4"
  if [ ! -e "$path" ] && [ ! -L "$path" ]; then
    echo "ℹ️  ${label}: 不存在（跳过） path=$path"
    return 0
  fi
  local ver="?"
  [ -f "$path/package.json" ] && ver="$(python3 -c "import json;print(json.load(open('$path/package.json'))['version'])" 2>/dev/null || echo '?')"
  local real
  real="$(python3 -c "import os;print(os.path.realpath('$path') if os.path.lexists('$path') else '')")"
  echo "${label} $PKG ver=$ver"
  echo "       path=$path"
  echo "       real=$real"
  echo "host   $PKG"
  echo "       path=$host"
  echo "       real=$h_real"
  if [ "$real" = "$h_real" ]; then
    echo "✅ ${label} realpath 一致（ESM / Symbol 同源）"
    return 0
  fi
  echo "❌ ${label} realpath 不一致 → 会导致 tool prepare 失败"
  if [ "$DO_FIX" = "1" ]; then
    link_to_host "$path" "$host" "$label"
    real="$(python3 -c "import os;print(os.path.realpath('$path'))")"
    if [ "$real" = "$h_real" ]; then
      echo "✅ ${label} 已修复"
      return 0
    fi
    echo "❌ ${label} 修复后仍不一致"
  fi
  FAILED=1
  return 1
}

HOST_DIR="$(find_host_tools || true)"
if [ -z "$HOST_DIR" ]; then
  echo "⚠️ 未找到宿主 $PKG，跳过"
  exit 0
fi
H_REAL="$(python3 -c "import os;print(os.path.realpath('$HOST_DIR'))")"
H_VER="$(python3 -c "import json;print(json.load(open('$HOST_DIR/package.json'))['version'])")"
echo "host   $PKG ver=$H_VER real=$H_REAL"
echo

check_one "vendor" "$VENDOR_DIR" "$HOST_DIR" "$H_REAL" || true
echo
check_one "profile:$PROFILE_NAME" "$PROFILE_TOOLS" "$HOST_DIR" "$H_REAL" || true

# 嵌套副本（市场插件 node_modules 内）也一并扫；--fix 时链到宿主
NESTED="$(find "$PROFILE_DIR/node_modules" -type d -path "*/node_modules/$PKG" 2>/dev/null | grep -v "^$PROFILE_TOOLS\$" || true)"
if [ -n "$NESTED" ]; then
  echo
  while IFS= read -r nest; do
    [ -z "$nest" ] && continue
    check_one "nested" "$nest" "$HOST_DIR" "$H_REAL" || true
  done <<< "$NESTED"
fi

if [ "$FAILED" = "0" ]; then
  exit 0
fi
if [ "$DO_FIX" != "1" ]; then
  echo
  echo "修复: scripts/check-vendor.sh --fix"
  echo "然后: scripts/plugin.sh --app zr-workbuddy install bridge --restart"
  exit 1
fi
echo
echo "✅ 请重启 DSH：scripts/plugin.sh --app zr-workbuddy install bridge --restart"
exit 0

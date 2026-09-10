#!/usr/bin/env bash
# 产出 Mac 宿主一体安装包：内嵌 Host（staged dsh）+ 内嵌引擎
# 用法:
#   ./scripts/package-desktop.sh           # 默认 unified；主产物 zip（不打 dmg）
#   ./scripts/package-desktop.sh unified
#   ./scripts/package-desktop.sh engine    # 仅引擎壳（旧体验包，需本机 dsh）
#   MAKE_DMG=1 ./scripts/package-desktop.sh  # 额外打 DMG（需本机 hdiutil 健康）
#   SKIP_RUNTIME=1 SKIP_HOST=1 SKIP_NODE=1 SKIP_MARKET=1 SKIP_PNPM=1 ./scripts/package-desktop.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

log() { printf '\033[1;34m[package-desktop]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[package-desktop]\033[0m %s\n' "$*" >&2; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "缺少命令: $1"; exit 1; }
}

need_cmd npm
need_cmd python3

MODE="${1:-unified}"
EB_TARGET=""
case "$MODE" in
  unified|host|一体) MODE="unified" ;;
  engine|engine-only|simple) MODE="engine" ;;
  mac|win|linux)
    EB_TARGET="$MODE"
    MODE="unified"
    ;;
  *)
    err "未知参数: $MODE（unified | engine | mac）"
    exit 1
    ;;
esac

DESKTOP_VERSION="$(python3 - <<PY
import json
from pathlib import Path
print(json.loads(Path("${ROOT}/desktop/package.json").read_text(encoding="utf-8"))["version"])
PY
)"
GIT_COMMIT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "版本: ZR WorkBuddy ${DESKTOP_VERSION} (git ${GIT_COMMIT}) mode=${MODE}"
log "提醒: 不会把 engine/config/config.yaml 真密钥打进包；用户安装后自行配置"

SKIP_RUNTIME="${SKIP_RUNTIME:-0}"
SKIP_HOST="${SKIP_HOST:-0}"

if [[ "$SKIP_RUNTIME" != "1" ]]; then
  log "构建内嵌引擎运行时 → desktop/runtime/ ..."
  python3 "$ROOT/desktop/py/build_runtime.py"
fi

test -e "$ROOT/desktop/runtime/bin/workbuddy-engine" \
  || test -e "$ROOT/desktop/runtime/bin/workbuddy-engine.cmd" \
  || { err "缺少 workbuddy-engine"; exit 1; }
test -d "$ROOT/desktop/runtime/python" || { err "缺少 desktop/runtime/python"; exit 1; }
# 打包前强制校验：内嵌 python 必须可执行（防绝对路径断链再次进包）
PY_BIN="$ROOT/desktop/runtime/python/bin/python3"
[[ -x "$PY_BIN" ]] || PY_BIN="$ROOT/desktop/runtime/python/bin/python"
if [[ ! -x "$PY_BIN" ]]; then
  err "内嵌 python 不可执行: $ROOT/desktop/runtime/python/bin/python3"
  exit 1
fi
if ! "$PY_BIN" -c "import fastapi, uvicorn; print('py_ok')" >/dev/null; then
  err "内嵌 python 无法 import fastapi/uvicorn。请去掉 SKIP_RUNTIME 重跑 build_runtime。"
  exit 1
fi
log "内嵌 python 校验通过: $PY_BIN"
test -d "$ROOT/desktop/runtime/app/apps/zr-workbuddy/engine" || { err "缺少 runtime app"; exit 1; }
test -f "$ROOT/desktop/runtime/app/scripts/lib/read_runtime.py" \
  || { err "runtime app 缺少 scripts/lib/read_runtime.py（请勿 SKIP_RUNTIME，或升级 build_runtime）"; exit 1; }
for _mod in code_dev code_review code_commit code_deploy hitl; do
  test -f "$ROOT/desktop/runtime/app/apps/zr-workbuddy/engine/app/${_mod}/__init__.py" \
    || { err "runtime 缺少引擎模块 ${_mod}（不要用旧 ignore 规则；请去掉 SKIP_RUNTIME 或 python3 desktop/py/build_runtime.py --app-only）"; exit 1; }
done
log "引擎能力模块校验通过: code_dev/review/commit/deploy/hitl"

# DSH 宿主必须 Node≥22；Electron 内嵌 Node 20 不够。打包时内嵌官方 Node 二进制。
NODE_RUNTIME_VER="${NODE_RUNTIME_VER:-22.23.1}"
NODE_STAGED="$ROOT/desktop/runtime/node"
stage_node_runtime() {
  local arch_node="x64"
  case "$(uname -m)" in
    arm64|aarch64) arch_node="arm64" ;;
    x86_64|amd64) arch_node="x64" ;;
  esac
  # electron-builder 当前默认打 x64 Mac；可用 NODE_RUNTIME_ARCH 覆盖
  arch_node="${NODE_RUNTIME_ARCH:-$arch_node}"
  local dest_bin="$NODE_STAGED/bin/node"
  if [[ -x "$dest_bin" ]]; then
    local maj
    maj="$("$dest_bin" -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
    if [[ "${maj:-0}" -ge 22 ]]; then
      log "复用已有内嵌 Node：$("$dest_bin" -v) ($dest_bin)"
      return 0
    fi
  fi
  rm -rf "$NODE_STAGED"
  mkdir -p "$NODE_STAGED/bin"

  # 优先本机 nvm / 同版本 node，避免每次下载
  local local_node=""
  if [[ -x "${HOME}/.nvm/versions/node/v${NODE_RUNTIME_VER}/bin/node" ]]; then
    local_node="${HOME}/.nvm/versions/node/v${NODE_RUNTIME_VER}/bin/node"
  elif command -v node >/dev/null 2>&1; then
    local v
    v="$(node -p 'process.versions.node' 2>/dev/null || true)"
    if [[ "$v" == "${NODE_RUNTIME_VER}" ]]; then
      local_node="$(command -v node)"
    fi
  fi
  if [[ -n "$local_node" && -x "$local_node" ]]; then
    # 校验 arch 大致匹配（可选）
    cp "$local_node" "$dest_bin"
    chmod +x "$dest_bin"
    log "从本机拷贝 Node → runtime/node：$("$dest_bin" -v)"
    return 0
  fi

  local tarball="node-v${NODE_RUNTIME_VER}-darwin-${arch_node}.tar.gz"
  local url="${NODE_DIST_URL:-https://nodejs.org/dist/v${NODE_RUNTIME_VER}/${tarball}}"
  local tmp
  tmp="$(mktemp -d)"
  log "下载 Node ${NODE_RUNTIME_VER} (${arch_node}) ..."
  if ! curl -fsSL "$url" -o "$tmp/$tarball"; then
    err "下载 Node 失败: $url"
    rm -rf "$tmp"
    return 1
  fi
  tar -xzf "$tmp/$tarball" -C "$tmp"
  cp "$tmp/node-v${NODE_RUNTIME_VER}-darwin-${arch_node}/bin/node" "$dest_bin"
  chmod +x "$dest_bin"
  rm -rf "$tmp"
  log "内嵌 Node 已就绪：$("$dest_bin" -v)"
}

if [[ "$MODE" == "unified" ]]; then
  if [[ "${SKIP_NODE:-0}" != "1" ]]; then
    stage_node_runtime || exit 1
  fi
  test -x "$NODE_STAGED/bin/node" || { err "缺少 desktop/runtime/node/bin/node（宿主需要 Node≥22）"; exit 1; }
  NODE_MAJ="$("$NODE_STAGED/bin/node" -p 'process.versions.node.split(".")[0]')"
  [[ "${NODE_MAJ:-0}" -ge 22 ]] || { err "内嵌 Node 主版本 ${NODE_MAJ} < 22"; exit 1; }
fi

HOST_STAGED="$ROOT/desktop/runtime/host"
# 钉与本机常用线一致；可用 DSH_NPM_VERSION 覆盖。
DSH_NPM_VERSION="${DSH_NPM_VERSION:-0.1.1-rc.2}"

stage_host_from_npm_global() {
  # 整包拷贝全局 @deepseek-ai/dsh（含其嵌套 node_modules 闭包）
  local g_root
  g_root="$(npm root -g 2>/dev/null || true)"
  local dsh_src="$g_root/@deepseek-ai/dsh"
  if [[ -z "$g_root" || ! -f "$dsh_src/package.json" ]]; then
    err "全局未安装 @deepseek-ai/dsh。请先: npm i -g @deepseek-ai/dsh@${DSH_NPM_VERSION}"
    return 1
  fi
  local ver
  ver="$(python3 -c "import json;print(json.load(open('$dsh_src/package.json'))['version'])")"
  log "从全局整包拷贝 Host: @deepseek-ai/dsh@${ver}（含嵌套依赖）"
  rm -rf "$HOST_STAGED"
  mkdir -p "$HOST_STAGED/node_modules/@deepseek-ai"
  cat > "$HOST_STAGED/package.json" <<EOF
{
  "name": "zr-workbuddy-host-runtime",
  "private": true,
  "version": "0.2.0",
  "dependencies": {
    "@deepseek-ai/dsh": "${ver}"
  }
}
EOF
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$dsh_src/" "$HOST_STAGED/node_modules/@deepseek-ai/dsh/"
  else
    cp -R "$dsh_src" "$HOST_STAGED/node_modules/@deepseek-ai/dsh"
  fi
  # 校验嵌套闭包体量（空壳约几十 K 则失败）
  local sz
  sz="$(du -sm "$HOST_STAGED/node_modules/@deepseek-ai/dsh" | awk '{print $1}')"
  if [[ "${sz:-0}" -lt 50 ]]; then
    err "Host 拷贝异常过小（${sz}M），请检查全局 dsh 安装"
    return 1
  fi
  log "Host 已就绪（约 ${sz}M）"
}

if [[ "$MODE" == "unified" ]]; then
  if [[ "$SKIP_HOST" != "1" ]]; then
    # 默认从本机全局 dsh 拷闭包（快）；HOST_FROM_GLOBAL=0 则走 npm install
    if [[ "${HOST_FROM_GLOBAL:-1}" == "1" ]]; then
      stage_host_from_npm_global
    else
      log "安装内嵌 Host CLI @deepseek-ai/dsh@${DSH_NPM_VERSION} → desktop/runtime/host/ ..."
      rm -rf "$HOST_STAGED"
      mkdir -p "$HOST_STAGED"
      cat > "$HOST_STAGED/package.json" <<EOF
{
  "name": "zr-workbuddy-host-runtime",
  "private": true,
  "version": "0.2.0",
  "dependencies": {
    "@deepseek-ai/dsh": "${DSH_NPM_VERSION}"
  }
}
EOF
      (
        cd "$HOST_STAGED"
        npm install --omit=dev --no-fund --no-audit --prefer-offline
      )
      log "Host npm 安装完成"
    fi
  fi
  test -f "$HOST_STAGED/node_modules/@deepseek-ai/dsh/lib/bin.js" \
    || { err "缺少内嵌 Host CLI（desktop/runtime/host/.../dsh/lib/bin.js）。去掉 SKIP_HOST 重跑，或先 npm i -g @deepseek-ai/dsh。"; exit 1; }
else
  log "engine-only：不打 Host；安装后若无本机 dsh 则仅引擎页"
  if [[ ! -f "$HOST_STAGED/package.json" ]]; then
    mkdir -p "$HOST_STAGED/node_modules"
    echo '{"name":"zr-workbuddy-host-placeholder","private":true}' > "$HOST_STAGED/package.json"
  fi
fi

# dsh web 设置里的「插件市场」来自社区包 dshmarket（不是官方 Desktop 插件中心）。
MARKET_VER="${MARKET_VER:-1.34.0}"
MARKET_STAGED="$ROOT/desktop/runtime/market"
stage_dshmarket() {
  local dest_pkg="$MARKET_STAGED/node_modules/dshmarket/package.json"
  local dest_client="$MARKET_STAGED/node_modules/dshmarket/client/client.js"
  if [[ "${SKIP_MARKET:-0}" == "1" && -f "$dest_pkg" && -f "$dest_client" ]]; then
    log "复用已有 dshmarket：$(python3 -c "import json;print(json.load(open('$dest_pkg'))['version'])")"
    return 0
  fi
  rm -rf "$MARKET_STAGED"
  mkdir -p "$MARKET_STAGED"
  cat > "$MARKET_STAGED/package.json" <<EOF
{
  "name": "zr-workbuddy-market-runtime",
  "private": true,
  "version": "0.2.11",
  "dependencies": {
    "dshmarket": "${MARKET_VER}"
  }
}
EOF
  log "安装内嵌插件市场 dshmarket@${MARKET_VER} → desktop/runtime/market/"
  (
    cd "$MARKET_STAGED"
    npm install --omit=dev --no-fund --no-audit
  )
  test -f "$dest_pkg" || { err "缺少 dshmarket package.json"; return 1; }
  test -f "$dest_client" || { err "缺少 dshmarket client.js"; return 1; }
  test -f "$MARKET_STAGED/node_modules/dshmarket/cordis.patch.yml" \
    || { err "缺少 dshmarket cordis.patch.yml"; return 1; }
  log "dshmarket 已就绪"
}

if [[ "$MODE" == "unified" ]]; then
  stage_dshmarket || exit 1
else
  mkdir -p "$MARKET_STAGED/node_modules"
fi

# 插件市场 / dsh plugin 需要 pnpm；一体包内嵌 Node 不可写，不能 npm i -g。
PNPM_VER="${PNPM_VER:-11.7.0}"
PNPM_STAGED="$ROOT/desktop/runtime/pnpm"
stage_pnpm() {
  local dest="$PNPM_STAGED/node_modules/pnpm/bin/pnpm.cjs"
  if [[ "${SKIP_PNPM:-0}" == "1" && -f "$dest" ]]; then
    log "复用已有 pnpm：$(python3 -c "import json;print(json.load(open('$PNPM_STAGED/node_modules/pnpm/package.json'))['version'])" 2>/dev/null || echo ok)"
    return 0
  fi
  rm -rf "$PNPM_STAGED"
  mkdir -p "$PNPM_STAGED"
  cat > "$PNPM_STAGED/package.json" <<EOF
{
  "name": "zr-workbuddy-pnpm-runtime",
  "private": true,
  "version": "0.2.13",
  "dependencies": {
    "pnpm": "${PNPM_VER}"
  }
}
EOF
  log "安装内嵌 pnpm@${PNPM_VER} → desktop/runtime/pnpm/"
  (
    cd "$PNPM_STAGED"
    npm install --omit=dev --no-fund --no-audit
  )
  test -f "$dest" || { err "缺少 pnpm.cjs"; return 1; }
  log "pnpm 已就绪"
}

if [[ "$MODE" == "unified" ]]; then
  stage_pnpm || exit 1
else
  mkdir -p "$PNPM_STAGED/node_modules/pnpm/bin"
  printf '%s\n' 'console.error("engine-only: no pnpm"); process.exit(1)' \
    > "$PNPM_STAGED/node_modules/pnpm/bin/pnpm.cjs"
fi

log "electron-builder（仅 dir+zip；DMG 自研，避开 builder 内置 UDRW+zlib 慢管线）..."
export ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}"
export ELECTRON_BUILDER_BINARIES_MIRROR="${ELECTRON_BUILDER_BINARIES_MIRROR:-https://npmmirror.com/mirrors/electron-builder-binaries/}"
export CSC_IDENTITY_AUTO_DISCOVERY="${CSC_IDENTITY_AUTO_DISCOVERY:-false}"

# 打包前语法检查，避免再把坏 main.js 打进 asar
node --check "$ROOT/desktop/main.js" || { err "desktop/main.js 语法错误"; exit 1; }
node --check "$ROOT/desktop/preload.js" || { err "desktop/preload.js 语法错误"; exit 1; }

(cd "$ROOT/desktop" && npm install)
(
  cd "$ROOT/desktop"
  if [[ -n "$EB_TARGET" ]]; then
    npx electron-builder --"$EB_TARGET"
  else
    # --mac 走 package.json mac.target = dir+zip
    npx electron-builder --mac
  fi
)

APP_BUNDLE="$ROOT/desktop/release/mac/ZR WorkBuddy.app"
ZIP_OUT="$ROOT/desktop/release/ZR WorkBuddy-${DESKTOP_VERSION}.zip"
DMG_OUT="$ROOT/desktop/release/ZR WorkBuddy-${DESKTOP_VERSION}.dmg"
test -d "$APP_BUNDLE" || { err "缺少 $APP_BUNDLE（electron-builder dir 失败）"; exit 1; }
test -f "$ZIP_OUT" || log "警告: 未找到 zip（$ZIP_OUT）；仍可继续打 DMG"

# DMG：默认跳过（本机 hdiutil 易对 ~1GB 一体包假死；zip 已够用）。
# 需要 dmg 时：MAKE_DMG=1 DMG_FORMAT=ULFO ./scripts/package-desktop.sh
SKIP_DMG="${SKIP_DMG:-1}"
if [[ "${MAKE_DMG:-0}" == "1" ]]; then
  SKIP_DMG=0
fi
DMG_OK=0
if [[ "$SKIP_DMG" == "1" ]]; then
  log "跳过 DMG（默认；主产物 zip）。需要时: MAKE_DMG=1"
else
  # 预检：15s 内打不出 1KB 测试镜像 → 认定 DiskImages 卡死，直接放弃
  PRE=$(mktemp -d "${TMPDIR:-/tmp}/wb-dmg-pre-XXXX")
  echo ok >"$PRE/a.txt"
  PRE_DMG="${TMPDIR:-/tmp}/wb-dmg-pre-$$.dmg"
  rm -f "$PRE_DMG"
  log "DMG 预检 hdiutil（15s）…"
  hdiutil create -srcfolder "$PRE" -ov -format UDRO "$PRE_DMG" &
  PRE_PID=$!
  pre_ok=0
  for _i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if ! kill -0 "$PRE_PID" 2>/dev/null; then
      wait "$PRE_PID" && pre_ok=1
      break
    fi
    sleep 1
  done
  if kill -0 "$PRE_PID" 2>/dev/null; then
    kill -9 "$PRE_PID" 2>/dev/null || true
    pkill -9 -f "hdiutil create.*wb-dmg-pre" 2>/dev/null || true
    err "hdiutil 预检超时：DiskImages 可能卡死。请执行: killall diskimages-helper；或重启后再 MAKE_DMG=1"
    pre_ok=0
  fi
  rm -rf "$PRE" "$PRE_DMG"
  if [[ "$pre_ok" == "1" ]]; then
    log "生成 DMG（DMG_FORMAT=${DMG_FORMAT:-ULFO}，超时 ${DMG_TIMEOUT_SEC:-300}s）…"
    if bash "$ROOT/scripts/lib/make_desktop_dmg.sh" \
      "$APP_BUNDLE" "$DMG_OUT" "ZR WorkBuddy ${DESKTOP_VERSION}"; then
      DMG_OK=1
    else
      err "DMG 失败或超时。可用产物: zip / release/mac/*.app"
    fi
  fi
fi

mkdir -p "$ROOT/desktop/release"
NOTE="宿主一体包（未 Apple 公证）；配置中心 / 设置填写 Key 后使用。主推 zip；dmg 为可选拖拽安装。"
if [[ "$MODE" != "unified" ]]; then
  NOTE="仅引擎壳；完整聊天需本机 dsh 或改用 unified 打包"
fi
ARTIFACTS="zip"
[[ "$DMG_OK" == "1" ]] && ARTIFACTS="zip,dmg"
cat > "$ROOT/desktop/release/build-info.json" <<EOF
{
  "product": "ZR WorkBuddy",
  "version": "${DESKTOP_VERSION}",
  "mode": "${MODE}",
  "git_commit": "${GIT_COMMIT}",
  "built_at": "${BUILD_TIME}",
  "platform": "$(uname -s)-$(uname -m)",
  "artifacts": "${ARTIFACTS}",
  "dmg_format": "${DMG_FORMAT:-ULFO}",
  "note": "${NOTE}"
}
EOF

log "完成。安装包目录: $ROOT/desktop/release"
[[ -f "$ZIP_OUT" ]] && log "主产物 zip: $ZIP_OUT ($(du -h "$ZIP_OUT" | awk '{print $1}'))"
if [[ "$DMG_OK" == "1" ]]; then
  log "DMG: $DMG_OUT ($(du -h "$DMG_OUT" | awk '{print $1}'))"
else
  log "无 DMG（可 unzip 后把 .app 拖进「应用程序」）"
fi
log "macOS 未签名：若拦截，请右键「打开」一次。"
if [[ "$MODE" == "unified" ]]; then
  log "一体包：内嵌 Host + Node≥22 + 引擎；启动用内嵌 Node 跑 dsh（勿用 Electron Node 20）。"
fi


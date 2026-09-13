#!/usr/bin/env bash
# 从已打好的 .app 生成「拖到应用程序」安装盘。
#
# 正规布局：盘里同时有 .app 和 Applications 快捷方式（指向 /Applications）。
# 禁止把该快捷方式放进 hdiutil -srcfolder：会偶发跟进整盘应用程序目录导致假死。
# 正确做法：先打可写镜像 → 挂上后再 ln -s /Applications → 再压缩。
#
# 用法:
#   make_desktop_dmg.sh <App.app> <out.dmg> [卷名]
#
# 环境变量:
#   DMG_FORMAT=ULFO|UDZO|UDRO   默认 ULFO（lzfse）
#   DMG_TIMEOUT_SEC=300         超时强杀（秒）；0=不限
#   DMG_ZLIB_LEVEL=6            仅 UDZO
set -euo pipefail

APP="${1:?用法: make_desktop_dmg.sh <App.app> <out.dmg> [volname]}"
OUT="${2:?}"
VOL="${3:-ZR WorkBuddy}"
FMT="${DMG_FORMAT:-ULFO}"
TIMEOUT_SEC="${DMG_TIMEOUT_SEC:-300}"

log() { printf '\033[1;34m[make-dmg]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[make-dmg]\033[0m %s\n' "$*" >&2; }

[[ -d "$APP" ]] || { err "缺少 .app: $APP"; exit 1; }
[[ "$APP" == *.app ]] || { err "第一个参数须是 .app 目录"; exit 1; }
APP="$(cd "$(dirname "$APP")" && pwd)/$(basename "$APP")"
APP_NAME="$(basename "$APP")"

pkill -9 -f "hdiutil create.*$(basename "$OUT" .dmg)" 2>/dev/null || true
pkill -9 -f "hdiutil convert.*$(basename "$OUT" .dmg)" 2>/dev/null || true
hdiutil detach -force "/Volumes/${VOL}" 2>/dev/null || true

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/wb-dmg-stage-XXXX")"
RW="${TMPDIR:-/tmp}/wb-dmg-rw-$$.dmg"
STARTED_AT=$SECONDS
MOUNT=""

cleanup() {
  if [[ -n "${MOUNT:-}" && -d "$MOUNT" ]]; then
    hdiutil detach -force "$MOUNT" 2>/dev/null || true
  fi
  hdiutil detach -force "/Volumes/${VOL}" 2>/dev/null || true
  rm -rf "$STAGE"
  rm -f "$RW"
}
trap cleanup EXIT

wait_pid() {
  local pid="$1" label="$2"
  while kill -0 "$pid" 2>/dev/null; do
    sleep 5
    local elapsed=$((SECONDS - STARTED_AT))
    if (( elapsed % 30 == 0 )); then
      log "进行中 ${elapsed}s（${label}）…"
    fi
    if [[ "$TIMEOUT_SEC" != "0" ]] && (( elapsed >= TIMEOUT_SEC )); then
      err "超时 ${TIMEOUT_SEC}s，强杀 ${label} pid=$pid"
      kill -9 "$pid" 2>/dev/null || true
      return 1
    fi
  done
  wait "$pid"
}

# 暂存里只放 .app，绝不放 Applications 链接
if ! cp -cR "$APP" "$STAGE/$APP_NAME" 2>/dev/null; then
  ditto "$APP" "$STAGE/$APP_NAME"
fi
log "暂存仅含 $APP_NAME（$(du -sh "$STAGE" | awk '{print $1}')）"

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT" "$RW"

log "创建可写镜像（UDRW）…"
hdiutil create -srcfolder "$STAGE" -format UDRW -volname "$VOL" -ov "$RW" &
wait_pid $! "create UDRW" || exit 1
[[ -f "$RW" ]] || { err "未生成可写镜像"; exit 1; }

ATTACH_OUT="$(hdiutil attach -readwrite -noverify -nobrowse -noautoopen "$RW")"
MOUNT="$(printf '%s\n' "$ATTACH_OUT" | sed -n 's#.*\(/Volumes/.*\)#\1#p' | tail -1)"
[[ -n "$MOUNT" && -d "$MOUNT" ]] || { err "挂载失败"; printf '%s\n' "$ATTACH_OUT" >&2; exit 1; }
[[ -d "$MOUNT/$APP_NAME" ]] || { err "镜像内缺少 $APP_NAME"; exit 1; }

# 挂载后再做快捷方式：hdiutil 不会再扫描 /Applications
rm -f "$MOUNT/Applications" "$MOUNT/应用程序"
ln -s /Applications "$MOUNT/Applications"
[[ -L "$MOUNT/Applications" ]] || { err "未能写入 Applications 快捷方式"; exit 1; }
log "已加入 Applications → /Applications"

# 图标摆放失败不阻断：有快捷方式就能拖进应用程序
osascript <<OSA 2>/dev/null || log "Finder 摆放跳过（不影响安装）"
tell application "Finder"
  tell disk "$VOL"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set bounds of container window to {360, 140, 920, 520}
    set arrangement of icon view options of container window to not arranged
    set icon size of icon view options of container window to 96
    delay 0.4
    try
      set position of item "$APP_NAME" of container window to {160, 180}
    end try
    try
      set position of item "Applications" of container window to {420, 180}
    end try
    close
    open
    update without registering applications
    delay 0.4
    close
  end tell
end tell
OSA

sync
hdiutil detach "$MOUNT"
MOUNT=""

log "压缩为 ${FMT}…"
CONVERT_ARGS=(-format "$FMT" -ov "$RW" -o "$OUT")
if [[ "$FMT" == "UDZO" ]]; then
  CONVERT_ARGS+=(-imagekey "zlib-level=${DMG_ZLIB_LEVEL:-6}")
fi
hdiutil convert "${CONVERT_ARGS[@]}" &
wait_pid $! "convert ${FMT}" || exit 1
[[ -f "$OUT" ]] || { err "未生成 $OUT"; exit 1; }

elapsed=$((SECONDS - STARTED_AT))
log "完成 $(ls -lh "$OUT" | awk '{print $5}')  约 ${elapsed}s（含 Applications 拖放安装）"
exit 0

#!/usr/bin/env bash
# 从已打好的 .app 生成 DMG —— 禁止再 ditto 全量拷贝。
#
# 用法:
#   make_desktop_dmg.sh <App.app> <out.dmg> [卷名]
#
# 环境变量:
#   DMG_FORMAT=ULFO|UDZO|UDRO   默认 ULFO（lzfse，远快于 electron-builder 的 UDZO）
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

# 清理历史卡住的同名打包
pkill -9 -f "hdiutil create.*$(basename "$OUT" .dmg)" 2>/dev/null || true
hdiutil detach -force "/Volumes/${VOL}" 2>/dev/null || true

# 直接以 .app 的父目录为源（通常是 release/mac，里面只有这一个 .app）
# 禁止 ln -s /Applications：hdiutil 偶发跟随整盘 Applications → 假死数十分钟
SRC="$(dirname "$APP")"
ONLY="$(find "$SRC" -mindepth 1 -maxdepth 1 ! -name '.DS_Store' | wc -l | tr -d ' ')"
if [[ "$ONLY" != "1" ]]; then
  # 父目录不干净时，建空暂存并用 APFS clone（写时复制，秒级），仍避免全量读写
  STAGE="$(mktemp -d "${TMPDIR:-/tmp}/wb-dmg-stage-XXXX")"
  cleanup() { rm -rf "$STAGE"; }
  trap cleanup EXIT
  if ! cp -cR "$APP" "$STAGE/$(basename "$APP")" 2>/dev/null; then
    err "父目录含多个条目且 APFS clone 失败；请保持 release/mac 下仅有 .app"
    exit 1
  fi
  SRC="$STAGE"
  log "APFS clone 暂存（父目录不干净）"
fi

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"

ARGS=(-volname "$VOL" -srcfolder "$SRC" -ov -format "$FMT")
if [[ "$FMT" == "UDZO" ]]; then
  ARGS+=(-imagekey "zlib-level=${DMG_ZLIB_LEVEL:-6}")
fi

log "格式=${FMT} 超时=${TIMEOUT_SEC}s 源=$(du -sh "$SRC" | awk '{print $1}') → $OUT"

hdiutil create "${ARGS[@]}" "$OUT" &
HPID=$!
elapsed=0
while kill -0 "$HPID" 2>/dev/null; do
  sleep 5
  elapsed=$((elapsed + 5))
  if (( elapsed % 30 == 0 )); then
    log "进行中 ${elapsed}s …"
  fi
  if [[ "$TIMEOUT_SEC" != "0" ]] && (( elapsed >= TIMEOUT_SEC )); then
    err "超时 ${TIMEOUT_SEC}s，强杀 hdiutil pid=$HPID（可改 DMG_FORMAT=UDRO 或 SKIP_DMG=1）"
    kill -9 "$HPID" 2>/dev/null || true
    pkill -9 -f "hdiutil create.*$(basename "$OUT")" 2>/dev/null || true
    rm -f "$OUT"
    exit 1
  fi
done

wait "$HPID"
EC=$?
if [[ $EC -ne 0 || ! -f "$OUT" ]]; then
  err "hdiutil 失败 exit=$EC"
  exit "${EC:-1}"
fi

log "完成 $(ls -lh "$OUT" | awk '{print $5}')  约 ${elapsed}s"
exit 0

#!/bin/bash
# 框架脚本：Cordis bridge 安装 + features 热插拔（无需重启）
#
#   scripts/plugin.sh --app <应用> list
#   scripts/plugin.sh --app <应用> install bridge|all [--restart]   # 仅常驻 bridge
#   scripts/plugin.sh --app <应用> uninstall <id|all> [--restart]
#   scripts/plugin.sh --app <应用> enable <feature-id>              # 热启用，不重启
#   scripts/plugin.sh --app <应用> disable <feature-id>             # 热停用，不重启
#   scripts/plugin.sh --app <应用> features                         # 列出 features
#   scripts/plugin.sh --app <应用> new <id> ["说明"]                # 新建 feature
#   scripts/plugin.sh --app <应用> backup|restore …
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/resolve_app.sh
. "$ROOT/scripts/lib/resolve_app.sh"
PROFILE="${DSH_PROFILE:-$HOME/.dsh/profiles/web}"
LINK_DIR="$HOME/.dsh/link"
# 仓库产品名即 link 名（勿再使用 dsh-ai-apps）
LINK_NAME="DSH-ZR-WorkBuddy"
LINK_REPO="$LINK_DIR/$LINK_NAME"
BAK_ROOT="$HOME/.dsh/profiles/web.bak"
APP=""
DO_RESTART=0
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --app) APP="${2:?}"; shift 2 ;;
    --restart) DO_RESTART=1; shift ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
set -- "${ARGS[@]}"
CMD="${1:?用法: plugin.sh --app <应用名> list|install|uninstall|enable|disable|features|new|backup|restore ...}"
shift || true

[ -n "$APP" ] || APP="zr-workbuddy"
APP="$(resolve_app_name "$APP")"
APP_ROOT="$ROOT/apps/$APP"
PLUGINS="$APP_ROOT/plugins"
FEATURES="$APP_ROOT/features"
ENGINE="$APP_ROOT/engine"
[ -d "$PLUGINS" ] || { echo "找不到 $PLUGINS"; exit 1; }

ensure_repo_link() {
  mkdir -p "$LINK_DIR"
  ln -sfn "$ROOT" "$LINK_REPO"
  # 清理旧仓库 link 名，避免 DSH 仍指向 dsh-ai-apps
  if [ -L "$LINK_DIR/dsh-ai-apps" ] || [ -e "$LINK_DIR/dsh-ai-apps" ]; then
    rm -f "$LINK_DIR/dsh-ai-apps"
  fi
}

plugin_link_spec() {
  local ID="$1"
  echo "link:../../link/$LINK_NAME/apps/$APP/plugins/$ID"
}

engine_base() {
  # 勿在 bash 单引号里写 d[\"host\"]：Python 会收到字面量反斜杠导致 SyntaxError
  python3 "$ROOT/scripts/lib/read_runtime.py" "$ENGINE" | python3 -c 'import json,sys;d=json.load(sys.stdin);print("http://%s:%s"%(d["host"],d["port"]))'
}

backup_profile() {
  ensure_repo_link
  local stamp dest
  stamp="$(date +%Y%m%d-%H%M%S)"
  dest="$BAK_ROOT/$stamp"
  mkdir -p "$dest"
  [ -f "$PROFILE/package.json" ] && cp "$PROFILE/package.json" "$dest/"
  [ -f "$PROFILE/cordis.patch.yml" ] && cp "$PROFILE/cordis.patch.yml" "$dest/"
  echo "$dest" > "$BAK_ROOT/LATEST"
  echo "已备份 profile → $dest"
}

is_cordis_plugin() {
  local DIR="$1"
  python3 - "$DIR" <<'PY'
import json, os, sys
d = sys.argv[1]
p = os.path.join(d, "package.json")
if not os.path.isfile(p):
    raise SystemExit(1)
meta = json.load(open(p))
dsh = meta.get("dshApp") or {}
if dsh.get("deprecated") is True:
    raise SystemExit(1)
if dsh.get("cordisPlugin") is False:
    raise SystemExit(1)
if dsh.get("cordisPlugin") is True:
    raise SystemExit(0)
name = meta.get("name") or ""
if name.endswith("-runtime") or "runtime" == os.path.basename(d):
    raise SystemExit(1)
raise SystemExit(0 if os.path.isfile(os.path.join(d, "lib", "index.js")) else 1)
PY
}

list_plugin_ids() {
  local ids=()
  for d in "$PLUGINS"/*/; do
    [ -d "$d" ] || continue
    local id; id="$(basename "$d")"
    if is_cordis_plugin "$d"; then
      ids+=("$id")
    fi
  done
  echo "${ids[@]}"
}

resolve_ids() {
  local out=()
  for a in "$@"; do
    case "$a" in --restart) continue ;; esac
    if [ "$a" = "all" ] || [ "$a" = "bridge" ]; then
      # shellcheck disable=SC2207
      out=($(list_plugin_ids))
      break
    fi
    out+=("$a")
  done
  echo "${out[@]}"
}

sync_panel_defaults() {
  local CLIENT="$PLUGINS/mes-bridge/lib/client.js"
  [ -f "$CLIENT" ] || return 0
  local HOST PORT _RT
  _RT="$(python3 "$ROOT/scripts/lib/read_runtime.py" "$ENGINE")"
  HOST="$(printf '%s' "$_RT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["host"])')"
  PORT="$(printf '%s' "$_RT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["port"])')"
  python3 - "$CLIENT" "$HOST" "$PORT" <<'PY'
import re, sys
path, host, port = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()
block = (
    "/*RUNTIME_BEGIN*/\n"
    f'window.__APP_ENGINE__ = {{ host: "{host}", port: {port} }};\n'
    "/*RUNTIME_END*/"
)
text2, n = re.subn(
    r"/\*RUNTIME_BEGIN\*/.*?/\*RUNTIME_END\*/",
    block,
    text,
    count=1,
    flags=re.S,
)
if n == 0:
    print("未找到 RUNTIME 块，跳过同步", file=sys.stderr)
else:
    open(path, "w", encoding="utf-8").write(text2)
    print(f"已同步面板引擎地址 → {host}:{port}")
PY
}

maybe_restart() {
  if [ "$DO_RESTART" = "1" ]; then
    echo "正在重启 DSH…"
    "$ROOT/scripts/restart-dsh.sh"
  else
    echo
    echo "（仅 bridge 变更需要重启）生效: scripts/restart-dsh.sh 或加 --restart"
  fi
}

install_one() {
  local ID="$1"
  local DIR="$PLUGINS/$ID"
  [ -d "$DIR" ] || { echo "找不到 $DIR"; return 1; }
  [ -f "$DIR/package.json" ] || { echo "$DIR 缺 package.json"; return 1; }
  if ! is_cordis_plugin "$DIR"; then
    echo "跳过 $ID（非常驻 Cordis 包 / 已废弃）"
    return 0
  fi
  ensure_repo_link
  # 安装前对齐 dsh-tools realpath，避免 prepare undefined
  if [ -x "$ROOT/scripts/check-vendor.sh" ]; then
    "$ROOT/scripts/check-vendor.sh" --fix || true
  fi
  local PKG_NAME PKG_ID LINK_SPEC
  PKG_NAME="$(python3 -c "import json;print(json.load(open('$DIR/package.json'))['name'])")"
  PKG_ID="${PKG_NAME##*/}"
  LINK_SPEC="$(plugin_link_spec "$ID")"

  cd "$DIR"
  if command -v pnpm >/dev/null 2>&1; then
    pnpm install 2>/dev/null || pnpm install
  fi

  python3 - "$PKG_NAME" "$LINK_SPEC" "$PROFILE" "$PKG_ID" <<'PY'
import json, os, sys
name, link, profile, pid = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
p = os.path.join(profile, "package.json")
d = json.load(open(p))
d.setdefault("dependencies", {})[name] = link
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
print("依赖:", name, "→", link)
patch = os.path.join(profile, "cordis.patch.yml")
src = open(patch, encoding="utf-8").read()
if f"id: {pid}" in src:
    print("patch 已有", pid); raise SystemExit(0)
block = (f"\n# --- {pid}（apps bridge） ---\n- insert:\n"
         f"    - id: {pid}\n      name: '{name}'\n")
marker = "# --- dsh-skin managed"
src = src.replace(marker, block + marker) if marker in src else src + block
open(patch, "w", encoding="utf-8").write(src)
print("patch insert:", pid)
# 清理误导项：disabled + id 写成 npm 全名（与 insert 短 id 对不上）
import re
src2 = open(patch, encoding="utf-8").read()
pat = re.compile(
    rf'\n- id: ["\']{re.escape(name)}["\']\n  name: ["\']{re.escape(name)}["\']\n  disabled: true\n?',
)
src3, n = pat.subn("\n", src2)
if n:
    open(patch, "w", encoding="utf-8").write(src3)
    print("已清理无效 disabled 行:", name)
PY
  echo "✅ [$APP] 已安装常驻包 $ID"
}

uninstall_one() {
  local ID="$1"
  local DIR="$PLUGINS/$ID"
  # 也允许按旧包名卸载（即使已 deprecated）
  local PKG_JSON="$DIR/package.json"
  if [ ! -f "$PKG_JSON" ]; then
    # 尝试按 npm 短名在 profile 清理
    echo "本地无 $DIR，尝试按 id 清理 profile: $ID"
    python3 - "$ID" "$PROFILE" <<'PY'
import json, os, re, sys
pid, profile = sys.argv[1], sys.argv[2]
# soft: remove deps whose name ends with pid
p = os.path.join(profile, "package.json")
d = json.load(open(p))
deps = d.get("dependencies") or {}
rm=[k for k in list(deps) if k.endswith('/'+pid) or k.endswith(pid)]
for k in rm:
    del deps[k]; print("移除依赖:", k)
json.dump(d, open(p,"w"), ensure_ascii=False, indent=2)
patch=os.path.join(profile,"cordis.patch.yml")
src=open(patch,encoding="utf-8").read()
# remove insert blocks mentioning pid
lines=src.splitlines(True); out=[]; i=0
while i < len(lines):
    if f"id: {pid}" in lines[i] or f"dsh-{pid}" in lines[i]:
        while out and (out[-1].lstrip().startswith("- insert") or out[-1].startswith("# ---")):
            out.pop()
        i+=1
        if i < len(lines) and "name:" in lines[i]: i+=1
        continue
    out.append(lines[i]); i+=1
open(patch,"w",encoding="utf-8").write("".join(out))
print("patch 已清理提及", pid)
PY
    return 0
  fi
  local PKG_NAME PKG_ID
  PKG_NAME="$(python3 -c "import json;print(json.load(open('$PKG_JSON'))['name'])")"
  PKG_ID="${PKG_NAME##*/}"
  python3 - "$PKG_NAME" "$PKG_ID" "$PROFILE" <<'PY'
import json, os, re, sys
name, pid, profile = sys.argv[1], sys.argv[2], sys.argv[3]
p = os.path.join(profile, "package.json")
d = json.load(open(p))
deps = d.get("dependencies") or {}
if name in deps:
    del deps[name]
    print("移除依赖:", name)
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
patch = os.path.join(profile, "cordis.patch.yml")
src = open(patch, encoding="utf-8").read()
pat = re.compile(
    rf"\n?# --- {re.escape(pid)}[^\n]*\n- insert:\n(?:    - id: {re.escape(pid)}\n      name: '[^']*'\n)+",
    re.M,
)
new, n = pat.subn("\n", src)
if n == 0:
    lines = src.splitlines(True)
    out, i = [], 0
    while i < len(lines):
        if f"id: {pid}" in lines[i]:
            while out and (out[-1].lstrip().startswith("- insert") or out[-1].startswith("# ---")):
                out.pop()
            i += 1
            if i < len(lines) and "name:" in lines[i]:
                i += 1
            continue
        out.append(lines[i]); i += 1
    new = "".join(out)
open(patch, "w", encoding="utf-8").write(new)
print("patch 已清理:", pid)
PY
  echo "✅ [$APP] 已卸载 $ID"
}

http_plugins() {
  local METHOD="$1" PATH_SUFFIX="$2" BODY="${3:-}"
  local BASE TMP CODE
  BASE="$(engine_base)"
  TMP="$(mktemp)"
  if [ -n "$BODY" ]; then
    CODE="$(curl -sS -o "$TMP" -w '%{http_code}' -X "$METHOD" "$BASE$PATH_SUFFIX" \
      -H 'Content-Type: application/json' -d "$BODY" 2>/dev/null || echo 000)"
  else
    CODE="$(curl -sS -o "$TMP" -w '%{http_code}' -X "$METHOD" "$BASE$PATH_SUFFIX" 2>/dev/null || echo 000)"
  fi
  if [ "$CODE" != "200" ]; then
    rm -f "$TMP"
    echo "引擎 API 不可用 ($BASE$PATH_SUFFIX → HTTP $CODE)，回退写本地 plugins.json" >&2
    return 2
  fi
  cat "$TMP"; echo
  rm -f "$TMP"
  return 0
}

write_state_local() {
  local ACTION="$1" FID="$2"
  # 与引擎 / bridge 同一写路径：app.plugins_store（flock + atomic）
  (cd "$ENGINE" && python3 -m app.plugins_store "$ACTION" "$FID")
}

case "$CMD" in
  list)
    ensure_repo_link
    echo "应用: $APP"
    echo "常驻 Cordis 包（需重启一次）:"
    for id in $(list_plugin_ids); do
      name="$(python3 -c "import json;print(json.load(open('$PLUGINS/$id/package.json'))['name'])")"
      echo "  $id  →  $name"
    done
    echo "热插拔 features（无需重启）:"
    if [ -d "$FEATURES" ]; then
      for d in "$FEATURES"/*/; do
        [ -f "${d}index.js" ] || continue
        id="$(basename "$d")"
        echo "  $id"
      done
    else
      echo "  （无 features/）"
    fi
    echo
    "$ROOT/scripts/engine.sh" "$APP" status || true
    ;;

  features)
    "$ROOT/scripts/engine.sh" "$APP" ensure >/dev/null || true
    http_plugins GET /api/plugins || {
      python3 - "$FEATURES" "$ENGINE/data/plugins.json" <<'PY'
import json,os,sys
feat,path=sys.argv[1:3]
enabled=[]
if os.path.isfile(path):
  try: enabled=json.load(open(path)).get("enabled") or []
  except Exception: pass
print("enabled:", ", ".join(enabled) or "(无)")
for name in sorted(os.listdir(feat) if os.path.isdir(feat) else []):
  if os.path.isfile(os.path.join(feat,name,"index.js")):
    flag="ON " if name in enabled else "off"
    print(f"  [{flag}] {name}")
PY
      exit 0
    }
    echo
    ;;

  enable)
    FID="${1:?用法: plugin.sh --app $APP enable <feature-id>}"
    "$ROOT/scripts/engine.sh" "$APP" ensure >/dev/null || true
    if ! http_plugins POST /api/plugins/enable "{\"id\":\"$FID\"}"; then
      write_state_local enable "$FID"
    fi
    echo
    echo "✅ 已请求启用 $FID（bridge ~1s 内热加载，无需重启）"
    ;;

  disable)
    FID="${1:?用法: plugin.sh --app $APP disable <feature-id>}"
    "$ROOT/scripts/engine.sh" "$APP" ensure >/dev/null || true
    if ! http_plugins POST /api/plugins/disable "{\"id\":\"$FID\"}"; then
      write_state_local disable "$FID"
    fi
    echo
    echo "✅ 已请求停用 $FID（bridge ~1s 内热卸载，无需重启）"
    ;;

  backup)
    backup_profile
    ;;

  restore)
    ensure_repo_link
    local_bak="${1:-}"
    if [ -z "$local_bak" ] && [ -f "$BAK_ROOT/LATEST" ]; then
      local_bak="$(cat "$BAK_ROOT/LATEST")"
    elif [ -n "$local_bak" ] && [ ! -d "$local_bak" ]; then
      local_bak="$BAK_ROOT/$local_bak"
    fi
    [ -d "$local_bak" ] || { echo "找不到备份"; exit 1; }
    [ -f "$local_bak/package.json" ] && cp "$local_bak/package.json" "$PROFILE/"
    [ -f "$local_bak/cordis.patch.yml" ] && cp "$local_bak/cordis.patch.yml" "$PROFILE/"
    cd "$PROFILE" && pnpm install
    echo "✅ 已从 $local_bak 恢复"
    maybe_restart
    ;;

  install)
    [ $# -ge 1 ] || { echo "用法: plugin.sh --app $APP install bridge|all [--restart]"; exit 1; }
    # 无完整 DSH profile 时拒绝：避免在共享机造半残 ~/.dsh 或误改其它服务环境
    if [ ! -f "$PROFILE/package.json" ]; then
      echo "拒绝安装：缺少 DSH profile → $PROFILE/package.json" >&2
      echo "本机请先按 DSH 文档初始化 profiles/web；共享部署机请勿跑 install bridge。" >&2
      exit 1
    fi
    backup_profile
    for id in $(resolve_ids "$@"); do
      install_one "$id"
    done
    sync_panel_defaults
    cd "$PROFILE" && pnpm install
    # bridge 变更需要重启一次
    DO_RESTART="${DO_RESTART:-0}"
    maybe_restart
    ;;

  uninstall)
    [ $# -ge 1 ] || { echo "用法: plugin.sh --app $APP uninstall <id|all> [--restart]"; exit 1; }
    backup_profile
    if [ "$1" = "legacy" ]; then
      # 卸掉旧的正式功能包
      for id in mes-ask mes-config mes-panel; do
        uninstall_one "$id" || true
      done
    else
      for id in $(resolve_ids "$@"); do
        uninstall_one "$id"
      done
    fi
    cd "$PROFILE" && pnpm install
    maybe_restart
    ;;

  new)
    ID="${1:?用法: plugin.sh --app $APP new <id> [说明]}"
    DESC="${2:-功能 $ID}"
    if ! [[ "$ID" =~ ^[a-z][a-z0-9_-]*$ ]]; then
      echo "id 须小写字母开头 [a-z0-9_-]"; exit 1
    fi
    DIR="$FEATURES/$ID"
    [ -e "$DIR" ] && { echo "已存在 $DIR"; exit 1; }
    mkdir -p "$DIR"
    cat > "$DIR/manifest.json" <<JSON
{
  "id": "$ID",
  "name": "$DESC",
  "purpose": "$DESC"
}
JSON
    cat > "$DIR/index.js" <<'JS'
/**
 * 热插拔 feature（无 import；经 ctx.get('mesEngine') 取能力）
 */
export const name = "FEATURE_ID";
export const inject = ["tools"];
// 若调用 eng.attachChart(ctx, …) 出图，必须改为:
// export const inject = ["tools", "attachments"];
// 且 attachChart 内部只用 ctx.get("attachments")，勿写 ctx.attachments。

export function apply(ctx) {
  const eng = ctx.get("mesEngine");
  if (!eng) {
    console.error("[FEATURE_ID] mesEngine 未提供");
    return;
  }
  ctx.tools.register(
    eng.defineTool({
      name: "app_FEATURE_SAFE",
      description: "FEATURE_DESC",
      parameters: {
        input: { type: "string", description: "输入" },
      },
      output: {
        schema: { type: "object", additionalProperties: true },
        render: eng.resultRender,
      },
      async execute(args) {
        return { ok: true, reply: "TODO: " + String(args.input || "") };
      },
    }),
  );
}
JS
    SAFE="${ID//-/_}"
    python3 - "$DIR/index.js" "$ID" "$SAFE" "$DESC" <<'PY'
import sys
path, fid, safe, desc = sys.argv[1:5]
t=open(path,encoding="utf-8").read()
t=t.replace("FEATURE_ID", fid).replace("FEATURE_SAFE", safe).replace("FEATURE_DESC", desc)
open(path,"w",encoding="utf-8").write(t)
PY
    # 默认启用：走与 enable 相同路径，立刻出现在「功能插件」管理页
    if ! http_plugins POST /api/plugins/enable "{\"id\":\"$ID\"}"; then
      write_state_local enable "$ID" >/dev/null || true
    fi
    echo "✅ 已创建热插拔 feature $DIR（已加入功能插件管理，默认开启）"
    echo "编辑 $DIR/index.js 后约 1s 热加载；启停：scripts/plugin.sh --app $APP enable|disable $ID"
    echo "管理页：引擎 SPA → 功能插件（自动列出 features/，无需改前端）"
    ;;

  *)
    echo "未知命令: $CMD"; exit 1
    ;;
esac

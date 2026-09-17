# shellcheck shell=bash
# 公司 DSH 插件市场：公司目录为公司插件真相源；官方目录每天最多合并一次。
# 不改 mes-bridge / features / 引擎。
#
# 【LOCKED · 不可削弱】WorkBuddy 交付态默认强制合并市场；禁止靠置空 DSHM_REGISTRY_URL=
# 静默掉回官方。唯一破窗：WORKBUDDY_ALLOW_OFFICIAL_MARKET=1（调试专用，不得发版）。
# 规则：.cursor/rules/workbuddy-company-market.mdc
#
# 用法（由 host.sh / restart-dsh.sh source）：
#   . "$ROOT/scripts/lib/company_dsh_market.sh"
#   apply_company_dsh_market

company_dsh_market_config() {
  echo "${COMPANY_DSH_MARKET_ENV:-$ROOT/apps/zr-workbuddy/config/company-dsh-market.env}"
}

_company_catalog_url() {
  echo "${COMPANY_DSH_MARKET_URL:-http://175.178.238.31/dsh-plugins/plugins.json}"
}

_company_allow_official_market() {
  [ "${WORKBUDDY_ALLOW_OFFICIAL_MARKET:-}" = "1" ]
}

# 写入 .env 前消毒：禁止换行/空格，仅允许 http(s) URL，防 .env 注入
_sanitize_dshm_registry_url() {
  local raw="$1"
  raw="$(printf '%s' "$raw" | tr -d '\r\n\t ' )"
  case "$raw" in
    http://127.0.0.1:*|http://localhost:*|https://127.0.0.1:*|https://localhost:*)
      printf '%s' "$raw"
      return 0
      ;;
    http://175.178.238.31/*|https://*)
      # 公司站或显式 https 自定义目录
      printf '%s' "$raw"
      return 0
      ;;
  esac
  return 1
}

# 从配置文件加载缺省值（不覆盖已存在的环境变量）
load_company_dsh_market_env() {
  local cfg
  cfg="$(company_dsh_market_config)"
  [ -f "$cfg" ] || return 0
  local line key val
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|\#*) continue ;;
    esac
    key="${line%%=*}"
    val="${line#*=}"
    key="$(printf '%s' "$key" | sed 's/[[:space:]]*$//')"
    case "$key" in
      DSHM_REGISTRY_URL|ZHONGRUAN_NPM_REGISTRY|COMPANY_DSH_MARKET_URL|OFFICIAL_DSH_MARKET_URL|WORKBUDDY_MARKET_MERGE_PORT) ;;
      *) continue ;;
    esac
    # 已设置则跳过（含用户主动 export）
    if [ -n "${!key+x}" ]; then
      continue
    fi
    export "$key=$val"
  done < "$cfg"
}

_company_dsh_home() {
  # host.sh 会 export DSH_HOME；裸默认与本机开发壳一致用 ~/.dsh
  printf '%s' "${DSH_HOME:-$HOME/.dsh}"
}

_company_dsh_default_profile() {
  local home
  home="$(_company_dsh_home)"
  if [ -n "${DSH_PROFILE:-}" ]; then
    case "$DSH_PROFILE" in
      /*|~*) printf '%s' "${DSH_PROFILE/#\~/$HOME}" ;;
      *) printf '%s' "$home/profiles/$DSH_PROFILE" ;;
    esac
  else
    printf '%s' "$home/profiles/web"
  fi
}

ensure_zhongruan_npmrc() {
  local profile="${1:-$(_company_dsh_default_profile)}"
  local registry="${ZHONGRUAN_NPM_REGISTRY:-}"
  [ -n "$registry" ] || return 0
  [ -d "$profile" ] || return 0

  local npmrc="$profile/.npmrc"
  local tmp
  tmp="$(mktemp)"
  if [ -f "$npmrc" ]; then
    awk '
      BEGIN { skip=0 }
      /^# --- company-dsh-market ---$/ { skip=1; next }
      /^# --- \/company-dsh-market ---$/ { skip=0; next }
      skip==0 { print }
    ' "$npmrc" >"$tmp"
  else
    : >"$tmp"
  fi
  {
    cat "$tmp"
    [ -s "$tmp" ] && [ "$(tail -c1 "$tmp" | wc -l)" -eq 0 ] && echo
    echo "# --- company-dsh-market ---"
    echo "@zhongruan:registry=${registry}"
    echo "strict-ssl=false"
    echo "# --- /company-dsh-market ---"
  } >"$npmrc"
  rm -f "$tmp"
}

# 持久化到 $DSH_HOME/.env：裸 `dsh web` 也会经 loadLayeredEnv 读到（DSHM_ 不在 bootstrap 禁写前缀）
ensure_dshm_registry_in_dsh_home_env() {
  local home envf url tmp
  home="$(_company_dsh_home)"
  [ -d "$home" ] || mkdir -p "$home" || return 0
  envf="$home/.env"
  url="${DSHM_REGISTRY_URL:-}"
  if [ -n "$url" ]; then
    if ! url="$(_sanitize_dshm_registry_url "$url")"; then
      echo "拒绝写入非法 DSHM_REGISTRY_URL（须为 http(s) 且无空白/换行）: ${DSHM_REGISTRY_URL}" >&2
      return 1
    fi
  fi

  tmp="$(mktemp)"
  if [ -f "$envf" ]; then
    awk '
      BEGIN { skip=0 }
      /^# --- workbuddy-company-market ---$/ { skip=1; next }
      /^# --- \/workbuddy-company-market ---$/ { skip=0; next }
      skip==0 { print }
    ' "$envf" >"$tmp"
  else
    : >"$tmp"
  fi

  if [ -z "$url" ]; then
    if ! _company_allow_official_market; then
      # LOCKED：无破窗时禁止清掉持久化块
      rm -f "$tmp"
      echo "拒绝清除 $envf 市场块：未设置 WORKBUDDY_ALLOW_OFFICIAL_MARKET=1" >&2
      return 1
    fi
    {
      cat "$tmp"
      [ -s "$tmp" ] && [ "$(tail -c1 "$tmp" | wc -l)" -eq 0 ] && echo
    } >"$envf"
    rm -f "$tmp"
    echo "已从 $envf 清除 WorkBuddy 市场目录块（破窗：官方市场）"
    return 0
  fi

  {
    cat "$tmp"
    [ -s "$tmp" ] && [ "$(tail -c1 "$tmp" | wc -l)" -eq 0 ] && echo
    echo "# --- workbuddy-company-market ---"
    echo "# LOCKED by WorkBuddy — 勿手删；改市场须走 scripts/host.sh + 破窗变量"
    echo "DSHM_REGISTRY_URL=${url}"
    echo "# --- /workbuddy-company-market ---"
  } >"$envf"
  rm -f "$tmp"
  echo "已持久化市场目录 → $envf"
}

# LOCKED：默认永不跳过合并。仅破窗变量允许回官方。
_skip_market_merge() {
  if ! _company_allow_official_market; then
    # 置空 / 误 export 一律打回，强制合并
    if [ -n "${DSHM_REGISTRY_URL+x}" ] && [ -z "$DSHM_REGISTRY_URL" ]; then
      echo "忽略空的 DSHM_REGISTRY_URL=（交付态禁止掉回官方；破窗请设 WORKBUDDY_ALLOW_OFFICIAL_MARKET=1）" >&2
      unset DSHM_REGISTRY_URL
    fi
    return 1
  fi
  # 破窗：空值 = 明确要官方
  if [ -n "${DSHM_REGISTRY_URL+x}" ] && [ -z "$DSHM_REGISTRY_URL" ]; then
    return 0
  fi
  return 1
}

ensure_merged_company_dsh_market() {
  local py="$ROOT/scripts/lib/merge_company_dsh_market.py"
  [ -f "$py" ] || {
    echo "缺少合并脚本: $py" >&2
    return 1
  }
  if _skip_market_merge; then
    unset DSHM_REGISTRY_URL
    return 0
  fi
  local cache home url
  local -a extra=()
  home="$(_company_dsh_home)"
  cache="${WORKBUDDY_MARKET_MERGE_DIR:-$home/market-merge}"
  if [ -n "${WORKBUDDY_MARKET_MERGE_PORT:-}" ]; then
    extra+=(--port "$WORKBUDDY_MARKET_MERGE_PORT")
  fi
  url="$(
    python3 "$py" ensure \
      --root "$ROOT" \
      --cache-dir "$cache" \
      --company-url "$(_company_catalog_url)" \
      --official-url "${OFFICIAL_DSH_MARKET_URL:-https://awesome-dsh-plugin.com/plugins.json}" \
      "${extra[@]}" \
      | sed -n 's/^DSHM_REGISTRY_URL=//p' | tail -1
  )" || true
  if [ -n "$url" ]; then
    if ! url="$(_sanitize_dshm_registry_url "$url")"; then
      echo "合并结果 URL 非法，回退公司站" >&2
      url=""
    else
      export DSHM_REGISTRY_URL="$url"
      return 0
    fi
  fi
  # 合并服务没起来 / URL 非法时仍指向公司站，保证公司插件可装
  export DSHM_REGISTRY_URL="$(_company_catalog_url)"
}

# 返回 0=交付可用；非 0=禁止启动宿主
apply_company_dsh_market() {
  load_company_dsh_market_env
  if ! ensure_merged_company_dsh_market; then
    echo "公司插件市场合并失败" >&2
    return 1
  fi
  if [ -z "${DSHM_REGISTRY_URL:-}" ]; then
    if _company_allow_official_market; then
      echo "插件市场目录: （破窗）dshmarket 默认官方"
      ensure_dshm_registry_in_dsh_home_env || true
      ensure_zhongruan_npmrc "$(_company_dsh_default_profile)"
      return 0
    fi
    echo "LOCKED：未得到 DSHM_REGISTRY_URL，拒绝以官方市场启动 WorkBuddy" >&2
    return 1
  fi
  echo "插件市场目录: $DSHM_REGISTRY_URL"
  ensure_dshm_registry_in_dsh_home_env || return 1
  ensure_zhongruan_npmrc "$(_company_dsh_default_profile)"
  return 0
}

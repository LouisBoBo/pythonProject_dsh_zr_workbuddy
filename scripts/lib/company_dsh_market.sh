# shellcheck shell=bash
# 公司 DSH 插件市场：仅设置市场目录 URL + profile 里 @zhongruan 私有 npm。
# 不改 mes-bridge / features / 引擎；已有环境变量优先，不覆盖用户显式配置。
#
# 用法（由 host.sh / restart-dsh.sh source）：
#   . "$ROOT/scripts/lib/company_dsh_market.sh"
#   apply_company_dsh_market

company_dsh_market_config() {
  echo "${COMPANY_DSH_MARKET_ENV:-$ROOT/apps/zr-workbuddy/config/company-dsh-market.env}"
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
      DSHM_REGISTRY_URL|ZHONGRUAN_NPM_REGISTRY) ;;
      *) continue ;;
    esac
    # 已设置则跳过（含用户主动 export）
    if [ -n "${!key+x}" ]; then
      continue
    fi
    export "$key=$val"
  done < "$cfg"
}

# 只重写标记块内的行，其它 .npmrc 内容原样保留
_company_dsh_default_profile() {
  # 与 host/plugin 默认一致：WorkBuddy 家目录
  local home="${DSH_HOME:-$HOME/.dsh-workbuddy}"
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
    # 保证文件末尾换行
    [ -s "$tmp" ] && [ "$(tail -c1 "$tmp" | wc -l)" -eq 0 ] && echo
    echo "# --- company-dsh-market ---"
    echo "@zhongruan:registry=${registry}"
    echo "strict-ssl=false"
    echo "# --- /company-dsh-market ---"
  } >"$npmrc"
  rm -f "$tmp"
}

apply_company_dsh_market() {
  load_company_dsh_market_env
  if [ -n "${DSHM_REGISTRY_URL:-}" ]; then
    echo "公司插件市场目录: $DSHM_REGISTRY_URL"
  fi
  ensure_zhongruan_npmrc "$(_company_dsh_default_profile)"
}

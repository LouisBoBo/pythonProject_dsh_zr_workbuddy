# WorkBuddy 聊天壳环境（host.sh / plugin.sh / restart-dsh.sh 共用）
# shellcheck shell=bash

# WorkBuddy 与会话/工作区共用 ~/.dsh（用户项目在这里）；干净官方壳用 ~/.dsh-workbuddy :3080
apply_workbuddy_dsh_home() {
  DSH_HOME_DIR="${DSH_HOME:-$HOME/.dsh}"
  export DSH_HOME="$DSH_HOME_DIR"
}

# pnpm 11 / dsh 需要 Node 22+；避免误用 PATH 里的 Node 20
prepend_workbuddy_node_path() {
  local dsh_bin node_bin c
  dsh_bin="$(command -v dsh 2>/dev/null || true)"
  if [ -n "$dsh_bin" ]; then
    node_bin="$(dirname "$dsh_bin")"
    if [ -x "$node_bin/node" ]; then
      export PATH="$node_bin${PATH:+:$PATH}"
      return 0
    fi
  fi
  for c in \
    "$HOME/.nvm/versions/node/v22.23.1/bin" \
    "$HOME/.nvm/versions/node/current/bin"; do
    if [ -x "$c/node" ]; then
      export PATH="$c${PATH:+:$PATH}"
      return 0
    fi
  done
}

# 开发态 :3081 须跟 runtime.yaml 对齐；勿继承桌面 App 注入的 18000
sync_dev_engine_env() {
  local root="${WORKBUDDY_ROOT:-}"
  if [ -z "$root" ]; then
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    root="$here"
  fi
  unset WORKBUDDY_DESKTOP DSH_DESKTOP WORKBUDDY_ENGINE_DIR \
    WORKBUDDY_ENGINE_HOST WORKBUDDY_ENGINE_PORT \
    APP_ENGINE_HOST APP_ENGINE_PORT APP_ENGINE_PYTHON || true
  local rt
  rt="$(python3 "$root/scripts/lib/read_runtime.py" "$root/apps/zr-workbuddy/engine" 2>/dev/null || true)"
  if [ -n "$rt" ]; then
    export APP_ENGINE_HOST="$(printf '%s' "$rt" | python3 -c 'import json,sys;print(json.load(sys.stdin)["host"])')"
    export APP_ENGINE_PORT="$(printf '%s' "$rt" | python3 -c 'import json,sys;print(json.load(sys.stdin)["port"])')"
    export APP_ENGINE_PYTHON="$(printf '%s' "$rt" | python3 -c 'import json,sys;print(json.load(sys.stdin)["python"])')"
  fi
}

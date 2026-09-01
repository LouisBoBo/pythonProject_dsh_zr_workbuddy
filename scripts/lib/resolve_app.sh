# 应用名解析（框架内部）
# 旧名 mes-analytics → 新名 zr-workbuddy；供 engine.sh / plugin.sh / test.sh / start-engine.sh 共用。
resolve_app_name() {
  local a="${1:?}"
  case "$a" in
    mes-analytics)
      echo "⚠️  应用已更名为 zr-workbuddy（旧名 mes-analytics 仍兼容一次）" >&2
      echo "zr-workbuddy"
      ;;
    *)
      echo "$a"
      ;;
  esac
}

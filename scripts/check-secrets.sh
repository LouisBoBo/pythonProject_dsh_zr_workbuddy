#!/bin/bash
# 密钥卫生：拒绝把真实 config.yaml / 常见密钥模式提交进仓库
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BAD=0
IS_GIT=0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 && IS_GIT=1

if [ "$IS_GIT" = "1" ]; then
  while IFS= read -r f; do
    echo "❌ 已跟踪敏感文件: $f"
    BAD=1
  done < <(git ls-files '**/config.yaml' '**/.env' '**/credentials.json' 2>/dev/null || true)
fi

# 工作区 config.yaml：须匹配仓库 .gitignore 约定
for f in apps/*/engine/config/config.yaml; do
  [ -f "$f" ] || continue
  if [ "$IS_GIT" = "1" ]; then
    if git check-ignore -q "$f" 2>/dev/null; then
      echo "ok ignore: $f"
    else
      echo "❌ $f 未被 gitignore"
      BAD=1
    fi
  else
    # 非 git 仓库：核对 .gitignore 是否含约定规则
    if grep -qE 'engine/config/config\.yaml|\*\*/engine/config/config\.yaml' .gitignore 2>/dev/null; then
      echo "ok ignore rule (no git): $f"
    else
      echo "❌ .gitignore 缺少 config.yaml 规则"
      BAD=1
    fi
  fi
done

if [ "$IS_GIT" = "1" ]; then
  while IFS= read -r hit; do
    [ -z "$hit" ] && continue
    echo "⚠️ 疑似密钥片段: $hit"
    BAD=1
  done < <(git grep -nE 'sk-[a-zA-Z0-9]{20,}|api_key:\s*["'\''][^"'\'']{8,}' -- '*.yaml' '*.yml' '*.json' '*.md' '*.js' '*.py' 2>/dev/null | grep -v 'config.example' | grep -v '示例' | head -20 || true)
fi

if [ "$BAD" -ne 0 ]; then
  echo "check-secrets: 发现问题（见上）"
  exit 1
fi
echo "check-secrets: 通过"

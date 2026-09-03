"""人触发提交：在工作分支 commit / push（不经模型执行）。"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

_PROTECTED = frozenset({"main", "master", "trunk", "production", "prod"})
_SAFE_RE = re.compile(r"[^a-zA-Z0-9._/-]+")
# 分支名白名单：禁止 refspec 注入（含冒号）与 git 选项字符
_BRANCH_OK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_GENERIC_COMMIT_PROMPTS = frozenset(
    {
        "提交",
        "提交代码",
        "提交本批代码",
        "提交今天的代码",
        "提交今日代码",
        "帮我提交",
        "请提交",
        "commit",
        "git commit",
    }
)
# 开发产物/日志：不应进入「待提交本批」
_COMMIT_NOISE_PARTS = (
    "/.dev-logs/",
    ".dev-logs/",
    "/.vite/",
    ".vite/",
    "/node_modules/",
    "/__pycache__/",
    "/.pytest_cache/",
)
_COMMIT_NOISE_SUFFIXES = (".log", ".pid", ".db-journal")
# git push / 远程连接类错误（可重试）
_NETWORK_ERROR_RE = re.compile(
    r"(timeout|timed out|time.?out|connection refused|connection reset|network is unreachable|"
    r"could not resolve|failed to connect|unable to access|no route to host|"
    r"ssl connect error|tls handshake|dns|temporary failure|name or service not known|"
    r"could not read from remote|rpc failed|http 502|http 503|http 504|"
    r"recv failure|operation timed out|"
    r"远程主机|网络|连接超时|无法连接|连接被拒绝|Connection timed out)",
    re.I,
)
# 远程已有本地没有的提交（需先拉取再推）
_NON_FF_ERROR_RE = re.compile(
    r"(fetch first|non-fast-forward|"
    r"updates were rejected because the remote contains work|"
    r"tip of your current branch is behind|"
    r"\[rejected\][^\n]*\(fetch first\))",
    re.I,
)


def _norm_rel_path(rel: str) -> str:
    r = (rel or "").replace("\\", "/").strip()
    while r.startswith("./"):
        r = r[2:]
    return r.lstrip("/")


def is_git_network_error(error: str) -> bool:
    """推送/远程 git 操作是否像网络原因（可重试）。"""
    return bool(_NETWORK_ERROR_RE.search(str(error or "")))


def is_git_non_fast_forward_error(error: str) -> bool:
    """远程分支含本地没有的提交，直接 push 会被拒绝。"""
    text = str(error or "")
    if is_git_network_error(text):
        return False
    return bool(_NON_FF_ERROR_RE.search(text))


def classify_push_error(error: str) -> str:
    """给用户看的推送失败原因分类。"""
    text = str(error or "").strip()
    if not text:
        return "unknown"
    if is_git_network_error(text):
        return "network"
    if is_git_non_fast_forward_error(text):
        return "non_fast_forward"
    if re.search(
        r"(auth|denied|403|401|permission|could not read Username|Invalid username)",
        text,
        re.I,
    ):
        return "auth"
    return "other"


def humanize_push_error(error: str) -> str:
    """把 git push 原始错误收成可读中文（保留关键原文片段）。"""
    raw = str(error or "").strip()
    kind = classify_push_error(raw)
    snippet = raw.replace("\n", " ").strip()
    if len(snippet) > 280:
        snippet = snippet[:280] + "…"
    if kind == "network":
        return f"网络不可达，暂时推不到远程。{snippet}"
    if kind == "non_fast_forward":
        return (
            "远程分支有本地没有的新提交，不能直接推送（非网络问题）。"
            f"详情：{snippet}"
        )
    if kind == "auth":
        return f"远程认证失败，请检查 GitHub 登录/Token/SSH 密钥。{snippet}"
    return snippet or "push 失败"


def push_retry_hint(error: str) -> str:
    """确认卡/摘要里「下一步怎么做」的短提示。"""
    kind = classify_push_error(error)
    if kind == "network":
        return "修复网络后请点「重试推送」（不会重新 commit）。"
    if kind == "non_fast_forward":
        return "请点「重试推送」：系统会先拉取远程并 rebase 再推（不会重新 commit）。"
    if kind == "auth":
        return "请检查 GitHub 权限后点「重试推送」（不会重新 commit）。"
    return "请点「重试推送」再试（不会重新 commit）。"


def is_commit_noise_path(rel: str) -> bool:
    """开发日志、Vite 缓存等不计入待提交本批。"""
    r = _norm_rel_path(rel).lower()
    if not r:
        return True
    for part in _COMMIT_NOISE_PARTS:
        if part in r or r.startswith(part.lstrip("/")):
            return True
    for suf in _COMMIT_NOISE_SUFFIXES:
        if r.endswith(suf):
            return True
    # Vite deps 元数据
    if r.endswith("/deps/_metadata.json") or r.endswith("/deps/package.json"):
        return True
    return False


def is_commit_result_retryable(result: dict[str, Any]) -> bool:
    """提交结果是否因网络等临时原因失败、允许用户重试。"""
    if not isinstance(result, dict):
        return False
    push = result.get("push") if isinstance(result.get("push"), dict) else None
    err = str(result.get("error") or "")
    if push is not None and not push.get("ok"):
        return is_git_network_error(str(push.get("error") or err))
    if not result.get("ok") and not result.get("skipped"):
        return is_git_network_error(err)
    if result.get("skipped") and push is not None and not push.get("ok"):
        return is_git_network_error(str(push.get("error") or err))
    return False


def is_push_retry_needed(result: dict[str, Any]) -> bool:
    """本地已 commit 但 push 未成功 —— 只能重试推送，不能重新提交。"""
    if not isinstance(result, dict):
        return False
    if not str(result.get("commit") or "").strip():
        return False
    push = result.get("push") if isinstance(result.get("push"), dict) else None
    return push is not None and not push.get("ok")


def is_commit_retryable(result: dict[str, Any]) -> bool:
    """是否应保留确认卡并允许用户重试（含 push-only）。"""
    return is_commit_result_retryable(result) or is_push_retry_needed(result)


def _is_business_source(rel: str) -> bool:
    """是否业务/功能源码（对齐 code_review 后缀白名单；排除文档/样式/敏感）。"""
    from .skill_review import is_functional_source_rel

    r = _norm_rel_path(rel)
    if not r or is_commit_noise_path(r):
        return False
    return bool(is_functional_source_rel(r))


def list_git_dirty_files(workspace: Path | str) -> set[str]:
    """工作区相对 HEAD 有变更的路径（含未跟踪）。"""
    root = Path(workspace).expanduser().resolve()
    code, out, _ = _run_git(root, "status", "--porcelain", "-uall")
    if code != 0:
        return set()
    dirty: set[str] = set()
    for line in (out or "").splitlines():
        # porcelain：前两列为状态，第 3 列起为路径（通常是空格分隔）
        if len(line) < 4:
            continue
        # 兼容「XY path」与异常缺前导空格的「XYpath」
        if line[2] == " ":
            path = line[3:]
        elif line[1] == " ":
            path = line[2:]
        else:
            path = line[3:] if len(line) > 3 else ""
        path = path.strip()
        if path.startswith('"') and path.endswith('"'):
            # git 可能对特殊字符路径加引号；简单去壳即可
            path = path[1:-1]
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        path = _norm_rel_path(path)
        if path:
            dirty.add(path)
    return dirty


def file_has_git_pending_change(root: Path, rel: str) -> bool:
    """文件相对 HEAD 是否仍有未提交变更。"""
    norm = _norm_rel_path(rel)
    if not norm:
        return False
    dirty = list_git_dirty_files(root)
    if norm in dirty:
        return True
    code, _, _ = _run_git(root, "diff", "--quiet", "HEAD", "--", norm)
    if code == 1:
        return True
    code2, _, _ = _run_git(root, "ls-files", "--error-unmatch", norm)
    if code2 != 0:
        # 未跟踪且不在 status（极少见）
        try:
            return (root / norm).is_file()
        except OSError:
            return False
    return False


def filter_pending_commit_files(
    workspace: Path | str,
    synced_files: list[str],
) -> dict[str, Any]:
    """从 WorkBuddy 同步池里筛出 Git 仍待提交的文件（交集，排除噪声路径）。

    若同步池与 Git 待提交无交集，但工作区仍有业务源码改动（例如在 IDE 直接改的），
    则回落为「Git 工作区业务改动」，避免用户看到 Changes 却提示 0 个文件。
    """
    root = Path(workspace).expanduser().resolve()
    synced = [_norm_rel_path(str(p)) for p in (synced_files or []) if str(p).strip()]
    synced = [p for p in dict.fromkeys(synced) if p and not is_commit_noise_path(p)]
    excluded_non_business: list[str] = []
    business_synced: list[str] = []
    for rel in synced:
        if _is_business_source(rel):
            business_synced.append(rel)
        else:
            excluded_non_business.append(rel)
    dirty_all = list_git_dirty_files(root)
    dirty_clean = {p for p in dirty_all if not is_commit_noise_path(p)}
    dirty_business = sorted(p for p in dirty_clean if _is_business_source(p))

    pending: list[str] = []
    for rel in business_synced:
        try:
            if not (root / rel).is_file():
                continue
        except OSError:
            continue
        if file_has_git_pending_change(root, rel):
            pending.append(rel)

    source = "sync_pool"
    if not pending and dirty_business:
        # 回落：纳入当前 Git 工作区业务改动（仍排除日志/缓存/配置等）
        pending = []
        for rel in dirty_business:
            try:
                if (root / rel).is_file():
                    pending.append(rel)
            except OSError:
                continue
            if len(pending) >= 80:
                break
        source = "git_dirty_fallback"
        business_synced = list(dict.fromkeys([*business_synced, *pending]))

    outside_pool = [p for p in dirty_business if p not in set(synced)]
    note = (
        f"WorkBuddy 同步池 {len(synced)} 个；"
        f"排除非业务 {len(excluded_non_business)} 个（配置/锁/样式/文档等）；"
        f"业务源码 {len([p for p in synced if _is_business_source(p)])} 个；"
        f"Git 工作区变更 {len(dirty_clean)} 个（已排除日志/缓存）；"
    )
    if source == "git_dirty_fallback":
        note += (
            f"同步池与 Git 无交集；已回落纳入 Git 业务改动 {len(pending)} 个"
            + (f"（含 IDE 直接修改 {len(outside_pool)} 个）" if outside_pool else "")
        )
    else:
        note += f"本批待提交 {len(pending)} 个（业务源码 ∩ Git 待提交）"
        if outside_pool:
            note += f"；另有 {len(outside_pool)} 个 Git 业务改动未在同步池（未纳入）"

    return {
        "pending_files": pending,
        "synced_pool": business_synced if source == "sync_pool" else pending,
        "synced_total": len(business_synced) if source == "sync_pool" else len(pending),
        "synced_raw_total": len(synced),
        "excluded_non_business": excluded_non_business,
        "excluded_non_business_total": len(excluded_non_business),
        "pending_total": len(pending),
        "git_dirty_total": len(dirty_clean),
        "git_dirty_business_total": len(dirty_business),
        "outside_sync_pool": outside_pool[:40],
        "pending_source": source,
        "scope_note": note,
    }


def _run_git(cwd: Path, *args: str, timeout: int = 60) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        # 勿对 stdout 做 strip()：git status --porcelain 首行常以空格开头（如「 M path」），
        # 整段 strip 会吃掉首字符，导致 line[3:] 解析成「ackend/...」之类坏路径。
        out = proc.stdout or ""
        err = proc.stderr or ""
        if out.endswith("\n"):
            out = out[:-1]
        if err.endswith("\n"):
            err = err[:-1]
        return proc.returncode, out, err
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def validate_branch_name(branch: str) -> tuple[bool, str]:
    """校验分支名：防保护分支、refspec 注入、选项注入。"""
    b = (branch or "").strip().strip("/")
    if not b:
        return False, "工作分支名为空"
    if b.lower() in _PROTECTED:
        return False, f"禁止提交到保护分支 {b}"
    if not _BRANCH_OK_RE.match(b):
        return False, "分支名含非法字符（仅允许字母数字与 . _ / -，且不能以符号开头）"
    if ".." in b or b.startswith("-") or b.endswith(".lock"):
        return False, "分支名不合法"
    lower = b.lower()
    # 路径段也不允许保护名（如 foo/main）
    for part in lower.split("/"):
        if part in _PROTECTED:
            return False, f"禁止提交到保护分支路径段 {part}"
    return True, ""


def resolve_work_branch(
    *,
    workspace: Path | str | None = None,
    username: str = "",
    user_id: str = "",
    work_branch: str = "",
) -> str:
    """解析提交分支。

    优先级：
    1. 配置中心 / 入参 work_branch（非空且通过校验）
    2. 环境变量 LOCAL_DEV_WORK_BRANCH / CURSOR_DEV_WORK_BRANCH
    3. **仓库当前分支**（非保护分支时）
    4. 按用户名生成 dev/wb/<slug>（无仓库或当前在保护分支时的兜底）
    """
    fixed = (work_branch or "").strip().strip("/")
    if not fixed:
        fixed = (
            os.getenv("LOCAL_DEV_WORK_BRANCH")
            or os.getenv("CURSOR_DEV_WORK_BRANCH")
            or ""
        ).strip().strip("/")
    if fixed:
        ok, _ = validate_branch_name(fixed)
        if ok:
            return fixed
        # 非法配置不静默沿用，落入后续策略

    if workspace:
        info = inspect_git_repo(workspace)
        cur = str(info.get("current_branch") or "").strip()
        if cur and cur.lower() not in {"head", "detached"}:
            ok, _ = validate_branch_name(cur)
            if ok:
                return cur

    prefix = (os.getenv("CURSOR_DEV_BRANCH_PREFIX") or "dev/wb/").strip()
    raw = (username or "").strip() or (f"u{user_id}" if user_id else "anon")
    if "@" in raw:
        raw = raw.split("@", 1)[0]
    slug = _SAFE_RE.sub("-", raw.replace(" ", "-")).strip(".-_") or "anon"
    slug = slug[:64]
    if not prefix:
        candidate = slug
    elif prefix.endswith(("/", "-", "_")):
        candidate = f"{prefix}{slug}"
    else:
        candidate = f"{prefix}/{slug}"
    ok, _ = validate_branch_name(candidate)
    if ok:
        return candidate
    return f"dev/wb/{slug}"


def normalize_push_remote_url(url: str) -> str:
    """校验推送用远程地址：HTTPS 或 SSH（git@host:path）。"""
    u = (url or "").strip()
    if not u:
        raise ValueError("远程仓库地址为空")
    # 粘贴时常见尾巴
    u = u.split()[0].rstrip("/")
    if u.startswith("git@"):
        # git@github.com:org/repo.git
        if ":" not in u[4:] or " " in u:
            raise ValueError("SSH 地址格式应为 git@host:path/repo.git")
        return u
    if u.startswith("ssh://"):
        return u
    if u.startswith("http://") or u.startswith("https://"):
        # 禁内网元数据等极端地址：仅做浅校验，实际 push 仍走本机 git 凭证
        low = u.lower()
        if "169.254.169.254" in low or "metadata.google" in low:
            raise ValueError("不允许的远程地址")
        return u
    raise ValueError("请填写 HTTPS（https://…）或 SSH（git@host:path.git）仓库地址")


def inspect_git_repo(
    workspace: Path | str,
    *,
    remote_name: str = "",
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        return {"is_git": False, "reason": "目录不存在"}
    code, out, err = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if code != 0 or out.lower() != "true":
        return {"is_git": False, "reason": err or "不是 git 仓库"}
    code, branch, _ = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch or ""
    rname = (remote_name or "").strip()
    if not rname:
        try:
            from .config import get_config

            rname = get_config().remote_name
        except Exception:
            rname = ""
    if not rname:
        rname = (os.getenv("LOCAL_DEV_GIT_REMOTE") or "origin").strip() or "origin"
    rcode, remote_url, _ = _run_git(root, "remote", "get-url", rname)
    has_remote = rcode == 0 and bool((remote_url or "").strip())
    return {
        "is_git": True,
        "current_branch": branch,
        "on_protected": branch.lower() in _PROTECTED,
        "remote_name": rname,
        "remote_url": (remote_url or "").strip() if has_remote else "",
        "has_remote": has_remote,
    }


def _rebase_onto_remote(
    root: Path,
    branch: str,
    *,
    remote_name: str = "origin",
    fetch_url: str | None = None,
) -> tuple[bool, str]:
    """fetch 远程分支并 rebase 到当前 HEAD。失败时尽量 abort rebase。"""
    if fetch_url:
        fc, fout, ferr = _run_git(root, "fetch", fetch_url, branch, timeout=120)
        upstream = "FETCH_HEAD"
    else:
        fc, fout, ferr = _run_git(root, "fetch", remote_name, branch, timeout=120)
        upstream = f"{remote_name}/{branch}"
    if fc != 0:
        return False, ferr or fout or "fetch 失败"
    rc, rout, rerr = _run_git(root, "rebase", upstream, timeout=120)
    if rc == 0:
        return True, ""
    _run_git(root, "rebase", "--abort")
    detail = (rerr or rout or "rebase 失败").strip()
    return False, (
        "远程有新提交，自动 rebase 失败（可能有冲突或工作区未干净）。"
        f"请在本机处理后再推送。详情：{detail}"
    )


def _push_work_branch(
    root: Path,
    branch: str,
    *,
    push_url: str | None = None,
    save_remote: bool = False,
) -> dict[str, Any]:
    """推送当前工作分支到远程；遇 non-fast-forward 时自动 fetch+rebase 再推一次。"""

    def _pack(
        *,
        ok: bool,
        error: str = "",
        remote: str = "",
        remote_url: str = "",
        saved_remote: bool | None = None,
        rebased: bool = False,
    ) -> dict[str, Any]:
        raw = str(error or "")
        out: dict[str, Any] = {
            "ok": ok,
            "error": "" if ok else humanize_push_error(raw),
            "raw_error": "" if ok else raw,
            "remote": remote,
            "remote_url": remote_url,
            "error_kind": "" if ok else classify_push_error(raw),
        }
        if saved_remote is not None:
            out["saved_remote"] = saved_remote
        if rebased:
            out["rebased"] = True
        return out

    ok_br, err_br = validate_branch_name(branch)
    if not ok_br:
        return _pack(ok=False, error=err_br)

    # 固定 heads 双向 refspec，杜绝 feature:main 类注入
    safe_refspec = f"refs/heads/{branch}:refs/heads/{branch}"

    def _attempt(
        *,
        remote_name: str,
        remote_url: str,
        saved_remote: bool | None,
        use_url: str | None,
    ) -> dict[str, Any]:
        if use_url:
            pc, pout, perr = _run_git(root, "push", "-u", use_url, safe_refspec, timeout=120)
            err = "" if pc == 0 else (perr or pout or "push 失败")
            return _pack(
                ok=pc == 0,
                error=err,
                remote=remote_name,
                remote_url=remote_url or use_url,
                saved_remote=saved_remote,
            )
        pc, pout, perr = _run_git(root, "push", "-u", remote_name, safe_refspec, timeout=120)
        err = "" if pc == 0 else (perr or pout or "push 失败")
        return _pack(
            ok=pc == 0,
            error=err,
            remote=remote_name,
            remote_url=remote_url,
            saved_remote=saved_remote,
        )

    def _needs_rebase(push_out: dict[str, Any]) -> bool:
        return is_git_non_fast_forward_error(
            str(push_out.get("raw_error") or push_out.get("error") or "")
        )

    info2 = inspect_git_repo(root)
    remote_name = str(info2.get("remote_name") or "origin")
    typed = (push_url or "").strip()
    if typed:
        try:
            target_url = normalize_push_remote_url(typed)
        except ValueError as exc:
            return _pack(ok=False, error=str(exc), remote=remote_name, remote_url=typed)

        if save_remote:
            if info2.get("has_remote"):
                _run_git(root, "remote", "set-url", remote_name, target_url)
            else:
                _run_git(root, "remote", "add", remote_name, target_url)
            first = _attempt(
                remote_name=remote_name,
                remote_url=target_url,
                saved_remote=True,
                use_url=None,
            )
            if first.get("ok") or not _needs_rebase(first):
                return first
            ok_rb, rb_err = _rebase_onto_remote(root, branch, remote_name=remote_name)
            if not ok_rb:
                return _pack(
                    ok=False,
                    error=rb_err or str(first.get("raw_error") or first.get("error") or ""),
                    remote=remote_name,
                    remote_url=target_url,
                    saved_remote=True,
                )
            second = _attempt(
                remote_name=remote_name,
                remote_url=target_url,
                saved_remote=True,
                use_url=None,
            )
            if second.get("ok"):
                second["rebased"] = True
                _annotate_head_commit(root, second)
            return second

        first = _attempt(
            remote_name="(对话框地址)",
            remote_url=target_url,
            saved_remote=False,
            use_url=target_url,
        )
        if first.get("ok") or not _needs_rebase(first):
            return first
        ok_rb, rb_err = _rebase_onto_remote(root, branch, fetch_url=target_url)
        if not ok_rb:
            return _pack(
                ok=False,
                error=rb_err or str(first.get("raw_error") or first.get("error") or ""),
                remote="(对话框地址)",
                remote_url=target_url,
                saved_remote=False,
            )
        second = _attempt(
            remote_name="(对话框地址)",
            remote_url=target_url,
            saved_remote=False,
            use_url=target_url,
        )
        if second.get("ok"):
            second["rebased"] = True
            _annotate_head_commit(root, second)
        return second

    if info2.get("has_remote"):
        remote_url = str(info2.get("remote_url") or "")
        first = _attempt(
            remote_name=remote_name,
            remote_url=remote_url,
            saved_remote=None,
            use_url=None,
        )
        if first.get("ok") or not _needs_rebase(first):
            return first
        ok_rb, rb_err = _rebase_onto_remote(root, branch, remote_name=remote_name)
        if not ok_rb:
            return _pack(
                ok=False,
                error=rb_err or str(first.get("raw_error") or first.get("error") or ""),
                remote=remote_name,
                remote_url=remote_url,
            )
        second = _attempt(
            remote_name=remote_name,
            remote_url=remote_url,
            saved_remote=None,
            use_url=None,
        )
        if second.get("ok"):
            second["rebased"] = True
            _annotate_head_commit(root, second)
        return second

    return _pack(
        ok=False,
        error="未配置远程仓库。请在确认卡填写仓库地址（与 Git 审码类似），或选择「仅本地提交」。",
        remote=remote_name,
        remote_url="",
    )


def _annotate_head_commit(root: Path, push_out: dict[str, Any]) -> None:
    """rebase 后 commit SHA 可能变化，附带当前 HEAD。"""
    code, sha, _ = _run_git(root, "rev-parse", "HEAD")
    if code == 0 and (sha or "").strip():
        push_out["head_commit"] = sha.strip()


def has_chinese_commit_text(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def validate_chinese_commit_message(message: str) -> tuple[bool, str]:
    """提交说明必须用中文概括本次改动；返回 (ok, error)。"""
    msg = (message or "").strip()
    if not msg:
        return False, "请填写中文提交说明（概括本次修改内容）"
    if len(msg) < 4:
        return False, "提交说明过短，请用中文说明本次改了什么"
    if len(msg) > 200:
        return False, "提交说明过长（最多 200 字）"
    if msg.lower().startswith("wb-local-dev"):
        return False, "请勿使用默认英文占位说明，请用中文描述本次修改"
    if not has_chinese_commit_text(msg):
        return False, "提交说明须含中文，概括本次修改内容"
    return True, ""


def draft_chinese_commit_message(
    *,
    user_message: str = "",
    files: list[str] | None = None,
) -> str:
    """为确认卡预填中文说明：优先用户原话，否则按文件名摘要。"""
    um = (user_message or "").strip()
    first = um.splitlines()[0].strip() if um else ""
    if (
        first
        and has_chinese_commit_text(first)
        and first not in _GENERIC_COMMIT_PROMPTS
        and len(first) >= 4
    ):
        return first[:200]

    paths = [str(p).replace("\\", "/").strip() for p in (files or []) if str(p).strip()]
    names: list[str] = []
    for p in paths[:5]:
        name = Path(p).name.strip()
        if name and name not in names:
            names.append(name)
    n = len(paths)
    if names:
        joined = "、".join(names)
        if n > len(names):
            return f"更新 {joined} 等共 {n} 个文件"[:200]
        return f"更新 {joined}（{n} 个文件）"[:200]
    return "同步本批写码改动"


def commit_synced_files(
    workspace: Path | str,
    synced_files: list[str],
    *,
    message: str,
    work_branch: str,
    push: bool = False,
    push_url: str | None = None,
    save_remote: bool = False,
) -> dict[str, Any]:
    """在工作分支仅 add 本轮文件并 commit。禁止直接提交到保护分支。

    push_url: 对话框填入的远程地址（可覆盖已有 origin）；空则用已配置 remote。
    save_remote: 将 push_url 写入/更新为 LOCAL_DEV_GIT_REMOTE（默认 origin）。

    若本批相对 HEAD 已无新变更但仍请求 push：跳过 commit，仍尝试推送当前分支
    （覆盖「上次已本地提交、本次只想推远程」）。
    """
    root = Path(workspace).expanduser().resolve()
    info = inspect_git_repo(root)
    if not info.get("is_git"):
        return {
            "ok": False,
            "skipped": True,
            "error": info.get("reason") or "不是 git 仓库",
            "branch": "",
            "commit": "",
        }

    branch = (work_branch or "").strip().strip("/")
    ok_br, err_br = validate_branch_name(branch)
    if not ok_br:
        return {
            "ok": False,
            "skipped": False,
            "error": err_br,
            "branch": branch,
            "commit": "",
        }

    cur = str(info.get("current_branch") or "")
    if cur != branch:
        code, _, err = _run_git(root, "checkout", "-B", branch)
        if code != 0:
            return {
                "ok": False,
                "skipped": False,
                "error": f"无法切换到工作分支 {branch}：{err}",
                "branch": branch,
                "commit": "",
            }

    rels: list[str] = []
    for p in synced_files or []:
        rel = str(p).replace("\\", "/").strip()
        while rel.startswith("./"):
            rel = rel[2:]
        rel = rel.lstrip("/")
        if not rel or ".." in rel.split("/"):
            continue
        abs_path = (root / rel).resolve()
        try:
            abs_path.relative_to(root)
        except ValueError:
            continue
        if abs_path.is_file():
            rels.append(rel)
    rels = list(dict.fromkeys(rels))
    if not rels:
        if push:
            code, sha, _ = _run_git(root, "rev-parse", "HEAD")
            sha = sha[:12] if code == 0 else ""
            msg_skip = "本批无文件列表，跳过 commit；尝试推送当前工作分支"
            out: dict[str, Any] = {
                "ok": True,
                "skipped": True,
                "error": "",
                "message": msg_skip,
                "branch": branch,
                "commit": sha,
                "files": [],
            }
            out["push"] = _push_work_branch(
                root, branch, push_url=push_url, save_remote=save_remote
            )
            if out["push"].get("ok"):
                out["message"] = msg_skip + "。已推送到远程。"
            else:
                # 推送错误只放在 push.error，勿并入 message（否则重试校验会报说明过长）
                out["message"] = msg_skip
            return out
        return {
            "ok": False,
            "skipped": True,
            "error": "没有可提交的已同步文件",
            "branch": branch,
            "commit": "",
        }

    # 跳过 .gitignore 忽略的文件（如 *.db），避免整批 git add 失败
    ignored: list[str] = []
    if rels:
        icode, iout, _ = _run_git(root, "check-ignore", "--", *rels)
        if icode == 0 and iout.strip():
            ignored = [ln.strip() for ln in iout.splitlines() if ln.strip()]
    ignored_set = set(ignored)
    to_add = [r for r in rels if r not in ignored_set]
    if not to_add:
        code, sha, _ = _run_git(root, "rev-parse", "HEAD")
        sha = sha[:12] if code == 0 else ""
        out: dict[str, Any] = {
            "ok": True,
            "skipped": True,
            "error": "",
            "message": "本批文件均被 .gitignore 忽略，未执行 commit"
            + (f"（如 {', '.join(ignored[:5])}）" if ignored else ""),
            "branch": branch,
            "commit": sha,
            "files": [],
            "skipped_ignored": ignored,
        }
        if push:
            out["push"] = _push_work_branch(
                root, branch, push_url=push_url, save_remote=save_remote
            )
        return out

    code, _, err = _run_git(root, "add", "--", *to_add)
    if code != 0:
        return {
            "ok": False,
            "skipped": False,
            "error": f"git add 失败：{err}",
            "branch": branch,
            "commit": "",
            "files": to_add,
            "skipped_ignored": ignored,
        }

    code, staged, _ = _run_git(root, "diff", "--cached", "--name-only")
    if code != 0 or not staged.strip():
        # 本批相对 HEAD 无新 diff：多半上次已 commit；若用户要推送，仍 push 当前分支
        code, sha, _ = _run_git(root, "rev-parse", "HEAD")
        sha = sha[:12] if code == 0 else ""
        msg_skip = (
            "本批文件相对当前分支无新变更（可能已本地提交过）"
            + (f"；已跳过忽略文件 {len(ignored)} 个" if ignored else "")
            + "。IDE Changes 里其它未同步文件不在本批范围内。"
        )
        out = {
            "ok": True,
            "skipped": True,
            "error": "",
            "message": msg_skip,
            "branch": branch,
            "commit": sha,
            "files": to_add,
            "skipped_ignored": ignored,
        }
        if push:
            out["push"] = _push_work_branch(
                root, branch, push_url=push_url, save_remote=save_remote
            )
            if out["push"].get("ok"):
                out["message"] = msg_skip + " 已尝试推送当前分支到远程。"
            else:
                # 推送错误只放在 push.error，勿并入 message
                out["message"] = msg_skip
        return out

    msg = (message or "").strip()[:200]
    if not msg:
        return {
            "ok": False,
            "skipped": False,
            "error": "缺少提交说明",
            "branch": branch,
            "commit": "",
            "files": to_add,
            "skipped_ignored": ignored,
        }
    code, _, err = _run_git(root, "commit", "-m", msg)
    if code != 0:
        return {
            "ok": False,
            "skipped": False,
            "error": f"git commit 失败：{err}",
            "branch": branch,
            "commit": "",
            "files": to_add,
            "skipped_ignored": ignored,
        }

    code, sha, _ = _run_git(root, "rev-parse", "HEAD")
    sha = sha[:12] if code == 0 else ""
    push_result: dict[str, Any] | None = None
    if push:
        push_result = _push_work_branch(
            root, branch, push_url=push_url, save_remote=save_remote
        )

    return {
        "ok": True,
        "skipped": False,
        "error": "",
        "branch": branch,
        "commit": sha,
        "files": to_add,
        "skipped_ignored": ignored,
        "message": msg,
        "push": push_result,
    }

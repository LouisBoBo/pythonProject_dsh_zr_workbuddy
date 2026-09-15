"""业务落盘后写入「我的空间」——全部 fail-soft，禁止影响主流程。"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from . import catalog
from .config import get_space_config
from .dsh_locate import looks_like_dsh_session_id
from .redact import redact_text

_LOG = logging.getLogger(__name__)

# 写码同步进资料库：仅这些扩展名；密钥/凭证文件名一律跳过
_CODE_FILE_EXTS = frozenset(
    {
        "py",
        "js",
        "jsx",
        "ts",
        "tsx",
        "vue",
        "css",
        "scss",
        "less",
        "html",
        "htm",
        "json",
        "yaml",
        "yml",
        "toml",
        "md",
        "txt",
        "sh",
        "bash",
        "sql",
        "go",
        "rs",
        "java",
        "kt",
        "c",
        "cc",
        "cpp",
        "h",
        "hpp",
        "xml",
        "r",
        "rb",
        "php",
        "swift",
    }
)
_SECRET_NAME = re.compile(
    r"(^|[/\\])("
    r"\.env(\..+)?|"
    r"config\.ya?ml|"
    r".*\.pem|"
    r".*\.key|"
    r".*\.p12|"
    r".*\.pfx|"
    r".*\.keystore|"
    r"id_rsa|"
    r"id_dsa|"
    r"id_ed25519|"
    r".*credential.*|"
    r".*secret.*|"
    r".*api[_-]?key.*|"
    r"jwt_secret|"
    r"\.npmrc|"
    r"\.pypirc"
    r")$",
    re.I,
)


def _catalog_session_for_ingest(
    *,
    ui_session_id: str,
    fallback_prefix: str,
    fallback_id: str,
) -> tuple[str, str]:
    """返回 (catalog_session_id, dsh_path)。有真实 DSH id 时两者一致，打开会话只认这个。"""
    dsh = looks_like_dsh_session_id(ui_session_id)
    if dsh:
        return dsh, dsh
    fb = str(fallback_id or "").strip()
    if not fb:
        return "unassigned", ""
    return f"{fallback_prefix}:{fb}", ""


def _resolve_user_id(explicit: str = "") -> str:
    uid = str(explicit or "").strip()
    if uid:
        return uid
    try:
        from ..auth import current_user_id, get_active_user

        uid = (current_user_id() or "").strip()
        if uid:
            return uid
        active = get_active_user()
        if active and active.get("id"):
            return str(active["id"]).strip()
    except Exception:
        _LOG.debug("space resolve user_id skipped", exc_info=True)
    return ""


def _session_summary_from_report(report: dict[str, Any], *, max_chars: int) -> tuple[str, bool]:
    reply = str(report.get("reply") or report.get("detail") or "").strip()
    title_hint = str(report.get("title") or "").strip()
    rid = str(report.get("id") or "").strip()
    parts = []
    if title_hint:
        parts.append(f"【审码】{title_hint}")
    else:
        parts.append(f"【审码报告】{rid or '未命名'}")
    if reply:
        parts.append(reply)
    body = "\n\n".join(parts)
    return redact_text(body, max_chars=max_chars)


def ingest_code_review_report(report: dict[str, Any]) -> None:
    """审码报告保存后调用；异常全部吞掉。"""
    try:
        if not isinstance(report, dict):
            return
        rid = str(report.get("id") or "").strip()
        if not rid:
            return
        cfg = get_space_config()
        max_chars = int(cfg.get("max_session_body_chars") or 65536)
        uid = _resolve_user_id(str(report.get("user_id") or ""))
        raw_sid = str(
            report.get("session_id")
            or report.get("ui_session_id")
            or report.get("dsh_session_id")
            or ""
        ).strip()
        sid, dsh_path = _catalog_session_for_ingest(
            ui_session_id=raw_sid,
            fallback_prefix="review",
            fallback_id=rid,
        )
        call_id = str(report.get("call_id") or report.get("ui_call_id") or "").strip()
        reply = str(report.get("reply") or "")
        body, truncated = _session_summary_from_report(report, max_chars=max_chars)
        title = str(report.get("title") or "").strip()
        if not title:
            title = (reply.splitlines()[0] if reply.strip() else "")[:80] or f"审码 {rid}"
        catalog.upsert_session(
            session_id=sid,
            user_id=uid,
            source="dsh",
            title=title[:200],
            body_text=body,
            body_kind="summary",
            body_truncated=truncated,
            dsh_path=dsh_path,
        )
        # 报告正文进空间文件
        report_body = reply.strip() or str(
            __import__("json").dumps(
                {k: report.get(k) for k in ("id", "ok", "detail", "reply", "feature") if k in report},
                ensure_ascii=False,
                indent=2,
            )
        )
        report_body, _ = redact_text(report_body, max_chars=max(max_chars, 200_000))
        relpath, nbytes = catalog.write_report_file(
            user_id=uid or "anonymous",
            artifact_id=rid,
            body=report_body,
            ext="md",
        )
        catalog.upsert_artifact(
            artifact_id=rid,
            session_id=sid,
            user_id=uid,
            kind="code_review_report",
            title=(title or rid)[:200],
            relpath=relpath,
            summary="审码报告",
            bytes_n=nbytes,
            call_id=call_id,
        )
    except Exception:
        _LOG.warning("space ingest code_review_report failed", exc_info=True)


def _code_artifact_id(job_id: str, rel: str) -> str:
    j = re.sub(r"[^A-Za-z0-9_-]", "", str(job_id or ""))[:40] or "job"
    h = hashlib.sha256(str(rel or "").encode("utf-8")).hexdigest()[:12]
    return f"code-{j}-{h}"


def _is_secret_rel(rel: str) -> bool:
    return bool(_SECRET_NAME.search(str(rel or "").replace("\\", "/")))


def _resolve_under_workspace(workspace: Path, rel: str) -> Path | None:
    """相对路径落到工作区，禁止逃逸；失败返回 None。"""
    raw = str(rel or "").replace("\\", "/").strip().lstrip("/")
    if not raw or raw.startswith("删除 ") or ".." in raw.split("/"):
        return None
    try:
        root = workspace.resolve()
        cand = (root / raw).resolve()
        try:
            cand.relative_to(root)
        except ValueError:
            return None
        if not cand.is_file():
            return None
        return cand
    except OSError:
        return None


def _norm_rel(raw: str) -> str:
    rel = str(raw or "").replace("\\", "/").strip()
    if rel.startswith("删除 "):
        return ""
    while rel.startswith("./"):
        rel = rel[2:]
    return rel.lstrip("/")


def _rels_from_delivery_text(text: str) -> list[str]:
    """从交付正文里抽出 `path/to/file.ext`（仅作 Job 字段缺失时的兜底）。"""
    body = str(text or "")
    if not body.strip():
        return []
    found: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"`([^`\n]+)`", body):
        rel = _norm_rel(m.group(1))
        if not rel or "/" not in rel and "." not in rel:
            continue
        # 只要像仓库相对路径
        if ".." in rel.split("/") or rel.startswith("~") or rel.startswith("/"):
            continue
        ext = Path(rel).suffix.lstrip(".").lower()
        if ext not in _CODE_FILE_EXTS:
            continue
        if rel in seen:
            continue
        seen.add(rel)
        found.append(rel)
    return found


def _rels_changed_and_synced(job: dict[str, Any]) -> list[str]:
    """只取「本任务改动且已同步到本机」的相对路径；删除项、未改动文件一律不含。"""
    synced_raw = job.get("synced_files") or []
    synced_writes: list[str] = []
    seen: set[str] = set()
    if isinstance(synced_raw, list):
        for raw in synced_raw:
            rel = _norm_rel(str(raw or ""))
            if not rel or rel in seen:
                continue
            seen.add(rel)
            synced_writes.append(rel)

    changed_raw = job.get("changed_files") or []
    changed_set: set[str] = set()
    if isinstance(changed_raw, list):
        for raw in changed_raw:
            rel = _norm_rel(str(raw or ""))
            if rel:
                changed_set.add(rel)

    if synced_writes and changed_set:
        # 既改动又已同步
        out = [r for r in synced_writes if r in changed_set]
        if out:
            return out
        # 路径集合对不上时，仍以「已同步写入」为准（synced 本身来自变更同步）
        return synced_writes
    if synced_writes:
        return synced_writes
    # Job 字段被清空时：从交付正文兜底（仍须磁盘上文件存在才入库）
    delivery = str(job.get("delivery_text") or "")
    return _rels_from_delivery_text(delivery)


def _ingest_synced_code_files(
    *,
    job: dict[str, Any],
    session_id: str,
    user_id: str,
    job_id: str,
    cfg: dict[str, Any],
) -> int:
    """仅入库本写码任务改动并已同步的源码副本。返回入库条数；全程 fail-soft。"""
    if not bool(cfg.get("ingest_code_files", True)):
        return 0
    if str(job.get("status") or "") != "succeeded":
        return 0
    ws_raw = str(job.get("workspace") or "").strip()
    if not ws_raw:
        return 0
    try:
        workspace = Path(ws_raw).expanduser().resolve()
    except OSError:
        return 0
    if not workspace.is_dir():
        return 0

    max_files = max(1, min(50, int(cfg.get("code_file_max_count") or 20)))
    max_bytes = max(4096, min(2_000_000, int(cfg.get("code_file_max_bytes") or 262_144)))
    max_chars = max_bytes
    candidates = _rels_changed_and_synced(job)
    if not candidates:
        return 0

    n = 0
    for rel in candidates:
        if n >= max_files:
            break
        if _is_secret_rel(rel):
            continue
        ext = Path(rel).suffix.lstrip(".").lower()
        if ext not in _CODE_FILE_EXTS:
            continue
        path = _resolve_under_workspace(workspace, rel)
        if path is None:
            continue
        try:
            size = path.stat().st_size
            if size <= 0 or size > max_bytes:
                continue
            head = path.read_bytes()[:4096]
            if b"\x00" in head:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.strip():
            continue
        body, _ = redact_text(text, max_chars=max(max_chars, 4096))
        if not body.strip():
            continue
        aid = _code_artifact_id(job_id, rel)
        title = Path(rel).name or rel
        if "/" in rel and len(rel) <= 120:
            title = rel
        try:
            relpath, nbytes = catalog.write_space_file(
                user_id=user_id or "anonymous",
                artifact_id=aid,
                body=body,
                ext=ext or "txt",
                subdir="code",
            )
            catalog.upsert_artifact(
                artifact_id=aid,
                session_id=session_id,
                user_id=user_id,
                kind="code_file",
                title=str(title)[:200],
                relpath=relpath,
                summary=rel[:500],
                bytes_n=nbytes,
                call_id=str(job.get("ui_call_id") or ""),
            )
            n += 1
        except Exception:
            _LOG.debug("space ingest code file skip rel=%s", rel, exc_info=True)
    return n


def _code_job_prefix(job_id: str) -> str:
    return f"code-{re.sub(r'[^A-Za-z0-9_-]', '', str(job_id or ''))[:40]}-"


def _backfill_should_skip_job(job: dict[str, Any], *, user_id: str) -> bool:
    """True=跳过。跨用户已占有则跳过；本用户已收齐候选源码则跳过；否则继续补缺。"""
    jid = str(job.get("id") or "")
    if not jid:
        return True
    prefix = _code_job_prefix(jid)
    try:
        arts = catalog.list_artifacts_by_id_prefix(prefix, limit=80)
    except Exception:
        arts = []
    code_arts = [a for a in arts if str(a.get("kind") or "") == "code_file"]
    if not code_arts:
        return False
    uid = str(user_id or "").strip()
    owners = {str(a.get("user_id") or "").strip() for a in code_arts}
    owners.discard("")
    if owners and uid and uid not in owners:
        return True  # 已被其他登录用户占用
    # 本用户：对照候选路径，缺一个就继续 ingest（幂等 upsert）
    try:
        candidates = _rels_changed_and_synced(job)
    except Exception:
        candidates = []
    if not candidates:
        return True
    have = {
        str(a.get("summary") or "").replace("\\", "/").strip()
        for a in code_arts
        if str(a.get("user_id") or "").strip() in {"", uid}
    }
    for rel in candidates:
        r = _norm_rel(str(rel or ""))
        if not r or _is_secret_rel(r):
            continue
        ext = Path(r).suffix.lstrip(".").lower()
        if ext not in _CODE_FILE_EXTS:
            continue
        if r not in have:
            return False
    return True


def purge_delivery_summaries(*, user_id: str = "") -> int:
    """清掉资料库里的「写码交付」摘要文档（只保留改动源码）。"""
    n = 0
    try:
        arts = catalog.list_artifacts(user_id=user_id or "", limit=500, offset=0)
        for art in arts:
            if not isinstance(art, dict):
                continue
            if str(art.get("kind") or "") != "delivery_summary":
                continue
            if catalog.delete_artifact(str(art.get("id") or ""), user_id=user_id or "", admin=not bool(user_id)):
                n += 1
    except Exception:
        _LOG.debug("purge delivery_summary failed", exc_info=True)
    return n


def ingest_code_dev_job(job: dict[str, Any]) -> None:
    """写码成功时 fail-soft 入库已改动源码；不写「写码交付」摘要文档。"""
    try:
        if not isinstance(job, dict):
            return
        status = str(job.get("status") or "")
        # 仅成功任务收源码；失败/取消不写交付摘要进资料库
        if status != "succeeded":
            return
        jid = str(job.get("id") or "").strip()
        if not jid:
            return
        cfg = get_space_config()
        max_chars = int(cfg.get("max_session_body_chars") or 65536)
        uid = _resolve_user_id(str(job.get("user_id") or ""))
        raw_sid = str(job.get("ui_session_id") or job.get("thread_id") or "").strip()
        sid, dsh_path = _catalog_session_for_ingest(
            ui_session_id=raw_sid,
            fallback_prefix="dev",
            fallback_id=jid,
        )
        msg0 = ""
        msgs = job.get("messages")
        if isinstance(msgs, list) and msgs:
            first = msgs[0]
            if isinstance(first, dict):
                msg0 = str(first.get("content") or "").strip()
        title = (msg0.splitlines()[0] if msg0 else "")[:80] or f"写码 {jid}"
        try:
            n_code = _ingest_synced_code_files(
                job=job,
                session_id=sid,
                user_id=uid,
                job_id=jid,
                cfg=cfg,
            )
        except Exception:
            _LOG.debug("space ingest synced code files failed", exc_info=True)
            n_code = 0
        if n_code <= 0:
            if job.get("synced_files") or job.get("changed_files") or job.get("delivery_text"):
                _LOG.info(
                    "space code ingest 0 files job=%s ws=%s rels=%s",
                    jid,
                    str(job.get("workspace") or "")[:80],
                    _rels_changed_and_synced(job)[:8],
                )
            return
        # 有源码才挂会话壳（分组展示）；已有会话不覆盖标题（同会话多 job 回填）
        prev = catalog.get_session(sid)
        body, truncated = redact_text(
            f"【写码】{title}\n已入库源码 {n_code} 个文件",
            max_chars=max_chars,
        )
        catalog.upsert_session(
            session_id=sid,
            user_id=uid,
            source="dsh",
            title="" if prev else title[:200],
            body_text=None if prev else body,
            body_kind="summary",
            body_truncated=None if prev else truncated,
            dsh_path=dsh_path or (str(prev.get("dsh_path") or "") if prev else ""),
        )
    except Exception:
        _LOG.warning("space ingest code_dev_job failed", exc_info=True)


def backfill_code_dev_files(*, user_id: str = "", limit: int = 40) -> dict[str, Any]:
    """打开资料库时：扫本机写码成功任务，补入库改动源码（fail-soft，幂等）。"""
    out = {"ok": True, "scanned": 0, "ingested_jobs": 0, "files": 0, "purged_delivery": 0}
    try:
        from ..code_dev.service import default_data_dir
        from ..code_dev import jobs as job_store

        cfg = get_space_config()
        if not bool(cfg.get("ingest_code_files", True)):
            return out
        uid = _resolve_user_id(user_id)
        # 历史误入库的「写码交付」摘要一律清掉
        try:
            out["purged_delivery"] = purge_delivery_summaries(user_id=uid)
            catalog.purge_empty_sessions(user_id=uid)
        except Exception:
            _LOG.debug("space purge delivery_summary on backfill failed", exc_info=True)
        rows = job_store.list_jobs(default_data_dir())[: max(1, min(80, int(limit or 40)))]
        for job in rows:
            if not isinstance(job, dict):
                continue
            if str(job.get("status") or "") != "succeeded":
                continue
            out["scanned"] += 1
            # 若 Job 无 user_id，挂到当前打开资料库的用户
            j = dict(job)
            if not str(j.get("user_id") or "").strip() and uid:
                j["user_id"] = uid
            if _backfill_should_skip_job(j, user_id=uid):
                continue
            try:
                ingest_code_dev_job(j)
                out["ingested_jobs"] += 1
            except Exception:
                _LOG.debug("space backfill one code_dev job failed", exc_info=True)
        # DSH Cursor 写码（ccj）与引擎 ldj 分轨；聊天里常见走 ccj，必须一并回填
        try:
            ccj = backfill_cursor_coding_files(user_id=uid, limit=limit)
            out["cursor_coding"] = ccj
            out["scanned"] += int(ccj.get("scanned") or 0)
            out["ingested_jobs"] += int(ccj.get("ingested_jobs") or 0)
        except Exception:
            _LOG.debug("space backfill cursor_coding failed", exc_info=True)
        return out
    except Exception:
        _LOG.warning("space backfill_code_dev_files failed", exc_info=True)
        return {"ok": False, "scanned": out["scanned"], "ingested_jobs": out["ingested_jobs"], "files": 0}


def _cursor_coding_jobs_dir() -> Path | None:
    """只读 DSH Cursor 写码 Job 目录（~/.zhongruan/cursor-coding/jobs）；禁止扫出 HOME。"""
    import os

    fallback = Path.home() / ".zhongruan" / "cursor-coding" / "jobs"
    env = (os.environ.get("CURSOR_CODING_HOME") or "").strip()
    if env:
        try:
            home = Path.home().resolve()
            base = Path(env).expanduser().resolve()
            if base != home and home in base.parents:
                cand = base / "jobs"
                if cand.is_dir():
                    return cand
        except OSError:
            pass
    try:
        if fallback.is_dir():
            home = Path.home().resolve()
            resolved = fallback.resolve()
            if home in resolved.parents:
                return resolved
    except OSError:
        return None
    return None


def _job_dict_from_ccj(raw: dict[str, Any], *, user_id: str) -> dict[str, Any] | None:
    """把 ccj 落盘映射成 ingest_code_dev_job 可吃的结构（不改插件文件）。"""
    if not isinstance(raw, dict):
        return None
    status = str(raw.get("status") or "").strip().lower()
    if status not in {"succeeded", "done"}:
        return None
    jid = str(raw.get("id") or "").strip()
    if not jid.startswith("ccj-"):
        return None
    ws = str(raw.get("workspace") or "").strip()
    if not ws:
        return None
    synced = raw.get("synced_files") or raw.get("last_synced_files") or []
    changed = raw.get("changed_files") or []
    if not isinstance(synced, list):
        synced = []
    if not isinstance(changed, list):
        changed = []
    req = str(raw.get("requirement") or "").strip()
    return {
        "id": jid,
        "status": "succeeded",
        "user_id": user_id,
        "workspace": ws,
        "changed_files": [str(x) for x in changed if str(x or "").strip()],
        "synced_files": [str(x) for x in synced if str(x or "").strip()],
        "ui_session_id": str(raw.get("dsh_session_id") or "").strip(),
        "ui_call_id": str(raw.get("dsh_call_id") or "").strip(),
        "thread_id": str(raw.get("dsh_session_id") or "").strip(),
        "messages": [{"role": "user", "content": req[:4000]}] if req else [],
        "delivery_text": str(raw.get("assistant_text") or "")[:12000],
    }


def backfill_cursor_coding_files(*, user_id: str = "", limit: int = 30) -> dict[str, Any]:
    """扫 ~/.zhongruan/cursor-coding/jobs 成功任务，把改动源码写入资料库（fail-soft，幂等）。"""
    out: dict[str, Any] = {"ok": True, "scanned": 0, "ingested_jobs": 0}
    try:
        cfg = get_space_config()
        if not bool(cfg.get("ingest_code_files", True)):
            return out
        uid = _resolve_user_id(user_id)
        jobs_dir = _cursor_coding_jobs_dir()
        if jobs_dir is None:
            return out
        paths = sorted(
            jobs_dir.glob("ccj-*.json"),
            key=lambda p: p.stat().st_mtime if p.is_file() else 0,
            reverse=True,
        )[: max(1, min(60, int(limit or 30)))]
        for path in paths:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            job = _job_dict_from_ccj(raw if isinstance(raw, dict) else {}, user_id=uid)
            if not job:
                continue
            # 会话已被其他用户占用则不抢
            sid = str(job.get("ui_session_id") or "").strip()
            if sid:
                sess = catalog.get_session(sid)
                if sess:
                    owner = str(sess.get("user_id") or "").strip()
                    if owner and owner != uid:
                        continue
            out["scanned"] += 1
            jid = str(job.get("id") or "")
            if _backfill_should_skip_job(job, user_id=uid):
                continue
            try:
                ingest_code_dev_job(job)
                out["ingested_jobs"] += 1
            except Exception:
                _LOG.debug("space backfill one ccj job failed id=%s", jid, exc_info=True)
        return out
    except Exception:
        _LOG.warning("space backfill_cursor_coding_files failed", exc_info=True)
        return {"ok": False, "scanned": out["scanned"], "ingested_jobs": out["ingested_jobs"]}


def ingest_chat_document(
    *,
    user_id: str,
    session_id: str,
    session_title: str,
    artifact_id: str,
    title: str,
    body: str,
    max_chars: int,
) -> None:
    """聊天壳助手产出的文档；须已有真实 DSH session-uuid。失败不抛。"""
    try:
        sid, dsh_path = _catalog_session_for_ingest(
            ui_session_id=session_id,
            fallback_prefix="chat",
            fallback_id=artifact_id,
        )
        if not dsh_path:
            return
        uid = _resolve_user_id(user_id)
        text, truncated = redact_text(str(body or ""), max_chars=max(max_chars, 200_000))
        if not text.strip():
            return
        summary, _ = redact_text(
            f"【聊天文档】{title}\n来源会话：{sid}\n",
            max_chars=max_chars,
        )
        catalog.upsert_session(
            session_id=sid,
            user_id=uid,
            source="dsh",
            title=(session_title or title or sid)[:200],
            body_text=summary,
            body_kind="summary",
            body_truncated=truncated,
            dsh_path=dsh_path,
        )
        relpath, nbytes = catalog.write_report_file(
            user_id=uid or "anonymous",
            artifact_id=artifact_id,
            body=text,
            ext="md",
        )
        catalog.upsert_artifact(
            artifact_id=artifact_id,
            session_id=sid,
            user_id=uid,
            kind="chat_document",
            title=(title or artifact_id)[:200],
            relpath=relpath,
            summary="聊天产出文档",
            bytes_n=nbytes,
        )
    except Exception:
        _LOG.warning("space ingest chat_document failed", exc_info=True)

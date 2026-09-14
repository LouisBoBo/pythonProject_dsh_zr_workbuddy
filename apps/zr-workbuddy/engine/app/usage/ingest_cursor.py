"""只读采集 DSH Cursor 写码 Job 的 SDK usage，不改插件源码。"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .parse import from_sdk_usage
from .store import append_event, drop_events_for_job, known_job_ids

_LOG = logging.getLogger(__name__)
_DONE = {"succeeded", "failed", "cancelled", "done", "error"}
_last_ingest = 0.0
_GLOB_META = re.compile(r"[*?\[\]]")
_JOB_ID_OK = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def _safe_home_path(raw: str, fallback: Path) -> Path:
    """环境变量覆盖必须落在当前用户 HOME 之下，且不能就是 HOME 本身。"""
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        cand = Path(text).expanduser().resolve()
        home = Path.home().resolve()
    except OSError:
        return fallback
    if cand == home or home not in cand.parents:
        _LOG.warning("ignore CURSOR_CODING_HOME outside home")
        return fallback
    return cand


def _inside(child: Path, root: Path) -> bool:
    try:
        c = child.expanduser().resolve()
        r = root.expanduser().resolve()
    except OSError:
        return False
    try:
        c.relative_to(r)
        return True
    except ValueError:
        return False


def _dsh_cursor_roots() -> list[Path]:
    fallback = Path.home() / ".zhongruan" / "cursor-coding"
    roots: list[Path] = []
    env = (os.environ.get("CURSOR_CODING_HOME") or "").strip()
    if env:
        roots.append(_safe_home_path(env, fallback))
    roots.append(fallback)
    seen: set[str] = set()
    out: list[Path] = []
    for p in roots:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _slug_sandbox(sandbox: str) -> str:
    # Cursor 项目 slug 会去掉路径段前导点：.zhongruan → zhongruan
    parts = [p.lstrip(".") for p in sandbox.strip("/").replace("\\", "/").split("/") if p]
    return "-".join(parts)


def _cursor_projects_root() -> Path:
    return Path.home() / ".cursor" / "projects"


def _allowed_cursor_roots() -> list[Path]:
    return [
        *_dsh_cursor_roots(),
        _cursor_projects_root(),
        Path.home() / ".cursor",
        Path.home() / ".zhongruan",
    ]


def _sdk_index_dbs(sandbox: str, job_id: str = "") -> list[Path]:
    found: list[Path] = []
    sb = (sandbox or "").strip()
    projects = _cursor_projects_root()
    allowed = _allowed_cursor_roots()
    if sb and not _GLOB_META.search(sb):
        p = Path(sb).expanduser()
        if any(_inside(p, root) for root in allowed):
            found.extend(p.glob(".cursor-sdk-store/*/index.db"))
            slug = _slug_sandbox(str(p))
            if slug and not _GLOB_META.search(slug):
                found.extend((projects / slug / "sdk-agent-store").glob("*/index.db"))
    jid = str(job_id or "").strip()
    if jid and _JOB_ID_OK.match(jid):
        found.extend(projects.glob(f"*{jid}*/sdk-agent-store/*/index.db"))
    uniq: list[Path] = []
    seen: set[str] = set()
    for db in found:
        if not db.is_file() or db.name != "index.db":
            continue
        if not any(_inside(db, root) for root in allowed):
            continue
        try:
            key = str(db.resolve())
        except OSError:
            key = str(db)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(db)
    return uniq


def _read_runs(db: Path, *, agent_id: str, run_id: str) -> list[dict[str, Any]]:
    uri = db.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    except sqlite3.Error:
        try:
            conn = sqlite3.connect(str(db), timeout=2.0)
        except sqlite3.Error:
            return []
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        queries: list[tuple[str, tuple[Any, ...]]] = []
        sql = (
            "SELECT run_id, status, model, usage_json, started_at, finished_at FROM runs"
        )
        if agent_id:
            queries.append((sql + " WHERE agent_id = ?", (agent_id,)))
        if run_id:
            queries.append((sql + " WHERE run_id = ?", (run_id,)))
        if not queries:
            return []
        for q, args in queries:
            try:
                cur.execute(q, args)
            except sqlite3.Error:
                continue
            rows = [{k: row[k] for k in row.keys()} for row in cur.fetchall()]
            if rows:
                return rows
        return []
    except sqlite3.Error:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _sum_usage(runs: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    merged: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }
    model = ""
    hit = False
    for run in runs:
        model = model or str(run.get("model") or "")
        raw = run.get("usage_json")
        obj: Any = raw
        if isinstance(raw, str) and raw.strip():
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                obj = None
        parsed = from_sdk_usage(obj)
        if not parsed:
            continue
        hit = True
        for k in merged:
            merged[k] += int(parsed.get(k) or 0)
    if not hit:
        return None, model
    merged["quality"] = "sdk"
    return merged, model


def _ingest_job(job: dict[str, Any], *, known_sdk: set[str], known_missing: set[str]) -> bool:
    job_id = str(job.get("id") or "").strip()
    if not job_id or job_id in known_sdk:
        return False
    status = str(job.get("status") or "").strip().lower()
    if status not in _DONE:
        return False
    sandbox = str(job.get("sandbox_path") or "").strip()
    agent_id = str(job.get("agent_id") or "").strip()
    run_id = str(job.get("run_id") or "").strip()
    tokens = None
    model = ""
    for db in _sdk_index_dbs(sandbox, job_id):
        runs = _read_runs(db, agent_id=agent_id, run_id=run_id)
        tokens, model = _sum_usage(runs)
        if tokens:
            break
    if job_id in known_missing:
        if not tokens:
            return False
        drop_events_for_job(job_id)
    ts = str(job.get("updated_at") or job.get("created_at") or "")
    evt = append_event(
        source="cursor",
        lane="dsh_cursor",
        provider="cursor",
        model=model or str(job.get("model") or "composer-2.5"),
        tokens=tokens,
        ok=status in {"succeeded", "done"},
        job_id=job_id,
        error_class="" if status in {"succeeded", "done"} else status,
        ts=ts,
    )
    return evt is not None


def ingest_dsh_cursor_jobs(*, force: bool = False) -> int:
    """扫描 ~/.zhongruan/cursor-coding/jobs，把已结束 Job 记入引擎账本。"""
    global _last_ingest
    now = time.monotonic()
    if not force and now - _last_ingest < 2.0:
        return 0
    from . import store as st

    if not force and getattr(st, "_data_dir_override", None):
        return 0
    _last_ingest = now
    known_sdk = known_job_ids(only_quality="sdk")
    known_missing = known_job_ids(only_quality="missing") - known_sdk
    added = 0
    for root in _dsh_cursor_roots():
        jobs_dir = root / "jobs"
        if not jobs_dir.is_dir():
            continue
        for path in sorted(jobs_dir.glob("ccj-*.json")):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(job, dict):
                continue
            try:
                if _ingest_job(job, known_sdk=known_sdk, known_missing=known_missing):
                    added += 1
                    jid = str(job.get("id") or "")
                    if jid:
                        known_sdk.add(jid)
                        known_missing.discard(jid)
            except Exception:
                _LOG.warning("ingest cursor job failed path=%s", path, exc_info=True)
    if added:
        _LOG.info("ingested %s DSH Cursor jobs into usage ledger", added)
    return added

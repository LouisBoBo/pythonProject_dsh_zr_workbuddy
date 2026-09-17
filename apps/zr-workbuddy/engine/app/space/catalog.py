"""SQLite catalog：sessions（含 body_text）+ artifacts。"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)
_lock = threading.Lock()
_data_dir_override: Path | None = None

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")


def set_data_dir(path: str | Path | None) -> None:
    global _data_dir_override
    _data_dir_override = Path(path) if path else None


def space_root() -> Path:
    if _data_dir_override is not None:
        root = Path(_data_dir_override)
    else:
        root = Path(__file__).resolve().parents[2] / "data" / "space"
    root.mkdir(parents=True, exist_ok=True)
    (root / "files").mkdir(parents=True, exist_ok=True)
    return root


def _db_path() -> Path:
    return space_root() / "catalog.sqlite"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY,
          source TEXT NOT NULL DEFAULT 'dsh',
          title TEXT NOT NULL DEFAULT '',
          user_id TEXT NOT NULL DEFAULT '',
          started_at INTEGER NOT NULL DEFAULT 0,
          updated_at INTEGER NOT NULL DEFAULT 0,
          body_kind TEXT NOT NULL DEFAULT 'summary',
          body_text TEXT NOT NULL DEFAULT '',
          body_truncated INTEGER NOT NULL DEFAULT 0,
          dsh_path TEXT NOT NULL DEFAULT '',
          artifact_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user_updated
          ON sessions(user_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS artifacts (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL DEFAULT 'unassigned',
          call_id TEXT NOT NULL DEFAULT '',
          user_id TEXT NOT NULL DEFAULT '',
          kind TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL DEFAULT '',
          relpath TEXT NOT NULL DEFAULT '',
          summary TEXT NOT NULL DEFAULT '',
          bytes INTEGER NOT NULL DEFAULT 0,
          created_at INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'ready'
        );
        CREATE INDEX IF NOT EXISTS idx_artifacts_user_created
          ON artifacts(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_artifacts_session
          ON artifacts(session_id);
        """
    )


def _safe_id(raw: str, *, fallback: str = "") -> str:
    text = str(raw or "").strip()
    if _SAFE_ID.match(text):
        return text
    return fallback


def _now() -> int:
    return int(time.time())


def _row_to_session(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "source": row["source"],
        "title": row["title"],
        "user_id": row["user_id"],
        "started_at": row["started_at"],
        "updated_at": row["updated_at"],
        "body_kind": row["body_kind"],
        "body_text": row["body_text"],
        "body_truncated": bool(row["body_truncated"]),
        "dsh_path": row["dsh_path"],
        "artifact_count": row["artifact_count"],
    }


def _row_to_artifact(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "call_id": row["call_id"],
        "user_id": row["user_id"],
        "kind": row["kind"],
        "title": row["title"],
        "relpath": row["relpath"],
        "summary": row["summary"],
        "bytes": row["bytes"],
        "created_at": row["created_at"],
        "status": row["status"],
    }


def _refresh_artifact_count(conn: sqlite3.Connection, session_id: str) -> None:
    sid = _safe_id(session_id)
    if not sid or sid == "unassigned":
        return
    n = conn.execute(
        "SELECT COUNT(*) FROM artifacts WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    mx_row = conn.execute(
        "SELECT COALESCE(MAX(created_at), 0) FROM artifacts WHERE session_id = ?",
        (sid,),
    ).fetchone()
    mx = int(mx_row[0] if mx_row else 0)
    # 会话排序跟「最新文档时间」对齐，避免 updated_at 陈旧导致旧会话排前
    conn.execute(
        """
        UPDATE sessions SET
          artifact_count = ?,
          updated_at = CASE
            WHEN ? > updated_at THEN ?
            ELSE updated_at
          END
        WHERE id = ?
        """,
        (int(n), mx, mx, sid),
    )


def upsert_session(
    *,
    session_id: str,
    user_id: str = "",
    source: str = "dsh",
    title: str = "",
    body_text: str | None = None,
    body_kind: str = "summary",
    body_truncated: bool | None = None,
    dsh_path: str = "",
    touch: bool = True,
    at: int | None = None,
) -> dict[str, Any] | None:
    sid = _safe_id(session_id)
    if not sid:
        return None
    now = int(at) if at is not None and int(at) > 0 else _now()
    src = (source or "dsh").strip()[:32] or "dsh"
    uid = str(user_id or "").strip()[:120]
    title_s = str(title or "").strip()[:200]
    kind = (body_kind or "summary").strip()[:32] or "summary"
    dsh = str(dsh_path or "").strip()[:500]
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            prev = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
            if prev:
                prev_uid = str(prev["user_id"] or "").strip()
                # 禁止跨用户抢会话归属
                if prev_uid and uid and prev_uid != uid:
                    return _row_to_session(prev)
                new_title = title_s or prev["title"]
                new_uid = prev_uid or uid
                new_body = prev["body_text"] if body_text is None else str(body_text)
                new_kind = kind if body_text is not None else prev["body_kind"]
                new_trunc = (
                    int(bool(body_truncated))
                    if body_truncated is not None
                    else int(prev["body_truncated"])
                )
                new_dsh = dsh or prev["dsh_path"]
                if at is not None and int(at) > 0:
                    updated = int(at)
                else:
                    updated = now if touch else int(prev["updated_at"] or now)
                started = int(prev["started_at"] or updated)
                if at is not None and int(at) > 0 and (not prev["started_at"] or int(prev["started_at"]) > updated):
                    started = updated
                conn.execute(
                    """
                    UPDATE sessions SET
                      source = ?, title = ?, user_id = ?, started_at = ?, updated_at = ?,
                      body_kind = ?, body_text = ?, body_truncated = ?, dsh_path = ?
                    WHERE id = ?
                    """,
                    (
                        src,
                        new_title,
                        new_uid,
                        started,
                        updated,
                        new_kind,
                        new_body,
                        new_trunc,
                        new_dsh,
                        sid,
                    ),
                )
            else:
                body = "" if body_text is None else str(body_text)
                trunc = int(bool(body_truncated)) if body_truncated is not None else 0
                conn.execute(
                    """
                    INSERT INTO sessions (
                      id, source, title, user_id, started_at, updated_at,
                      body_kind, body_text, body_truncated, dsh_path, artifact_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (sid, src, title_s or sid, uid, now, now, kind, body, trunc, dsh),
                )
            conn.commit()
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
            return _row_to_session(row)
        finally:
            conn.close()


def upsert_artifact(
    *,
    artifact_id: str,
    session_id: str = "unassigned",
    user_id: str = "",
    kind: str,
    title: str = "",
    relpath: str = "",
    summary: str = "",
    bytes_n: int = 0,
    call_id: str = "",
    status: str = "ready",
    at: int | None = None,
) -> dict[str, Any] | None:
    aid = _safe_id(artifact_id)
    if not aid:
        return None
    sid = _safe_id(session_id, fallback="unassigned") or "unassigned"
    now = int(at) if at is not None and int(at) > 0 else _now()
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            prev = conn.execute("SELECT * FROM artifacts WHERE id = ?", (aid,)).fetchone()
            payload = (
                sid,
                str(call_id or "").strip()[:200],
                str(user_id or "").strip()[:120],
                str(kind or "").strip()[:64],
                str(title or "").strip()[:200],
                str(relpath or "").strip()[:500],
                str(summary or "").strip()[:500],
                max(0, int(bytes_n or 0)),
                str(status or "ready").strip()[:32] or "ready",
            )
            if prev:
                created = int(prev["created_at"] or now)
                if at is not None and int(at) > 0:
                    created = int(at)
                prev_uid = str(prev["user_id"] or "").strip()
                new_uid = str(user_id or "").strip()[:120]
                # 禁止跨用户抢归属：已有主人且与请求用户不同 → 不更新
                if prev_uid and new_uid and prev_uid != new_uid:
                    return _row_to_artifact(prev)
                keep_uid = prev_uid or new_uid
                conn.execute(
                    """
                    UPDATE artifacts SET
                      session_id = ?, call_id = ?, user_id = ?, kind = ?,
                      title = ?, relpath = ?, summary = ?, bytes = ?, status = ?,
                      created_at = ?
                    WHERE id = ?
                    """,
                    (
                        sid,
                        str(call_id or "").strip()[:200],
                        keep_uid[:120],
                        str(kind or "").strip()[:64],
                        str(title or "").strip()[:200],
                        str(relpath or "").strip()[:500],
                        str(summary or "").strip()[:500],
                        max(0, int(bytes_n or 0)),
                        str(status or "ready").strip()[:32] or "ready",
                        created,
                        aid,
                    ),
                )
                old_sid = prev["session_id"]
            else:
                conn.execute(
                    """
                    INSERT INTO artifacts (
                      id, session_id, call_id, user_id, kind, title,
                      relpath, summary, bytes, created_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (aid, *payload[:8], now, payload[8]),
                )
                old_sid = None
            _refresh_artifact_count(conn, sid)
            if old_sid and old_sid != sid:
                _refresh_artifact_count(conn, old_sid)
            conn.commit()
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (aid,)).fetchone()
            return _row_to_artifact(row)
        finally:
            conn.close()


def list_sessions(
    *,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    admin_all: bool = False,
) -> list[dict[str, Any]]:
    lim = max(1, min(200, int(limit or 50)))
    off = max(0, int(offset or 0))
    uid = str(user_id or "").strip()
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            if admin_all:
                rows = conn.execute(
                    """
                    SELECT * FROM sessions
                    ORDER BY updated_at DESC LIMIT ? OFFSET ?
                    """,
                    (lim, off),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM sessions WHERE user_id = ?
                    ORDER BY updated_at DESC LIMIT ? OFFSET ?
                    """,
                    (uid, lim, off),
                ).fetchall()
            return [_row_to_session(r) for r in rows if r]
        finally:
            conn.close()


def get_session(session_id: str) -> dict[str, Any] | None:
    sid = _safe_id(session_id)
    if not sid:
        return None
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
            return _row_to_session(row)
        finally:
            conn.close()


def list_artifacts(
    *,
    user_id: str,
    session_id: str = "",
    kind: str = "",
    limit: int = 50,
    offset: int = 0,
    admin_all: bool = False,
) -> list[dict[str, Any]]:
    lim = max(1, min(500, int(limit or 50)))
    off = max(0, int(offset or 0))
    uid = str(user_id or "").strip()
    sid = _safe_id(session_id) if session_id else ""
    k = str(kind or "").strip()[:64]
    clauses: list[str] = []
    args: list[Any] = []
    if not admin_all:
        clauses.append("user_id = ?")
        args.append(uid)
    if sid:
        clauses.append("session_id = ?")
        args.append(sid)
    if k:
        clauses.append("kind = ?")
        args.append(k)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            rows = conn.execute(
                f"SELECT * FROM artifacts{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (*args, lim, off),
            ).fetchall()
            return [_row_to_artifact(r) for r in rows if r]
        finally:
            conn.close()


def list_library(
    *,
    user_id: str,
    page: int = 1,
    page_size: int = 10,
    q: str = "",
) -> dict[str, Any]:
    """按会话挂文档；只返回「至少有一份文档」的会话；分页。

    返回 ``{sessions, total, page, page_size}``。列表不含超长 body_text。
    """
    uid = str(user_id or "").strip()
    ps = max(1, min(50, int(page_size or 10)))
    pg = max(1, int(page or 1))
    needle = str(q or "").strip().lower()
    off = (pg - 1) * ps

    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            # 只取有文档的会话
            base_sql = """
                SELECT s.* FROM sessions s
                WHERE s.user_id = ?
                  AND EXISTS (SELECT 1 FROM artifacts a WHERE a.session_id = s.id)
            """
            params: list[Any] = [uid]
            if needle:
                base_sql += """
                  AND (
                    lower(s.title) LIKE ?
                    OR EXISTS (
                      SELECT 1 FROM artifacts a2
                      WHERE a2.session_id = s.id
                        AND (lower(a2.title) LIKE ? OR lower(a2.id) LIKE ?)
                    )
                  )
                """
                like = f"%{needle}%"
                params.extend([like, like, like])
            count_row = conn.execute(
                f"SELECT COUNT(*) FROM ({base_sql})",
                tuple(params),
            ).fetchone()
            total = int(count_row[0] if count_row else 0)
            # 按「会话下最新文档时间」倒序（与资料库「更新时间」列一致）；无文档时回退 sessions.updated_at
            rows = conn.execute(
                base_sql
                + """
                ORDER BY COALESCE(
                  (SELECT MAX(a3.created_at) FROM artifacts a3 WHERE a3.session_id = s.id),
                  s.updated_at
                ) DESC
                LIMIT ? OFFSET ?
                """,
                (*params, ps, off),
            ).fetchall()
            sessions = [_row_to_session(r) for r in rows if r]
            tree: list[dict[str, Any]] = []
            for sess in sessions:
                sid = str(sess.get("id") or "")
                arts_rows = conn.execute(
                    """
                    SELECT * FROM artifacts WHERE session_id = ?
                    ORDER BY created_at DESC LIMIT 100
                    """,
                    (sid,),
                ).fetchall()
                arts = [_row_to_artifact(r) for r in arts_rows if r]
                if needle:
                    arts = [
                        a
                        for a in arts
                        if needle in str(a.get("title") or "").lower()
                        or needle in str(a.get("id") or "").lower()
                        or needle in str(sess.get("title") or "").lower()
                    ]
                if not arts:
                    continue
                item = {k: v for k, v in sess.items() if k != "body_text"}
                body = str(sess.get("body_text") or "")
                item["body_preview"] = (body[:400] + "…") if len(body) > 400 else body
                item["artifacts"] = arts
                item["artifact_count"] = len(arts)
                tree.append(item)
            return {"sessions": tree, "total": total, "page": pg, "page_size": ps}
        finally:
            conn.close()


def purge_empty_sessions(*, user_id: str = "") -> int:
    """删除没有任何文档的会话档案（保留有文档的会话标题）。返回删除条数。"""
    uid = str(user_id or "").strip()
    n = 0
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            if uid:
                rows = conn.execute(
                    """
                    SELECT s.id FROM sessions s
                    WHERE s.user_id = ?
                      AND NOT EXISTS (
                        SELECT 1 FROM artifacts a WHERE a.session_id = s.id
                      )
                    """,
                    (uid,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT s.id FROM sessions s
                    WHERE NOT EXISTS (
                      SELECT 1 FROM artifacts a WHERE a.session_id = s.id
                    )
                    """
                ).fetchall()
            for row in rows:
                sid = row["id"] if row else ""
                if not sid:
                    continue
                conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
                n += 1
            conn.commit()
        finally:
            conn.close()
    return n


def get_artifact(artifact_id: str) -> dict[str, Any] | None:
    aid = _safe_id(artifact_id)
    if not aid:
        return None
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (aid,)).fetchone()
            return _row_to_artifact(row)
        finally:
            conn.close()


def list_artifacts_by_id_prefix(prefix: str, *, limit: int = 80) -> list[dict[str, Any]]:
    """按 id 前缀列举文档（跨用户，供回填幂等/归属判断）。"""
    pfx = str(prefix or "").strip()
    if not pfx or len(pfx) < 6:
        return []
    # 仅允许安全前缀字符，防 LIKE 注入通配
    if not re.match(r"^[A-Za-z0-9_.:-]{6,80}$", pfx):
        return []
    lim = max(1, min(200, int(limit or 80)))
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            rows = conn.execute(
                """
                SELECT * FROM artifacts
                WHERE id LIKE ? ESCAPE '\\'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (pfx.replace("%", "\\%").replace("_", "\\_") + "%", lim),
            ).fetchall()
            return [_row_to_artifact(r) for r in rows if r]
        finally:
            conn.close()


def _unlink_relpath(relpath: str) -> None:
    rel = str(relpath or "").strip().replace("\\", "/")
    if not rel or ".." in rel.split("/"):
        return
    under = rel[len("space/") :] if rel.startswith("space/") else rel
    if not under.startswith("files/"):
        return
    root = space_root()
    try:
        resolved = (root / under).resolve()
        files_root = (root / "files").resolve()
        if str(resolved).startswith(str(files_root)) and resolved.is_file():
            resolved.unlink()
    except OSError:
        _LOG.debug("space unlink failed rel=%s", relpath, exc_info=True)


def delete_artifact(artifact_id: str, *, user_id: str = "", admin: bool = False) -> bool:
    aid = _safe_id(artifact_id)
    if not aid:
        return False
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (aid,)).fetchone()
            if not row:
                return False
            if not admin and str(user_id or "") and row["user_id"] != str(user_id):
                return False
            sid = row["session_id"]
            rel = row["relpath"]
            conn.execute("DELETE FROM artifacts WHERE id = ?", (aid,))
            _refresh_artifact_count(conn, sid)
            conn.commit()
        finally:
            conn.close()
    _unlink_relpath(rel)
    return True


def delete_session(
    session_id: str,
    *,
    user_id: str = "",
    admin: bool = False,
    cascade_artifacts: bool = True,
) -> bool:
    sid = _safe_id(session_id)
    if not sid:
        return False
    rels: list[str] = []
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
            if not row:
                return False
            if not admin and str(user_id or "") and row["user_id"] != str(user_id):
                return False
            if cascade_artifacts:
                arts = conn.execute(
                    "SELECT id, relpath FROM artifacts WHERE session_id = ?",
                    (sid,),
                ).fetchall()
                for a in arts:
                    rels.append(a["relpath"])
                    conn.execute("DELETE FROM artifacts WHERE id = ?", (a["id"],))
            conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            conn.commit()
        finally:
            conn.close()
    for rel in rels:
        _unlink_relpath(rel)
    return True


def status_counts(*, user_id: str = "", admin_all: bool = False) -> dict[str, Any]:
    uid = str(user_id or "").strip()
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            if admin_all:
                sc = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                ac = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
                bsum = conn.execute("SELECT COALESCE(SUM(bytes),0) FROM artifacts").fetchone()[0]
            else:
                sc = conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (uid,)
                ).fetchone()[0]
                ac = conn.execute(
                    "SELECT COUNT(*) FROM artifacts WHERE user_id = ?", (uid,)
                ).fetchone()[0]
                bsum = conn.execute(
                    "SELECT COALESCE(SUM(bytes),0) FROM artifacts WHERE user_id = ?",
                    (uid,),
                ).fetchone()[0]
            return {
                "sessions": int(sc),
                "artifacts": int(ac),
                "bytes": int(bsum or 0),
            }
        finally:
            conn.close()


def list_expired_session_ids(*, older_than_ts: int, user_id: str = "") -> list[str]:
    """updated_at < older_than_ts 的会话 id。"""
    with _lock:
        conn = _connect()
        try:
            _init_schema(conn)
            if user_id:
                rows = conn.execute(
                    "SELECT id FROM sessions WHERE updated_at < ? AND user_id = ?",
                    (int(older_than_ts), str(user_id)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM sessions WHERE updated_at < ?",
                    (int(older_than_ts),),
                ).fetchall()
            return [str(r["id"]) for r in rows]
        finally:
            conn.close()


def read_artifact_body(artifact: dict[str, Any]) -> str:
    """读取空间内报告等正文；失败返回空串。"""
    rel = str((artifact or {}).get("relpath") or "").strip().replace("\\", "/")
    if not rel or ".." in rel.split("/"):
        return ""
    # 约定 relpath 为 engine/data 下 space/files/...；读时落到 space_root()/files/...
    under = rel
    if under.startswith("space/"):
        under = under[len("space/") :]
    if not under.startswith("files/"):
        return ""
    root = space_root()
    try:
        resolved = (root / under).resolve()
        files_root = (root / "files").resolve()
        if not str(resolved).startswith(str(files_root)):
            return ""
        if resolved.is_file():
            return resolved.read_text(encoding="utf-8")
    except OSError:
        return ""
    return ""


def write_report_file(
    *,
    user_id: str,
    artifact_id: str,
    body: str,
    ext: str = "md",
) -> tuple[str, int]:
    """写入 space/files/{user}/reports/{id}.ext，返回 (相对 engine/data 的 relpath, bytes)。"""
    return write_space_file(
        user_id=user_id,
        artifact_id=artifact_id,
        body=body,
        ext=ext,
        subdir="reports",
    )


# 允许落盘的文本扩展名（源码进资料库用；未知扩展回退 txt）
_SPACE_TEXT_EXTS = frozenset(
    {
        "md",
        "json",
        "txt",
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
        "yaml",
        "yml",
        "toml",
        "ini",
        "cfg",
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
        "svg",
        "r",
        "rb",
        "php",
        "swift",
        "kt",
        "gradle",
        "dockerfile",
    }
)


def write_space_file(
    *,
    user_id: str,
    artifact_id: str,
    body: str,
    ext: str = "md",
    subdir: str = "reports",
) -> tuple[str, int]:
    """写入 space/files/{user}/{subdir}/{id}.ext；路径受前缀校验。"""
    uid = _safe_id(user_id, fallback="anonymous") or "anonymous"
    aid = _safe_id(artifact_id)
    if not aid:
        raise ValueError("invalid artifact_id")
    folder = str(subdir or "reports").strip().lower()
    if folder not in {"reports", "code"}:
        folder = "reports"
    raw_ext = str(ext or "txt").strip().lower().lstrip(".")
    safe_ext = raw_ext if raw_ext in _SPACE_TEXT_EXTS else "txt"
    under = f"files/{uid}/{folder}/{aid}.{safe_ext}"
    path = space_root() / under
    path.parent.mkdir(parents=True, exist_ok=True)
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    relpath = f"space/{under}"
    return relpath, path.stat().st_size

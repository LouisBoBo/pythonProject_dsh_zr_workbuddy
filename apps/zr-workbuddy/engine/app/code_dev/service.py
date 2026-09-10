"""本机写码 Job 执行：沙箱 → Cursor Local → 快照 diff → 受限同步（无提交/预览）。"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import jobs as job_store
from .config import CodeDevConfig, get_config
from .cursor_agent import build_prompt, run_cursor_local_agent, split_delivery_markdown
from .fs_snapshot import deleted_from_snapshots, diff_snapshots, snapshot_sandbox
from .path_scope import partition_by_scope
from .sandbox import apply_deletes_to_target, prepare_sandbox, sync_changed_to_target
from .workspace import validate_workspace

Sink = Callable[[dict[str, Any]], None]

_bg_lock = threading.Lock()
_bg_threads: dict[str, threading.Thread] = {}

_CODE_LANG = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "vue",
    ".py": "python",
    ".json": "json",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sql": "sql",
    ".sh": "bash",
    ".xml": "xml",
    ".toml": "toml",
    ".ini": "ini",
}

_SECRET_NAMES = {".env", ".pem", "id_rsa", "id_ed25519", "credentials.json"}


def _fence_lang(rel: str) -> str:
    return _CODE_LANG.get(Path(rel).suffix.lower(), "text")


def substantial_code_fences(text: str) -> bool:
    """正文里是否已有足够长的代码围栏（避免再贴一遍沙箱文件）。"""
    fences = 0
    body_lines = 0
    in_fence = False
    for line in (text or "").splitlines():
        if line.strip().startswith("```"):
            if in_fence:
                fences += 1
            in_fence = not in_fence
            continue
        if in_fence:
            body_lines += 1
    return fences >= 1 and body_lines >= 24


def build_changed_code_markdown(sandbox: Path, rels: list[str]) -> str:
    """把沙箱里实际改动的文件贴成 Markdown 代码块，保证正文有详细源码。"""
    chunks: list[str] = ["## 改动代码\n"]
    used = 0
    count = 0
    for rel in rels or []:
        if count >= 10 or used >= 60000:
            break
        name = Path(rel).name.lower()
        if name in _SECRET_NAMES or name.endswith(".pem") or name.endswith(".key"):
            continue
        if ".env" in name:
            continue
        path = sandbox / rel
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "\0" in raw[:4096]:
            continue
        if len(raw) > 24000:
            raw = raw[:24000] + "\n/* … 已截断 */\n"
        lang = _fence_lang(rel)
        block = f"`{rel}`\n\n```{lang}\n{raw.rstrip()}\n```\n\n"
        chunks.append(block)
        used += len(block)
        count += 1
    if count == 0:
        return ""
    return "".join(chunks).rstrip() + "\n"


def merge_changed_code_into_text(text: str, sandbox: Path, rels: list[str]) -> str:
    """过程段缺少详细代码时，把沙箱改动文件补进正文（终稿说明方案保持在后）。"""
    proc, delivery = split_delivery_markdown(text or "")
    if substantial_code_fences(proc):
        return text or ""
    extra = build_changed_code_markdown(sandbox, rels)
    if not extra:
        return text or ""
    proc2 = (proc.rstrip() + "\n\n" + extra).strip() if proc.strip() else extra.strip()
    if delivery:
        return proc2 + "\n\n" + delivery
    return proc2


def _data_dir() -> Path:
    # engine/app/code_dev → engine/data
    return Path(__file__).resolve().parents[2] / "data"


def _emit(sink: Sink | None, event: dict[str, Any]) -> None:
    if sink:
        try:
            sink(event)
        except Exception:
            pass


class _LiveProcess:
    """删除任务正文规则：只要 Cursor 对话框；引擎旁白只走 status。

    - wrap_sink：实时透传 Cursor replace_text
    - push：只发 status，不进正文（cursor_only=True）
    - 无 Cursor（已下线/engine_first）：用 set_fact 写一句事实
    """

    def __init__(
        self,
        sink: Sink | None,
        *,
        chunk_chars: int = 16,
        chunk_delay_sec: float = 0.045,
        buffer_then_stream: bool = True,
        cursor_only: bool = True,
    ) -> None:
        self._sink = sink
        self._engine: list[str] = []
        self._blob = ""
        self._cursor_raw = ""
        self._cursor_delivery = ""
        self._last_cursor_emit = ""
        self._queued: list[str] = []
        self._cursor_prose = ""
        self._flushed = False
        self._delivery_held = ""
        self._delivery_blob = ""
        self._delivery_flushed = False
        self._buffer = bool(buffer_then_stream)
        self._cursor_only = bool(cursor_only)
        self._chunk = max(4, int(chunk_chars or 16))
        self._delay = max(0.0, float(chunk_delay_sec or 0.0))

    def _append_stream(self, addition: str) -> None:
        add = str(addition or "")
        if not add:
            return
        for i in range(0, len(add), self._chunk):
            piece = add[i : i + self._chunk]
            self._blob += piece
            _emit(self._sink, {"type": "token", "text": piece})
            if self._delay > 0:
                time.sleep(self._delay)

    def _append_delivery_stream(self, addition: str) -> None:
        add = str(addition or "")
        if not add:
            return
        for i in range(0, len(add), self._chunk):
            piece = add[i : i + self._chunk]
            self._delivery_blob += piece
            _emit(self._sink, {"type": "token_delivery", "text": piece})
            if self._delay > 0:
                time.sleep(self._delay)

    def set(self, text: str) -> None:
        t = str(text or "").strip()
        self._engine = [t] if t else []
        self._queued = [t] if t else []
        self._cursor_prose = ""
        self._flushed = False
        self._blob = ""
        _emit(self._sink, {"type": "replace_text", "text": ""})
        if not self._buffer and t:
            self._append_stream(t)

    def set_fact(self, text: str) -> None:
        """无 Cursor 输出时，正文只留这一句事实（禁止堆引擎套话）。"""
        t = str(text or "").strip()
        if not t:
            return
        self._queued = []
        self._cursor_prose = ""
        self._cursor_raw = ""
        self._last_cursor_emit = ""
        self._blob = ""
        self._flushed = False
        _emit(self._sink, {"type": "replace_text", "text": ""})
        if self._delay > 0:
            time.sleep(min(0.06, self._delay * 2))
        self._append_stream(t)
        self._flushed = True

    def push(self, sentence: str) -> None:
        s = str(sentence or "").strip()
        if not s:
            return
        if not s.endswith(("。", "！", "？", "…")):
            s += "。"
        _emit(self._sink, {"type": "status", "text": s})
        if self._cursor_only:
            return
        if self._engine and (self._engine[-1] == s or s in self._engine[-1]):
            return
        joined = "\n\n".join(self._engine)
        if s in joined[-160:]:
            return
        self._engine.append(s)
        if len(self._engine) > 48:
            self._engine = self._engine[-48:]
        if self._buffer and not self._flushed:
            self._queued.append(s)
            return
        prefix = "\n\n" if self._blob else ""
        self._append_stream(prefix + s)

    def set_cursor(self, text: str) -> None:
        t = str(text or "").strip()
        if t:
            self._cursor_raw = t

    def cursor_raw(self) -> str:
        return str(self._cursor_raw or "")

    def cursor_delivery(self) -> str:
        return str(self._cursor_delivery or "")

    def apply_cursor_dialog(self, cre: dict[str, Any] | None = None, *, raw: str = "") -> None:
        """用 Cursor 对话框正文覆盖过程区（拒绝引擎种子句）。"""
        from .cursor_agent import is_engine_seed_text

        cre = cre if isinstance(cre, dict) else {}

        def _pick(*parts: str) -> str:
            for p in parts:
                s = str(p or "").strip()
                if s and not is_engine_seed_text(s):
                    return s
            return ""

        body = _pick(
            cre.get("process"),
            cre.get("thinking"),
            cre.get("final_text"),
            cre.get("assistant_raw"),
            raw or self._cursor_raw,
            cre.get("text"),
        )
        delivery = str(cre.get("delivery") or "").strip()
        if delivery and not is_engine_seed_text(delivery):
            self._cursor_delivery = delivery
        if not body:
            return
        if "说明方案" in body or "一句话结论" in body or "删除清单" in body or "结论" in body:
            from .cursor_agent import format_cursor_dialog, _split_process_delivery

            pretty_proc, pretty_del = format_cursor_dialog(body)
            if pretty_del and not self._cursor_delivery:
                self._cursor_delivery = pretty_del
            if pretty_proc:
                body = pretty_proc
            elif "说明方案" in body or "一句话结论" in body:
                proc, deliv = _split_process_delivery(body)
                if deliv and not self._cursor_delivery:
                    self._cursor_delivery = deliv
                if proc and not is_engine_seed_text(proc):
                    body = proc
        else:
            from .cursor_agent import dedupe_dialog_sentences

            body = dedupe_dialog_sentences(body)
        self._queued = []
        self._cursor_raw = body
        self._cursor_prose = body
        self._last_cursor_emit = body
        self._blob = body
        self._flushed = False
        _emit(self._sink, {"type": "replace_text", "text": body})

    def reveal_cursor(self, raw: str | None = None) -> None:
        self.apply_cursor_dialog(raw=str(raw if raw is not None else self._cursor_raw or ""))

    def flush_reveal(self) -> None:
        """有 Cursor 则钉住对话框；无则保留 set_fact 已写内容。"""
        if self._flushed:
            return
        self._queued = []
        self._buffer = False
        self._flushed = True
        body = (self._cursor_prose or self._cursor_raw or self._blob or "").strip()
        if body and body != self._blob:
            self._blob = body
            _emit(self._sink, {"type": "replace_text", "text": body})

    def hold_delivery(self, text: str) -> None:
        t = str(text or "").strip()
        if t:
            self._delivery_held = t

    def flush_delivery(self, text: str | None = None, *, force: bool = False) -> None:
        if text is not None:
            t = str(text or "").strip()
            if t:
                self._delivery_held = t
                # 强制用引擎四段式终稿时，清掉 Cursor 短结论，避免薄文盖掉完整模板
                if force:
                    self._cursor_delivery = ""
        full = str(self._cursor_delivery or self._delivery_held or "").strip()
        self._delivery_held = ""
        if self._delivery_flushed and not full:
            return
        self._delivery_flushed = True
        if not full:
            return
        self._delivery_blob = full
        # 结论一次到位：避免先清空再逐字流造成「卡顿后突然出现」
        _emit(self._sink, {"type": "replace_delivery", "text": full})
        # 再发一条 token_delivery 便于前端动画衔接（无 sleep，不重复拼装）
        _emit(self._sink, {"type": "token_delivery", "text": ""})

    def text(self) -> str:
        return self._blob or self._cursor_prose or "\n\n".join(self._queued)

    def wrap_sink(self, *, absorb_cursor_text: bool = False) -> Sink:
        outer = self._sink
        _ = absorb_cursor_text

        def _wrapped(ev: dict[str, Any]) -> None:
            if not isinstance(ev, dict):
                return
            et = str(ev.get("type") or "")
            if et == "replace_text":
                piece = str(ev.get("text") or "").strip()
                if not piece:
                    return
                self._cursor_raw = piece
                if piece == self._last_cursor_emit:
                    return
                self._last_cursor_emit = piece
                self._cursor_prose = piece
                self._blob = piece
                self._queued = []
                _emit(self._sink, {"type": "replace_text", "text": piece})
                return
            if et == "replace_delivery":
                piece = str(ev.get("text") or "").strip()
                if piece:
                    self._cursor_delivery = piece
                return
            if outer:
                try:
                    outer(ev)
                except Exception:
                    pass

        return _wrapped



def _minimal_delete_delivery(
    *,
    feat_label: str,
    forced_deletes: list[str] | None = None,
    patched: list[str] | None = None,
    verify_detail: str = "",
    mode: str = "cursor_plan",
    requirement: str = "",
    process_text: str = "",
) -> str:
    """删除终稿：结论/改动文件/行为约定/验收（与 build_engine_delete_delivery 同模板）。"""
    from .delete_enforce import build_engine_delete_delivery

    req = (requirement or "").strip() or f"下线{feat_label}"
    return build_engine_delete_delivery(
        req,
        forced_deletes=list(forced_deletes or []),
        patched=list(patched or []),
        verify_detail=str(verify_detail or ""),
        mode=mode,
        process_text=str(process_text or ""),
    )


def _merge_runtime_hints(*parts: str) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return "\n\n".join(out)


def _remote_deploy_hint(synced_files: list[str] | None) -> str:
    """若配置了远端 entry_url，提醒本机 sync 不会更新远端界面。"""
    touched = any(
        str(f or "").replace("删除 ", "").startswith("frontend/")
        for f in (synced_files or [])
    )
    if not touched:
        return ""
    try:
        from ..code_deploy.config import get_config as get_deploy_cfg

        dep = get_deploy_cfg()
        if not dep.enabled:
            return ""
        url = str(dep.entry_url or dep.health_url or "").strip()
    except Exception:
        return ""
    if not url or "127.0.0.1" in url or "localhost" in url:
        return ""
    return (
        f"【远端入口 {url}】当前写码只同步到本机工程目录；"
        "若您在浏览器打开的是上述远端地址，界面不会变，须走「部署上线」把改动推到服务器。"
    )


def _append_remote_deploy_hint(runtime_hint: str, synced_files: list[str] | None) -> str:
    return _merge_runtime_hints(runtime_hint, _remote_deploy_hint(synced_files))


def run_job(
    data_dir: Path,
    job: dict[str, Any],
    *,
    sink: Sink | None = None,
    cfg: CodeDevConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or get_config()
    job_id = str(job.get("id") or "")
    if not job_id:
        raise ValueError("job id missing")

    if not cfg.enabled:
        err = "本机写码未开启（config.yaml → code_dev.enabled）"
        job_store.update_job(data_dir, job_id, status="failed", error=err)
        _emit(sink, {"type": "error", "message": err})
        return job_store.get_job(data_dir, job_id) or job

    job_store.update_job(data_dir, job_id, status="running", error=None, runtime="cursor_local")
    _emit(sink, {"type": "status", "text": "本机 Cursor Local 写码开始", "phase": "start"})

    workspace = str(job.get("workspace") or "").strip()
    check = validate_workspace(workspace)
    if not check.get("ok"):
        err = check.get("error") or "目标目录无效"
        job_store.update_job(data_dir, job_id, status="failed", error=err)
        _emit(sink, {"type": "error", "message": err})
        return job_store.get_job(data_dir, job_id) or job

    target = Path(check["path"])
    empty_target = bool(check.get("empty"))
    job_store.update_job(data_dir, job_id, empty_target=empty_target)

    def step(title: str, *, sid: str, state: str = "running") -> None:
        _emit(sink, {"type": "step", "id": sid, "state": state, "title": title})

    try:
        if job_store.is_cancel_requested(data_dir, job_id):
            raise RuntimeError("任务已取消")

        requirement = ""
        for m in reversed(job.get("messages") or []):
            if m.get("role") == "user":
                requirement = str(m.get("content") or "")
                break
        if not requirement.strip():
            raise RuntimeError("需求为空")

        from .brief import is_delete_intent
        from .delete_enforce import plan_delete_file_targets
        from .delete_preflight import audit_delete_target, delivery_indicates_already_done

        step("准备沙箱", sid="sandbox-prep")
        scope_for_copy = list(job.get("write_scope") or [])
        if is_delete_intent(requirement):
            delete_targets = plan_delete_file_targets(requirement, target)
            scope_for_copy = list(
                dict.fromkeys(
                    [
                        *scope_for_copy,
                        *delete_targets,
                        "frontend/src/layouts/AppLayout.vue",
                        "frontend/src/router/index.js",
                    ]
                )
            )
        meta = prepare_sandbox(
            data_dir,
            job_id,
            target,
            empty_target=empty_target,
            cfg=cfg,
            on_progress=lambda t: step(t, sid="sandbox-prep"),
            include_rels=scope_for_copy or None,
        )
        sandbox_path = Path(meta["sandbox"])
        job_store.update_job(
            data_dir,
            job_id,
            sandbox_path=str(sandbox_path),
            sandbox_mode=meta.get("mode"),
            sandbox_copied_files=meta.get("copied_files"),
        )
        step(
            f"沙箱就绪（{meta.get('mode') or 'copy'} · {meta.get('copied_files') or 0} 文件）",
            sid="sandbox-prep",
            state="done",
        )

        preflight_skipped = False
        assistant_text = ""
        agent_id = ""
        forced_deletes: list[str] = []
        engine_patched: list[str] = []
        live = _LiveProcess(
            sink,
            chunk_chars=12,
            chunk_delay_sec=float(getattr(cfg, "live_stream_delay_sec", 0.045) or 0.0),
            buffer_then_stream=bool(is_delete_intent(requirement)),
            cursor_only=bool(is_delete_intent(requirement)),
        )
        delete_mode = str(cfg.delete_mode or "cursor_plan").strip().lower()
        if delete_mode not in {"cursor_plan", "engine_first", "cursor_full"}:
            delete_mode = "cursor_plan"
        before = snapshot_sandbox(sandbox_path)

        if is_delete_intent(requirement):
            from .delete_enforce import (
                build_engine_delete_delivery,
                parse_delete_plan_from_text,
                plan_delete_file_targets,
                reconcile_delete_artifacts,
                restore_sandbox_scope_from_target,
                validate_delete_plan,
            )
            from .delete_verify import extract_delete_features, verify_delete_on_target
            from .cursor_agent import build_delete_plan_prompt

            feat_list0 = extract_delete_features(requirement)
            feat_label = "、".join(feat_list0) if feat_list0 else "目标功能"
            live.push(f"开始处理删除诉求：下线「{feat_label}」")

            scope_for_restore = list(
                dict.fromkeys(
                    [
                        *(job.get("write_scope") or []),
                        "frontend/src/layouts/AppLayout.vue",
                        "frontend/src/router/index.js",
                    ]
                )
            )

            if delete_mode == "engine_first":
                step("引擎删除（跳过 Cursor）", sid="agent-loop", state="running")
                live.set_fact(f"引擎已直接删除「{feat_label}」（未调用 Cursor）。")
                rec = reconcile_delete_artifacts(
                    sandbox=sandbox_path,
                    target=target,
                    requirement=requirement,
                    assistant_text="",
                    sink=sink,
                )
                forced_deletes = list(rec.get("forced_deletes") or [])
                engine_patched = list(rec.get("patched") or [])
                for rel in forced_deletes[:12]:
                    live.push(f"已删除 `{rel}`")
                if engine_patched:
                    live.push("已修补菜单与路由：\n" + "\n".join(f"`{p}`" for p in engine_patched[:6]))
                live.push("正在本机验尸，确认菜单/路由/页面已消失")
                tv = verify_delete_on_target(
                    target,
                    requirement,
                    synced_files=engine_patched,
                    deleted_files=forced_deletes,
                )
                if not tv.get("ok"):
                    raise RuntimeError(
                        f"引擎删除后验收未通过：{tv.get('detail') or ''}"
                        "请检查工程路径或手动确认待删功能名。"
                    )
                live.push("本机验尸通过，删除目标已达成")
                assistant_text = build_engine_delete_delivery(
                    requirement,
                    forced_deletes=forced_deletes,
                    patched=engine_patched,
                    verify_detail=str(tv.get("detail") or ""),
                    mode="engine_first",
                )
                live.hold_delivery(assistant_text)
                step("引擎删除完成", sid="agent-loop", state="done")
            elif delete_mode == "cursor_plan":
                tv_pre = verify_delete_on_target(target, requirement)
                feat_list = feat_list0
                # 仅当验尸明确「已不存在」且能解析叶子功能名时才跳过；inconclusive/仍有命中必须继续删
                if tv_pre.get("ok") and feat_list and not tv_pre.get("inconclusive"):
                    preflight_skipped = True
                    step("本机验尸：目标已下线", sid="delete-plan", state="done")
                    step("无需再删", sid="delete-exec", state="skipped")
                    live.set_fact(f"本机已无「{feat_label}」，本次未调用 Cursor。")
                    assistant_text = build_engine_delete_delivery(
                        requirement,
                        forced_deletes=[],
                        patched=[],
                        verify_detail=str(tv_pre.get("detail") or ""),
                        mode="already_done",
                    )
                    live.hold_delivery(assistant_text)
                    step("同步（无变更）", sid="sync", state="skipped")
                else:
                    step("Cursor 定位待删文件（只读）…", sid="delete-plan", state="running")
                    _emit(sink, {"type": "status", "text": "正在调用 Cursor 只读定位（正文将同步对话框输出）"})
                    plan_prompt = build_delete_plan_prompt(
                        requirement=requirement,
                        workspace_hint=str(target),
                    )
                    cre = run_cursor_local_agent(
                        sandbox=sandbox_path,
                        prompt=plan_prompt,
                        sink=live.wrap_sink(),
                        step=step,
                        is_cancel_requested=lambda: job_store.is_cancel_requested(data_dir, job_id),
                        timeout_sec=min(cfg.delete_plan_timeout_sec, cfg.delete_verify_timeout_sec),
                        max_read_tools=min(16, cfg.max_read_tools),
                        read_only=True,
                    )
                    from .cursor_agent import is_engine_seed_text, looks_like_delete_plan_reply

                    plan_text = str(cre.get("text") or "") if cre.get("ok") else ""
                    if is_engine_seed_text(plan_text):
                        plan_text = ""
                    # 用 Cursor 对话框正文覆盖过程区（拒绝种子句；优先 thinking）
                    live.apply_cursor_dialog(cre if isinstance(cre, dict) else None, raw=plan_text or live.cursor_raw())
                    body_now = str(live.text() or "").strip()
                    if not body_now or is_engine_seed_text(body_now):
                        think = str((cre or {}).get("thinking") or "").strip()
                        proc = str((cre or {}).get("process") or "").strip()
                        if think and not is_engine_seed_text(think):
                            live.apply_cursor_dialog({"process": think, "thinking": think})
                        elif proc and not is_engine_seed_text(proc):
                            live.apply_cursor_dialog({"process": proc})
                        else:
                            err = str((cre or {}).get("error") or "").strip()
                            if err:
                                live.set_fact(f"Cursor 未能产出对话框正文：{err[:220]}")
                            else:
                                live.set_fact("Cursor 未输出对话框正文；已改用引擎规则整理删除清单。")
                    if not cre.get("ok"):
                        _emit(
                            sink,
                            {
                                "type": "status",
                                "text": f"Cursor 定位未完成（{cre.get('error') or '超时'}），改用引擎规则清单。",
                            },
                        )
                    plan_ok = bool(plan_text) and looks_like_delete_plan_reply(plan_text)
                    # 即使 plan 文案不完整，只要有真实 Cursor 正文也算定位有输出
                    if not plan_ok and cre.get("ok") and (
                        str(cre.get("process") or "").strip()
                        or str(cre.get("thinking") or "").strip()
                    ):
                        # 仍用引擎规则删，但正文已保留 Cursor 输出
                        pass
                    step(
                        "定位完成" if plan_ok else "定位未完成，改用引擎规则",
                        sid="delete-plan",
                        state="done" if plan_ok else "skipped",
                    )
                    cursor_paths = parse_delete_plan_from_text(plan_text if plan_ok else "")
                    approved, rejected = validate_delete_plan(
                        cursor_paths,
                        requirement,
                        target,
                        write_scope=list(job.get("write_scope") or []),
                    )
                    if rejected:
                        live.push("部分路径已拦截，不纳入删除：" + "；".join(rejected[:3]))
                        _emit(
                            sink,
                            {
                                "type": "status",
                                "text": "以下路径未纳入删除（已拦截）：" + "；".join(rejected[:6]),
                            },
                        )
                    if not approved:
                        tv_empty = verify_delete_on_target(target, requirement)
                        if tv_empty.get("ok") and feat_list and not tv_empty.get("inconclusive"):
                            preflight_skipped = True
                            step("本机已达成目标", sid="delete-exec", state="done")
                            live.set_fact(f"本机已无「{feat_label}」，本次未调用 Cursor 写删。")
                            assistant_text = build_engine_delete_delivery(
                                requirement,
                                forced_deletes=[],
                                patched=[],
                                verify_detail=str(tv_empty.get("detail") or ""),
                                mode="already_done",
                            )
                            live.hold_delivery(assistant_text)
                            step("同步（无变更）", sid="sync", state="skipped")
                        else:
                            # Cursor 空清单：回退引擎规则清单（避免品质子页在 production/ 时直接失败）
                            floor = plan_delete_file_targets(requirement, target)
                            live.push(
                                "Cursor 删除清单为空，改用引擎规则清单"
                                + (f"（{len(floor)} 项）" if floor else "（仅修补菜单/路由）")
                            )
                            _emit(
                                sink,
                                {
                                    "type": "status",
                                    "text": (
                                        "Cursor 删除清单为空，改用引擎规则清单"
                                        + (f"（{len(floor)} 项）" if floor else "（仅修补菜单/路由）")
                                        + "。"
                                    ),
                                },
                            )
                            restore_sandbox_scope_from_target(
                                sandbox_path,
                                target,
                                scope_for_restore + floor,
                            )
                            step("引擎校验并执行删除…", sid="delete-exec", state="running")
                            live.push("阶段 2/2：引擎校验清单并执行删除与菜单修补")
                            rec = reconcile_delete_artifacts(
                                sandbox=sandbox_path,
                                target=target,
                                requirement=requirement,
                                assistant_text=plan_text,
                                explicit_planned=floor,
                                sink=sink,
                            )
                            forced_deletes = list(rec.get("forced_deletes") or [])
                            engine_patched = list(rec.get("patched") or [])
                            for rel in forced_deletes[:12]:
                                live.push(f"已删除 `{rel}`")
                            if engine_patched:
                                live.push("已修补菜单与路由：\n" + "\n".join(f"`{p}`" for p in engine_patched[:6]))
                            live.push("正在本机验尸，确认菜单/路由/页面已消失")
                            tv = verify_delete_on_target(
                                target,
                                requirement,
                                synced_files=engine_patched,
                                deleted_files=forced_deletes,
                            )
                            if not tv.get("ok"):
                                detail = str(tv.get("detail") or "").strip()
                                rej = "；".join(rejected[:4]) if rejected else ""
                                raise RuntimeError(
                                    "删除清单为空且引擎回退后本机仍可检出待删功能。"
                                    + (f"验尸：{detail}。" if detail else "")
                                    + (f"拦截：{rej}。" if rej else "")
                                    + "请补充功能名、检查 write_scope 或工程路径。"
                                )
                            live.push("本机验尸通过，删除目标已达成")
                            assistant_text = build_engine_delete_delivery(
                                requirement,
                                forced_deletes=forced_deletes,
                                patched=engine_patched,
                                verify_detail=str(tv.get("detail") or "") + "；引擎规则回退",
                                mode="cursor_plan",
                                process_text=str(plan_text or live.text() or ""),
                            )
                            live.hold_delivery(assistant_text)
                            step("引擎删除完成", sid="delete-exec", state="done")
                    else:
                        restore_sandbox_scope_from_target(
                            sandbox_path,
                            target,
                            scope_for_restore + approved,
                        )
                        step("引擎校验并执行删除…", sid="delete-exec", state="running")
                        live.push(
                            f"阶段 2/2：引擎将删除 {len(approved)} 个文件并修补菜单/路由"
                        )
                        for rel in approved[:10]:
                            live.push(f"准备删除 `{rel}`")
                        _emit(
                            sink,
                            {
                                "type": "status",
                                "text": "引擎将删除 "
                                + str(len(approved))
                                + " 个文件并修补菜单/路由："
                                + "、".join(approved[:8])
                                + ("…" if len(approved) > 8 else ""),
                            },
                        )
                        rec = reconcile_delete_artifacts(
                            sandbox=sandbox_path,
                            target=target,
                            requirement=requirement,
                            assistant_text=plan_text,
                            explicit_planned=approved,
                            sink=sink,
                        )
                        forced_deletes = list(rec.get("forced_deletes") or [])
                        engine_patched = list(rec.get("patched") or [])
                        for rel in forced_deletes[:12]:
                            live.push(f"已删除 `{rel}`")
                        if engine_patched:
                            live.push("已修补菜单与路由：\n" + "\n".join(f"`{p}`" for p in engine_patched[:6]))
                        live.push("正在本机验尸，确认菜单/路由/页面已消失")
                        tv = verify_delete_on_target(
                            target,
                            requirement,
                            synced_files=engine_patched,
                            deleted_files=forced_deletes,
                        )
                        if not tv.get("ok"):
                            raise RuntimeError(
                                f"引擎删除后验收未通过：{tv.get('detail') or ''}"
                                "请核对 Cursor 清单或改 delete_mode。"
                            )
                        live.push("本机验尸通过，删除目标已达成")
                        assistant_text = build_engine_delete_delivery(
                            requirement,
                            forced_deletes=forced_deletes,
                            patched=engine_patched,
                            verify_detail=(
                                str(tv.get("detail") or "")
                                + (f"；Cursor 清单 {len(approved)} 项" if plan_text else "；引擎规则清单")
                            ),
                            mode="cursor_plan",
                            process_text=str(plan_text or live.text() or ""),
                        )
                        live.hold_delivery(assistant_text)
                        step("引擎删除完成", sid="delete-exec", state="done")
            else:
                audit = audit_delete_target(target, requirement)
                if cfg.delete_preflight_auto_skip and audit.get("skip_cursor"):
                    preflight_skipped = True
                    assistant_text = str(audit.get("delivery") or "")
                    step("本机预检：目标已下线", sid="cursor-local", state="running")
                    live.set_fact(f"本机已无「{feat_label}」，预检跳过 Cursor。")
                    live.hold_delivery(assistant_text)
                    step("预检跳过 Cursor", sid="cursor-local", state="done")
                    step("写码（已跳过）", sid="agent-loop", state="skipped")
                    step("同步（无变更）", sid="sync", state="skipped")
                else:
                    step("Cursor 在沙箱内改码…", sid="agent-loop")
                    prompt = build_prompt(
                        requirement=requirement,
                        workspace_hint=str(target),
                        empty_target=empty_target,
                    )
                    cre = run_cursor_local_agent(
                        sandbox=sandbox_path,
                        prompt=prompt,
                        sink=sink,
                        step=step,
                        is_cancel_requested=lambda: job_store.is_cancel_requested(data_dir, job_id),
                        timeout_sec=min(cfg.cursor_timeout_sec, cfg.delete_verify_timeout_sec),
                        max_read_tools=cfg.max_read_tools,
                    )
                    if not cre.get("ok"):
                        err = str(cre.get("error") or "Cursor 本机写码失败")
                        step("Cursor 失败，尝试引擎兜底删除…", sid="agent-loop", state="running")
                        rec = reconcile_delete_artifacts(
                            sandbox=sandbox_path,
                            target=target,
                            requirement=requirement,
                            assistant_text=str(cre.get("text") or ""),
                            sink=sink,
                        )
                        forced_deletes = list(rec.get("forced_deletes") or [])
                        patched = list(rec.get("patched") or [])
                        tv_fb = verify_delete_on_target(
                            target,
                            requirement,
                            deleted_files=forced_deletes,
                        )
                        if tv_fb.get("ok"):
                            assistant_text = build_engine_delete_delivery(
                                requirement,
                                forced_deletes=forced_deletes,
                                patched=patched,
                                verify_detail=f"（Cursor 未成功：{err}；已由引擎兜底完成）",
                            )
                            live.hold_delivery(assistant_text)
                            step("引擎兜底删除完成", sid="agent-loop", state="done")
                        else:
                            raise RuntimeError(err)
                    else:
                        assistant_text = str(cre.get("text") or "")
                        agent_id = str(cre.get("agent_id") or "")
                        if agent_id:
                            job_store.update_job(data_dir, job_id, agent_id=agent_id)
                        step("沙箱内改码完成", sid="agent-loop", state="done")
        else:
            prompt = build_prompt(
                requirement=requirement,
                workspace_hint=str(target),
                empty_target=empty_target,
            )
            step("Cursor 在沙箱内改码…", sid="agent-loop")
            cre = run_cursor_local_agent(
                sandbox=sandbox_path,
                prompt=prompt,
                sink=sink,
                step=step,
                is_cancel_requested=lambda: job_store.is_cancel_requested(data_dir, job_id),
                timeout_sec=cfg.cursor_timeout_sec,
                max_read_tools=cfg.max_read_tools,
            )
            if not cre.get("ok"):
                raise RuntimeError(cre.get("error") or "Cursor 本机写码失败")
            assistant_text = str(cre.get("text") or "")
            agent_id = str(cre.get("agent_id") or "")
            if agent_id:
                job_store.update_job(data_dir, job_id, agent_id=agent_id)
            step("沙箱内改码完成", sid="agent-loop", state="done")

        if is_delete_intent(requirement) and not preflight_skipped and delete_mode == "cursor_full":
            rec = reconcile_delete_artifacts(
                sandbox=sandbox_path,
                target=target,
                requirement=requirement,
                assistant_text=assistant_text,
                sink=sink,
            )
            forced_deletes = list(dict.fromkeys([*forced_deletes, *(rec.get("forced_deletes") or [])]))
            detail = str(rec.get("detail") or "").strip()
            if detail:
                _emit(sink, {"type": "status", "text": detail})

        after = snapshot_sandbox(sandbox_path)
        changed = diff_snapshots(before, after)
        deleted = deleted_from_snapshots(before, after)
        if forced_deletes:
            deleted = sorted(set(deleted) | set(forced_deletes))
        if engine_patched:
            changed = sorted(set(changed) | set(engine_patched))
        # 删除任务：禁止把沙箱源码灌进正文（会覆盖 LiveProcess 流式过程）
        if not is_delete_intent(requirement):
            merged_text = merge_changed_code_into_text(assistant_text, sandbox_path, changed)
            if merged_text and merged_text != assistant_text:
                from .cursor_agent import _sanitize_delivery_body, _split_process_delivery, _strip_all_code_from_body

                proc, delivery = _split_process_delivery(merged_text)
                proc = _strip_all_code_from_body(proc)
                delivery = _sanitize_delivery_body(delivery) if delivery else ""
                assistant_text = "\n\n".join(p for p in (proc, delivery) if p).strip() or merged_text
                if proc:
                    _emit(sink, {"type": "replace_text", "text": proc})
                if delivery:
                    _emit(sink, {"type": "replace_delivery", "text": delivery})
        else:
            live.push("正在同步到本机工程并验尸")
        all_rels = list(dict.fromkeys([*changed, *deleted]))
        if len(all_rels) > cfg.max_changed_files:
            raise RuntimeError(
                f"变更文件过多（{len(all_rels)}>{cfg.max_changed_files}），已中止同步以防误伤"
            )

        scope = job.get("write_scope") or []
        inside, outside = partition_by_scope(
            all_rels,
            scope,
            sandbox_root=sandbox_path,
        )
        # P0：范围外文件不同步（记入 deferred），不进入 awaiting_scope（无 SPA 卡）
        # 若触及路由/布局/config，同批 views 已由 partition 强制提升，避免「写完看不见」
        from .path_scope import is_ui_shell_wiring

        leftover_wiring = [r for r in outside if is_ui_shell_wiring(r)]
        if leftover_wiring:
            inside = list(dict.fromkeys([*inside, *leftover_wiring]))
            outside = [r for r in outside if r not in set(leftover_wiring)]

        changed_set = set(changed)
        deleted_set = set(deleted)
        if not changed_set and not deleted_set:
            if is_delete_intent(requirement):
                from .delete_verify import verify_delete_on_target

                tv_pre = verify_delete_on_target(target, requirement)
                if not tv_pre.get("ok"):
                    raise RuntimeError(
                        "Cursor 未产生变更且本机仍可检出待删功能。"
                        f"{tv_pre.get('detail') or ''}请重新开工或补充需求。"
                    )
            elif not (preflight_skipped or delivery_indicates_already_done(assistant_text)):
                raise RuntimeError(
                    "Cursor 在沙箱内未产生任何文件变更，本机工程不会被修改。"
                    "常见原因：仍在读盘定位、需求未写清改哪些菜单/文件、或 Cursor 未完成写入。"
                    "请核对工程路径与需求摘要后重新开工。"
                )
        inside_copy = [rel for rel in inside if rel in changed_set]
        inside_del = [rel for rel in inside if rel in deleted_set]
        synced: list[str] = []
        deleted_ok: list[str] = []
        runtime_hint = ""
        target_verify_detail = ""
        if inside_copy:
            step(f"同步 {len(inside_copy)} 个文件到目标目录…", sid="sync")
            synced = sync_changed_to_target(sandbox_path, target, inside_copy, cfg=cfg)
        if inside_del:
            step(f"从目标目录删除 {len(inside_del)} 个文件…", sid="sync-del")
            deleted_ok = apply_deletes_to_target(target, inside_del)
            synced.extend(f"删除 {p}" for p in deleted_ok)
        for rel in forced_deletes:
            if rel not in deleted_ok:
                deleted_ok.append(rel)
            tag = f"删除 {rel}"
            if tag not in synced:
                synced.append(tag)
        if inside_copy or inside_del or forced_deletes:
            step("同步完成", sid="sync", state="done")
        elif preflight_skipped and is_delete_intent(requirement):
            step("同步（无变更）", sid="sync", state="skipped")
        elif outside:
            sample = "、".join(outside[:8])
            raise RuntimeError(
                f"有 {len(outside)} 个文件已在沙箱改动，但因 write_scope 限制未同步到本机：{sample}。"
                "改菜单/路由须同步 router 与 layouts；请重新开工或缩小范围后重试。"
            )

        from .brief import append_sync_mismatch_warning, validate_delete_completion
        from .delete_verify import frontend_runtime_hint, verify_delete_on_target, verify_sync_to_target
        from .vite_reload import nudge_vite_after_sync

        runtime_hint = ""
        target_verify_detail = ""
        if is_delete_intent(requirement):
            step("验尸：核对本机菜单/路由/页面…", sid="sync", state="running")
            tv = verify_delete_on_target(
                target,
                requirement,
                synced_files=synced,
                deleted_files=deleted_ok,
            )
            if not tv.get("ok"):
                raise RuntimeError(
                    f"删除验收失败：{tv.get('detail')}。"
                    "磁盘上仍可检出待删功能，请勿信任「已同步」提示，请重新开工。"
                )
            target_verify_detail = str(tv.get("detail") or "")
            runtime_hint = str(tv.get("runtime_hint") or "")
            live.push("本机验尸通过，删除流程完成")
            if preflight_skipped and not runtime_hint:
                from .delete_verify import runtime_hint_always

                runtime_hint = runtime_hint_always()
            if inside_copy or inside_del:
                sv = verify_sync_to_target(target, sandbox_path, inside_copy, inside_del)
                if not sv.get("ok"):
                    raise RuntimeError(f"同步验尸失败：{sv.get('detail')}")
            # 删除后唤醒 Vite，避免用户重启 npm run dev
            nudge = nudge_vite_after_sync(
                target,
                synced_files=synced,
                deleted_files=deleted_ok,
                force=True,
            )
            if nudge.get("ok") and not nudge.get("skipped"):
                if nudge.get("restarted"):
                    step(
                        "已自动软重启 Vite（硬刷新浏览器即可）",
                        sid="sync",
                    )
                else:
                    step("已触发 Vite 热更新（刷新即可）", sid="sync")
            runtime_hint = _merge_runtime_hints(
                runtime_hint,
                frontend_runtime_hint(synced, deleted_ok),
                _remote_deploy_hint(synced),
            )
            step("本机验尸通过", sid="sync", state="done")
        elif inside_copy or inside_del:
            sv = verify_sync_to_target(target, sandbox_path, inside_copy, inside_del)
            if not sv.get("ok"):
                raise RuntimeError(f"同步验尸失败：{sv.get('detail')}")
            nudge_vite_after_sync(
                target,
                synced_files=synced,
                deleted_files=deleted_ok,
                force=False,
            )
            runtime_hint = frontend_runtime_hint(synced, deleted_ok)
            runtime_hint = _append_remote_deploy_hint(runtime_hint, synced)

        # 硬门禁：接线/config 不得留在 deferred；新增菜单/报表须本机 catalog 可见
        from .menu_verify import deferred_wiring_blockers, verify_add_menu_on_target

        wiring_left = deferred_wiring_blockers(outside)
        if wiring_left:
            raise RuntimeError(
                "菜单/路由配置未同步到本机，禁止报成功："
                + "、".join(wiring_left[:8])
                + "。请重新开工（write_scope 须含 frontend/src/config/ 与 router）。"
            )
        if not is_delete_intent(requirement) and (inside_copy or inside_del or outside):
            mv = verify_add_menu_on_target(
                target,
                requirement,
                synced_files=synced,
                deferred_files=outside,
            )
            if not mv.get("ok"):
                raise RuntimeError(f"菜单验尸失败：{mv.get('detail')}")
            if mv.get("detail"):
                target_verify_detail = str(mv.get("detail") or "")

        delete_err = validate_delete_completion(
            requirement,
            assistant_text,
            deleted_ok,
            target_root=target,
            forced_deletes=forced_deletes,
        )
        if delete_err:
            raise RuntimeError(delete_err)

        mismatch = append_sync_mismatch_warning(
            {
                "messages": job.get("messages") or [],
                "synced_files": synced,
                "brief": job.get("brief"),
            }
        )

        # 删除任务：正文保留 Cursor 对话框；结论用四段式模板（结论/改动文件/行为约定/验收）
        if is_delete_intent(requirement):
            from .cursor_agent import format_cursor_dialog, is_engine_seed_text
            from .delete_enforce import build_engine_delete_delivery

            live.flush_reveal()
            body_now = str(live.text() or "").strip()
            if is_engine_seed_text(body_now):
                live.set_fact("Cursor 未输出对话框正文；执行结果见结论与改动文件。")
            else:
                prose = str(live.cursor_raw() or live.text() or "").strip()
                if prose and not is_engine_seed_text(prose):
                    pretty_proc, _pretty_del = format_cursor_dialog(prose)
                    if pretty_proc and pretty_proc != prose:
                        live.apply_cursor_dialog({"process": pretty_proc})

            if preflight_skipped:
                deliv_mode = "already_done"
            elif str(delete_mode or "") == "engine_first":
                deliv_mode = "engine_first"
            else:
                deliv_mode = "cursor_plan"
            rich = build_engine_delete_delivery(
                requirement,
                forced_deletes=list(deleted_ok or forced_deletes or []),
                patched=list(
                    dict.fromkeys(
                        [
                            *(engine_patched or []),
                            *[
                                str(s)
                                for s in (synced or [])
                                if s
                                and not str(s).startswith("删除 ")
                                and str(s) not in set(deleted_ok or [])
                            ],
                        ]
                    )
                ),
                verify_detail=str(target_verify_detail or ""),
                mode=deliv_mode,
                process_text=str(live.cursor_raw() or live.text() or ""),
            )
            live.flush_delivery(rich, force=True)

        job_store.update_job(
            data_dir,
            job_id,
            status="succeeded",
            error=None,
            changed_files=changed,
            deleted_files=deleted_ok,
            synced_files=synced,
            deferred_files=outside,
            sync_mismatch=mismatch or None,
            target_verify_detail=target_verify_detail or None,
            runtime_hint=runtime_hint or None,
        )
        assistant_body = assistant_text + (
            f"\n\n【同步】写入 {len(synced) - len(deleted_ok)} 个"
            + (f"；删除 {len(deleted_ok)} 个" if deleted_ok else "")
            + (f"；范围外未同步 {len(outside)} 个" if outside else "")
            + (f"\n\n{target_verify_detail}" if target_verify_detail else "")
            + (f"\n\n{runtime_hint}" if runtime_hint else "")
            + (f"\n\n{mismatch}" if mismatch else "")
        )
        job_store.append_message(
            data_dir,
            job_id,
            role="assistant",
            content=assistant_body,
        )
        _emit(
            sink,
            {
                "type": "done",
                "ok": True,
                "synced_files": synced,
                "deleted_files": deleted_ok,
                "deferred_files": outside,
            },
        )
        return job_store.get_job(data_dir, job_id) or job

    except Exception as exc:  # noqa: BLE001
        err = str(exc) or type(exc).__name__
        if job_store.is_cancel_requested(data_dir, job_id):
            job_store.update_job(data_dir, job_id, status="cancelled", error=err)
        else:
            job_store.update_job(data_dir, job_id, status="failed", error=err)
        _emit(sink, {"type": "error", "message": err})
        return job_store.get_job(data_dir, job_id) or job


def reconcile_stale_jobs(data_dir: Path, *, reason: str = "引擎重启，任务已中断") -> int:
    """引擎进程重启后：磁盘上仍为 queued/running、但无存活后台线程的任务标为已取消。"""
    with _bg_lock:
        alive_ids = {jid for jid, t in _bg_threads.items() if t.is_alive()}
    n = 0
    for job in job_store.list_jobs(data_dir, statuses={"queued", "running"}):
        jid = str(job.get("id") or "")
        if not jid or jid in alive_ids:
            continue
        job_store.request_cancel(data_dir, jid, reason=reason)
        n += 1
    return n


def start_job_background(data_dir: Path, job_id: str) -> None:
    """后台线程跑 Job；同 id 不重复启动。进度经 sink 写入 job 供面板轮询/SSE。"""

    def _sink(event: dict[str, Any]) -> None:
        try:
            job_store.record_event(data_dir, job_id, event)
        except Exception:
            pass

    def _run() -> None:
        try:
            claimed = job_store.try_claim_job(data_dir, job_id)
            if not claimed:
                return
            run_job(data_dir, claimed, sink=_sink)
        finally:
            with _bg_lock:
                _bg_threads.pop(job_id, None)

    with _bg_lock:
        t_old = _bg_threads.get(job_id)
        if t_old and t_old.is_alive():
            return
        t = threading.Thread(target=_run, name=f"code-dev-{job_id}", daemon=True)
        _bg_threads[job_id] = t
        t.start()


def default_data_dir() -> Path:
    return _data_dir()

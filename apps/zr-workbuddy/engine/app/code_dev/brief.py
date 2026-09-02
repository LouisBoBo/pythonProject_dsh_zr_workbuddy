"""写码需求简报：跨轮次累积、保真、校验（产品级）。"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

_OPTIONS_PREFIX = "【写码需求选项已确认】"
_MAX_GOAL_LEN = 4000
_MAX_NOTE_LEN = 2000
_MAX_SELECTION_ROUNDS = 24
_MAX_SELECTION_LINES = 80
_MAX_NOTES = 20

_PATH_RE = re.compile(
    r"(/(?:Users|home|opt|var/www|data)[^\s，。；;]+|[A-Za-z]:\\[^\s，。；;]+)"
)

# 过泛的 LLM 摘要（易改错模块）
_GENERIC_PATTERNS = (
    r"在项目内实现一个列表页",
    r"对接现有后端接口",
    r"查询列表数据、新增/编辑保存、删除数据",
    r"接口字段以现有后端协议为准",
    r"按已确认选项完成本机写码",
)

MODULE_HINTS: list[dict[str, Any]] = [
    {
        "module": "报表中心",
        "keywords": ("报表中心", "工时报表", "员工工时", "日产报表", "在制品报表", "reports/"),
        "paths": (
            "frontend/src/views/reports/",
            "frontend/src/router/index.js",
            "frontend/src/layouts/AppLayout.vue",
            "frontend/src/api/reports.js",
            "backend/app/routers/reports.py",
        ),
    },
    {
        "module": "消息中心",
        "keywords": ("消息中心", "消息列表", "已读", "未读", "messages"),
        "paths": (
            "frontend/src/views/messages/",
            "frontend/src/api/messages.js",
            "backend/app/routers/messages.py",
        ),
    },
    {
        "module": "生产管理",
        "keywords": ("生产", "工单", "production", "work_order"),
        "paths": (
            "frontend/src/views/production/",
            "backend/app/routers/work_orders.py",
        ),
    },
    {
        "module": "系统设置",
        "keywords": ("系统设置", "settings", "配置中心"),
        "paths": (
            "frontend/src/views/settings/",
            "backend/app/routers/settings.py",
        ),
    },
]


@dataclass
class CodeDevBrief:
    original_goal: str = ""
    workspace: str = ""
    selections: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    option_rounds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CodeDevBrief:
        if not data or not isinstance(data, dict):
            return cls()
        try:
            rounds = int(data.get("option_rounds") or 0)
        except (TypeError, ValueError):
            rounds = 0
        rounds = max(0, min(rounds, _MAX_SELECTION_ROUNDS))
        selections: list[dict[str, Any]] = []
        for sel in list(data.get("selections") or [])[:_MAX_SELECTION_ROUNDS]:
            if not isinstance(sel, dict):
                continue
            lines = [str(ln).strip()[:512] for ln in (sel.get("lines") or []) if str(ln).strip()]
            selections.append({"round": sel.get("round"), "lines": lines[:20]})
        notes = [
            str(n).strip()[:_MAX_NOTE_LEN]
            for n in (data.get("notes") or [])[:_MAX_NOTES]
            if str(n).strip()
        ]
        return cls(
            original_goal=str(data.get("original_goal") or "").strip()[:_MAX_GOAL_LEN],
            workspace=str(data.get("workspace") or "").strip()[:512],
            selections=selections,
            notes=notes,
            option_rounds=rounds,
        )


def _strip_options_prefix(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith(_OPTIONS_PREFIX):
        return raw[len(_OPTIONS_PREFIX) :].strip()
    return raw


def parse_options_confirm_lines(text: str) -> list[str]:
    body = _strip_options_prefix(text)
    return [ln.strip() for ln in body.splitlines() if ln.strip()]


def extract_workspace_from_text(text: str) -> str:
    m = _PATH_RE.search(text or "")
    if not m:
        return ""
    return m.group(1).rstrip("。．，,；;）)」」\"'")


def is_options_confirm_message(text: str) -> bool:
    return bool((text or "").strip().startswith(_OPTIONS_PREFIX))


def is_generic_requirement(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    # 服务端 canonical 需求（含原始诉求块）不按「通用 CRUD 模板」拦截
    if "【原始诉求】" in raw and "【硬性约束】" in raw:
        return False
    hits = sum(1 for p in _GENERIC_PATTERNS if re.search(p, raw))
    if hits >= 2:
        return True
    if hits >= 1 and len(raw) < 160:
        return True
    return False


def _goal_tokens(goal: str) -> list[str]:
    """从原始诉求提取用于校验的关键词片段。"""
    g = (goal or "").strip()
    if not g:
        return []
    parts = re.split(r"[\s，。；;、/|]+", g)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2:
            out.append(p)
    if len(g) >= 4:
        out.append(g[: min(24, len(g))])
    return out[:12]


def merge_brief(
    client_brief: dict[str, Any] | None,
    text: str,
    *,
    workspace: str = "",
) -> CodeDevBrief:
    """合并客户端累积简报与当前消息。"""
    brief = CodeDevBrief.from_dict(client_brief)
    raw = (text or "").strip()
    ws = (workspace or extract_workspace_from_text(raw) or brief.workspace or "").strip()
    if ws:
        brief.workspace = ws

    if is_options_confirm_message(raw):
        lines = parse_options_confirm_lines(raw)[:_MAX_SELECTION_LINES]
        brief.option_rounds = min(brief.option_rounds + 1, _MAX_SELECTION_ROUNDS)
        brief.selections = (brief.selections or [])[-(_MAX_SELECTION_ROUNDS - 1) :]
        brief.selections.append({"round": brief.option_rounds, "lines": lines})
        for ln in lines:
            if ln.startswith("备注："):
                note = ln[3:].strip()[:_MAX_NOTE_LEN]
                if note and note not in brief.notes:
                    brief.notes = (brief.notes or [])[-(_MAX_NOTES - 1) :]
                    brief.notes.append(note)
        return brief

    # 首轮或补充说明：记为原始诉求（勿用确认卡/ canonical 长文覆盖）
    if raw and not raw.startswith("【写码确认】"):
        if "【原始诉求】" in raw or "【硬性约束】" in raw:
            return brief
        candidate = raw[:_MAX_GOAL_LEN]
        if not brief.original_goal or len(candidate) > len(brief.original_goal):
            if len(candidate) >= 6:
                brief.original_goal = candidate
    return brief


def infer_target(brief: CodeDevBrief) -> dict[str, Any]:
    """从简报推断目标模块与预期改动区域。"""
    corpus = " ".join(
        [brief.original_goal]
        + [ln for s in brief.selections for ln in (s.get("lines") or [])]
        + brief.notes
    ).lower()

    best: dict[str, Any] | None = None
    best_score = 0
    for hint in MODULE_HINTS:
        score = sum(1 for kw in hint["keywords"] if kw.lower() in corpus)
        if score > best_score:
            best_score = score
            best = hint

    if not best or best_score == 0:
        return {
            "module": "",
            "confidence": "low",
            "expected_paths": [],
            "keywords": [],
        }

    confidence = "high" if best_score >= 2 else "medium"
    return {
        "module": best["module"],
        "confidence": confidence,
        "expected_paths": list(best["paths"]),
        "keywords": [kw for kw in best["keywords"] if kw.lower() in corpus],
    }


def ready_to_propose(brief: CodeDevBrief) -> bool:
    """是否已够信息、应直接出确认卡（少轮询）。"""
    goal = (brief.original_goal or "").strip()
    if len(goal) < 8:
        return False
    hints = infer_target(brief)
    if hints.get("confidence") == "high" and brief.option_rounds >= 1:
        return True
    if brief.option_rounds >= 2:
        return True
    # 原始诉求已含模块+动作，且至少一轮勾选
    if brief.option_rounds >= 1 and hints.get("module") and re.search(
        r"(新增|增加|开发|实现|菜单|页面|接口)", goal
    ):
        return True
    return False


def build_requirement(brief: CodeDevBrief, llm_requirement: str = "") -> str:
    """构建发给 Cursor 的 canonical 需求（必须含原始诉求）。"""
    hints = infer_target(brief)
    parts: list[str] = []

    goal = (brief.original_goal or "").strip()
    if goal:
        parts.append(f"【原始诉求】{goal}")

    for sel in brief.selections:
        for ln in sel.get("lines") or []:
            if ln.startswith("工程路径："):
                continue
            if ln and ln not in parts:
                parts.append(ln)

    if brief.notes:
        parts.append("【备注】" + "；".join(brief.notes))

    llm = (llm_requirement or "").strip()
    if llm and not is_generic_requirement(llm):
        if goal not in llm and llm not in goal:
            parts.append(f"【实现要点】{llm}")

    parts.append("【硬性约束】")
    parts.append("必须完整实现「原始诉求」中的业务目标；禁止改错模块或只做无关模块的通用 CRUD。")
    if hints.get("module"):
        parts.append(f"目标业务模块：{hints['module']}。")
    if hints.get("expected_paths"):
        parts.append("预期主要改动区域（仅供参考，可增减）：")
        for p in hints["expected_paths"][:8]:
            parts.append(f"  - {p}")

    parts.append("【验收】")
    parts.append("1) 菜单/路由/页面与原始诉求一致；2) 接口与页面联调可用；3) 勿改动无关模块。")
    return "\n".join(parts)


def validate_requirement_for_start(
    brief: CodeDevBrief,
    requirement: str,
) -> dict[str, Any]:
    """开工前校验；errors 阻断，warnings 需用户勾选确认。"""
    req = (requirement or "").strip()
    hints = infer_target(brief)
    errors: list[str] = []
    warnings: list[str] = []

    if len(req) < 40:
        errors.append("需求摘要过短，请补充业务模块与验收点。")

    goal = (brief.original_goal or "").strip()
    if goal and goal not in req and "【原始诉求】" not in req:
        errors.append("需求摘要须包含原始诉求（勿删除「原始诉求」段落或关键业务名称）。")

    if is_generic_requirement(req):
        if hints.get("module"):
            errors.append(
                f"需求摘要过于笼统（像通用列表页 CRUD），请明确「{hints['module']}」下的具体页面与接口。"
            )
        else:
            errors.append("需求摘要过于笼统，请在备注中写明业务模块、页面名称与接口路径。")

    # 原始诉求关键词应出现在最终需求中
    if goal and hints.get("keywords"):
        missing = [kw for kw in hints["keywords"][:4] if kw.lower() not in req.lower()]
        if len(missing) >= 2:
            errors.append(f"摘要偏离原始诉求（缺少：{'、'.join(missing[:3])}）。")
    elif goal:
        tokens = _goal_tokens(goal)
        hit = sum(1 for t in tokens if t.lower() in req.lower())
        if tokens and hit == 0:
            errors.append("需求摘要未体现原始诉求中的业务名称，请补全后再开工。")

    if not goal and brief.option_rounds >= 1:
        warnings.append("未记录首轮原始诉求，请确认需求摘要是否完整。")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "target_hints": hints,
    }


def validate_synced_files(
    brief: CodeDevBrief,
    requirement: str,
    synced_files: list[str],
) -> dict[str, Any]:
    """任务完成后：同步文件是否落在预期模块。"""
    hints = infer_target(brief)
    module = hints.get("module") or ""
    paths = hints.get("expected_paths") or []
    synced = [str(f).replace("\\", "/") for f in (synced_files or []) if f]

    if not module or not synced or not paths:
        return {"ok": True, "mismatch": False, "detail": ""}

    def in_expected(rel: str) -> bool:
        rel = rel.replace("\\", "/")
        for p in paths:
            prefix = p.rstrip("/")
            if rel == prefix or rel.startswith(prefix + "/"):
                return True
        return False

    matched = [f for f in synced if in_expected(f)]
    if matched:
        return {"ok": True, "mismatch": False, "detail": ""}

    # 明显改错模块：如目标是报表中心，却只改了 messages
    wrong_prefix = ""
    for f in synced:
        if "messages" in f and module == "报表中心":
            wrong_prefix = "messages"
            break
        if "reports" in f and module == "消息中心":
            wrong_prefix = "reports"
            break

    detail = (
        f"⚠️ 同步文件与目标模块「{module}」不一致（改动落在 {wrong_prefix or '其它区域'}）。"
        f"已同步：{'、'.join(synced[:5])}。请核对需求摘要或重新写码。"
    )
    return {"ok": False, "mismatch": True, "detail": detail}


def write_scope_from_hints(hints: dict[str, Any]) -> list[str]:
    """高置信度时自动限制同步范围，防止改错模块。"""
    if hints.get("confidence") != "high":
        return []
    out: list[str] = []
    for p in hints.get("expected_paths") or []:
        rel = str(p).replace("\\", "/").strip()
        if rel.endswith("/"):
            out.append(rel)
        elif rel:
            out.append(rel)
    return out[:12]


def infer_target_from_text(*texts: str) -> dict[str, Any]:
    """从需求正文复验目标模块（降低仅伪造 client brief 的风险）。"""
    corpus = " ".join(t for t in texts if t).strip()
    if not corpus:
        return {"module": "", "confidence": "low", "expected_paths": [], "keywords": []}
    return infer_target(CodeDevBrief(original_goal=corpus[:800]))


def append_sync_mismatch_warning(
    job: dict[str, Any],
    *,
    brief_dict: dict[str, Any] | None = None,
) -> str:
    """终态：同步文件是否与目标模块一致。"""
    brief = CodeDevBrief.from_dict(brief_dict or job.get("brief"))
    req = ""
    for m in job.get("messages") or []:
        if m.get("role") == "user":
            req = str(m.get("content") or "")
            break
    check = validate_synced_files(brief, req, job.get("synced_files") or [])
    if check.get("mismatch"):
        return check.get("detail") or ""
    return ""

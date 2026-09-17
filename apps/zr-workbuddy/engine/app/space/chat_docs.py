"""从本机 DSH session.jsonl 抽出聊天产出的文档进资料库（只读投影，fail-soft）。

只收：创作类 AIGC（《标题》/童话故事等）、测试用例/规格等实质文档。
不收：写码/提交结论、菜单增删完成确认、工具卡状态、闲聊说明、
      **知识库/文档检索问答**（RAG 召回、源自《…》标准答案、工业 FAQ 提纲）。
绑定真实 session-uuid。聊天扫描不收工程源码；写码同步源码另走 hooks.ingest_code_dev_job。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

from ..usage.ingest_dsh_llm import _iter_lines, _iter_session_files, _session_id_from_path, _sessions_root
from . import catalog
from .config import get_space_config
from .dsh_locate import looks_like_dsh_session_id
from .hooks import ingest_chat_document

_LOG = logging.getLogger(__name__)

_DOC_HINT = re.compile(
    r"(测试用例|用例说明|验收标准|测试步骤|测试点|Given|When|Then|"
    r"规格说明|设计说明|检查表|SOP|操作手册|需求规格)",
    re.I,
)
_CREATIVE_HINT = re.compile(
    r"(童话|故事|小说|散文|诗歌|诗篇|寓言|剧本|短篇|微小说|作文|"
    r"小红帽|续写一个|改写成|童话故事|恐怖故事|科幻短篇)",
    re.I,
)
# 仅书名号《》——「」在中文里常用于菜单/路径引用，不能当创作标记
_CREATIVE_BOOK = re.compile(r"《[^》]{1,40}》")
# 书名号若是「引用资料」而非作品标题，不算创作
_BOOK_CITATION = re.compile(
    r"(源自|来自|参考|根据|见|摘自|引自|出处)[《「『]|"
    r"标准答案[（(]?源自|"
    r"[《「『][^》」』]{1,40}[》」』].{0,12}(FMEA|文档|手册|规范|规则|报价|"
    r"第[一二三四五六七八九十百零\d]+[节章条])",
    re.I,
)

# 知识库 / 文档检索生成的问答——一律不进资料库
_KB_RETRIEVAL = re.compile(
    r"("
    r"源自《|来自《|参考《|根据《|摘自《|引自《|"
    r"知识库|知识文档|知识问答|挂载召回|召回片段|文档检索|检索到以下|"
    r"根据(?:你的)?知识|相关文档如下|根据挂载|"
    r"FMEA\s*标准答案|标准答案[（(]?源自|"
    r"P0\s*最着急|直接卡出货|"
    r"(?:一|二|三)、.{0,40}权重\s*\d+\s*%|"
    r"计价规则|失效模式|潜在后果|检验关卡|成本内核|"
    r"专属.?计费|二钻\s*/\s*二锣|二锣计价|压合板计价|"
    r"(?:一|二|三)、.{0,20}公式\b|"
    r"报价规则|铜价折算|半固化片|PP\s*片|"
    r"\d+\s*元\s*/\s*(?:㎡|张|pcs|PCS)|元/㎡|元/张"
    r")",
    re.I,
)
# 工业问答提纲（无创作意图）：「一、二、」+ 领域词 → 视为检索/FAQ
_KB_OUTLINE = re.compile(r"(?m)^[一二三四五六七八九十]+、")
_KB_DOMAIN = re.compile(
    r"(合格率|计价规则|加工费|计费项|失效模式|潜在后果|V\s*割|检验关卡|压合板|沉金|"
    r"FMEA|出货|客诉|锣带|二钻|二锣|成本内核|铜价|报价|表面处理|压合)",
    re.I,
)

# 车道结论 / 工具卡 / 菜单操作完成确认 / 闲聊——一律不进
_OPS_NOISE = re.compile(
    r"("
    r"本轮结论|做了什么|改动方案|提交完成|写码已完成|已同步到本机|同步到本机|"
    r"交付小结|任务已完成|已取消写码|部署完成|确认卡|路径票据|path_ticket|"
    r"synced_files|已同步：|先确认需求|code_dev\.disabled|写码车道|"
    r"无法生成写码|工具卡|待审同步|job\s*`?ccj-|Cursor\s*写码|"
    r"已完成删除|已删除完成|彻底移除|彻底删除|处理完毕|执行完毕|"
    r"菜单入口|菜单项\s*\+|对应页面文件|页面文件一起删|入口\s*\+\s*页面|"
    r"已从「[^」]+」删除|已在「[^」]+」(?:下)?新增|已按你的|"
    r"写码通道结果|没有改动任何文件|我不是替代\s*Cursor|不是\s*Cursor|"
    r"不再继续动了|核对本机工程|前端构建通过|本地项目落地"
    r")",
    re.I,
)
_LANE_HEADING = re.compile(
    r"(?m)^#{1,3}\s*(本轮结论|做了什么|改动方案|提交完成|下一步|风险|已同步|先确认需求)\b",
)
_EIGHT_D_ID = re.compile(r"8D-[A-Za-z0-9._-]{4,80}")
_CR_ID = re.compile(r"报告 ID：`?(cr-[a-f0-9]{8,})")
_MIN_DOC_CHARS = 400
_MIN_CREATIVE_CHARS = 120


def _title_from_body(text: str) -> str:
    for line in str(text or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            t = re.sub(r"^#+\s*", "", s).strip()
            if t:
                return t[:200]
    for line in str(text or "").splitlines():
        s = line.strip()
        if s:
            # 去掉加粗标记便于标题展示
            return re.sub(r"^\*\*|\*\*$", "", s).strip()[:200]
    return "聊天文档"


def is_ops_noise(text: str) -> bool:
    """操作状态 / 车道结论 / 菜单增删确认 / 闲聊——不应进资料库。"""
    body = str(text or "").strip()
    if not body:
        return True
    title = _title_from_body(body)
    if _OPS_NOISE.search(title):
        return True
    if _LANE_HEADING.search(body):
        return True
    if _OPS_NOISE.search(body):
        # 创作正文里偶尔提到「菜单」不算；有书名号创作或明确创作词则放行
        if _is_creative_body(body):
            return False
        return True
    return False


def is_knowledge_retrieval(text: str) -> bool:
    """知识库/文档检索生成的问答（RAG、标准答案、工业 FAQ 提纲）——不应进资料库。"""
    body = str(text or "").strip()
    if not body:
        return False
    if _KB_RETRIEVAL.search(body):
        return True
    if _BOOK_CITATION.search(body):
        return True
    if _CREATIVE_HINT.search(body):
        return False
    outlines = _KB_OUTLINE.findall(body)
    # 多级提纲 + 工业域词；或单条「一、…」标题本身已带域词（资料库列表常见）
    if _KB_DOMAIN.search(body) and (len(outlines) >= 2 or (len(outlines) >= 1 and len(body) < 800)):
        return True
    return False


def _is_creative_body(body: str) -> bool:
    if _CREATIVE_HINT.search(body):
        return True
    if _CREATIVE_BOOK.search(body) and not _BOOK_CITATION.search(body):
        return True
    return False


def looks_like_chat_document(text: str) -> bool:
    """仅创作类 AIGC 或实质规格/用例文档。"""
    body = str(text or "").strip()
    if not body:
        return False
    if is_ops_noise(body):
        return False
    if is_knowledge_retrieval(body):
        return False
    # 创作：书名号《》或创作关键词（引用资料的《》不算）
    if _is_creative_body(body):
        return len(body) >= _MIN_CREATIVE_CHARS
    if len(body) < _MIN_DOC_CHARS:
        return False
    if "def test_" in body:
        return True
    if _DOC_HINT.search(body):
        return True
    return False


def _assistant_text(obj: dict[str, Any]) -> tuple[str, str]:
    msg = (obj.get("data") or {}).get("message") or {}
    mid = str(msg.get("id") or "").strip()
    parts: list[str] = []
    content = msg.get("content")
    if not isinstance(content, list):
        return mid, ""
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return mid, "\n".join(parts).strip()


def _artifact_id(session_id: str, message_id: str, body: str) -> str:
    mid = re.sub(r"[^A-Za-z0-9_-]", "", message_id)[:36]
    if mid:
        return f"chat-{mid}"
    digest = hashlib.sha1(f"{session_id}\n{body[:800]}".encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"chat-{digest}"


def _already_covered_elsewhere(body: str) -> bool:
    m = _EIGHT_D_ID.search(body or "")
    if m and catalog.get_artifact(m.group(0)):
        return True
    m2 = _CR_ID.search(body or "")
    if m2 and catalog.get_artifact(m2.group(1)):
        return True
    return False


def purge_ops_noise_artifacts(*, user_id: str = "") -> int:
    """清掉误入库的操作状态/结论类、以及知识库检索问答类 chat_document。"""
    n = 0
    try:
        arts = catalog.list_artifacts(user_id=user_id or "", limit=200, offset=0)
        for art in arts:
            if not isinstance(art, dict):
                continue
            if str(art.get("kind") or "") != "chat_document":
                continue
            title = str(art.get("title") or "")
            try:
                body = catalog.read_artifact_body(art) or ""
            except Exception:
                body = title
            sample = (title + "\n" + (body or "")[:3000]).strip()
            if (
                is_ops_noise(sample)
                or is_knowledge_retrieval(sample)
                or not looks_like_chat_document(body or title)
            ):
                if catalog.delete_artifact(str(art.get("id") or ""), user_id=user_id or "", admin=False):
                    n += 1
    except Exception:
        _LOG.debug("purge ops/knowledge noise artifacts failed", exc_info=True)
    return n


def sync_chat_docs_from_dsh(user_id: str = "") -> dict[str, Any]:
    """扫描本机 DSH 会话，只把创作/实质文档写入资料库。失败不抛。"""
    out: dict[str, Any] = {"ok": True, "scanned": 0, "ingested": 0, "skipped": 0, "purged": 0}
    try:
        cfg = get_space_config()
        if cfg.get("sync_chat_docs") is False:
            return out
        uid = str(user_id or "").strip()
        if not uid:
            return {**out, "ok": False, "detail": "no user"}
        out["purged"] = purge_ops_noise_artifacts(user_id=uid)
        try:
            out["purged_empty_sessions"] = catalog.purge_empty_sessions(user_id=uid)
        except Exception:
            out["purged_empty_sessions"] = 0
        root = _sessions_root()
        try:
            files = sorted(
                _iter_session_files(root),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            files = []
        deadline = time.time() + 4.0
        max_chars = int(cfg.get("max_session_body_chars") or 65536)
        for path in files[:80]:
            if time.time() > deadline:
                break
            sid = looks_like_dsh_session_id(_session_id_from_path(path))
            if not sid:
                continue
            existing_sess = catalog.get_session(sid)
            if existing_sess:
                owner = str(existing_sess.get("user_id") or "").strip()
                if owner and owner != uid:
                    out["skipped"] += 1
                    continue
            out["scanned"] += 1
            title = ""
            try:
                for line in _iter_lines(path):
                    if '"session/title"' not in line and '"assistant/message"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    typ = obj.get("type")
                    if typ == "session/title":
                        t = str(((obj.get("data") or {}) or {}).get("title") or "").strip()
                        if t:
                            title = t
                        continue
                    if typ != "assistant/message":
                        continue
                    mid, body = _assistant_text(obj)
                    if not looks_like_chat_document(body):
                        out["skipped"] += 1
                        continue
                    if _already_covered_elsewhere(body):
                        out["skipped"] += 1
                        continue
                    aid = _artifact_id(sid, mid, body)
                    prev_art = catalog.get_artifact(aid)
                    if prev_art:
                        prev_owner = str(prev_art.get("user_id") or "").strip()
                        if prev_owner and prev_owner != uid:
                            out["skipped"] += 1
                            continue
                        out["skipped"] += 1
                        continue
                    ingest_chat_document(
                        user_id=uid,
                        session_id=sid,
                        session_title=title or sid,
                        artifact_id=aid,
                        title=_title_from_body(body),
                        body=body,
                        max_chars=max_chars,
                    )
                    out["ingested"] += 1
            except Exception:
                out["skipped"] += 1
                _LOG.debug("space sync chat docs one session failed path=%s", path, exc_info=True)
    except Exception:
        _LOG.warning("space sync_chat_docs_from_dsh failed", exc_info=True)
        return {**out, "ok": False}
    return out


# 兼容旧名
is_lane_conclusion = is_ops_noise
purge_lane_conclusion_artifacts = purge_ops_noise_artifacts

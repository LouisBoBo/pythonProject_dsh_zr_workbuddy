"""加载 .dsh/skills/zr-workbuddy-code-review（Viprasol + 门禁），供引擎 LLM 使用。

禁止在业务代码里自造审查原则；方法论以 Skill 文件为准。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# apps/zr-workbuddy/engine/app/code_review → 仓库根
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SKILL_DIR = _REPO_ROOT / ".dsh" / "skills" / "zr-workbuddy-code-review"

_MACHINE_BLOCK = """
## 本批机器输出约定（引擎解析用，必须遵守）

你正在审查**本批已提供的源码正文**（系统已分批读取，无需再调工具）。

1. 严格按上方 Viprasol + workbuddy-gate-90 做审查（正确性→安全→性能→可维护性/风格）。
2. 用户可见文字用中文；不要输出报告大标题（系统汇总时套壳）。
3. severity 与报告 band：
   - critical / high → 高危 P0（仅真实可利用安全/正确性硬伤）
   - medium → 中危 P1（规范、性能隐患、可维护性、非立即利用的安全债）
   - low → 低危 P2（命名、注释、风格、小幅可读性）
4. **禁止把命名/注释/缩进/风格标成 critical 或 high**；这类必须用 low。
5. **禁止整批复审只出 P0**：若本批有真实非阻塞问题，必须同时写入 medium/low；
   只有本批确实无中低危时才可省略。安全硬伤仍必须报。
6. 每条 finding 尽量含：触发条件、问题代码片段、修复建议、修复代码、验证思路。
7. **必须**在摘要后输出机器块（不要用 markdown 代码围栏包住 JSON）：

:::code_review_findings
[{"file":"相对路径","line":12,"severity":"medium","title":"简短标题","description":"错在哪/为何危险/触发条件","code_snippet":"原文片段","fix_suggestion":"怎么改与如何验证","fix_code":"可粘贴修复示例"}]
:::

severity 只能是：critical、high、medium、low（也可用 P0/P1/P2，引擎会映射）。
8. **禁止偷懒空数组**：OpenAPI / Nginx / Docker Compose / 鉴权 / 公网 URL / 明文 http /
   硬编码密钥 / 未鉴权接口 等真实风险必须写入 findings；只有真正审完且确认无问题才可用 []。
9. 本批无问题则 findings 为 []，仍必须输出该机器块。
10. **若模型有思考/reasoning 通道**：最终中文摘要与 :::code_review_findings 必须出现在最终正文；
    禁止只写在思考过程里。思考可以简短，把额度留给 findings JSON。
""".strip()


def skill_dir() -> Path:
    return _SKILL_DIR


@lru_cache(maxsize=1)
def load_review_skill_texts() -> tuple[str, str, str]:
    """返回 (skill_md, viprasol_md, gate90_md)；缺文件时对应空串。"""
    skill = _SKILL_DIR / "SKILL.md"
    vip = _SKILL_DIR / "references" / "viprasol-skill.md"
    gate = _SKILL_DIR / "references" / "workbuddy-gate-90.md"

    def _read(p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return ""

    return _read(skill), _read(vip), _read(gate)


@lru_cache(maxsize=1)
def build_review_system_prompt() -> str:
    """拼装引擎 LLM system prompt：Skill 薄封装 + Viprasol + gate-90 + 机器块。"""
    skill_md, vip_md, gate_md = load_review_skill_texts()
    if not vip_md.strip():
        # 兜底极短提示（仅当 Skill 文件丢失时）
        return (
            "你是专业代码审查员。优先正确性与安全（OWASP/CWE），再性能与可维护性。"
            "输出中文摘要，并附 :::code_review_findings JSON 数组。\n"
            + _MACHINE_BLOCK
        )

    parts = [
        "你是 ZR-WorkBuddy 本机代码审查员。以下方法论来自官方 Skill（Viprasol MIT + 公司门禁），"
        "**不得自行发明另一套检查清单**。",
        "",
        "=== SKILL.md（薄封装）===",
        skill_md.strip(),
        "",
        "=== references/viprasol-skill.md（上游全文，必须执行）===",
        vip_md.strip(),
        "",
        "=== references/workbuddy-gate-90.md（公司门禁叠层，必须执行）===",
        gate_md.strip(),
        "",
        "=== 引擎取码说明 ===",
        "本环境无 VS Code Bridge：源码已由引擎 local_files 分批提供在用户消息中。"
        "gate-90 中「经 Bridge 取码」改为「审阅下方 FILE 正文」；依赖/配置文件若本批未出现，"
        "在摘要中声明未覆盖即可，勿假装已审。",
        "",
        _MACHINE_BLOCK,
    ]
    return "\n".join(parts)


def clear_skill_cache() -> None:
    load_review_skill_texts.cache_clear()
    build_review_system_prompt.cache_clear()

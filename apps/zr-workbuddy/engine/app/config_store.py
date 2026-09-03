"""配置存储：YAML 读写、默认模板、密钥脱敏与合并。"""

import os
import shutil
from copy import deepcopy
from typing import Any, Dict, List, Tuple

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.yaml")
BACKUP_PATH = CONFIG_PATH + ".bak"

MASK = "••••••••"

# 需要脱敏的字段路径（界面回显时打码；保存时若传入打码值则保留原值）
SECRET_PATHS: List[Tuple[str, ...]] = [
    ("mes", "password"),
    ("mes", "token"),
    ("deepseek", "api_key"),
    ("code_dev", "cursor_api_key"),
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "mes": {
        "base_url": "",
        "auth_type": "password",  # password | token | apikey | none
        "username": "",
        "password": "",
        "token": "",
        "enterprise_code": "江西中软",  # MES 登录企业编码
        "extra_headers": "{}",    # JSON 字符串，如 {"X-Tenant": "xxx"}
        "verify_ssl": True,
        "timeout": 30,
    },
    "api_docs": {
        # endpoint: {name, method, path, table, desc}
        "endpoints": [
            {"name": "工单列表", "method": "GET", "path": "", "table": "work_orders",
             "desc": "按时间范围拉取生产工单"},
            {"name": "设备事件", "method": "GET", "path": "", "table": "equipment_events",
             "desc": "设备运行/停机事件记录"},
            {"name": "质检记录", "method": "GET", "path": "", "table": "quality_records",
             "desc": "检验与不良记录"},
        ],
        "raw_docs": "",  # 粘贴的接口文档原文，供后续分析
    },
    "data_dictionary": {
        # 每张标准表的字段映射: {mes_field, std_field, type, desc}
        "work_orders": [
            {"mes_field": "工单号", "std_field": "work_order_no", "type": "文本", "desc": ""},
            {"mes_field": "产品编码", "std_field": "product_code", "type": "文本", "desc": ""},
            {"mes_field": "产品名称", "std_field": "product_name", "type": "文本", "desc": ""},
            {"mes_field": "产线", "std_field": "line_name", "type": "文本", "desc": ""},
            {"mes_field": "班次", "std_field": "shift", "type": "文本", "desc": ""},
            {"mes_field": "计划数量", "std_field": "planned_qty", "type": "数值", "desc": ""},
            {"mes_field": "实际数量", "std_field": "actual_qty", "type": "数值", "desc": ""},
            {"mes_field": "开始时间", "std_field": "start_time", "type": "时间", "desc": ""},
            {"mes_field": "结束时间", "std_field": "end_time", "type": "时间", "desc": ""},
            {"mes_field": "状态", "std_field": "status", "type": "文本", "desc": ""},
        ],
        "equipment_events": [
            {"mes_field": "设备编码", "std_field": "equipment_code", "type": "文本", "desc": ""},
            {"mes_field": "设备名称", "std_field": "equipment_name", "type": "文本", "desc": ""},
            {"mes_field": "产线", "std_field": "line_name", "type": "文本", "desc": ""},
            {"mes_field": "事件类型", "std_field": "event_type", "type": "文本",
             "desc": "运行/停机/维修/待机等"},
            {"mes_field": "开始时间", "std_field": "start_time", "type": "时间", "desc": ""},
            {"mes_field": "结束时间", "std_field": "end_time", "type": "时间", "desc": ""},
            {"mes_field": "时长(分钟)", "std_field": "duration_min", "type": "数值", "desc": ""},
        ],
        "quality_records": [
            {"mes_field": "工单号", "std_field": "work_order_no", "type": "文本", "desc": ""},
            {"mes_field": "产品编码", "std_field": "product_code", "type": "文本", "desc": ""},
            {"mes_field": "检验时间", "std_field": "inspect_time", "type": "时间", "desc": ""},
            {"mes_field": "抽检数", "std_field": "sample_qty", "type": "数值", "desc": ""},
            {"mes_field": "不良数", "std_field": "defect_qty", "type": "数值", "desc": ""},
            {"mes_field": "缺陷类型", "std_field": "defect_type", "type": "文本", "desc": ""},
        ],
    },
    "deepseek": {
        "provider": "deepseek",   # deepseek（OpenAI 兼容 API）| ollama（本地模型）| none
        "api_key": "",
        "base_url": "https://api.deepseek.com",  # deepseek 默认；ollama 填 http://127.0.0.1:11434
        "model": "deepseek-chat",  # deepseek 默认；ollama 填已拉取的模型名，如 qwen2.5:7b
    },
    # P0-1 本机 Cursor Local 写码（默认关闭，避免误改工程）
    "code_dev": {
        "enabled": False,
        "cursor_api_key": "",
        "model": "composer-2.5",
        "max_concurrent": 1,
        "cursor_timeout_sec": 2700,
        "default_workspace": "",
    },
    # P0-3 本机目录直读审码（默认关闭；无 Git / 无 IDE Bridge）
    "code_review": {
        "enabled": False,
        "max_files": 40,
        "max_file_bytes": 120000,
        "max_total_bytes": 800000,
        "default_workspace": "",
    },
}


def _deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    """递归合并：source 覆盖 target（标量/列表直接替换）。"""
    for k, v in source.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            _deep_merge(target[k], v)
        else:
            target[k] = deepcopy(v)


def _get(node: Dict[str, Any], path: Tuple[str, ...]):
    cur = node
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _set(node: Dict[str, Any], path: Tuple[str, ...], value: Any) -> None:
    cur = node
    for k in path[:-1]:
        cur = cur.setdefault(k, {})
    cur[path[-1]] = value


def load_config() -> Dict[str, Any]:
    """读取配置；不存在则写入默认模板（含数据字典示例）。"""
    if not os.path.exists(CONFIG_PATH):
        save_config(deepcopy(DEFAULT_CONFIG))
    with open(CONFIG_PATH, encoding="utf-8") as f:
        raw = f.read()
    cfg = raw and yaml_safe_load(raw) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    merged = deepcopy(DEFAULT_CONFIG)
    _deep_merge(merged, cfg)
    return merged


def save_config(cfg: Dict[str, Any]) -> None:
    """写入配置（先备份旧文件）。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        shutil.copy2(CONFIG_PATH, BACKUP_PATH)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("# DSH-ZR-WorkBuddy / ZR-WorkBuddy 配置\n")
        f.write("# 由配置界面写入，包含密钥，请勿外传/提交版本库\n")
        f.write(yaml_dump(cfg))


def mask_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """回显用：密钥字段打码。"""
    out = deepcopy(cfg)
    for path in SECRET_PATHS:
        v = _get(out, path)
        if v:
            _set(out, path, MASK)
    return out


def merge_secrets(saved: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """把界面提交的配置合并到已保存配置上：
    - 非密钥字段：以界面提交为准
    - 密钥字段：提交值为打码值 → 保留原值；空字符串 → 清空；其他 → 更新
    """
    merged = deepcopy(saved)
    if isinstance(incoming, dict):
        _deep_merge(merged, incoming)
    for path in SECRET_PATHS:
        inv = _get(incoming, path)
        if inv is None:
            continue
        if inv == MASK:
            keep = _get(saved, path) or ""
            _set(merged, path, keep)
        else:
            _set(merged, path, inv)
    return merged


def yaml_safe_load(text: str):
    import yaml
    return yaml.safe_load(text)


def yaml_dump(cfg: Dict[str, Any]) -> str:
    import yaml
    return yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)

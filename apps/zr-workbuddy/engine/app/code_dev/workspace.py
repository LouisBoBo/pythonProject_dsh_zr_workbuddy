"""校验用户确认的本机目标目录。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import FORBIDDEN_TARGET_PREFIXES

# 顶层出现任一即可认定「像工程」
_PROJECT_FILES = frozenset(
    {
        "package.json",
        "pnpm-workspace.yaml",
        "lerna.json",
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "Pipfile",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "CMakeLists.txt",
        "Makefile",
        "composer.json",
        "Gemfile",
        "mix.exs",
        "manage.py",
        "tsconfig.json",
        "vite.config.js",
        "vite.config.ts",
        "vite.config.mjs",
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
        "nuxt.config.js",
        "nuxt.config.ts",
        "docker-compose.yml",
        "docker-compose.yaml",
    }
)

_PROJECT_DIR_NAMES = frozenset(
    {
        "frontend",
        "backend",
        "src",
        "app",
        "apps",
        "lib",
        "cmd",
        "internal",
        "packages",
        "services",
    }
)

_CODE_SUFFIXES = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".vue",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".rb",
        ".php",
        ".swift",
    }
)

_WIDE_HOME_CHILDREN = frozenset(
    {
        "Desktop",
        "Documents",
        "Downloads",
        "Library",
        "Pictures",
        "Movies",
        "Music",
        "Public",
        "Applications",
    }
)


def normalize_workspace(path: str) -> Path:
    raw = (path or "").strip()
    if not raw:
        raise ValueError("本地目录不能为空")
    p = Path(raw).expanduser()
    # 禁止未解析的相对路径作为目标（避免歧义）
    if not p.is_absolute():
        raise ValueError("请填写绝对路径（例如 /Users/你/项目）")
    return p.resolve(strict=False)


def _is_forbidden_target(root: Path) -> str | None:
    s = str(root)
    # 禁止根目录本身
    if s in {"/", "/Users", "/home", "/Volumes", "/tmp", "/private/tmp"}:
        return f"不能选择系统根或用户根目录：{s}"
    for prefix in FORBIDDEN_TARGET_PREFIXES:
        if s == prefix or s.startswith(prefix + os.sep):
            return f"目标目录落在敏感系统路径下：{prefix}"

    # 禁止家目录本身及过宽根（须落到具体工程子目录）
    try:
        home = Path.home().resolve()
        if root == home:
            return "不能选择用户家目录，请选择具体工程文件夹"
        # /Users/<name> 或 /home/<name>
        parts = root.parts
        if len(parts) == 3 and parts[1] in {"Users", "home"}:
            return "不能选择用户主目录，请选择其下的具体工程路径"
        for wide in _WIDE_HOME_CHILDREN:
            if root == (home / wide):
                return f"不能选择整个 {wide} 目录，请选择其下的具体工程文件夹"
    except OSError:
        pass

    # 拒绝把沙箱/数据目录当目标，避免递归拷贝
    lowered = s.replace("\\", "/").lower()
    if "/local_dev/sandboxes" in lowered or lowered.endswith("/local_dev/sandboxes"):
        return "不能选择本机写码沙箱目录作为目标"
    return None


def detect_project_markers(root: Path) -> list[str]:
    """扫描目录顶层，返回工程特征标记（相对名）。"""
    found: list[str] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return []

    dir_names: set[str] = set()
    file_names: set[str] = set()
    for child in children:
        name = child.name
        if name in {".", ".."}:
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if is_dir:
            dir_names.add(name)
            if name == ".git":
                found.append(".git/")
        else:
            file_names.add(name)
            lower = name.lower()
            if name in _PROJECT_FILES or lower in {x.lower() for x in _PROJECT_FILES}:
                found.append(name)
            elif child.suffix.lower() in {".sln", ".csproj"}:
                found.append(name)

    # 常见前后端一体结构
    if "frontend" in dir_names and "backend" in dir_names:
        found.append("frontend+backend/")
    for d in sorted(_PROJECT_DIR_NAMES & dir_names):
        # 目录内至少有一个源码/配置文件才算
        sub = root / d
        try:
            for sub_child in sub.iterdir():
                if sub_child.is_file() and (
                    sub_child.name in _PROJECT_FILES
                    or sub_child.suffix.lower() in _CODE_SUFFIXES
                    or sub_child.name.lower().startswith("readme")
                ):
                    found.append(f"{d}/")
                    break
                if sub_child.is_dir() and sub_child.name in {"src", "app", "pages", "components", "routers"}:
                    found.append(f"{d}/")
                    break
        except OSError:
            continue

    # 顶层直接有源码文件
    for name in sorted(file_names):
        p = root / name
        if p.suffix.lower() in _CODE_SUFFIXES and name not in found:
            found.append(name)
            if len(found) >= 8:
                break

    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for m in found:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out[:12]


def looks_like_project(root: Path) -> tuple[bool, list[str]]:
    markers = detect_project_markers(root)
    return (len(markers) > 0, markers)


def validate_workspace(path: str) -> dict[str, Any]:
    """返回 {ok, path, exists, writable, empty, looks_like_project, project_markers, error}。"""
    base = {
        "ok": False,
        "path": (path or "").strip(),
        "exists": False,
        "writable": False,
        "empty": False,
        "looks_like_project": False,
        "project_markers": [],
        "error": "",
    }
    try:
        root = normalize_workspace(path)
    except ValueError as e:
        base["error"] = str(e)
        return base

    base["path"] = str(root)
    bad = _is_forbidden_target(root)
    if bad:
        base["exists"] = root.exists()
        base["error"] = bad
        return base

    if not root.exists():
        base["error"] = "目录不存在，请先创建该文件夹"
        return base
    if not root.is_dir():
        base["exists"] = True
        base["error"] = "路径不是目录"
        return base
    if not os.access(root, os.W_OK | os.X_OK):
        base["exists"] = True
        base["error"] = "目录不可写"
        return base

    base["exists"] = True
    base["writable"] = True

    empty = True
    try:
        next(root.iterdir())
        empty = False
    except StopIteration:
        empty = True
    except OSError as e:
        base["error"] = f"无法读取目录：{e}"
        return base

    base["empty"] = empty
    if empty:
        # 空目录：允许新建项目
        base["ok"] = True
        base["error"] = ""
        return base

    is_proj, markers = looks_like_project(root)
    base["looks_like_project"] = is_proj
    base["project_markers"] = markers
    if not is_proj:
        base["error"] = (
            "该目录不像工程目录（未发现 package.json、requirements.txt、"
            "frontend/backend、src 等工程特征）。"
            "请选择具体项目文件夹；若要新建项目请选空文件夹。"
        )
        return base

    base["ok"] = True
    base["error"] = ""
    return base

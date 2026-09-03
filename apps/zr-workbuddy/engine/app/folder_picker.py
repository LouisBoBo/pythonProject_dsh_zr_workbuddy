"""弹出本机原生「选择文件夹」对话框，返回绝对路径。

仅适用于引擎与浏览器同机（127.0.0.1）：对话框出现在运行引擎的那台机器上。
对齐 simplified-workbuddy apps/local_dev/folder_picker.py。
"""
from __future__ import annotations

import platform
import subprocess
from typing import Any


def pick_local_folder(*, prompt: str = "选择工程目录") -> dict[str, Any]:
    """阻塞直到用户选中或取消。返回 {ok, path, error}。"""
    system = platform.system()
    try:
        if system == "Darwin":
            return _pick_macos(prompt)
        if system == "Windows":
            return _pick_windows(prompt)
        return _pick_linux(prompt)
    except subprocess.TimeoutExpired:
        return {"ok": False, "path": "", "error": "选择超时，请重试"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "path": "", "error": f"{type(e).__name__}: {e}"}


def _normalize_path(raw: str) -> str:
    p = (raw or "").strip().strip('"').strip("'")
    while len(p) > 1 and p.endswith(("/", "\\")):
        p = p[:-1]
    return p


def _pick_macos(prompt: str) -> dict[str, Any]:
    safe = prompt.replace("\\", "\\\\").replace('"', '\\"')
    script = f'POSIX path of (choose folder with prompt "{safe}")'
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        if "User canceled" in err or "-128" in err or not err:
            return {"ok": False, "path": "", "error": "已取消选择"}
        return {"ok": False, "path": "", "error": err or "选文件夹失败"}
    path = _normalize_path(proc.stdout or "")
    if not path:
        return {"ok": False, "path": "", "error": "未返回路径"}
    return {"ok": True, "path": path, "error": ""}


def _pick_windows(prompt: str) -> dict[str, Any]:
    safe = prompt.replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
        f"$f.Description = '{safe}'; "
        "$f.ShowNewFolderButton = $true; "
        "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath } "
        "else { exit 2 }"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if proc.returncode == 2:
        return {"ok": False, "path": "", "error": "已取消选择"}
    if proc.returncode != 0:
        return {
            "ok": False,
            "path": "",
            "error": (proc.stderr or proc.stdout or "选文件夹失败").strip(),
        }
    path = _normalize_path(proc.stdout or "")
    if not path:
        return {"ok": False, "path": "", "error": "已取消选择"}
    return {"ok": True, "path": path, "error": ""}


def _pick_linux(prompt: str) -> dict[str, Any]:
    for cmd in (
        ["zenity", "--file-selection", "--directory", f"--title={prompt}"],
        ["kdialog", "--getexistingdirectory", ".", prompt],
    ):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except FileNotFoundError:
            continue
        if proc.returncode != 0:
            return {"ok": False, "path": "", "error": "已取消选择"}
        path = _normalize_path(proc.stdout or "")
        if path:
            return {"ok": True, "path": path, "error": ""}
        return {"ok": False, "path": "", "error": "已取消选择"}
    return {
        "ok": False,
        "path": "",
        "error": "本机未找到 zenity/kdialog，请手动粘贴绝对路径",
    }

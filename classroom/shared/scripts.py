"""Пресеты скриптов запуска (ШБ и пользовательские)."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from .constants import config_path

# Wi‑Fi + сброс прокси — как connect.bat из «ПАПКА НА УРОКИ»
SHB_SCRIPT = r"""@echo off
chcp 65001 > nul

:: 1. Clear Proxy
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f > nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /f > nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v AutoDetect /t REG_DWORD /d 0 /f > nul

:: 2. Set WiFi Variables
set "SSID=106k"
set "PASSWORD=*8KxOZq?hE"
set "XML_PATH=%TEMP%\wifi_profile.xml"

:: 3. Create XML Profile Line by Line (Without using parentheses block)
echo ^<?xml version="1.0"?^> > "%XML_PATH%"
echo ^<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1"^> >> "%XML_PATH%"
echo     ^<name^>%SSID%^</name^> >> "%XML_PATH%"
echo     ^<SSIDConfig^> >> "%XML_PATH%"
echo         ^<SSID^> >> "%XML_PATH%"
echo             ^<name^>%SSID%^</name^> >> "%XML_PATH%"
echo         ^</SSID^> >> "%XML_PATH%"
echo     ^</SSIDConfig^> >> "%XML_PATH%"
echo     ^<connectionType^>ESS^</connectionType^> >> "%XML_PATH%"
echo     ^<connectionMode^>auto^</connectionMode^> >> "%XML_PATH%"
echo     ^<MSM^> >> "%XML_PATH%"
echo         ^<security^> >> "%XML_PATH%"
echo             ^<authEncryption^> >> "%XML_PATH%"
echo                 ^<authentication^>WPA2PSK^</authentication^> >> "%XML_PATH%"
echo                 ^<encryption^>AES^</encryption^> >> "%XML_PATH%"
echo                 ^<useOneX^>false^</useOneX^> >> "%XML_PATH%"
echo             ^</authEncryption^> >> "%XML_PATH%"
echo             ^<sharedKey^> >> "%XML_PATH%"
echo                 ^<keyType^>passPhrase^</keyType^> >> "%XML_PATH%"
echo                 ^<protected^>false^</protected^> >> "%XML_PATH%"
echo                 ^<keyMaterial^>%PASSWORD%^</keyMaterial^> >> "%XML_PATH%"
echo             ^</sharedKey^> >> "%XML_PATH%"
echo         ^</security^> >> "%XML_PATH%"
echo     ^</MSM^> >> "%XML_PATH%"
echo ^</WLANProfile^> >> "%XML_PATH%"

:: 4. Add Profile and Connect
netsh wlan add profile filename="%XML_PATH%" user=all > nul
netsh wlan connect name="%SSID%"

:: 5. Clean up
del "%XML_PATH%"

echo DONE!
"""


def _scripts_path() -> Path:
    return config_path("scripts.json")


def _safe_id(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_\-]+", "_", name.strip())[:40] or "script"
    return base.lower()


def default_presets() -> list[dict]:
    return [
        {
            "id": "shb",
            "name": "ШБ",
            "kind": "bat",
            "builtin": True,
            "content": SHB_SCRIPT,
        }
    ]


def _normalize_preset(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    preset_id = str(item.get("id") or "").strip() or str(uuid.uuid4())[:8]
    name = str(item.get("name") or preset_id).strip()
    kind = str(item.get("kind") or "bat").strip().lower()
    if kind not in {"bat", "cmd", "ps1"}:
        kind = "bat"
    content = str(item.get("content") or "")
    if item.get("builtin") and preset_id == "shb" and not content.strip():
        content = SHB_SCRIPT
    if not content.strip() and not item.get("builtin"):
        return None
    return {
        "id": preset_id,
        "name": name,
        "kind": kind,
        "builtin": bool(item.get("builtin")),
        "content": content if content.strip() else (SHB_SCRIPT if preset_id == "shb" else content),
    }


def load_scripts() -> dict:
    path = _scripts_path()
    presets = default_presets()
    selected = "shb"
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}
        if isinstance(raw, dict):
            selected = str(raw.get("selected") or selected)
            loaded = []
            for item in raw.get("presets") or []:
                norm = _normalize_preset(item)
                if norm:
                    loaded.append(norm)
            if loaded:
                # гарантируем наличие ШБ
                if not any(p["id"] == "shb" for p in loaded):
                    loaded.insert(0, default_presets()[0])
                else:
                    for p in loaded:
                        if p["id"] == "shb":
                            p["name"] = "ШБ"
                            p["builtin"] = True
                            if not p.get("content", "").strip():
                                p["content"] = SHB_SCRIPT
                presets = loaded
    if not any(p["id"] == selected for p in presets):
        selected = presets[0]["id"]
    return {"presets": presets, "selected": selected}


def save_scripts(data: dict) -> dict:
    presets = []
    for item in data.get("presets") or []:
        norm = _normalize_preset(item)
        if norm:
            presets.append(norm)
    if not presets:
        presets = default_presets()
    if not any(p["id"] == "shb" for p in presets):
        presets.insert(0, default_presets()[0])
    selected = str(data.get("selected") or presets[0]["id"])
    if not any(p["id"] == selected for p in presets):
        selected = presets[0]["id"]
    payload = {"presets": presets, "selected": selected}
    _scripts_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def get_preset(preset_id: str | None = None) -> dict | None:
    data = load_scripts()
    pid = preset_id or data.get("selected")
    for preset in data["presets"]:
        if preset["id"] == pid:
            return preset
    return data["presets"][0] if data["presets"] else None


def set_selected(preset_id: str) -> dict:
    data = load_scripts()
    data["selected"] = preset_id
    return save_scripts(data)


def add_preset_from_file(path: Path, name: str | None = None) -> dict:
    path = Path(path)
    content = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower().lstrip(".")
    kind = suffix if suffix in {"bat", "cmd", "ps1"} else "bat"
    display = (name or path.stem).strip() or path.stem
    preset_id = f"{_safe_id(display)}_{str(uuid.uuid4())[:6]}"
    data = load_scripts()
    data["presets"].append(
        {
            "id": preset_id,
            "name": display,
            "kind": kind,
            "builtin": False,
            "content": content,
        }
    )
    data["selected"] = preset_id
    return save_scripts(data)


def remove_preset(preset_id: str) -> dict:
    data = load_scripts()
    if preset_id == "shb":
        return data
    data["presets"] = [p for p in data["presets"] if p["id"] != preset_id]
    if data.get("selected") == preset_id:
        data["selected"] = "shb"
    return save_scripts(data)


def script_extension(kind: str) -> str:
    return {"bat": ".bat", "cmd": ".cmd", "ps1": ".ps1"}.get(kind, ".bat")


def public_presets() -> list[dict]:
    """Список пресетов для UI/API без лишних полей — content нужен ученикам."""
    data = load_scripts()
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "kind": p["kind"],
            "builtin": p.get("builtin", False),
            "content": p.get("content", ""),
        }
        for p in data["presets"]
    ]

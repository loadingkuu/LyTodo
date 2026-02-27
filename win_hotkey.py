from __future__ import annotations
import sys

IS_WINDOWS = sys.platform.startswith("win")

WM_HOTKEY = 0x0312

# Modifiers
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    # SetWindowPos
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOACTIVATE = 0x0010
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2

    def set_topmost(hwnd: int, topmost: bool):
        h = HWND_TOPMOST if topmost else HWND_NOTOPMOST
        user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(h), 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _vk_from_qt_key(name: str) -> int:
        # Basic mapping (letters/digits/F-keys)
        name = name.upper()
        if len(name) == 1:
            return ord(name)
        if name.startswith("F") and name[1:].isdigit():
            n = int(name[1:])
            return 0x70 + (n - 1)  # VK_F1 = 0x70
        mapping = {
            "TAB": 0x09, "ESC": 0x1B, "SPACE": 0x20,
            "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
        }
        return mapping.get(name, 0)

    def parse_hotkey(seq: str):
        # seq like "Ctrl+Alt+T"
        parts = [p.strip() for p in (seq or "").split("+") if p.strip()]
        mods = 0
        key = ""
        for p in parts:
            pl = p.lower()
            if pl in ("ctrl", "control"):
                mods |= MOD_CONTROL
            elif pl == "alt":
                mods |= MOD_ALT
            elif pl == "shift":
                mods |= MOD_SHIFT
            elif pl in ("win", "meta", "super"):
                mods |= MOD_WIN
            else:
                key = p
        vk = _vk_from_qt_key(key)
        return mods, vk

    class GlobalHotkey:
        def __init__(self, hotkey_id: int = 1):
            self.hotkey_id = int(hotkey_id)

        def register(self, hwnd: int, sequence: str) -> bool:
            mods, vk = parse_hotkey(sequence)
            if vk == 0:
                return False
            return bool(user32.RegisterHotKey(wintypes.HWND(hwnd), self.hotkey_id, mods, vk))

        def unregister(self, hwnd: int):
            try:
                user32.UnregisterHotKey(wintypes.HWND(hwnd), self.hotkey_id)
            except Exception:
                pass

else:
    def set_topmost(hwnd: int, topmost: bool):
        return

    class GlobalHotkey:
        def __init__(self, hotkey_id: int = 1):
            self.hotkey_id = int(hotkey_id)

        def register(self, hwnd: int, sequence: str) -> bool:
            return False

        def unregister(self, hwnd: int):
            return

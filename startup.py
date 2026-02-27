from __future__ import annotations

import os
import sys

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    import winreg

    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _startup_command() -> str:
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return f'"{exe}"'
    script = os.path.abspath(sys.argv[0])
    return f'"{exe}" "{script}"'


def set_launch_at_startup(app_name: str, enabled: bool) -> bool:
    if not IS_WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False

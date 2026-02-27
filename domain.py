from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
import time
import uuid


def now_ts() -> float:
    return float(time.time())


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Task:
    id: str
    text: str
    tag: str = "默认"
    done: bool = False
    pinned: bool = False
    note: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    completed_at: Optional[float] = None
    order: float = 0.0
    deleted: bool = False

    def __post_init__(self):
        t = now_ts()
        if not self.id:
            self.id = new_id()
        if not self.created_at:
            self.created_at = t
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.order:
            self.order = self.created_at

        if self.done and not self.completed_at:
            self.completed_at = self.updated_at
        if (not self.done) and self.completed_at is not None:
            self.completed_at = None

    def first_line(self) -> str:
        s = (self.text or "").splitlines()
        return s[0] if s else ""

    def touch(self):
        self.updated_at = now_ts()
        if self.done:
            self.completed_at = self.updated_at
        else:
            self.completed_at = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Task":
        tid = str(d.get("id") or "") or new_id()
        text = str(d.get("text", ""))
        tag = str(d.get("tag", "默认") or "默认")
        done = bool(d.get("done", False))
        pinned = bool(d.get("pinned", False))
        note = str(d.get("note", "") or "")
        created_at = float(d.get("created_at", 0.0) or 0.0)
        updated_at = float(d.get("updated_at", 0.0) or 0.0)

        if not created_at:
            created_at = float(d.get("created_ts", 0.0) or 0.0) or now_ts()
        if not updated_at:
            updated_at = created_at

        completed_at = d.get("completed_at", None)
        if completed_at is not None:
            try:
                completed_at = float(completed_at)
            except Exception:
                completed_at = None

        order = float(d.get("order", 0.0) or 0.0)
        if not order:
            order = created_at

        deleted = bool(d.get("deleted", False))

        return Task(
            id=tid, text=text, tag=tag, done=done, pinned=pinned, note=note,
            created_at=created_at, updated_at=updated_at, completed_at=completed_at,
            order=order, deleted=deleted
        )


@dataclass
class Tag:
    id: str
    name: str
    color: str = ""
    updated_at: float = 0.0
    deleted: bool = False

    def __post_init__(self):
        if not self.id:
            self.id = new_id()
        if not self.updated_at:
            self.updated_at = now_ts()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Tag":
        return Tag(
            id=str(d.get("id") or "") or new_id(),
            name=str(d.get("name") or "").strip() or "默认",
            color=str(d.get("color") or ""),
            updated_at=float(d.get("updated_at", 0.0) or 0.0) or now_ts(),
            deleted=bool(d.get("deleted", False)),
        )


@dataclass
class Settings:
    show_completed_in_main: bool = True
    auto_archive_completed: bool = True

    font_family: str = ""
    font_size: int = 10

    panel_opacity: int = 160
    always_on_top: bool = False

    hotkey_enabled: bool = False
    hotkey_sequence: str = "Ctrl+Alt+T"
    hotkey_force_top: bool = True

    win_x: int = 200
    win_y: int = 200
    win_w: int = 360
    win_h: int = 560

    # 同步：默认写入连接信息，但保持关闭（sync_enabled=False），避免自动拉取/覆盖
    sync_enabled: bool = False
    sync_base_url: str = "http://111.228.36.13:8080"
    sync_token: str = "UeENtPn3LXXniEnS-R_DmcjCC3aUrzEvh83JWC477YI"
    sync_user: str = "liuyang"
    sync_timer_enabled: bool = True
    sync_strategy_b: bool = True

    # 便签页：每个元素形如 {id,title,content,created_at,updated_at}
    note_pages: list = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Settings":
        def g(key, default):
            return d.get(key, default) if isinstance(d, dict) else default
        return Settings(
            show_completed_in_main=bool(g("show_completed_in_main", True)),
            auto_archive_completed=bool(g("auto_archive_completed", True)),
            font_family=str(g("font_family", "") or ""),
            font_size=int(g("font_size", 10)),
            panel_opacity=int(g("panel_opacity", 160)),
            always_on_top=bool(g("always_on_top", False)),            hotkey_enabled=bool(g("hotkey_enabled", False)),
            hotkey_sequence=str(g("hotkey_sequence", "Ctrl+Alt+T") or "Ctrl+Alt+T"),
            hotkey_force_top=bool(g("hotkey_force_top", True)),
            win_x=int(g("win_x", 200)),
            win_y=int(g("win_y", 200)),
            win_w=int(g("win_w", 360)),
            win_h=int(g("win_h", 560)),
            sync_enabled=bool(g("sync_enabled", False)),
            sync_base_url=str(g("sync_base_url", "http://111.228.36.13:8080") or "http://111.228.36.13:8080"),
            sync_token=str(g("sync_token", "UeENtPn3LXXniEnS-R_DmcjCC3aUrzEvh83JWC477YI") or "UeENtPn3LXXniEnS-R_DmcjCC3aUrzEvh83JWC477YI"),
            sync_user=str(g("sync_user", "liuyang") or "liuyang"),
            sync_timer_enabled=bool(g("sync_timer_enabled", True)),
            sync_strategy_b=bool(g("sync_strategy_b", True)),
            note_pages=g("note_pages", None) if isinstance(g("note_pages", None), list) else None,
        )

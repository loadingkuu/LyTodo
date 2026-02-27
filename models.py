from __future__ import annotations

from typing import List, Optional
from PySide6.QtCore import Qt, QAbstractListModel, QModelIndex

from domain import Task

ROLE_TEXT = Qt.ItemDataRole.DisplayRole
ROLE_DONE = Qt.ItemDataRole.UserRole + 1
ROLE_TAG = Qt.ItemDataRole.UserRole + 2
ROLE_NOTE = Qt.ItemDataRole.UserRole + 3
ROLE_PINNED = Qt.ItemDataRole.UserRole + 4
ROLE_ID = Qt.ItemDataRole.UserRole + 5
ROLE_ORDER = Qt.ItemDataRole.UserRole + 6


class TaskListModel(QAbstractListModel):
    def __init__(self, tasks: List[Task]):
        super().__init__()
        self._tasks = tasks
        self._show_completed = True
        self._completed_only = False
        self._tag_filter: Optional[str] = None
        self._search: str = ""

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._visible_real_indexes())

    def _visible_real_indexes(self) -> List[int]:
        idxs = [i for i, t in enumerate(self._tasks) if not t.deleted]

        if self._completed_only:
            idxs = [i for i in idxs if self._tasks[i].done]

        if (not self._completed_only) and (not self._show_completed):
            idxs = [i for i in idxs if not self._tasks[i].done]

        if self._tag_filter and self._tag_filter != "全部":
            idxs = [i for i in idxs if self._tasks[i].tag == self._tag_filter]

        if self._search:
            s = self._search.lower()
            def match(t: Task) -> bool:
                return (s in (t.text or "").lower()) or (s in (t.note or "").lower()) or (s in (t.tag or "").lower())
            idxs = [i for i in idxs if match(self._tasks[i])]

        pinned = sorted([i for i in idxs if self._tasks[i].pinned], key=lambda i: -float(self._tasks[i].order))
        normal = sorted([i for i in idxs if not self._tasks[i].pinned], key=lambda i: -float(self._tasks[i].order))
        return pinned + normal

    def visible_real_indexes(self) -> List[int]:
        return self._visible_real_indexes()

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return None
        real = self._visible_real_indexes()[index.row()]
        t = self._tasks[real]
        if role == ROLE_TEXT:
            return t.first_line()
        if role == ROLE_DONE:
            return t.done
        if role == ROLE_TAG:
            return t.tag
        if role == ROLE_NOTE:
            return t.note
        if role == ROLE_PINNED:
            return t.pinned
        if role == ROLE_ID:
            return t.id
        if role == ROLE_ORDER:
            return t.order
        if role == Qt.ItemDataRole.EditRole:
            return t.text
        return None

    def set_show_completed(self, show: bool):
        self.beginResetModel()
        self._show_completed = bool(show)
        self.endResetModel()


    def set_completed_only(self, enabled: bool):
        self.beginResetModel()
        self._completed_only = bool(enabled)
        self.endResetModel()

    def set_tag_filter(self, tag: Optional[str]):
        self.beginResetModel()
        self._tag_filter = tag
        self.endResetModel()

    def set_search(self, text: str):
        self.beginResetModel()
        self._search = (text or "").strip()
        self.endResetModel()

    def add_task(self, text: str = "", tag: str = "默认") -> str:
        self.beginResetModel()
        t = Task(id="", text=text, tag=tag or "默认", done=False)
        max_order = max([x.order for x in self._tasks if (not x.deleted and x.pinned == t.pinned)] + [t.order])
        t.order = max_order + 1.0
        self._tasks.append(t)
        self.endResetModel()

    def get_all_tasks(self) -> List[Task]:
        return self._tasks

    def get_completed_real_indexes(self) -> List[int]:
        return [i for i, t in enumerate(self._tasks) if (not t.deleted and t.done)]

    def restore_completed(self, real_indexes: List[int]):
        self.beginResetModel()
        for i in real_indexes:
            if 0 <= i < len(self._tasks):
                self._tasks[i].done = False
                self._tasks[i].touch()
        self.endResetModel()

    def delete_real_indexes_soft(self, real_indexes: List[int]):
        self.beginResetModel()
        for i in real_indexes:
            if 0 <= i < len(self._tasks):
                self._tasks[i].deleted = True
                self._tasks[i].touch()
        self.endResetModel()

    def remove_task_hard_by_id(self, task_id: str) -> bool:
        """完全移除某条任务（用于“新增后取消/空提交”时清理占位行）。"""
        tid = str(task_id or "")
        if not tid:
            return False
        self.beginResetModel()
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t.id != tid]
        self.endResetModel()
        return len(self._tasks) != before


    def purge_completed_hard(self):
        self.beginResetModel()
        self._tasks = [t for t in self._tasks if not (t.done and not t.deleted)]
        self.endResetModel()

    def get_deleted_real_indexes(self) -> List[int]:
        return [i for i, t in enumerate(self._tasks) if (t.deleted)]

    def restore_deleted(self, real_indexes: List[int]):
        self.beginResetModel()
        for i in real_indexes:
            if 0 <= i < len(self._tasks):
                self._tasks[i].deleted = False
                self._tasks[i].touch()
        self.endResetModel()

    def purge_deleted_hard(self):
        self.beginResetModel()
        self._tasks = [t for t in self._tasks if not t.deleted]
        self.endResetModel()

    def real_index_from_proxy(self, proxy_row: int) -> int:
        return self._visible_real_indexes()[proxy_row]

    
    def flags(self, index: QModelIndex):
        base = super().flags(index)
        # 允许拖拽排序（视图侧会限制仅在“全部/非搜索/非收集箱”生效）
        if index.isValid():
            return base | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled | Qt.ItemIsEditable
        return base | Qt.ItemIsDropEnabled

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def move_visible(self, src_row: int, dst_row: int) -> bool:
        """按“当前可见顺序”移动一行，并通过调整 order 实现持久化排序。

        注意：该方法只调整同一 pinned 分组内的顺序；跨组拖动会被拒绝。
        """
        vis = self._visible_real_indexes()
        if src_row < 0 or src_row >= len(vis):
            return False
        if dst_row < 0:
            dst_row = 0
        if dst_row >= len(vis):
            dst_row = len(vis) - 1

        src_real = vis[src_row]
        dst_real = vis[dst_row]
        if src_real == dst_real:
            return False

        src_task = self._tasks[src_real]
        dst_task = self._tasks[dst_real]
        if bool(src_task.pinned) != bool(dst_task.pinned):
            return False

        group_vis = [i for i in vis if self._tasks[i].pinned == src_task.pinned]
        src_pos = group_vis.index(src_real)
        dst_pos = group_vis.index(dst_real)

        group_vis2 = group_vis[:]
        group_vis2.pop(src_pos)
        group_vis2.insert(dst_pos, src_real)

        idx = group_vis2.index(src_real)
        prev_order = self._tasks[group_vis2[idx-1]].order if idx-1 >= 0 else None
        next_order = self._tasks[group_vis2[idx+1]].order if idx+1 < len(group_vis2) else None

        # 通过“夹逼”生成新 order，避免整体重排（性能更稳定）
        if prev_order is None and next_order is None:
            new_order = float(src_task.order)
        elif prev_order is None:
            new_order = float(next_order) + 1.0
        elif next_order is None:
            new_order = float(prev_order) - 1.0
        else:
            new_order = (float(prev_order) + float(next_order)) / 2.0

        self.beginResetModel()
        src_task.order = float(new_order)
        src_task.touch()
        self.endResetModel()
        return True

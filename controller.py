from __future__ import annotations

from typing import List, Dict, Optional, Tuple
import os
import tempfile

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QMessageBox

from domain import Tag, Settings, now_ts
from repository import JsonRepository
from models import TaskListModel, ROLE_TAG
from version import VERSION
from views import (
    FramelessMainWindow,
    TaskDelegate,
    SettingsDialog,
    TagManagerDialog,
    TaskEditDialog,
    best_default_font_family,
)
from sync_service import SyncService
from win_hotkey import GlobalHotkey, IS_WINDOWS, WM_HOTKEY, set_topmost


CONTROLLER_BUILD = "V1.0"


class AppController:
    """
    LyTodo Controller（重写版，专治缩进炸裂）

    关键点：
    - 🗑不再弹窗：进入“已完成模式”（主窗口内的一个视图/标签页效果）
    - 同步方案A：启动自动 pull；退出自动 push；可选每60秒定时 push
    """

    def __init__(self, repo: JsonRepository, app):
        self.repo = repo
        self.app = app
        print(f"[LyTodo] controller {CONTROLLER_BUILD}")

        # ---------- load ----------
        tasks, settings, tags = self.repo.load()
        self.settings: Settings = settings
        self.tags: List[Tag] = tags

        # ---------- state ----------
        self.current_filter: str = "全部"
        self._last_filter_before_completed: str = "全部"
        self.in_completed_mode: bool = False
        self._editing_index = None
        self._pending_new_task_id = None
        self._creating_new_task = False
        self._creating_new_tag = "默认"
        self._last_auto_sync_ts = 0.0

        # ---------- model ----------
        self.model = TaskListModel(tasks)

        # ---------- window ----------
        self.window = FramelessMainWindow()
        self.window.list_view.setModel(self.model)

        fam = self.settings.font_family or best_default_font_family()
        self.delegate = TaskDelegate(
            font_family=fam,
            font_size=int(self.settings.font_size),
            tag_colors=self._tag_color_map(),
        )
        self.window.list_view.setItemDelegate(self.delegate)

        # restore geometry + flags
        self.window.panel_alpha = int(self.settings.panel_opacity)
        self.window.set_window_flags(self.settings.always_on_top)
        self.window.resize(int(self.settings.win_w), int(self.settings.win_h))
        self.window.move(int(self.settings.win_x), int(self.settings.win_y))

        # ---------- connect signals ----------
        self.window.request_settings.connect(self.open_settings)
        self.window.request_new_task.connect(self.add_task)
        self.window.request_open_sort.connect(self.open_sort_menu)
        self.window.request_open_tag_manager.connect(self.open_tag_manager)
        self.window.request_tag_filter.connect(self.set_filter_tag)
        self.window.request_add_page.connect(self.add_page)
        self.window.request_page_context_menu.connect(self.open_page_menu)
        self.window.request_task_context_menu.connect(self.open_task_menu)
        self.window.request_open_top_editor.connect(self.open_top_editor_for_index)
        self.window.request_search_text.connect(self.on_search)
        self.window.request_manual_sync.connect(self.manual_sync)
        # removed header notes button
        self.window.request_move_task.connect(self.on_move_task)
        self.window.window_geometry_changed.connect(self.on_geometry_changed)

        # completed-mode signals
        self.window.request_enter_completed_mode.connect(self.enter_completed_mode)
        self.window.request_exit_completed_mode.connect(self.exit_completed_mode)
        self.window.request_completed_restore_selected.connect(self.restore_selected_in_view)
        self.window.request_completed_delete_selected.connect(self.delete_selected_in_view)
        self.window.request_completed_clear_all.connect(self.clear_all_completed)

        # top editor signals
        self.window.top_editor.accepted.connect(self.commit_top_editor)
        self.window.top_editor.cancelled.connect(self.cancel_top_editor)

        # ---------- tray ----------
        self.tray = self._setup_tray()

        # ---------- hotkey ----------
        self.hotkey = GlobalHotkey(hotkey_id=1)
        self._apply_hotkey()

        # ---------- sync ----------
        self.storage_path = getattr(self.repo, "path", "storage.json")
        self.sync = SyncService(
            self.settings.sync_base_url,
            self.settings.sync_token,
            getattr(self.settings, "sync_user", "default"),
        )

        self._sync_timer = QTimer(self.window)
        self._sync_timer.setInterval(60_000)
        self._sync_timer.timeout.connect(self._timer_push)

        self._pull_timer = QTimer(self.window)
        self._pull_timer.setInterval(8_000)
        self._pull_timer.timeout.connect(self._timer_pull)

        # 策略B：本地变更后 3 秒自动 push（防抖）
        self._push_debounce = QTimer(self.window)
        self._push_debounce.setSingleShot(True)
        self._push_debounce.setInterval(3000)
        self._push_debounce.timeout.connect(self._debounced_push)

        if self.settings.sync_enabled and self.sync.available():
            self._startup_pull_reload()

        if self.settings.sync_enabled and self.sync.available():
            # periodic pull helps multi-client consistency
            self._pull_timer.start()

            if self.settings.sync_enabled and self.sync.available():
                try:
                    self._pull_timer.start()
                except Exception:
                    pass

        if self.settings.sync_enabled and self.settings.sync_timer_enabled and self.sync.available():
            self._sync_timer.start()

        self.app.aboutToQuit.connect(self._on_app_quit)

        # ---------- initial UI ----------
        self._apply_filters()
        self._refresh_tagbar()

        # ---------- sync status hint ----------
        try:
            if self.settings.sync_enabled and self.sync.available():
                self.window.set_sync_status("同步已启用", ok=True, auto_clear_ms=1800)
            else:
                self.window.set_sync_status("同步未启用", ok=False, auto_clear_ms=1800)
        except Exception:
            pass

    # ---------------- public ----------------

    def show(self):
        self.window.show()

    # ---------------- persistence ----------------

    def manual_sync(self):
        """手动同步：pull(合并) + push。用于多端即时刷新。"""
        if not self.settings.sync_enabled:
            self.window.set_sync_status("未开启同步", ok=False, auto_clear_ms=2200)
            return
        if not self.sync.available():
            self.window.set_sync_status("同步不可用", ok=False, auto_clear_ms=2200)
            return
        try:
            self._pull_merge_reload()
            self.save()
            ok = self.sync.push_from_file(self.storage_path)
            self.window.set_sync_status("手动同步完成" if ok else "推送失败", ok=bool(ok), auto_clear_ms=2000)
        except Exception as e:
            self.window.set_sync_status(f"同步失败：{e}", ok=False, auto_clear_ms=3500)

    def save(self):
        self.repo.save(self.model.get_all_tasks(), self.settings, self.tags)
    def _merge_remote_into_local(self, remote_tasks, remote_tags, remote_settings):
        """Merge remote state into local state.
        Tasks: merge by id, keep newer updated_at.
        Tags: merge by name, keep newer updated_at.
        Settings: only sync-related settings are merged (avoid overriding local UI/background paths).
        """
        # --- tasks ---
        local = {t.id: t for t in self.model.get_all_tasks() if getattr(t, "id", "")}
        for rt in remote_tasks or []:
            tid = str(getattr(rt, "id", "") or "")
            if not tid:
                continue
            lt = local.get(tid)
            if lt is None:
                local[tid] = rt
            else:
                ru = float(getattr(rt, "updated_at", 0.0) or 0.0)
                lu = float(getattr(lt, "updated_at", 0.0) or 0.0)
                if ru >= lu:
                    local[tid] = rt
        merged_tasks = list(local.values())

        # --- tags ---
        local_tags = {t.name: t for t in getattr(self, "tags", [])}
        for rt in remote_tags or []:
            name = str(getattr(rt, "name", "") or "").strip() or "默认"
            lt = local_tags.get(name)
            if lt is None:
                local_tags[name] = rt
            else:
                ru = float(getattr(rt, "updated_at", 0.0) or 0.0)
                lu = float(getattr(lt, "updated_at", 0.0) or 0.0)
                if ru >= lu:
                    lt.color = getattr(rt, "color", "") or lt.color
                    lt.updated_at = max(lu, ru)
                    lt.deleted = bool(getattr(rt, "deleted", False))
        merged_tags = list(local_tags.values())

        # ensure default tags exist
        from domain import Tag
        if not any(t.name == "全部" for t in merged_tags):
            merged_tags.insert(0, Tag(id="", name="全部", color=""))
        if not any(t.name == "默认" for t in merged_tags):
            merged_tags.append(Tag(id="", name="默认", color=""))

        # --- settings (sync-only) ---
        try:
            self.settings.sync_enabled = bool(getattr(remote_settings, "sync_enabled", self.settings.sync_enabled))
            self.settings.sync_base_url = str(getattr(remote_settings, "sync_base_url", self.settings.sync_base_url) or self.settings.sync_base_url)
            self.settings.sync_token = str(getattr(remote_settings, "sync_token", self.settings.sync_token) or self.settings.sync_token)
            self.settings.sync_user = str(getattr(remote_settings, "sync_user", self.settings.sync_user) or self.settings.sync_user)
            self.settings.sync_timer_enabled = bool(getattr(remote_settings, "sync_timer_enabled", self.settings.sync_timer_enabled))
            self.settings.sync_strategy_b = bool(getattr(remote_settings, "sync_strategy_b", self.settings.sync_strategy_b))
        except Exception:
            pass

        # apply merged
        self.model.beginResetModel()
        self.model._tasks = merged_tasks
        self.model.endResetModel()
        self.tags = merged_tags
        self._refresh_tagbar()

    def _pull_merge_reload(self):
        """Pull remote storage to temp, merge into local, refresh UI."""
        tmpfile = os.path.join(tempfile.gettempdir(), "lytodo_remote_storage.json")
        ok = self.sync.pull_to_file(tmpfile)
        if not ok:
            raise RuntimeError("pull失败")
        rrepo = JsonRepository(tmpfile)
        r_tasks, r_settings, r_tags = rrepo.load()
        self._merge_remote_into_local(r_tasks, r_tags, r_settings)
        if not getattr(self, "in_completed_mode", False):
            self._apply_filters()

    def on_geometry_changed(self, x: int, y: int, w: int, h: int):
        self.settings.win_x, self.settings.win_y = int(x), int(y)
        self.settings.win_w, self.settings.win_h = int(w), int(h)
        self.save()
        self._mark_dirty_and_debounce()

    # ---------------- tags ----------------

    def add_page(self):
        """新增“页面/类别”（即标签）。"""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self.window, "新增页面", "页面名称：")
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        if name in ("全部", "已完成"):
            return
        if any((t.name == name and not t.deleted) for t in self.tags):
            self.set_filter_tag(name)
            return
        self.tags.append(Tag(id="", name=name, color=""))
        self.save()
        self._refresh_tagbar()
        self.set_filter_tag(name)

    def open_page_menu(self, tag_name: str, global_pos):
        """右键页面（标签）菜单：默认/全部不允许删除。"""
        from PySide6.QtWidgets import QMenu
        tag = str(tag_name or "").strip()
        if not tag:
            return
        m = QMenu(self.window)
        act_use = m.addAction("设为当前")
        act_rename = None
        act_delete = None
        if tag not in ("全部", "默认"):
            act_rename = m.addAction("重命名")
            act_delete = m.addAction("删除")

        act = m.exec(global_pos)
        if act == act_use:
            self.set_filter_tag(tag)
        elif act == act_rename:
            self.rename_page(tag)
        elif act == act_delete:
            self.delete_page(tag)

    def rename_page(self, old: str):
        from PySide6.QtWidgets import QInputDialog
        old = str(old or "").strip()
        if not old or old in ("全部", "默认"):
            return
        new, ok = QInputDialog.getText(self.window, "重命名页面", "新名称：", text=old)
        if not ok:
            return
        new = (new or "").strip()
        if not new or new == old:
            return
        if new in ("全部", "已完成"):
            return
        if any((t.name == new and not t.deleted) for t in self.tags):
            return

        # rename tag object
        for t in self.tags:
            if (not t.deleted) and t.name == old:
                t.name = new
                t.updated_at = now_ts()

        # migrate tasks
        for i in range(self.model.rowCount()):
            idx = self.model.index(i, 0)
            if self.model.data(idx, ROLE_TAG) == old:
                self.model.setData(idx, new, ROLE_TAG)

        if self.current_filter == old:
            self.current_filter = new

        self.save()
        self._refresh_tagbar()
        self._apply_filters()

    
    def delete_page(self, name: str):
        name = str(name or "").strip()
        if not name or name in ("全部", "默认"):
            return

        # 统计将被迁移到“默认”的任务数量（包含：未完成/已完成，但不含已删除）
        move_count = 0
        try:
            for t in self.model.get_all_tasks():
                if (not getattr(t, "deleted", False)) and getattr(t, "tag", "") == name:
                    move_count += 1
        except Exception:
            pass

        # 删除确认：明确告知“任务会移动到默认”
        from PySide6.QtWidgets import QMessageBox
        msg = f"确定删除页面「{name}」吗？\n\n该页面下的 {move_count} 条任务将移动到「默认」。"
        ret = QMessageBox.question(
            self.window,
            "删除页面确认",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return

        # 标记标签为 deleted（而不是物理删除，便于同步/回收站扩展）
        for tg in self.tags:
            if (not tg.deleted) and tg.name == name:
                tg.deleted = True
                tg.updated_at = now_ts()

        # 迁移所有任务（包含隐藏/筛选掉的、已完成的）
        try:
            for t in self.model.get_all_tasks():
                if (not getattr(t, "deleted", False)) and getattr(t, "tag", "") == name:
                    t.tag = "默认"
                    try:
                        t.touch()
                    except Exception:
                        pass
        except Exception:
            pass

        if self.current_filter == name:
            self.current_filter = "全部"

        self.model.beginResetModel()
        self.model.endResetModel()
        self.save()
        self._refresh_tagbar()
        self._apply_filters()


    def _tag_color_map(self) -> Dict[str, str]:
        return {t.name: t.color for t in self.tags if (not t.deleted and t.color)}

    def _tag_names(self) -> List[str]:
        names = [t.name for t in self.tags if not t.deleted]
        # “已完成”不作为普通标签展示，已完成列表由🗑入口统一管理
        names = [n for n in names if str(n).strip() != "已完成"]
        if "全部" not in names:
            names.insert(0, "全部")
        if "默认" not in names:
            names.append("默认")
        # dedupe
        out: List[str] = []
        seen = set()
        for n in names:
            n = str(n).strip()
            if n and n not in seen:
                out.append(n)
                seen.add(n)
        return out

    def _is_tag_deleted(self, name: str) -> bool:
        name = str(name or "").strip()
        if not name:
            return False
        for t in self.tags:
            if t.name == name and bool(getattr(t, "deleted", False)):
                return True
        return False

    def _refresh_tagbar(self):
        self.window.tagbar.set_colors(self._tag_color_map())
        self.window.tagbar.set_tags(self._tag_names(), self.current_filter)

    # ---------------- tray ----------------

    def _setup_tray(self):
        tray = QSystemTrayIcon(
            self.app.style().standardIcon(self.app.style().StandardPixmap.SP_ComputerIcon),
            self.app,
        )
        menu = QMenu()
        a_toggle = QAction("显示/隐藏", menu)
        a_quit = QAction("退出", menu)
        a_toggle.triggered.connect(self.toggle_visible)
        a_quit.triggered.connect(self.app.quit)
        menu.addAction(a_toggle)
        menu.addSeparator()
        menu.addAction(a_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda r: self.toggle_visible() if r == QSystemTrayIcon.Trigger else None)
        tray.show()
        return tray

    def toggle_visible(self):
        if self.window.isVisible():
            self.window.hide()
        else:
            self._show_raise_force_top()

    def _show_raise_force_top(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

        # 非常置顶时，通过“临时置顶”确保从其他软件上方弹出
        if (not self.settings.always_on_top) and self.settings.hotkey_force_top and IS_WINDOWS:
            hwnd = int(self.window.winId())
            set_topmost(hwnd, True)
            self.window.raise_()
            self.window.activateWindow()
            QTimer.singleShot(900, lambda: set_topmost(hwnd, False))

    # ---------------- hotkey ----------------

    def _apply_hotkey(self):
        if not IS_WINDOWS:
            return

        hwnd = int(self.window.winId())
        self.hotkey.unregister(hwnd)
        if self.settings.hotkey_enabled:
            self.hotkey.register(hwnd, self.settings.hotkey_sequence)

        def _nativeEvent(eventType, message):
            try:
                import ctypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    self._show_raise_force_top()
                    return True, 0
            except Exception:
                pass
            return False, 0

        self.window.nativeEvent = _nativeEvent  # type: ignore

    # ---------------- filtering / completed mode ----------------

    def _apply_filters(self):
        if self.in_completed_mode:
            return

        show_completed = bool(self.settings.show_completed_in_main)
        if bool(self.settings.auto_archive_completed):
            show_completed = False

        self.model.set_completed_only(False)
        self.model.set_show_completed(show_completed)

        if self.current_filter and self.current_filter not in ("全部", "已完成"):
            self.model.set_tag_filter(self.current_filter)
        else:
            self.model.set_tag_filter(None)

    def on_search(self, text: str):
        self.model.set_search(text)

    def set_filter_tag(self, tag: str):
        tag = tag or "全部"
        if tag == "已完成":
            self.enter_completed_mode()
            return

        if self.in_completed_mode:
            self.exit_completed_mode()

        self.current_filter = tag
        self._apply_filters()
        self._refresh_tagbar()

    def enter_completed_mode(self):
        if self.in_completed_mode:
            return
        self.in_completed_mode = True
        self._last_filter_before_completed = self.current_filter if self.current_filter != "已完成" else "全部"
        self.current_filter = "已完成"

        self.window.set_completed_mode_ui(True)
        self.model.set_tag_filter(None)
        self.model.set_completed_only(True)
        self._refresh_tagbar()

    def exit_completed_mode(self):
        if not self.in_completed_mode:
            return
        self.in_completed_mode = False
        self.window.set_completed_mode_ui(False)

        self.current_filter = self._last_filter_before_completed or "全部"
        self.model.set_completed_only(False)
        self._apply_filters()
        self._refresh_tagbar()

    # ---------------- tasks ----------------

    def add_task(self):
        """点击加号：进入“新建任务”编辑模式。
        - 不创建空白任务占位
        - 编辑框不沿用上一次的内容
        - 提交空文本则什么都不做
        """
        if self.in_completed_mode:
            return

        tag = self.current_filter if self.current_filter != "全部" else "默认"
        if tag not in self._tag_names():
            tag = "默认"

        self._creating_new_task = True
        self._creating_new_tag = tag
        self._editing_index = None
        self._pending_new_task_id = None

        fam = self.settings.font_family or best_default_font_family()
        self.window.open_editor("", fam, int(self.settings.font_size))

    def _real_index(self, proxy_index) -> int:

        return self.model.real_index_from_proxy(proxy_index.row())

    def selected_real_indexes_in_view(self) -> List[int]:
        sel = self.window.list_view.selectionModel()
        if not sel:
            return []
        rows = [idx.row() for idx in sel.selectedIndexes() if idx.isValid()]
        rows = sorted(set(rows))
        return [self.model.real_index_from_proxy(r) for r in rows]

    def restore_selected_in_view(self):
        if not self.in_completed_mode:
            return
        idxs = self.selected_real_indexes_in_view()
        if not idxs:
            return
        self.model.restore_completed(idxs)
        self.save()
        self._mark_dirty_and_debounce()

    def delete_selected_in_view(self):
        if not self.in_completed_mode:
            return
        idxs = self.selected_real_indexes_in_view()
        if not idxs:
            return
        self.model.delete_real_indexes_soft(idxs)
        self.save()
        self._mark_dirty_and_debounce()

    def clear_all_completed(self):
        self.model.purge_completed_hard()
        self.save()

    # ---------------- editor ----------------

    def open_top_editor_for_index(self, index):
        if not index or not index.isValid():
            return
        self._editing_index = index
        real = self._real_index(index)
        txt = self.model.get_all_tasks()[real].text
        fam = self.settings.font_family or best_default_font_family()
        self.window.open_editor(txt, fam, int(self.settings.font_size))

    def commit_top_editor(self, text: str):
        cleaned = (text or "").rstrip()

        # 新建模式：不创建空白任务；空提交 = 什么都不做
        if getattr(self, "_creating_new_task", False):
            if cleaned.strip():
                tag = getattr(self, "_creating_new_tag", "默认") or "默认"
                self.model.add_task(cleaned, tag=tag)

                # refresh
                self.model.beginResetModel()
                self.model.endResetModel()
                self.save()
                self._mark_dirty_and_debounce()
                try:
                    self.window.set_sync_status("已添加", ok=True, auto_clear_ms=900)
                except Exception:
                    pass

            self.window.close_editor()
            self._creating_new_task = False
            self._creating_new_tag = "默认"
            return

        # 编辑已有任务
        if self._editing_index and self._editing_index.isValid():
            real = self._real_index(self._editing_index)
            t = self.model.get_all_tasks()[real]
            t.text = cleaned
            t.touch()

        self.window.close_editor()
        self._editing_index = None
        self._pending_new_task_id = None

        # refresh
        self.model.beginResetModel()
        self.model.endResetModel()
        self.save()
        self._mark_dirty_and_debounce()

    def cancel_top_editor(self):
        # 新建模式取消：什么都不做（因为根本没有创建空任务）
        self.window.close_editor()
        self._editing_index = None
        self._pending_new_task_id = None
        self._creating_new_task = False
        self._creating_new_tag = "默认"

    #
    # ---------------- context menu ----------------


    def on_move_task(self, src_row: int, dst_row: int):
        """拖拽排序回调：仅在“全部 + 非搜索 + 非收集箱”下允许排序。"""
        if getattr(self, "in_completed_mode", False):
            return
        try:
            if hasattr(self.window, "search") and self.window.search.text().strip():
                return
        except Exception:
            pass

        try:
            moved = self.model.move_visible(int(src_row), int(dst_row))
        except Exception:
            moved = False

        if moved:
            self.save()
            self._mark_dirty_and_debounce()

    def open_sort_menu(self):
        """顶部“排序/更多”菜单。为避免打扰，尽量保持轻量。"""
        menu = QMenu(self.window)

        # Completed bin toggle
        if getattr(self, "in_completed_mode", False):
            a_back = QAction("返回主界面", menu)
            a_back.triggered.connect(self.exit_completed_mode)
            menu.addAction(a_back)
        else:
            a_bin = QAction("已完成收集箱", menu)
            a_bin.triggered.connect(self.enter_completed_mode)
            menu.addAction(a_bin)

        # Show/hide completed in main
        a_show = QAction("显示已完成" if not getattr(self.settings, "show_completed_in_main", True) else "隐藏已完成", menu)

        def _toggle_show_completed():
            self.settings.show_completed_in_main = not bool(getattr(self.settings, "show_completed_in_main", True))
            self._apply_filters()
            self.save()
            self._mark_dirty_and_debounce()

        a_show.triggered.connect(_toggle_show_completed)
        menu.addAction(a_show)

        menu.addSeparator()

        a_settings = QAction("设置…", menu)
        a_settings.triggered.connect(self.open_settings)
        menu.addAction(a_settings)

        # anchor position near sort button if exists
        try:
            btn = getattr(self.window.header, "btn_sort", None)
            if btn:
                menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
                return
        except Exception:
            pass
        menu.exec(self.window.mapToGlobal(self.window.rect().center()))

    def open_task_menu(self, global_pos, index):
        menu = QMenu()

        if index.isValid():
            a_edit = QAction("编辑…", menu)
            menu.addAction(a_edit)

            sub = menu.addMenu("更改标签")
            for tname in self._tag_names():
                if tname in ("全部", "已完成"):
                    continue
                act = QAction(tname, sub)
                act.triggered.connect(lambda _=False, tt=tname: self._set_item_tag(index, tt))
                sub.addAction(act)

            a_pin = QAction("置顶/取消置顶", menu)
            a_del = QAction("删除", menu)
            menu.addAction(a_pin)
            menu.addAction(a_del)

            a_edit.triggered.connect(lambda: self.edit_task_dialog(index))
            a_pin.triggered.connect(lambda: self.toggle_pin(index))
            a_del.triggered.connect(lambda: self.delete_task(index))
        else:
            a_new = QAction("新增任务", menu)
            a_set = QAction("设置…", menu)
            menu.addAction(a_new)
            menu.addSeparator()
            menu.addAction(a_set)
            a_new.triggered.connect(self.add_task)
            a_set.triggered.connect(self.open_settings)

        menu.exec(global_pos)

    def _set_item_tag(self, index, tag: str):
        real = self._real_index(index)
        t = self.model.get_all_tasks()[real]
        t.tag = tag or "默认"
        t.touch()

        if t.tag not in self._tag_names():
            if self._is_tag_deleted(t.tag):
                t.tag = "默认"
            else:
                self.tags.append(Tag(id="", name=t.tag))
        self.model.beginResetModel()
        self.model.endResetModel()
        self._refresh_tagbar()
        self.save()
        self._mark_dirty_and_debounce()

    def toggle_pin(self, index):
        real = self._real_index(index)
        t = self.model.get_all_tasks()[real]
        t.pinned = not t.pinned
        t.touch()
        self.model.beginResetModel()
        self.model.endResetModel()
        self.save()
        self._mark_dirty_and_debounce()

    def delete_task(self, index):
        real = self._real_index(index)
        self.model.delete_real_indexes_soft([real])
        self.save()
        self._mark_dirty_and_debounce()

    def edit_task_dialog(self, index):
        real = self._real_index(index)
        t = self.model.get_all_tasks()[real]

        tags = [x for x in self._tag_names() if x not in ("全部", "已完成")]
        deleted_flag = {"v": False}

        dlg = TaskEditDialog(t.text, t.note, t.tag, tags, t.done, t.pinned, parent=self.window)
        dlg.request_delete.connect(lambda: deleted_flag.__setitem__("v", True))

        if dlg.exec():
            if deleted_flag["v"]:
                self.model.delete_real_indexes_soft([real])
            else:
                v = dlg.values()
                t.text = v["text"] or t.text
                t.note = v["note"]
                t.tag = v["tag"] or "默认"
                t.done = bool(v["done"])
                t.pinned = bool(v["pinned"])
                t.touch()

                if t.tag not in self._tag_names():
                    if self._is_tag_deleted(t.tag):
                        t.tag = "默认"
                    else:
                        self.tags.append(Tag(id="", name=t.tag))
            self.model.beginResetModel()
            self.model.endResetModel()
            self._refresh_tagbar()
            self.save()
            self._mark_dirty_and_debounce()

    # ---------------- tag manager ----------------

    def open_tag_manager(self):
        if self.in_completed_mode:
            QMessageBox.information(self.window, "提示", "请先返回主列表再管理标签。")
            return

        dlg = TagManagerDialog(self._tag_names(), self._tag_color_map(), parent=self.window)

        def on_colors_changed(colors: dict):
            for tg in self.tags:
                if tg.name in colors:
                    tg.color = colors[tg.name]
            self.delegate.tag_colors = self._tag_color_map()
            self._refresh_tagbar()
            self.window.list_view.viewport().update()
            self.save()
            self._mark_dirty_and_debounce()

        def on_tags_changed(names: list):
            names = [str(x).strip() for x in (names or []) if str(x).strip()]
            if "全部" not in names:
                names.insert(0, "全部")
            if "默认" not in names:
                names.append("默认")
            if "已完成" not in names:
                names.append("已完成")

            old = {t.name: t for t in self.tags}
            keep = set(names)

            new_tags: List[Tag] = []
            for n in names:
                if n in old:
                    old[n].deleted = False
                    new_tags.append(old[n])
                else:
                    new_tags.append(Tag(id="", name=n))

            for n, tg in old.items():
                if n not in keep:
                    tg.deleted = True
                    new_tags.append(tg)

            self.tags = new_tags
            self.delegate.tag_colors = self._tag_color_map()
            self._refresh_tagbar()
            self.save()
            self._mark_dirty_and_debounce()

        dlg.colors_changed.connect(on_colors_changed)
        dlg.tags_changed.connect(on_tags_changed)
        dlg.request_set_filter.connect(self.set_filter_tag)
        dlg.exec()

    # ---------------- settings ----------------


    def open_settings(self):
        dlg = SettingsDialog(self.settings, parent=self.window)
        dlg.request_purge_completed.connect(self.clear_all_completed)

        if dlg.exec():
            v = dlg.get_values()

            self.settings.auto_archive_completed = bool(v.get("auto_archive_completed", True))
            self.settings.show_completed_in_main = bool(v.get("show_completed_in_main", True))
            self.settings.font_family = str(v.get("font_family", "") or "")
            self.settings.font_size = int(v.get("font_size", 10))
            self.settings.always_on_top = bool(v.get("always_on_top", False))
            self.settings.panel_opacity = int(v.get("panel_opacity", 160))

            self.settings.hotkey_enabled = bool(v.get("hotkey_enabled", False))
            self.settings.hotkey_sequence = str(v.get("hotkey_sequence", "Ctrl+Alt+T") or "Ctrl+Alt+T")
            self.settings.hotkey_force_top = bool(v.get("hotkey_force_top", True))

            self.settings.sync_enabled = bool(v.get("sync_enabled", False))
            self.settings.sync_base_url = str(v.get("sync_base_url", "") or "")
            self.settings.sync_token = str(v.get("sync_token", "") or "")
            self.settings.sync_user = str(v.get("sync_user", "default") or "default")
            self.settings.sync_timer_enabled = bool(v.get("sync_timer_enabled", True))

            # apply UI
            fam = self.settings.font_family or best_default_font_family()
            self.delegate.font_family = fam
            self.delegate.font_size = int(self.settings.font_size)

            self.window.panel_alpha = int(self.settings.panel_opacity)
            self.window.set_window_flags(self.settings.always_on_top)
            self.window.update()

            self._apply_hotkey()

            # apply sync
            self.sync = SyncService(self.settings.sync_base_url, self.settings.sync_token, self.settings.sync_user)
            self._sync_timer.stop()
            try:
                self._pull_timer.stop()
            except Exception:
                pass
            if self.settings.sync_enabled and self.settings.sync_timer_enabled and self.sync.available():
                self._sync_timer.start()

            if not self.in_completed_mode:
                self._apply_filters()

            self._refresh_tagbar()
            self.save()
            self._mark_dirty_and_debounce()

    # ---------------- sync ----------------


    def _mark_dirty_and_debounce(self):
        if not (self.settings.sync_enabled and self.sync.available()):
            return
        if not getattr(self.settings, "sync_strategy_b", True):
            return
        self._push_debounce.start()

    def _debounced_push(self):
        if not (self.settings.sync_enabled and self.sync.available()):
            return
        try:
            self.save()
            self.sync.push_from_file(self.storage_path)
            import time
            now = time.time()
            # 自动同步提示节流：避免频繁闪烁
            if (now - float(self._last_auto_sync_ts)) >= 8.0:
                self.window.set_sync_status("已自动同步", ok=True, auto_clear_ms=1200)
                self._last_auto_sync_ts = now
        except Exception as e:
            self.window.set_sync_status("同步失败", ok=False, auto_clear_ms=3500)
            # 可选：托盘气泡（若你启用了托盘）
            try:
                if hasattr(self, "tray") and self.tray:
                    self.tray.showMessage("LyTodo", f"同步失败：{e}", 3000)
            except Exception:
                pass


    def _timer_pull(self):
        """后台定时拉取远端并合并到本地（静默）。"""
        try:
            if not (self.settings.sync_enabled and self.sync.available()):
                return
            self._pull_merge_reload()
        except Exception:
            pass


    def _timer_push(self):
        # 后台定时推送：每60秒调用一次（不走防抖）
        if not (self.settings.sync_enabled and self.sync.available()):
            return
        try:
            self.save()
            self.sync.push_from_file(self.storage_path)
            self.window.set_sync_status("同步成功", ok=True, auto_clear_ms=1000)
        except Exception as e:
            self.window.set_sync_status("同步失败", ok=False, auto_clear_ms=3500)
            try:
                if hasattr(self, "tray") and self.tray:
                    self.tray.showMessage("LyTodo", f"同步失败：{e}", 3000)
            except Exception:
                pass

    def _startup_pull_reload(self):
        if not self.sync.pull_to_file(self.storage_path):
            try:
                self.window.set_sync_status("云端拉取失败/无更新", ok=False, auto_clear_ms=2200)
            except Exception:
                pass
            return
        try:
            tasks, settings, tags = self.repo.load()
        except Exception:
            return

        try:
            self.window.set_sync_status("已从云端拉取", ok=True, auto_clear_ms=1800)
        except Exception:
            pass

        self.settings = settings
        self.tags = tags
        self.model = TaskListModel(tasks)
        self.window.list_view.setModel(self.model)
        self.window.list_view.setItemDelegate(self.delegate)

        # apply window
        self.window.panel_alpha = int(self.settings.panel_opacity)
        self.window.set_window_flags(self.settings.always_on_top)
        self.window.resize(int(self.settings.win_w), int(self.settings.win_h))
        self.window.move(int(self.settings.win_x), int(self.settings.win_y))

        # apply delegate
        fam = self.settings.font_family or best_default_font_family()
        self.delegate.font_family = fam
        self.delegate.font_size = int(self.settings.font_size)
        self.delegate.tag_colors = self._tag_color_map()

        # reset to normal mode
        self.in_completed_mode = False
        self.current_filter = "全部"
        self.model.set_search(self.window.search.text())
        self._apply_filters()
        self._refresh_tagbar()

    def _timer_push(self):
        if not (self.settings.sync_enabled and self.sync.available()):
            return
        self.save()
        self.sync.push_from_file(self.storage_path)

    def _on_app_quit(self):
        if not (self.settings.sync_enabled and self.sync.available()):
            return
        try:
            self.save()
        except Exception:
            pass
        self.sync.push_from_file(self.storage_path)

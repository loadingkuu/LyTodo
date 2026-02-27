from __future__ import annotations
from typing import List, Tuple, Dict, Optional
import hashlib

from PySide6.QtCore import Qt, QRect, QSize, Signal, QEvent, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QFontDatabase, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListView, QStyledItemDelegate, QStyleOptionViewItem,
    QDialog, QLabel, QCheckBox, QPushButton, QListWidget, QListWidgetItem,
    QStyle, QSizeGrip, QTabWidget, QSlider, QFontComboBox, QSpinBox, QTextEdit,
    QComboBox, QKeySequenceEdit, QFrame, QLineEdit, QColorDialog, QAbstractItemView, QMenu
)

from models import ROLE_DONE, ROLE_TAG, ROLE_PINNED
from version import VERSION


def best_default_font_family() -> str:
    fams = set(QFontDatabase.families())
    for cand in ["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"]:
        if cand in fams:
            return cand
    return ""


def _hash_color(tag: str) -> QColor:
    h = hashlib.md5((tag or "默认").encode("utf-8")).hexdigest()
    r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
    r = int((r + 255) / 2); g = int((g + 255) / 2); b = int((b + 255) / 2)
    return QColor(r, g, b, 210)


def tag_color(tag: str, tag_colors: Dict[str, str]) -> QColor:
    hexv = (tag_colors or {}).get(tag, "") if tag else ""
    if isinstance(hexv, str) and hexv.startswith("#") and len(hexv) == 7:
        c = QColor(hexv)
        if c.isValid():
            c.setAlpha(230)
            return c
    return _hash_color(tag or "默认")


class TopEditor(QFrame):
    accepted = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopEditor")
        self.setStyleSheet(
            "#TopEditor{background: rgba(20,25,35,210); border: 1px solid rgba(255,255,255,45); border-radius: 12px;}"
            "QTextEdit{background: rgba(0,0,0,35); border: 1px solid rgba(255,255,255,35); border-radius: 10px; padding:8px; color:white;}"
            "QPushButton{background: rgba(255,255,255,16); border:none; border-radius:8px; color:white; font-weight:800; padding:4px 10px;}"
            "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(4)

        self.edit = QTextEdit()
        self.edit.setMinimumHeight(220)
        self.edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.edit.setLineWrapMode(QTextEdit.WidgetWidth)
        lay.addWidget(self.edit, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_cancel = QPushButton("×")
        self.btn_ok = QPushButton("✓")
        self.btn_cancel.setFixedWidth(36)
        self.btn_ok.setFixedWidth(36)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)

        self.btn_ok.clicked.connect(lambda: self.accepted.emit(self.edit.toPlainText()))
        self.btn_cancel.clicked.connect(lambda: self.cancelled.emit())
        self.edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.cancelled.emit()
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                # Enter 直接提交；Shift+Enter 换行
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self.accepted.emit(self.edit.toPlainText())
                return True
        return super().eventFilter(obj, event)


class TagButton(QWidget):
    clicked = Signal()
    def __init__(self, text: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0,0,0,0)
        lay.setSpacing(0)
        self.btn = QPushButton(text)
        self.btn.setFixedHeight(20)
        self.btn.setStyleSheet(
            "QPushButton{background: rgba(255,255,255,16); border:none; border-radius: 9px; color:white; padding: 0 9px; font-weight: 700; font-size: 11px;}"
            "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
        )
        self.underline = QFrame()
        self.underline.setFixedHeight(0)
        self.underline.setStyleSheet("background: rgba(0,0,0,0); border:none;")
        lay.addWidget(self.btn)
        lay.addWidget(self.underline)
        self.btn.clicked.connect(self.clicked.emit)

    def set_active(self, active: bool, color: QColor):
        if active:
            self.underline.setStyleSheet(f"background: rgba({color.red()},{color.green()},{color.blue()},230); border:none;")
            self.btn.setStyleSheet(
                f"QPushButton{{background: rgba(255,255,255,28); border:2px solid rgba({color.red()},{color.green()},{color.blue()},230); border-radius: 9px; color:white; padding: 0 8px; font-weight: 800; font-size: 11px;}}"
                "QPushButton:hover{background: rgba(255,255,255,34);} QPushButton:pressed{background: rgba(255,255,255,12);}"
            )
        else:
            self.underline.setStyleSheet("background: rgba(0,0,0,0); border:none;")
            self.btn.setStyleSheet(
                "QPushButton{background: rgba(255,255,255,16); border:none; border-radius: 9px; color:white; padding: 0 9px; font-weight: 700; font-size: 11px;}"
                "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
            )



class FooterBar(QWidget):
    request_open_notes = Signal()
    request_manual_sync = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedHeight(28)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(8)

        self.lbl_sync = QLabel("")
        self.lbl_sync.setStyleSheet(
            "QLabel{color: rgba(255,255,255,190); padding: 0 6px;}"
        )
        self.lbl_sync.hide()

        self.btn_sync = QPushButton("⟳ 手动同步")
        self.btn_sync.setFixedHeight(22)
        self.btn_sync.setStyleSheet(
            "QPushButton{background: rgba(255,255,255,14); border:none; border-radius:8px; color:white; font-weight:800; padding:0 10px;}"
            "QPushButton:hover{background: rgba(255,255,255,22);} QPushButton:pressed{background: rgba(255,255,255,10);}"
        )

        self.btn_sync.clicked.connect(self.request_manual_sync.emit)
        lay.addWidget(self.lbl_sync, 1)
        lay.addWidget(self.btn_sync, 0, Qt.AlignRight)
class TagBar(QWidget):
    tag_clicked = Signal(str)
    manage_clicked = Signal()
    bin_clicked = Signal()
    add_clicked = Signal()
    tag_menu_requested = Signal(str, object)  # (tag, global_pos)

    def __init__(self):
        super().__init__()
        self._tag_colors: Dict[str, str] = {}
        self._btns: List[Tuple[str, TagButton]] = []

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2,0,2,0)
        lay.setSpacing(6)

        # 管理入口已移到顶部栏（HeaderBar）

        self._insert_anchor = QWidget()
        self._insert_anchor.setFixedWidth(1)
        lay.addWidget(self._insert_anchor)
        lay.addStretch(1)

        # 右侧“＋”：新增页面（标签）
        self.btn_add_tag = QPushButton("＋")
        self.btn_add_tag.setFixedSize(26, 20)
        self.btn_add_tag.setStyleSheet(
            "QPushButton{background: rgba(255,255,255,16); border:none; border-radius: 9px; color:white; font-weight: 900;}"
            "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}" 
        )
        self.btn_add_tag.clicked.connect(self.add_clicked.emit)
        lay.addWidget(self.btn_add_tag)

        self.btn_bin = QPushButton("🗑")
        self.btn_bin.setFixedSize(26, 20)
        self.btn_bin.setStyleSheet(
            "QPushButton{background: rgba(255,255,255,16); border:none; border-radius: 9px; color:white; font-weight: 800;}"
            "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
        )
        self.btn_bin.clicked.connect(self.bin_clicked.emit)
        lay.addWidget(self.btn_bin)

        self._lay = lay

    def set_colors(self, tag_colors: Dict[str, str]):
        self._tag_colors = tag_colors or {}

    def set_tags(self, tags: List[str], current: str):
        for _, w in self._btns:
            try:
                self._lay.removeWidget(w)
            except Exception:
                pass
            w.hide()
            w.deleteLater()
        self._btns.clear()

        # insert after anchor (index 1)
        insert_at = 1
        for t in tags:
            if not t:
                continue
            w = TagButton(t)
            c = tag_color(t, self._tag_colors)
            w.set_active(t == current, c)
            w.clicked.connect(lambda _=False, tt=t: self.tag_clicked.emit(tt))
            # 右键标签（页面）菜单
            w.setContextMenuPolicy(Qt.CustomContextMenu)
            w.customContextMenuRequested.connect(
                lambda p, tt=t, ww=w: self.tag_menu_requested.emit(tt, ww.mapToGlobal(p))
            )
            self._lay.insertWidget(insert_at, w)
            insert_at += 1
            self._btns.append((t, w))


class HeaderBar(QWidget):
    request_new_task = Signal()
    request_open_settings = Signal()
    request_open_sort = Signal()
    request_open_tag_manager = Signal()
    request_focus_search = Signal()
    request_manual_sync = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedHeight(30)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6,2,6,2)
        lay.setSpacing(8)

        self.title = QLabel(f"LyTodo v{VERSION}")
        self.title.setStyleSheet("color: rgba(255,255,255,230); font-weight: 900; font-size: 11px;")

        self.btn_manage = QPushButton("管理")
        self.btn_sort = QPushButton("⇅")
        self.btn_add = QPushButton("＋")
        self.btn_search = QPushButton("🔍")
        self.btn_settings = QPushButton("⚙")
        for b in (self.btn_manage, self.btn_sort, self.btn_add, self.btn_search, self.btn_settings):
            b.setFixedSize(26, 20)
            b.setStyleSheet(
                "QPushButton{background: rgba(255,255,255,16); border:none; border-radius:8px; color:white; font-weight:800;}"
                "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
            )

        lay.addWidget(self.title)
        lay.addStretch(1)
        lay.addWidget(self.btn_manage)
        lay.addWidget(self.btn_sort)
        lay.addWidget(self.btn_add)
        lay.addWidget(self.btn_search)
        lay.addWidget(self.btn_settings)

        self.btn_add.clicked.connect(self.request_new_task.emit)
        self.btn_settings.clicked.connect(self.request_open_settings.emit)
        self.btn_sort.clicked.connect(self.request_open_sort.emit)
# (removed) legacy header sync button

        self.btn_manage.clicked.connect(self.request_open_tag_manager.emit)
        self.btn_search.clicked.connect(self.request_focus_search.emit)



class DraggableListView(QListView):
    move_request = Signal(int, int)
    blank_double_clicked = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_row: Optional[int] = None
        self.setDragEnabled(False)
        self._lp_timer = QTimer(self)
        self._lp_timer.setSingleShot(True)
        self._lp_timer.setInterval(260)
        self._lp_timer.timeout.connect(self._enable_longpress_drag)
        self._lp_ready = False
        self._pressing = False
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)


    def _enable_longpress_drag(self):
        if self._pressing:
            self._lp_ready = True
            self.setDragEnabled(True)


    def mousePressEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        self._drag_row = idx.row() if idx.isValid() else None
        self._pressing = True
        self._lp_ready = False
        self.setDragEnabled(False)
        try:
            self._lp_timer.start()
        except Exception:
            pass
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        # 只有长按(约260ms)后才允许拖动排序，避免误触
        if not self._lp_ready:
            super().mouseMoveEvent(e)
            return
        super().mouseMoveEvent(e)

    
    def mouseDoubleClickEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        if not idx.isValid():
            self.blank_double_clicked.emit()
            e.accept()
            return
        super().mouseDoubleClickEvent(e)


    def mouseReleaseEvent(self, e):
        self._pressing = False
        self._lp_ready = False
        self.setDragEnabled(False)
        try:
            self._lp_timer.stop()
        except Exception:
            pass
        super().mouseReleaseEvent(e)


    def dropEvent(self, e):
        dest = self.indexAt(e.position().toPoint()).row()
        if dest < 0:
            dest = (self.model().rowCount() - 1) if self.model() else 0
        if self._drag_row is not None:
            self.move_request.emit(int(self._drag_row), int(dest))
        e.accept()
        self.viewport().update()



class TaskDelegate(QStyledItemDelegate):
    """任务绘制 Delegate（自适应字号）"""
    def __init__(self, font_family: str = "", font_size: int = 10, tag_colors: Optional[Dict[str, str]] = None):
        super().__init__()
        self.font_family = font_family
        self.font_size = int(font_size)
        self.tag_colors = tag_colors or {}

    def _font(self) -> QFont:
        f = QFont()
        if self.font_family:
            f.setFamily(self.font_family)
        f.setPointSize(int(self.font_size))
        f.setBold(True)
        return f

    def _layout(self) -> dict:
        f = self._font()
        fm = QFontMetrics(f)
        h = max(8, fm.height())

        # 外边距（整体更紧凑）
        outer_x = max(4, int(h * 0.42))
        outer_y = max(3, int(h * 0.28))

        # 内边距
        inner_x = max(6, int(h * 0.52))

        # 色条
        bar_w = max(5, int(h * 0.20))
        bar_pad = max(5, int(h * 0.55))

        # 复选框
        cb_size = max(15, int(h * 1.00))
        cb_radius = max(4, int(cb_size * 0.28))

        # 圆角
        card_radius = max(9, int(h * 0.70))

        # pin 预留
        pin_w = max(14, int(h * 0.90))
        pin_pad = max(6, int(h * 0.40))

        # 行高（核心：随字号变化的行间距）
        row_padding = max(9, int(h * 0.60))
        row_h = max(28, h + row_padding)

        gap = max(8, int(h * 0.50))

        return {
            "font": f, "fm": fm, "h": h,
            "outer_x": outer_x, "outer_y": outer_y,
            "inner_x": inner_x,
            "bar_w": bar_w, "bar_pad": bar_pad,
            "cb_size": cb_size, "cb_radius": cb_radius,
            "card_radius": card_radius,
            "pin_w": pin_w, "pin_pad": pin_pad,
            "row_h": row_h, "gap": gap,
        }

    def sizeHint(self, option, index):
        lay = self._layout()
        return QSize(option.rect.width(), int(lay["row_h"]))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        try:
            lay = self._layout()
            ox, oy = lay["outer_x"], lay["outer_y"]
            rect = option.rect.adjusted(ox, oy, -ox, -oy)

            is_selected = bool(option.state & QStyle.State_Selected)
            done = bool(index.data(ROLE_DONE))
            tag = str(index.data(ROLE_TAG) or "")
            pinned = bool(index.data(ROLE_PINNED))

            painter.setRenderHint(QPainter.Antialiasing, True)

            if is_selected:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255, 18))
                painter.drawRoundedRect(rect, lay["card_radius"], lay["card_radius"])

            # left tag bar
            bar_x = rect.left() + lay["inner_x"]
            bar = QRect(bar_x, rect.top() + lay["bar_pad"], lay["bar_w"], max(6, rect.height() - lay["bar_pad"] * 2))
            painter.setPen(Qt.NoPen)
            painter.setBrush(tag_color(tag, self.tag_colors))
            rr = max(3, int(lay["bar_w"] * 0.6))
            painter.drawRoundedRect(bar, rr, rr)

            # checkbox
            cb_size = lay["cb_size"]
            cb_x = bar.right() + lay["gap"]
            cb_y = int(rect.center().y() - cb_size / 2)
            cb = QRect(cb_x, cb_y, cb_size, cb_size)
            painter.setBrush(QColor(0, 0, 0, 60))
            painter.drawRoundedRect(cb, lay["cb_radius"], lay["cb_radius"])
            if done:
                painter.setPen(QColor(255, 255, 255, 220))
                painter.setFont(lay["font"])
                painter.drawText(cb, Qt.AlignCenter, "✓")

            # title
            text_left = cb.right() + lay["gap"]
            pin_reserve = lay["pin_w"] + lay["pin_pad"]
            title_rect = QRect(text_left, rect.top(), max(10, rect.right() - text_left - pin_reserve), rect.height())
            title = str(index.data(Qt.ItemDataRole.DisplayRole) or "")

            painter.setFont(lay["font"])
            painter.setPen(QColor(255, 255, 255, 230) if not done else QColor(255, 255, 255, 120))
            painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, title)

            if pinned:
                p_rect = QRect(rect.right() - lay["pin_w"] - lay["pin_pad"], rect.top(), lay["pin_w"], rect.height())
                painter.setPen(QColor(255, 255, 255, 180))
                painter.setFont(lay["font"])
                painter.drawText(p_rect, Qt.AlignCenter, "★")
        finally:
            painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            lay = self._layout()
            ox, oy = lay["outer_x"], lay["outer_y"]
            rect = option.rect.adjusted(ox, oy, -ox, -oy)

            bar_x = rect.left() + lay["inner_x"]
            bar = QRect(bar_x, rect.top() + lay["bar_pad"], lay["bar_w"], max(6, rect.height() - lay["bar_pad"] * 2))

            cb_size = lay["cb_size"]
            cb_x = bar.right() + lay["gap"]
            cb_y = int(rect.center().y() - cb_size / 2)
            cb = QRect(cb_x, cb_y, cb_size, cb_size)

            if cb.contains(event.position().toPoint()):
                try:
                    real = model.real_index_from_proxy(index.row())
                    t = model.get_all_tasks()[real]
                    t.done = not bool(t.done)
                    t.touch()
                    model.beginResetModel(); model.endResetModel()
                except Exception:
                    pass
                return True
        return super().editorEvent(event, model, option, index)



class CompletedModeBar(QWidget):
    request_restore_selected = Signal()
    request_delete_selected = Signal()
    request_clear_all = Signal()
    request_exit = Signal()

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4,0,4,0)
        lay.setSpacing(8)

        self.lbl = QLabel("已完成模式")
        self.lbl.setStyleSheet("color: rgba(255,255,255,220); font-weight: 900;")
        lay.addWidget(self.lbl)
        lay.addStretch(1)

        self.btn_restore = QPushButton("恢复选中")
        self.btn_delete = QPushButton("删除选中")
        self.btn_clear = QPushButton("全部清空")
        self.btn_back = QPushButton("返回")

        for b in (self.btn_restore, self.btn_delete, self.btn_clear, self.btn_back):
            b.setFixedHeight(28)
            b.setStyleSheet(
                "QPushButton{background: rgba(255,255,255,16); border:none; border-radius:10px; color:white; font-weight:800; padding: 0 10px;}"
                "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
            )

        lay.addWidget(self.btn_restore)
        lay.addWidget(self.btn_delete)
        lay.addWidget(self.btn_clear)
        lay.addWidget(self.btn_back)

        self.btn_restore.clicked.connect(self.request_restore_selected.emit)
        self.btn_delete.clicked.connect(self.request_delete_selected.emit)
        self.btn_clear.clicked.connect(self.request_clear_all.emit)
        self.btn_back.clicked.connect(self.request_exit.emit)

class FramelessMainWindow(QWidget):
    request_settings = Signal()
    request_new_task = Signal()
    request_open_sort = Signal()
    request_open_tag_manager = Signal()
    request_manual_sync = Signal()
    request_open_bin = Signal()
    request_enter_completed_mode = Signal()
    request_exit_completed_mode = Signal()
    request_completed_restore_selected = Signal()
    request_completed_delete_selected = Signal()
    request_completed_clear_all = Signal()
    request_tag_filter = Signal(str)
    request_add_page = Signal()
    request_page_context_menu = Signal(str, object)
    request_task_context_menu = Signal(object, object)
    request_open_top_editor = Signal(object)
    request_search_text = Signal(str)
    request_move_task = Signal(int, int)
    window_geometry_changed = Signal(int,int,int,int)

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.panel_alpha = 160

        root = QVBoxLayout(self)
        self._root_layout = root
        root.setContentsMargins(10,10,10,10)
        root.setSpacing(4)

        self.header = HeaderBar()
        root.addWidget(self.header)

        self.tagbar = TagBar()
        root.addWidget(self.tagbar)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索任务/备注/标签…")
        self.search.setStyleSheet(
            "QLineEdit{background: rgba(255,255,255,12); border: 1px solid rgba(255,255,255,18);"
            "border-radius: 10px; padding: 4px 10px; font-size: 11px; color: white;}"
            "QLineEdit:focus{border: 1px solid rgba(255,255,255,35);}"
        )
        root.addWidget(self.search)

        self.completed_bar = CompletedModeBar()
        self.completed_bar.setVisible(False)
        root.addWidget(self.completed_bar)

        self.top_editor = TopEditor()
        self.top_editor.setVisible(False)
        root.addWidget(self.top_editor, 1)

        self.list_view = DraggableListView()
        self.list_view.setStyleSheet("QListView{background:transparent; border:none; outline:none;} QListView::item{border:none;}")
        self.list_view.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.list_view.setEditTriggers(QListView.NoEditTriggers)
        root.addWidget(self.list_view, 5)

        self.footer = FooterBar()
        root.addWidget(self.footer)

        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(18,18)

        self._dragging=False
        self._drag_pos=None

        self.setMinimumSize(300, 280)

        self.header.request_new_task.connect(self.request_new_task.emit)
        self.header.request_open_settings.connect(self.request_settings.emit)
        self.header.request_open_sort.connect(self.request_open_sort.emit)
        self.header.request_open_tag_manager.connect(self.request_open_tag_manager.emit)
        self.header.request_focus_search.connect(lambda: self.search.setFocus())
        self.footer.request_manual_sync.connect(self.request_manual_sync.emit)

        self.tagbar.tag_clicked.connect(self.request_tag_filter.emit)
        self.tagbar.add_clicked.connect(self.request_add_page.emit)
        self.tagbar.tag_menu_requested.connect(self.request_page_context_menu.emit)
        self.tagbar.bin_clicked.connect(self.request_enter_completed_mode.emit)

        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._on_context)
        self.list_view.doubleClicked.connect(self._on_double)
        self.list_view.blank_double_clicked.connect(self.request_new_task.emit)
        self.list_view.move_request.connect(self.request_move_task.emit)

        self.search.textChanged.connect(self.request_search_text.emit)

        self.completed_bar.request_restore_selected.connect(self.request_completed_restore_selected.emit)
        self.completed_bar.request_delete_selected.connect(self.request_completed_delete_selected.emit)
        self.completed_bar.request_clear_all.connect(self.request_completed_clear_all.emit)
        self.completed_bar.request_exit.connect(self.request_exit_completed_mode.emit)

        self.header.installEventFilter(self)
        self.tagbar.installEventFilter(self)
        self.search.installEventFilter(self)

    def set_window_flags(self, always_on_top: bool):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def set_completed_mode_ui(self, enabled: bool):
        self.completed_bar.setVisible(bool(enabled))
        # when in completed mode, disable creating/moving tasks visually
        self.header.btn_add.setEnabled(not enabled)
        self.header.btn_sort.setEnabled(not enabled)
        # 标签栏：完成模式下禁止新增/管理，但允许查看筛选
        if hasattr(self.tagbar, "btn_add_tag"):
            self.tagbar.btn_add_tag.setEnabled(not enabled)
        self.search.setEnabled(True)

    def _on_context(self, pos):
        idx = self.list_view.indexAt(pos)
        self.request_task_context_menu.emit(self.list_view.viewport().mapToGlobal(pos), idx)

    def _on_double(self, idx):
        if idx and idx.isValid():
            self.request_open_top_editor.emit(idx)

    def open_editor(self, text: str, font_family: str, font_size: int):
        f = QFont()
        if font_family:
            f.setFamily(font_family)
        f.setPointSize(int(font_size))
        self.top_editor.edit.setFont(f)
        self.top_editor.edit.setPlainText(text or "")
        self.top_editor.setVisible(True)
        self.top_editor.edit.setFocus()
        # make editor taller while visible
        try:
            self._root_layout.setStretchFactor(self.top_editor, 3)
            self._root_layout.setStretchFactor(self.list_view, 4)
        except Exception:
            pass

    def close_editor(self):
        self.top_editor.setVisible(False)
        try:
            self._root_layout.setStretchFactor(self.top_editor, 1)
            self._root_layout.setStretchFactor(self.list_view, 5)
        except Exception:
            pass


    def set_sync_status(self, text: str, ok: bool = True, auto_clear_ms: int = 2500):
        """在底部状态栏提示同步状态（适用于 --noconsole 的 exe）。"""
        if not hasattr(self, "footer") or not hasattr(self.footer, "lbl_sync"):
            return

        label = self.footer.lbl_sync
        if not text:
            label.hide()
            return

        if ok:
            label.setStyleSheet(
                "QLabel{background: rgba(40,180,110,120); color: white; padding: 0 8px; border-radius: 8px;}"
            )
        else:
            label.setStyleSheet(
                "QLabel{background: rgba(220,60,60,135); color: white; padding: 0 8px; border-radius: 8px;}"
            )

        label.setText(str(text))
        label.show()

        try:
            QTimer.singleShot(int(auto_clear_ms), label.hide)
        except Exception:
            pass

    def _commit_if_click_blank(self, global_pos: QPoint):
        if not self.top_editor.isVisible():
            return
        local = self.mapFromGlobal(global_pos)
        if not self.top_editor.geometry().contains(local):
            self.top_editor.accepted.emit(self.top_editor.edit.toPlainText())

    def mousePressEvent(self, event):
        self._commit_if_click_blank(event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if obj in (self.header, self.tagbar, self.search):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._dragging=True
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return False
            if event.type() == QEvent.MouseMove and self._dragging and (event.buttons() & Qt.LeftButton):
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                return True
            if event.type() == QEvent.MouseButtonRelease:
                self._dragging=False
        return super().eventFilter(obj, event)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.top_editor.isVisible():
            self.top_editor.edit.setMinimumHeight(max(220, int(self.height()*0.40)))
        self._grip.move(self.width()-self._grip.width()-6, self.height()-self._grip.height()-6)
        self.window_geometry_changed.emit(self.x(), self.y(), self.width(), self.height())

    def moveEvent(self, e):
        super().moveEvent(e)
        self.window_geometry_changed.emit(self.x(), self.y(), self.width(), self.height())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # panel overlay
        r = self.rect().adjusted(3,3,-3,-3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20,25,35,int(self.panel_alpha)))
        p.drawRoundedRect(r, 14, 14)
def closeEvent(self, event):
    # 有托盘时：点击右上角 X 仅隐藏到托盘
    if hasattr(self, "_tray") and self._tray and self._tray.isVisible():
        event.ignore()
        self.hide()
        return
    super().closeEvent(event)


class NotesWindow(QWidget):
    """便签窗口：支持多标签页、右侧 + 新增、右键标签页删除/重命名。"""
    pages_changed = Signal(list)

    def __init__(self, pages: Optional[List[dict]] = None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.panel_alpha = 170
        self.setMinimumSize(520, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        lbl = QLabel("便签")
        lbl.setStyleSheet("color: rgba(255,255,255,230); font-weight: 900;")
        top.addWidget(lbl)
        top.addStretch(1)

        self.btn_close = QPushButton("×")
        self.btn_close.setFixedSize(32, 26)
        self.btn_close.setStyleSheet(
            "QPushButton{background: rgba(255,255,255,16); border:none; border-radius:8px; color:white; font-weight:900;}"
            "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
        )
        top.addWidget(self.btn_close)
        root.addLayout(top)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        root.addWidget(self.tabs, 1)

        # 右上角 + 按钮
        self.btn_add_tab = QPushButton("＋")
        self.btn_add_tab.setFixedSize(28, 22)
        self.btn_add_tab.setStyleSheet(
            "QPushButton{background: rgba(255,255,255,16); border:none; border-radius:8px; color:white; font-weight:900; padding:0 0;}"
            "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
        )
        self.tabs.setCornerWidget(self.btn_add_tab, Qt.TopRightCorner)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(500)
        self._debounce.timeout.connect(self._emit_pages_changed)

        self._pages: List[dict] = []
        self.set_pages(pages or [])

        tb = self.tabs.tabBar()
        tb.setContextMenuPolicy(Qt.CustomContextMenu)
        tb.customContextMenuRequested.connect(self._on_tab_menu)

        self.btn_add_tab.clicked.connect(self._add_page)
        self.btn_close.clicked.connect(self.hide)
        self.tabs.currentChanged.connect(lambda _i: self._debounce.start())

        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(18, 18)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._grip.move(self.width() - self._grip.width() - 6, self.height() - self._grip.height() - 6)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(3, 3, -3, -3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 25, 35, int(self.panel_alpha)))
        p.drawRoundedRect(r, 14, 14)

    def set_pages(self, pages: List[dict]):
        self._pages = []
        self.tabs.clear()

        norm = []
        for p in pages if isinstance(pages, list) else []:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or "")
            title = str(p.get("title") or "").strip() or "便签"
            content = str(p.get("content") or "")
            created_at = float(p.get("created_at", 0.0) or 0.0)
            updated_at = float(p.get("updated_at", 0.0) or 0.0)
            norm.append({"id": pid, "title": title, "content": content, "created_at": created_at, "updated_at": updated_at})

        if not norm:
            norm = [self._new_page_dict("便签 1")]

        for p in norm:
            self._add_page_widget(p, make_current=False)
            self._pages.append(p)

        self.tabs.setCurrentIndex(0)
        self._debounce.start()

    def _new_page_dict(self, title: str) -> dict:
        import uuid, time
        return {
            "id": str(uuid.uuid4()),
            "title": (title or "").strip() or "便签",
            "content": "",
            "created_at": float(time.time()),
            "updated_at": float(time.time()),
        }

    def _add_page_widget(self, page: dict, make_current: bool = True):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        ed = QTextEdit()
        ed.setStyleSheet(
            "QTextEdit{background: rgba(0,0,0,18); border: 1px solid rgba(255,255,255,18); border-radius: 12px; color: white; padding:8px;}"
            "QTextEdit:focus{border: 1px solid rgba(255,255,255,35);}"
        )
        ed.setPlainText(str(page.get("content") or ""))
        lay.addWidget(ed, 1)

        idx = self.tabs.addTab(w, str(page.get("title") or "便签"))

        def on_changed():
            try:
                i = self.tabs.indexOf(w)
                if i < 0:
                    return
                self._pages[i]["content"] = ed.toPlainText()
                import time as _t
                self._pages[i]["updated_at"] = float(_t.time())
                self._debounce.start()
            except Exception:
                pass

        ed.textChanged.connect(on_changed)

        # 双击标签页标题重命名
        #（Qt 没有原生直接编辑标题，这里用右键菜单做主入口）

        if make_current:
            self.tabs.setCurrentIndex(idx)

    def _on_tab_menu(self, pos: QPoint):
        tb = self.tabs.tabBar()
        idx = tb.tabAt(pos)
        if idx < 0:
            return

        menu = QMenu(self)
        act_rename = menu.addAction("重命名")
        act_delete = menu.addAction("删除标签页")

        act = menu.exec(tb.mapToGlobal(pos))
        if act == act_rename:
            self._rename_page(idx)
        elif act == act_delete:
            self._delete_page(idx)

    def _rename_page(self, idx: int):
        if idx < 0 or idx >= len(self._pages):
            return
        cur = str(self._pages[idx].get("title") or "")
        name = self._prompt("重命名标签页", cur)
        if not name:
            return
        self._pages[idx]["title"] = name
        self.tabs.setTabText(idx, name)
        self._debounce.start()

    def _delete_page(self, idx: int):
        if len(self._pages) <= 1:
            # 至少保留一个便签页
            return
        if idx < 0 or idx >= len(self._pages):
            return
        self._pages.pop(idx)
        self.tabs.removeTab(idx)
        self._debounce.start()

    def _add_page(self):
        title = f"便签 {len(self._pages) + 1}"
        p = self._new_page_dict(title)
        self._pages.append(p)
        self._add_page_widget(p, make_current=True)

        # 创建后引导重命名（可选）
        self._debounce.start()

    def _prompt(self, title: str, default: str = "") -> Optional[str]:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setFixedSize(320, 140)
        lay = QVBoxLayout(dlg)
        ed = QLineEdit()
        ed.setText(default or "")
        lay.addWidget(ed)
        row = QHBoxLayout()
        row.addStretch(1)
        b_ok = QPushButton("确定")
        b_cancel = QPushButton("取消")
        row.addWidget(b_ok)
        row.addWidget(b_cancel)
        lay.addLayout(row)
        b_ok.clicked.connect(dlg.accept)
        b_cancel.clicked.connect(dlg.reject)
        ed.setFocus()
        ed.selectAll()
        if dlg.exec():
            v = ed.text().strip()
            return v if v else None
        return None

    def _emit_pages_changed(self):
        try:
            self.pages_changed.emit(list(self._pages))
        except Exception:
            pass


class TrashBinWindow(QWidget):
    # mode: "completed" or "deleted"
    request_restore_completed = Signal(list)
    request_delete_completed_selected = Signal(list)
    request_clear_all_completed = Signal()

    request_restore_deleted = Signal(list)
    request_delete_deleted_selected = Signal(list)   # hard delete selected deleted items
    request_clear_all_deleted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.panel_alpha = 170
        self.setMinimumSize(420, 360)

        root = QVBoxLayout(self)
        root.setContentsMargins(10,10,10,10)
        root.setSpacing(8)

        top = QHBoxLayout()
        lbl = QLabel("收集箱")
        lbl.setStyleSheet("color: rgba(255,255,255,230); font-weight: 900;")
        top.addWidget(lbl); top.addStretch(1)
        self.btn_close = QPushButton("×")
        self.btn_close.setFixedSize(32,26)
        self.btn_close.setStyleSheet(
            "QPushButton{background: rgba(255,255,255,16); border:none; border-radius:8px; color:white; font-weight:900;}"
            "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
        )
        top.addWidget(self.btn_close)
        root.addLayout(top)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # Completed tab
        self.tab_completed = QWidget()
        c_lay = QVBoxLayout(self.tab_completed)
        self.list_completed = QListWidget()
        self.list_completed.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_completed.setStyleSheet(
            "QListWidget{background: rgba(0,0,0,18); border: 1px solid rgba(255,255,255,18); border-radius: 12px; color: white; padding:6px;}"
            "QListWidget::item{padding:6px; border-radius:8px;} QListWidget::item:selected{background: rgba(255,255,255,16);}"
        )
        c_lay.addWidget(self.list_completed, 1)

        c_btns = QHBoxLayout()
        self.btn_restore_c = QPushButton("恢复选中")
        self.btn_delete_c = QPushButton("删除选中")
        self.btn_clear_c = QPushButton("全部清空")
        for b in (self.btn_restore_c, self.btn_delete_c, self.btn_clear_c):
            b.setFixedHeight(30)
            b.setStyleSheet(
                "QPushButton{background: rgba(255,255,255,16); border:none; border-radius:10px; color:white; font-weight:800; padding: 0 12px;}"
                "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
            )
        c_btns.addWidget(self.btn_restore_c)
        c_btns.addWidget(self.btn_delete_c)
        c_btns.addStretch(1)
        c_btns.addWidget(self.btn_clear_c)
        c_lay.addLayout(c_btns)

        # Deleted tab
        self.tab_deleted = QWidget()
        d_lay = QVBoxLayout(self.tab_deleted)
        self.list_deleted = QListWidget()
        self.list_deleted.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_deleted.setStyleSheet(
            "QListWidget{background: rgba(0,0,0,18); border: 1px solid rgba(255,255,255,18); border-radius: 12px; color: white; padding:6px;}"
            "QListWidget::item{padding:6px; border-radius:8px;} QListWidget::item:selected{background: rgba(255,255,255,16);}"
        )
        d_lay.addWidget(self.list_deleted, 1)

        d_btns = QHBoxLayout()
        self.btn_restore_d = QPushButton("恢复选中")
        self.btn_delete_d = QPushButton("彻底删除选中")
        self.btn_clear_d = QPushButton("全部清空")
        for b in (self.btn_restore_d, self.btn_delete_d, self.btn_clear_d):
            b.setFixedHeight(30)
            b.setStyleSheet(
                "QPushButton{background: rgba(255,255,255,16); border:none; border-radius:10px; color:white; font-weight:800; padding: 0 12px;}"
                "QPushButton:hover{background: rgba(255,255,255,24);} QPushButton:pressed{background: rgba(255,255,255,12);}"
            )
        d_btns.addWidget(self.btn_restore_d)
        d_btns.addWidget(self.btn_delete_d)
        d_btns.addStretch(1)
        d_btns.addWidget(self.btn_clear_d)
        d_lay.addLayout(d_btns)

        self.tabs.addTab(self.tab_completed, "已完成")
        self.tabs.addTab(self.tab_deleted, "已删除")

        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(18,18)

        self.btn_close.clicked.connect(self.hide)
        self.btn_restore_c.clicked.connect(self._restore_completed)
        self.btn_delete_c.clicked.connect(self._delete_completed)
        self.btn_clear_c.clicked.connect(self.request_clear_all_completed.emit)

        self.btn_restore_d.clicked.connect(self._restore_deleted)
        self.btn_delete_d.clicked.connect(self._delete_deleted)
        self.btn_clear_d.clicked.connect(self.request_clear_all_deleted.emit)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._grip.move(self.width()-self._grip.width()-6, self.height()-self._grip.height()-6)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(3,3,-3,-3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20,25,35,int(self.panel_alpha)))
        p.drawRoundedRect(r, 14, 14)

    def set_completed_items(self, items: List[Tuple[int,str]]):
        self.list_completed.clear()
        for real_idx, text in items:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, real_idx)
            self.list_completed.addItem(it)

    def set_deleted_items(self, items: List[Tuple[int,str]]):
        self.list_deleted.clear()
        for real_idx, text in items:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, real_idx)
            self.list_deleted.addItem(it)

    def _selected_real(self, which: str) -> List[int]:
        lw = self.list_completed if which=="c" else self.list_deleted
        return [int(it.data(Qt.UserRole)) for it in lw.selectedItems()]

    def _remove_selected(self, which: str):
        lw = self.list_completed if which=="c" else self.list_deleted
        rows = sorted([lw.row(it) for it in lw.selectedItems()], reverse=True)
        for r in rows:
            lw.takeItem(r)

    def _restore_completed(self):
        idxs = self._selected_real("c")
        if not idxs: return
        self.request_restore_completed.emit(idxs)
        self._remove_selected("c")

    def _delete_completed(self):
        idxs = self._selected_real("c")
        if not idxs: return
        self.request_delete_completed_selected.emit(idxs)
        self._remove_selected("c")

    def _restore_deleted(self):
        idxs = self._selected_real("d")
        if not idxs: return
        self.request_restore_deleted.emit(idxs)
        self._remove_selected("d")

    def _delete_deleted(self):
        idxs = self._selected_real("d")
        if not idxs: return
        self.request_delete_deleted_selected.emit(idxs)
        self._remove_selected("d")


class SettingsDialog(QDialog):
    request_purge_completed = Signal()
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(480, 360)

        root = QVBoxLayout(self)
        tabs = QTabWidget(); root.addWidget(tabs)

        tab_basic = QWidget(); lay = QVBoxLayout(tab_basic)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("已完成自动收纳："))
        self.cb_auto_archive = QCheckBox(); self.cb_auto_archive.setChecked(settings.auto_archive_completed)
        row1.addWidget(self.cb_auto_archive); row1.addStretch(1)
        lay.addLayout(row1)

        row_startup = QHBoxLayout()
        row_startup.addWidget(QLabel("开机自启动（Windows）："))
        self.cb_startup = QCheckBox(); self.cb_startup.setChecked(bool(getattr(settings, "launch_at_startup", False)))
        row_startup.addWidget(self.cb_startup); row_startup.addStretch(1)
        lay.addLayout(row_startup)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("主界面显示已完成："))
        self.cb_show_completed = QCheckBox()
        self.cb_show_completed.setChecked(settings.show_completed_in_main and (not settings.auto_archive_completed))
        self.cb_show_completed.setEnabled(not settings.auto_archive_completed)
        row2.addWidget(self.cb_show_completed); row2.addStretch(1)
        lay.addLayout(row2)

        def _sync_enable():
            enabled = not self.cb_auto_archive.isChecked()
            self.cb_show_completed.setEnabled(enabled)
            if not enabled:
                self.cb_show_completed.setChecked(False)
        self.cb_auto_archive.toggled.connect(lambda _: _sync_enable())

        b_purge = QPushButton("清空已完成（危险）")
        b_purge.clicked.connect(self.request_purge_completed.emit)
        lay.addWidget(b_purge)
        lay.addStretch(1)
        tabs.addTab(tab_basic, "基础")

        tab_main = QWidget(); lay2 = QVBoxLayout(tab_main)
        rowf = QHBoxLayout(); rowf.addWidget(QLabel("字体："))
        self.font_box = QFontComboBox()
        fam = settings.font_family or best_default_font_family()
        if fam:
            self.font_box.setCurrentFont(QFont(fam))
        rowf.addWidget(self.font_box); rowf.addStretch(1)
        lay2.addLayout(rowf)

        rows = QHBoxLayout(); rows.addWidget(QLabel("字号："))
        self.spin_font = QSpinBox(); self.spin_font.setRange(8,22); self.spin_font.setValue(int(settings.font_size))
        rows.addWidget(self.spin_font); rows.addStretch(1)
        lay2.addLayout(rows)

        lay2.addStretch(1)
        tabs.addTab(tab_main, "主窗口")

        tab_float = QWidget(); lay3 = QVBoxLayout(tab_float)
        rowt = QHBoxLayout(); rowt.addWidget(QLabel("置顶显示："))
        self.cb_top = QCheckBox(); self.cb_top.setChecked(settings.always_on_top)
        rowt.addWidget(self.cb_top); rowt.addStretch(1)
        lay3.addLayout(rowt)

        rowo = QHBoxLayout(); rowo.addWidget(QLabel("背景透明度："))
        self.slider_opacity = QSlider(Qt.Horizontal); self.slider_opacity.setRange(40,230); self.slider_opacity.setValue(int(settings.panel_opacity))
        rowo.addWidget(self.slider_opacity)
        self.lbl_op = QLabel(str(int(settings.panel_opacity))); self.lbl_op.setFixedWidth(40)
        rowo.addWidget(self.lbl_op)
        lay3.addLayout(rowo)
        self.slider_opacity.valueChanged.connect(lambda v: self.lbl_op.setText(str(int(v))))
        lay3.addStretch(1)
        tabs.addTab(tab_float, "浮窗")


        tab_sync = QWidget(); layS = QVBoxLayout(tab_sync)
        rowse = QHBoxLayout(); rowse.addWidget(QLabel("启用同步："))
        self.cb_sync = QCheckBox(); self.cb_sync.setChecked(settings.sync_enabled)
        rowse.addWidget(self.cb_sync); rowse.addStretch(1)
        layS.addLayout(rowse)

        rurl = QHBoxLayout(); rurl.addWidget(QLabel("服务器URL："))
        self.ed_sync_url = QLineEdit(); self.ed_sync_url.setText(settings.sync_base_url)
        rurl.addWidget(self.ed_sync_url)
        layS.addLayout(rurl)

        rt = QHBoxLayout(); rt.addWidget(QLabel("Token："))
        self.ed_sync_token = QLineEdit(); self.ed_sync_token.setEchoMode(QLineEdit.Password)
        self.ed_sync_token.setText(settings.sync_token)
        rt.addWidget(self.ed_sync_token)
        layS.addLayout(rt)

        ru = QHBoxLayout(); ru.addWidget(QLabel("用户ID："))
        self.ed_sync_user = QLineEdit(); self.ed_sync_user.setText(getattr(settings, "sync_user", "default") or "default")
        ru.addWidget(self.ed_sync_user)
        layS.addLayout(ru)

        layS.addWidget(QLabel("策略：启动自动拉取（pull），退出自动推送（push）。"))
        self.cb_sync_b = QCheckBox("策略B：编辑后3秒自动推送（推荐）")
        self.cb_sync_b.setChecked(bool(getattr(settings, "sync_strategy_b", True)))
        layS.addWidget(self.cb_sync_b)

        self.cb_sync_timer = QCheckBox("后台定时推送（60秒）")
        self.cb_sync_timer.setChecked(bool(getattr(settings, "sync_timer_enabled", True)))
        layS.addWidget(self.cb_sync_timer)
        layS.addStretch(1)
        tabs.addTab(tab_sync, "同步")


        tab_hotkey = QWidget(); lay5 = QVBoxLayout(tab_hotkey)
        rowh1 = QHBoxLayout(); rowh1.addWidget(QLabel("启用全局快捷键（Windows）："))
        self.cb_hotkey = QCheckBox(); self.cb_hotkey.setChecked(settings.hotkey_enabled)
        rowh1.addWidget(self.cb_hotkey); rowh1.addStretch(1)
        lay5.addLayout(rowh1)

        rowh2 = QHBoxLayout(); rowh2.addWidget(QLabel("显示/隐藏："))
        self.key_edit = QKeySequenceEdit(QKeySequence(settings.hotkey_sequence))
        rowh2.addWidget(self.key_edit); rowh2.addStretch(1)
        lay5.addLayout(rowh2)

        rowh3 = QHBoxLayout(); rowh3.addWidget(QLabel("触发时短暂置顶："))
        self.cb_force_top = QCheckBox(); self.cb_force_top.setChecked(settings.hotkey_force_top)
        rowh3.addWidget(self.cb_force_top); rowh3.addStretch(1)
        lay5.addLayout(rowh3)

        lay5.addWidget(QLabel("提示：若快捷键被占用会注册失败，换个组合键即可。"))
        lay5.addStretch(1)
        tabs.addTab(tab_hotkey, "快捷键")

        bottom = QHBoxLayout(); bottom.addStretch(1)
        ok = QPushButton("确定"); cancel = QPushButton("取消")
        bottom.addWidget(ok); bottom.addWidget(cancel)
        root.addLayout(bottom)
        ok.clicked.connect(self.accept); cancel.clicked.connect(self.reject)

    def get_values(self):
        return {
            "auto_archive_completed": self.cb_auto_archive.isChecked(),
            "show_completed_in_main": self.cb_show_completed.isChecked(),
            "launch_at_startup": self.cb_startup.isChecked(),
            "font_family": self.font_box.currentFont().family(),
            "font_size": int(self.spin_font.value()),
            "always_on_top": self.cb_top.isChecked(),
            "panel_opacity": int(self.slider_opacity.value()),
            "hotkey_enabled": self.cb_hotkey.isChecked(),
            "hotkey_sequence": self.key_edit.keySequence().toString() or "Ctrl+Alt+T",
            "hotkey_force_top": self.cb_force_top.isChecked(),
            "sync_enabled": self.cb_sync.isChecked(),
            "sync_base_url": self.ed_sync_url.text().strip(),
            "sync_token": self.ed_sync_token.text().strip(),
            "sync_user": self.ed_sync_user.text().strip() or "default",
            "sync_strategy_b": self.cb_sync_b.isChecked(),
            "sync_timer_enabled": self.cb_sync_timer.isChecked(),
        }


class TagManagerDialog(QDialog):
    request_set_filter = Signal(str)
    colors_changed = Signal(dict)
    tags_changed = Signal(list)

    def __init__(self, tag_names: List[str], tag_colors: Dict[str,str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("标签管理")
        self.setFixedSize(420, 360)

        self._tags = [t for t in tag_names if t and t.strip()]
        if "默认" not in self._tags: self._tags.append("默认")
        if "全部" not in self._tags: self._tags.insert(0,"全部")
        self._colors = dict(tag_colors or {})

        root = QVBoxLayout(self)
        root.addWidget(QLabel("标签列表"))
        self.listw = QListWidget(); self.listw.setSelectionMode(QListWidget.SingleSelection)
        root.addWidget(self.listw)
        self._reload()

        btns = QHBoxLayout()
        self.btn_add = QPushButton("新增"); self.btn_rename=QPushButton("重命名"); self.btn_color=QPushButton("颜色…"); self.btn_delete=QPushButton("删除")
        for b in (self.btn_add, self.btn_rename, self.btn_color, self.btn_delete):
            btns.addWidget(b)
        root.addLayout(btns)

        self.btn_use = QPushButton("设为当前筛选")
        root.addWidget(self.btn_use)

        bottom = QHBoxLayout(); bottom.addStretch(1); ok=QPushButton("关闭"); bottom.addWidget(ok); root.addLayout(bottom)
        ok.clicked.connect(self.accept)

        self.btn_add.clicked.connect(self._add)
        self.btn_rename.clicked.connect(self._rename)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_use.clicked.connect(self._use)
        self.btn_color.clicked.connect(self._set_color)

    def _reload(self):
        self.listw.clear()
        for t in self._tags:
            it = QListWidgetItem(t)
            c = QColor(self._colors.get(t,"")) if self._colors.get(t) else None
            if c and c.isValid():
                it.setForeground(c)
            self.listw.addItem(it)

    def _selected(self) -> Optional[str]:
        items = self.listw.selectedItems()
        return items[0].text() if items else None

    def _prompt(self, title: str, default: str="") -> Optional[str]:
        dlg = QDialog(self); dlg.setWindowTitle(title); dlg.setFixedSize(320,140)
        lay = QVBoxLayout(dlg)
        ed = QLineEdit(); ed.setText(default); lay.addWidget(ed)
        row = QHBoxLayout(); row.addStretch(1)
        b_ok=QPushButton("确定"); b_cancel=QPushButton("取消")
        row.addWidget(b_ok); row.addWidget(b_cancel); lay.addLayout(row)
        b_ok.clicked.connect(dlg.accept); b_cancel.clicked.connect(dlg.reject)
        if dlg.exec():
            v = ed.text().strip()
            return v if v else None
        return None

    def _add(self):
        name = self._prompt("新增标签","")
        if not name or name in self._tags: return
        self._tags.append(name)
        self._reload(); self.tags_changed.emit(self._tags)

    def _rename(self):
        cur = self._selected()
        if not cur or cur in ("默认","全部"): return
        new = self._prompt("重命名标签", cur)
        if not new or new==cur or new in self._tags: return
        i=self._tags.index(cur); self._tags[i]=new
        if cur in self._colors:
            self._colors[new]=self._colors.pop(cur)
        self._reload(); self.colors_changed.emit(self._colors); self.tags_changed.emit(self._tags)

    def _set_color(self):
        cur = self._selected()
        if not cur or cur=="全部": return
        base = QColor(self._colors.get(cur,"")) if self._colors.get(cur) else QColor(80,180,255)
        c = QColorDialog.getColor(base, self, "选择标签颜色")
        if c.isValid():
            self._colors[cur]=c.name()
            self._reload(); self.colors_changed.emit(self._colors)

    def _delete(self):
        cur = self._selected()
        if not cur or cur in ("默认","全部"): return
        self._tags=[t for t in self._tags if t!=cur]
        self._colors.pop(cur, None)
        self._reload(); self.colors_changed.emit(self._colors); self.tags_changed.emit(self._tags)

    def _use(self):
        cur=self._selected()
        if cur:
            self.request_set_filter.emit(cur)


class TaskEditDialog(QDialog):
    request_delete = Signal()
    def __init__(self, text: str, note: str, tag: str, tags: List[str], done: bool, pinned: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑任务")
        self.setFixedSize(440, 420)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("任务（支持多行）："))
        self.ed_text = QTextEdit(); self.ed_text.setPlainText(text or ""); self.ed_text.setFixedHeight(110)
        self.ed_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ed_text.setLineWrapMode(QTextEdit.WidgetWidth)
        root.addWidget(self.ed_text)
        self._install_cn_context_menu(self.ed_text)

        row = QHBoxLayout(); row.addWidget(QLabel("标签："))
        self.cb_tag = QComboBox()
        for t in tags:
            if t!="全部": self.cb_tag.addItem(t)
        if tag: self.cb_tag.setCurrentText(tag)
        row.addWidget(self.cb_tag); row.addStretch(1)

        self.cb_done = QCheckBox("已完成"); self.cb_done.setChecked(done)
        self.cb_pinned = QCheckBox("置顶"); self.cb_pinned.setChecked(pinned)
        row.addWidget(self.cb_done); row.addWidget(self.cb_pinned)
        root.addLayout(row)

        root.addWidget(QLabel("备注："))
        self.ed_note = QTextEdit(); self.ed_note.setPlainText(note or ""); self.ed_note.setFixedHeight(140)
        self.ed_note.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ed_note.setLineWrapMode(QTextEdit.WidgetWidth)
        root.addWidget(self.ed_note)
        self._install_cn_context_menu(self.ed_note)

        btns = QHBoxLayout()
        self.btn_delete=QPushButton("删除"); btns.addWidget(self.btn_delete)
        btns.addStretch(1)
        ok=QPushButton("确定"); cancel=QPushButton("取消")
        btns.addWidget(ok); btns.addWidget(cancel)
        root.addLayout(btns)
        ok.clicked.connect(self.accept); cancel.clicked.connect(self.reject)
        self.btn_delete.clicked.connect(self._del)

    def _del(self):
        self.request_delete.emit()
        self.accept()

    def values(self):
        return {
            "text": self.ed_text.toPlainText(),
            "note": self.ed_note.toPlainText(),
            "tag": self.cb_tag.currentText() or "默认",
            "done": self.cb_done.isChecked(),
            "pinned": self.cb_pinned.isChecked(),
        }

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont


import os
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction

def setup_tray(app: QApplication, main_window):
    """Windows 托盘图标：右键菜单包含 显示/隐藏 与 退出。"""
    icon_path = os.path.join(os.path.dirname(__file__), "tray.ico")
    icon = QIcon(icon_path) if os.path.exists(icon_path) else app.windowIcon()

    tray = QSystemTrayIcon(icon, parent=main_window)
    tray.setToolTip("LyTodo")

    menu = QMenu()

    act_show_hide = QAction("显示/隐藏", tray)
    act_quit = QAction("退出", tray)

    def toggle_show():
        if main_window.isVisible():
            main_window.hide()
        else:
            main_window.show()
            main_window.raise_()
            main_window.activateWindow()

    def do_quit():
        # 触发 Qt 正常退出流程（会调用 aboutToQuit / closeEvent 等）
        tray.hide()
        app.quit()

    act_show_hide.triggered.connect(toggle_show)
    act_quit.triggered.connect(do_quit)

    menu.addAction(act_show_hide)
    menu.addSeparator()
    menu.addAction(act_quit)

    tray.setContextMenu(menu)

    def on_activated(reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            toggle_show()

    tray.activated.connect(on_activated)
    tray.show()

    # 防止被 GC 回收
    main_window._tray = tray
    return tray

from repository import JsonRepository
from version import VERSION
from controller import AppController


def main():
    app = QApplication(sys.argv)
    # Modern default font
    app.setFont(QFont("Microsoft YaHei UI", 10))
    repo = JsonRepository("storage.json")
    controller = AppController(repo, app)
    controller.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

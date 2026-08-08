# -*- coding: utf-8 -*-
"""入口：启动爱心入口 + 控制面板 + 系统托盘（面板可隐藏，点爱心唤回）。"""
import sys

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from control_panel import ControlPanel
from heart_entry import HeartEntry


def _make_icon():
    """生成一个粉色小猫脸托盘图标。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 143, 179))
    p.drawEllipse(6, 12, 52, 52)
    p.drawEllipse(4, 0, 22, 22)   # 左耳
    p.drawEllipse(38, 0, 22, 22)  # 右耳
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(19, 30, 11, 13)
    p.drawEllipse(34, 30, 11, 13)
    p.setBrush(QColor(64, 64, 64))
    p.drawEllipse(23, 34, 5, 6)
    p.drawEllipse(36, 34, 5, 6)
    p.setPen(QColor(214, 90, 130))
    p.drawArc(26, 40, 12, 10, 0, -180 * 16)
    p.end()
    return QIcon(pm)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("桌宠插件")

    panel = ControlPanel()

    def toggle_panel():
        if panel.isHidden():
            panel.show_panel()
        else:
            panel.hide_to_tray()

    # 爱心入口：点击切换面板
    heart = HeartEntry(size=120, on_click=toggle_panel)
    scr = QApplication.primaryScreen().availableGeometry()
    heart.move(scr.right() - heart.width() - 24, scr.center().y() - heart.height() // 2)
    heart.show()

    # 待办提醒调度：到点让第一只存活宠物走到屏幕中央播报
    from reminder import RemindScheduler
    scheduler = RemindScheduler(app)
    scheduler.remind_fired.connect(panel.on_reminder)

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(_make_icon(), app)
        tray.setToolTip("桌宠插件")
        menu = QMenu()
        act_show = menu.addAction("🖥️ 显示/隐藏面板")
        act_show.triggered.connect(toggle_panel)
        act_quit = menu.addAction("退出")
        act_quit.triggered.connect(app.quit)
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: toggle_panel()
            if reason == QSystemTrayIcon.Trigger else None)
        tray.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
# -*- coding: utf-8 -*-
"""控制面板：异形可爱卡片窗口，选择图片、抠图预览、创建/管理桌宠。"""
import json
import os
import random

from PyQt5.QtCore import QPointF, QRectF, Qt, QThread, pyqtSignal
from PyQt5.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QRegion)
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from animations import ACTIONS
from cutout import cutout
from pet_window import PetWindow

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

PANEL_QSS = """
QWidget#PanelRoot { background: transparent; }
QLabel { color: #7a5a70; font-family: "Microsoft YaHei"; }
QLabel#StatusLabel { color: #a68097; }
QPushButton {
  background: #ffe3ee; color: #b05f87; border: none; border-radius: 14px;
  font-family: "Microsoft YaHei"; font-size: 12px; padding: 7px 8px;
}
QPushButton:hover { background: #ffd2e4; }
QPushButton:pressed { background: #ffbdd8; }
QPushButton#PickBtn {
  background: #ff8fb3; color: white; font-size: 14px; border-radius: 14px; padding: 9px;
}
QPushButton#PickBtn:hover { background: #ff79a6; }
QPushButton#DangerBtn { background: #ffe6e6; color: #c0506d; }
QPushButton#DangerBtn:hover { background: #ffd4d4; }
QSlider::groove:horizontal { height: 8px; background: #ffe3ee; border-radius: 4px; }
QSlider::sub-page:horizontal { background: #ff8fb3; border-radius: 4px; }
QSlider::handle:horizontal {
  width: 18px; height: 18px; margin: -5px 0; background: #ffffff;
  border: 2px solid #ff8fb3; border-radius: 9px;
}
QComboBox {
  background: #ffffff; border: 1px solid #ffc4d8; border-radius: 8px;
  padding: 4px 8px; color: #7a5a70; font-family: "Microsoft YaHei";
}
QCheckBox { color: #7a5a70; font-family: "Microsoft YaHei"; }
QCheckBox::indicator {
  width: 16px; height: 16px; border: 2px solid #ff9fc0; border-radius: 4px;
  background: white;
}
QCheckBox::indicator:checked { background: #ff8fb3; }
"""


def pil_to_qimage(pil_img):
    img = pil_img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    return qimg.copy()


class CutWorker(QThread):
    done = pyqtSignal(object, str)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, path, model):
        super().__init__()
        self.path = path
        self.model = model

    def run(self):
        try:
            result = cutout(self.path, model=self.model, on_status=self.status.emit)
            self.done.emit(result, self.path)
        except Exception as e:
            self.failed.emit(str(e))


class DragBar(QWidget):
    """可爱标题栏，按住可拖动整个面板，可最小化到托盘。"""

    def __init__(self, text, on_min=None):
        super().__init__()
        self.setFixedHeight(46)
        self._drag = None
        self.title = QLabel(text)
        self.title.setStyleSheet("font-size:16px;font-weight:bold;color:#b05a80;"
                                 "background:transparent;padding-left:8px;")
        self.sub = QLabel("⋆｡°✩ 抠图 · 桌宠 · 一屏玩")
        self.sub.setStyleSheet("font-size:10px;color:#c98aa6;background:transparent;")
        self.btn_min = QPushButton("─")
        self.btn_min.setFixedSize(30, 30)
        self.btn_min.setStyleSheet(
            "QPushButton{background:#ffd1e2;color:#b05f87;border-radius:15px;"
            "font-size:14px;font-weight:bold;}"
            "QPushButton:hover{background:#ffc2d9;}")
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(30, 30)
        self.btn_close.setStyleSheet(
            "QPushButton{background:#ff8fb3;color:white;border-radius:15px;"
            "font-size:14px;font-weight:bold;}"
            "QPushButton:hover{background:#ff6f9f;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 0)
        lay.setSpacing(6)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(self.title)
        col.addWidget(self.sub)
        lay.addLayout(col)
        lay.addStretch(1)
        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_close)
        self.btn_close.clicked.connect(self.window().close)
        if on_min is not None:
            self.btn_min.clicked.connect(on_min)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPos() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.LeftButton):
            self.window().move(e.globalPos() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("桌宠插件 - 控制面板")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setFixedSize(520, 720)
        self.setObjectName("PanelRoot")
        self._drag = None
        self.pets = []
        self._pending_result = None
        self._pending_path = None
        self._worker = None
        self._config = self._load_config()

        self.setStyleSheet(PANEL_QSS)
        self._load_ui()
        self._apply_config_ui()
        self.setAcceptDrops(True)

    # ---------- 异形外观 ----------
    def hide_to_tray(self):
        """最小化到托盘：隐藏面板，用托盘图标恢复（由 main 负责创建托盘）。"""
        self.hide()

    def show_panel(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _panel_path(self):
        w, h = self.width(), self.height()
        path = QPainterPath()
        r = 24
        path.addRoundedRect(QRectF(0, 0, w, h), r, r)
        ear = QPainterPath()
        ear.addEllipse(QRectF(w - 104, -30, 54, 54))
        path = path.united(ear)
        ear = QPainterPath()
        ear.addEllipse(QRectF(16, -24, 46, 46))
        path = path.united(ear)
        return path

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = self._panel_path()
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor("#fff2f7"))
        grad.setColorAt(0.12, QColor("#ffe3ee"))
        grad.setColorAt(1.0, QColor("#ffd0e3"))
        p.fillPath(path, grad)
        p.setPen(QPen(QColor(255, 255, 255, 200), 2))
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 214, 233, 190), 1))
        p.setBrush(QColor(255, 255, 255, 150))
        p.drawEllipse(QRectF(28, self.height() - 40, 16, 16))
        p.drawEllipse(QRectF(52, self.height() - 30, 12, 12))

    def _apply_mask(self):
        self.setMask(QRegion(self._panel_path().toFillPolygon().toPolygon()))

    def showEvent(self, e):
        super().showEvent(e)
        self._apply_mask()

    # ---------- 配置 ----------
    def _load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        return cfg

    def _save_config(self):
        cfg = self._config
        cfg["model"] = self.model_combo.currentText()
        cfg["size_scale"] = self.size_slider.value() / 100.0
        cfg["opacity"] = self.opacity_slider.value() / 100.0
        cfg["auto_actions"] = self.auto_check.isChecked()
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- UI ----------
    def _load_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 4, 28, 20)
        root.setSpacing(8)

        root.addWidget(DragBar("🐾 桌宠小屋", on_min=self.hide_to_tray))
        root.addSpacing(2)

        self.btn_pick = QPushButton("🌈 选择图片 · 自动抠图")
        self.btn_pick.setObjectName("PickBtn")
        self.btn_pick.clicked.connect(self.pick_image)
        root.addWidget(self.btn_pick)

        self.preview = QLabel("选一张照片，AI 自动识别主体抠图\n把 TA 变成桌面上的小精灵")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(130)
        self.preview.setStyleSheet(
            "QLabel{border:2px solid #ffc9dc;border-radius:16px;background:#ffffff;"
            "color:#c88aa6;font-size:13px;}")
        root.addWidget(self.preview)

        self.status = QLabel("提示：把图片直接拖进来也可以")
        self.status.setObjectName("StatusLabel")
        root.addWidget(self.status)

        opt = QWidget()
        ov = QVBoxLayout(opt)
        ov.setContentsMargins(0, 4, 0, 4)
        ov.setSpacing(6)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("抠图模型"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["u2net（推荐·质量好）", "u2netp（轻量·快）", "isnet-general-use"])
        model_row.addWidget(self.model_combo, 1)
        ov.addLayout(model_row)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("大小"))
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(8, 230)
        self.size_slider.setValue(100)
        self.size_label = QLabel("100%")
        size_row.addWidget(self.size_slider, 1)
        size_row.addWidget(self.size_label)
        self.size_slider.valueChanged.connect(self._on_size)
        ov.addLayout(size_row)

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("透明度"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(100)
        self.opacity_label = QLabel("100%")
        op_row.addWidget(self.opacity_slider, 1)
        op_row.addWidget(self.opacity_label)
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        ov.addLayout(op_row)

        self.auto_check = QCheckBox("自动随机动作（每隔几秒自己跟自己玩）")
        self.auto_check.toggled.connect(self._on_auto)
        ov.addWidget(self.auto_check)
        root.addWidget(opt)

        act_label = QLabel("🎬 点它！开始表演")
        act_label.setStyleSheet("font-weight:bold;color:#b3597f;font-size:13px;")
        root.addWidget(act_label)

        grid = QGridLayout()
        grid.setSpacing(6)
        for i, a in enumerate(ACTIONS):
            btn = QPushButton(a.name)
            btn.clicked.connect(lambda checked=False, k=a.key: self._on_action(k))
            grid.addWidget(btn, i // 4, i % 4)
        root.addLayout(grid)

        row2 = QHBoxLayout()
        btn_random = QPushButton("🎲 随机动作")
        btn_random.clicked.connect(self._on_random)
        btn_say = QPushButton("💬 让它说话")
        btn_say.clicked.connect(self._on_say)
        row2.addWidget(btn_random)
        row2.addWidget(btn_say)
        root.addLayout(row2)

        row3 = QHBoxLayout()
        self.btn_add = QPushButton("➕ 再来一只")
        self.btn_add.clicked.connect(self.add_more_pet)
        self.btn_clear = QPushButton("🗑️ 清空宠物")
        self.btn_clear.setObjectName("DangerBtn")
        self.btn_clear.clicked.connect(self.clear_pets)
        row3.addWidget(self.btn_add)
        row3.addWidget(self.btn_clear)
        root.addLayout(row3)

    # ---------- 事件 ----------
    def _apply_config_ui(self):
        cfg = self._config
        model = cfg.get("model", "u2net")
        names = {self.model_combo.itemText(i): ("u2netp" if "u2netp" in self.model_combo.itemText(i) else
                  ("isnet-general-use" if "isnet" in self.model_combo.itemText(i) else "u2net")) for i in range(self.model_combo.count())}
        for i in range(self.model_combo.count()):
            if names[self.model_combo.itemText(i)] == model:
                self.model_combo.setCurrentIndex(i)
                break
        if "size_scale" in cfg:
            self.size_slider.setValue(int(cfg["size_scale"] * 100))
        if "opacity" in cfg:
            self.opacity_slider.setValue(int(cfg["opacity"] * 100))
        if "auto_actions" in cfg:
            self.auto_check.setChecked(cfg["auto_actions"])
        if "talk_lines" not in cfg:
            cfg["talk_lines"] = [
                "你好呀！我是你的桌面伙伴~",
                "今天也要加油鸭！",
                "写累了可以看看我哦~",
                "猜猜我现在在想什么？",
                "我超会卖萌的！",
                "要给我投喂好吃的吗？",
                "嘿嘿，抓住你啦！",
                "今天天气不错，适合发呆~",
                "看到你我就开心！",
            ]
            self._save_config()

    def pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp *.gif)")
        if path:
            self.start_cut(path)

    def start_cut(self, path):
        model = "u2net"
        txt = self.model_combo.currentText()
        if "u2netp" in txt:
            model = "u2netp"
        elif "isnet" in txt:
            model = "isnet-general-use"
        self.btn_pick.setEnabled(False)
        self.status.setText("正在抠图…首次运行需要下载模型，请稍候")
        self._worker = CutWorker(path, model)
        self._worker.status.connect(self.status.setText)
        self._worker.done.connect(self._on_cut_done)
        self._worker.failed.connect(self._on_cut_failed)
        self._worker.start()

    def _on_cut_done(self, pil_img, path):
        self.btn_pick.setEnabled(True)
        self._pending_result = pil_img
        self._pending_path = path
        qimg = pil_to_qimage(pil_img)
        pw = 440
        ph = 118
        pm = QPixmap.fromImage(qimg).scaled(pw, ph, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._set_preview(pm)
        self.status.setText("抠图完成！小宠物已经放到桌面上了~")
        self._create_new_pet(qimg, os.path.basename(path))

    def _on_cut_failed(self, msg):
        self.btn_pick.setEnabled(True)
        self.status.setText("抠图失败：" + msg)

    def _set_preview(self, pm):
        checker = QPixmap(14, 14)
        p = QPainter(checker)
        p.fillRect(checker.rect(), QColor("#ffffff"))
        p.fillRect(0, 0, 7, 7, QColor("#f2e3ea"))
        p.fillRect(7, 7, 7, 7, QColor("#f2e3ea"))
        p.end()
        canvas = QPixmap(440, 118)
        b = QBrush(checker)
        pa = QPainter(canvas)
        pa.fillRect(canvas.rect(), b)
        x = (440 - pm.width()) // 2
        y = (118 - pm.height()) // 2
        pa.drawPixmap(x, y, pm)
        pa.end()
        self.preview.setPixmap(canvas)

    def _create_new_pet(self, qimg, name):
        pet = PetWindow(qimg, self._config, name=name,
                        recut_cb=lambda: self.start_cut(self._pending_path),
                        toggle_panel_cb=self.show_panel)
        pet.set_auto(self.auto_check.isChecked())
        pet.set_size_scale(self.size_slider.value() / 100.0)
        pet.setWindowOpacity(self.opacity_slider.value() / 100.0)
        pet.destroyed.connect(lambda: self._remove_pet(pet))
        self.pets.append(pet)
        pet.show()
        return pet

    def add_more_pet(self):
        if self._pending_result is None:
            self.status.setText("请先选择一张图片并完成抠图")
            return
        qimg = pil_to_qimage(self._pending_result)
        self._create_new_pet(qimg, os.path.basename(self._pending_path))

    def clear_pets(self):
        for pet in list(self.pets):
            pet.close()

    def _remove_pet(self, pet):
        if pet in self.pets:
            self.pets.remove(pet)

    def on_reminder(self, r):
        """到点提醒：让第一只存活宠物走到屏幕中央并播报。"""
        pet = next((p for p in self.pets if not p.isHidden() and p.isVisible()), None)
        if pet is None and self.pets:
            pet = self.pets[0]
        if pet is not None:
            pet.start_reminder(r)

    def _on_action(self, key):
        if not self.pets:
            self.status.setText("桌面上还没有宠物，先添加一只吧")
            return
        for pet in self.pets:
            pet.set_action(key)

    def _on_random(self):
        for pet in self.pets:
            pet.random_action()

    def _on_say(self):
        cfg = self._config
        lines = cfg.get("talk_lines", ["嗨~"])
        for pet in self.pets:
            pet.say(random.sample(lines, min(2, len(lines))))

    def _on_size(self, v):
        self.size_label.setText("%d%%" % v)
        for pet in self.pets:
            pet.set_size_scale(v / 100.0)

    def _on_opacity(self, v):
        self.opacity_label.setText("%d%%" % v)
        for pet in self.pets:
            pet.setWindowOpacity(v / 100.0)

    def _on_auto(self, checked):
        for pet in self.pets:
            pet.set_auto(checked)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                self.start_cut(path)
                return

    def closeEvent(self, e):
        self._save_config()
        for pet in list(self.pets):
            pet.close()
        super().closeEvent(e)
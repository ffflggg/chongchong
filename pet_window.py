# -*- coding: utf-8 -*-
"""桌宠窗口：透明置顶、可拖动、躯干动画渲染、对话框气泡、右键菜单。"""
import hashlib
import os
import random
import time

import numpy as np
from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import (QColor, QCursor, QFont, QImage, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QPolygonF)
from PyQt5.QtWidgets import QApplication, QMenu, QWidget

from animations import ACTIONS, ACTIONS_BY_KEY, Frame
from cutout import compute_parts_from_alpha

BUBBLE_FONT = "Microsoft YaHei"
EMOJI_FONT = "Segoe UI Emoji"
BUBBLE_TOP_MARGIN = 60
SIDE_MARGIN = 18
MAX_BASE = 480
_FONT_CACHE = {}
MAX_PARTICLES = 40


def _get_font(family, size):
    key = (family, size)
    f = _FONT_CACHE.get(key)
    if f is None:
        f = QFont(family, size)
        _FONT_CACHE[key] = f
    return f


# ---- ins 风波点菜单 ----
RED_DOT_QSS = """
QMenu {
  background-color: #fff4ec;
  border: none;
}
QMenu::item {
  color: #8a2038; font-weight: bold; font-size: 12px;
  background-color: rgba(255, 251, 252, 90);
  border-radius: 12px;
  padding: 7px 24px; margin: 2px 7px;
}
QMenu::item:selected:enabled {
  color: white;
  background-color: #ff4b6e;
}
QMenu::item:disabled { color: #c98ba0; background-color: transparent; }
QMenu::separator {
  height: 1px; background-color: rgba(255, 75, 110, 60);
  margin: 5px 14px;
}
QMenu::icon { padding-left: 8px; }
"""


class DotMenu(QMenu):
    """红色波点 ins 风格菜单：米白底 + 红点阵列 + 红底高亮。"""

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        # 红点阵列（点在窗口左右空隙与 item 边缘，不压文字）
        step = 26
        off = 13
        p.setPen(Qt.NoPen)
        for yy in range(off, r.height(), step):
            for xx in range(off, r.width(), step):
                rr = 3.0 + ((xx + yy) % 7) * 0.25
                p.setBrush(QColor(255, 75, 110, 130 if (xx + yy) % 2 else 105))
                p.drawEllipse(QPointF(xx, yy), rr, rr)
        # 圆角边框
        path = QPainterPath()
        path.addRoundedRect(QRectF(r), 14, 14)
        pen = QPen(QColor(255, 75, 110, 170), 1.6)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()


class PetWindow(QWidget):
    def __init__(self, qimage, config, name="桌宠", recut_cb=None, toggle_panel_cb=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(name)

        self._recut_cb = recut_cb
        self._toggle_panel_cb = toggle_panel_cb
        self._pix = QPixmap.fromImage(qimage)
        self._qimage = qimage
        self._size_scale = float(config.get("size_scale", 1.0))
        self._auto_actions = bool(config.get("auto_actions", True))
        self._auto_interval = int(config.get("auto_interval", 9))
        self._random_lines = list(config.get("talk_lines", []))
        self._name = name
        self._neck_r, self._waist_r = self._analyze_parts(qimage)

        k = 1.0
        if max(self._pix.width(), self._pix.height()) > MAX_BASE:
            k = MAX_BASE / float(max(self._pix.width(), self._pix.height()))
        self._base_w = max(1, int(self._pix.width() * k))
        self._base_h = max(1, int(self._pix.height() * k))

        self._pet_w = int(self._base_w * self._size_scale)
        self._pet_h = int(self._base_h * self._size_scale)
        self._win_w = max(self._pet_w + SIDE_MARGIN * 2, 110)
        self._win_h = self._pet_h + BUBBLE_TOP_MARGIN + SIDE_MARGIN

        self._frame = Frame()
        self._action = ACTIONS_BY_KEY["idle"]
        self._t = 0.0
        self._last = time.time()
        self._facing_right = True
        self._drag_pos = None
        self._active_particles = []
        self._dialog_lines = []
        self._line_idx = 0
        self._typed = 0.0
        self._line_wait = None
        self._auto_counter = 0
        self._pending_say = []
        self._shadow = None

        self.setWindowOpacity(float(config.get("opacity", 1.0)))
        self.setFixedSize(self._win_w, self._win_h)
        self._make_shadow()
        self._smooth_head = 0.0
        self._smooth_upper = 0.0
        self._smooth_lower = 0.0
        self._smooth_lean = 0.0
        self._build_bands()

        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - self._win_w - random.randint(50, 200)
        y = screen.bottom() - self._win_h - random.randint(0, 60)
        x = max(screen.left(), min(x, screen.right() - self._win_w))
        y = max(screen.top(), min(y, screen.bottom() - self._win_h))
        self.move(x, y)
        self._screen = screen

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._auto_check)
        self._auto_timer.start(1000)

        self._longpress = QTimer(self)
        self._longpress.setSingleShot(True)
        self._longpress.timeout.connect(self._longpress_triggered)
        self._press_pos = None

        # ---- 待办提醒状态 ----
        self._reminder = None   # 正在播报的待办 dict
        self._reminder_done = False

    def _analyze_parts(self, qimage):
        try:
            ptr = qimage.constBits()
            ptr.setsize(qimage.sizeInBytes())
            arr = np.frombuffer(ptr, np.uint8).reshape(
                qimage.height(), qimage.width(), 4)
            neck_r, waist_r, quality = compute_parts_from_alpha(arr[..., 3])
            self._split_quality = quality
            return neck_r, waist_r
        except Exception:
            self._split_quality = 0
            return 0.28, 0.52

    def _make_shadow(self):
        sw = max(24, self._pet_w)
        sh = max(6, int(sw * 0.16))
        pm = QPixmap(sw, sh)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, 0, sh)
        grad.setColorAt(0.0, QColor(0, 0, 0, 90))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QRectF(1, 1, sw - 2, sh - 2))
        p.end()
        self._shadow = pm

    def _build_bands(self):
        """按波浪曲线 + 羽化边缘预切头/上身/下身三段 pixmap。

        结果 self._bands = [(pixmap, src_y0, src_y1, pivot_row), ...]
        分别对应 头/上身/下身；src_y0/src_y1 为源图行范围，
        pivot_row 为旋转轴（源图行），绘制时换算到窗口坐标。
        分界采用波浪曲线而非横线，边界行做 1..fade 渐变羽化，
        旋转时上下段相接处自然融合、不露硬切口。
        """
        self._bands = None
        try:
            q = self._qimage
            hh, ww = q.height(), q.width()
            if hh < 8 or ww < 8:
                return
            img = q.convertToFormat(QImage.Format_RGBA8888)
            ptr = img.constBits()
            ptr.setsize(img.sizeInBytes())
            arr = np.frombuffer(ptr, np.uint8).reshape(hh, ww, 4)
            # 超大图避免 numpy 三份整图内存，回退整幅直画
            if ww * hh > 4096 * 4096:
                return
        except Exception:
            return
        neck_r, waist_r = self._neck_r, self._waist_r
        quality = int(getattr(self, "_split_quality", 0))
        if quality == 0 or waist_r - neck_r < 0.08:
            # 无可靠分割：保留整幅直画，动作只做整体摆动，最自然
            return

        amp = int(max(3.0, hh * 0.008))
        fade = int(max(4.0, hh * 0.012))
        x = np.arange(ww, dtype=np.float64)

        def curve(base, phase):
            return base + amp * np.sin(2 * np.pi * 4 * x / ww + phase)

        c1 = curve(int(neck_r * hh), 1.3)   # 颈部分界（波浪线）
        c2 = curve(int(waist_r * hh), 4.4)  # 腰部分界（波浪线，相位错开）

        def cut_band(y0, y1, top_fade, bot_fade):
            """从源图截取 [y0, y1]（行曲线）, 上下边缘各羽化 top/bot_fade 行。"""
            r0 = max(0, int(np.floor(np.min(y0))))
            r1 = min(hh, int(np.ceil(np.max(y1))))
            hb = r1 - r0
            if hb <= 0:
                return None
            out = np.zeros((hb, ww, 4), np.uint8)
            for c in range(ww):
                t = max(r0, int(np.ceil(y0[c])))
                b = min(r1, int(np.floor(y1[c])))
                if b <= t:
                    continue
                seg = arr[t:b, c].copy()
                seg = seg.astype(np.float64)
                if top_fade:
                    fw = min(top_fade, b - t)
                    seg[:fw, 3] *= (np.arange(fw, dtype=np.float64) + 1) / (fw + 1)
                if bot_fade:
                    fw = min(bot_fade, b - t)
                    seg[-fw:, 3] *= (np.arange(fw, dtype=np.float64) + 1)[::-1] / (fw + 1)
                out[t - r0:b - r0, c] = seg.astype(np.uint8)
            qi = QImage(out.data, ww, hb, ww * 4, QImage.Format_RGBA8888)
            pm = QPixmap.fromImage(qi.copy())
            return (pm, r0, r1)

        # 两端均留 fade 重叠缓冲；淡出只做在下缘，下缘淡出处露出下一段的不透明区，
        # 保证接缝处永不透底、旋转时也不露硬直线切口
        head = cut_band(np.zeros(ww), c1 + fade, 0, fade)
        if quality == 1:
            # 仅识别出头部：头/身体两段
            body = cut_band(c1 - fade, np.full(ww, hh), 0, 0)
            if not head or not body:
                return
            self._bands = [head, body]
            self._band_ww = ww
            return
        mid = cut_band(c1 - fade, c2 + fade, 0, fade)
        leg = cut_band(c2 - fade, np.full(ww, hh), 0, 0)
        if not head or not mid or not leg:
            return
        self._bands = [head, mid, leg]
        self._band_ww = ww

    # ---------- 对外接口 ----------
    def set_action(self, key):
        a = ACTIONS_BY_KEY.get(key)
        if a is None:
            return
        self._action = a
        self._t = 0.0
        self._active_particles = []
        self._dialog_lines = []
        if a.lines:
            self._dialog_lines = list(a.lines)
            self._line_idx = 0
            self._typed = 0.0

    def say(self, lines):
        self._dialog_lines = list(lines)
        self._line_idx = 0
        self._typed = 0.0

    def random_action(self):
        keys = [a.key for a in ACTIONS if a.key != "idle"]
        self.set_action(random.choice(keys))

    def set_auto(self, enabled):
        self._auto_actions = enabled
        self._auto_counter = 0

    def set_size_scale(self, scale):
        self._size_scale = scale
        self._pet_w = max(12, int(self._base_w * scale))
        self._pet_h = max(12, int(self._base_h * scale))
        self._win_w = max(self._pet_w + SIDE_MARGIN * 2, 110)
        self._win_h = self._pet_h + BUBBLE_TOP_MARGIN + SIDE_MARGIN
        self.setFixedSize(self._win_w, self._win_h)
        self._make_shadow()

    # ---------- 内部逻辑 ----------
    def _auto_check(self):
        if not self._auto_actions:
            return
        self._auto_counter += 1
        if self._auto_counter >= self._auto_interval:
            self._auto_counter = 0
            if random.random() < 0.55:
                self.random_action()
            elif self._random_lines:
                self.say(random.sample(self._random_lines, min(2, len(self._random_lines))))

    def _tick(self):
        now = time.time()
        dt = min(now - self._last, 0.1)
        self._last = now

        # 待办提醒优先移动（宠物走到屏幕中央播报）
        self._tick_reminder(dt)

        finished = False
        if self._action.loop and self._action.duration > 0:
            self._t = (self._t + dt) % self._action.duration
        else:
            self._t += dt
            if self._action.duration > 0 and self._t >= self._action.duration:
                finished = True

        if finished:
            self._action = ACTIONS_BY_KEY["idle"]
            self._t = 0.0
            self._active_particles = []
            self._pending_say.clear()

        a = self._action
        self._frame = a.fn(self._t)
        f = self._frame

        # 旋转平滑：指数阻尼，动画不跳变
        k = 1.0 - np.exp(-dt * 10.0)
        self._smooth_head += (f.head_rot - self._smooth_head) * k
        self._smooth_upper += (f.upper_rot - self._smooth_upper) * k
        self._smooth_lower += (f.lower_rot - self._smooth_lower) * k
        self._smooth_lean += (getattr(f, "lean", 0.0) - self._smooth_lean) * k

        if a.can_move and self._frame.move_x:
            self._move_by(self._frame.move_x * dt)

        for p in a.particles:
            if self._t >= p.t and self._t - p.t < p.life:
                if not any(q is p for q, s0 in self._active_particles):
                    self._active_particles.append((p, self._t))
        self._active_particles = [(p, s0) for (p, s0) in self._active_particles
                                  if self._t - s0 < p.life]
        if len(self._active_particles) > MAX_PARTICLES:
            self._active_particles = self._active_particles[-MAX_PARTICLES:]

        if self._dialog_lines:
            line = self._dialog_lines[self._line_idx]
            if self._typed < len(line):
                self._typed += dt * 24.0
                if self._typed >= len(line):
                    self._typed = len(line)
            else:
                wait = 1.1
                if self._line_wait is None:
                    self._line_wait = 0.0
                self._line_wait += dt
                if self._line_wait >= wait and self._line_idx < len(self._dialog_lines) - 1:
                    self._line_idx += 1
                    self._typed = 0.0
                    self._line_wait = None
                elif self._line_wait >= wait:
                    self._dialog_lines = []
                    self._line_idx = 0
                    self._typed = 0.0
                    self._line_wait = None
        self.update()

    def _move_by(self, dx):
        x = self.x() + dx
        w = self.width()
        if x < self._screen.left():
            x = self._screen.left()
            self._facing_right = True
        elif x + w > self._screen.right():
            x = self._screen.right() - w
            self._facing_right = False
        self.move(int(x), self.y())

    # ---------- 待办提醒 ----------
    def start_reminder(self, r):
        """到点提醒：宠物从当前位置平滑移到屏幕中央，播报待办内容（气泡+语音）。"""
        if self._reminder is not None:
            return
        self._reminder = r
        self._reminder_done = False
        s = QApplication.primaryScreen().availableGeometry()
        tx = s.center().x() - self._win_w // 2
        ty = s.center().y() - self._win_h // 2
        ty = max(s.top(), min(ty, s.bottom() - self._win_h))
        dist = max(abs(ty - self.y()), abs(tx - self.x()))
        # 3 秒内到达，速度不超过 220px/s
        dur = min(3.0, max(0.8, dist / 220.0))
        self._remind_x = tx
        self._remind_y = ty
        self._remind_t = 0.0
        self._remind_dur = dur
        self._remind_done = False

    def _tick_reminder(self, dt):
        if self._reminder is None:
            return
        if not self._reminder_done:
            self._remind_t += dt
            k = min(1.0, self._remind_t / self._remind_dur)
            ease = 1.0 - (1.0 - k) ** 3
            x = self.x() + (self._remind_x - self.x()) * ease
            y = self.y() + (self._remind_y - self.y()) * ease
            self.move(int(x), int(max(self._screen.top(), min(y, self._screen.bottom() - self._win_h))))
            if k >= 1.0:
                self._reminder_done = True
                text = self._reminder.get("text", "该做事啦")
                self.say(["⏰ " + text])
                self._play_remind_voice(text)
                # 播报后 8 秒内保持静止，再淡出提醒状态
                QTimer.singleShot(8000, self._end_reminder)

    def _end_reminder(self):
        self._reminder = None
        self._reminder_done = False

    def _play_remind_voice(self, text):
        """按用户设置播放提醒声音：系统TTS / 我的录音 / AI变声。"""
        try:
            import reminder as rm
            v = rm.load_voice_cfg()
            cache_dir = rm.CACHE_DIR or os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
            os.makedirs(cache_dir, exist_ok=True)
            h = hashlib.md5(text.encode("utf-8")).hexdigest()[:10]
            cache = os.path.join(cache_dir, "voice_%s.wav" % h)
            voice = v.get("voice", "system")
            if voice == "record" and v.get("record_path") and os.path.exists(v["record_path"]):
                rm.play_wav(v["record_path"])
            elif voice == "ai":
                src = v.get("record_path")
                if src and os.path.exists(src):
                    rm.ai_transform(src, v.get("ai_style", "萝莉音"), cache)
                    rm.play_wav(cache)
                else:
                    rm.tts_to_wav(text, cache, rate=2)
                    rm.play_wav(cache)
            else:
                rm.tts_to_wav("主人，" + text, cache, rate=1)
                rm.play_wav(cache)
        except Exception:
            pass

    # ---------- 鼠标交互 ----------
    def move_to_center(self):
        s = QApplication.primaryScreen().availableGeometry()
        x = s.center().x() - self._win_w // 2
        y = s.center().y() - self._win_h // 2
        y = min(y, s.bottom() - self._win_h)
        self.move(max(s.left(), x), max(s.top(), y))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
            self._press_pos = e.globalPos()
            self._longpress.setInterval(600)
            self._longpress.start()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None:
            # 移动超过阈值视为拖拽，取消长按
            if self._longpress.isActive():
                if (e.globalPos() - self._press_pos).manhattanLength() > 8:
                    self._longpress.stop()
            if e.buttons() & Qt.LeftButton:
                self.move(e.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        if self._longpress.isActive():
            self._longpress.stop()
        self._drag_pos = None

    def _longpress_triggered(self):
        """长按（触屏/手机手势）弹出功能菜单。"""
        if self._longpress.isActive():
            self._longpress.stop()
        self._drag_pos = None  # 防止松手时误判为拖拽位移
        self._show_menu(QCursor.pos())

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            now = time.time()
            if getattr(self, "_last_random", 0.0) + 0.6 < now:
                self._last_random = now
                self.random_action()

    def contextMenuEvent(self, e):
        self._show_menu(e.globalPos())

    def _add_reminder_menu(self, menu):
        """在菜单上添加「⏰ 待办提醒」与「🔊 提醒语音」子菜单。"""
        import reminder as rm

        sub = menu.addMenu("⏰ 待办提醒")
        sub.setStyleSheet(RED_DOT_QSS)

        a = sub.addAction("➕ 新建待办…")
        a.triggered.connect(lambda: self._dialog_new_reminder())
        sub.addSeparator()

        rms = rm.Reminders.load()
        if rms:
            today = time.strftime("%Y-%m-%d")
            for r in rms:
                mark = "✔" if r.get("enabled", True) else "✖"
                adv = int(r.get("advance", 0))
                adv_txt = ("（提前%d分）" % adv) if adv else ""
                fired = "✅" if r.get("fired_date") == today else ""
                label = "%s %s · %s%s %s" % (mark, r.get("time"), r.get("text"), adv_txt, fired)
                act = sub.addAction(label)
                act.setCheckable(True)
                act.setChecked(bool(r.get("enabled", True)))
                act.triggered.connect(lambda checked=False, rid=r.get("id"): self._toggle_reminder(rid))
            sub.addSeparator()
            a = sub.addAction("🗑 删除全部待办")
            a.triggered.connect(self._del_all_reminders)
        else:
            a = sub.addAction("（还没有待办，点上面新建）")
            a.setEnabled(False)

        # 语音设置
        vmenu = menu.addMenu("🔊 提醒语音 (%s)" % rm.voice_summary())
        vmenu.setStyleSheet(RED_DOT_QSS)
        v = rm.load_voice_cfg()["voice"]
        for label, key in (("🗣 系统女声", "system"),
                           ("🎤 我的录音", "record"),
                           ("🤖 AI 变声", "ai")):
            act = vmenu.addAction(label)
            act.setCheckable(True)
            act.setChecked(v == key)
            act.triggered.connect(lambda checked=False, k=key: self._set_remind_voice(k))
        if v == "ai":
            smenu = vmenu.addMenu("变声风格")
            smenu.setStyleSheet(RED_DOT_QSS)
            cur = rm.load_voice_cfg().get("ai_style", "萝莉音")
            for st in rm.AI_STYLES:
                act = smenu.addAction(st)
                act.setCheckable(True)
                act.setChecked(cur == st)
                act.triggered.connect(lambda checked=False, s=st: self._set_ai_style(s))
        vmenu.addSeparator()
        a = vmenu.addAction("🎙 录我自己的声音（3秒）")
        a.triggered.connect(self._record_my_voice)
        a = vmenu.addAction("▶ 试听一下")
        a.triggered.connect(self._preview_voice)

    def _dialog_new_reminder(self):
        """新建待办：内容 + 时间 + 提前量。"""
        import reminder as rm
        from PyQt5.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "新建待办", "待办内容（如：记得喝水）")
        if not ok or not text.strip():
            return
        cur = rm.add_minutes(rm.now_hhmm(), 10)
        time_str, ok = QInputDialog.getText(
            self, "新建待办", "提醒时间（HH:MM，24小时制）", text=cur)
        if not ok:
            return
        tstr = time_str.strip()
        try:
            hh, mm = map(int, tstr.split(":"))
            if not (0 <= hh < 24 and 0 <= mm < 60):
                raise ValueError
            tstr = "%02d:%02d" % (hh, mm)
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "格式不对", "请输入正确的时间，例如 14:30")
            return
        adv, ok = QInputDialog.getItem(
            self, "新建待办", "提前几分钟提醒？",
            [str(x) for x in rm.ADVANCE_CHOICES], 1, False)
        if not ok:
            return
        rms = rm.Reminders.load()
        rid = "r%d" % (int(time.time()) % 100000)
        rms.append({"id": rid, "text": text.strip(), "time": tstr,
                    "advance": int(adv), "enabled": True})
        rm.Reminders.save(rms)
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(self, "已设置", "好哦~ 到点我就叫你！\n%s 待办：%s" % (tstr, text.strip()))

    def _toggle_reminder(self, rid):
        import reminder as rm
        rms = rm.Reminders.load()
        for r in rms:
            if r.get("id") == rid:
                r["enabled"] = not r.get("enabled", True)
                r.pop("fired_date", None)
        rm.Reminders.save(rms)

    def _del_all_reminders(self):
        import reminder as rm
        rm.Reminders.save([])

    def _set_remind_voice(self, mode):
        import reminder as rm
        rm.save_voice_cfg(voice=mode)

    def _set_ai_style(self, style):
        import reminder as rm
        rm.save_voice_cfg(ai_style=style)

    def _record_my_voice(self):
        """录 3 秒声音并保存为提醒音。"""
        import reminder as rm
        from PyQt5.QtWidgets import QMessageBox
        ok = QMessageBox.question(
            self, "录制提醒声", "点击「是」后开始录音 3 秒，请对着麦克风说："
            '"该起床啦！"\n是否开始？',
            QMessageBox.Yes | QMessageBox.No)
        if ok != QMessageBox.Yes:
            return
        cache = rm.CACHE_DIR
        os.makedirs(cache, exist_ok=True)
        path = os.path.join(cache, "my_voice.wav")
        QMessageBox.information(self, "录音中", "正在录音 3 秒…（结束后自动保存）",
                                QMessageBox.Ok)
        if rm.record_wav(path, 3.0):
            rm.save_voice_cfg(voice="record", record=path)
            QMessageBox.information(self, "完成", "录音已保存！已切换为「我的录音」提醒。")
        else:
            QMessageBox.warning(self, "失败", "录音失败：请检查麦克风是否可用。")

    def _preview_voice(self):
        self._play_remind_voice("这是提醒声音的预览")

    def _show_menu(self, pos):
        menu = DotMenu(self)
        menu.setStyleSheet(RED_DOT_QSS)
        act_menu = menu.addMenu("🎬 动作")
        act_menu.setStyleSheet(RED_DOT_QSS)
        for a in ACTIONS:
            act = act_menu.addAction(a.name)
            act.triggered.connect(lambda checked=False, k=a.key: self.set_action(k))
        menu.addSeparator()

        move_menu = menu.addMenu("🚶 移动模式")
        move_menu.setStyleSheet(RED_DOT_QSS)
        for label, key in (("散步（持续走动）", "walk"), ("奔跑（快速移动）", "run"), ("停止移动", "idle")):
            act = move_menu.addAction(label)
            act.triggered.connect(lambda checked=False, k=key: self.set_action(k))
        menu.addSeparator()

        say_menu = menu.addMenu("💬 让它说话")
        say_menu.setStyleSheet(RED_DOT_QSS)
        groups = [
            ("闲聊", list(self._random_lines) or ["嗨~"]),
            ("打招呼", list(ACTIONS_BY_KEY["hello"].lines)),
            ("吃东西", list(ACTIONS_BY_KEY["eat"].lines)),
            ("自夸", ["我最可爱！", "今天也是元气满满！", "能遇到你真好~"]),
        ]
        for label, lines in groups:
            act = say_menu.addAction(label)
            act.triggered.connect(lambda checked=False, ls=lines: self.say(random.sample(ls, min(2, len(ls)))))
        menu.addSeparator()

        self._add_reminder_menu(menu)
        menu.addSeparator()

        act = menu.addAction("自动随机动作：%s" % ("开" if self._auto_actions else "关"))
        act.triggered.connect(lambda: self.set_auto(not self._auto_actions))
        act = menu.addAction("🎯 移到屏幕中间")
        act.triggered.connect(self.move_to_center)
        if self._toggle_panel_cb is not None:
            act = menu.addAction("🖥️ 打开控制面板")
            act.triggered.connect(self._toggle_panel_cb)
        act = menu.addAction("换一张图片…")
        act.triggered.connect(self._recut_cb if self._recut_cb else (lambda: None))
        act = menu.addAction("关闭这个宠物")
        act.triggered.connect(self.close)
        act = menu.addAction("退出整个插件")
        act.triggered.connect(QApplication.instance().quit)
        menu.exec_(pos)

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        cx = self._win_w / 2.0
        cy = self._win_h - SIDE_MARGIN - self._pet_h / 2.0
        f = self._frame
        lean = getattr(f, "lean", 0.0)
        rot = f.rot + (lean if self._facing_right else -lean)

        # 主体与阴影先在离屏 QImage 上合成：
        # 透明置顶窗口上带源矩形的 drawPixmap 会被静默丢弃（Qt/Windows 限制），
        # 先渲染到内存 QImage，再整幅一次贴上窗口。
        canvas = QImage(self._win_w, self._win_h, QImage.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.transparent)
        c = QPainter(canvas)
        c.setRenderHint(QPainter.Antialiasing)
        c.setRenderHint(QPainter.SmoothPixmapTransform)

        if self._shadow is not None:
            c.setOpacity(0.5 * f.alpha)
            c.drawPixmap(int(cx - self._shadow.width() / 2.0) + int(f.x),
                         int(cy + self._pet_h / 2.0 - 3),
                         self._shadow)
            c.setOpacity(1.0)

        c.setOpacity(f.alpha)
        c.save()
        c.translate(cx + f.x, cy + f.y)
        c.scale(f.sx * f.scale, f.sy * f.scale)
        c.rotate(rot)
        if not self._facing_right:
            c.scale(-1, 1)
        c.translate(-cx, -cy)
        self._draw_body(c, f)
        c.restore()
        c.setOpacity(1.0)
        c.end()

        p.drawPixmap(0, 0, QPixmap.fromImage(canvas))

        pet_top = cy - self._pet_h / 2.0
        self._draw_bubble(p, cx + f.x, pet_top + f.y)
        self._draw_particles(p, cx, cy, f.alpha)

    def _draw_body(self, p, f):
        """绘制躯体：整幅直画（无分割）或头/身分段（波浪羽化边界 + 平滑旋转）。"""
        w, h = self._pet_w, self._pet_h
        top = self._win_h - SIDE_MARGIN - h
        left = (self._win_w - w) / 2.0
        bands = self._bands
        if not bands:
            # 整幅直画（无可靠分割时最自然）：整体旋转已由 paintEvent 完成
            p.drawPixmap(int(left), int(top), w, h, self._pix)
            return
        hh = self._qimage.height()
        sx = w / float(self._band_ww)
        sy = h / float(hh)

        def draw(band, ang, pivot_y):
            pm, r0, r1 = band
            y0 = top + r0 * sy
            th = (r1 - r0) * sy
            if abs(ang) < 0.05:
                p.drawPixmap(int(left), int(y0), w, int(th), pm)
                return
            p.save()
            p.translate(left + w / 2.0, pivot_y)
            p.rotate(-ang)
            p.translate(-(left + w / 2.0), -pivot_y)
            p.drawPixmap(int(left), int(y0), w, int(th), pm)
            p.restore()

        neck_y = top + self._neck_r * h
        if len(bands) == 2:
            # 仅头部分割
            draw(bands[1], 0.0, neck_y)                  # 身体整块不单独旋转
            draw(bands[0], self._smooth_head, neck_y)    # 头以颈为轴
            return
        waist_y = top + self._waist_r * h
        draw(bands[2], self._smooth_lower, waist_y)  # 腿：以腰为轴
        draw(bands[1], self._smooth_upper, waist_y)  # 上身：以腰为轴
        draw(bands[0], self._smooth_head, neck_y)    # 头：以颈为轴

    def _draw_bubble(self, p, cx, pet_top):
        if not self._dialog_lines or self._frame.alpha < 0.3:
            return
        idx = min(self._line_idx, len(self._dialog_lines) - 1)
        text = self._dialog_lines[idx][:int(self._typed)]
        p.setFont(_get_font(BUBBLE_FONT, 12))
        fm = p.fontMetrics()
        t_width = fm.horizontalAdvance(text)
        bw = min(max(t_width + 28, 70), self._win_w - 16)
        bh = 38
        bx = cx - bw / 2.0
        by = pet_top - bh - 14
        if bx < 6:
            bx = 6
        if bx + bw > self._win_w - 6:
            bx = self._win_w - bw - 6

        p.setPen(QPen(QColor(60, 60, 60), 1.5))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 12, 12)
        tri = QPolygonF([QPointF(cx, by + bh - 2),
                         QPointF(cx - 7, by + bh + 7),
                         QPointF(cx + 7, by + bh + 7)])
        p.setPen(Qt.NoPen)
        p.drawPolygon(tri)

        p.setPen(QColor(40, 40, 40))
        p.drawText(QRectF(bx, by, bw, bh), Qt.AlignCenter, text)

    def _draw_particles(self, p, cx, cy, body_alpha):
        p.setFont(_get_font(EMOJI_FONT, 12))
        for part, s0 in self._active_particles:
            lt = self._t - s0
            if lt < 0 or lt > part.life:
                continue
            x = cx + part.x + part.dx * lt
            y = cy + part.y + part.dy * lt
            alpha = (1.0 if part.burst else max(0.0, 1.0 - lt / part.life)) * body_alpha
            if alpha <= 0.01:
                continue
            size = part.size
            p.setOpacity(alpha)
            p.setFont(_get_font(EMOJI_FONT, int(size)))
            p.drawText(QRectF(x - size, y - size, size * 2, size * 2), Qt.AlignCenter, part.emoji)
        p.setOpacity(1.0)

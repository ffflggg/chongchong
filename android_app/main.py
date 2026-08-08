# -*- coding: utf-8 -*-
"""桌宠爱心版（Android / Kivy）

爱心入口 → 操作面板（选图抠图/大小/语音/待办） → 桌宠上屏。
桌宠：呼吸/点头/挥手/走路/气泡；待办到点走到屏幕中心 + 中文播报。
全功能零外网依赖：抠图 numpy、录音 AudioRecord、变声 numpy、播放 Kivy。
"""
import json
import os
import random
import struct
import time
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.image import Image as KImage
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import (Color, Ellipse, Line, PopMatrix, PushMatrix,
                           Rectangle, Rotate, Scale)
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.utils import get_color_from_hex

ANDROID = True
try:
    from jnius import autoclass
    _ACTIVITY = autoclass("org.kivy.android.PythonActivity").mActivity
    _TTS = None
    _TTS_OK = [False]
except Exception:
    _ACTIVITY = None

try:
    import plyer
    HAS_PLYER = True
except Exception:
    HAS_PLYER = False

DATA_DIR = "/sdcard/桌宠" if ANDROID else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data")
CFG_PATH = os.path.join(DATA_DIR, "config.json")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    pass

# ---------------- 配置 ----------------
def load_cfg():
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg):
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------- 音频 ----------------
def tts_speak(text):
    """Android TextToSpeech 中文播报。"""
    global _TTS
    try:
        TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
        Locale = autoclass("java.util.Locale")
        if _TTS is None:
            _TTS = TextToSpeech(_ACTIVITY, None)
        _TTS.setLanguage(Locale.CHINESE)
        _TTS.speak(text, TextToSpeech.QUEUE_FLUSH, None)
    except Exception:
        pass


def play_sound(path):
    try:
        s = SoundLoader.load(path)
        if s:
            s.play()
            return True
    except Exception:
        pass
    return False


def record_audio(path, seconds=3.0):
    """AudioRecord 直接录 PCM → 写 wav（Android，无第三方依赖）。"""
    try:
        AudioRecord = autoclass("android.media.AudioRecord")
        AudioFormat = autoclass("android.media.AudioFormat")
        AudioManager = autoclass("android.media.AudioManager")
        SR = 44100
        rec = AudioRecord(
            AudioManager.AUDIO_SOURCE_MIC,
            SR,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            SR * 4)
        if rec.getState() != AudioRecord.STATE_INITIALIZED:
            return False
        rec.startRecording()
        n = int(SR * seconds)
        buf = rec.read([0] * n, 0, n)
        rec.stop()
        rec.release()
        if buf is None or len(buf) < 1000:
            return False
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(bytearray(0))
        # read 返回的是 list[int]（PCM16）
        import array
        pcm = array.array("h", buf).tobytes()
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm)
        return os.path.exists(path) and os.path.getsize(path) > 1024
    except Exception:
        return False


def ai_transform_wav(src, style, dst):
    """numpy AI 变声：萝莉(高)/大叔(低)/机器人(断续颤音)。"""
    try:
        with wave.open(src, "rb") as w:
            sr = w.getframerate()
            ch = w.getnchannels()
            raw = w.readframes(w.getnframes())
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        if ch > 1:
            data = data.reshape(-1, ch).mean(axis=1)
        if style == "萝莉音":
            n = int(len(data) * 1.3)
            out = np.interp(np.linspace(0, len(data) - 1, n),
                            np.arange(len(data)), data)
            sr2 = int(sr * 1.3)
        elif style == "大叔音":
            n = int(len(data) * 0.65)
            out = np.interp(np.linspace(0, len(data) - 1, n),
                            np.arange(len(data)), data)
            sr2 = int(sr * 0.65)
        else:
            hop = sr // 8
            segs = [data[i:i + hop] for i in range(0, max(len(data) - hop, 1), hop * 2)]
            out = np.concatenate(segs) if segs else data
            t = np.arange(len(out)) / sr
            out = out * (0.75 + 0.25 * np.sin(2 * np.pi * 5 * t))
            sr2 = sr
        with wave.open(dst, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr2)
            w.writeframes((np.clip(out, -1, 1) * 32767).astype("<i2").tobytes())
        return True
    except Exception:
        return False


def manual_cutout(img):
    """numpy 背景去除（与桌面版同算法，手机离线）。"""
    try:
        img = img.convert("RGB")
        arr = np.asarray(img).astype(np.float64)
        h, w, _ = arr.shape
        edges = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]], axis=0)
        thresh = int(np.linalg.norm(np.std(edges, axis=0)))
        thresh = max(40, min(90, thresh))
        fill = (255, 0, 255)
        work = img.copy()
        for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
            try:
                ImageDraw.floodfill(work, corner, fill, thresh=thresh)
            except Exception:
                pass
        mask = np.all(np.asarray(work.convert("RGB")) == fill, axis=2)
        alpha = np.where(mask, 0, 255).astype(np.uint8)
        alpha_img = Image.fromarray(alpha, "L").filter(ImageFilter.GaussianBlur(1.2))
        out = img.convert("RGBA")
        out.putalpha(alpha_img)
        return out
    except Exception:
        return img.convert("RGBA")


# ---------------- 待办 ----------------
ADVANCE_CHOICES = [0, 5, 10, 15, 30, 60]


def add_minutes(hhmm, minutes):
    try:
        h, m = map(int, hhmm.split(":"))
        t = (h * 60 + m + minutes) % 1440
        return "%02d:%02d" % (t // 60, t % 60)
    except Exception:
        return hhmm


def due_now(cfg):
    now = time.strftime("%H:%M")
    today = time.strftime("%Y-%m-%d")
    out = []
    for r in cfg.get("reminders", []):
        if not r.get("enabled", True):
            continue
        if r.get("fired_date") == today:
            continue
        if now >= add_minutes(r.get("time", "09:00"), -int(r.get("advance", 0))):
            out.append(r)
    return out


def mark_fired(cfg, rid):
    today = time.strftime("%Y-%m-%d")
    for r in cfg.get("reminders", []):
        if r.get("id") == rid:
            r["fired_date"] = today
    save_cfg(cfg)


# ---------------- 桌宠精灵 ----------------
class PetSprite(FloatLayout):
    """Canvas 桌宠：呼吸/摇头/挥手/走路/提醒移动 + 气泡。"""

    def __init__(self, png_path, size_px=400, **kw):
        super().__init__(**kw)
        self._tex = KImage(png_path).texture
        self._tex.mag_filter = "linear"
        self._sx, self._sy = self._tex.size
        self._phase = random.uniform(0, 6.28)
        self._t = 0.0
        self._walk_dir = 1
        self._walking = False
        self._remind = None
        self._lines = []
        self._typed = 0.0
        self._bubble = None
        self._hp = 0.0
        self._base_size = dp(220) if ANDROID else 220
        Clock.schedule_interval(self._tick, 1.0 / 60.0)
        self.bind(size=self._mk_bubble, pos=self._mk_bubble)

    def _mk_bubble(self, *a):
        if self._lines and self._bubble is None:
            self._bubble = Label(
                text="", size_hint=(None, None), size=(dp(220), dp(60)),
                font_size=dp(15), color=(0.5, 0.1, 0.2, 1),
                background_color=(1, 1, 1, 0.92),
                halign="center", valign="middle")
            self.add_widget(self._bubble)
        if self._bubble:
            self._bubble.pos = (self.x, self.y + self.height + dp(6))

    def say(self, lines):
        self._lines = list(lines)
        self._typed = 0.0

    def start_remind(self, r):
        if self._remind:
            return
        self._remind = r
        self._walking = True
        self._remind_text = r.get("text", "该做事啦")

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._hp = 1.0
            return True
        return super().on_touch_down(touch)

    def _tick(self, dt):
        self._t += dt
        self._phase = time.time() * 2.4
        if self._remind:
            cx = Window.width * 0.5 - self.width / 2
            cy = Window.height * 0.45 - self.height / 2
            dx, dy = cx - self.x, cy - self.y
            if abs(dx) > 3 or abs(dy) > 3:
                sp = min(300.0, (dx * dx + dy * dy) ** 0.5 * 3.0)
                self.x = float(self.x + np.sign(dx) * sp * dt)
                self.y = float(self.y + np.sign(dy) * sp * dt)
                self.y = max(30, min(self.y, Window.height - self.height - 30))
                self.x = max(10, min(self.x, Window.width - self.width - 10))
            else:
                self._remind = None
                self.say(["⏰ " + self._remind_text])
                tts_speak("主人，" + self._remind_text)
        if self._lines:
            line = self._lines[0]
            if self._typed < len(line):
                self._typed += dt * 30
                if self._typed >= len(line):
                    self._typed = len(line)
        self.canvas.clear()
        with self.canvas:
            # 脚下阴影
            Color(0, 0, 0, 0.18)
            Ellipse(pos=(self.x, self.y - dp(6)), size=(self.width, dp(12)))
            # 宠物主体（呼吸缩放 + 摇头 + 挥手旋转）
            breathe = 1.0 + 0.05 * np.sin(self._phase)
            rot = 6.0 * np.sin(self._phase * 0.6)
            Color(1, 1, 1, 1)
            PushMatrix()
            Rotate(angle=rot, origin=(self.x + self.width / 2,
                                      self.y + self.height / 2))
            Scale(x=breathe, y=breathe, origin=(self.x + self.width / 2,
                                                self.y + self.height / 2))
            Rectangle(
                pos=self.pos, size=self.size,
                texture=self._tex)
            PopMatrix()
        if self._hp > 0:
            self._hp -= dt
            self.size = (self._base_size * (1 + self._hp * 0.08),
                         self._base_size * (1 + self._hp * 0.08))
        elif self.size != (self._base_size, self._base_size):
            self.size = (self._base_size, self._base_size)


class HeartEntry(FloatLayout):
    """屏幕上的呼吸红心：点击打开/隐藏操作面板。"""

    def __init__(self, on_click=None, **kw):
        kw.pop("size_hint", None)
        kw.pop("size", None)
        kw.pop("pos_hint", None)
        super().__init__(**kw)
        self.size_hint = (None, None)
        self.size = (dp(90), dp(90))
        self._on_click = on_click
        Clock.schedule_interval(self._beat, 1.0 / 30.0)

    def _beat(self, dt):
        self.canvas.clear()
        with self.canvas:
            sc = 1.0 + 0.10 * (np.sin(time.time() * 4.0) ** 8)
            w, h = self.width, self.height
            r = w * 0.20
            Color(1, 0.30, 0.45, 0.95)
            PushMatrix()
            Scale(origin=(w / 2, h / 2), x=sc, y=sc)
            Ellipse(pos=(w * 0.32 - r, h * 0.34 - r), size=(2 * r, 2 * r))
            Ellipse(pos=(w * 0.68 - r, h * 0.34 - r), size=(2 * r, 2 * r))
            Color(1, 0.30, 0.45, 0.95)
            Line(points=[w * 0.24, h * 0.38, w * 0.5, h * 0.10,
                         w * 0.76, h * 0.38, w * 0.5, h * 0.90,
                         w * 0.24, h * 0.38],
                 width=w * 0.14, cap="round", join="round")
            PopMatrix()

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if self._on_click:
                self._on_click()
            return True
        return super().on_touch_down(touch)


class PetApp(App):
    """爱心 → 面板 → 桌宠。"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.cfg = load_cfg()
        self._panel_on = False
        self._pet = None
        self._pending_img = None   # 最终宠物 PNG
        self._voice_mode = self.cfg.get("voice", "system")
        self._ai_style = self.cfg.get("ai_style", "萝莉音")
        self._record_path = self.cfg.get("record_path", "")

    def build(self):
        Window.clearcolor = (1, 1, 1, 1)
        root = FloatLayout()
        # 桌宠（延迟到 root 就绪后）
        if os.path.exists(os.path.join(DATA_DIR, "pet.png")):
            Clock.schedule_once(lambda dt: self._spawn_pet(), 0.3)
        # 爱心
        self.heart = HeartEntry(size_hint=(None, None), size=(dp(90), dp(90)),
                                pos_hint={"right": 0.95, "y": 0.5},
                                on_click=self._toggle_panel)
        root.add_widget(self.heart)
        # 面板（默认隐藏）
        self.panel = self._build_panel(root)
        root.add_widget(self.panel)
        self.panel.opacity = 0
        self.panel.disabled = True
        return root

    def _spawn_pet(self):
        p = os.path.join(DATA_DIR, "pet.png")
        pet = PetSprite(p)
        with pet.canvas:
            pass
        self.root.add_widget(pet)
        self._pet = pet
        pet.size = (dp(200), dp(200))
        from kivy.core.window import Window
        pet.x = Window.width * 0.5 - pet.width / 2
        pet.y = Window.height * 0.2
        Clock.schedule_once(lambda dt: self._check_reminders(), 2)

    def _build_panel(self, root):
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.scrollview import ScrollView

        p = FloatLayout(size_hint=(None, None), size=(Window.width * 0.9,
                                                       Window.height * 0.85),
                        pos_hint={"center_x": 0.5, "top": 0.93})
        with p.canvas.before:
            Color(1, 0.88, 0.92, 0.99)
            Rectangle(pos=p.pos, size=p.size)
        p.bind(pos=lambda w, v: self._update_panel(w), size=lambda w, v: self._update_panel(w))
        sv = ScrollView(size_hint=(1, 1))
        inner = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8),
                          size_hint_y=None)
        inner.bind(minimum_height=inner.setter("height"))

        t = Label(text="🐾 桌宠小屋", font_size=dp(24), bold=True,
                  color=(0.85, 0.2, 0.4, 1), size_hint_y=None, height=dp(50))
        inner.add_widget(t)

        b = Button(text="📷 从相册选照片 · 自动抠图", size_hint_y=None, height=dp(52),
                   background_color=(1, 0.62, 0.74, 1), bold=True)
        b.bind(on_release=lambda *a: self._pick_image())
        inner.add_widget(b)

        self.status = Label(text="提示：相册图片会做背景去除再放桌面上",
                            size_hint_y=None, height=dp(30),
                            color=(0.6, 0.3, 0.4, 1), font_size=dp(14))
        inner.add_widget(self.status)

        inner.add_widget(Label(text="大小", size_hint_y=None, height=dp(20),
                               color=(0.6, 0.25, 0.4, 1), font_size=dp(13)))
        self.sl = Slider(min=30, max=130, value=self.cfg.get("size", 80),
                         size_hint_y=None, height=dp(30))
        self.sl.bind(value=lambda *a: self._apply_size())
        inner.add_widget(self.sl)

        inner.add_widget(Label(text="提醒语音", size_hint_y=None, height=dp(20),
                               color=(0.6, 0.25, 0.4, 1), font_size=dp(13)))
        self.vmode = ToggleButton(text="系统女声", state="down" if self._voice_mode == "system" else "normal",
                                  size_hint_y=None, height=dp(40), group="voice")
        self.vmode.bind(on_release=lambda *a: self._set_voice("system"))
        self.vrec = ToggleButton(text="我的录音", state="down" if self._voice_mode == "record" else "normal",
                                 size_hint_y=None, height=dp(40), group="voice")
        self.vrec.bind(on_release=lambda *a: self._set_voice("record"))
        self.vai = ToggleButton(text="AI 变声", state="down" if self._voice_mode == "ai" else "normal",
                                size_hint_y=None, height=dp(40), group="voice")
        self.vai.bind(on_release=lambda *a: self._set_voice("ai"))
        inner.add_widget(self.vmode)
        inner.add_widget(self.vrec)
        inner.add_widget(self.vai)

        self.airow = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        for st in ("萝莉音", "大叔音", "机器人"):
            tb = ToggleButton(text=st, group="aistyle",
                              state="down" if st == self._ai_style else "normal",
                              background_color=(1, 0.75, 0.82, 1))
            tb.bind(on_release=lambda *a, s=st: self._set_ai(s))
            self.airow.add_widget(tb)
        inner.add_widget(self.airow)

        bt = Button(text="🎤 录 3 秒提醒声（说：该起床啦）", size_hint_y=None, height=dp(44),
                    background_color=(0.95, 0.55, 0.65, 1))
        bt.bind(on_release=lambda *a: self._record_voice())
        inner.add_widget(bt)
        bt2 = Button(text="▶ 试听提醒声", size_hint_y=None, height=dp(40))
        bt2.bind(on_release=lambda *a: self._preview_voice())
        inner.add_widget(bt2)

        inner.add_widget(Label(text="待办提醒", size_hint_y=None, height=dp(20),
                               color=(0.6, 0.25, 0.4, 1), font_size=dp(13)))
        bb = Button(text="＋ 新建待办", size_hint_y=None, height=dp(42))
        bb.bind(on_release=lambda *a: self._new_todo())
        inner.add_widget(bb)
        self.todo_list = Label(text="", size_hint_y=None, height=dp(60),
                               font_size=dp(13), color=(0.4, 0.15, 0.25, 1))
        inner.add_widget(self.todo_list)
        bd = Button(text="🗑 删除全部待办", size_hint_y=None, height=dp(34))
        bd.bind(on_release=lambda *a: self._del_todos())
        inner.add_widget(bd)

        bc = Button(text="✕ 收起面板（桌宠留在桌面）", size_hint_y=None, height=dp(46),
                     background_color=(1, 0.5, 0.6, 1))
        bc.bind(on_release=lambda *a: self._toggle_panel())
        inner.add_widget(bc)

        sv.add_widget(inner)
        p.add_widget(sv)
        self._panel_inner = inner
        return p

    def _update_panel(self, w):
        w.canvas.before.clear()
        with w.canvas.before:
            Color(1, 0.88, 0.92, 0.98)
            Rectangle(pos=w.pos, size=w.size)

    def _refresh_todos(self):
        rms = self.cfg.get("reminders", [])
        self.todo_list.text = "\n".join(
            "%s %s %s" % (r.get("time"), r.get("text"), "✔" if r.get("enabled") else "✖")
            for r in rms) if rms else "（暂无待办）"

    def _toggle_panel(self):
        self._panel_on = not self._panel_on
        self.panel.opacity = 1 if self._panel_on else 0
        self.panel.disabled = not self._panel_on
        self.panel.pos = (Window.width * 0.05, Window.height * 0.075)
        self.panel.size = (Window.width * 0.9, Window.height * 0.85)
        if self._panel_on:
            self._refresh_todos()

    def _pick_image(self):
        if HAS_PLYER:
            try:
                from plyer import filechooser
                filechooser.open_file(on_selection=self._on_pick, filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"])
                return
            except Exception:
                pass
        self.status.text = "此设备暂不支持系统相册，请用文件管理器放入 /sdcard/桌宠/pet.png"

    def _on_pick(self, selection):
        if not selection:
            return
        threading.Thread(target=self._process_photo, args=(selection[0],), daemon=True).start()

    def _process_photo(self, path):
        try:
            img = Image.open(path)
            out = manual_cutout(img)
            img = out
            # 自动裁剪透明边缘
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
            img.save(os.path.join(DATA_DIR, "pet.png"))
            Clock.schedule_once(lambda dt: self._done_pick(), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: self._fail_pick(str(e)), 0)

    def _done_pick(self):
        self.status.text = "抠图完成，桌宠已上屏！"
        if hasattr(self, "_pet"):
            self.root.remove_widget(self._pet)
        self._spawn_pet()

    def _fail_pick(self, msg):
        self.status.text = "抠图失败：" + msg

    def _apply_size(self):
        self.cfg["size"] = int(self.sl.value)
        save_cfg(self.cfg)
        if self._pet:
            self._pet._base_size = int(dp(self.sl.value) * 2.2)

    def _set_voice(self, mode):
        self._voice_mode = mode
        self.cfg["voice"] = mode
        save_cfg(self.cfg)
        self.vmode.state = "down" if mode == "system" else "normal"
        self.vrec.state = "down" if mode == "record" else "normal"
        self.vai.state = "down" if mode == "ai" else "normal"

    def _set_ai(self, style):
        self._ai_style = style
        self.cfg["ai_style"] = style
        save_cfg(self.cfg)

    def _record_voice(self):
        path = os.path.join(DATA_DIR, "my_voice.wav")
        if not ANDROID or _ACTIVITY is None:
            self.status.text = "录音仅支持安卓（电脑上请用桌面版）"
            return
        self.status.text = "正在录音 3 秒，请说：该起床啦！"
        threading.Thread(target=self._do_record, args=(path,), daemon=True).start()

    def _do_record(self, path):
        ok = record_audio(path, 3.0)
        if ok:
            self._record_path = path
            self.cfg["record_path"] = path
            self.cfg["voice"] = "record"
            save_cfg(self.cfg)
            self._voice_mode = "record"
            Clock.schedule_once(lambda dt: self._after_record(True), 0)
        else:
            Clock.schedule_once(lambda dt: self._after_record(False), 0)

    def _after_record(self, ok):
        if ok:
            self.status.text = "录音已保存！已切换为「我的录音」"
            self.vrec.state = "down"
            self.vmode.state = "normal"
            self.vai.state = "normal"
        else:
            self.status.text = "录音失败：请检查麦克风权限"

    def _preview_voice(self):
        if self._voice_mode == "record" and self._record_path and os.path.exists(self._record_path):
            play_sound(self._record_path)
        elif self._voice_mode == "ai" and self._record_path and os.path.exists(self._record_path):
            out = os.path.join(DATA_DIR, "preview_ai.wav")
            ai_transform_wav(self._record_path, self._ai_style, out)
            play_sound(out)
        else:
            tts_speak("这是提醒声音的预览")

    # ---- 待办 ----
    def _new_todo(self):
        from kivy.uix.boxlayout import BoxLayout
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        box.add_widget(Label(text="待办内容", color=(0.5, 0.2, 0.35, 1)))
        ti = TextInput(hint_text="如：记得喝水", size_hint_y=None, height=dp(40))
        ts = TextInput(hint_text="时间 HH:MM（如 14:30）", size_hint_y=None, height=dp(24))
        ta = TextInput(hint_text="提前几分钟（0/5/10/15/30/60）", size_hint_y=None, height=dp(24))
        box.add_widget(ti); box.add_widget(ts); box.add_widget(ta)
        pop = Popup(title="新建待办", content=box, size_hint=(0.85, 0.6))
        def _save(*a):
            txt = ti.text.strip()
            t = ts.text.strip()
            try:
                hh, mm = map(int, t.split(":"))
                t = "%02d:%02d" % (hh, mm) if 0 <= hh < 24 and 0 <= mm < 60 else t
            except Exception:
                pop.dismiss(); return
            try:
                adv = int(ta.text) if ta.text.strip() else 0
            except Exception:
                adv = 0
            rms = self.cfg.get("reminders", [])
            rms.append({"id": "r%d" % (time.time() * 100 % 1e6), "text": txt,
                        "time": t, "advance": adv if adv >= 0 else 0, "enabled": True,
                        "fired_date": ""})
            self.cfg["reminders"] = rms
            save_cfg(self.cfg); self._refresh_todos(); pop.dismiss()
        ok = Button(text="保存", size_hint_y=None, height=dp(36))
        ok.bind(on_release=_save)
        box.add_widget(ok)
        pop.content = box; pop.open()

    def _del_todos(self):
        self.cfg["reminders"] = []
        save_cfg(self.cfg); self._refresh_todos()

    def _refresh_todo_list(self):
        self._refresh_todos()

    # ---- 调度 ----
    def _check_reminders(self):
        cfg = load_cfg()
        for r in due_now(cfg):
            mark_fired(cfg, r["id"])
            if self._pet:
                self._pet.start_remind(r)
        Clock.schedule_once(lambda dt: self._check_reminders(), 20)

    def on_start(self):
        self._start_loop = Clock.schedule_interval(self._tick_all, 1.0)
        self._heart_click = self.heart

    def _tick_all(self, dt):
        pass  # pet 自带时钟

    def _on_heart_tap_impl(self):
        self._toggle_panel()

    def _heart_tap(self, touch):
        if self.heart.collide_point(*touch.pos):
            self._toggle_panel()
            return True
        return False


if __name__ == "__main__":
    PetApp().run()
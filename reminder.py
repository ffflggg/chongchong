# -*- coding: utf-8 -*-
"""桌面彼得提醒模块：配置加载/保存 + Windows 多媒体（MCI）录音 + 系统 TTS 合成
wav + AI 变声（萝莉/大叔/机器人）+ 播放。全部用标准库/系统组件，稳定可靠。"""
import ctypes
import json
import os
import subprocess
import tempfile
import time
import wave

import numpy as np

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

AI_STYLES = ["萝莉音", "大叔音", "机器人"]
ADVANCE_CHOICES = [0, 5, 10, 15, 30, 60]
CACHE_DIR = os.path.join(BASE_DIR, "cache")


def voice_summary():
    v = load_voice_cfg()
    if v["voice"] == "record":
        return "我的录音"
    if v["voice"] == "ai":
        return "AI·%s" % v["ai_style"]
    return "系统女声"

def mci_send(cmd):
    """发送 MCI 命令字符串，返回 (ok, 返回文本)。"""
    try:
        mci = ctypes.WinDLL("winmm")
        mci.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                       ctypes.c_uint, ctypes.c_void_p]
        mci.mciSendStringW.restype = ctypes.c_uint
        buf = ctypes.create_unicode_buffer(256)
        err = mci.mciSendStringW(cmd, buf, 255, None)
        return err == 0, buf.value
    except Exception:
        return False, ""


def record_wav(path, seconds=3.0):
    """MCI 录音（Windows 自带），返回是否成功。"""
    alias = "pet_rec"
    try:
        _close(alias)
        ok, _ = mci_send('open new type waveaudio alias %s' % alias)
        if not ok:
            return False
        ok, _ = mci_send('record %s' % alias)
        if not ok:
            _close(alias)
            return False
        deadline = time.time() + seconds + 0.5
        while time.time() < deadline:
            time.sleep(0.05)
        mci_send('stop %s' % alias)
        mci_send('save %s "%s"' % (alias, path.replace('"', '""')))
        mci_send('close %s' % alias)
    except Exception:
        _close(alias)
        return False
    return os.path.exists(path) and os.path.getsize(path) > 512


def _close(alias):
    try:
        mci_send('close %s' % alias)
    except Exception:
        pass


def tts_to_wav(text, path, rate=1):
    """系统 TTS（中文女声）合成 wav 文件。PowerShell 自带组件。"""
    ps = (
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$s.Rate = %d\n"
        "$s.SetOutputToWaveFile('%s')\n"
        "$s.Speak('%s')\n"
        "$s.Dispose()\n"
    ) % (rate, path.replace("'", "''"), text.replace("'", "''").replace('\n', ' '))
    script = os.path.join(tempfile.gettempdir(), "pet_tts.ps1")
    try:
        with open(script, "w", encoding="utf-8-sig") as f:
            f.write(ps)
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", script], capture_output=True, timeout=40)
    except Exception:
        return False
    return os.path.exists(path) and os.path.getsize(path) > 1024


def _read_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        data = np.frombuffer(raw, dtype="<i2")
    else:
        data = np.frombuffer(raw, dtype="<i1").astype(np.float32) / 127.0
    data = data.astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def _write_wav(path, data, sr):
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def ai_transform(src, style, dst):
    """AI 变声：萝莉(调高)、大叔(调低)、机器人(电音分段)。"""
    try:
        data, sr = _read_wav(src)
    except Exception:
        return False
    try:
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
        else:  # 机器人：跳帧断续
            hop = sr // 8
            out = []
            for i in range(0, max(len(data) - hop, 1), hop * 2):
                out.append(data[i:i + hop])
            out = np.concatenate(out) if out else data
            # 加谐波颤音
            t = np.arange(len(out)) / sr
            out = out * (0.75 + 0.25 * np.sin(2 * np.pi * 5 * t))
            sr2 = sr
        _write_wav(dst, out, sr2)
        return True
    except Exception:
        return False


def play_wav(path):
    """异步播放 wav（winsound）。"""
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception:
        return False


# ---------------- 待办数据 ----------------

class Reminders:
    """config.json 中的待办列表读写 + 到期计算。"""

    @staticmethod
    def load(cfg=None):
        if cfg is None:
            cfg = _read_config()
        rms = cfg.get("reminders") or []
        return rms

    @staticmethod
    def save(reminders):
        cfg = _read_config()
        cfg["reminders"] = reminders
        _write_config(cfg)

    @staticmethod
    def due_now(rms, now="now"):
        """返回到点（含提前量）且当日未提醒过的待办。now=None 用当前时间。"""
        if now == "now":
            now = time.strftime("%H:%M")
        today = time.strftime("%Y-%m-%d")
        out = []
        for r in rms:
            if not r.get("enabled", True):
                continue
            if r.get("fired_date") == today:
                continue
            fire_at = add_minutes(r.get("time", "09:00"), -int(r.get("advance", 0)))
            if now >= fire_at:
                out.append(r)
        return out

    @staticmethod
    def mark_fired(rms, rid):
        today = time.strftime("%Y-%m-%d")
        for r in rms:
            if r.get("id") == rid:
                r["fired_date"] = today
        Reminders.save(rms)


def _read_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_minutes(hhmm, minutes):
    try:
        h, m = map(int, hhmm.split(":"))
    except Exception:
        return hhmm
    t = (h * 60 + m + minutes) % 1440
    return "%02d:%02d" % (t // 60, t % 60)


def now_hhmm():
    return time.strftime("%H:%M")


def load_voice_cfg():
    cfg = _read_config()
    return {"voice": cfg.get("reminder_voice", "system"),
            "ai_style": cfg.get("reminder_ai_style", "萝莉音"),
            "record_path": cfg.get("reminder_record", ""),
            "advance": cfg.get("reminder_advance", 5)}


def save_voice_cfg(voice=None, ai_style=None, record=None, advance=None):
    cfg = _read_config()
    if voice is not None:
        cfg["reminder_voice"] = voice
    if ai_style is not None:
        cfg["reminder_ai_style"] = ai_style
    if record is not None:
        cfg["reminder_record"] = record
    if advance is not None:
        cfg["reminder_advance"] = advance
    _write_config(cfg)


class RemindScheduler(QObject):
    """每秒检查待办，到点发 remind_fired(id, text)。"""

    remind_fired = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        rms = Reminders.load()
        due = Reminders.due_now(rms)
        for r in due:
            Reminders.mark_fired(rms, r["id"])
            self.remind_fired.emit(r)
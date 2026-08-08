# -*- coding: utf-8 -*-
"""动作库：桌宠的全部动态动作定义（舞蹈/问好/对话/吃东西/睡觉/奔跑等）。"""
import math
from dataclasses import dataclass, field

TWO_PI = 2.0 * math.pi


@dataclass
class Frame:
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0
    sx: float = 1.0
    sy: float = 1.0
    rot: float = 0.0
    alpha: float = 1.0
    flip: bool = False
    move_x: float = 0.0
    lean: float = 0.0
    head_rot: float = 0.0
    upper_rot: float = 0.0
    lower_rot: float = 0.0


@dataclass
class Particle:
    emoji: str
    t: float
    x: float
    y: float
    dx: float = 0.0
    dy: float = -40.0
    life: float = 1.2
    size: float = 24.0
    burst: bool = False


@dataclass
class Action:
    key: str
    name: str
    duration: float
    loop: bool
    fn: object
    particles: tuple = ()
    lines: tuple = ()
    can_move: bool = False


def P(emoji, t, x, y, dx=0.0, dy=-40.0, life=1.2, size=24.0, burst=False):
    return Particle(emoji, t, x, y, dx, dy, life, size, burst)


def _idle(t):
    return Frame(y=math.sin(t * TWO_PI * 0.5) * 4,
                   sx=1 + 0.02 * math.sin(t * TWO_PI * 0.3),
                   sy=1 - 0.02 * math.sin(t * TWO_PI * 0.3),
                   head_rot=2.0 * math.sin(t * TWO_PI * 0.7))


def _walk(t):
    s = math.sin(t * TWO_PI * 2.4)
    return Frame(y=abs(s) * 7,
                 upper_rot=10.0 * s,
                 lower_rot=-10.0 * s,
                 head_rot=3.0 * math.sin(t * TWO_PI * 4.8),
                 move_x=120.0)


def _run(t):
    s = math.sin(t * TWO_PI * 5.0)
    return Frame(y=abs(s) * -6,
                 upper_rot=-14.0 * s,
                 lower_rot=8.0 * s,
                 head_rot=4.0 * math.sin(t * TWO_PI * 10.0),
                 move_x=340.0,
                 lean=14.0)


def _dance(t):
    p = abs(math.sin(t * TWO_PI * 2.2))
    return Frame(y=-p * 16,
                 sx=1 + 0.09 * math.sin(t * TWO_PI * 4.4),
                 sy=1 - 0.09 * math.sin(t * TWO_PI * 4.4),
                 rot=7.0 * math.sin(t * TWO_PI * 1.8),
                 upper_rot=-14.0 * math.sin(t * TWO_PI * 1.8),
                 lower_rot=8.0 * math.sin(t * TWO_PI * 1.8),
                 head_rot=-10.0 * math.sin(t * TWO_PI * 1.8 + 0.6))


def _hello(t):
    slide = min(t / 0.6, 1.0)
    rot = 14.0 * math.sin(t * TWO_PI * 2.0) if t > 0.6 else 0.0
    return Frame(x=-90 * (1 - slide), rot=rot,
                 upper_rot=-24.0 * math.sin(t * TWO_PI * 2.0) * min(t * 1.4, 1.0),
                 head_rot=-6.0 * math.sin(t * TWO_PI * 2.0 + 0.5),
                 sy=1 + 0.02 * math.sin(t * TWO_PI * 3.0))


def _wave(t):
    return Frame(rot=26.0 * math.sin(t * TWO_PI * 1.6),
                 upper_rot=-30.0 * math.sin(t * TWO_PI * 2.8),
                 head_rot=-4.0 * math.sin(t * TWO_PI * 1.6),
                 y=1 * (2 + math.sin(t * TWO_PI * 1.6)))


def _talk(t):
    m = math.sin(t * TWO_PI * 5.5)
    return Frame(sy=1 + 0.05 * m,
                 head_rot=6.0 * math.sin(t * TWO_PI * 2.5),
                 upper_rot=3.0 * math.sin(t * TWO_PI * 2.5),
                 y=2.0 * math.sin(t * TWO_PI * 2.5))


def _eat(t):
    chew = abs(math.sin(t * TWO_PI * 4.0))
    return Frame(rot=9.0 * math.sin(t * TWO_PI * 1.2),
                 head_rot=-8.0 * math.sin(t * TWO_PI * 1.2) - 4.0 * chew,
                 upper_rot=-5.0 * math.sin(t * TWO_PI * 1.2),
                 y=-chew * 5,
                 sy=1 + 0.02 * math.sin(t * TWO_PI * 4.0))


def _sleep(t):
    return Frame(y=10, scale=0.86, alpha=0.9,
                 head_rot=-14.0, upper_rot=-5.0)


def _jump(t):
    d = 1.2
    p = min(t / d, 1.0)
    y = -90 * 4 * p * (1 - p)
    if t < 0.12:
        return Frame(y=0, sy=0.86, sx=1.18)
    if p > 0.8:
        return Frame(y=y, sy=0.86, sx=1.16, head_rot=-5.0, upper_rot=-8.0)
    return Frame(y=y, sy=1.14, sx=0.92, head_rot=-6.0, upper_rot=-12.0)


def _spin(t):
    return Frame(t / 1.5 * 720.0 + 4.0 * math.sin(t * 20.0))


def _angry(t):
    s = math.sin(t * TWO_PI * 30.0)
    return Frame(x=7.0 * math.sin(t * TWO_PI * 22.0),
                 rot=4.0 * s,
                 upper_rot=8.0 * s,
                 head_rot=8.0 * s,
                 y=abs(s * math.sin(t * 12.0)))


def _sneeze(t):
    if t < 0.25:
        return Frame(scale=1.05, y=-4)
    s = math.sin(t * TWO_PI * 26.0)
    return Frame(x=15.0 * s, y=1.0 * abs(math.sin(t * 15.0)),
                 rot=5.0 * s,
                 head_rot=16.0 * math.sin(t * TWO_PI * 34.0),
                 upper_rot=10.0 * s)


def _sad(t):
    return Frame(y=5 + 3 * math.sin(t * TWO_PI * 0.8),
                 rot=2.5 * math.sin(t * TWO_PI * 0.8),
                 head_rot=-8.0,
                 upper_rot=-4.0,
                 alpha=0.95)


def _magic(t):
    return Frame(y=-7 * math.sin(t * TWO_PI * 1.2),
                 rot=3.0 * math.sin(t * TWO_PI),
                 head_rot=4.0 * math.sin(t * TWO_PI * 1.2),
                 upper_rot=-3.0 * math.sin(t * TWO_PI * 1.2),
                 sx=1 + 0.03 * math.sin(t * TWO_PI * 2.0),
                 sy=1 - 0.03 * math.sin(t * TWO_PI * 2.0))


def _ghost(t):
    if t < 0.5:
        alpha = 1.0 - t / 0.5
    elif t < 1.5:
        alpha = 0.0
    elif t < 2.0:
        alpha = (t - 1.5) / 0.5
    else:
        alpha = 1.0
    return Frame(alpha=max(0.0, min(1.0, alpha)),
                 y=4 * math.sin(min(max(t, 0.0), 2.0) * TWO_PI * 0.6))


def _love(t):
    hb = math.sin(t * TWO_PI * 1.6)
    return Frame(sx=1 + 0.05 * hb, sy=1 - 0.05 * hb,
                 y=-2 * hb)


def _double_happy(t):
    return Frame(y=-abs(math.sin(t * TWO_PI * 1.4)) * 22,
                 upper_rot=-14.0 * math.sin(t * TWO_PI * 2.8),
                 lower_rot=8.0 * math.sin(t * TWO_PI * 2.8),
                 head_rot=-8.0 * math.sin(t * TWO_PI * 2.8 + 0.4),
                 sx=1 + 0.06 * math.sin(t * TWO_PI * 5.6))


def sin(v):
    return math.sin(v)


ACTIONS = [
    Action("idle", "发呆", 0.0, True, _idle),
    Action("dance", "跳舞", 6.0, False, _dance,
           particles=(P("🎵", 0.2, -50, -60, 10, -50, 1.2, 24),
                      P("🎶", 0.8, 60, -50, -8, -60, 1.3, 26),
                      P("✨", 1.4, -30, -80, 6, -55, 1.0, 20, burst=True),
                      P("🎵", 2.2, 70, -70, -12, -45, 1.2, 24),
                      P("💃", 2.9, -60, -40, 8, -55, 1.1, 28),
                      P("🎶", 3.6, 40, -90, -6, -60, 1.3, 26),
                      P("✨", 4.3, -20, -85, 5, -50, 1.0, 20, burst=True),
                      P("🎵", 5.0, 65, -55, -10, -50, 1.2, 24)),
           lines=("music! 动起来~", "一起摇摆~", "蹦迪时刻！"),
           ),
    Action("hello", "打招呼", 2.8, False, _hello,
           particles=(P("👋", 0.7, 40, -55, 6, -45, 1.0, 26),
                      P("✨", 0.9, -35, -60, -5, -40, 1.0, 18, burst=True)),
           lines=("你好呀~", "嗨！很高兴见到你！", "有什么需要帮忙的吗？"),
           ),
    Action("wave", "挥手", 4.0, True, _wave,
           particles=(P("👋", 0.4, 38, -60, 5, -45, 1.0, 24),
                      P("👋", 2.0, -40, -55, -6, -40, 1.0, 24)),
           lines=("挥手致意~", "嗨嗨~"),
           ),
    Action("talk", "聊天", 8.0, False, _talk,
           lines=("今天过得怎么样呀？", "我陪着你吧~", "猜猜我在想什么~", "忽然想听个笑话了~"),
           ),
    Action("eat", "吃东西", 6.0, False, _eat,
           particles=(
               P("🍔", 0.5, -80, 25, 65, -55, 0.9, 36),
               P("💦", 1.3, 5, -25, 0, -35, 0.7, 16, burst=True),
               P("🍕", 2.1, -85, 30, 70, -50, 0.9, 36),
               P("💦", 2.9, 5, -25, 0, -35, 0.7, 16, burst=True),
               P("🍖", 3.7, -80, 25, 60, -50, 0.9, 34),
               P("💦", 4.5, 5, -25, 0, -35, 0.7, 16, burst=True),
               P("😋", 5.2, 30, -70, 4, -40, 1.0, 24, burst=True)),
           lines=("啊呜啊呜…", "好好吃！", "吧唧吧唧…", "再来一口！", "吃饱啦，嗝~"),
           ),
    Action("sleep", "睡觉", 6.0, False, _sleep,
           particles=(P("💤", 0.6, 40, -90, 12, -35, 1.4, 28),
                      P("💤", 1.8, 65, -80, 10, -40, 1.5, 32),
                      P("💤", 3.0, 48, -95, 14, -30, 1.4, 26),
                      P("💤", 4.4, 70, -85, 12, -42, 1.5, 30)),
           lines=("Zzz…", "呼~呼呼~", "晚安啦…"),
           ),
    Action("jump", "跳跃", 1.3, False, _jump,
           particles=(P("✨", 0.15, 0, 10, 0, 0, 0.7, 18, burst=True),
                      P("✦", 1.05, -20, -5, -10, -30, 0.8, 16)),
           lines=("嘿咻！", "跳高高~"),
    ),
    Action("run", "奔跑", 1.0, True, _run,
           particles=(P("💨", 0.2, -70, -15, -30, -5, 0.8, 26),
                      P("💨", 0.7, -75, 15, -30, -2, 0.8, 24),
                      P("💨", 1.2, -70, 0, -35, -8, 0.9, 28)),
           lines=("冲鸭——！", "让开让开~"),
           can_move=True,
           ),
    Action("walk", "散步", 1.0, True, _walk,
           lines=("走两圈~", "今天的空气不错~"),
           can_move=True,
    ),
    Action("spin", "转圈圈", 1.6, False, _spin,
           particles=(P("🌀", 0.3, 30, -60, 8, -50, 1.1, 26),
                      P("🌟", 0.9, -40, -80, -6, -40, 1.2, 24),
                      P("🌀", 1.1, 20, -70, 6, -35, 1.0, 24)),
           lines=("转晕啦…", "头晕眼花~"),
    ),
    Action("angry", "生气", 2.5, False, _angry,
           particles=(P("💢", 0.4, 45, -100, 8, -25, 0.9, 26, burst=True),
                      P("💢", 1.0, -40, -90, -6, -20, 0.9, 24, burst=True)),
           lines=("哼！！", "我生气啦！", "哄不好的那种！"),
    ),
    Action("sneeze", "打喷嚏", 1.2, False, _sneeze,
           particles=(P("💦", 0.5, 0, 0, 0, 0, 0.9, 36, burst=True),
                      P("✨", 0.6, 30, 10, 8, -30, 0.8, 18)),
           lines=("阿嚏！！", "谁在想我~"),
    ),
    Action("sad", "难过", 3.0, False, _sad,
           particles=(P("💧", 0.8, 35, -20, 4, 45, 1.4, 22),
                      P("💧", 2.0, 45, -25, 6, 45, 1.4, 22)),
           lines=("呜……", "有点难过呢", "求安慰…"),
    ),
    Action("magic", "魔法", 4.0, True, _magic,
           particles=(P("✨", 0.5, -30, -70, 0, -30, 1.2, 22, burst=True),
                      P("🌟", 1.2, 40, -60, -6, -40, 1.2, 24, burst=True),
                      P("🧚", 2.0, -40, -40, 5, -45, 1.3, 26),
                      P("✨", 2.8, 60, -70, -8, -50, 1.2, 22, burst=True),
                      P("⭐", 3.4, 20, -85, 4, -45, 1.1, 20)),
           lines=("叮咚！魔法时间~", "呼啦呼啦变！", "见证奇迹~"),
    ),
    Action("ghost", "隐身术", 2.0, True, _ghost,
           particles=(P("👻", 0.15, 20, -60, 8, -30, 0.6, 26),
                      P("✨", 1.95, -30, -70, 0, -30, 0.8, 20, burst=True)),
           lines=("看不见我看不见我~", "隐形中…完全消失！"),
    ),
    Action("happy", "开心跳跃", 2.5, True, _double_happy,
           particles=(P("🎉", 0.4, -40, -50, 0, -45, 1.1, 24, burst=True),
                      P("🎊", 1.2, 50, -55, -4, -50, 1.2, 26, burst=True),
                      P("✨", 2.0, -20, -60, 5, -40, 1.0, 18)),
           lines=("耶！太开心啦~", "好运来~"),
    ),
]


ACTIONS_BY_KEY = {a.key: a for a in ACTIONS}

def clamp(v, lo, hi):
    return max(lo, min(hi, v))
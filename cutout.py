# -*- coding: utf-8 -*-
"""抠图模块：自动识别图片主体并去除背景。"""
import hashlib
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
MODEL_CHOICES = ["u2net", "u2netp", "isnet-general-use"]


def _ensure_bundled_models():
    """如果 exe 内嵌了抠图模型（打包时 --add-data），复制到用户 ~/.u2net，
    让 rembg 离线也能加载，别人分享的 exe 无需联网。"""
    try:
        bundled = None
        if getattr(sys, "_MEIPASS", None):
            p = os.path.join(sys._MEIPASS, "models")
            if os.path.isdir(p):
                bundled = p
        if bundled is None:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
            if os.path.isdir(p):
                bundled = p
        if not bundled:
            return False
        home = os.path.join(os.path.expanduser("~"), ".u2net")
        os.makedirs(home, exist_ok=True)
        os.environ["U2NET_HOME"] = home
        copied = False
        for name in os.listdir(bundled):
            if name.endswith(".onnx"):
                src = os.path.join(bundled, name)
                dst = os.path.join(home, name)
                if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
                    shutil.copy2(src, dst)
                    copied = True
        return copied or True
    except Exception:
        return False


def _has_alpha(img):
    if img.mode not in ("RGBA", "LA"):
        return False
    a = np.asarray(img)
    if img.mode == "RGBA":
        a = a[:, :, 3]
    else:
        a = a[:, :, 1]
    return bool((a < 255).any())


def _manual_cutout(img):
    """离线兜底抠图：从边缘向内颜色洪水填充，适合背景较单纯的图片。"""
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


def compute_parts_from_alpha(alpha):
    """定位躯干分割线。返回 (neck_r, waist_r, quality)。

    quality: 0=无可靠分割（整幅直画，最自然），
             1=仅能分出头部（头/身体两段），
             2=颈腰均可靠（头/上身/腿三段）。

    仅当候选行宽度显著小于其上下邻域（局部谷）时才认定分割线，
    否则保守回退，宁可不分也绝不硬切躯干。
    """
    try:
        h, w = alpha.shape
        if h < 20:
            return 0.28, 0.52, 0
        mask = alpha > 20
        profile = mask.sum(axis=1).astype(float)
        nz = np.nonzero(profile)[0]
        if nz.size < 10:
            return 0.28, 0.52, 0
        top, bot = int(nz[0]), int(nz[-1])
        H = bot - top + 1
        p = profile[top:bot + 1]
        widest = p.max()
        if widest < 10:
            return 0.28, 0.52, 0

        def find_valley(lo, hi):
            """在行区间找“明显窄于周围主体”的局部最小，返回行号(全局)或 None。"""
            lo = max(1, lo)
            hi = min(len(p) - 2, hi)
            if hi <= lo + 3:
                return None
            half = max(3, int(H * 0.045))
            for i in range(lo, hi):
                v = p[i]
                if v < 3:
                    continue
                w0 = max(0, i - half)
                w1 = min(len(p), i + half + 1)
                m = p[w0:w1].mean()
                if v < m * 0.80 and v < widest * 0.88:
                    return i
            return None

        neck_i = find_valley(int(0.05 * H), int(0.42 * H))
        if neck_i is None:
            return 0.28, 0.52, 0
        neck = (top + neck_i) / float(h)
        neck_r = max(0.12, min(0.42, neck))

        waist_i = find_valley(int(neck_i + 0.12 * H), int(0.88 * H))
        if waist_i is None or (waist_i - neck_i) < 0.10 * H:
            # 仅头部可分：两段，腰部用保守位置供两段绘制
            return round(neck_r, 3), round(max(0.45, min(0.65, neck_r + 0.30)), 3), 1
        waist_r = (top + waist_i) / float(h)
        waist_r = max(neck_r + 0.10, min(0.80, waist_r))
        return round(neck_r, 3), round(waist_r, 3), 2
    except Exception:
        return 0.28, 0.52, 0


def cutout(path, model="u2net", on_status=None):
    """对图片做主体抠图，返回 RGBA 的 PIL.Image。"""
    def status(msg):
        if on_status:
            on_status(msg)

    _ensure_bundled_models()

    img = Image.open(path)
    if _has_alpha(img):
        status("图片本身已带透明通道，跳过抠图")
        return img.convert("RGBA")

    key = hashlib.md5((model + os.path.basename(path)).encode("utf-8")).hexdigest()
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, key + ".png")
    if os.path.exists(cache):
        status("使用缓存的抠图结果")
        return Image.open(cache).convert("RGBA")

    order = [model] + [m for m in MODEL_CHOICES if m != model]
    result = None
    for m in order:
        try:
            status("正在用模型 %s 抠图…（首次运行需下载模型，请稍候）" % m)
            from rembg import new_session, remove
            session = new_session(m)
            result = remove(img, session=session)
            break
        except Exception as e:
            status("模型 %s 加载失败：%s" % (m, e))

    if result is None:
        status("模型不可用，已切换为内置自动背景去除（适合背景较单纯的图片）")
        result = _manual_cutout(img)

    result = result.convert("RGBA")
    try:
        result.save(cache)
    except Exception:
        pass
    return result

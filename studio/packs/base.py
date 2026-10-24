"""База шаблона сцены. Контракт — studio/templates.py (докстринг) и docs/SCENE_SPEC.md."""
from __future__ import annotations

from .. import style as SM
from ..gfx import eio, eo, lerp, prog

class Box:
    """Рамка в пикселях кадра: x0, y0, x1, y1 и производные w, h, cx, cy."""

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.w, self.h = x1 - x0, y1 - y0
        self.cx, self.cy = (x0 + x1) / 2, (y0 + y1) / 2

    def __repr__(self):
        return f"Box({self.x0:g}, {self.y0:g}, {self.x1:g}, {self.y1:g})"


SAFE = {"top": 0.04, "bottom": 0.04, "left": 0.04, "right": 0.04}  # ctx без "safe" (тесты, старые вызовы)


class Template:
    uses_phone = False

    def __init__(self, ctx, scene, state):
        self.ctx, self.s, self.state = ctx, scene, state
        self.style = ctx.get("style") or SM.active()
        self.p = scene.get("params") or {}
        self.W, self.H = ctx["W"], ctx["H"]
        self.u = min(self.W, self.H) / 1080
        self.vert = self.H >= self.W
        # сетка безопасной зоны (ROADMAP B2): поля площадки проекта или формата, интерфейс площадки — в боковых полях
        # с запасом 1 % на покачивание и сглаживание; self.area — то же без полосы субтитров (тело шаблона)
        sf, e = ctx.get("safe") or SAFE, 0.01 * min(self.W, self.H)
        self.safe = Box(sf["left"] * self.W + e, sf["top"] * self.H + e,
                        self.W * (1 - sf["right"]) - e, self.H * (1 - sf["bottom"]) - e)
        st = ctx.get("subs_top")
        self.area = Box(self.safe.x0, self.safe.y0, self.safe.x1,
                        min(self.safe.y1, st * self.H - 2 * e) if st else self.safe.y1)
        self.D = scene["dur"]
        self.fps = ctx["fps"]
        self.beats = scene["beats"]
        self.first, self.last = scene.get("first", False), scene.get("last", False)
        if self.vert:
            self.fx, self.fy = self.W / 2, self.H * 0.42
        else:
            self.fx, self.fy = self.W * 0.66, self.H * 0.44
        self.cy = self.H * (0.42 if self.vert else 0.47)  # центр текстовых шаблонов
        self.k = 1.0 if self.vert else 1.18               # в широком кадре текст крупнее

    # --- beats
    def bt(self, i, default=None):
        if i is None:
            return default
        if -len(self.beats) <= i < len(self.beats):
            return self.beats[i]["t0"]
        return default if default is not None else self.D

    def be(self, i, default=None):
        if -len(self.beats) <= i < len(self.beats):
            return self.beats[i]["t1"]
        return default if default is not None else self.D

    def io(self, t, a=0.35, b=0.35, enter=True, exit=True):
        k = 1.0
        if enter:
            k = min(k, eo(prog(t, 0, a)))
        if exit:
            k = min(k, 1 - prog(t, self.D - b, self.D))
        return k

    def setup(self):
        pass

    def draw(self, img, t, T):
        raise NotImplementedError

    def safe_draw(self, img, t, T):
        """То, что проверяет «Контент в безопасной зоне» (studio/safezone.py): по умолчанию весь кадр шаблона;
        фото и видео на весь кадр (media) — подложка, им можно под обрез, проверяется только то, что поверх."""
        self.draw(img, t, T)

    feed_speed = None
    dim_out = 0.0  # затемнение экрана телефона в конце сцены (передаётся следующей сцене)

    def dim(self, t, target, dur=0.6, start=0.0):
        """Плавно ведём затемнение от уровня предыдущей сцены к target -> на стыке нет вспышки."""
        d0 = self.state.get("screen_dim", 0.0)
        return lerp(d0, target, eio(prog(t, start, start + dur)))


def plural(n, forms):
    """forms: строка | [один, много] (en) | [один, два-четыре, пять] (ru)."""
    if isinstance(forms, str):
        return forms
    if len(forms) == 2:
        return forms[0] if abs(int(n)) == 1 else forms[1]
    n = abs(int(n)) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    return forms[0] if n == 1 else forms[1] if 2 <= n <= 4 else forms[2]

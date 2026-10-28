"""Стиль ролика: палитра, настроение, шрифты по ролям, фон, камера, режим субтитров — один объект `Style`.

Строится из `project.yaml → style` (`Style.from_cfg`), неизменяемый и хэшируемый: кэши спрайтов в gfx держат
стиль в ключе, поэтому смена стиля в процессе не требует `cache_clear`. Рендер кладёт стиль в `ctx["style"]`,
шаблоны читают `self.style`. `use()` делает стиль активным для хелперов gfx, вызванных без `style=` (шаблоны
проектов, старый код) — это единственная точка «текущего стиля»; глобалов стиля в gfx нет.
"""
from __future__ import annotations

import functools
import json
import os
import re
from dataclasses import dataclass
from types import MappingProxyType

# ------------------------------------------------------------------ palette
PALETTES = {
    "neon": {
        "bg_top": (7, 6, 16), "bg_bot": (14, 10, 32), "text": (244, 241, 255), "dim": (141, 134, 181),
        "cyan": (56, 243, 255), "magenta": (255, 61, 242), "violet": (139, 92, 255),
        "lime": (182, 255, 61), "amber": (255, 194, 61), "red": (255, 77, 109),
        "panel": (20, 17, 40), "accent": (56, 243, 255), "accent2": (255, 61, 242),
    },
    "calm": {
        "bg_top": (8, 14, 18), "bg_bot": (10, 24, 30), "text": (236, 248, 246), "dim": (126, 160, 160),
        "cyan": (90, 230, 210), "magenta": (255, 140, 120), "violet": (120, 150, 255),
        "lime": (170, 240, 120), "amber": (255, 205, 110), "red": (255, 110, 110),
        "panel": (16, 30, 36), "accent": (90, 230, 210), "accent2": (255, 205, 110),
    },
    # канал Notes From The Mind: channel/STYLE.md, раздел 2. Цвета вердиктов — только для вердиктов.
    "lab": {
        "bg_top": (10, 13, 20), "bg_bot": (10, 13, 20), "bg": (10, 13, 20), "bg2": (17, 23, 38),
        "text": (238, 242, 248), "dim": (139, 149, 167),
        "cyan": (61, 214, 245), "magenta": (155, 140, 255), "violet": (155, 140, 255),
        "lime": (52, 211, 153), "amber": (251, 191, 36), "red": (242, 84, 91),
        "panel": (17, 23, 38), "accent": (61, 214, 245), "accent2": (155, 140, 255),
        "true": (52, 211, 153), "half": (251, 191, 36), "myth": (242, 84, 91), "noev": (139, 149, 167),
        "ink": (20, 28, 46),
    },
}

# Пресет = палитра + (необязательно) фон, шрифты по ролям, камера. Без записи здесь — прежнее поведение.
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
STYLES = {
    "lab": {
        "background": "lab",          # studio/lab.py: LabBackground
        "camera": True,                # дрейф камеры для шаблонов с camera = True
        "subs": "karaoke",             # слова загораются по мере произнесения
        "fonts": {"head": "fonts/Manrope-VF.ttf", "num": "fonts/Unbounded-VF.ttf", "mono": "fonts/JetBrainsMono-VF.ttf"},
    },
}

# Цветовые настроения поверх палитры (channel/STYLE.md §14): подсветки фона + второй акцент.
# `lab` — значения самой палитры, т.е. «без настроения». Каркас (bg, accent, вердикты) не трогаем.
MOODS = {
    "lab": {"glow_cool": (61, 214, 245), "glow_warm": (155, 140, 255), "accent2": (155, 140, 255)},
    "night": {"glow_cool": (91, 124, 255), "glow_warm": (155, 140, 255), "accent2": (109, 124, 255)},
    "ember": {"glow_cool": (61, 214, 245), "glow_warm": (255, 159, 107), "accent2": (247, 143, 179)},
    "deep": {"glow_cool": (43, 179, 201), "glow_warm": (109, 124, 255), "accent2": (165, 200, 255)},
    "orchid": {"glow_cool": (61, 214, 245), "glow_warm": (213, 140, 255), "accent2": (213, 140, 255)},
}
MOOD_KEYS = ("glow_cool", "glow_warm", "accent2")
DEFAULT_FONT = "Inter Display"


def hex_rgb(s):
    s = str(s).strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", s):
        raise ValueError(f"цвет '{s}' — нужен #RRGGBB")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def mood_colors(mood=None, overrides=None, base=None):
    """Цвета настроения: {glow_cool, glow_warm, accent2}. Без настроения — accent/accent2 палитры
    (base; по умолчанию — палитра активного стиля)."""
    base = base or active().pal
    out = {"glow_cool": base["accent"], "glow_warm": base["accent2"], "accent2": base["accent2"]}
    if mood:
        if mood not in MOODS:
            raise ValueError(f"нет настроения '{mood}' (есть: {', '.join(MOODS)})")
        out.update(MOODS[mood])
    for k, v in (overrides or {}).items():
        if k not in MOOD_KEYS:
            raise ValueError(f"style.overrides.{k}: можно только {', '.join(MOOD_KEYS)}")
        out[k] = hex_rgb(v)
    return out


@dataclass(frozen=True)
class Style:
    """Сравнение и хэш — по входам (палитра, настроение, overrides, семейство шрифта, кит); остальное выводится."""
    palette: str = "neon"
    mood: str | None = None
    overrides: tuple = ()          # ((ключ, "#hex"), ...) отсортировано
    font: str = DEFAULT_FONT       # семейство для fc-match, когда у пресета нет своих файлов
    kit: str = ""                  # бренд-кит (studio/brand.py) — JSON; пусто — встроенные PALETTES/STYLES
    subs_mode: str = ""            # subtitles.style проекта: plate | karaoke | tiktok поверх пресета/кита (ROADMAP C4)

    @classmethod
    def from_cfg(cls, style: dict | None) -> "Style":
        """project.yaml → style: palette, mood, overrides, font; kit — развёрнутый бренд-кит (brand.resolve)."""
        style = style or {}
        kit = style.get("kit")
        return cls(kit["base"] if kit else style.get("palette", "neon"), style.get("mood"),
                   tuple(sorted((style.get("overrides") or {}).items())), style.get("font") or DEFAULT_FONT,
                   json.dumps(kit, sort_keys=True, ensure_ascii=False) if kit else "", style.get("subs") or "")

    def __post_init__(self):
        self.pal  # неверное настроение/overrides — ошибка сразу, как раньше в apply_style

    def __reduce__(self):  # в воркеры рендера — только входы; производные пересчитаются
        return (Style, (self.palette, self.mood, self.overrides, self.font, self.kit, self.subs_mode))

    @functools.cached_property
    def brand(self):
        """Бренд-кит (только чтение) или None."""
        return MappingProxyType(json.loads(self.kit)) if self.kit else None

    @functools.cached_property
    def pal(self):
        """Палитра с цветами настроения (только чтение)."""
        if self.brand:
            p = {k: tuple(v) for k, v in self.brand["colors"].items()}
        else:
            p = dict(PALETTES.get(self.palette, PALETTES["neon"]))
        p.update(mood_colors(self.mood, dict(self.overrides), base=p))
        return MappingProxyType(p)

    @functools.cached_property
    def preset(self):
        """Фон, камера, субтитры, шрифты по ролям: из кита, иначе встроенный пресет палитры (STYLES)."""
        if self.brand:
            b = self.brand
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            fonts = {r: os.path.normpath(os.path.join(root, p)) for r, p in b["fonts"].items()}
            return MappingProxyType({"background": b["background"]["type"], "camera": b["camera"],
                                     "subs": b["subs"], "fonts": fonts})
        return MappingProxyType(STYLES.get(self.palette, {}))

    @property
    def background(self):
        return self.preset.get("background")

    @property
    def camera(self):
        return bool(self.preset.get("camera"))

    @property
    def subs(self):
        """Режим субтитров: subtitles.style проекта, иначе пресет или бренд-кит (karaoke | plate | tiktok), иначе None."""
        return self.subs_mode or self.preset.get("subs")

    @property
    def fonts(self):
        """Файлы шрифтов по ролям (head | num | mono), пути от assets/ (кита — абсолютные). Пусто — системное семейство `font`."""
        return self.preset.get("fonts") or {}

    @property
    def shape(self):
        """Радиус и толщина линий бренда (дизайн-пиксели 1920×1080): {radius, line}; пусто — токены шаблонов."""
        return dict(self.brand["shape"]) if self.brand else {}

    @property
    def motion(self):
        """Движение бренда: {transition: none | wipe, bg: скорость пятен фона}; пусто — без кита или без ключа motion."""
        return dict((self.brand or {}).get("motion") or {})

    @property
    def key(self):
        return (self.palette, self.mood, self.overrides, self.font, self.kit) + ((self.subs_mode,) if self.subs_mode else ())

    def col(self, c, a=255):
        """'cyan' | (r,g,b) | '#rrggbb' -> (r,g,b,a); неизвестное имя — accent."""
        if isinstance(c, str):
            if c.startswith("#"):
                c = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
            else:
                c = self.pal.get(c, self.pal["accent"])
        return (c[0], c[1], c[2], a)


_active = Style()


def use(style: Style) -> Style:
    """Сделать стиль активным для хелперов gfx без явного `style=`. Возвращает его же."""
    global _active
    _active = style
    return style


def active() -> Style:
    return _active

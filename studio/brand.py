"""Бренд-кит студии (ROADMAP A2): `studios/<id>/brand/brand.yaml` → стиль ролика без программирования.

Проект включает кит ключом `style.brand` (путь к папке кита от корня студии, обычно `brand`; умолчание — в
`studio.yaml → defaults`). `project.load` разворачивает кит в `cfg["style"]["kit"]` (`resolve`): полная палитра,
шрифты по ролям, фон, камера, субтитры и ассеты бренда — пути от корня репозитория, чтобы ключ кэша рендера
(хэш `cfg["style"]`) не зависел от машины и менялся при правке `brand.yaml`. `Style.from_cfg` строит стиль из кита.

Формат и порядок «свой стиль по референсу» — docs/BRAND.md.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from .style import ASSETS, PALETTES, hex_rgb
from .workspace import ROOT

BACKGROUNDS = ("lab", "gradient", "solid", "image")  # lab — LabBackground; image — фото-подложка
SUBS = ("karaoke", "plate", "tiktok")                # караоке по словам | плашка | крупные TikTok-субтитры
FONT_ROLES = ("head", "num", "mono")
# Роль палитры → ключи палитры движка (шаблоны читают ключи). Ключ палитры можно задать и напрямую — он главнее роли.
ROLES = {
    "bg": ("bg", "bg_top", "bg_bot"), "surface": ("bg2", "panel"), "text": ("text",), "dim": ("dim",),
    "accent": ("accent", "cyan"), "accent2": ("accent2", "magenta", "violet"),
    "good": ("true", "lime"), "warn": ("half", "amber"), "bad": ("myth", "red"), "neutral": ("noev",),
    "ink": ("ink",),
}
KEYS = ("name", "base", "palette", "fonts", "logo", "shape", "background", "camera", "subs",
        "intro", "outro", "cta", "music", "voice")


def _rel(p: Path) -> str:
    """Путь для кита: от корня репозитория (переносимо между машинами), вне его — абсолютный."""
    p = p.resolve()
    try:
        return p.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def path(rel: str) -> str:
    """Путь из кита → абсолютный."""
    return rel if os.path.isabs(rel) else str(ROOT / rel)


def _file(kit_dir: Path, name, where, errs, fonts=False):
    """Файл ассета: в папке кита (для шрифтов ещё brand/fonts/ и общие assets/fonts/)."""
    if not isinstance(name, str) or not name:
        errs.append(f"{where}: нужен путь к файлу")
        return None
    cands = [kit_dir / name]
    if fonts:
        cands += [kit_dir / "fonts" / name, Path(ASSETS) / name, Path(ASSETS) / "fonts" / name]
    for c in cands:
        if c.is_file():
            return _rel(c)
    errs.append(f"{where}: нет файла {name} (искал в {kit_dir.name}/" + (", fonts/, assets/fonts/)" if fonts else ")"))
    return None


def load(kit_dir) -> dict:
    """brand.yaml → нормализованный кит (словарь из JSON-типов). Ошибки — SystemExit со списком."""
    kit_dir = Path(kit_dir)
    f = kit_dir / "brand.yaml"
    if not f.is_file():
        raise SystemExit(f"Бренд-кит: нет {f}")
    raw = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    kit, errs = parse(raw, kit_dir)
    if errs:
        raise SystemExit(f"Бренд-кит {f}:\n" + "\n".join(f"  ❌ {e}" for e in errs))
    return kit


def parse(raw: dict, kit_dir: Path) -> tuple[dict, list[str]]:
    errs = []
    for k in raw:
        if k not in KEYS:
            errs.append(f"неизвестный ключ {k} (есть: {', '.join(KEYS)})")
    base = raw.get("base", "neon")
    if base not in PALETTES:
        errs.append(f"base: {base!r} — нет палитры (есть: {', '.join(PALETTES)})")
        base = "neon"
    colors = {k: list(v) for k, v in PALETTES[base].items()}
    pal = raw.get("palette") or {}
    if not isinstance(pal, dict):
        errs.append("palette: нужен словарь роль → #RRGGBB")
        pal = {}
    direct = {}
    for k, v in pal.items():
        try:
            rgb = list(hex_rgb(v))
        except ValueError as e:
            errs.append(f"palette.{k}: {e}")
            continue
        if k in ROLES:
            for key in ROLES[k]:
                colors[key] = rgb
        elif k in colors:
            direct[k] = rgb
        else:
            errs.append(f"palette.{k}: нет такой роли или ключа палитры (роли: {', '.join(ROLES)})")
    colors.update(direct)  # ключ палитры главнее роли: bg: + bg_bot: — градиент

    fonts = {}
    for role, spec in (raw.get("fonts") or {}).items():
        if role not in FONT_ROLES:
            errs.append(f"fonts.{role}: роли шрифтов — {', '.join(FONT_ROLES)}")
            continue
        spec = spec if isinstance(spec, dict) else {"file": spec}
        if not spec.get("license"):
            errs.append(f"fonts.{role}: укажите license (OFL, коммерческая лицензия клиента…) — права на шрифт")
        p = _file(kit_dir, spec.get("file"), f"fonts.{role}", errs, fonts=True)
        if p:
            fonts[role] = p

    bg = raw.get("background", "gradient")
    bg = bg if isinstance(bg, dict) else {"type": bg}
    if bg.get("type") not in BACKGROUNDS:
        errs.append(f"background: {bg.get('type')!r} — можно {', '.join(BACKGROUNDS)}")
    background = {"type": bg.get("type")}
    if bg.get("type") == "image":
        background["file"] = _file(kit_dir, bg.get("file"), "background.file", errs)
        dim = bg.get("dim", 0.45)
        if not (isinstance(dim, (int, float)) and 0 <= dim <= 1):
            errs.append(f"background.dim = {dim!r}: доля 0–1 затемнения фото")
        background["dim"] = dim

    subs = raw.get("subs", "plate")
    if subs not in SUBS:
        errs.append(f"subs: {subs!r} — можно {', '.join(SUBS)}")
    camera = raw.get("camera", False)
    if not isinstance(camera, bool):
        errs.append(f"camera: {camera!r} — да/нет")

    shape = raw.get("shape") or {}
    for k, v in shape.items():
        if k not in ("radius", "line") or not isinstance(v, (int, float)) or v < 0:
            errs.append(f"shape.{k} = {v!r}: можно radius, line — числа ≥ 0 (дизайн-пиксели 1920×1080)")

    logo = {}
    for k, v in (raw.get("logo") or {}).items():
        if k not in ("light", "dark"):
            errs.append(f"logo.{k}: варианты логотипа — light (на тёмном фоне), dark (на светлом)")
            continue
        logo[k] = _file(kit_dir, v, f"logo.{k}", errs)
    assets = {k: _file(kit_dir, raw[k], k, errs) for k in ("intro", "outro", "music") if raw.get(k)}
    cta = raw.get("cta")
    if cta is not None and not isinstance(cta, dict):
        errs.append("cta: словарь (text, url…)")
    voice = raw.get("voice")
    if voice is not None and not isinstance(voice, dict):
        errs.append("voice: словарь (tone: …)")

    kit = {"name": str(raw.get("name") or kit_dir.parent.name), "base": base, "colors": colors, "fonts": fonts,
           "background": background, "camera": camera is True, "subs": subs, "shape": dict(shape), "logo": logo,
           **assets, "cta": cta or {}, "voice": voice or {}}
    return kit, errs


def resolve(cfg: dict, studio_root: Path) -> dict:
    """cfg проекта → cfg с развёрнутым китом (`style.kit`), если задан `style.brand`. Палитра проекта — база кита;
    музыка бренда — если у проекта нет своей."""
    st = cfg.get("style") or {}
    ref = st.get("brand")
    if not ref:
        return cfg
    d = Path(ref)
    d = d if d.is_absolute() else Path(studio_root) / d
    kit = load(d)
    cfg = dict(cfg, style=dict(st, kit=kit, palette=kit["base"]))
    if kit.get("music") and not (cfg.get("music") or {}).get("file"):
        cfg["music"] = dict(cfg.get("music") or {}, file=path(kit["music"]))
    return cfg


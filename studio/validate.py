"""Проверка сценария (`python -m studio validate`): ошибки и предупреждения без печати — печатает команда."""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field


@dataclass
class Report:
    errs: list = field(default_factory=list)
    warns: list = field(default_factory=list)
    scenes: int = 0
    words: int = 0
    est: float = 0.0       # оценка речи, c
    pace: float = 0.0      # слов/мин, по которым оценка
    pace_src: str = ""

    @property
    def ok(self):
        return not self.errs


def check(proj) -> Report:
    from .packs import REGISTRY, TemplateNameError, load_project_templates
    from .textutil import word_count, segments, line_text, line_voice, AUDIO_TAG
    from .lang import profile
    lp = profile(proj.cfg["language"])
    errs, warns = [], []
    try:
        load_project_templates(proj.root)
    except TemplateNameError as e:
        errs.append(f"templates/: {e}")
    off_format = {}  # шаблон → сцены, когда шаблон не свёрстан под format проекта
    ids = set()
    words = 0
    accents = []  # где переопределён голос: правило канала — 1–2 на ролик (крючок, вердикт)
    for ch, d in proj.chapters:
        for s in d.get("scenes") or []:
            sid = s.get("id")
            if not sid or (ch, sid) in ids:
                errs.append(f"{ch}: сцена без id или повтор id ({sid})")
            ids.add((ch, sid))
            tp = s.get("template", "statement")
            if tp not in REGISTRY:
                near = difflib.get_close_matches(str(tp), list(REGISTRY), n=3)
                errs.append(f"{ch}/{sid}: нет шаблона '{tp}'" + (f" — может, {' / '.join(near)}?" if near else "")
                            + f" (есть: {', '.join(sorted(REGISTRY))})")
            else:
                cls = REGISTRY[tp]
                warns += params(cls, tp, s.get("params"), f"{ch}/{sid}")
                if proj.cfg["format"] not in cls.FORMATS:
                    off_format.setdefault(cls, []).append(f"{ch}/{sid}")
            lines = s.get("lines") or []
            if not lines and not s.get("min_duration"):
                errs.append(f"{ch}/{sid}: нет текста и не задан min_duration")
            if s.get("voice"):
                accents.append(f"{ch}/{sid}")
                voice(proj, s["voice"], f"{ch}/{sid}", errs, warns)
            for item in lines:
                l = line_text(item)
                if isinstance(item, dict) and not l.strip():
                    errs.append(f"{ch}/{sid}: строка-словарь без text")
                if line_voice(item):
                    accents.append(f"{ch}/{sid}: «{l[:30]}…»")
                    voice(proj, line_voice(item), f"{ch}/{sid}", errs, warns)
                model = {**proj.cfg["tts"], **(s.get("voice") or {}), **line_voice(item)}.get("model", "")
                if AUDIO_TAG.search(l) and not str(model).startswith("eleven_v3"):
                    warns.append(f"{ch}/{sid}: «{l[:40]}…»: тег эмоции без model: eleven_v3 — будет прочитан вслух")
                words += word_count(l)
                if lp["foreign"] and re.search(lp["foreign"], l.replace("|", "")):
                    warns.append(f"{ch}/{sid}: «{l[:40]}…»: {lp['foreign_msg']}")
                if len(l) > 220:
                    warns.append(f"{ch}/{sid}: очень длинная строка ({len(l)} симв.) — разбейте на предложения")
                if any(len(x) > 90 for x in segments(l)):
                    warns.append(f"{ch}/{sid}: длинный бит без '|' — субтитры порежутся по словам")
    if off_format:
        where = [w for ws in off_format.values() for w in ws]
        warns.append(f"format: {proj.cfg['format']} — шаблоны свёрстаны под другой формат: "
                     + ", ".join(f"{c.NAME} ({'/'.join(c.FORMATS)})" for c in off_format)
                     + f"; сцен {len(where)}: {', '.join(where[:4])}{' …' if len(where) > 4 else ''}")
    if len(accents) > 2:
        warns.append(f"голос переопределён {len(accents)} раз ({', '.join(accents)}) — правило канала: 1–2 акцента "
                     f"на ролик (крючок, вердикт), спокойный рассказчик — часть тона")
    style(proj, errs, warns)
    triggers(proj, errs, warns)
    from .calibration import wpm
    pace, pace_src = wpm(proj)
    est = words / pace * 60
    tgt = proj.cfg.get("target_duration")
    if tgt and est > tgt * 0.92:
        warns.append(f"Текста много для {tgt} c (оценка {est:.0f} c) — темп может упереться в потолок")
    return Report(errs, warns, len(ids), words, est, pace, pace_src)


def params(cls, tp, p, where):
    """Параметры сцены по PARAMS шаблона (registry.Param): неизвестные ключи и тип значения → предупреждения."""
    p = p or {}
    out = []
    unknown = set(p) - set(cls.PARAMS)
    if unknown:
        out.append(f"{where}: неизвестные параметры {sorted(unknown)} для {tp}")
    for k, v in p.items():
        bad = k in cls.PARAMS and cls.PARAMS[k].check(v)
        if bad:
            out.append(f"{where}: {tp}.{k} = {v!r} — {bad}")
    return out


def voice(proj, v, where, errs, warns):
    """voice: сцены/строки (docs/TTS.md): только elevenlabs, известные ключи, диапазоны API, не быстрее rate_range."""
    from .tts import EL_VOICE_KEYS, EL_SPEED
    tc = proj.cfg["tts"]
    if not isinstance(v, dict):
        errs.append(f"{where}: voice должен быть словарём {{stability, style, speed, …}}")
        return
    if tc["backend"] != "elevenlabs":
        warns.append(f"{where}: voice действует только для tts.backend: elevenlabs — сейчас игнорируется")
    unknown = set(v) - set(EL_VOICE_KEYS)
    if unknown:
        errs.append(f"{where}: неизвестные ключи voice {sorted(unknown)} (есть: {', '.join(EL_VOICE_KEYS)})")
    for k in ("stability", "similarity_boost", "style"):
        if k in v and not (isinstance(v[k], (int, float)) and 0 <= v[k] <= 1):
            errs.append(f"{where}: voice.{k} = {v[k]!r}, нужно число 0–1")
    if "speed" in v:
        sp, hi = v["speed"], tc.get("rate_range", [98, 125])[1] / 100
        if not (isinstance(sp, (int, float)) and EL_SPEED[0] <= sp <= EL_SPEED[1]):
            errs.append(f"{where}: voice.speed = {sp!r}, API принимает {EL_SPEED[0]}–{EL_SPEED[1]}")
        elif sp > hi:
            errs.append(f"{where}: voice.speed {sp} быстрее потолка rate_range ({hi:g}) — речь не ускоряем")
    if "model" in v:
        warns.append(f"{where}: voice.model = {v['model']} — эксперимент: тембр и таймкоды сверить на слух и в stills")


def style(proj, errs, warns):
    """style.mood / style.overrides / glow глав (channel/STYLE.md §14): accent2 не спорит с вердиктами и бренд-цианом."""
    from . import gfx as G
    st = proj.cfg["style"]
    kit = st.get("kit")
    pal = ({k: tuple(v) for k, v in kit["colors"].items()} if kit
           else G.PALETTES.get(st.get("palette", "neon"), G.PALETTES["neon"]))
    try:
        mc = G.mood_colors(st.get("mood"), st.get("overrides"), base=pal)
    except ValueError as e:
        errs.append(f"style: {e}")
        return
    if (st.get("mood") or st.get("overrides")) and st.get("palette") != "lab" and not kit:
        warns.append("style.mood/overrides рассчитаны на palette: lab")
    near = lambda a, b: sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5 < 48
    for k in ("true", "half", "myth", "noev", "accent"):
        if k in pal and near(mc["accent2"], pal[k]):
            what = "бренд-цианом accent" if k == "accent" else f"цветом вердикта {k}"
            errs.append(f"style: accent2 #{'%02X%02X%02X' % tuple(mc['accent2'])} совпадает с {what} "
                        f"#{'%02X%02X%02X' % tuple(pal[k])} — выберите другое настроение или overrides.accent2")
    for ch, d in proj.chapters:
        try:
            G.chapter_glow(d.get("glow"))
        except ValueError as e:
            errs.append(f"{ch}: {e}")


def triggers(proj, errs, warns):
    """Триггеры at: (B8) — по словам озвучки, только если timeline.json актуален (иначе слова старые)."""
    from .packs import REGISTRY
    from .packs.lab import trigger_errors
    from .timing import source_hash
    p = proj.build / "timeline.json"
    if not p.exists():
        return
    tl = json.loads(p.read_text(encoding="utf-8"))
    if tl.get("src") != source_hash(proj):
        warns.append("timeline.json устарел — триггеры at: проверит voice")
        return
    errs += trigger_errors(tl["scenes"], REGISTRY)

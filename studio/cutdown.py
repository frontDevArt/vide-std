"""Нарезка (ROADMAP B4): длинный ролик → короткие ролики под площадку (Shorts, TikTok, Reels).

Проект-нарезка — обычный проект студии с ключом `cutdown: {source: <slug исходника>}` в project.yaml:
- настройки (голос, темп, стиль, музыка, паузы…) — из project.yaml исходника, поверх — свои (площадка, формат, главы);
- сцена в script/*.yaml — ссылка `from: ch02/s05` (или `from: s05` — глава та же) на сцену исходника, остальные
  ключи сцены — поверх неё (`params` сливаются); новые сцены (крючок, CTA) — как обычно, текстом;
- озвучка — кэш исходника (`build/tts/` исходника): у строк сцены-ссылки контекст соседних строк (ElevenLabs
  previous_text/next_text) — как в исходнике (`_ctx`), ключ кэша совпадает, синтез не нужен;
- подсветка главы (`glow`) — у главы с тем же id в исходнике; шапка `chrome` (lab) — накопленная к первой сцене-ссылке;
- шаблоны проекта — копией `templates/` исходника (как у `demo`).

`python -m studio cutdown <исходник> --to youtube-shorts --count 3` выбирает отрезки (`candidates`): подряд идущие
сцены одной главы с крючком (цифра, вопрос) и развязкой (вердикт, цифра), без карточек глав и призывов исходника,
в пределах длительности площадки, — и пишет проекты `<исходник>-cut-N/`. Claude смотрит список, при нужде
выбирает сам (`--pick ch02/s05-s08`) и дописывает строку крючка в начало и CTA в конец (заготовки — в комментариях).
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import imagegen as IG
from .cutrefs import read_yaml  # загрузка проекта-нарезки (ссылки from:) — studio/cutrefs.py

CTA_WORDS = ("subscribe", "comment", "подпиш", "коммент")  # призывы исходника — не в нарезку (у нарезки свой CTA)
NUMBER_TEMPLATES = ("number", "counter", "hero")  # fd_number, lab_full_number, counter, lab_hero_stack…


# ---------------------------------------------------------------- выбор отрезков
@dataclass
class Scene:
    chapter: str
    id: str
    template: str
    dur: float
    text: str
    score: float = 0.0
    tags: list = field(default_factory=list)
    skip: str = ""  # почему сцена не годится для нарезки
    n: int = 0      # номер в ролике


@dataclass
class Cut:
    scenes: list
    score: float
    label: str = ""  # как задан в --pick (`ch02/s13-s15,s17`); пусто — по первой и последней сцене

    @property
    def dur(self) -> float:
        return sum(s.dur for s in self.scenes)

    @property
    def chapter(self) -> str:
        return self.scenes[0].chapter

    @property
    def span(self) -> str:
        if self.label:
            return self.label
        a, b = self.scenes[0].id, self.scenes[-1].id
        return f"{self.chapter}/{a}" + (f"-{b}" if b != a else "")


def _lines(sc) -> list[str]:
    from .textutil import display_text, line_text
    return [display_text(line_text(l)) for l in sc.get("lines") or []]


def rate(sc: dict) -> tuple[float, list, str]:
    """(очки, метки, причина пропуска) сцены: развязка и крючок — очки; карточка главы и призыв — пропуск."""
    tp = str(IG.template_of(sc))
    p = sc.get("params") or {}
    text = " ".join(_lines(sc))
    if "chapter" in tp:
        return 0, [], "карточка главы"
    if tp in ("outro", "core.outro"):
        return 0, [], "концовка"
    if any(w in text.lower() for w in CTA_WORDS):
        return 0, [], "призыв исходника"
    score, tags = 0.0, []
    if "verdict" in tp or p.get("verdict"):
        score += 3; tags.append("вердикт")
    if any(w in tp for w in NUMBER_TEMPLATES) or p.get("hero") or p.get("number"):
        score += 2; tags.append("цифра")
    if "?" in text:
        score += 1; tags.append("вопрос")
    if p.get("source"):
        score += 0.5; tags.append("источник")
    return score, tags, ""


def scene_table(src) -> tuple[list, str]:
    """([Scene] исходника по порядку, откуда длительности): timeline.json исходника, иначе оценка по темпу голоса."""
    from .textutil import line_text, word_count
    from .timing import source_hash
    durs, how = {}, ""
    for o in src.targets():
        tlp = o.build / "timeline.json"
        if tlp.exists():
            tl = json.loads(tlp.read_text(encoding="utf-8"))
            if tl.get("src") == source_hash(o):
                durs = {(s["chapter"], s["id"]): s["dur"] for s in tl["scenes"]}
                how = f"timeline.json {o.out or ''}".strip()
                break
    if not durs:
        from .calibration import wpm
        pace, why = wpm(src)
        how = f"оценка по темпу {pace:g} слов/мин ({why}) — точнее после voice исходника"
    P = src.cfg["pauses"]
    out = []
    for ch, data in src.chapters:
        for sc in data.get("scenes") or []:
            d = durs.get((ch, sc.get("id")))
            if d is None:
                lines = sc.get("lines") or []
                words = sum(word_count(line_text(l)) for l in lines)
                d = words / pace * 60 + P["sentence"] * max(0, len(lines) - 1) + P["scene"] + float(sc.get("hold", 0))
                d = max(d, float(sc.get("min_duration", 0)))
            score, tags, skip = rate(sc)
            text = _lines(sc)
            out.append(Scene(ch, str(sc.get("id")), str(IG.template_of(sc)), round(d, 2),
                             text[0] if text else "", score, tags, skip, len(out)))
    return out, how


def candidates(scenes: list, lo: float, hi: float, target: float) -> list:
    """Отрезки: подряд идущие сцены одной главы без пропусков, длительность [lo, hi]; лучшие — первыми.
    Очки: сумма очков сцен + крючок в первой сцене + развязка в последней − удалённость от target."""
    out = []
    for i, a in enumerate(scenes):
        if a.skip:
            continue
        for j in range(i, len(scenes)):
            b = scenes[j]
            if b.skip or b.chapter != a.chapter:
                break
            cut = Cut(scenes[i:j + 1], 0.0)
            if cut.dur > hi:
                break
            if cut.dur < lo:
                continue
            hook = 1.5 if {"цифра", "вопрос"} & set(a.tags) else 0
            payoff = 1.5 if {"вердикт", "цифра"} & set(b.tags) else 0
            cut.score = round(sum(s.score for s in cut.scenes) + hook + payoff - abs(cut.dur - target) / 15, 2)
            out.append(cut)
    return sorted(out, key=lambda c: (-c.score, c.chapter, c.scenes[0].id))


def pick(cands: list, count: int) -> list:
    """Лучшие `count` отрезков без общих сцен, по порядку в ролике."""
    chosen, used = [], set()
    for c in cands:
        keys = {(s.chapter, s.id) for s in c.scenes}
        if keys & used:
            continue
        chosen.append(c); used |= keys
        if len(chosen) == count:
            break
    return sorted(chosen, key=lambda c: c.scenes[0].n)


def parse_pick(spec: str, scenes: list) -> Cut:
    """`ch02/s05-s08`, `ch02/s05` или с пропуском `ch02/s13-s15,s17` → Cut по сценам исходника (одна глава)."""
    m = re.match(r"^([\w-]+)/(\w+(?:-\w+)?(?:,\w+(?:-\w+)?)*)$", spec.strip())
    if not m:
        raise SystemExit(f"--pick {spec!r}: нужно chNN/sNN, chNN/sNN-sMM или chNN/sNN-sMM,sKK")
    ch = m[1]
    ids = [s for s in scenes if s.chapter == ch]
    names = [s.id for s in ids]
    out = []
    for part in m[2].split(","):
        a, _, b = part.partition("-")
        b = b or a
        for x in (a, b):
            if x not in names:
                raise SystemExit(f"--pick {spec}: нет сцены {ch}/{x}")
        i, j = names.index(a), names.index(b)
        if j < i or (out and i <= out[-1].n - ids[0].n):
            raise SystemExit(f"--pick {spec}: сцены не по порядку")
        out += ids[i:j + 1]
    return Cut(out, 0.0, spec.strip() if "," in spec else "")


# ---------------------------------------------------------------- запись проектов
HOOK = """\
  # Крючок (необязательно, Claude): одна строка, которая цепляет без контекста ролика. Новая строка — новый синтез
  # (у elevenlabs — платно, `voice` покажет символы). Раскомментируйте и поставьте первой сценой:
  # - id: hook
  #   template: {tp}
  #   lines:
  #     - "…"
"""
CTA = """\
  # CTA в конце (необязательно, Claude): «полная версия — на канале» и т. п. Раскомментируйте:
  # - id: cta
  #   template: {tp}
  #   lines:
  #     - "…"
"""


def write(src, cut: Cut, dst: Path, platform, rate_fixed=None, n: int = 1) -> Path:
    """Проект-нарезка `dst` по отрезку `cut` исходника `src` (Project) для площадки `platform`."""
    (dst / "script").mkdir(parents=True, exist_ok=True)
    src_user = read_yaml(src.root / "project.yaml")
    title = src_user.get("title") or src.slug
    lines = [f"# Нарезка (ROADMAP B4) из {src.slug}: {cut.span}, ≈ {cut.dur:.0f} c. Сцены — ссылки на исходник,",
             "# настройки (голос, стиль, музыка) — из его project.yaml, озвучка — его кэш build/tts/.",
             yaml.safe_dump({"title": f"{title} — cut {n}", "cutdown": {"source": src.slug},
                             "platform": platform.id, "format": platform.formats[0],
                             "chapters": [cut.chapter]}, allow_unicode=True, sort_keys=False).rstrip()]
    if rate_fixed is not None:  # темп исходника подобран (auto): у нарезки — числом, иначе кэш не совпадёт
        lines.append(f"tts: {{rate: {rate_fixed:g}}}   # темп исходника (у него auto): ключ кэша озвучки")
    (dst / "project.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    tp = cut.scenes[0].template if cut.scenes[0].template.startswith("lab") else "statement"
    tp = "lab_hero_stack" if tp.startswith("lab") else tp
    body = [f"# {cut.span} из {src.slug}. `from:` — сцена исходника; свои ключи рядом с from — поверх неё.",
            f"chapter: {cut.chapter}", "scenes:", HOOK.format(tp=tp).rstrip()]
    for s in cut.scenes:
        body.append(f"  - from: {s.id}" + (f"   # {s.text[:60]}" if s.text else ""))
    body.append(CTA.format(tp=tp).rstrip())
    (dst / "script" / f"{cut.chapter}.yaml").write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")
    if (src.root / "templates").exists():
        shutil.copytree(src.root / "templates", dst / "templates", dirs_exist_ok=True)
    return dst

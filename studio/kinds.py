"""Типы роликов (ROADMAP C1): `kind` в project.yaml — объяснялка, крючок, промо, ролик под музыку, слайдшоу…

Тип задаёт голос (озвученный — правило «нет голоса — стоп»; без голоса — `tts.backend: none`, текст только в кадре),
пределы длительности, обязательные поля `brief:` (файлы из брифа — фаза «Материалы» в status), проверки validate и QA.
Без `kind` проект — `explainer`, как до C1; в cfg ключ не попадает (ключ кэша рендера старых проектов не меняется).
`needs` — чего ещё нет в движке (задача ROADMAP): тип принимается, validate предупреждает, демо — вместе с той задачей.
Фото, видео, запись экрана и звук исходника — шаблоны `media.*` и ассеты проекта (ROADMAP C2, studio/assets.py).
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass

DEFAULT = "explainer"


@dataclass(frozen=True)
class Kind:
    id: str
    title: str
    voice: bool = True          # False — без голоса: tts.backend: none, сцены без lines (длительность — min_duration)
    duration: tuple | None = None  # (мин, макс) секунд итога
    exact: bool = False         # нужен target_duration (точная длительность)
    brief: tuple = ()           # обязательные поля brief:
    files: tuple = ()           # поля brief — пути к файлам от папки проекта (строка или список)
    music: bool = False         # музыка — содержание ролика: music.enabled обязателен, QA — «музыка звучит»
    default_duration: float | None = None  # `new --kind` без --duration (для exact)
    source_audio: bool = False  # речь — звук исходника (clip): QA — «Звук исходника звучит»
    beat: bool = False          # склейки в долю трека (ROADMAP C3): music.sync, QA — «Склейки в долю»
    needs: str = ""             # недостающий слой движка (задача ROADMAP)
    hint: str = ""              # как строить: шаблоны, структура


KINDS = {k.id: k for k in (
    Kind("explainer", "объяснялка: диктор + анимация + субтитры",
         hint="любые шаблоны; длительность по речи или точная; смена картинки каждые 6–8 с"),
    Kind("short-hook", "короткий ролик с крючком (Shorts, TikTok, Reels)", duration=(15, 60), exact=True,
         brief=("hook",), default_duration=30,
         hint="крючок (brief.hook) — первой строкой первой сцены, одна мысль, финал-призыв"),
    Kind("promo", "промо продукта: продукт, цена, призыв", duration=(6, 60), exact=True,
         brief=("product", "price", "cta"), default_duration=15,
         hint="logo_sting / title → media.product_card (фото, цена) или price_tag → outro с brief.cta; "
              "фото и логотип — assets/ + assets.yaml"),
    Kind("music", "кинетическая типографика под трек, без голоса", voice=False, duration=(10, 90), exact=True,
         music=True, default_duration=20, beat=True,
         hint="сцены без lines, длительность — min_duration (склейка — в ближайшую долю), текст в params; "
              "music.sync: beat | bar, music.file — свой трек (иначе ритм-трек кодом, music.bpm); "
              "first_beat / at_beat / at: N — элементы в долю"),
    Kind("slideshow", "фото + подписи + музыка, без голоса", voice=False, duration=(10, 180), music=True,
         files=("photos",),
         hint="brief.photos — файлы в assets/ (+ assets.yaml); сцена — media.image на фото с подписью (caption), "
              "Ken Burns, min_duration 3–5 c"),
    Kind("listicle", "топ-N: пункты по порядку", brief=("count",),
         hint="вступление, затем сцены пунктов с item: 1…N (по возрастанию или обратный отсчёт), brief.count = N"),
    Kind("data-story", "история в цифрах: графики из CSV", files=("data",),
         needs="C4 (шаблон chart: столбики, линия, круг из данных)",
         hint="brief.data — CSV в assets/; counter / number для отдельных чисел уже есть"),
    Kind("tutorial", "туториал: запись экрана + выноски + зум", files=("recording",),
         hint="brief.recording — запись экрана в assets/; сцены media.screen с одним файлом: start — с какой "
              "секунды, zoom / callouts / clicks — по битам озвучки"),
    Kind("clip", "кусок подкаста или интервью: звук/видео + волна + караоке", voice=False, files=("source",),
         source_audio=True,
         hint="brief.source — аудио или видео исходника в assets/; сцены media.clip (start — с какой секунды, "
              "min_duration — длина куска, captions — расшифровка); речь — из исходника, не синтез"),
)}


def of(cfg: dict) -> Kind:
    """Тип проекта; неизвестный — explainer (validate скажет ❌)."""
    return KINDS.get(cfg.get("kind") or DEFAULT, KINDS[DEFAULT])


def _scenes(proj):
    return [(ch, s) for ch, d in proj.chapters for s in d.get("scenes") or []]


def _length(proj, est):
    """Длительность для проверки до voice: target_duration, иначе речь (оценка) или сумма min_duration."""
    tgt = proj.cfg.get("target_duration")
    if tgt:
        return float(tgt)
    floor = sum(float(s.get("min_duration", 0)) + float(s.get("hold", 0)) for _, s in _scenes(proj))
    return max(est, floor)


def _files(proj, field):
    v = (proj.cfg.get("brief") or {}).get(field)
    return [v] if isinstance(v, str) else list(v or [])


def missing_files(proj) -> list[str]:
    """Файлы брифа (photos, data, recording, source), которых нет в папке проекта."""
    k = of(proj.cfg)
    return [f for fld in k.files for f in _files(proj, fld) if not (proj.root / f).exists()]


def brief_missing(proj) -> list[str]:
    """Обязательные поля brief: типа, которые не заполнены."""
    k = of(proj.cfg)
    b = proj.cfg.get("brief") or {}
    return [f for f in k.brief + k.files if b.get(f) in (None, "", [], "TODO")]


def issues(proj, est: float) -> tuple[list[str], list[str]]:
    """validate: (ошибки, предупреждения) по типу ролика. est — оценка речи, c."""
    errs, warns = [], []
    name = proj.cfg.get("kind") or DEFAULT
    if name not in KINDS:
        near = difflib.get_close_matches(str(name), list(KINDS), n=1)
        errs.append(f"kind: нет типа '{name}'" + (f" — может, {near[0]}?" if near else "")
                    + f" (есть: {', '.join(KINDS)})")
        return errs, warns
    k = KINDS[name]
    backend = proj.cfg["tts"]["backend"]
    voiced = [f"{ch}/{s.get('id')}" for ch, s in _scenes(proj) if s.get("lines")]
    if k.voice and backend == "none":
        errs.append(f"kind: {k.id} — озвученный тип, а tts.backend: none (без голоса). Нет голоса — стоп: "
                    f"поставьте голос (python -m studio doctor) или выберите тип без голоса (music, slideshow)")
    if not k.voice:
        if voiced:
            errs.append(f"kind: {k.id} — без голоса, а у сцен есть lines ({', '.join(voiced[:4])}): текст в кадре — "
                        f"в params, длительность — min_duration")
        if backend != "none" and k.id != "clip":
            warns.append(f"kind: {k.id} — без голоса: укажите tts.backend: none (сейчас {backend})")
    if k.music and not proj.cfg["music"].get("enabled", True):
        errs.append(f"kind: {k.id} — музыка и есть ролик: music.enabled: true")
    if k.beat and not proj.cfg["music"].get("sync"):
        warns.append(f"kind: {k.id} — склейки не привязаны к долям: music.sync: beat (qa проверяет ±1 кадр от доли)")
    if k.exact and not proj.cfg.get("target_duration"):
        errs.append(f"kind: {k.id} — нужна точная длительность: target_duration")
    if k.duration:
        lo, hi = k.duration
        n = _length(proj, est)
        if n and not lo <= n <= hi:
            (errs if proj.cfg.get("target_duration") else warns).append(
                f"kind: {k.id} — длительность {n:.0f} c вне {lo}–{hi} c")
    for f in brief_missing(proj):
        errs.append(f"brief.{f}: обязательное поле для типа {k.id}")
    for f in missing_files(proj):
        errs.append(f"brief: файла {f} нет в папке проекта")
    if k.needs:
        warns.append(f"kind: {k.id} — шаблонов для него ещё нет в студии: {k.needs}; пока только кодовая графика")
    if k.id == "listicle":
        errs += _listicle(proj)
    return errs, warns


def _listicle(proj) -> list[str]:
    try:
        n = int((proj.cfg.get("brief") or {}).get("count"))
    except (TypeError, ValueError):
        return []  # brief_missing уже сказал
    items = [s.get("item") for _, s in _scenes(proj) if s.get("item") is not None]
    if sorted(items) != list(range(1, n + 1)) or items not in (sorted(items), sorted(items, reverse=True)):
        return [f"kind: listicle — пункты item: {items or 'нет'}, нужно 1…{n} по порядку (brief.count = {n})"]
    return []


def qa(proj, tl: dict, dur: float, music_db: float | None, final=None) -> list[tuple[bool, str, str]]:
    """Проверки QA по типу: [(ok, имя, подробно)]. music_db — средний уровень итога, dB (для роликов без голоса);
    final — готовый файл: склейки в долю (тип music или music.sync, ROADMAP C3) — по долям в его звуке."""
    k = of(proj.cfg)
    out = []
    if k.duration:
        lo, hi = k.duration
        out.append((lo - 0.02 <= dur <= hi + 0.02, f"Тип {k.id}: длительность {lo}–{hi} c", f"{dur:.2f} c"))
    if not k.voice:
        said = sum(len(s["lines"]) for s in tl["scenes"])
        out.append((said == 0, f"Тип {k.id}: без голоса", "речи нет" if not said else f"строк речи: {said}"))
    if k.music:
        out.append((music_db is not None and music_db > -35, "Музыка звучит",
                    f"средний уровень {music_db} dB" if music_db is not None else "тишина"))
    if k.source_audio:
        out.append((music_db is not None and music_db > -35, "Звук исходника звучит",
                    f"средний уровень {music_db} dB" if music_db is not None else "тишина"))
    from . import music as M
    if final is not None and (k.beat or M.sync_mode(proj)):
        r = M.qa_sync(proj, tl, final)
        if r:
            out.append((r[0], "Склейки в долю трека", r[1]))
    return out

"""Профили площадок (ROADMAP B1): кадр, fps, пределы длительности, безопасные зоны, громкость, субтитры, кодек, обложка.

Проект выбирает площадку ключом `platform:` в project.yaml; `validate` сверяет с ней формат и оценку длительности,
`qa` — готовый файл (`checks`), `stills`/`qa` — вёрстку (безопасная зона площадки, studio/safezone.py).
`python -m studio platforms` — таблица профилей.

Цифры сверены по документации площадок 2026-10-23 (ссылки — `source` у профиля). Где площадка пикселей не публикует
(интерфейс TikTok и Shorts), зона — оценка по шаблонам площадки и сторонним разборам, это сказано в `note`.
Картину профиль меняет только полями сетки вёрстки (`layout_zone`, ROADMAP B2) — они в ключе сцены, поэтому модуль
вне хэша кода рендера: правка профиля пересчитывает только сцены, чьи поля изменились.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass

CHECKED = "2026-10-23"
FPS_ANY = (24, 25, 30, 48, 50, 60)  # частоты, которые принимают все площадки; студия рендерит делители 48000
YT_ENCODING = "https://support.google.com/youtube/answer/1722171"


@dataclass(frozen=True)
class Safe:
    """Поля, свободные от интерфейса площадки, — доли стороны кадра."""
    top: float = 0.04
    bottom: float = 0.04
    left: float = 0.04
    right: float = 0.04


@dataclass(frozen=True)
class UI:
    """Прямоугольник интерфейса внутри полей (x0, y0, x1, y1 — доли кадра), например колонка кнопок справа."""
    name: str
    box: tuple


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    formats: tuple            # форматы проекта (project.FORMATS); первый — основной; portrait = 4:5
    min_dur: float | None     # с; None — без нижнего предела
    max_dur: float | None     # с; None — без предела для студии
    safe: Safe = Safe()
    ui: tuple = ()            # UI(...) поверх полей
    fps: tuple = FPS_ANY
    lufs: float = -14.0       # площадка нормирует к этому уровню: громче — приглушит, тише — не поднимет
    true_peak: float = -1.0   # dBTP
    burn_subs: bool = True    # вшитые субтитры: смотрят без звука
    vcodec: str = "h264"
    acodec: str = "aac"
    min_kbps: int | None = None  # нижний предел видеобитрейта, где площадка его требует
    kbps: int = 8000          # рекомендованный видеобитрейт 1080p, кбит/с (ориентир, не предел)
    cover: tuple | None = None   # обложка (Ш, В) px; None — кадр из ролика
    source: str = ""
    note: str = ""
    # пакет к выходу (ROADMAP B5, studio/package.py): пределы текста, главы, хэштеги, отметка ИИ-контента
    title_max: int | None = None   # символов в названии; None — названия нет (подпись) или не проверяем
    text_max: int | None = None    # символов в описании / подписи
    chapters: bool = False         # главы таймкодами в описании
    tags_max: int = 0              # хэштегов в подписи; 0 — не ставим
    cover_mb: float | None = None  # предел файла обложки, МБ
    ai: str = ""                   # отметка «синтетический / ИИ-контент» при загрузке: где и когда
    ai_voice: bool = False         # реалистичный синтетический голос сам по себе требует этой отметки


ASPECT = {"vertical": "9:16", "horizontal": "16:9", "square": "1:1", "portrait": "4:5"}

_VERT_UI = Safe(top=0.08, bottom=0.20, left=0.05, right=0.05)  # TikTok / Shorts: вкладки сверху, подпись и меню снизу
_ADS = ("horizontal", "vertical", "square")
# Отметка ИИ-контента (сверено 2026-10-23): YouTube — support.google.com/youtube/answer/14328491, TikTok — правила
# сообщества (реалистичный ИИ-контент — переключатель «AI-generated content»), Meta — help.instagram.com/761121959519495
# Нужна ли отметка у конкретного ролика — package.ai_label (правила там); здесь — где её ставить и общий принцип.
_AI_YT = ("YouTube Studio → «Attributes» → «AI use» (раньше «Altered or synthetic content»): «Yes» — реалистичное, что "
          "можно принять за настоящее (реальный человек говорит или делает то, чего не было; изменённая съёмка "
          "реального места или события; реалистичная сцена, которой не было; ИИ-музыка как основа ролика); «No» — "
          "нереалистичная анимация, синтетический диктор без подражания реальному человеку, ИИ для сценария, названия, "
          "обложки, субтитров. Ответить явно в обоих случаях. Источник: support.google.com/youtube/answer/14328491")
_AI_TT = ("При загрузке: «More options» → «AI-generated content» — включить для реалистичного ИИ-контента "
          "(в т. ч. реалистичный синтетический голос). Неотмеченный реалистичный ИИ-контент TikTok может удалить. "
          "Источник: правила сообщества TikTok, раздел «Edited media and AI-generated content»")
_AI_META = ("При публикации: «Advanced settings» → «Add AI label» (AI info) — обязательно для фотореалистичного видео "
            "и реалистично звучащего ИИ-аудио (пример Meta: Reels с реалистичным ИИ-закадром). "
            "Источник: help.instagram.com/761121959519495")
_ADS_SRC = ("Google Ads Help, форматы видеорекламы YouTube (bumper ≤ 6 c, non-skippable ≤ 15–30 c); "
            "https://ads.tiktok.com/help/article/tiktok-reservation-in-feed-ads-reach-frequency (5–60 c, ≥ 2500 кбит/с)")

PLATFORMS: dict[str, Platform] = {p.id: p for p in (
    Platform("youtube", "YouTube", ("horizontal",), None, None, safe=Safe(0.04, 0.04, 0.04, 0.04),
             burn_subs=False, cover=(1280, 720), source=YT_ENCODING,
             title_max=100, text_max=5000, chapters=True, cover_mb=2, ai=_AI_YT,
             note="H.264 High, AAC-LC 48 кГц, 8 Мбит/с для 1080p SDR (12 — для 48–60 fps); "
                  "субтитры — файлом .srt/.vtt; громкость нормируется к ≈ −14 LUFS (только вниз). "
                  "Ролики длиннее 15 мин — только с подтверждённым аккаунтом."),
    Platform("youtube-shorts", "YouTube Shorts", ("vertical", "square"), None, 180, safe=_VERT_UI,
             ui=(UI("колонка кнопок справа", (0.86, 0.45, 1.0, 0.85)),),
             title_max=100, text_max=5000, tags_max=3, ai=_AI_YT,
             source="https://support.google.com/youtube/answer/15424877",
             note="Short — квадрат или вертикаль до 3 мин (с 15.10.2024). Пикселей интерфейса YouTube не публикует — "
                  "зона: оценка (вкладки сверху, название и канал снизу, кнопки справа)."),
    Platform("tiktok", "TikTok", ("vertical",), None, 600, safe=_VERT_UI,
             ui=(UI("колонка кнопок справа", (0.86, 0.35, 1.0, 0.80)),),
             text_max=2200, tags_max=5, ai=_AI_TT, ai_voice=True,
             source="https://ads.tiktok.com/help/article/tiktok-reservation-topview",
             note="1080×1920; в приложении — до 10 мин (загрузка до 60 мин есть не у всех аккаунтов). "
                  "Пикселей интерфейса TikTok не публикует (шаблоны и Ad Preview Tool) — зона: оценка "
                  "(≈ 120–200 px сверху, 250–440 px снизу, кнопки справа)."),
    Platform("instagram-reels", "Instagram Reels", ("vertical",), None, 180,
             safe=Safe(top=0.14, bottom=0.35, left=0.06, right=0.06), text_max=2200, tags_max=5, ai=_AI_META, ai_voice=True,
             source="https://www.facebook.com/business/ads-guide (Reels: поля 14 % / 35 % / 6 %)",
             note="Reels до 3 мин (с 20.01.2025). Зона — рекомендация Meta для 9:16: верх 14 %, низ 35 %, бока 6 % "
                  "(кнопки и подпись — в нижних 35 %). Обложка в сетке профиля режется до 3:4."),
    Platform("instagram-feed", "Instagram, лента 4:5", ("portrait", "square"), 3, 3600,
             safe=Safe(top=0.04, bottom=0.075, left=0.09, right=0.09), burn_subs=True,
             text_max=2200, tags_max=5, ai=_AI_META, ai_voice=True,
             source="https://www.facebook.com/business/ads-guide (лента: 4:5 1080×1350, ≈ 100 px снизу и по бокам)",
             note="Основной кадр — 4:5 1080×1350, 1:1 тоже принимается."),
    Platform("square", "Квадрат 1:1 (лента, мессенджеры)", ("square",), None, None,
             safe=Safe(0.05, 0.05, 0.05, 0.05), source=YT_ENCODING,
             note="Общий профиль квадрата: поля 5 %, громкость −14 LUFS."),
    Platform("ad-6", "Реклама 6 с (bumper)", _ADS, None, 6, safe=Safe(0.05, 0.05, 0.05, 0.05), source=_ADS_SRC,
             note="YouTube bumper: до 6 с, без пропуска. Формат — любой из студии, кадр по формату проекта."),
    Platform("ad-15", "Реклама 15 с", _ADS, 5, 15, safe=Safe(0.05, 0.05, 0.05, 0.05), min_kbps=2500,
             source=_ADS_SRC,
             note="YouTube non-skippable — до 15 с (в части стран до 30); TikTok in-feed: 5–60 с, "
                  "рекомендация 9–15 с, видео ≥ 2500 кбит/с."),
    Platform("ad-30", "Реклама 30 с", _ADS, 5, 30, safe=Safe(0.05, 0.05, 0.05, 0.05), min_kbps=2500,
             source=_ADS_SRC,
             note="YouTube in-stream до 30 с, TikTok in-feed 5–60 с, видео ≥ 2500 кбит/с."),
)}


def get(pid: str) -> Platform:
    if pid not in PLATFORMS:
        near = difflib.get_close_matches(str(pid), list(PLATFORMS), n=2, cutoff=0.5)
        raise KeyError(f"нет площадки {pid!r}" + (f" — может быть, {' / '.join(near)}?" if near else "")
                       + f" (есть: {', '.join(PLATFORMS)})")
    return PLATFORMS[pid]


def of(proj) -> Platform | None:
    """Площадка проекта (`platform:` в project.yaml) или None. Неизвестную ловит validate, здесь — None."""
    pid = proj.cfg.get("platform")
    return PLATFORMS.get(pid) if pid else None


# площадка, по зоне которой верстается проект без `platform:` (ROADMAP B2): 9:16 — почти всегда TikTok/Shorts/Reels
LAYOUT = {"horizontal": "youtube", "vertical": "tiktok", "portrait": "instagram-feed", "square": "square"}


def layout_zone(cfg: dict) -> dict:
    """Поля сетки вёрстки шаблонов {top, bottom, left, right} — доли стороны (`Template.safe`, ROADMAP B2).
    Площадка проекта, без неё — площадка формата из LAYOUT; не меньше `qa.safe_margin`. Интерфейс площадки
    (колонка кнопок справа) входит в боковые поля, и они симметричны: вёрстка по центру не заезжает под кнопки.
    Результат — в ключе сцены (render._prepare), поэтому модуль вне хэша кода рендера."""
    base = float((cfg.get("qa") or {}).get("safe_margin", 0.04))
    p = PLATFORMS.get(cfg.get("platform") or "") or PLATFORMS[LAYOUT.get(cfg.get("format"), "youtube")]
    side = max([p.safe.left, p.safe.right] + [1 - u.box[0] for u in p.ui])
    return {"top": max(base, p.safe.top), "bottom": max(base, p.safe.bottom),
            "left": max(base, side), "right": max(base, side)}


def size(fmt: str) -> tuple | None:
    from .config import FORMATS
    return FORMATS.get(fmt)


def _dur(p: Platform) -> str:
    def s(x):
        return f"{x / 60:g} мин" if x >= 60 else f"{x:g} с"
    if p.min_dur is None and p.max_dur is None:
        return "—"
    if p.min_dur is None:
        return f"≤ {s(p.max_dur)}"
    return f"{s(p.min_dur)}–{s(p.max_dur)}"


def _zone(p: Platform) -> str:
    z = p.safe
    pct = lambda x: f"{x * 100:g}"  # noqa: E731
    out = f"{pct(z.top)}/{pct(z.bottom)}/{pct(z.left)}/{pct(z.right)} %"
    return out + (" + кнопки справа" if p.ui else "")


def table() -> list[list[str]]:
    """Строки таблицы `platforms`: первая — заголовок."""
    rows = [["площадка", "кадр", "fps", "длительность", "поля в/н/л/п", "LUFS", "субтитры", "видео", "обложка"]]
    for p in PLATFORMS.values():
        frames = []
        for f in p.formats:
            w, h = size(f)
            frames.append(f"{ASPECT[f]} {w}×{h}")
        rows.append([p.id, ", ".join(frames), "/".join(map(str, p.fps)), _dur(p), _zone(p), f"{p.lufs:g}",
                     "вшитые" if p.burn_subs else "файлом", f"{p.vcodec} ~{p.kbps // 1000} Мбит/с"
                     + (f", ≥ {p.min_kbps}" if p.min_kbps else ""),
                     f"{p.cover[0]}×{p.cover[1]}" if p.cover else "кадр"])
    return rows


# --- проверки ------------------------------------------------------------------------------------------------------

def plan_issues(proj, est: float | None = None) -> tuple[list[str], list[str]]:
    """Для validate: (ошибки, предупреждения) — площадка известна, формат проекта ей подходит, оценка речи в пределах."""
    pid = proj.cfg.get("platform")
    if not pid:
        return [], []
    try:
        p = get(pid)
    except KeyError as e:
        return [f"platform: {e.args[0]}"], []
    errs, warns = [], []
    fmt = proj.cfg["format"]
    if fmt not in p.formats:
        errs.append(f"platform: {pid} — формат {fmt} не подходит, нужен {' или '.join(p.formats)}")
    tgt = proj.cfg.get("target_duration")
    d = tgt or est
    if d and p.max_dur and d > p.max_dur:
        warns.append(f"platform: {pid} — длительность {d:.0f} c больше предела площадки {p.max_dur:g} c")
    if tgt and p.min_dur and tgt < p.min_dur:
        warns.append(f"platform: {pid} — длительность {tgt:g} c меньше минимума площадки {p.min_dur:g} c")
    return errs, warns


def checks(proj, info: dict, dur: float, lufs: float | None, peak: float | None, add, warn):
    """Для qa: готовый файл по профилю площадки. add(ok, имя, подробности) — ❌ при нарушении, warn(статус, …) — ⚠️."""
    p = of(proj)
    if not p:
        return
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    w, h = v["width"], v["height"]
    ok_size = any(size(f) == (w, h) for f in p.formats)
    add(ok_size, f"Площадка {p.id}: кадр", f"{w}×{h} (нужно {', '.join(ASPECT[f] for f in p.formats)})")
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    add(den == 1 and num in p.fps, f"Площадка {p.id}: FPS", f"{v['r_frame_rate']} (принимает {'/'.join(map(str, p.fps))})")
    lo = p.min_dur or 0
    hi = p.max_dur or float("inf")
    add(lo <= dur <= hi + 1e-3, f"Площадка {p.id}: длительность", f"{dur:.2f} c (предел {_dur(p)})")
    codec_ok = v["codec_name"] == p.vcodec and (not a or a[0]["codec_name"] == p.acodec)
    add(codec_ok, f"Площадка {p.id}: кодеки", f"{v['codec_name']}/{a[0]['codec_name'] if a else '—'} "
                                              f"(нужно {p.vcodec}/{p.acodec})")
    if p.min_kbps:
        size_b = float(info["format"].get("size") or 0)
        kbps = size_b * 8 / 1000 / dur if dur else 0
        warn("PASS" if kbps >= p.min_kbps else "WARN", f"Площадка {p.id}: битрейт",
             f"≈ {kbps:.0f} кбит/с (площадка требует ≥ {p.min_kbps})")
    if lufs is not None:
        loud = lufs > p.lufs + 1 or (peak is not None and peak > p.true_peak)
        warn("WARN" if loud else "PASS", f"Площадка {p.id}: громкость",
             f"{lufs:.1f} LUFS, пик {peak:.1f} dBFS (площадка нормирует к {p.lufs:g} LUFS, пик ≤ {p.true_peak:g})"
             + (" — громче: площадка приглушит" if loud else ""))
    if p.burn_subs and not proj.cfg["subtitles"].get("enabled", True):
        warn("WARN", f"Площадка {p.id}: субтитры", "площадка ждёт вшитых субтитров (смотрят без звука), а они выключены")

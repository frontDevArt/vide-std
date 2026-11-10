"""Пакет к выходу (ROADMAP B5): рядом с MP4 в output/<slug>/ — всё для ручной загрузки на площадку.

`python -m studio package <проект> [--out <выход>]` (и последний шаг `all`) пишет для каждого выхода:
`<выход>.cover.jpg` (кадр ролика + заголовок и плашка вердикта по шаблону обложки бренд-кита `brand/cover.yaml`),
`<выход>.description.md` (название, описание, главы YouTube из таймлайна, источники, хэштеги — блоком для копирования)
и `<выход>.checklist.md` (что проверить перед публикацией, с отметкой ИИ-контента там, где площадка её требует).
MP4 и `.srt`/`.vtt` там уже лежат (assemble); у проекта без `deliverables` их копирует сюда же `package`.

Входы — ключ `package:` в project.yaml (вне ключа рендера: правка текста ничего не перерисовывает), пределы
площадок — профили studio/platforms.py. Источники: цитаты `source: {text: "Автор, год · …"}` из сцен сопоставляются
с полными ссылками `package.sources` по фамилии первого автора и году; у нарезки (B4) — ещё ссылки исходника,
и в описание идут только процитированные в её сценах.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

from . import platforms
from .project import Project

YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
CITE = re.compile(r"^\s*(?P<who>[^,·]+?)(?:,[^·]*)?,\s*(?P<year>\d{4})\s*$")  # «Krishna, Briesch & Yuan, 2002»
COVER = {  # шаблон обложки по умолчанию; бренд-кит перекрывает его файлом brand/cover.yaml (docs/BRAND.md)
    # размеры (size) — доли меньшей стороны обложки
    "text": {"font": "head", "weight": "extrabold", "size": 0.16, "color": "text", "upper": True, "max_words": 3},
    "verdict": {"size": 0.17, "pos": "bottom"},  # высота плашки — доля меньшей стороны; bottom (над текстом) | top
    "shade": 0.6,                              # затемнение под текстом (градиент цвета фона), 0 — без него
}
REALISTIC = ("elevenlabs", "edge", "piper")  # нейросетевые голоса: на слух — человек
_SHORT_CH = 10  # с: глава YouTube не короче (support.google.com/youtube/answer/9884579)


# --- входы ------------------------------------------------------------------------------------------------------

def settings(proj: Project) -> dict:
    """`package:` проекта с перекрытием выхода (`by_output.<выход>`)."""
    pk = dict(proj.cfg.get("package") or {})
    over = (pk.pop("by_output", None) or {}).get(proj.out or "") or {}
    pk.update(over)
    return pk


def name(proj: Project) -> str:
    """Имя файлов пакета: выход, у проекта без deliverables — slug."""
    return proj.out or proj.slug


def texts(proj: Project) -> tuple[str, str]:
    """(название, описание) из `<выход>.description.md`, собранного `build`, — для загрузки через API (E2)."""
    f = proj.output_dir() / f"{name(proj)}.description.md"
    if not f.exists():
        raise SystemExit(f"нет {f.name} — сначала: python -m studio package {proj.slug}")
    s = f.read_text(encoding="utf-8")
    title = re.search(r"^## Название[^\n]*\n\n([^\n]*)\n", s, re.M)
    text = re.search(r"^```text\n(.*?)\n```$", s, re.M | re.S)
    if not (title and text):
        raise SystemExit(f"{f.name}: не найдены название и описание — пересоберите: python -m studio package {proj.slug}")
    return title.group(1).strip(), text.group(1).strip()


def ai_label(proj: Project) -> tuple[bool, str]:
    """Нужна ли отметка ИИ-контента на площадке выхода: (да/нет, почему). Правила (сверено 2026-10-25,
    support.google.com/youtube/answer/14328491; TikTok и Meta — Platform.ai): отметка — за реалистичное, что можно
    принять за настоящее, а не за сам факт ИИ.
    1. `package.ai_label: true|false` — решение человека, важнее всего ниже (голос-клон реального человека,
       ИИ-музыка как основа ролика, реалистичная сцена — студия этого сама не видит).
    2. Картинки генератора (`images.enabled`, backend kie, у сцен есть image:) — да: реалистичность кадра не проверить.
    3. Площадка с `ai_voice` (TikTok, Instagram) и нейросетевой голос (REALISTIC) — да: реалистичный ИИ-голос сам
       по себе требует отметки.
    Иначе — нет: графика нарисована кодом (нереалистичная анимация), голос диктора синтетический и не подражает
    реальному человеку (YouTube такое отмечать не требует)."""
    from . import imagegen
    pk = settings(proj)
    if pk.get("ai_label") is not None:
        v = bool(pk["ai_label"])
        return v, f"package.ai_label: {str(v).lower()} — решение человека"
    if imagegen.enabled(proj.cfg) and imagegen.settings(proj.cfg)["backend"] == "kie" and imagegen.requests(proj):
        return True, "картинки сцен из генератора (images.backend: kie) — реалистичность кадра не проверить"
    p, _ = platform(proj)
    synth = proj.cfg["tts"]["backend"]
    if p.ai_voice and synth in REALISTIC:
        return True, f"{p.name}: реалистичный синтетический голос ({synth}) сам по себе требует отметки"
    voice = "голоса нет" if synth == "none" else f"голос {synth} не подражает реальному человеку"
    return False, f"графика нарисована кодом, {voice} — {p.name} такое отмечать не требует"


def platform(proj: Project) -> tuple[platforms.Platform, bool]:
    """Площадка выхода; не задана — площадка формата (platforms.LAYOUT) и False."""
    p = platforms.of(proj)
    return (p, True) if p else (platforms.PLATFORMS[platforms.LAYOUT.get(proj.cfg["format"], "youtube")], False)


def _who(s: str) -> str:
    return re.sub(r"[^a-z]", "", re.sub(r"\bet al\.?", "", s.split("&")[0], flags=re.I).lower())


def citations(proj: Project) -> list[tuple[str, str, str | None]]:
    """Цитаты из сцен по порядку: [(текст, фамилия, год)] без повторов. В `source.text` части через «·» или «→»
    (оригинал → репликация); цитата — часть вида «Автор(ы), год», остальное (журнал, выборка) пропускается."""
    out, seen = [], set()
    for _, ch in proj.chapters:
        for sc in ch.get("scenes") or []:
            src = (sc.get("params") or {}).get("source")
            for part in re.split(r"[·→]", str((src or {}).get("text") or "")) if isinstance(src, dict) else ():
                m = CITE.match(part)
                if m and (k := (_who(m["who"]), m["year"])) not in seen:
                    seen.add(k)
                    out.append((part.strip(), *k))
    return out


def _ref_key(ref: str) -> tuple[str, str | None]:
    first = re.split(r"[\s,.(]", ref.strip(), maxsplit=1)[0]
    y = YEAR.search(ref)
    return _who(first), y.group(1) if y else None


def _bare(text: str) -> str:
    """Фамилия цитаты без подводки: «vs Carney, 2010», «popular summary of Mehrabian, 1971», «drivers: Svenson,
    1981» → carney / mehrabian / svenson."""
    m = CITE.match(text)
    who = re.sub(r"^.*:\s*", "", m["who"] if m else text)
    return _who(re.sub(r"^(?:[a-z][\w.-]*\s+)+", "", who))


def _find(keys: list, text: str, who: str, year: str | None) -> int | None:
    """Номер полной ссылки для цитаты: фамилия и год; иначе фамилия без подводки; иначе ссылка организации,
    у которой первое слово — начало имени в цитате («Microsoft Canada, 2015» ↔ «Microsoft Canada, … (2015)»)."""
    fits = lambda y: y is None or y == year  # noqa: E731
    for test in (lambda w: w == who, lambda w: w == _bare(text),
                 lambda w: len(w) >= 3 and _bare(text).startswith(w)):
        hit = next((i for i, (w, y) in enumerate(keys) if test(w) and fits(y)), None)
        if hit is not None:
            return hit
    return None


def short_ref(ref: str) -> str:
    """Короткая ссылка для описания с пределом: «Автор (год) ссылка», «A & B (год)», «A et al. (год)»;
    без ссылки — с началом названия, чтобы источник можно было найти."""
    m = re.match(r"^(?P<au>.+?)\s*\((?P<y>(?:1[89]|20)\d\d)[a-z]?\)\.?\s*(?P<rest>.*)$", ref.strip())
    if not m:
        return ref
    au, rest = m["au"].rstrip(" ,."), m["rest"]
    first = au.split(",")[0].strip()
    if "et al" in au:
        who = f"{first} et al."
    elif "&" in au:
        before, after = au.split("&", 1)
        who = (f"{first} & {after.split(',')[0].strip()}" if before.rstrip(" ,").count(",") <= 1
               else f"{first} et al.")
    else:
        who = first
    url = re.search(r"https?://\S+", rest)
    if url:
        return f"{who} ({m['y']}) {url.group(0).rstrip('.,)')}"
    title = re.split(r"(?<=[.?!])\s", rest, maxsplit=1)[0].rstrip(".")
    title = title if len(title) <= 80 else title[:79].rstrip() + "…"
    return f"{who} ({m['y']}). {title}" if title else f"{who} ({m['y']})"


def sources(proj: Project) -> tuple[list[str], list[str]]:
    """(строки источников для описания, цитаты без полной ссылки). Полная ссылка подходит цитате, если совпала
    фамилия первого автора и год (у ссылки без года — только фамилия; подводка цитаты «vs …», «summary of …»
    не мешает, см. _find). Проект (не нарезка) получает и ссылки, которых нет в сценах: их автор положил
    в package.sources сам."""
    refs = list(settings(proj).get("sources") or [])
    if proj.src:  # нарезка: ссылки исходника — запасной пул, в описание только процитированные
        from .cutrefs import read_yaml
        refs += [r for r in ((read_yaml(proj.src / "project.yaml").get("package") or {}).get("sources") or [])
                 if r not in refs]
    keys = [_ref_key(r) for r in refs]
    used, lines, missing = set(), [], []
    for text, who, year in citations(proj):
        hit = _find(keys, text, who, year)
        if hit is None:
            missing.append(text)
            lines.append(text)
        elif hit not in used:
            used.add(hit)
            lines.append(refs[hit])
    if not proj.src:
        lines += [r for i, r in enumerate(refs) if i not in used and r not in lines]
    return lines, missing


def tc(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def chapters(proj: Project, tl: dict) -> tuple[list[tuple[float, str]], str]:
    """Главы YouTube из таймлайна: (список (начало, название), причина, если глав нет). Правила площадки:
    первая — 0:00, не меньше трёх, каждая не короче 10 с (короткая сливается с предыдущей)."""
    titles = {c: (d.get("title") or c) for c, d in proj.chapters}
    marks = []
    for s in tl["scenes"]:
        if not marks or marks[-1][2] != s["chapter"]:
            marks.append([s["start"], titles.get(s["chapter"], s["chapter"]), s["chapter"]])
    ends = [m[0] for m in marks[1:]] + [tl["duration"]]
    out = []
    for (t0, title, _), t1 in zip(marks, ends):
        if out and t1 - t0 < _SHORT_CH:
            continue
        out.append((0.0 if not out else t0, title))
    if len(out) > 1 and tl["duration"] - out[-1][0] < _SHORT_CH:
        out.pop()
    if len(out) < 3:
        return [], f"глав {len(out)} — YouTube нужно не меньше трёх по 10 с"
    return out, ""


def hashtags(pk: dict, p: platforms.Platform) -> tuple[list[str], list[str]]:
    """(хэштеги в пределе площадки, лишние)."""
    tags = []
    for t in pk.get("hashtags") or []:
        t = "#" + re.sub(r"\s+", "", str(t)).lstrip("#")
        if len(t) > 1 and t not in tags:
            tags.append(t)
    return tags[:p.tags_max], tags[p.tags_max:]


def verdict(proj: Project) -> str | None:
    """Первый вердикт сценария (`params.verdict.verdict` у lab_verdict / шапки)."""
    for _, ch in proj.chapters:
        for sc in ch.get("scenes") or []:
            v = (sc.get("params") or {}).get("verdict")
            if isinstance(v, dict) and v.get("verdict"):
                return str(v["verdict"]).upper()
    return None


# --- обложка ----------------------------------------------------------------------------------------------------

def cover_template(proj: Project) -> dict:
    """Шаблон обложки: умолчание COVER ← `brand/cover.yaml` бренд-кита проекта (если есть)."""
    from .config import deep_merge
    tpl = COVER
    kit = (proj.cfg.get("style") or {}).get("brand")
    if kit:
        f = proj.ws.root / kit / "cover.yaml"
        if f.is_file():
            tpl = deep_merge(COVER, yaml.safe_load(f.read_text(encoding="utf-8")) or {})
    return tpl


def cover_time(proj: Project, tl: dict, at) -> float:
    """`cover.at`: секунды или chNN/sNN (60 % сцены); по умолчанию — 60 % первой сцены (крючок с предметом ролика)."""
    if isinstance(at, (int, float)):
        return float(min(max(at, 0), tl["duration"] - 1 / tl["fps"]))
    scenes = tl["scenes"]
    if at:
        ch, _, sid = str(at).rpartition("/")
        scenes = [s for s in scenes if s["id"] == sid and (not ch or s["chapter"] == ch)]
        if not scenes:
            raise SystemExit(f"package.cover.at: нет сцены {at}")
    s = scenes[0]
    return s["start"] + s["dur"] * 0.6


def clean_frame(proj: Project, t: float):
    """Кадр ролика в момент t без субтитров (как render.frame_png, но сцена — с пустыми `subs`)."""
    from . import subs as S
    from .render import frame, make_template, prepare
    tl, ctx = prepare(proj)
    for s in tl["scenes"]:
        if s["start"] <= t < s["start"] + s["dur"]:
            s = dict(s, subs=[])
            return frame(ctx, make_template(ctx, s), s, int(round((t - s["start"]) * tl["fps"])),
                         S.font_size(proj)).convert("RGBA")
    raise SystemExit(f"package.cover.at: {t:.2f} c — вне ролика")


def _fit(img, size):
    """Кадрирование по центру под размер обложки («cover»)."""
    from PIL import Image
    W, H = size
    k = max(W / img.width, H / img.height)
    im = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def cover(proj: Project, tl: dict, out: Path, p: platforms.Platform) -> tuple[list[str], list[str]]:
    """Обложка `out` (JPEG): кадр ролика в момент `cover.at`, затемнение снизу, заголовок `cover.text`
    и плашка вердикта (`cover.verdict`: auto — из сценария, none — без неё) внутри безопасной зоны площадки."""
    from PIL import Image
    from . import gfx as G
    errs, warns = [], []
    pk, tpl = settings(proj), cover_template(proj)
    cv = pk.get("cover") or {}
    img = clean_frame(proj, cover_time(proj, tl, cv.get("at")))
    W, H = p.cover or img.size
    img = _fit(img, (W, H))
    style = G.apply_style(proj.cfg["style"])
    z = platforms.layout_zone(proj.cfg)
    x0, x1 = int(W * z["left"]), int(W * (1 - z["right"]))
    y0, y1 = int(H * z["top"]), int(H * (1 - z["bottom"]))
    if tpl.get("shade"):
        import numpy as np
        ramp = np.clip((np.arange(H) / H - 0.35) / 0.65, 0, 1) ** 1.5 * float(tpl["shade"]) * 255
        sh = Image.new("RGBA", (W, H), G.col("bg"))
        sh.putalpha(Image.fromarray(np.repeat(ramp[:, None], W, 1).astype(np.uint8)))
        img.alpha_composite(sh)
    t = tpl["text"]
    text = str(cv.get("text") or "").strip()
    if text and len(text.split()) > int(t.get("max_words") or 99):
        warns.append(f"обложка: «{text}» — {len(text.split())} слов, шаблон бренда — не больше {t['max_words']}")
    bottom = y1
    if text:
        spr = G.text_sprite(text.upper() if t.get("upper") else text, int(min(W, H) * float(t["size"])),
                            t.get("weight", "extrabold"), t.get("color", "text"), maxw=x1 - x0, align="left",
                            spacing=1.0, family=t.get("font", "head"))
        bottom = y1 - spr.height
        img.alpha_composite(spr, (x0, bottom))
    v = cv.get("verdict", "auto")
    v = verdict(proj) if v in ("auto", None) else None if str(v).lower() == "none" else str(v).upper()
    if v:
        vt = tpl["verdict"]
        st = _plate(v, style)
        h = int(min(W, H) * float(vt["size"]))
        st = st.resize((max(1, round(st.width * h / st.height)), h), Image.LANCZOS)
        if st.width > x1 - x0:
            st = st.resize((x1 - x0, max(1, round(st.height * (x1 - x0) / st.width))), Image.LANCZOS)
        y = y0 if vt.get("pos", "top") == "top" else bottom - st.height - int(H * 0.02)
        img.alpha_composite(st, (x0, max(y0, y)))
    q = 92
    while True:
        img.convert("RGB").save(out, "JPEG", quality=q, optimize=True)
        if not p.cover_mb or out.stat().st_size <= p.cover_mb * 1e6 or q <= 60:
            break
        q -= 8
    if p.cover_mb and out.stat().st_size > p.cover_mb * 1e6:
        errs.append(f"обложка {out.stat().st_size / 1e6:.1f} МБ больше предела {p.id} {p.cover_mb:g} МБ")
    return errs, warns


def _plate(v: str, style):
    """Плашка вердикта: у пресета lab — фирменный штамп, иначе — скруглённая плашка цвета вердикта."""
    from . import gfx as G
    from .packs.lab.elements import VERDICTS
    if style.palette == "lab" or (style.kit or {}).get("base") == "lab":
        from .packs.lab.elements import stamp_sprite
        return stamp_sprite(v)
    c = VERDICTS.get(v, "accent")
    word = G.text_sprite(v, 120, "extrabold", c, family="num")
    pad = 40
    plate = G.rrect((word.width + 2 * pad, word.height + pad), 24, G.col("bg", 230), outline=G.col(c), width=6)
    plate.alpha_composite(word, (pad, pad // 2))
    return plate


# --- пакет ------------------------------------------------------------------------------------------------------

def _qa_status(proj: Project) -> str:
    f = proj.qa_dir / "report.md"
    if not f.exists():
        return "не запускался"
    return "PASS" if "Итог: **PASS**" in f.read_text(encoding="utf-8") else "FAIL"


def _needs_sources(proj: Project) -> bool:
    """Канал (YouTube-студия или позиционирование канала) — источники в описании обязательны."""
    ws = proj.ws
    return ws.config.get("kind") == "youtube" or ws.is_channel()


def build(proj: Project, log=print) -> tuple[list[str], list[str]]:
    """Пакет выхода в output/<slug>/. Возвращает (ошибки, предупреждения); файлы пишутся в любом случае."""
    from .timing import load_timeline
    errs, warns = [], []
    tl = load_timeline(proj)
    p, own = platform(proj)
    nm = name(proj)
    d = proj.output_dir()
    d.mkdir(parents=True, exist_ok=True)
    final = proj.final_path()
    video = d / f"{nm}.mp4"
    if final != video:  # проект без deliverables: финал в build/final/ — копия в папку пакета
        for suf in (".mp4", ".srt", ".vtt"):
            f = final.with_suffix(suf)
            if f.exists():
                shutil.copy2(f, video.with_suffix(suf))
    if not video.exists():
        errs.append(f"нет {video.name} — сначала: python -m studio assemble {proj.slug}")
    pk = settings(proj)
    title = str(pk.get("title") or proj.cfg.get("title") or proj.slug).strip()
    body = str(pk.get("description") or proj.cfg.get("topic") or "").strip()
    srcs, missing = sources(proj)
    chs, ch_why = chapters(proj, tl) if p.chapters else ([], "")
    tags, extra = hashtags(pk, p) if p.tags_max else ([], [])
    if extra:
        warns.append(f"хэштеги сверх предела {p.id} ({p.tags_max}): {' '.join(extra)}")
    if missing:
        warns.append("цитаты без полной ссылки в package.sources: " + "; ".join(missing))
    need_src = _needs_sources(proj)
    if need_src and not srcs:
        errs.append("канал: источники в описании обязательны — нет ни цитат в сценах, ни package.sources")
    text = body
    if chs:
        text += "\n\nChapters:\n" + "\n".join(f"{tc(t)} {n}" for t, n in chs) if proj.cfg["language"] == "en" \
            else "\n\nГлавы:\n" + "\n".join(f"{tc(t)} {n}" for t, n in chs)
    head_src = "Sources:" if proj.cfg["language"] == "en" else "Источники:"
    tail = ("\n\n" + " ".join(tags)) if tags else ""
    if srcs and p.title_max:
        fmt = pk.get("sources_format") or "auto"
        full = f"\n\n{head_src}\n" + "\n".join(f"- {s}" for s in srcs)
        if fmt == "short" or (fmt == "auto" and p.text_max and len((text + full + tail).strip()) > p.text_max):
            full = f"\n\n{head_src}\n" + "\n".join(f"- {short_ref(s)}" for s in srcs)
            if fmt == "auto":
                warns.append(f"полные ссылки не влезают в {p.text_max} символов {p.id} — в описании короткие "
                             "(«Автор (год) ссылка»); полный список — package.sources")
        text += full
    elif srcs:  # подпись (TikTok, Instagram — 2200 символов): короткие цитаты сцен одной строкой
        short = [c[0] for c in citations(proj)] or srcs
        text += f"\n\n{head_src} " + "; ".join(short)
    text = (text + tail).strip()
    if p.title_max and len(title) > p.title_max:
        errs.append(f"название {len(title)} символов — у {p.id} предел {p.title_max}")
    if p.text_max and len(text) > p.text_max:
        errs.append(f"описание {len(text)} символов — у {p.id} предел {p.text_max}")

    cov = d / f"{nm}.cover.jpg"
    e, w = cover(proj, tl, cov, p)
    errs += e
    warns += w

    W, H = proj.size
    head = f"{p.name} · {W}×{H} · {tc(tl['duration'])}" + ("" if own else f" (площадка не задана — по формату: {p.id})")
    desc = [f"# {nm}: описание", "", f"<!-- {head}; собрано `python -m studio package` из project.yaml → package -->",
            "", "## Название" if p.title_max else "## Название (для себя: у площадки — только подпись)", "", title,
            f"\n{len(title)} символов" + (f" из {p.title_max}" if p.title_max else ""), "",
            "## Описание — скопировать целиком" if p.title_max else "## Подпись — скопировать целиком", "",
            "```text", text, "```", f"\n{len(text)} символов" + (f" из {p.text_max}" if p.text_max else ""), ""]
    if p.chapters and not chs:
        desc += [f"Главы не добавлены: {ch_why}.", ""]
    (d / f"{nm}.description.md").write_text("\n".join(desc), encoding="utf-8")

    burned = proj.cfg["subtitles"].get("enabled", True) and p.burn_subs
    ok = lambda c: "✅" if c else "❌"  # noqa: E731
    qa = _qa_status(proj)
    lim = platforms._dur(p)
    dur_ok = (p.min_dur or 0) <= tl["duration"] <= (p.max_dur or float("inf"))
    items = [
        f"- [ ] {ok(video.exists())} Файл `{video.name}` — {W}×{H}, {tc(tl['duration'])} "
        f"({ok(dur_ok)} предел {p.id}: {lim})",
        f"- [ ] {'✅' if qa == 'PASS' else '❌'} QA: {qa} (`python -m studio qa {proj.slug}"
        + (f" --out {proj.out}" if proj.out else "") + "`, открыть `subs_check.png` и `final_frames.png`)",
        "- [ ] Посмотреть ролик целиком со звуком (начало, вердикт, концовка)",
        (f"- [ ] Субтитры вшиты — автосубтитры площадки не включать (будут двойные)" if burned else
         f"- [ ] Загрузить субтитры `{nm}.srt` (язык: {proj.cfg['language']})" if p.id.startswith("youtube") else
         f"- [ ] Субтитры не вшиты: `{nm}.srt` рядом"),
        f"- [ ] Обложка `{cov.name}` ({W if not p.cover else p.cover[0]}×{H if not p.cover else p.cover[1]}"
        + (f", ≤ {p.cover_mb:g} МБ" if p.cover_mb else "") + ") — посмотреть глазами"
        + ("" if p.cover else "; площадка берёт кадр — загрузить её как обложку или выбрать кадр"),
        f"- [ ] Название и {'описание' if p.title_max else 'подпись'} — из `{nm}.description.md` "
        f"({len(text)} символов" + (f" из {p.text_max}" if p.text_max else "") + ")",
    ]
    if p.chapters:
        items.append(f"- [ ] {'✅ Главы в описании: ' + str(len(chs)) if chs else '⚠️ Глав нет: ' + ch_why}")
    items.append(f"- [ ] {ok(bool(srcs)) if need_src else ('✅' if srcs else '—')} Источники в описании: {len(srcs)}"
                 + ((" (канал: обязательны" + ("; минимум 3 на длинный ролик — POSITIONING §15" if tl["duration"] > 180
                                                 else "") + ")") if need_src else ""))
    if p.tags_max:
        items.append(f"- [ ] Хэштеги: {len(tags)} из {p.tags_max}" + (f" ({' '.join(tags)})" if tags else ""))
    need, why = ai_label(proj)
    items.append(f"- [ ] {'**Отметка ИИ-контента: ДА**' if need else 'Отметка ИИ-контента: нет'} — {why}. "
                 + (p.ai or "Где отметить — по правилам площадки.")
                 + ("" if need else " Голос похож на реального человека, ИИ-музыка или реалистичная сцена — "
                    "`package.ai_label: true` и пересобрать пакет."))
    items.append(f"- [ ] Язык ролика на площадке: {proj.cfg['language']}; аудитория «не для детей», если так")
    chk = [f"# {nm}: перед публикацией", "", f"<!-- {head} -->", ""] + items
    if errs or warns:
        chk += ["", "## Замечания пакета", ""] + [f"- ❌ {x}" for x in errs] + [f"- ⚠️ {x}" for x in warns]
    (d / f"{nm}.checklist.md").write_text("\n".join(chk) + "\n", encoding="utf-8")
    log(f"Пакет {nm}: {d} — {video.name}, {cov.name}, {nm}.description.md, {nm}.checklist.md")
    for x in errs:
        log(f"  ❌ {x}")
    for x in warns:
        log(f"  ⚠️ {x}")
    return errs, warns

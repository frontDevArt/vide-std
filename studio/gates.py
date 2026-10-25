"""Ворота качества (ROADMAP D4): правила брифа `avoid` / `done_means` и правила студии → проверки validate и qa.

Правила — списки в `project.yaml` и в `studio.yaml` студии (`quality: {avoid: [...], done_means: [...]}`); у проекта
список дополняет студийный, одноимённое правило проекта главнее (`{numbers_without_source: false}` — выключить).
- строка — пункт «проверить глазами»: идёт в чек-лист `qa/report.md`;
- словарь из одного ключа — автоматическая проверка (RULES ниже): validate — ❌ с подсказкой, qa — строка отчёта.

Визуальный QA (всегда, без правил): контраст текста палитры к фону, мелькание по готовому файлу (WCAG 2.3.1:
не больше 3 вспышек в секунду), плотность текста в кадре. Безопасные зоны — studio/safezone.py.
"""
from __future__ import annotations

import difflib
import re
import subprocess

# правило → (раздел, тип значения, описание)
RULES = {
    "max_words_on_screen": ("avoid", int, "не больше N слов надписей в кадре сцены одновременно"),
    "words": ("avoid", list, "запрещённые слова и фразы — в озвучке и в кадре"),
    "numbers_without_source": ("avoid", bool, "цифра в кадре без источника (params.source / study / cite: сцена)"),
    "final_hold": ("done_means", (int, float), "финальный кадр держится ≥ N c после последнего слова"),
    "logo_in_final": ("done_means", bool, "логотип в финале (media.logo_sting или kit.cta_end с логотипом)"),
    "cta_in_final": ("done_means", bool, "призыв в финале (kit.cta_end или текст brief.cta / cta бренд-кита)"),
}
SECTIONS = ("avoid", "done_means")
FINAL = 2  # «финал» — две последние сцены ролика (призыв, затем логотип-стинг)
CHAPTER_TEMPLATES = {"lab.chapter", "kit.chapter_bumper", "core.title"}  # цифры там — нумерация глав
NUMERIC_TEMPLATES = {"kit.chart"}  # график — всегда цифры
NUM_PATHS = {("value",), ("to",), ("hero", "value"), ("myth", "value"), ("crowd", "n")}  # числа params в кадре
SMALL_PRINT = {"chrome", "source", "study"}  # шапка и плашки источника — не «текст сцены» для плотности
DENSITY = {"horizontal": 20}       # слов в кадре без ⚠️ (остальные форматы — DENSITY_TALL)
DENSITY_TALL = 14
DIGIT = re.compile(r"\d")


# ---------------------------------------------------------------- правила
def collect(proj) -> tuple[dict, list, list]:
    """(правила {имя: значение}, пункты глазами [(раздел, текст)], ошибки формата). Студия, затем проект."""
    rules, eyes, errs = {}, [], []
    q = proj.ws.config.get("quality") or {}
    layers = [("studio.yaml: quality.", q if isinstance(q, dict) else {}), ("", proj.cfg)]
    if not isinstance(q, dict):
        errs.append("studio.yaml: quality — словарь {avoid: [...], done_means: [...]}")
    for prefix, src in layers:
        for sec in SECTIONS:
            items = src.get(sec)
            if items is None:
                continue
            where = f"{prefix}{sec}"
            if not isinstance(items, list):
                errs.append(f"{where}: список — строки (глазами) и правила {{имя: значение}}")
                continue
            for it in items:
                if isinstance(it, str) and it.strip():
                    if (sec, it.strip()) not in eyes:
                        eyes.append((sec, it.strip()))
                elif isinstance(it, dict) and len(it) == 1:
                    (k, v), = it.items()
                    e = _rule_error(sec, k, v)
                    if e:
                        errs.append(f"{where}: {e}")
                    else:
                        rules[k] = v
                else:
                    errs.append(f"{where}: {it!r} — строка (проверить глазами) или правило {{имя: значение}}")
    return rules, eyes, errs


def _rule_error(sec, k, v):
    if k not in RULES:
        near = difflib.get_close_matches(str(k), list(RULES), n=1)
        return (f"нет правила '{k}'" + (f" — может, {near[0]}?" if near else "")
                + f" (есть: {', '.join(RULES)}; свободный текст — строкой, в чек-лист глазами)")
    want, typ, _ = RULES[k]
    if want != sec:
        return f"{k} — правило раздела {want}, а не {sec}"
    if isinstance(v, bool) and typ is not bool and v is False:
        return None  # {final_hold: false} — выключить правило студии
    ok = isinstance(v, typ) and not (isinstance(v, bool) and typ is not bool)
    if not ok:
        return f"{k}: {v!r} — нужно {_typename(typ)}"
    if typ is int and v < 1 or k == "final_hold" and v <= 0:
        return f"{k}: {v!r} — нужно число > 0"
    if k == "words" and not all(isinstance(w, str) and w.strip() for w in v):
        return f"words: {v!r} — список непустых строк"
    return None


def _typename(t):
    return {int: "целое", bool: "true | false", list: "список строк"}.get(t, "число")


def active(rules: dict) -> dict:
    """Включённые правила: без `false` (выключено проектом)."""
    return {k: v for k, v in rules.items() if v is not False}


# ---------------------------------------------------------------- текст в кадре
def _scenes(proj):
    return [(ch, s) for ch, d in proj.chapters for s in d.get("scenes") or []]


def _name(s):
    from . import imagegen as IG
    from .packs import REGISTRY
    cls = REGISTRY.get(IG.template_of(s))
    return cls.NAME if cls else str(IG.template_of(s))


def screen_texts(s, small=True) -> list[str]:
    """Надписи сцены из params (как лист перевода, studio/translate.py); small=False — без шапки и плашек источника."""
    from .translate import kind, walk
    out = []
    for path, v in walk(s.get("params") or {}):
        if not small and path and path[0] in SMALL_PRINT:
            continue
        if kind(path, v) == "text":
            out.append(v)
    return out


def _words(texts) -> int:
    from .textutil import word_count
    return sum(word_count(t.replace("*", "")) for t in texts)


def numbers_on_screen(s) -> list[str]:
    """Цифры в кадре сцены: надписи с цифрами (кроме шапки) и числовые value / to / n; у графика — всегда."""
    from .translate import walk
    name = _name(s)
    if name in CHAPTER_TEMPLATES:
        return []
    out = [t for t in screen_texts(s, small=False) if DIGIT.search(t)]
    for path, v in walk(s.get("params") or {}):
        if tuple(path) in NUM_PATHS and isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(f"{'.'.join(map(str, path))} = {v}")
    if name in NUMERIC_TEMPLATES and not out:
        out.append("график")
    return out


def has_source(s) -> bool:
    p = s.get("params") or {}
    src = p.get("source")
    if isinstance(src, dict):
        src = src.get("text")
    st = p.get("study")
    return bool(isinstance(src, str) and src.strip()) or bool(isinstance(st, dict) and (st.get("authors") or st.get("where")))


def _keeps_source(s) -> bool:
    keep = (s.get("params") or {}).get("keep") or []
    return has_source(s) and "source" in keep


# ---------------------------------------------------------------- проверки
def scene_issues(proj, rules: dict) -> list[tuple[str, str, list[str]]]:
    """Правила по сценарию (без тайминга): [(правило, имя строки отчёта, нарушения)]."""
    from .textutil import line_text
    rules = active(rules)
    out = []
    scenes = _scenes(proj)
    if "max_words_on_screen" in rules:
        n = rules["max_words_on_screen"]
        bad = []
        for ch, s in scenes:
            texts = screen_texts(s, small=False)
            w = _words(texts)
            if w > n:
                bad.append(f"{ch}/{s.get('id')}: в кадре {w} слов (бриф avoid: не больше {n}) — "
                           f"«{' / '.join(texts)[:80]}» — сократите надписи или разбейте сцену")
        out.append(("max_words_on_screen", f"Бриф: не больше {n} слов в кадре", bad))
    if "words" in rules:
        pats = [(w, re.compile(r"(?<!\w)" + re.escape(w.strip()) + r"(?!\w)", re.I)) for w in rules["words"]]
        bad = []
        for ch, s in scenes:
            where = [("озвучка", line_text(l).replace("|", "")) for l in s.get("lines") or []]
            where += [("кадр", t) for t in screen_texts(s)]
            for w, rx in pats:
                hit = next((f"{k}: «{t[:60]}»" for k, t in where if rx.search(t)), None)
                if hit:
                    bad.append(f"{ch}/{s.get('id')}: «{w}» — в списке avoid ({hit})")
        out.append(("words", "Бриф: без запрещённых слов", bad))
    if "numbers_without_source" in rules:
        bad = []
        by_id = {(ch, s.get("id")): s for ch, s in scenes}
        prev = {}
        for ch, s in scenes:
            nums = numbers_on_screen(s)
            ok = has_source(s) or (prev.get(ch) is not None and _keeps_source(prev[ch]))
            cite = s.get("cite")
            if cite and not ok:
                c_ch, _, c_id = str(cite).rpartition("/")
                tgt = by_id.get((c_ch or ch, c_id))
                if tgt is None:
                    bad.append(f"{ch}/{s.get('id')}: cite: {cite} — нет такой сцены")
                    nums = []
                elif not has_source(tgt):
                    bad.append(f"{ch}/{s.get('id')}: cite: {cite} — у той сцены нет источника")
                    nums = []
                else:
                    ok = True
            if nums and not ok:
                bad.append(f"{ch}/{s.get('id')}: цифры в кадре без источника ({'; '.join(nums[:3])}) — правило "
                           f"«у каждой цифры источник»: params.source {{label, text}} или cite: <сцена с источником>")
            prev[ch] = s
        out.append(("numbers_without_source", "Цифры в кадре — с источником", bad))
    fin = scenes[-FINAL:]
    fin_s = ", ".join(f"{c}/{s.get('id')} ({_name(s)})" for c, s in fin)
    if "logo_in_final" in rules and scenes:
        ok = any(_has_logo(proj, s) for _, s in fin)
        out.append(("logo_in_final", "Финал: логотип", [] if ok else [
            f"финал ({fin_s}) без логотипа — done_means: logo_in_final; последней сценой — media.logo_sting "
            "или kit.cta_end (логотип — бренд-кит или params.logo)"]))
    if "cta_in_final" in rules and scenes:
        ok = any(_has_cta(proj, s) for _, s in fin)
        out.append(("cta_in_final", "Финал: призыв", [] if ok else [
            f"финал ({fin_s}) без призыва — done_means: cta_in_final; kit.cta_end или текст призыва "
            f"({_cta_text(proj) or 'brief.cta'}) в надписи или озвучке"]))
    return out


def _kit(proj):
    return proj.cfg["style"].get("kit") or {}


def _has_logo(proj, s):
    n = _name(s)
    if n == "media.logo_sting":
        return True
    if n == "kit.cta_end":
        return bool((s.get("params") or {}).get("logo") or (_kit(proj).get("logo") or {}).get("light"))
    return False


def _cta_text(proj):
    b = (proj.cfg.get("brief") or {}).get("cta")
    return (b if isinstance(b, str) else None) or (_kit(proj).get("cta") or {}).get("text")


def _has_cta(proj, s):
    from .textutil import line_text
    if _name(s) == "kit.cta_end":
        return True
    cta = _cta_text(proj)
    if not cta:
        return False
    norm = lambda x: re.sub(r"[\W_]+", " ", x.replace("*", "")).strip().lower()  # noqa: E731
    texts = screen_texts(s) + [line_text(l).replace("|", "") for l in s.get("lines") or []]
    return any(norm(cta) in norm(t) for t in texts)


def final_hold(tl: dict) -> float:
    """Сколько держится финальный кадр после последнего слова, c (без речи — длина последней сцены)."""
    last = tl["scenes"][-1]
    end = last["start"] + last["dur"]
    said = [s["start"] + L["t1"] for s in tl["scenes"] for L in s["lines"]]
    return end - max(said) if said else last["dur"]


def timeline_issue(rules: dict, tl: dict):
    """final_hold по таймлайну: (имя строки, нарушения) или None."""
    n = active(rules).get("final_hold")
    if n is None:
        return None
    h = final_hold(tl)
    return (f"Финал держится ≥ {n:g} c", [] if h >= n - 1e-3 else [
        f"финальный кадр держится {h:.2f} c после последнего слова (done_means: final_hold {n:g}) — "
        f"добавьте hold: {n - h + 0.05:.1f} последней сцене"])


def validate(proj, errs, warns):
    """validate: ошибки формата правил и нарушения правил по сценарию (и по актуальному таймлайну)."""
    import json
    from .timing import source_hash
    rules, _, ferrs = collect(proj)
    errs += ferrs
    for _, _, bad in scene_issues(proj, rules):
        errs += bad
    p = proj.build / "timeline.json"
    if "final_hold" in active(rules) and p.exists():
        tl = json.loads(p.read_text(encoding="utf-8"))
        if tl.get("src") == source_hash(proj):
            errs += timeline_issue(rules, tl)[1]


# ---------------------------------------------------------------- визуальный QA
def _lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    """Контраст WCAG двух цветов RGB: 1–21."""
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# роль текста → минимум контраста (WCAG: 4.5 обычный текст, 3 — крупный; надписи ролика крупные)
TEXT_ROLES = {"text": 4.5, "dim": 3.0, "accent": 3.0, "accent2": 3.0}


def palette_contrast(pal) -> tuple[bool, str]:
    """Цвета текста палитры (с настроением и бренд-китом) к фону: (ok, подробно)."""
    bgs = [tuple(pal[k]) for k in ("bg", "bg_top", "bg_bot") if k in pal]
    worst, bad = None, []
    for role, need in TEXT_ROLES.items():
        if role not in pal:
            continue
        r = min(contrast(pal[role], b) for b in bgs)
        if worst is None or r < worst[1]:
            worst = (role, r)
        if r < need:
            bad.append(f"{role} #{'%02X%02X%02X' % tuple(pal[role][:3])} — {r:.1f}:1 (нужно ≥ {need:g})")
    det = f"худший — {worst[0]} {worst[1]:.1f}:1" if worst else "нет цветов текста"
    return not bad, det + (f"; мало: {', '.join(bad)}" if bad else "")


def luma_series(path, grid=2) -> list[list[float]]:
    """Относительная яркость по кадрам готового файла: [области grid×grid][кадры]."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={grid}:{grid}:flags=area,format=rgb24",
                        "-f", "rawvideo", "-"], capture_output=True, stdin=subprocess.DEVNULL, check=True)
    px = 3 * grid * grid
    data = r.stdout
    out = [[] for _ in range(grid * grid)]
    for i in range(0, len(data) - px + 1, px):
        for j in range(grid * grid):
            out[j].append(_lum(data[i + 3 * j:i + 3 * j + 3]))
    return out


def flashes(series, fps) -> float:
    """Наибольшее число вспышек за любую секунду (WCAG: вспышка — пара противоположных перепадов яркости ≥ 10 %
    при более тёмном состоянии ниже 0.8)."""
    edges = []  # кадры значимых перепадов (смена направления)
    lo = hi = series[0] if series else 0
    direction = 0
    for i, y in enumerate(series):
        hi, lo = max(hi, y), min(lo, y)
        if direction >= 0 and hi - y >= 0.1 and y < 0.8:  # спад
            edges.append(i); direction, hi, lo = -1, y, y
        elif direction <= 0 and y - lo >= 0.1 and lo < 0.8:  # подъём
            edges.append(i); direction, hi, lo = 1, y, y
    best, j = 0, 0
    win = max(1, int(round(fps)))
    for i in range(len(edges)):
        while edges[i] - edges[j] >= win:
            j += 1
        best = max(best, i - j + 1)
    return best / 2


def flash_check(path, fps) -> tuple[bool, str]:
    worst = max((flashes(s, fps) for s in luma_series(path)), default=0)
    return worst <= 3, f"до {worst:g} вспышек в секунду (предел WCAG — 3)"


def density(proj, limit=None):
    """Самая плотная по тексту сцена: (слов, где, предел)."""
    lim = limit or DENSITY.get(proj.cfg["format"], DENSITY_TALL)
    best = (0, "—")
    for ch, s in _scenes(proj):
        w = _words(screen_texts(s, small=False))
        if w > best[0]:
            best = (w, f"{ch}/{s.get('id')}")
    return best[0], best[1], lim


def qa(proj, tl, final, chk, warn):
    """Строки отчёта qa: правила брифа и студии, контраст, мелькание, плотность. Возвращает пункты «глазами»."""
    from . import gfx as G
    rules, eyes, ferrs = collect(proj)
    if ferrs:
        chk(False, "Бриф и студия: правила качества", "; ".join(ferrs[:3]))
    for _, name, bad in scene_issues(proj, rules):
        chk(not bad, name, "; ".join(bad[:3]) if bad else "нарушений нет")
    ti = timeline_issue(rules, tl)
    if ti:
        chk(not ti[1], ti[0], ti[1][0] if ti[1] else f"{final_hold(tl):.2f} c")
    ok, det = palette_contrast(G.SM.active().pal)
    chk(ok, "Контраст текста к фону", det)
    ok, det = flash_check(final, tl["fps"])
    chk(ok, "Без мелькания (≤ 3 вспышек в секунду)", det)
    lim = active(rules).get("max_words_on_screen")
    w, where, lim2 = density(proj, lim)
    if lim:  # предел из брифа — проверка «не больше N слов в кадре» выше (❌)
        pass
    elif w > lim2:
        warn("WARN", "Плотность текста в кадре", f"{where}: {w} слов (больше {lim2} — читается с трудом)")
    else:
        chk(True, "Плотность текста в кадре", f"до {w} слов в сцене ({where}), предел {lim2}")
    return eyes

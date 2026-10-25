"""Перевод ролика (ROADMAP D3): тот же ролик на другом языке.

`python -m studio translate <исходник> --to es` создаёт проект-перевод `<исходник>-es/` рядом с исходником:
- `translation.yaml` — рабочий лист: по сценам строки озвучки (`lines`), надписи в кадре из `params` (`text`) и
  слова-триггеры анимации (`at`) с пустым переводом. Переводит Claude, сам файл — единственный вход перевода;
- `project.yaml` и `script/*.yaml` — **производные**: настройки и сцены исходника, строки заменены переводом, поверх —
  `overrides` листа (`project:` — голос, площадки…; `scenes: {chNN/sNN: {...}}` — вёрстка под длинный текст).
  Пишет их повторный `translate` (руками не править — перезапишутся);
- `templates/`, `assets/`, `assets.yaml` — копией исходника (стиль, сцены, картинки те же).

Повторный запуск (`translate <исходник> --to es` или `translate <перевод>`) сверяет лист с исходником: новые строки —
с пустым переводом, переведённые по тексту исходника сохраняются. Сценарий пишется, только когда переведено всё и
проверки пройдены: столько же битов `|`, цифры надписей те же, слово-триггер есть в переведённых строках сцены, нет
«чужого алфавита» языка перевода (studio/lang.py). Источники (`source`, `source.text`, `authors`, `where`) и числа
в `params` не меняются — их нет в листе. Голос — студии для языка перевода (`voices:` в studio.yaml), темп — тот же.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import deep_merge
from .cutrefs import read_yaml

SHEET = "translation.yaml"
# ключи params, где строка — не текст в кадре: цвета, иконки, файлы, режимы, столбцы CSV, перечисления
SKIP_KEYS = {"color", "icon", "icons", "shape", "role", "fit", "enter", "exit", "file", "photo", "logo", "backdrop",
             "data", "x", "y", "type", "side", "motion", "frame", "mood", "glow", "font", "template", "id", "align",
             "anchor", "ease", "layout", "kind", "style", "palette", "image", "src", "path", "handle", "verdict",
             "reveal", "view", "time", "time_from", "time_to", "date", "prefix", "suffix", "was", "now", "price"}
KEEP_KEYS = {"authors", "where", "url", "author"}  # ссылки на источник: не переводятся
TRIGGER_KEYS = {"at", "until"}  # и *_at: слово озвучки, бит или секунды
SECONDS = re.compile(r"^\s*[\d.]+s\s*$")
FILEISH = re.compile(r"^[\w./\\-]+\.[A-Za-z0-9]{2,4}$|^#[0-9A-Fa-f]{3,8}$")
DIGITS = re.compile(r"\d+")
BACKEND_KEYS = ("model", "context", "stability", "similarity_boost", "style", "use_speaker_boost", "speed")


def _key(path) -> str:
    """Имя ключа строки: последний не-индекс в пути (`steps.0` → steps)."""
    for p in reversed(path):
        if not isinstance(p, int):
            return str(p)
    return ""


def kind(path: tuple, value) -> str | None:
    """Что за строка в params: 'text' (перевести), 'at' (слово-триггер), None (не трогать)."""
    if not isinstance(value, str) or not value.strip():
        return None
    k = _key(path)
    names = [p for p in path if not isinstance(p, int)]
    if k in TRIGGER_KEYS or k.endswith("_at"):
        return None if SECONDS.match(value) else "at"
    if k in SKIP_KEYS or k in KEEP_KEYS:
        return None
    if k == "source" or (len(names) >= 2 and names[-2] == "source" and k == "text"):
        return None  # источник цитаты — как в исходнике
    if not any(ch.isalpha() for ch in value) or FILEISH.match(value.strip()):
        return None
    return "text"


def walk(obj, path=()):
    """(путь, строка) по вложенным dict/list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (i,))
    else:
        yield path, obj


def _set(obj, path, value):
    for p in path[:-1]:
        obj = obj[p]
    obj[path[-1]] = value


def _lines(sc) -> list[str]:
    from .textutil import line_text
    return [line_text(l) for l in sc.get("lines") or []]


# ---------------------------------------------------------------- строки исходника
@dataclass
class Items:
    """Строки одной сцены (или проекта) по видам, без повторов, по порядку."""
    lines: list = field(default_factory=list)
    text: list = field(default_factory=list)
    at: list = field(default_factory=list)

    def add(self, kind_, s):
        lst = getattr(self, kind_)
        if kind_ == "lines" or s not in lst:
            lst.append(s)


PROJECT_PATHS = (("title",), ("topic",), ("package", "title"), ("package", "description"), ("package", "cover", "text"))


def project_strings(user: dict) -> list[tuple]:
    """(путь, строка) в project.yaml, видимые зрителю: название, тема, описание и обложка пакета, хэштеги."""
    out = []

    def get(d, path):
        for p in path:
            if not isinstance(d, dict) or p not in d:
                return None
            d = d[p]
        return d
    for path in PROJECT_PATHS:
        v = get(user, path)
        if isinstance(v, str) and v.strip():
            out.append((path, v))
    pk = user.get("package") or {}
    for i, h in enumerate(pk.get("hashtags") or []):
        out.append((("package", "hashtags", i), str(h)))
    for o, ov in (pk.get("by_output") or {}).items():
        for sub in (("title",), ("description",), ("cover", "text")):
            v = get(ov, sub)
            if isinstance(v, str) and v.strip():
                out.append((("package", "by_output", o) + sub, v))
        for i, h in enumerate((ov or {}).get("hashtags") or []):
            out.append((("package", "by_output", o, "hashtags", i), str(h)))
    return out


def chapter_files(src: Path, user: dict) -> list[tuple]:
    """[(id главы, данные script/<id>.yaml)] исходника — как в project.yaml (chapters), файлы как есть."""
    out = []
    for ch in user.get("chapters") or []:
        p = src / "script" / f"{ch}.yaml"
        if p.exists():
            out.append((ch, read_yaml(p)))
    return out


def collect(src: Path, user: dict) -> tuple[dict, list]:
    """({chNN/sNN: Items}, [строки проекта]) исходника."""
    scenes = {}
    for ch, data in chapter_files(src, user):
        if isinstance(data.get("title"), str) and data["title"].strip():
            scenes.setdefault(f"{ch}", Items()).add("text", data["title"])
        for sc in data.get("scenes") or []:
            it = scenes.setdefault(f"{ch}/{sc.get('id')}", Items())
            for l in _lines(sc):
                it.add("lines", l)
            for path, v in walk(sc.get("params") or {}):
                k = kind(path, v)
                if k:
                    it.add(k, v)
    proj = list(dict.fromkeys(v for _, v in project_strings(user)))
    return scenes, proj


# ---------------------------------------------------------------- рабочий лист
def _pairs(old: list, frm: str, to: str) -> dict:
    return {str(e.get(frm)): e.get(to) for e in old or [] if isinstance(e, dict) and e.get(frm) is not None}


def sheet_data(src_slug: str, frm: str, to: str, scenes: dict, proj: list, old: dict | None = None) -> dict:
    """Лист перевода: строки исходника, переводы из старого листа по тексту исходника (по сцене), overrides — как были."""
    old = old or {}
    osc = old.get("scenes") or {}
    out = {"source": src_slug, "from": frm, "to": to,
           "project": [{frm: s, to: _pairs(old.get("project"), frm, to).get(s) or ""} for s in proj], "scenes": {}}
    for sid, it in scenes.items():
        o = osc.get(sid) or {}
        block = {}
        for kind_ in ("lines", "text", "at"):
            vals = getattr(it, kind_)
            if vals:
                tr = _pairs(o.get(kind_), frm, to)
                block[kind_] = [{frm: s, to: tr.get(s) or ""} for s in vals]
        out["scenes"][sid] = block
    out["overrides"] = old.get("overrides") or {"project": {}, "scenes": {}}
    return out


HEAD = """\
# Перевод ролика (ROADMAP D3): {src} ({frm}) → {to}. Заполните пустые `{to}:` и запустите
#   python -m studio translate {dst}
# lines — строки озвучки: столько же `|` (биты), числа — как в исходнике (словами, если там словами);
# text  — надписи в кадре (params): цифры те же; если перевод совпадает с исходником (имя, бренд) — повторите его;
# at    — слова-триггеры анимации: переведённое слово (или фраза) должно быть в строках этой сцены.
# Источники (source, authors, where) и числа в params не переводятся — их здесь нет.
# overrides.project — поверх project.yaml исходника (голос: tts); overrides.scenes.chNN/sNN — поверх сцены
# (params под длинный текст). project.yaml и script/*.yaml перевода пишет translate — руками их не править.
"""


def write_sheet(dst: Path, data: dict):
    text = HEAD.format(src=data["source"], frm=data["from"], to=data["to"], dst=dst.name)
    text += yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000)
    (dst / SHEET).write_text(text, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- проверка и запись перевода
@dataclass
class Result:
    total: int = 0
    missing: list = field(default_factory=list)  # (где, текст)
    errs: list = field(default_factory=list)
    warns: list = field(default_factory=list)

    @property
    def done(self):
        return not self.missing and not self.errs


def _words(lines: list[str]) -> list[dict]:
    from .textutil import tts_text
    return [{"w": w, "t0": 0.0} for l in lines for w in tts_text(l).split()]


def check(data: dict) -> Result:
    """Полнота и проверки листа: биты, цифры, триггеры, чужой алфавит, расхождения одинаковых надписей."""
    from .lang import profile
    from .packs.lab.triggers import word_time
    frm, to = data["from"], data["to"]
    foreign = profile(to).get("foreign")
    r = Result()
    seen = {}  # надпись исходника → (перевод, где) — одна надпись, разные переводы

    def one(where, kind_, e):
        s, t = str(e.get(frm) or ""), e.get(to)
        r.total += 1
        if not isinstance(t, str) or not t.strip():
            r.missing.append((where, s))
            return None
        if foreign and re.search(foreign, t):
            r.errs.append(f"{where}: «{t[:50]}» — {profile(to)['foreign_msg']}")
        if kind_ == "lines":
            if t.strip() == s.strip():
                r.errs.append(f"{where}: строка не переведена: «{s[:50]}»")
            if t.count("|") != s.count("|"):
                r.errs.append(f"{where}: битов «|» {t.count('|')}, в исходнике {s.count('|')}: «{t[:50]}»")
        elif kind_ == "text":
            if sorted(DIGITS.findall(t)) != sorted(DIGITS.findall(s)):
                r.errs.append(f"{where}: цифры не те, что в исходнике: «{s[:40]}» → «{t[:40]}»")
            if seen.setdefault(s, t) != t:
                r.warns.append(f"{where}: «{s[:40]}» переведено иначе, чем в другой сцене: «{t[:40]}» / «{seen[s][:40]}»")
        if t.count("*") != s.count("*"):
            r.warns.append(f"{where}: акцентов *…* иначе, чем в исходнике: «{t[:50]}»")
        return t

    for e in data.get("project") or []:
        one("project.yaml", "text", e)
    for sid, block in (data.get("scenes") or {}).items():
        lines = [one(sid, "lines", e) for e in block.get("lines") or []]
        for e in block.get("text") or []:
            one(sid, "text", e)
        words = _words([l for l in lines if l])
        for e in block.get("at") or []:
            t = one(sid, "at", e)
            if t and lines and all(lines) and word_time(words, t)[0] is None:
                r.errs.append(f"{sid}: триггер at «{t}» (из «{e.get(frm)}») не найден в переведённых строках сцены")
    return r


def _tables(data: dict) -> tuple[dict, dict]:
    frm, to = data["from"], data["to"]
    proj = _pairs(data.get("project"), frm, to)
    scenes = {sid: {k: _pairs(b.get(k), frm, to) for k in ("lines", "text", "at")}
              for sid, b in (data.get("scenes") or {}).items()}
    return proj, scenes


def tr(table: dict, s: str) -> str:
    t = table.get(s)
    return t if isinstance(t, str) and t.strip() else s


def project_yaml(src_user: dict, data: dict) -> dict:
    """project.yaml перевода: исходника, язык и метка перевода, голос языка, переведённые поля, overrides.project."""
    import copy
    user = copy.deepcopy(src_user)
    proj_tr, _ = _tables(data)
    for path, v in project_strings(src_user):
        _set(user, path, tr(proj_tr, v))
    user["language"] = data["to"]
    user["translation"] = {"source": data["source"], "from": data["from"]}
    over = (data.get("overrides") or {}).get("project") or {}
    tts = dict(user.get("tts") or {})
    if tts:
        tts["voice"] = "auto"  # голос исходника — для его языка; auto — голос студии / профиля языка перевода
        user["tts"] = tts
    nb = (over.get("tts") or {}).get("backend")
    if nb and nb != tts.get("backend"):
        for k in BACKEND_KEYS + ("voice",):
            user.get("tts", {}).pop(k, None)
    return deep_merge(user, over)


def script(ch: str, data_ch: dict, data: dict) -> dict:
    """script/<ch>.yaml перевода: строки и надписи — переводом, поверх сцены — overrides.scenes."""
    import copy
    _, scenes = _tables(data)
    d = copy.deepcopy(data_ch)
    if isinstance(d.get("title"), str):
        d["title"] = tr(scenes.get(ch, {}).get("text", {}), d["title"])
    over = (data.get("overrides") or {}).get("scenes") or {}
    out = []
    for sc in d.get("scenes") or []:
        sid = f"{ch}/{sc.get('id')}"
        t = scenes.get(sid, {})
        for i, l in enumerate(sc.get("lines") or []):
            if isinstance(l, dict):
                l["text"] = tr(t.get("lines", {}), str(l.get("text", "")))
            else:
                sc["lines"][i] = tr(t.get("lines", {}), str(l))
        for path, v in list(walk(sc.get("params") or {})):
            k = kind(path, v)
            if k:
                _set(sc["params"], path, tr(t.get(k, {}), v))
        out.append(deep_merge(sc, over.get(sid) or {}))
    if "scenes" in d:
        d["scenes"] = out
    return d


def dump(path: Path, head: str, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(head + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000),
                    encoding="utf-8", newline="\n")


def copy_inputs(src: Path, dst: Path):
    """Шаблоны, ассеты и их реестр исходника — в перевод (стиль и картинки те же)."""
    for name in ("templates", "assets"):
        if (src / name).is_dir():
            shutil.copytree(src / name, dst / name, dirs_exist_ok=True)
    if (src / "assets.yaml").exists():
        shutil.copy2(src / "assets.yaml", dst / "assets.yaml")


def sync(src: Path, dst: Path, to: str | None = None, tts: str | None = None) -> tuple[dict, Result]:
    """Создать или обновить перевод `dst` исходника `src`: лист, project.yaml, при готовом листе — script/*.yaml."""
    src_user = read_yaml(src / "project.yaml")
    if src_user.get("cutdown"):
        raise SystemExit(f"{src.name} — нарезка: переводите исходный ролик, затем режьте перевод (cutdown)")
    if src_user.get("translation"):
        raise SystemExit(f"{src.name} — уже перевод: переводите исходник {src_user['translation'].get('source')}")
    frm = str(src_user.get("language") or "ru")
    old = read_yaml(dst / SHEET) if (dst / SHEET).exists() else {}
    to = to or old.get("to")
    if not to:
        raise SystemExit("Укажите язык перевода: --to es")
    if old and old.get("to") and old["to"] != to:
        raise SystemExit(f"{dst.name} — перевод на {old['to']}, а не на {to}: --slug для другого языка")
    if to == frm:
        raise SystemExit(f"Исходник уже на языке {to}")
    scenes, proj = collect(src, src_user)
    data = sheet_data(src.name, frm, to, scenes, proj, old)
    if tts:
        data["overrides"].setdefault("project", {}).setdefault("tts", {})["backend"] = tts
    dst.mkdir(parents=True, exist_ok=True)
    write_sheet(dst, data)
    copy_inputs(src, dst)
    head = (f"# Перевод {src.name} ({frm}) → {to} (ROADMAP D3). Файл пишет `python -m studio translate {dst.name}`\n"
            f"# из project.yaml исходника и {SHEET} — правки голоса и площадок: overrides.project в {SHEET}.\n")
    dump(dst / "project.yaml", head, project_yaml(src_user, data))
    r = check(data)
    if r.done:
        for ch, d in chapter_files(src, src_user):
            dump(dst / "script" / f"{ch}.yaml",
                 f"# {ch}: перевод {src.name}/{ch} на {to} — пишет translate из {SHEET}, руками не править.\n",
                 script(ch, d, data))
    return data, r

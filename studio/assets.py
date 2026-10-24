"""Ассеты проекта (ROADMAP C2): фото, видео, звук, логотипы клиента — `projects/<slug>/assets/` + `assets.yaml`.

```yaml
# projects/<slug>/assets.yaml — у каждого файла, что попадает в кадр или в звук, известны источник и права
assets:
  - file: assets/lamp-front.jpg
    source: фотосессия клиента 2026-10
    license: права у клиента, передано для рекламы
    by: Aurora Lighting
```
Сцены ссылаются на файлы путём от папки проекта (`params: {file: assets/lamp-front.jpg}`); ссылка — любая строка
в `params` с расширением медиа или данных (CSV графиков, ROADMAP C4) (`refs`). validate: файла нет — ❌, файл не в `assets.yaml` или без лицензии — ⚠️;
qa: всё, что звучит и видно, есть в `assets.yaml` с лицензией и источником — иначе ❌ (не сдаём чужое без прав).
Содержимое файла входит в ключ кэша рендера сцены (`fingerprint`): заменили фото — сцена перерисуется.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v", ".mkv")
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac")
DATA_EXT = (".csv",)  # данные графиков (kit.chart, ROADMAP C4): у источника данных те же правила, что у фото
MEDIA_EXT = IMAGE_EXT + VIDEO_EXT + AUDIO_EXT + DATA_EXT
FILE = "assets.yaml"
FIELDS = ("source", "license")  # обязательные поля записи; by — кто дал (необязательно)


def is_media(v) -> bool:
    return isinstance(v, str) and v.lower().endswith(MEDIA_EXT) and "\n" not in v


def refs(params) -> list[str]:
    """Пути к медиафайлам в params сцены (рекурсивно: layers, callouts…), по порядку, без повторов."""
    out = []

    def walk(v):
        if is_media(v):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(params or {})
    return list(dict.fromkeys(out))


def roots(proj) -> list[Path]:
    """Где искать ассеты: папка проекта, у нарезки (ROADMAP B4) ещё папка исходника — сцены `from:` ссылаются на его
    assets/."""
    return [proj.root] + ([proj.src] if getattr(proj, "src", None) else [])


def path(root, rel) -> Path:
    """Файл ассета: путь от папки проекта (абсолютный — как есть). root — папка или список папок (первая, где файл
    есть; нет нигде — путь от первой)."""
    p = Path(rel)
    if p.is_absolute():
        return p
    rs = [Path(r) for r in root] if isinstance(root, (list, tuple)) else [Path(root)]
    for r in rs:
        if (r / p).is_file():
            return r / p
    return rs[0] / p


def _key(rel) -> str:
    return Path(rel).as_posix()  # «./assets/a.jpg» и «assets/a.jpg» — одна запись


def load(root) -> tuple[dict, list[str]]:
    """assets.yaml → ({файл: запись}, ошибки формата). Нет файла — пусто. root — папка или список (записи сливаются,
    первая папка главнее)."""
    if isinstance(root, (list, tuple)):
        out, errs = {}, []
        for r in reversed(root):
            o, e = load(r)
            out.update(o)
            errs += e
        return out, errs
    f = Path(root) / FILE
    if not f.is_file():
        return {}, []
    try:
        raw = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return {}, [f"{FILE}: не читается ({e})"]
    items = raw.get("assets") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return {}, [f"{FILE}: нужен список assets: [{{file, source, license, by}}]"]
    out, errs = {}, []
    for i, e in enumerate(items):
        if not isinstance(e, dict) or not isinstance(e.get("file"), str):
            errs.append(f"{FILE}: запись {i + 1} без file")
            continue
        out[_key(e["file"])] = e
    return out, errs


def scene_refs(proj) -> list[tuple[str, str]]:
    """[(где, путь)] — медиа из params всех сцен проекта."""
    return [(f"{ch}/{s.get('id')}", r) for ch, d in proj.chapters for s in d.get("scenes") or []
            for r in refs(s.get("params"))]


def issues(proj) -> tuple[list[str], list[str]]:
    """validate: (ошибки, предупреждения) по ассетам сцен и assets.yaml."""
    rs = roots(proj)
    reg, errs = load(rs)
    warns = []
    used = scene_refs(proj)
    for where, r in used:
        if not path(rs, r).is_file():
            errs.append(f"{where}: нет файла {r} (путь — от папки проекта, обычно assets/…)")
    seen = set()
    for where, r in used:
        k = _key(r)
        if k in seen or not path(rs, r).is_file():
            continue
        seen.add(k)
        e = reg.get(k)
        if e is None:
            warns.append(f"{where}: {r} нет в {FILE} — запишите источник и лицензию (qa без них не пройдёт)")
        else:
            miss = [x for x in FIELDS if not e.get(x)]
            if miss:
                warns.append(f"{FILE}: {r} — не заполнено {', '.join(miss)} (qa без них не пройдёт)")
    for k in reg:
        if not path(rs, k).is_file():
            errs.append(f"{FILE}: нет файла {k}")
    return errs, warns


def qa_check(proj) -> tuple[bool, str] | None:
    """QA «Ассеты: источник и лицензия» — (ok, подробно); None — в ролике нет медиафайлов."""
    used = list(dict.fromkeys(_key(r) for _, r in scene_refs(proj)))
    if not used:
        return None
    rs = roots(proj)
    reg, _ = load(rs)
    bad = [r for r in used if not path(rs, r).is_file()
           or not all((reg.get(r) or {}).get(x) for x in FIELDS)]
    if bad:
        return False, f"без файла, источника или лицензии в {FILE}: {', '.join(bad[:4])}" + (" …" if len(bad) > 4 else "")
    lic = sorted({str(reg[r]["license"]) for r in used})
    return True, f"{len(used)} файлов; лицензии: {'; '.join(lic[:3])}" + (" …" if len(lic) > 3 else "")


_SHA = {}  # (путь, mtime, размер) → sha1: файл не перечитывается, пока не изменился


def file_hash(p) -> str:
    p = Path(p)
    try:
        st = p.stat()
    except OSError:
        return "missing"
    k = (str(p.resolve()), st.st_mtime_ns, st.st_size)
    if k not in _SHA:
        h = hashlib.sha1()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        _SHA[k] = h.hexdigest()[:12]
    return _SHA[k]


def fingerprint(root, params) -> list | None:
    """Содержимое медиа сцены для ключа кэша рендера: [(путь, sha1)] или None, если медиа нет. root — как у path."""
    rs = refs(params)
    return [(r, file_hash(path(root, r))) for r in rs] or None

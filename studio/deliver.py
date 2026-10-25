"""Версии и сдача (ROADMAP D5): `python -m studio deliver <проект>`.

Каждая сдача — снимок пакета всех выходов (`package`: MP4, .srt/.vtt, обложка, описание, чек-лист) в
`output/<slug>/vN/` рядом с прошлыми версиями, `manifest.json` версии (хэши сцен сценария, разделов project.yaml и
файлов, начало и длительность сцен, все закрытые к сдаче комментарии ревью D1), раздел в `CHANGELOG.md` проекта — что изменили
по сравнению с прошлой версией: комментарии ревью, сцены (изменены / добавлены / удалены), разделы project.yaml,
длительность, файлы; лист `compare.jpg` — кадры изменённых сцен «было → стало». Архив для клиента —
`output/<slug>/<slug>-vN.zip` (папка версии + CHANGELOG.md).

`output/` не в git, `CHANGELOG.md` — вход проекта (лежит в git, правится руками: заметки к версии дописывать можно).
Ворота: нет видео, QA не PASS или ошибка пакета — версия не создаётся (`--force` — всё равно сдать, с пометкой).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from . import package
from .project import Project, stable_hash

SUFFIXES = (".mp4", ".srt", ".vtt", ".cover.jpg", ".description.md", ".checklist.md")
STORED = (".mp4", ".jpg")  # уже сжаты — в архив без сжатия
MAX_COMPARE = 6  # пар кадров на листе compare.jpg
CHANGELOG_HEAD = "# Изменения по версиям\n\nСдачи `python -m studio deliver` — новые сверху; файлы версий — `output/{slug}/vN/`.\n"


# ---------------------------------------------------------------- версии
def vdir(proj: Project, n: int) -> Path:
    return proj.output_dir() / f"v{n}"


def versions(proj: Project) -> list[int]:
    """Номера сданных версий по порядку (папки vN с manifest.json)."""
    d = proj.output_dir()
    if not d.exists():
        return []
    return sorted(int(p.name[1:]) for p in d.iterdir()
                  if re.fullmatch(r"v\d+", p.name) and (p / "manifest.json").exists())


def manifest(proj: Project, n: int) -> dict:
    f = vdir(proj, n) / "manifest.json"
    if not f.exists():
        raise SystemExit(f"Версии v{n} нет — python -m studio deliver {proj.slug} --list")
    return json.loads(f.read_text(encoding="utf-8"))


def _sha1(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:12]


# ---------------------------------------------------------------- снимок
def scenes(proj: Project) -> dict:
    """{'ch01/s02': {hash, start, dur, text}} — хэш сцены сценария; начало и длительность — из timeline.json."""
    from .timing import load_timeline
    tl = {f"{s['chapter']}/{s['id']}": s for s in load_timeline(proj)["scenes"]}
    out = {}
    for ch, data in proj.chapters:
        for s in data.get("scenes") or []:
            k = f"{ch}/{s['id']}"
            t = tl.get(k, {})
            out[k] = {"hash": stable_hash(s), "start": round(t.get("start", 0.0), 3), "dur": round(t.get("dur", 0.0), 3),
                      "text": " ".join(l.get("text", "") for l in t.get("lines") or [])[:120]}
    return out


def cfg_hashes(proj: Project) -> dict:
    """Хэш каждого раздела project.yaml (после наследования): что поменяли — style, tts, package…"""
    return {k: stable_hash(v) for k, v in sorted(proj.cfg.items())}


def review_done(t: Project) -> list[dict]:
    from . import review
    return [{"out": t.out, "id": c["id"], "t": c["t"], "scene": f"{c['chapter']}/{c['scene']}", "text": c["text"]}
            for c in review.load(t)["comments"] if c.get("status") == "done"]


def gates(proj: Project, log=print) -> tuple[list[str], list[str]]:
    """Пакет каждого выхода (`package.build`) + проверки сдачи: (ошибки, предупреждения)."""
    from . import review
    errs, warns = [], []
    for t in proj.targets():
        tag = f"[{t.out}] " if t.out else ""
        e, w = package.build(t, log=log)
        errs += [tag + x for x in e]
        warns += [tag + x for x in w]
        qa = package._qa_status(t)
        if qa != "PASS":
            errs.append(f"{tag}QA: {qa} — python -m studio qa {proj.slug}" + (f" --out {t.out}" if t.out else ""))
        r = review.load(t)
        if r["comments"] or review.path(t).exists():
            oc = review.open_comments(r)
            if oc:
                warns.append(f"{tag}ревью: открытых комментариев {len(oc)} ({', '.join(c['id'] for c in oc)})")
            elif r["status"] != "approved":
                warns.append(f"{tag}ревью: версия не утверждена (review --status approved)")
    return errs, warns


def diff(old: dict | None, new: dict) -> dict:
    """Чем версия new отличается от old (манифесты)."""
    if old is None:
        return {"first": True, "scenes": len(new["scenes"]), "duration": new["duration"]}
    os_, ns = old["scenes"], new["scenes"]
    seen = {(c.get("out"), c["id"]) for c in old.get("comments", [])}
    return {
        "first": False,
        "changed": [k for k in ns if k in os_ and ns[k]["hash"] != os_[k]["hash"]],
        "added": [k for k in ns if k not in os_],
        "removed": [k for k in os_ if k not in ns],
        "cfg": [k for k in sorted(set(old["cfg"]) | set(new["cfg"])) if old["cfg"].get(k) != new["cfg"].get(k)],
        "duration": (old["duration"], new["duration"]),
        "files": {f: ("новый" if f not in old["files"] else "изменён") for f, m in new["files"].items()
                  if old["files"].get(f, {}).get("sha1") != m["sha1"]}
                 | {f: "удалён" for f in old["files"] if f not in new["files"]},
        "comments": [c for c in new.get("comments", []) if (c.get("out"), c["id"]) not in seen],
    }


def _mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def summary(d: dict) -> list[str]:
    """Строки отличий для CHANGELOG и `--list`/`--diff`."""
    if d["first"]:
        return [f"- Первая версия: {d['scenes']} сцен, {_mmss(d['duration'])}."]
    out = []
    if d["comments"]:
        out.append(f"- По ревью закрыто комментариев: {len(d['comments'])}")
        out += [f"  - [{c['id']}{'@' + c['out'] if c.get('out') else ''}] {_mmss(c['t'])} {c['scene']}: {c['text']}"
                for c in d["comments"]]
    for key, word in (("changed", "изменены"), ("added", "добавлены"), ("removed", "удалены")):
        if d[key]:
            out.append(f"- Сцены {word} ({len(d[key])}): {', '.join(d[key])}")
    if d["cfg"]:
        out.append(f"- project.yaml, разделы: {', '.join(d['cfg'])}")
    a, b = d["duration"]
    if abs(b - a) >= 0.05:
        out.append(f"- Длительность: {_mmss(a)} → {_mmss(b)} ({b - a:+.1f} с)")
    if d["files"]:
        out.append("- Файлы: " + ", ".join(f"{f} — {s}" for f, s in d["files"].items()))
    return out or ["- Отличий нет: та же сборка."]


# ---------------------------------------------------------------- сдача
def _changelog(proj: Project, n: int, man: dict, lines: list[str]):
    f = proj.root / "CHANGELOG.md"
    text = f.read_text(encoding="utf-8") if f.exists() else CHANGELOG_HEAD.format(slug=proj.slug)
    sec = [f"## v{n} — {man['date']}"]
    if man.get("note"):
        sec += ["", man["note"]]
    if man.get("forced"):
        sec += ["", "⚠️ Сдано с `--force`: " + "; ".join(man["forced"])]
    sec += [""] + lines + [""]
    m = re.search(r"^## v\d+", text, flags=re.M)  # новые сверху: перед первой версией, иначе в конец
    text = (text[:m.start()] + "\n".join(sec) + "\n" + text[m.start():]) if m else text.rstrip() + "\n\n" + "\n".join(sec)
    f.write_text(text, encoding="utf-8")
    return f


def compare(proj: Project, old: dict, new: dict, d: dict, out: Path) -> Path | None:
    """Лист «было → стало»: средний кадр изменённых сцен в прошлом и новом видео первого выхода."""
    from .qa import grab, sheet
    keys = (d["changed"] + d["added"])[:MAX_COMPARE]
    vid = next((f for f in new["files"] if f.endswith(".mp4")), None)
    if not keys or not vid:
        return None
    ov, nv = vdir(proj, old["version"]) / vid, out.parent / vid
    if not ov.exists() or not nv.exists():
        return None
    imgs, labels = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for i, k in enumerate(keys):
            for tag, man, v in (("было", old, ov), ("стало", new, nv)):
                s = man["scenes"].get(k)
                if not s:  # добавленная сцена: слева пусто
                    imgs.append(None); labels.append(f"v{man['version']} {k}: нет")
                    continue
                t = s["start"] + s["dur"] / 2
                im = grab(v, t, Path(tmp) / f"{i}-{tag}.png")
                imgs.append(im.reduce(2) if im.width >= 1000 else im)
                labels.append(f"v{man['version']} {tag} · {k} · {t:.1f}s")
        size = next(im.size for im in imgs if im is not None)
        from PIL import Image
        imgs = [im or Image.new("RGB", size, (30, 30, 30)) for im in imgs]
        return sheet(imgs, labels, 2, out)


def _zip(proj: Project, n: int, files: list[Path]) -> Path:
    z = proj.output_dir() / f"{proj.slug}-v{n}.zip"
    part = z.with_suffix(".zip.part")
    with zipfile.ZipFile(part, "w") as zf:
        for f in files:
            zf.write(f, f"{proj.slug}-v{n}/{f.name}",
                     zipfile.ZIP_STORED if f.suffix in STORED else zipfile.ZIP_DEFLATED)
    part.replace(z)
    return z


def deliver(proj: Project, note: str | None = None, force: bool = False, log=print) -> int | None:
    """Новая версия: пакет → ворота → output/<slug>/vN/ + manifest.json + CHANGELOG.md + compare.jpg + ZIP.
    Возвращает номер версии или None (ворота не пройдены)."""
    errs, warns = gates(proj, log=log)
    for x in warns:
        log(f"  ⚠️ {x}")
    if errs and not force:
        log("❌ Версия не создана:\n" + "\n".join(f"  ❌ {x}" for x in errs) + "\n(--force — сдать всё равно)")
        return None
    prev = versions(proj)
    old = manifest(proj, prev[-1]) if prev else None
    n = (prev[-1] if prev else 0) + 1
    out = vdir(proj, n)
    if out.exists():  # обрыв прошлой сдачи: папка без manifest.json
        shutil.rmtree(out)
    out.mkdir(parents=True)
    src = proj.output_dir()
    files = {}
    for t in proj.targets():
        nm = package.name(t)
        for suf in SUFFIXES:
            f = src / f"{nm}{suf}"
            if f.exists():
                shutil.copy2(f, out / f.name)  # копия, не жёсткая ссылка: assemble перезапишет файл на месте
                files[f.name] = {"size": f.stat().st_size, "sha1": _sha1(f)}
    first = proj.targets()[0]
    from .timing import load_timeline
    man = {"version": n, "slug": proj.slug, "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "note": note or "", "forced": errs, "duration": round(load_timeline(first)["duration"], 2),
           "outputs": [t.out for t in proj.targets() if t.out], "scenes": scenes(first), "cfg": cfg_hashes(proj),
           "files": files, "comments": [c for t in proj.targets() for c in review_done(t)]}  # все закрытые на момент сдачи
    d = diff(old, man)
    lines = summary(d)
    cmp = None
    if old is not None:
        try:
            cmp = compare(proj, old, man, d, out / "compare.jpg")
        except Exception as e:  # лист — подсказка, не повод сорвать сдачу (нет ffmpeg, битое старое видео)
            log(f"  ⚠️ compare.jpg не собран: {e}")
    if cmp:
        lines.append(f"- Кадры «было → стало»: `output/{proj.slug}/v{n}/compare.jpg`")
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ch = _changelog(proj, n, man, lines)
    shutil.copy2(ch, out / "CHANGELOG.md")
    z = _zip(proj, n, sorted(p for p in out.iterdir() if p.name != "manifest.json"))
    log(f"✅ v{n}: {out} ({len(files)} файлов), архив {z.name} ({z.stat().st_size / 1e6:.1f} МБ)")
    for s in lines:
        log("  " + s)
    return n


def listing(proj: Project, log=print):
    vs = versions(proj)
    if not vs:
        log(f"У {proj.slug} сданных версий нет — python -m studio deliver {proj.slug}")
        return
    old = None
    for v in vs:
        m = manifest(proj, v)
        log(f"v{v} — {m['date']}, {_mmss(m['duration'])}, файлов {len(m['files'])}"
            + (f": {m['note']}" if m.get("note") else "") + (" ⚠️ --force" if m.get("forced") else ""))
        for s in summary(diff(old, m)):
            log("  " + s)
        old = m


def compare_versions(proj: Project, a: int, b: int, log=print):
    for s in summary(diff(manifest(proj, a), manifest(proj, b))):
        log(s)

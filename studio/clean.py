"""Чистка build/ проекта (REFACTOR P4.3): всё, что пересобирается командами, с отчётом об освобождённом месте.

Остаются: `timeline.json`, `voice_calibration.json` и озвучка, на которую ссылается таймлайн (`build/tts/`).
Строки TTS, которых в таймлайне нет (старые версии текста), удаляются — кроме платного синтеза (elevenlabs):
там кэш дороже места. `keep_final` оставляет `build/final/` (без черновика) и `mix/levels.json` — по нему qa
проверяет громкость. Рендер после чистки — заново (`render`), это и есть цена места.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from .project import Project

PAID = ("elevenlabs",)
_UNITS = {"h": 3600, "d": 86400, "w": 7 * 86400}


def parse_age(s: str) -> int:
    """'30d' / '12h' / '2w' / '7' (дни) -> секунды."""
    m = re.fullmatch(r"\s*(\d+)\s*([hdw]?)\s*", s)
    if not m:
        raise ValueError(f"возраст: {s!r} — нужно число с h/d/w, например 30d")
    return int(m[1]) * _UNITS[m[2] or "d"]


def last_activity(root: Path) -> float:
    """Время последней правки проекта: самый свежий файл, кроме logs/ (их пишет и сама чистка)."""
    return max((p.stat().st_mtime for p in root.rglob("*") if p.is_file() and "logs" not in p.relative_to(root).parts),
               default=0.0)


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _tts_used(proj: Project):
    """Имена файлов TTS из таймлайна (wav + words.json) или None, если таймлайна нет — тогда TTS не трогаем.
    У проекта с выходами (ROADMAP B3) — из таймлайнов всех выходов; нет хоть одного — None."""
    used = set()
    for o in proj.targets():
        tl = o.build / "timeline.json"
        if not tl.exists():
            return None
        for s in json.loads(tl.read_text(encoding="utf-8")).get("scenes", []):
            for L in s.get("lines", []):
                stem = Path(L["wav"]).stem
                used |= {f"{stem}.wav", f"{stem}.words.json"}
    return used


def targets(proj: Project, keep_final=False):
    """[(группа, путь)] — что удалить."""
    out = []
    for o in proj.targets():  # выходы (ROADMAP B3): build/<выход>/, финалы — output/<slug>/<выход>.*
        out += _build_targets(o, keep_final)
        fin = o.output_dir()
        if o.out and not keep_final and fin.exists():
            out += [("финал", p) for p in sorted(fin.glob(f"{o.out}.*"))]
    b = proj.root / "build"
    used = _tts_used(proj)
    if used is not None and proj.cfg["tts"]["backend"] not in PAID and (b / "tts").exists():
        out += [("TTS вне таймлайна", p) for p in sorted((b / "tts").iterdir()) if p.is_file() and p.name not in used]
    out += [("логи build/", p) for p in sorted(b.glob("*.log"))]  # до studio/log.py логи лежали здесь
    return out


def _build_targets(proj: Project, keep_final):
    b = proj.build
    out = [("сцены", b / d) for d in ("render", "render-draft") if (b / d).exists()]
    if (b / "chapters").exists():
        out.append(("главы", b / "chapters"))
    for p in sorted((b / "mix").glob("*")) if (b / "mix").exists() else []:
        if not (keep_final and p.name == "levels.json"):
            out.append(("микс", p))
    for p in sorted((b / "final").glob("*")) if (b / "final").exists() else []:
        if not keep_final or p.name.endswith(".draft.mp4"):
            out.append(("финал", p))
    return out


def clean(proj: Project, keep_final=False, dry_run=False, log=print) -> int:
    """Удаляет `targets()`, печатает отчёт по группам; возвращает освобождённые байты."""
    by = {}
    for group, p in targets(proj, keep_final):
        n = _size(p)
        if not dry_run:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        by[group] = by.get(group, 0) + n
    total = sum(by.values())
    verb = "освободится" if dry_run else "освобождено"
    for group, n in by.items():
        log(f"  {group:<18} {_mb(n)}")
    log(f"{proj.slug}: {verb} {_mb(total)}" + (" (пробный прогон, ничего не удалено)" if dry_run else ""))
    if proj.cfg["tts"]["backend"] in PAID:
        log("  TTS не тронут: платный синтез, повторная озвучка стоила бы денег")
    return total


def _mb(n: int) -> str:
    return f"{n / 1e6:.1f} МБ"


def stale(root: Path, age: int, now=None) -> bool:
    return (now or time.time()) - last_activity(root) >= age

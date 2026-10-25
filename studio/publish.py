"""Публикация вручную (ROADMAP E1): `python -m studio publish <проект> [--out <выход>]`.

Студия ничего не загружает и не нажимает «опубликовать» — это делает человек. Команда готовит его к загрузке и
запоминает результат:
- без флагов — карточка загрузки каждого выхода: свежий пакет (`package`: MP4, обложка, .srt, описание, чек-лист),
  ворота (нет видео, QA не PASS, ❌ пакета — «не публиковать»), куда загружать, какие файлы в какое поле,
  название, отметка ИИ-контента площадки и что пройти в `<выход>.checklist.md`;
- `--done --url <ссылка> [--at "ГГГГ-ММ-ДД ЧЧ:ММ"]` — человек опубликовал: запись в `published.yaml` проекта
  (вход, в git — `output/` не в git, а история публикаций нужна аналитике E3 и календарю E4): площадка, ссылка,
  время, сданная версия D5 с тем же файлом, sha1 и длительность файла;
- `--list` — что, где и когда опубликовано.
Ворота у `--done` те же, что у карточки: опубликовано непроверенное — отметить можно только с `--force` (с пометкой).
Загрузка через API (ROADMAP E2, только YouTube) — `--api youtube`, studio/youtube.py; запись — тем же `record`.
"""
from __future__ import annotations

import datetime
import re
from urllib.parse import urlparse

import yaml

from . import package
from .project import Project

FILE = "published.yaml"
HEAD = ("# Публикации проекта (ROADMAP E1): python -m studio publish <проект> --done --url <ссылка>.\n"
        "# Пишет команда после ручной загрузки или загрузки через API (--api youtube); поправить ссылку или время руками можно.\n")
# куда загружать вручную: площадка → (страница загрузки, шаги); у рекламы и квадрата — кабинет заказчика
UPLOAD = {
    "youtube": ("https://studio.youtube.com", ("«Создать» → «Загрузить видео»; видимость — сначала «Доступ по "
                "ссылке» или по расписанию, проверить на площадке, потом «Открытый доступ»")),
    "youtube-shorts": ("https://studio.youtube.com", ("«Создать» → «Загрузить видео» (вертикальный ≤ 3 мин станет "
                       "Shorts); видимость — сначала «Доступ по ссылке»")),
    "tiktok": ("https://www.tiktok.com/tiktokstudio/upload", ("загрузить файл, обложку выбрать из файла; "
               "видимость — сначала «Только я», проверить, потом «Все»")),
    "instagram-reels": ("приложение Instagram или https://business.facebook.com", ("«Reels» → файл; обложка — "
                        "«Изменить обложку» → «Добавить из галереи»")),
    "instagram-feed": ("приложение Instagram или https://business.facebook.com", "«Публикация» → файл 4:5"),
}
DOMAINS = {"youtube": ("youtube.com", "youtu.be"), "tiktok": ("tiktok.com",), "instagram": ("instagram.com",)}


# ---------------------------------------------------------------- записи
def path(proj: Project):
    return proj.root / FILE


def load(proj: Project) -> list[dict]:
    f = path(proj)
    if not f.exists():
        return []
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise SystemExit(f"{f}: ожидается список публикаций")
    return data


def _save(proj: Project, recs: list[dict]):
    path(proj).write_text(HEAD + yaml.safe_dump(recs, allow_unicode=True, sort_keys=False), encoding="utf-8")


def of(proj: Project, out: str | None) -> list[dict]:
    """Публикации выхода (у проекта без deliverables — out: None)."""
    return [r for r in load(proj) if r.get("out") == out]


# ---------------------------------------------------------------- ворота
def gates(t: Project, log=print) -> tuple[list[str], list[str]]:
    """Свежий пакет выхода + QA: (ошибки — не публиковать, предупреждения)."""
    errs, warns = package.build(t, log=log)
    qa = package._qa_status(t)
    if qa != "PASS":
        errs.append(f"QA: {qa} — python -m studio qa {t.slug}" + (f" --out {t.out}" if t.out else ""))
    return errs, warns


def _domain_ok(pid: str, url: str) -> bool | None:
    """Ссылка ведёт на площадку выхода? None — площадка без своего домена (реклама, квадрат)."""
    dom = next((d for k, d in DOMAINS.items() if pid.startswith(k)), None)
    if not dom:
        return None
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in dom)


def _version(t: Project, sha: str) -> int | None:
    """Сданная версия (D5), в которой лежит этот же файл."""
    from . import deliver
    nm = f"{package.name(t)}.mp4"
    for n in reversed(deliver.versions(t)):
        if deliver.manifest(t, n)["files"].get(nm, {}).get("sha1") == sha:
            return n
    return None


# ---------------------------------------------------------------- команды
def card(t: Project, log=print) -> bool:
    """Карточка ручной загрузки выхода. True — можно публиковать."""
    from .timing import load_timeline
    errs, warns = gates(t, log=lambda *_: None)
    p, _ = package.platform(t)
    nm = package.name(t)
    d = t.output_dir()
    where, how = UPLOAD.get(p.id, ("кабинет площадки / заказчика", "загрузить файл по требованиям площадки"))
    title = str(package.settings(t).get("title") or t.cfg.get("title") or t.slug).strip()
    log(f"📤 {nm} → {p.name}: {d}")
    for x in errs:
        log(f"  ❌ {x}")
    for x in warns:
        log(f"  ⚠️ {x}")
    if errs:
        log("  Не публиковать: сначала исправить ❌ (python -m studio package / qa).")
    log(f"  Куда: {where} — {how}")
    log(f"  Видео: {nm}.mp4 ({package.tc(load_timeline(t)['duration'])}); обложка: {nm}.cover.jpg"
        + (f"; субтитры: {nm}.srt" if (d / f"{nm}.srt").exists() else ""))
    log(f"  Название: {title}")
    log(f"  {'Описание' if p.title_max else 'Подпись'}: блок из {nm}.description.md — целиком")
    if p.ai:
        log(f"  ИИ-контент: {p.ai}")
    log(f"  Перед кнопкой «Опубликовать» — пройти {nm}.checklist.md")
    done = of(t, t.out)
    if done:
        log("  Уже опубликовано: " + "; ".join(f"{r['date']} {r['url']}" for r in done))
    log(f"  После публикации: python -m studio publish {t.slug}" + (f" --out {t.out}" if t.out else "")
        + " --done --url <ссылка>")
    return not errs


def record(t: Project, url: str, at: str | None = None, note: str | None = None, force: bool = False,
           extra: dict | None = None, log=print) -> dict | None:
    """Отметить публикацию выхода в published.yaml (вручную; `extra` — поля загрузки через API, E2).
    None — ворота не пройдены (без --force)."""
    from .deliver import _sha1
    from .timing import load_timeline
    p, _ = package.platform(t)
    if not re.match(r"https?://", url or ""):
        raise SystemExit(f"--url: нужна ссылка на ролик на площадке (https://…), получено: {url!r}")
    errs, warns = gates(t, log=lambda *_: None)
    if _domain_ok(p.id, url) is False:
        errs.append(f"ссылка {urlparse(url).hostname} — не {p.name}")
    for x in warns:
        log(f"  ⚠️ {x}")
    if errs and not force:
        log("❌ Публикация не отмечена:\n" + "\n".join(f"  ❌ {x}" for x in errs) + "\n(--force — отметить всё равно)")
        return None
    if at:
        try:
            when = datetime.datetime.strptime(at, "%Y-%m-%d %H:%M")
        except ValueError:
            raise SystemExit(f"--at: время как «ГГГГ-ММ-ДД ЧЧ:ММ», получено: {at!r}")
    else:
        when = datetime.datetime.now()
    video = t.output_dir() / f"{package.name(t)}.mp4"
    sha = _sha1(video) if video.exists() else None
    rec = {"out": t.out, "platform": p.id, "url": url, "date": when.strftime("%Y-%m-%d %H:%M"),
           "version": _version(t, sha) if sha else None, "file": video.name, "sha1": sha,
           "duration": round(load_timeline(t)["duration"], 2)}
    if note:
        rec["note"] = note
    rec.update(extra or {})
    if errs:
        rec["forced"] = errs
    recs = [r for r in load(t) if r.get("url") != url]  # та же ссылка — обновить запись, не дублировать
    recs.append(rec)
    _save(t, recs)
    done = f"загружен ({rec['privacy']})" if rec.get("via") == "api" and rec.get("privacy") != "public" else "опубликован"
    log(f"✅ {package.name(t)} {done}: {url} ({rec['date']}"
        + (f", версия v{rec['version']}" if rec["version"] else ", вне сданных версий") + f") → {FILE}")
    return rec


def listing(proj: Project, log=print):
    recs = load(proj)
    if not recs:
        log(f"У {proj.slug} публикаций нет — python -m studio publish {proj.slug}")
        return
    for r in recs:
        log(f"{r['date']} · {r.get('out') or proj.slug} → {r['platform']}: {r['url']}"
            + (f" (v{r['version']})" if r.get("version") else "") + (" ⚠️ --force" if r.get("forced") else ""))


def summary(proj: Project) -> str:
    """Строка для status: где опубликован проект."""
    recs = load(proj)
    if not recs:
        return f"не опубликован (вручную: python -m studio publish {proj.slug})"
    return "; ".join(f"{r.get('out') or r['platform']} {r['date'][:10]}" for r in recs)

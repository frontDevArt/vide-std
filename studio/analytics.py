"""Аналитика студии (ROADMAP E3): цифры опубликованных роликов → `studios/<id>/analytics/` → радар тем и брифы.

`python -m studio --studio <id> analytics` — ролики студии из `published.yaml` всех её проектов (E1/E2) с тем, что о них
знает сценарий (рубрика из шапки `chrome.rubric`, вердикт, длина, площадка, хук — первая реплика), и их цифры:
- `--fetch` — YouTube: YouTube Analytics API (просмотры, время, средний просмотр в секундах и %, лайки, комментарии,
  подписки; удержание — кривая `audienceWatchRatio`: на 3-й секунде, на середине и у конца) и YouTube Reporting API
  (показы значка и CTR — в Analytics API их нет, только в массовом отчёте `channel_reach_basic_a1`: задание создаётся
  при первом запуске, отчёты по дням появляются через сутки-двое, скачанные — кэш `analytics/reach/`);
- `--import <csv>` — выгрузка таблицы из YouTube Studio («Аналитика» → «Расширенный режим» → «Экспорт» → CSV);
- `--set <ссылка> views=… ctr=…` — руками: TikTok и Instagram (их API аналитики без проверки приложения не дают).
Только чтение: ничего не меняет на площадках и ничего не стоит (квота Analytics API — запрос на ролик).
Доступ — вход E2 (`studio/youtube.py`) с правом `yt-analytics.readonly`; старый вход — `analytics --auth`.

Итог — `analytics/videos.yaml` (вход, в git: цифры по ссылке ролика, у каждой — откуда и когда) и
`analytics/REPORT.md`: таблица роликов и «что зашло» по рубрикам, длинам, площадкам и хукам — его читают
`/topic-radar` и `/topic-to-brief` и ссылаются на эти цифры.
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import re
import statistics
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import yaml

from . import package, publish, workspace, youtube
from .project import Project, load

DIR = "analytics"
FILE = "videos.yaml"
REPORT = "REPORT.md"
HEAD = ("# Цифры роликов студии (ROADMAP E3): python -m studio --studio <id> analytics [--fetch | --import | --set].\n"
        "# Поля ролика берутся из проекта заново при каждом запуске; metrics/sources — копятся (руками можно).\n")
ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
REPORTING_URL = "https://youtubereporting.googleapis.com/v1"
REACH = "channel_reach_basic_a1"
# метрика → (подпись, единица); проценты — числом 0–100
METRICS = {
    "views": ("просмотры", ""), "watch_min": ("время просмотра", " мин"), "avg_view_s": ("средний просмотр", " с"),
    "avg_view_pct": ("досмотр", " %"), "ret_3s": ("на 3-й секунде", " %"), "ret_50": ("на середине", " %"),
    "ret_end": ("у конца", " %"), "impressions": ("показы значка", ""), "ctr": ("CTR", " %"),
    "likes": ("лайки", ""), "comments": ("комментарии", ""), "subs": ("подписки", ""),
}
API = {"views": "views", "estimatedMinutesWatched": "watch_min", "averageViewDuration": "avg_view_s",
       "averageViewPercentage": "avg_view_pct", "likes": "likes", "comments": "comments",
       "subscribersGained": "subs"}
LENGTHS = ((60, "Shorts ≤ 1 мин"), (300, "1–5 мин"), (900, "5–15 мин"), (float("inf"), "15+ мин"))
FEW = 3  # меньше роликов в группе — «мало данных», сигнал, а не вывод


def folder(ws: workspace.Workspace) -> Path:
    return ws.root / DIR


def today() -> str:
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------- ролики студии
def video_id(url: str) -> str | None:
    """ID ролика YouTube из ссылки (watch?v=, youtu.be/, /shorts/)."""
    u = urlparse(url or "")
    host = (u.hostname or "").lower()
    if host.endswith("youtu.be"):
        return u.path.strip("/") or None
    if host.endswith("youtube.com"):
        if parse_qs(u.query).get("v"):
            return parse_qs(u.query)["v"][0]
        m = re.match(r"/(?:shorts|live)/([\w-]+)", u.path)
        return m.group(1) if m else None
    return None


def _scenes(t: Project):
    for _, ch in t.chapters:
        yield from ch.get("scenes") or []


def rubric(t: Project) -> str | None:
    """Рубрика ролика — из шапки lab (`params.chrome.rubric`) первой сцены, где она есть."""
    for sc in _scenes(t):
        r = ((sc.get("params") or {}).get("chrome") or {}).get("rubric")
        if r:
            return str(r)
    return None


def hook(t: Project) -> str:
    """Хук — первая реплика ролика (без `|` и `*`)."""
    for sc in _scenes(t):
        for line in sc.get("lines") or []:
            return re.sub(r"\s+", " ", str(line).replace("|", " ").replace("*", "")).strip()
    return ""


def collect(ws: workspace.Workspace) -> list[dict]:
    """Опубликованные ролики студии: запись `published.yaml` + сведения из сценария."""
    rows = []
    for root in workspace.projects(ws):
        proj = load(root)
        for r in publish.load(proj):
            t = proj.output(r["out"]) if r.get("out") else proj
            rows.append({
                "url": r["url"], "project": proj.slug, "out": r.get("out"), "platform": r.get("platform"),
                "video_id": r.get("video_id") or video_id(r["url"]), "published": r.get("date"),
                "privacy": r.get("privacy") or "public", "duration": r.get("duration"),
                "title": str(package.settings(t).get("title") or t.cfg.get("title") or proj.slug),
                "rubric": rubric(t), "verdict": package.verdict(t), "format": t.cfg.get("format"), "hook": hook(t)})
    return rows


def stored(ws: workspace.Workspace) -> dict[str, dict]:
    f = folder(ws) / FILE
    if not f.exists():
        return {}
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise SystemExit(f"{f}: ожидается список роликов")
    return {r["url"]: r for r in data if isinstance(r, dict) and r.get("url")}


def videos(ws: workspace.Workspace) -> list[dict]:
    """Ролики студии с накопленными цифрами (сведения — свежие из проектов, metrics/sources — из videos.yaml).
    Ролик пропал из published.yaml, а цифры есть — остаётся (история канала не теряется)."""
    old = stored(ws)
    rows = collect(ws)
    for r in rows:
        prev = old.pop(r["url"], {})
        r["metrics"], r["sources"] = prev.get("metrics") or {}, prev.get("sources") or {}
    return rows + [r for r in old.values() if r.get("metrics")]


def save(ws: workspace.Workspace, rows: list[dict]):
    d = folder(ws)
    d.mkdir(parents=True, exist_ok=True)
    (d / FILE).write_text(HEAD + yaml.safe_dump(rows, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _put(r: dict, vals: dict, source: str):
    for k, v in vals.items():
        if v is None:
            continue
        r.setdefault("metrics", {})[k] = round(float(v), 2) if not float(v).is_integer() else int(v)
        r.setdefault("sources", {})[k] = f"{source} {today()}"


# ---------------------------------------------------------------- YouTube: Analytics API + Reporting API
def can_read(tok: dict) -> bool:
    return youtube.ANALYTICS in (tok.get("scope") or "").split()


def _get(tok: str, url: str, what: str) -> bytes:
    st, _, b = youtube._http("GET", url, {"Authorization": f"Bearer {tok}"})
    if st != 200:
        raise youtube._error(st, b, what)
    return b


def _table(b: bytes) -> list[dict]:
    d = json.loads(b or b"{}")
    names = [h["name"] for h in d.get("columnHeaders") or []]
    return [dict(zip(names, row)) for row in d.get("rows") or []]


def _at(curve: list[tuple[float, float]], x: float) -> float | None:
    """Доля зрителей (%) в точке кривой удержания: первая точка ≥ x."""
    for pos, ratio in curve:
        if pos >= x - 1e-9:
            return ratio * 100
    return None


def fetch(ws: workspace.Workspace, rows: list[dict], log=print) -> int:
    """Цифры роликов YouTube через API. Возвращает, у скольких обновлены."""
    yt = [r for r in rows if r.get("video_id") and str(r.get("platform", "")).startswith("youtube")
          and r.get("project")]
    if not yt:
        log("YouTube: опубликованных роликов с ссылкой YouTube нет — нечего запрашивать")
        return 0
    if not can_read(youtube.token(ws)):
        raise SystemExit("YouTube: вход без права читать аналитику — войти заново: "
                         "python -m studio --studio " + ws.id + " analytics --auth")
    tok = youtube.access(ws)
    start = min(str(r.get("published") or today())[:10] for r in yt)
    q = {"ids": "channel==MINE", "startDate": start, "endDate": today(), "dimensions": "video",
         "metrics": ",".join(API), "filters": "video==" + ",".join(r["video_id"] for r in yt), "maxResults": 200}
    got = {x["video"]: x for x in _table(_get(tok, ANALYTICS_URL + "?" + urlencode(q), "аналитика роликов"))}
    for r in yt:
        x = got.get(r["video_id"])
        vals = {API[k]: (x or {}).get(k, 0) for k in API}  # ролика нет в ответе — просмотров ещё нет (нули)
        q = {"ids": "channel==MINE", "startDate": start, "endDate": today(), "dimensions": "elapsedVideoTimeRatio",
             "metrics": "audienceWatchRatio", "filters": f"video=={r['video_id']}"}
        curve = sorted((float(c["elapsedVideoTimeRatio"]), float(c["audienceWatchRatio"]))
                       for c in _table(_get(tok, ANALYTICS_URL + "?" + urlencode(q), "удержание")))
        if curve:
            dur = float(r.get("duration") or 0) or 60.0
            vals.update(ret_3s=_at(curve, min(3 / dur, 1)), ret_50=_at(curve, 0.5), ret_end=_at(curve, 0.95))
        _put(r, vals, "api")
    log(f"✅ YouTube Analytics: {len(yt)} ролик(ов), {start} … {today()}")
    reach(ws, tok, yt, log)
    return len(yt)


def reach(ws: workspace.Workspace, tok: str, rows: list[dict], log=print):
    """Показы значка и CTR — массовый отчёт Reporting API (в Analytics API этих метрик нет)."""
    jobs = json.loads(_get(tok, REPORTING_URL + "/jobs", "задания отчётов")).get("jobs") or []
    job = next((j for j in jobs if j.get("reportTypeId") == REACH), None)
    if not job:
        st, _, b = youtube._http("POST", REPORTING_URL + "/jobs", {
            "Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"},
            json.dumps({"reportTypeId": REACH, "name": "studio reach"}).encode())
        if st != 200:
            raise youtube._error(st, b, "задание отчёта показов")
        log("⏳ CTR: задание отчёта показов создано — первые отчёты YouTube выложит через сутки-двое, "
            "тогда повторите --fetch (или --import CSV из YouTube Studio)")
        return
    cache = folder(ws) / "reach"
    cache.mkdir(parents=True, exist_ok=True)
    url, new = f"{REPORTING_URL}/jobs/{job['id']}/reports", 0
    while url:
        d = json.loads(_get(tok, url, "список отчётов показов"))
        for rep in d.get("reports") or []:
            f = cache / f"{rep['id']}.csv"
            if not f.exists():
                f.write_bytes(_get(tok, rep["downloadUrl"], "отчёт показов"))
                new += 1
        nxt = d.get("nextPageToken")
        url = f"{REPORTING_URL}/jobs/{job['id']}/reports?" + urlencode({"pageToken": nxt}) if nxt else None
    imp: dict[str, float] = {}
    clicks: dict[str, float] = {}
    for f in sorted(cache.glob("*.csv")):
        for x in csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))):
            n = float(x.get("video_thumbnail_impressions") or 0)
            c = float(x.get("video_thumbnail_impressions_ctr") or 0)
            vid = x.get("video_id")
            imp[vid] = imp.get(vid, 0) + n
            clicks[vid] = clicks.get(vid, 0) + n * (c / 100 if c > 1 else c)  # доля или проценты — обе формы
    have = 0
    for r in rows:
        n = imp.get(r["video_id"])
        if n:
            _put(r, {"impressions": n, "ctr": clicks[r["video_id"]] / n * 100}, "reach")
            have += 1
    log(f"✅ CTR: отчётов показов {len(list(cache.glob('*.csv')))} (новых {new}), с показами — {have} ролик(ов)")


# ---------------------------------------------------------------- руками: CSV из YouTube Studio, --set
def _seconds(v: str) -> float:
    parts = [float(p) for p in str(v).strip().split(":")]
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def _num(v: str) -> float | None:
    v = str(v or "").strip().replace(" ", "").replace(" ", "").replace("%", "")
    if not v or v in ("-", "—"):
        return None
    try:
        return _seconds(v) if ":" in v else float(v.replace(",", "."))
    except ValueError:
        return None


# заголовок колонки выгрузки Studio (англ. или рус. интерфейс, нижний регистр) → метрика; порядок важен
COLUMNS = (
    ("ctr", lambda h: "click-through" in h or "ctr" in h),
    ("impressions", lambda h: h in ("impressions", "показы")),
    ("avg_view_pct", lambda h: "average percentage viewed" in h or "средний процент просмотра" in h),
    ("avg_view_s", lambda h: "average view duration" in h or "средняя продолжительность просмотра" in h),
    ("watch_min", lambda h: h.startswith("watch time (hours)") or h.startswith("время просмотра (часы)")),
    ("views", lambda h: h in ("views", "просмотры")),
    ("likes", lambda h: h == "likes" or "нравится" in h),
    ("comments", lambda h: h.startswith("comments") or h.startswith("комментари")),
    ("subs", lambda h: h in ("subscribers", "подписчики")),
)


def import_csv(rows: list[dict], file: Path, log=print) -> int:
    """Выгрузка таблицы YouTube Studio: строки по ID ролика (колонка «Content»/«Контент») или названию."""
    text = Path(file).read_text(encoding="utf-8-sig")
    data = list(csv.DictReader(io.StringIO(text)))
    if not data:
        raise SystemExit(f"{file}: пустая таблица")
    heads = {h: h.strip().lower() for h in data[0]}
    idcol = next((h for h, l in heads.items() if l in ("content", "контент", "video", "видео")), None)
    tcol = next((h for h, l in heads.items() if l in ("video title", "название видео")), None)
    cols = {}
    for h, l in heads.items():
        m = next((k for k, ok in COLUMNS if ok(l)), None)
        if m and m not in cols.values():
            cols[h] = m
    if not cols or not (idcol or tcol):
        raise SystemExit(f"{file}: не похоже на выгрузку YouTube Studio (колонки: {', '.join(data[0])})")
    by_id = {r["video_id"]: r for r in rows if r.get("video_id")}
    by_title = {r["title"].strip().lower(): r for r in rows}
    hit, miss = 0, []
    for x in data:
        key = (x.get(idcol) or "").strip() if idcol else ""
        if key.lower() in ("total", "итого", "всего"):
            continue
        r = by_id.get(key) or by_title.get((x.get(tcol) or "").strip().lower() if tcol else "")
        if not r:
            miss.append(key or (x.get(tcol) or "?"))
            continue
        vals = {m: _num(x[h]) for h, m in cols.items()}
        if vals.get("watch_min") is not None:
            vals["watch_min"] *= 60  # выгрузка — в часах
        _put(r, vals, f"csv {Path(file).name}")
        hit += 1
    log(f"✅ {Path(file).name}: {hit} ролик(ов), колонки — {', '.join(sorted(set(cols.values())))}")
    if miss:
        log(f"  ⚠️ не из опубликованных студии (пропущены): {', '.join(miss[:8])}" + (" …" if len(miss) > 8 else ""))
    return hit


def set_manual(rows: list[dict], url: str, pairs: list[str], log=print) -> dict:
    """`--set <ссылка> views=1200 ctr=4.1 avg_view_pct=55` — цифры площадки без API (TikTok, Instagram)."""
    r = next((x for x in rows if x["url"] == url or (video_id(url) and x.get("video_id") == video_id(url))), None)
    if not r:
        raise SystemExit(f"--set: ролика {url} нет среди опубликованных студии (сначала publish --done --url)")
    vals = {}
    for p in pairs:
        k, _, v = p.partition("=")
        if k not in METRICS or _num(v) is None:
            raise SystemExit(f"--set: «{p}» — нужно метрика=число, метрики: {', '.join(METRICS)}")
        vals[k] = _num(v)
    _put(r, vals, "manual")
    log(f"✅ {r['project']}{'/' + r['out'] if r.get('out') else ''}: " + ", ".join(f"{k}={v}" for k, v in vals.items()))
    return r


# ---------------------------------------------------------------- отчёт
def _fmt(v, unit: str = "") -> str:
    if v is None:
        return "—"
    v = float(v)
    if unit == " с" and v >= 60:
        return f"{int(v // 60)}:{int(v % 60):02d}"
    return (f"{v:.1f}" if not v.is_integer() and v < 100 else f"{v:,.0f}".replace(",", " ")) + \
        (unit if unit != " мин" else " мин")


def length(r: dict) -> str:
    d = float(r.get("duration") or 0)
    return next(name for lim, name in LENGTHS if d <= lim)


def _name(r: dict) -> str:
    return r["project"] + (f"/{r['out']}" if r.get("out") else "")


def _group(rows: list[dict], key) -> list[tuple[str, list[dict]]]:
    g: dict[str, list[dict]] = {}
    for r in rows:
        g.setdefault(key(r) or "—", []).append(r)
    return sorted(g.items(), key=lambda kv: -_median(kv[1], "views"))


def _median(rows: list[dict], k: str) -> float:
    v = [r["metrics"][k] for r in rows if r["metrics"].get(k) is not None]
    return statistics.median(v) if v else -1


def _mean(rows: list[dict], k: str) -> float | None:
    v = [r["metrics"][k] for r in rows if r["metrics"].get(k) is not None]
    return sum(v) / len(v) if v else None


def report(ws: workspace.Workspace, rows: list[dict]) -> Path:
    """`analytics/REPORT.md`: таблица роликов, группы (рубрика, длина, площадка), хуки, выводы с цифрами."""
    has = [r for r in rows if r["metrics"].get("views") is not None]
    out = [f"# Аналитика студии {ws.name} — {today()}", "",
           "Собрано: `python -m studio --studio " + ws.id + " analytics` (ROADMAP E3). Цифры — накопленные с даты "
           "публикации; откуда каждая — `videos.yaml`, поле `sources`. Радар и брифы ссылаются на этот файл.", ""]
    if not rows:
        out += ["Опубликованных роликов нет — `publish --done --url` (E1) или `publish --api youtube --yes` (E2)."]
    elif not has:
        out += ["Цифр пока нет: `analytics --fetch` (YouTube), `--import <csv>` (YouTube Studio), "
                "`--set <ссылка> views=…` (TikTok, Instagram)."]
    out += ["", "## Ролики", "",
            "| Ролик | Площадка | Вышел | Рубрика | Длина | Просмотры | Досмотр | 3 с | Середина | CTR | Хук |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: str(r.get("published") or ""), reverse=True):
        m = r["metrics"]
        priv = "" if r.get("privacy") in (None, "public") else f" ({r['privacy']})"
        out.append(f"| [{_name(r)}]({r['url']}) | {r.get('platform')}{priv} | {str(r.get('published') or '')[:10]} | "
                   f"{r.get('rubric') or '—'} | {package.tc(float(r.get('duration') or 0))} | {_fmt(m.get('views'))} | "
                   f"{_fmt(m.get('avg_view_pct'), ' %')} | {_fmt(m.get('ret_3s'), ' %')} | "
                   f"{_fmt(m.get('ret_50'), ' %')} | {_fmt(m.get('ctr'), ' %')} | {r.get('hook', '')[:70]} |")
    if has:
        out += ["", "## Что зашло", ""]
        for title, key in (("Рубрики", lambda r: r.get("rubric")), ("Длина", length),
                           ("Площадки", lambda r: r.get("platform"))):
            out += [f"### {title}", "", "| Группа | Роликов | Просмотры (медиана) | Досмотр (ср.) | CTR (ср.) |",
                    "|---|---|---|---|---|"]
            groups = _group(has, key)
            for name, g in groups:
                few = " ⚠️ мало данных" if len(g) < FEW else ""
                out.append(f"| {name}{few} | {len(g)} | {_fmt(_median(g, 'views'))} | "
                           f"{_fmt(_mean(g, 'avg_view_pct'), ' %')} | {_fmt(_mean(g, 'ctr'), ' %')} |")
            out.append("")
        out += ["### Хуки (по удержанию на 3-й секунде, иначе по досмотру)", ""]
        top = sorted(has, key=lambda r: (r["metrics"].get("ret_3s") or -1, r["metrics"].get("avg_view_pct") or -1),
                     reverse=True)
        for r in top[:5]:
            m = r["metrics"]
            out.append(f"- «{r.get('hook')}» — {_name(r)}: 3 с {_fmt(m.get('ret_3s'), ' %')}, досмотр "
                       f"{_fmt(m.get('avg_view_pct'), ' %')}, просмотры {_fmt(m.get('views'))}")
        out += ["", "## Выводы для радара", ""] + conclusions(has)
    f = folder(ws) / REPORT
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(out) + "\n", encoding="utf-8")
    return f


def conclusions(has: list[dict]) -> list[str]:
    """Короткие выводы с цифрами — то, на что ссылается радар. Мало роликов — так и сказано."""
    lines = []
    if len(has) < FEW:
        lines.append(f"- ⚠️ Роликов с цифрами {len(has)} (< {FEW}) — это сигналы, а не закономерности; "
                     "радар упоминает их, но не перестраивает микс.")
    if all(r.get("privacy") not in (None, "public") for r in has):
        lines.append("- Все ролики с цифрами не открыты (private/unlisted) — просмотры ещё не от зрителей.")
    best = max(has, key=lambda r: r["metrics"].get("views") or 0)
    m = best["metrics"]
    lines.append(f"- Больше всего просмотров: {_name(best)} ({best.get('rubric') or 'без рубрики'}, {length(best)}) — "
                 f"{_fmt(m.get('views'))}, досмотр {_fmt(m.get('avg_view_pct'), ' %')}, CTR {_fmt(m.get('ctr'), ' %')}.")
    for title, key in (("рубрика", lambda r: r.get("rubric")), ("длина", length)):
        groups = [(n, g) for n, g in _group(has, key) if n != "—"]
        if len(groups) >= 2:
            (n1, g1), (n2, g2) = groups[0], groups[-1]
            lines.append(f"- Лучшая {title}: {n1} — медиана {_fmt(_median(g1, 'views'))} просмотров "
                         f"(n={len(g1)}) против {_fmt(_median(g2, 'views'))} у «{n2}» (n={len(g2)}).")
    hooked = [r for r in has if r["metrics"].get("ret_3s") is not None]
    if hooked:
        h = max(hooked, key=lambda r: r["metrics"]["ret_3s"])
        lines.append(f"- Лучший хук: «{h.get('hook')}» ({_name(h)}) — {_fmt(h['metrics']['ret_3s'], ' %')} "
                     "зрителей на 3-й секунде.")
    return lines


def table(rows: list[dict], log=print):
    for r in rows:
        m = r["metrics"]
        nums = ", ".join(f"{METRICS[k][0]} {_fmt(v, METRICS[k][1])}" for k, v in m.items() if k in METRICS)
        log(f"{str(r.get('published') or '')[:10]} · {_name(r)} → {r.get('platform')}: {nums or 'цифр нет'}")

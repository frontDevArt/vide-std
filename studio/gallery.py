"""python -m studio gallery — HTML-страница с превью каждого шаблона в каждом формате (ROADMAP C4).

Кадры — из фикстур selftest: tests/fixtures/gallery (базовые и lab) и tests/fixtures/library (kit, commerce, media),
голос fake, офлайн. На шаблон — сцены фикстур в каждом формате, по 5 кадров (наведение — проигрывание), описание,
биты и параметры из метаданных шаблона (те же, что у `python -m studio templates`); отдельно — режимы субтитров
(плашка, караоке, крупные TikTok). Шаблон без сцены в фикстурах — в списке «нет в галерее» (test_gallery это ловит).
Страница и кадры — output/gallery/ в корне студии (не в git).
"""
from __future__ import annotations

import html
import json
import os
import shutil
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .project import STUDIO_ROOT

OUT = STUDIO_ROOT / "output" / "gallery"
FRACS = (0.1, 0.3, 0.5, 0.7, 0.92)  # кадры сцены для превью: от входа до «всё вышло»
SHOW = 3                            # кадр по умолчанию (0,7 сцены)
SUB_MODES = ("plate", "karaoke", "tiktok")
SUB_SCENE = ("ch01", "s02")         # сцена library для режимов субтитров
FORMAT_NAMES = {"horizontal": "16:9", "vertical": "9:16", "square": "1:1", "portrait": "4:5"}


def _fixture(name, dst, fmt, subs=None):
    from . import selftest
    if name == "gallery":
        return selftest.make_gallery(dst, fmt)
    return selftest.make_library(dst, fmt, subs)


def _shoot(job):
    """Воркер: (фикстура, формат, режим субтитров | None, папка кадров, рабочая папка) → [{template, …, frames}]."""
    name, fmt, subs, out, work = job
    from . import project, render, selftest, timing
    from . import subs as S
    from .packs import REGISTRY
    selftest.pin_fonts()
    root = _fixture(name, Path(work) / f"{name}-{fmt}-{subs or 'x'}" / name, fmt, subs)
    proj = project.load(root)
    timing.layout(proj, log=lambda *_a, **_k: None)
    tl, ctx = render.prepare(proj)
    size = S.font_size(proj)
    d = Path(out) / fmt
    d.mkdir(parents=True, exist_ok=True)
    res = []
    for s in tl["scenes"]:
        if subs and (s["chapter"], s["id"]) != SUB_SCENE:
            continue
        tpl = render.make_template(ctx, s)
        frames = []
        for i, fr in enumerate(FRACS):
            f = min(s["n_frames"] - 1, int(s["n_frames"] * fr))
            img = render.frame(ctx, tpl, s, f, size).convert("RGB")
            img = img.reduce(4 if max(img.size) > 1400 else 3)
            fn = f"{name}-{subs + '-' if subs else ''}{s['chapter']}-{s['id']}-{i}.jpg"
            img.save(d / fn, quality=84)
            frames.append(f"img/{fmt}/{fn}")
        res.append({"template": f"subtitles.{subs}" if subs else REGISTRY.canonical(s["template"]),
                    "fixture": name, "scene": f"{s['chapter']}/{s['id']}", "format": fmt,
                    "dur": round(s["dur"], 2), "frames": frames})
    return res


def build(formats=None, out: Path | None = None, workers=None, log=print) -> Path:
    """Снять кадры и собрать out/index.html. Возвращает путь к странице."""
    from .config import FORMATS as ALL
    formats = [f for f in (formats or list(ALL)) if f in ALL] or list(ALL)
    out = Path(out or OUT)
    img = out / "img"
    shutil.rmtree(img, ignore_errors=True)
    work = tempfile.mkdtemp(prefix="studio-gallery-")
    jobs = [(n, f, None, str(img), work) for n in ("gallery", "library") for f in formats]
    jobs += [(n, f, m, str(img), work) for f in formats for m in SUB_MODES for n in ("library",)]
    t0 = time.time()
    workers = workers or max(1, min(len(jobs), (os.cpu_count() or 2) - 1, 6))
    log(f"gallery: {len(formats)} формата, {len(jobs)} заданий, воркеров {workers}; кадры — {img}")
    entries = []
    try:
        with ProcessPoolExecutor(workers) as ex:
            for res in ex.map(_shoot, jobs):
                entries += res
    finally:
        shutil.rmtree(work, ignore_errors=True)
    page = out / "index.html"
    page.write_text(render_html(entries, formats), encoding="utf-8")
    missing = absent(entries)
    log(f"✅ {page} — {len({e['template'] for e in entries})} шаблонов и режимов, {len(entries)} сцен, "
        f"{time.time() - t0:.0f} c")
    if missing:
        log(f"⚠️  нет в галерее (добавьте сцену в tests/fixtures/library): {', '.join(missing)}")
    return page


def absent(entries) -> list[str]:
    from .packs import REGISTRY
    seen = {e["template"] for e in entries}
    return sorted(n for n, c in REGISTRY.templates().items()
                  if n not in seen and not n.startswith("project.") and not getattr(c, "REQUIRES", None))  # web.html (C6)


# ------------------------------------------------------------------ HTML
PACKS = {"core": "core — общие текстовые", "kit": "kit — библиотека для любой палитры (C4)",
         "media": "media — фото, видео, экран, клип, бренд (C2)", "commerce": "commerce — цены и суммы",
         "phone": "phone — телефон и лента", "lab": "lab — канал Notes From The Mind",
         "subtitles": "Субтитры — subtitles.style"}
SUB_DOC = {"plate": "Плашка под текстом: по умолчанию у палитр без пресета.",
           "karaoke": "Караоке: слова загораются по мере произнесения (пресет lab).",
           "tiktok": "Крупные TikTok-субтитры: без плашки, обводка, звучащее слово — акцентом, выше интерфейса "
                     "площадки. subtitles: {style: tiktok} в project.yaml или subs: tiktok в бренд-ките."}


def _e(s):
    return html.escape(str(s), quote=True)


def _card(name, items, formats):
    from .packs import REGISTRY
    if name.startswith("subtitles."):
        mode = name.split(".", 1)[1]
        head, doc, beats, params, al, fm = name, SUB_DOC.get(mode, ""), "", {}, [], None
    else:
        cls = REGISTRY[name]
        head, doc, beats, params = name, cls.DOC, cls.BEATS, cls.PARAMS
        al, fm = REGISTRY.aliases(name), cls.FORMATS
    shots = []
    for fmt in formats:
        for e in (x for x in items if x["format"] == fmt):
            fr = json.dumps(e["frames"])
            shots.append(f'<figure class="shot f-{fmt}" data-frames=\'{_e(fr)}\'>'
                         f'<img loading="lazy" src="{_e(e["frames"][SHOW])}" alt="{_e(name)} {fmt}">'
                         f'<figcaption>{FORMAT_NAMES.get(fmt, fmt)} · {_e(e["scene"])} · {e["dur"]:g} c</figcaption>'
                         f'</figure>')
    rows = "".join(f"<tr><td><code>{_e(k)}</code></td><td>{_e(p)}</td></tr>" for k, p in params.items())
    meta = []
    if al:
        meta.append("алиас: " + ", ".join(f"<code>{_e(a)}</code>" for a in al))
    if fm and len(fm) < 4:
        meta.append("форматы: " + ", ".join(fm))
    return (f'<article class="card" id="{_e(name)}" data-name="{_e(name + " " + " ".join(al) + " " + doc).lower()}">'
            f'<h3>{_e(head)}</h3>' + (f'<p class="meta">{" · ".join(meta)}</p>' if meta else "")
            + f'<p>{_e(doc)}</p>' + (f'<p class="beats">Биты: {_e(beats)}</p>' if beats else "")
            + f'<div class="shots">{"".join(shots)}</div>'
            + (f'<details><summary>Параметры ({len(params)})</summary><table>{rows}</table></details>' if params else "")
            + "</article>")


def render_html(entries, formats) -> str:
    by = {}
    for e in entries:
        by.setdefault(e["template"], []).append(e)
    groups = {}
    for name in sorted(by):
        groups.setdefault(name.split(".", 1)[0], []).append(name)
    order = [p for p in PACKS if p in groups] + sorted(set(groups) - set(PACKS))
    nav = " ".join(f'<a href="#pack-{p}">{_e(p)}</a>' for p in order)
    btns = "".join(f'<button class="fmt on" data-fmt="{f}">{FORMAT_NAMES.get(f, f)}</button>' for f in formats)
    body = "".join(f'<section id="pack-{p}"><h2>{_e(PACKS.get(p, p))}</h2>'
                   + "".join(_card(n, by[n], formats) for n in groups[p]) + "</section>" for p in order)
    miss = absent(entries)
    warn = (f'<p class="warn">Нет в галерее: {", ".join(_e(m) for m in miss)}</p>' if miss else "")
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Шаблоны студии</title>
<style>
:root {{ --bg: #0b0e15; --panel: #141a28; --text: #e8ecf3; --dim: #8b95a7; --acc: #3dd6f5; --line: #253049; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 system-ui, sans-serif; }}
header {{ position: sticky; top: 0; z-index: 2; background: rgba(11,14,21,.94); border-bottom: 1px solid var(--line);
  padding: 12px 16px; display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; }}
header h1 {{ font-size: 18px; margin: 0 8px 0 0; }}
header a {{ color: var(--dim); text-decoration: none; }} header a:hover {{ color: var(--acc); }}
input {{ background: var(--panel); color: var(--text); border: 1px solid var(--line); border-radius: 8px;
  padding: 6px 10px; min-width: 200px; }}
button.fmt {{ background: var(--panel); color: var(--dim); border: 1px solid var(--line); border-radius: 999px;
  padding: 4px 12px; cursor: pointer; }} button.fmt.on {{ color: var(--bg); background: var(--acc); }}
main {{ padding: 8px 16px 40px; max-width: 1600px; margin: 0 auto; }}
h2 {{ margin: 32px 0 8px; font-size: 20px; color: var(--acc); }}
.card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; margin: 12px 0; }}
.card h3 {{ margin: 0 0 4px; font: 600 17px ui-monospace, monospace; }}
.card p {{ margin: 4px 0; }} .meta, .beats {{ color: var(--dim); font-size: 13px; }}
.shots {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin: 10px 0; }}
figure {{ margin: 0; }} figure img {{ display: block; border-radius: 8px; border: 1px solid var(--line); height: 240px;
  width: auto; max-width: 100%; }}
figcaption {{ color: var(--dim); font-size: 12px; margin-top: 4px; }}
table {{ border-collapse: collapse; font-size: 13px; margin-top: 6px; }}
td {{ border-top: 1px solid var(--line); padding: 4px 10px 4px 0; vertical-align: top; }}
summary {{ cursor: pointer; color: var(--dim); }}
.warn {{ color: #fbbf24; }} .hide {{ display: none !important; }}
@media (max-width: 700px) {{ figure img {{ height: 160px; }} }}
</style></head><body>
<header><h1>Шаблоны студии</h1>{nav}<input id="q" placeholder="поиск: chart, цена, timeline…">{btns}</header>
<main>
<p class="meta">Кадры — фикстуры selftest (tests/fixtures/gallery и library), голос fake. Наведите на кадр — сцена
проигрывается по 5 кадрам. Пересобрать: <code>python -m studio gallery</code>. В сценарии — <code>template: &lt;имя&gt;</code>
или алиас; параметры — <code>params</code>.</p>{warn}
{body}
</main>
<script>
document.querySelectorAll('.shot').forEach(function (f) {{
  var fr = JSON.parse(f.dataset.frames), img = f.querySelector('img'), t = null, i = {SHOW};
  f.addEventListener('mouseenter', function () {{
    t = setInterval(function () {{ i = (i + 1) % fr.length; img.src = fr[i]; }}, 380); }});
  f.addEventListener('mouseleave', function () {{ clearInterval(t); i = {SHOW}; img.src = fr[i]; }});
}});
var off = {{}};
function apply() {{
  var q = document.getElementById('q').value.trim().toLowerCase();
  document.querySelectorAll('.card').forEach(function (c) {{
    c.classList.toggle('hide', q && c.dataset.name.indexOf(q) < 0); }});
  document.querySelectorAll('.shot').forEach(function (s) {{
    var fmt = (s.className.match(/f-(\\w+)/) || [])[1]; s.classList.toggle('hide', !!off[fmt]); }});
}}
document.getElementById('q').addEventListener('input', apply);
document.querySelectorAll('button.fmt').forEach(function (b) {{
  b.addEventListener('click', function () {{ off[b.dataset.fmt] = !off[b.dataset.fmt];
    b.classList.toggle('on', !off[b.dataset.fmt]); apply(); }}); }});
</script>
</body></html>
"""

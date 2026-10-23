"""cutdown — нарезка: длинный ролик → короткие под площадку (ROADMAP B4, studio/cutdown.py)."""
from __future__ import annotations

from ..project import load, resolve_project


def add(sp):
    q = sp.add_parser("cutdown", help="нарезка: длинный ролик → короткие (Shorts, TikTok, Reels)")
    q.add_argument("project", help="исходник: slug или путь")
    q.add_argument("--to", required=True, metavar="ПЛОЩАДКА", help="площадка нарезки: youtube-shorts | tiktok | …")
    q.add_argument("--count", type=int, default=3, help="сколько роликов (по умолчанию 3)")
    q.add_argument("--pick", action="append", metavar="chNN/sNN-sMM[,sKK]",
                   help="свой отрезок вместо автоматического выбора (через запятую — с пропуском); флаг можно повторить")
    q.add_argument("--min", type=float, default=20, help="нижний предел длительности, c (20)")
    q.add_argument("--max", type=float, default=60, help="верхний предел, c (60; не больше предела площадки)")
    q.add_argument("--list", action="store_true", help="только показать отрезки, проекты не создавать")
    q.add_argument("--force", action="store_true", help="перезаписать существующие проекты-нарезки")


def run(a):
    from .. import cutdown as C
    from ..platforms import get
    try:
        plat = get(a.to)
    except KeyError as e:
        raise SystemExit(f"--to: {e.args[0]}")
    src = load(resolve_project(a.project))
    if src.src:
        raise SystemExit("Это уже нарезка — укажите исходный проект")
    hi = min(a.max, plat.max_dur or a.max)
    lo = min(a.min, hi)
    scenes, how = C.scene_table(src)
    print(f"Исходник {src.slug}: {len(scenes)} сцен, длительности — {how}")
    print(f"Площадка {plat.id}: {plat.formats[0]}, отрезок {lo:g}–{hi:g} c (предел площадки: "
          f"{f'{plat.max_dur:g} c' if plat.max_dur else 'нет'})")
    if a.pick:
        cuts = [C.parse_pick(x, scenes) for x in a.pick]
    else:
        cands = C.candidates(scenes, lo, hi, (lo + hi) / 2)
        print(f"Отрезков-кандидатов: {len(cands)}; лучшие:")
        for c in cands[:10]:
            tags = sorted({t for s in c.scenes for t in s.tags})
            print(f"  {c.score:5.1f}  {c.span:<16} {c.dur:5.1f} c  {', '.join(tags)}  «{c.scenes[0].text[:50]}»")
        cuts = C.pick(cands, a.count)
        if len(cuts) < a.count:
            print(f"⚠️  непересекающихся отрезков {len(cuts)} из {a.count}: ослабьте --min/--max или задайте --pick")
    for c in cuts:
        if not lo <= c.dur <= hi:
            print(f"⚠️  {c.span}: ≈ {c.dur:.0f} c — вне {lo:g}–{hi:g} c")
    if a.list or not cuts:
        return 0 if cuts else 1
    tc = src.cfg["tts"]
    rate_fixed = None
    if tc.get("rate", "auto") == "auto":  # подобранный темп исходника — из его timeline.json
        tl = next((o.build / "timeline.json" for o in src.targets() if (o.build / "timeline.json").exists()), None)
        if tl is None:
            raise SystemExit("У исходника tts.rate: auto и нет timeline.json — сначала voice исходника")
        import json
        rate_fixed = json.loads(tl.read_text(encoding="utf-8"))["rate"]
    made = []
    for n, c in enumerate(cuts, 1):
        dst = src.root.parent / f"{src.slug}-cut-{n}"
        if dst.exists() and not a.force:
            print(f"⏭  {dst.name} уже есть — не трогаю (--force перезапишет)")
            continue
        C.write(src, c, dst, plat, rate_fixed, n)
        made.append(dst)
        print(f"✅ {dst.name}: {c.span}, ≈ {c.dur:.0f} c, {len(c.scenes)} сцен")
    if made:
        print("Дальше: прочитать script/*.yaml нарезок, при нужде дописать крючок и CTA (заготовки в комментариях), "
              "затем validate → voice → stills → render → assemble → qa каждой.")
    return 0

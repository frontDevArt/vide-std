"""platforms — профили площадок (ROADMAP B1): кадр, fps, длительность, безопасная зона, громкость, субтитры, кодек."""
from __future__ import annotations

LOG = False  # только чтение


def add(sp):
    q = sp.add_parser("platforms", help="профили площадок")
    q.add_argument("id", nargs="?", help="площадка — подробно, с источником цифр")


def run(a):
    from ..platforms import ASPECT, CHECKED, PLATFORMS, _dur, _zone, get, table
    if a.id:
        try:
            p = get(a.id)
        except KeyError as e:
            print(f"❌ {e.args[0]}")
            return 2
        print(f"{p.id} — {p.name}\n  форматы: {', '.join(f'{f} ({ASPECT[f]})' for f in p.formats)}"
              f"\n  fps: {'/'.join(map(str, p.fps))}\n  длительность: {_dur(p)}\n  поля в/н/л/п: {_zone(p)}"
              + "".join(f"\n  интерфейс: {u.name} {u.box}" for u in p.ui)
              + f"\n  громкость: {p.lufs:g} LUFS, пик ≤ {p.true_peak:g} dBTP"
              f"\n  субтитры: {'вшитые' if p.burn_subs else 'файлом .srt/.vtt'}"
              f"\n  видео: {p.vcodec} ~{p.kbps} кбит/с" + (f", не меньше {p.min_kbps}" if p.min_kbps else "")
              + f", звук {p.acodec}\n  обложка: {'%d×%d' % p.cover if p.cover else 'кадр из ролика'}"
              f"\n  {p.note}\n  источник: {p.source} (сверено {CHECKED})")
        return 0
    rows = table()
    w = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for n, r in enumerate(rows):
        print("  ".join(c.ljust(w[i]) for i, c in enumerate(r)).rstrip())
        if n == 0:
            print("  ".join("-" * x for x in w))
    print(f"\nЦифры сверены с документацией площадок {CHECKED}; подробно и источник — python -m studio platforms <id>."
          f"\nВ проекте: platform: <id> в project.yaml — validate сверит формат и длительность, qa — готовый файл."
          f"\n(B2) — формата ещё нет в студии. Всего площадок: {len(PLATFORMS)}.")
    return 0

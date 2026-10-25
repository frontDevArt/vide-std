"""translate — тот же ролик на другом языке (ROADMAP D3, studio/translate.py)."""
from __future__ import annotations

from ..project import resolve_project


def add(sp):
    q = sp.add_parser("translate", help="перевод ролика: проект <slug>-<язык> с листом translation.yaml")
    q.add_argument("project", help="исходник (slug или путь) или уже созданный перевод")
    q.add_argument("--to", metavar="ЯЗЫК", help="язык перевода: es, ru, en… (studio/lang.py); у перевода — не нужен")
    q.add_argument("--slug", help="имя проекта-перевода (по умолчанию <исходник>-<язык>)")
    q.add_argument("--tts", metavar="БЭКЕНД", help="голос перевода: edge | elevenlabs | piper | … "
                                                   "(иначе — как у исходника, голос — студии для языка)")


def run(a):
    from .. import translate as T
    from ..cutrefs import read_yaml
    from ..lang import LANGS
    root = resolve_project(a.project)
    meta = read_yaml(root / "project.yaml").get("translation")
    if meta:  # указан сам перевод
        near = root.parent / str(meta["source"])
        src, dst = (near if (near / "project.yaml").exists() else resolve_project(meta["source"])), root
    else:
        if not a.to:
            raise SystemExit("Укажите язык перевода: --to es")
        src, dst = root, root.parent / (a.slug or f"{root.name}-{a.to}")
        if (dst / "project.yaml").exists() and not (dst / T.SHEET).exists():
            raise SystemExit(f"{dst.name} уже есть и это не перевод — задайте --slug")
    to = a.to or None
    if to and to not in LANGS:
        print(f"⚠️  язык {to} не из studio/lang.py ({', '.join(LANGS)}): нет проверки алфавита и голоса по умолчанию")
    new = not (dst / T.SHEET).exists()
    data, r = T.sync(src, dst, to, a.tts)
    print(f"{'Создан' if new else 'Обновлён'} перевод {dst.name}: {src.name} ({data['from']}) → {data['to']}, "
          f"лист — {dst.name}/{T.SHEET}")
    print(f"Строк: {r.total}, переведено {r.total - len(r.missing)}, осталось {len(r.missing)}")
    for where, s in r.missing[:12]:
        print(f"  … {where}: «{s[:60]}»")
    if len(r.missing) > 12:
        print(f"  … и ещё {len(r.missing) - 12}")
    for w in r.warns:
        print(f"⚠️  {w}")
    for e in r.errs:
        print(f"❌ {e}")
    if not r.done:
        print(f"Сценарий перевода не записан: заполните {T.SHEET} (Claude переводит) и запустите "
              f"python -m studio translate {dst.name}")
        return 1
    print(f"✅ Сценарий перевода записан: {dst.name}/script/. Дальше: validate → voice → stills → render → assemble → qa.")
    return 0

"""kinds — типы роликов (ROADMAP C1): голос, длительность, поля брифа, чего ещё нет в движке."""
from __future__ import annotations

LOG = False  # только чтение


def add(sp):
    sp.add_parser("kinds", help="типы роликов: kind в project.yaml")


def run(a):
    from ..kinds import DEFAULT, KINDS
    for k in KINDS.values():
        dur = f"{k.duration[0]}–{k.duration[1]} c" if k.duration else "по речи"
        print(f"## {k.id}{'  (по умолчанию)' if k.id == DEFAULT else ''}\n{k.title}"
              f"\n  голос: {'да' if k.voice else 'нет (tts.backend: none)'}; длительность: {dur}"
              + (", точная (target_duration)" if k.exact else "")
              + (f"\n  brief: {', '.join(k.brief)}" if k.brief else "")
              + (f"\n  файлы брифа: {', '.join(k.files)} — фаза «Материалы»" if k.files else "")
              + f"\n  как: {k.hint}"
              + (f"\n  ⚠️  ждёт: {k.needs}" if k.needs else "") + "\n")
    print("В проекте: kind: <тип> и brief: {…} в project.yaml; новый — python -m studio new \"<тема>\" --kind <тип>.")
    return 0

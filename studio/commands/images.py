"""images — картинки сцен (ROADMAP C5.4, docs/IMAGES.md): смета → «да» → генерация в assets/images/ → assets.yaml."""
from __future__ import annotations

from ..project import load, resolve_project
from . import project_parser


def add(sp):
    q = project_parser(sp, "images", "картинки сцен: смета, генерация (кэш), учёт в assets.yaml")
    q.add_argument("--yes", action="store_true", help="подтвердить платную генерацию (images.backend: kie)")


def run(a):
    from .. import imagegen
    proj = load(resolve_project(a.project))
    if not imagegen.enabled(proj.cfg):
        print("Картинки выключены (images.enabled не true) — генерировать нечего. Включить — images: {enabled: true} в "
              "project.yaml (docs/IMAGES.md)")
        return 0
    errs, _ = imagegen.issues(proj)
    for e in errs:
        print("  ❌", e)
    if errs:
        print("Поправьте сценарий или images: (python -m studio validate) и повторите")
        return 1
    try:
        return _images(proj, getattr(a, "yes", False))
    except imagegen.ImagesUnavailable as e:
        print(f"❌ Картинки: {e}")
        return 2


def _images(proj, yes):
    from .. import imagegen
    st = imagegen.settings(proj.cfg)
    b = st["backend"]
    jobs = imagegen.plan(proj)
    if not jobs:
        print("Сцены не просят картинок (image:) — делать нечего")
        return 0
    est = imagegen.estimate(proj, jobs)
    todo = est["todo"]
    print(f"Картинки: backend {b}, модель {st['model']} {st['resolution']}; работ {len(jobs)}, в кэше {est['cached']}, "
          f"сделать {len(todo)}")
    for j in todo:
        price = "локально" if j.local else (f"{j.credits:g} кр" + ("" if j.priced else " (цена не замерена)")
                                            if b == "kie" else "бесплатно")
        print(f"  {j.where:<18} {j.step:<7} {j.model:<40} {price}")
    paid = b == "kie" and est["credits"] > 0
    before = None
    if paid:
        print(f"Смета: {est['credits']:g} кредитов ≈ ${est['usd']:.2f} (предел images.budget_usd ${est['budget_usd']:g})")
        if est["unpriced"]:
            print(f"  ⚠️  цена не замерена: {', '.join(est['unpriced'])} — в смете по {imagegen.UNPRICED} кр за вызов")
        if est["over"]:
            print(f"❌ Смета ${est['usd']:.2f} больше images.budget_usd ${est['budget_usd']:g} — генерация не запущена. "
                  "Сократите картинки или поднимите budget_usd (с согласия пользователя)")
            return 3
        if not yes:
            print("Платная генерация не запущена. Подтвердите: python -m studio images <проект> --yes")
            return 3
        before = imagegen.kie_balance()
        print(f"Баланс Kie до: {before:g} кр")
        if before < est["credits"]:
            print(f"❌ На балансе {before:g} кр, а смета {est['credits']:g} — пополните kie.ai")
            return 3
    spent, failed, code = {}, [], 0
    total = 0.0
    try:
        for j in todo:
            if paid and (total + j.credits) / imagegen.CREDITS_PER_USD > est["budget_usd"]:
                print(f"❌ Списано {total:g} кр; следующая работа ({j.where} {j.step}, {j.credits:g} кр) выведет за "
                      f"images.budget_usd ${est['budget_usd']:g} — стоп. Сделанное в кэше, повтор его не оплатит")
                code = 3
                break
            try:
                r = imagegen.generate(proj, j)
            except imagegen.ImagesUnavailable as e:
                if b != "none":
                    raise
                failed.append(str(e))  # none: собрать все недостающие файлы разом
                continue
            c = r.get("credits")
            c = (j.credits if paid and not j.local else 0) if c is None else c
            total += float(c)
            spent[j.out] = {"credits": c, "task": r.get("task")}
            print(f"  ✅ {j.where} {j.step} → {j.out.relative_to(proj.root).as_posix()}"
                  + (f" ({c:g} кр)" if paid and not j.local else ""))
    finally:
        added = imagegen.register(proj, imagegen.entries(proj, jobs, spent))
        if paid:
            after = imagegen.kie_balance()
            print(f"Баланс Kie: {before:g} → {after:g} кр, списано {before - after:g} (по задачам {total:g}, "
                  f"смета {est['credits']:g})")
    for e in failed:
        print("  ❌", e)
    if b == "none":
        print("  ⚠️  backend none: источник и лицензию своих файлов впишите в assets.yaml сами")
    print(f"assets.yaml: +{added} записей")
    if failed:
        return 1
    if code == 0:
        print(f"✅ Картинки готовы: {len(jobs)} работ ({len(spent)} сделано сейчас, {est['cached']} из кэша)")
    return code

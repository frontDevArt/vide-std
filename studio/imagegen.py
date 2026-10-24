"""Картинки для сцен (ROADMAP C5, docs/IMAGES.md): блок `images:` проекта и запросы `image:` сцен.

```yaml
# project.yaml (умолчание — studio.yaml → defaults; без блока = выключено)
images:
  enabled: true
  style: "flat vector illustration, palette #0B0F1A #4FD1C5 …"   # суффикс ко всем промптам
  budget_usd: 3            # остальное — умолчания config.SCHEMA["images"]: kie, nano-banana-2, 2K, seedream, rembg

# script/chNN.yaml — сцена просит картинку (одну или списком)
- id: s05
  template: media.image   # можно не писать: сцена с image: — media.image
  image:
    prompt: "a cozy bedroom at night, a person asleep in bed, a bedside lamp"
    role: scene            # scene | bg | subject | state_b (ROLES)
    layers: [room, bed with a person, bedside table with a lamp]   # только scene: что вынести в слои
    variant: 0             # сид: другой вариант той же картинки
```
Здесь — схема, проверки validate, путь картинки в кэше (`path`), план работ со сметой (`plan`, `estimate`) и бэкенды
(`generate`): `kie` (Kie AI: задача → опрос статуса), `fake` (процедурные PNG, офлайн — тесты и selftest), `none` (только
готовые файлы), вырезание `rembg` (`tools/rembg-venv/`) и учёт в `assets.yaml` (`entries`, `register`). Команда —
`python -m studio images` (`studio/commands/images.py`): смета, «да», бюджет, баланс Kie до и после.

Ключ Kie — только `workspace.secret("KIE_API_KEY", ws)` (.env студии → окружение → корневой .env); в лог, чат,
сообщения об ошибках и ключи кэша не попадает.
"""
from __future__ import annotations

import io
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import workspace
from .project import stable_hash

ROLES = {
    "scene": "сцена целиком — под раскладку на базу и слои (images.layers), параллакс",
    "bg": "фон без объектов",
    "subject": "объект на ровном фоне — вырезается (images.cutout) и ставится стикером",
    "state_b": "правка первой картинки сцены «та же сцена, но…» — для «до → после»",
}
BACKENDS = ("kie", "fake", "none")
CUTOUTS = ("rembg", "kie", "none")
RESOLUTIONS = ("1K", "2K", "4K")
KEYS = ("prompt", "role", "variant", "layers")
DIR = "assets/images"  # кэш картинок в папке проекта: <ключ>.png


TEMPLATE = "media.image"  # шаблон сцены с image: (без template — он)


def template_of(scene: dict) -> str:
    """Шаблон сцены сценария: явный `template`; нет — media.image у сцены с `image:`, иначе statement."""
    return scene.get("template", TEMPLATE if scene.get("image") else "statement")


def settings(cfg: dict) -> dict:
    """Блок images с умолчаниями; нет блока — выключено."""
    from .config import section_defaults
    return {**section_defaults("images"), **(cfg.get("images") if isinstance(cfg.get("images"), dict) else {})}


def enabled(cfg: dict) -> bool:
    return settings(cfg)["enabled"] is True


def scene_requests(scene: dict) -> list:
    """Запросы сцены: `image:` — словарь или список словарей (что угодно другое вернётся как есть — для ошибки)."""
    v = scene.get("image")
    return [] if v is None else list(v) if isinstance(v, list) else [v]


def requests(proj) -> list[tuple[str, dict]]:
    """[(chNN/sNN#i, запрос)] по всем сценам; только корректные словари с промптом."""
    out = []
    for ch, d in proj.chapters:
        for s in d.get("scenes") or []:
            for i, r in enumerate(scene_requests(s)):
                if isinstance(r, dict) and isinstance(r.get("prompt"), str) and r["prompt"].strip():
                    out.append((f"{ch}/{s.get('id')}#{i}", r))
    return out


def cache_key(req: dict, st: dict, base: str | None = None) -> str:
    """Ключ картинки: промпт + стиль + модель + разрешение + вариант (у state_b — ещё ключ первой картинки сцены).
    Повторный запуск с тем же ключом — без запроса и без денег."""
    return stable_hash([req["prompt"].strip(), st.get("style") or "", st["model"], st["resolution"],
                        int(req.get("variant") or 0), base], 16)


def keys(proj) -> list[tuple[str, dict, str]]:
    """[(где, запрос, ключ)]; state_b ссылается на ключ первой картинки своей сцены."""
    st = settings(proj.cfg)
    out, first = [], {}
    for where, r in requests(proj):
        scene = where.split("#")[0]
        base = first.get(scene) if r.get("role") == "state_b" else None
        k = cache_key(r, st, base)
        first.setdefault(scene, k)
        out.append((where, r, k))
    return out


def path(proj, key: str) -> Path:
    return proj.root / DIR / f"{key}.png"


def missing(proj) -> list[str]:
    """Сцены, чьих картинок ещё нет в кэше (фаза «картинки» в status)."""
    return [w for w, _, k in keys(proj) if not path(proj, k).exists()]


def issues(proj) -> tuple[list, list]:
    """validate: блок images и запросы image: сцен → (ошибки, предупреждения)."""
    errs, warns = [], []
    raw = proj.cfg.get("images")
    st = settings(proj.cfg)
    if raw is not None and not isinstance(raw, dict):
        errs.append(f"images: должен быть словарём {{enabled, model, style, budget_usd, …}}, а не {raw!r}")
    for k, allowed in (("backend", BACKENDS), ("cutout", CUTOUTS), ("resolution", RESOLUTIONS)):
        if st[k] not in allowed:
            errs.append(f"images.{k}: {st[k]!r} — можно {', '.join(allowed)}")
    b = st["budget_usd"]
    if isinstance(b, bool) or not isinstance(b, (int, float)) or b <= 0:
        errs.append(f"images.budget_usd = {b!r}: нужно число > 0 (предел на ролик, $)")
    want = []
    for ch, d in proj.chapters:
        for s in d.get("scenes") or []:
            where = f"{ch}/{s.get('id')}"
            reqs = scene_requests(s)
            if reqs:
                want.append(where)
            for i, r in enumerate(reqs):
                w = where + (f" image[{i}]" if len(reqs) > 1 else " image")
                if not isinstance(r, dict):
                    errs.append(f"{w}: нужен словарь {{prompt, role, variant}}, а не {r!r}")
                    continue
                unknown = set(r) - set(KEYS)
                if unknown:
                    warns.append(f"{w}: неизвестные ключи {sorted(unknown)} (есть: {', '.join(KEYS)})")
                if not isinstance(r.get("prompt"), str) or not r["prompt"].strip():
                    errs.append(f"{w}: нет prompt — что нарисовать (текст и цифры в кадр — только кодом)")
                role = r.get("role", "scene")
                if role not in ROLES:
                    errs.append(f"{w}: role {role!r} — можно {', '.join(ROLES)}")
                elif role == "state_b" and i == 0:
                    errs.append(f"{w}: role state_b — правка первой картинки сцены, а она первая: "
                                "сначала image с role scene или bg")
                v = r.get("variant", 0)
                if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                    errs.append(f"{w}: variant = {v!r} — целое ≥ 0 (сид)")
                if "layers" in r:
                    if role != "scene":
                        warns.append(f"{w}: layers — только у role scene (раскладка), здесь игнорируется")
                    elif not (isinstance(r["layers"], list) and r["layers"]
                              and all(isinstance(x, str) and x.strip() for x in r["layers"])):
                        errs.append(f"{w}: layers — список названий слоёв (строки), а не {r['layers']!r}")
                    elif not st["layers"]:
                        warns.append(f"{w}: layers задан, а images.layers: null — раскладки не будет")
    if want and not enabled(proj.cfg):
        errs.append(f"сцены просят картинки ({', '.join(want[:4])}{' …' if len(want) > 4 else ''}), а "
                    "images.enabled не true — включите images: {enabled: true} в project.yaml (платно, смета и "
                    "«да» перед генерацией, docs/IMAGES.md) или уберите image: из сцен")
    elif want and st["backend"] == "none":
        warns.append("images.backend: none — картинки сцен генерироваться не будут, нужны готовые файлы в "
                     f"{DIR}/")
    return errs, warns


# ---------------------------------------------------------------- план и смета
class ImagesUnavailable(RuntimeError):
    """Генерация невозможна или прервана (нет ключа, 401/402/403, задача упала, таймаут) — без ретраев."""


CREDITS_PER_USD = 200  # курс Kie (docs/IMAGES.md)
UNPRICED = 20  # кредитов за вызов модели без замеренной цены: смета с запасом, а не ноль
# Модели генерации: цена (кредиты; по разрешению или одна; None — не замерена), поле картинок-входов, сид, кадры.
# edit — модель, которой уходит запрос с картинками-входами (референс стиля, база state_b), если своя их не берёт.
ASPECTS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")
KLEIN_ASPECTS = ("1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9")
MODELS = {
    "nano-banana-2": {"credits": {"1K": 8, "2K": 12, "4K": 18}, "refs": "image_input", "resolution": True},
    "google/nano-banana": {"credits": 4, "edit": "google/nano-banana-edit"},
    "google/nano-banana-edit": {"credits": None, "refs": "image_urls", "refs_required": True},
    "flux-3/klein-text-to-image": {"credits": {"1K": 1.6, "2K": 2.5, "4K": 6.5}, "edit": "flux-3/klein-edit-image",
                                   "resolution": True, "seed": True, "aspects": KLEIN_ASPECTS},
    "flux-3/klein-edit-image": {"credits": None, "refs": "image_urls", "refs_required": True, "resolution": True,
                                "seed": True, "aspects": KLEIN_ASPECTS},
}
LAYER_MODELS = {"seedream/5-flash-layer-decomposition": 12.96}  # картинка → база + слои с bounding_box
CUTOUT_MODEL, CUTOUT_CREDITS = "recraft/remove-background", None  # images.cutout: kie; вход ≤ 5 МБ
FORMAT_ASPECT = {"vertical": "9:16", "horizontal": "16:9", "square": "1:1", "portrait": "4:5"}


@dataclass
class Job:
    """Одна работа плана. step: image (генерация) | layers (раскладка картинки key) | cutout (вырезание объекта).
    out — что появится по готовности (есть файл — работа сделана, повтор бесплатен)."""
    step: str
    where: str
    key: str
    model: str
    credits: float
    out: Path
    req: dict = field(default_factory=dict)
    base: str | None = None  # state_b — ключ картинки, которую правим
    priced: bool = True
    local: bool = False  # rembg — без сети и денег, шаг команды images (C5.4)


def layers_dir(proj, key: str) -> Path:
    """Раскладка картинки: base.png (сцена без объектов), 1.png… (прозрачные слои), layers.json (рамки 0–1)."""
    return proj.root / DIR / f"{key}.layers"


def cut_path(proj, key: str) -> Path:
    return proj.root / DIR / f"{key}.cut.png"


def aspect(proj, req: dict) -> str:
    """Кадр картинки: объект для вырезания — квадрат, остальное — по формату проекта."""
    return "1:1" if req.get("role") == "subject" else FORMAT_ASPECT.get(proj.cfg.get("format"), "16:9")


def _model(st: dict, refs: bool) -> str:
    """Модель запроса: с картинками-входами — та, что их берёт (images.model или её edit)."""
    m = st["model"]
    if m not in MODELS:
        raise ImagesUnavailable(f"images.model {m!r} не описан в imagegen.MODELS (вход и цена) — можно "
                                f"{', '.join(MODELS)}; новую модель — добавить туда с замером цены (docs/IMAGES.md)")
    if refs and not MODELS[m].get("refs"):
        m = MODELS[m]["edit"]
    return m


def _price(model: str, resolution: str) -> float | None:
    c = MODELS[model]["credits"]
    return c.get(resolution) if isinstance(c, dict) else c


def plan(proj) -> list[Job]:
    """Все работы ролика по порядку (state_b — после своей базы, раскладка и вырезание — после картинки)."""
    st = settings(proj.cfg)
    ref = bool(st.get("reference"))
    jobs = []
    for where, r, k in keys(proj):
        role = r.get("role", "scene")
        scene = where.split("#")[0]
        base = None
        if role == "state_b":
            base = next(j.key for j in jobs if j.step == "image" and j.where.split("#")[0] == scene)
        m = _model(st, ref or base is not None)
        c = _price(m, st["resolution"])
        jobs.append(Job("image", where, k, m, UNPRICED if c is None else c, path(proj, k), r, base, c is not None))
        if role == "scene" and r.get("layers") and st["layers"]:
            c = LAYER_MODELS.get(st["layers"])
            jobs.append(Job("layers", where, k, st["layers"], UNPRICED if c is None else c,
                            layers_dir(proj, k) / "layers.json", r, priced=c is not None))
        if role == "subject" and st["cutout"] == "kie":
            jobs.append(Job("cutout", where, k, CUTOUT_MODEL, UNPRICED if CUTOUT_CREDITS is None else CUTOUT_CREDITS,
                            cut_path(proj, k), r, priced=CUTOUT_CREDITS is not None))
        elif role == "subject" and st["cutout"] != "none":
            jobs.append(Job("cutout", where, k, st["cutout"], 0, cut_path(proj, k), r, local=True))
    return jobs


def estimate(proj, jobs: list[Job] | None = None) -> dict:
    """Смета того, чего ещё нет в кэше: {todo, cached, credits, usd, budget_usd, over, unpriced}.
    fake и none — бесплатно. Цена не замерена — UNPRICED кредитов за вызов, модель — в unpriced."""
    st = settings(proj.cfg)
    jobs = plan(proj) if jobs is None else jobs
    todo = [j for j in jobs if not j.out.exists()]
    paid = [j for j in todo if st["backend"] == "kie" and not j.local]
    credits = round(sum(j.credits for j in paid), 2)
    usd = round(credits / CREDITS_PER_USD, 4)
    return {"todo": todo, "cached": len(jobs) - len(todo), "credits": credits, "usd": usd,
            "budget_usd": st["budget_usd"], "over": usd > st["budget_usd"],
            "unpriced": sorted({j.model for j in paid if not j.priced})}


def prompt_text(req: dict, st: dict) -> str:
    """Промпт модели: текст сцены + стиль ролика (images.style)."""
    p = req["prompt"].strip()
    s = (st.get("style") or "").strip()
    return f"{p.rstrip('.')}. {s}" if s else p


def generate(proj, job: Job, ws=None) -> dict:
    """Сделать одну работу бэкендом images.backend → {credits, files, task?}. Файл пишется целиком или никак."""
    st = settings(proj.cfg)
    b = st["backend"]
    if job.local and b != "fake":  # rembg — локально при любом бэкенде, и у none: вырезает готовый файл
        job.out.parent.mkdir(parents=True, exist_ok=True)
        return rembg_cut(proj, job)
    if b == "none":
        raise ImagesUnavailable(f"images.backend: none — генерации нет; положите готовый файл {job.out.name} в "
                                f"{job.out.parent.relative_to(proj.root).as_posix()}/ ({job.where})")
    fn = {"fake": _fake, "kie": _kie_job}.get(b)
    if fn is None:
        raise ImagesUnavailable(f"images.backend {b!r} — можно {', '.join(BACKENDS)}")
    job.out.parent.mkdir(parents=True, exist_ok=True)
    return fn(proj, job, st, ws or proj.ws)


# ---------------------------------------------------------------- сцена → params шаблона image (C5.5)
# Объект без своей рамки (subject) — стикер в этом месте кадра: доли картинки фона, объект стоит внизу рамки.
SUBJECT_BOX = {"horizontal": [0.3, 0.1, 0.7, 0.95], "vertical": [0.08, 0.22, 0.92, 0.8],
               "square": [0.15, 0.1, 0.85, 0.95], "portrait": [0.12, 0.15, 0.88, 0.9]}
BASE_DEPTH, BG_DEPTH = 0.1, 0.15  # дальний слой почти неподвижен
NEAR = (0.45, 1.0)  # глубины слоёв раскладки: от дальнего к ближнему


def _rel(proj, p: Path) -> str:
    return p.relative_to(proj.root).as_posix()


def _fg_at(layers: list, n_beats: int) -> list:
    """Слои поверх базы появляются по битам: i-й — на бите i (битов меньше — на последнем). Бит один — сразу все."""
    if n_beats >= 2:
        for i, L in enumerate(layers):
            L["at"] = min(i, n_beats - 1)
    return layers


def scene_params(proj, chapter: str, scene: dict, n_beats: int = 0) -> tuple[dict, list[str]]:
    """Сцена с `image:` → (params шаблона image, недостающие файлы). Только по готовым PNG: файлы не генерируются,
    одно и то же на входе — одно и то же на выходе. Явные `params` сцены поверх этого (render._prepare).
    scene — раскладка на базу и слои (layers.json) → параллакс, слои на месте `box` и по битам; без раскладки — Ken
    Burns. bg (+ subject) → параллакс: фон и вырезанный объект стикером. subject один — стикер на фоне ролика.
    state_b → «до → после» с первой картинкой сцены на втором бите."""
    if not enabled(proj.cfg):
        return {}, []
    st = settings(proj.cfg)
    where = f"{chapter}/{scene.get('id')}"
    mine = [(r, k) for w, r, k in keys(proj) if w.split("#")[0] == where]
    if not mine:
        return {}, []
    need = []

    def have(p: Path) -> str:
        if not p.exists():
            need.append(_rel(proj, p))
        return _rel(proj, p)

    def subject(k):
        cut = cut_path(proj, k) if st["cutout"] != "none" else path(proj, k)
        box = SUBJECT_BOX.get(proj.cfg.get("format"), SUBJECT_BOX["horizontal"])
        return {"file": have(cut), "depth": 1.0, "box": list(box), "sticker": True}

    role = lambda r: r.get("role", "scene")  # noqa: E731
    first, k0 = mine[0]
    out = {"file": have(path(proj, k0))}
    after = next((k for r, k in mine[1:] if role(r) == "state_b"), None)
    subj = next((k for r, k in mine if role(r) == "subject"), None)
    if after is not None:
        out.update({"motion": "before_after", "after": have(path(proj, after))})
        if n_beats >= 2:
            out["at"] = 1
    elif role(first) == "scene" and first.get("layers") and st["layers"]:
        lj = layers_dir(proj, k0) / "layers.json"
        have(lj)
        if lj.exists():
            meta = json.loads(lj.read_text(encoding="utf-8"))
            d = lj.parent
            base = [{"file": have(d / meta["base"]), "depth": BASE_DEPTH}] if meta.get("base") else [
                {"file": out["file"], "depth": BASE_DEPTH}]
            fg = sorted(meta.get("layers") or [], key=lambda x: int(x.get("z", 0)))
            n = len(fg)
            fg = [{"file": have(d / x["file"]), "box": [float(v) for v in x["box"]],
                   "depth": round(NEAR[0] + (NEAR[1] - NEAR[0]) * (i / (n - 1) if n > 1 else 1.0), 3)}
                  for i, x in enumerate(fg)]
            out.update({"motion": "parallax", "layers": base + _fg_at(fg, n_beats)})
    elif role(first) == "subject":
        out.update({"motion": "parallax", "layers": _fg_at([subject(k0)], n_beats)})
    elif subj is not None:  # фон + объект
        out.update({"motion": "parallax",
                    "layers": [{"file": out["file"], "depth": BG_DEPTH}] + _fg_at([subject(subj)], n_beats)})
    return out, list(dict.fromkeys(need))


def _save_png(data, out: Path):
    """Картинка (байты любого формата или PIL.Image) → PNG атомарно: обрыв не оставит битый файл в кэше."""
    from PIL import Image
    im = data if isinstance(data, Image.Image) else Image.open(io.BytesIO(data))
    im.load()
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() or im.mode == "P" else "RGB")
    tmp = out.with_name(out.name + ".part")
    im.save(tmp, format="PNG")
    tmp.replace(out)


def _write_json(obj, out: Path):
    tmp = out.with_name(out.name + ".part")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out)


# ---------------------------------------------------------------- fake (тесты и selftest)
# Процедурные PNG без сети и денег: градиент и фигуры из ключа — одинаково на любой ОС. Длинная сторона FAKE_SIDE —
# чтобы selftest шёл быстро; раскладка и вырезание дают те же файлы, что у kie.
FAKE_SIDE = 768


def _fake_size(a: str) -> tuple[int, int]:
    w, h = (int(x) for x in a.split(":"))
    return (FAKE_SIDE, round(FAKE_SIDE * h / w)) if w >= h else (round(FAKE_SIDE * w / h), FAKE_SIDE)


def _fake_picture(seed: str, size, rgba=False):
    from PIL import Image, ImageDraw
    rnd = random.Random(stable_hash(seed, 16))
    color = (lambda: tuple(rnd.randrange(30, 230) for _ in range(3)))
    w, h = size
    c0, c1 = color(), color()
    im = Image.new("RGBA" if rgba else "RGB", size, (0, 0, 0, 0) if rgba else c0)
    d = ImageDraw.Draw(im)
    if not rgba:
        for y in range(h):
            t = y / max(1, h - 1)
            d.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(c0, c1)))
    for _ in range(4):
        x0, y0 = rnd.randrange(0, max(1, w * 3 // 4)), rnd.randrange(0, max(1, h * 3 // 4))
        x1, y1 = x0 + rnd.randrange(w // 8, w // 3 + 1), y0 + rnd.randrange(h // 8, h // 3 + 1)
        (d.ellipse if rnd.random() < 0.5 else d.rectangle)([x0, y0, x1, y1], fill=color() + (255,))
    return im


def _fake(proj, job: Job, st: dict, ws) -> dict:
    from PIL import Image, ImageDraw
    if job.step == "image":
        _save_png(_fake_picture(job.key, _fake_size(aspect(proj, job.req))), job.out)
        return {"credits": 0, "files": [job.out]}
    src = Image.open(path(proj, job.key)).convert("RGBA")
    w, h = src.size
    if job.step == "cutout":  # объект — овал в центре, вокруг прозрачно
        mask = Image.new("L", src.size, 0)
        ImageDraw.Draw(mask).ellipse([w // 6, h // 6, w * 5 // 6, h * 5 // 6], fill=255)
        src.putalpha(mask)
        _save_png(src, job.out)
        return {"credits": 0, "files": [job.out]}
    d = job.out.parent  # layers: база — сама картинка, слои — фигуры в рамках вдоль низа кадра
    d.mkdir(parents=True, exist_ok=True)
    _save_png(src.convert("RGB"), d / "base.png")
    names = job.req.get("layers") or []
    meta, files = {"model": job.model, "base": "base.png", "layers": []}, [d / "base.png"]
    for i, name in enumerate(names, 1):
        box = [round((i - 1) / len(names) + 0.02, 4), 0.55, round(i / len(names) - 0.02, 4), 0.95]
        size = (max(1, round((box[2] - box[0]) * w)), max(1, round((box[3] - box[1]) * h)))
        _save_png(_fake_picture(f"{job.key}/{i}", size, rgba=True), d / f"{i}.png")
        meta["layers"].append({"file": f"{i}.png", "name": name, "z": i, "box": box})
        files.append(d / f"{i}.png")
    _write_json(meta, job.out)
    return {"credits": 0, "files": files}


# ---------------------------------------------------------------- kie (Kie AI, платно)
KIE_API = "https://api.kie.ai/api/v1"
KIE_UPLOAD = "https://kieai.redpandaai.co/api/file-stream-upload"
KIE_TIMEOUT = 600  # с на задачу: у Kie задача без результата 10 мин → 408
KIE_POLL = 4  # с между опросами статуса
KIE_RETRIES = 3  # сбоев опроса подряд (сеть, 5xx); создание задачи не повторяем — оно стоит денег
KIE_HINTS = {401: "ключ неверный (KIE_API_KEY)", 402: "нет кредитов — пополните баланс kie.ai",
             403: "доступ запрещён (тариф/прокси) — не ретраим", 404: "нет такой задачи или ресурса",
             422: "неверные параметры запроса", 429: "лимит запросов", 455: "сервис на обслуживании"}
_sleep, _clock = time.sleep, time.monotonic  # подменяются в тестах
_UPLOADS: dict = {}  # (файл, mtime) → URL загрузки: живёт 24 ч, на один запуск хватит


class _Transient(ImagesUnavailable):
    """Сбой сети или 5xx — опрос статуса можно повторить."""


def _kie_key(ws=None) -> str:
    k = workspace.secret("KIE_API_KEY", ws)
    if not k:
        raise ImagesUnavailable("нет ключа Kie AI: впишите KIE_API_KEY в .env студии (studios/<id>/.env) или в "
                                "корневой .env (имя — в .env.example)")
    return k


def _urlopen(req, timeout):
    import urllib.request
    return urllib.request.urlopen(req, timeout=timeout)


def _kie_call(url, *, body=None, data=None, ctype=None, method="GET", ws=None, timeout=60):
    """Запрос к Kie → поле data. Ошибка бывает и с HTTP 200 — смотрим `code`. 4xx (401/402/403/422…) — ошибка сразу,
    без ретраев; сеть и 5xx — _Transient. Ключ из сообщений вырезается."""
    import urllib.error
    import urllib.request
    key = _kie_key(ws)
    if body is not None:
        data, ctype = json.dumps(body).encode(), "application/json"
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _urlopen(req, timeout) as r:
            raw = r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace").replace(key, "***")[:300]
        raise (_Transient if e.code >= 500 else ImagesUnavailable)(
            f"Kie HTTP {e.code} {KIE_HINTS.get(e.code, '')}: {msg}")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise _Transient(f"Kie недоступен: {getattr(e, 'reason', e)}")
    try:
        j = json.loads(raw)
    except ValueError:
        raise _Transient(f"Kie: ответ не JSON: {raw.replace(key, '***')[:200]}")
    code = j.get("code")
    if code != 200:
        msg = str(j.get("msg") or "").replace(key, "***")[:300]
        raise (_Transient if isinstance(code, int) and code >= 500 else ImagesUnavailable)(
            f"Kie code {code} {KIE_HINTS.get(code, '')}: {msg}")
    return j.get("data")


def kie_balance(ws=None) -> float:
    """Баланс, кредиты (200 = $1): смету сверять с ним до и после генерации."""
    return float(_kie_call(f"{KIE_API}/chat/credit", ws=ws))


def kie_upload(file, ws=None) -> str:
    """Свою картинку на вход модели (референс, база state_b, вход раскладки) → URL (живёт 24 ч: кэшируем результат
    генерации, а не ссылку)."""
    file = Path(file)
    memo = (str(file.resolve()), file.stat().st_mtime)
    if memo in _UPLOADS:
        return _UPLOADS[memo]
    bnd = uuid.uuid4().hex
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        file.suffix.lower(), "application/octet-stream")
    data = (f'--{bnd}\r\nContent-Disposition: form-data; name="uploadPath"\r\n\r\nvide-std/images\r\n'
            f'--{bnd}\r\nContent-Disposition: form-data; name="file"; filename="{file.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n").encode() + file.read_bytes() + f"\r\n--{bnd}--\r\n".encode()
    d = _kie_call(KIE_UPLOAD, data=data, ctype=f"multipart/form-data; boundary={bnd}", method="POST", ws=ws,
                  timeout=180)
    url = (d or {}).get("downloadUrl")
    if not url:
        raise ImagesUnavailable(f"Kie upload {file.name}: нет downloadUrl в ответе")
    _UPLOADS[memo] = url
    return url


def kie_task(model: str, inp: dict, ws=None, timeout: float = KIE_TIMEOUT, poll: float = KIE_POLL) -> dict:
    """createTask → опрос recordInfo до success / fail / таймаута → {task, credits, result} (result — resultJson)."""
    tid = (_kie_call(f"{KIE_API}/jobs/createTask", body={"model": model, "input": inp}, method="POST", ws=ws)
           or {}).get("taskId")
    if not tid:
        raise ImagesUnavailable(f"Kie createTask {model}: нет taskId в ответе")
    t0, fails, state = _clock(), 0, None
    while True:
        _sleep(poll)
        try:
            d = _kie_call(f"{KIE_API}/jobs/recordInfo?taskId={tid}", ws=ws) or {}
            fails, state = 0, d.get("state")
        except _Transient as e:
            fails += 1
            if fails >= KIE_RETRIES:
                raise ImagesUnavailable(f"Kie задача {tid}: {fails} сбоя опроса подряд — {e}")
            d = {}
        if state == "success":
            res = d.get("resultJson") or "{}"
            return {"task": tid, "credits": d.get("creditsConsumed"),
                    "result": json.loads(res) if isinstance(res, str) else res}
        if state == "fail":
            raise ImagesUnavailable(f"Kie задача {tid} ({model}) упала: {d.get('failCode')} {d.get('failMsg')}")
        if _clock() - t0 > timeout:
            raise ImagesUnavailable(f"Kie задача {tid} ({model}): нет результата за {timeout:.0f} с (состояние "
                                    f"{state}); кредиты могли списаться — сверить баланс")


def _download(url: str) -> bytes:
    import urllib.error
    import urllib.request
    try:
        with _urlopen(urllib.request.Request(url, headers={"User-Agent": "vide-std"}), 180) as r:
            return r.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise ImagesUnavailable(f"не скачать результат Kie {url.split('?')[0]}: {getattr(e, 'reason', e)}")


def kie_input(proj, job: Job, st: dict, refs: list) -> dict:
    """Вход модели генерации по MODELS: промпт со стилем, кадр, разрешение, сид (= variant), картинки-входы."""
    m = MODELS[job.model]
    want, allowed = aspect(proj, job.req), m.get("aspects", ASPECTS)
    if want not in allowed:  # ближайший по отношению сторон: шаблон всё равно кадрирует
        ratio = (lambda a: int(a.split(":")[0]) / int(a.split(":")[1]))
        want = min(allowed, key=lambda a: abs(ratio(a) - ratio(want)))
    inp = {"prompt": prompt_text(job.req, st), "aspect_ratio": want, "output_format": "png"}
    if m.get("resolution"):
        inp["resolution"] = st["resolution"]
    if m.get("seed"):
        inp["seed"] = int(job.req.get("variant") or 0)
    if refs:
        inp[m["refs"]] = refs
    elif m.get("refs_required"):
        raise ImagesUnavailable(f"{job.model}: нужна картинка-вход (images.reference или база state_b)")
    return inp


def _kie_one(job: Job, model: str, inp: dict, ws) -> dict:
    r = kie_task(model, inp, ws)
    urls = r["result"].get("resultUrls") or []
    if not urls:
        raise ImagesUnavailable(f"Kie задача {r['task']}: нет resultUrls")
    _save_png(_download(urls[0]), job.out)
    return {"credits": r["credits"], "task": r["task"], "files": [job.out]}


def _kie_job(proj, job: Job, st: dict, ws) -> dict:
    if job.step == "image":
        refs = [kie_upload(path(proj, job.base), ws)] if job.base else []  # «та же сцена, но…»: база — первой
        if st.get("reference"):
            ref = proj.root / st["reference"]
            if not ref.exists():
                raise ImagesUnavailable(f"images.reference: нет файла {st['reference']}")
            refs.append(kie_upload(ref, ws))
        return _kie_one(job, job.model, kie_input(proj, job, st, refs), ws)
    src = kie_upload(path(proj, job.key), ws)
    if job.step == "cutout":
        return _kie_one(job, job.model, {"image": src}, ws)
    r = kie_task(job.model, {"image_url": src, "prompt": "Separate into layers: " + "; ".join(job.req["layers"]) + ".",
                             "size": st["resolution"], "output_format": "png"}, ws)
    data = (r["result"].get("resultObject") or {}).get("layers_data") or []
    if not data:
        raise ImagesUnavailable(f"Kie задача {r['task']}: нет layers_data в ответе раскладки")
    d = job.out.parent
    d.mkdir(parents=True, exist_ok=True)
    meta, files = {"model": job.model, "task": r["task"], "base": None, "layers": []}, []
    for x in sorted(data, key=lambda x: int(x.get("z_index", 0))):
        z, bb = int(x.get("z_index", 0)), (x.get("bounding_box") or {}).get("normalized")
        name = f"{z}.png" if bb else "base.png"
        _save_png(_download(x["url"]), d / name)
        files.append(d / name)
        if bb:  # рамка 0–1000 → доли кадра; PNG слоя крупнее рамки — шаблон вписывает его в box (C5.5)
            meta["layers"].append({"file": name, "name": x.get("name") or "", "z": z,
                                   "box": [round(v / 1000, 4) for v in bb]})
        else:
            meta["base"] = name
    _write_json(meta, job.out)
    return {"credits": r["credits"], "task": r["task"], "files": files}


# ---------------------------------------------------------------- rembg (локально, tools/rembg-venv)
REMBG_MODEL = "isnet-general-use"  # Apache-2.0; не bria-rmbg — некоммерческая (docs/IMAGES.md)
REMBG_TIMEOUT = 600  # с: первый запуск качает модель (179 МБ)


# Через Python API, а не CLI `rembg i`: в venv стоит rembg без зависимостей CLI (click и др.) — лишнего не ставим.
_REMBG_CODE = ("import sys; from PIL import Image; from rembg import new_session, remove; "
               "remove(Image.open(sys.argv[2]), session=new_session(sys.argv[1])).save(sys.argv[3], format='PNG')")


def rembg_python() -> Path:
    """python своего venv с rembg: в окружении студии rembg поднял бы Pillow (риск для golden)."""
    venv = workspace.current().tools / "rembg-venv"  # tools/ общий для всех студий
    for p in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
        if p.exists():
            return p
    raise ImagesUnavailable(f"нет {venv.as_posix()}/ с rembg — поставить по docs/IMAGES.md "
                            "(«Вырезание объекта: локально») с согласия пользователя или images.cutout: kie | none")


def rembg_cut(proj, job: Job) -> dict:
    """Вырезать объект картинки job.key → <ключ>.cut.png (RGBA), атомарно."""
    import subprocess
    src = path(proj, job.key)
    if not src.exists():
        raise ImagesUnavailable(f"{job.where}: нет картинки {src.name} для вырезания — сначала её генерация")
    tmp = job.out.with_name(job.out.stem + ".part.png")
    cmd = [str(rembg_python()), "-I", "-c", _REMBG_CODE, REMBG_MODEL, str(src), str(tmp)]
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                           timeout=REMBG_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        raise ImagesUnavailable(f"rembg {src.name}: нет результата за {REMBG_TIMEOUT} с")
    if r.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise ImagesUnavailable(f"rembg {src.name}: код {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}")
    tmp.replace(job.out)
    return {"credits": 0, "files": [job.out]}


# ---------------------------------------------------------------- учёт в assets.yaml
# Права на выход определяет поставщик модели, Kie своих ограничений не добавляет (ответ поддержки, docs/IMAGES.md).
LICENSES = (("nano-banana", "Google Gemini API terms (через Kie AI)"),
            ("google/", "Google Gemini API terms (через Kie AI)"),
            ("flux-3/", "BFL FLUX Klein (через Kie AI) — условия не проверены"),
            ("seedream/", "ByteDance Seedream (через Kie AI) — условия не проверены"),
            ("recraft/", "Recraft (через Kie AI) — условия не проверены"))
FAKE_SOURCE = "imagegen fake — процедурная заглушка студии"
FAKE_LICENSE = "CC0 — нарисовано кодом студии (заглушка, не для публикации)"


def license_of(model: str) -> str:
    return next((v for k, v in LICENSES if model.startswith(k)), f"{model} (через Kie AI) — условия не проверены")


def entries(proj, jobs: list[Job], spent: dict | None = None) -> list[dict]:
    """Записи assets.yaml для готовых файлов работ: файл, источник, лицензия, промпт, модель, цена.
    spent — {out: {credits, task}} фактическое за этот запуск; иначе цена — по смете плана. backend none — пусто:
    файлы свои, источник и лицензию пишет пользователь."""
    st = settings(proj.cfg)
    b = st["backend"]
    if b == "none":
        return []
    rel = (lambda p: p.relative_to(proj.root).as_posix())
    img = {j.key: j for j in jobs if j.step == "image"}
    out = []
    for j in jobs:
        if not j.out.exists():
            continue
        src_img = img.get(j.key)
        lic0 = license_of(src_img.model) if src_img else ""
        if b == "fake":
            src, lic = f"{FAKE_SOURCE} ({j.step})", FAKE_LICENSE
        elif j.step == "image":
            src = f"Kie AI {j.model} {st['resolution']}" + (f", правка {j.base}.png" if j.base else "") + (
                f", референс {st['reference']}" if st.get("reference") else "")
            lic = license_of(j.model)
        elif j.local:
            src, lic = f"{j.key}.png → rembg {REMBG_MODEL}", f"{lic0}; вырезано rembg (Apache-2.0)"
        else:
            src, lic = f"{j.key}.png → Kie AI {j.model}", f"{lic0} + {license_of(j.model)}"
        meta = {"by": "генерация", "prompt": prompt_text(j.req, st)}
        if b == "kie" and not j.local:
            got = (spent or {}).get(j.out) or {}
            c = got.get("credits")
            c = j.credits if c is None else c
            meta.update({"model": j.model, "credits": c, "usd": round(float(c) / CREDITS_PER_USD, 4)})
            if got.get("task"):
                meta["task"] = got["task"]
        if j.step == "layers":
            lj = json.loads(j.out.read_text(encoding="utf-8"))
            files = ([(lj["base"], "база — сцена без объектов")] if lj.get("base") else []) + [
                (x["file"], f"слой «{x.get('name') or x['z']}»") for x in lj.get("layers") or []]
            for i, (f, what) in enumerate(files):
                e = {"file": rel(j.out.parent / f), "source": f"{src}, {what}", "license": lic, **meta}
                if i:  # цена раскладки — одна на все её файлы, у первого
                    for k in ("credits", "usd", "task"):
                        e.pop(k, None)
                out.append(e)
        else:
            out.append({"file": rel(j.out), "source": src, "license": lic, **meta})
    return out


def register(proj, items: list[dict]) -> int:
    """Дописать в assets.yaml записи файлов, которых там ещё нет (ручные записи и комментарии не трогаем) → сколько
    добавлено. Файл не дописывается как список — переписывается целиком через YAML."""
    import yaml

    from . import assets
    reg, errs = assets.load(proj.root)
    if errs:
        raise ImagesUnavailable(f"{'; '.join(errs)} — поправьте {assets.FILE} вручную, затем повторите images")
    new = [e for e in items if assets._key(e["file"]) not in reg]
    if not new:
        return 0
    f = proj.root / assets.FILE
    lines = "".join("  - " + yaml.safe_dump(e, default_flow_style=True, allow_unicode=True, width=10 ** 9,
                                            sort_keys=False).strip() + "\n" for e in new)
    old = f.read_text(encoding="utf-8") if f.exists() else ""
    text = (old.rstrip("\n") + "\n" + lines) if old.strip() else (
        "# Источник и лицензия всего, что видно и слышно в ролике (studio/assets.py); картинки дописывает "
        "`python -m studio images`.\nassets:\n" + lines)
    try:
        got = (yaml.safe_load(text) or {}).get("assets")
        ok = isinstance(got, list) and len(got) == len(reg) + len(new)
    except yaml.YAMLError:
        ok = False
    if not ok:  # assets: не последний или в своей разметке — переписать целиком (комментарии потеряются)
        raw = yaml.safe_load(old) or {}
        raw["assets"] = list(raw.get("assets") or []) + new
        text = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=10 ** 9)
    tmp = f.with_name(f.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(f)
    return len(new)

"""Картинки для сцен (ROADMAP C5, docs/IMAGES.md): блок `images:` проекта и запросы `image:` сцен.

```yaml
# project.yaml (умолчание — studio.yaml → defaults; без блока = выключено)
images:
  enabled: true
  style: "flat vector illustration, palette #0B0F1A #4FD1C5 …"   # суффикс ко всем промптам
  budget_usd: 3            # остальное — умолчания config.SCHEMA["images"]: kie, nano-banana-2, 2K, seedream, rembg

# script/chNN.yaml — сцена просит картинку (одну или списком)
- id: s05
  template: image
  image:
    prompt: "a cozy bedroom at night, a person asleep in bed, a bedside lamp"
    role: scene            # scene | bg | subject | state_b (ROLES)
    layers: [room, bed with a person, bedside table with a lamp]   # только scene: что вынести в слои
    variant: 0             # сид: другой вариант той же картинки
```
Здесь — схема, проверки validate и путь картинки в кэше (`path`). Бэкенды и генерация — C5.3, команда `images` — C5.4.
"""
from __future__ import annotations

from pathlib import Path

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

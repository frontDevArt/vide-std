"""ИИ-трек под ролик (ElevenLabs Music, POST /v1/music): ровно в длину ролика, без вокала → assets/music/ + assets.yaml.

```yaml
# project.yaml
music:
  file: assets/music/a-1f2e3d4c.mp3   # выбранный вариант (пути печатает `python -m studio music`)
  under_lu: -15                       # громкость от голоса (studio/audio.py, music_relative)
  generate:
    model: music_v2_5                 # music_v1 | music_v2 | music_v2_5
    prompts:                          # имя: описание по-английски; каждый — отдельный платный трек
      a: "Instrumental synthwave …"
```
Длина — по build/timeline.json (после voice); трек ровно в длину ролика, поэтому концовка у музыки своя, а не обрыв.
Платно: кредиты ElevenLabs общие с озвучкой, ~CREDITS_PER_MIN за минуту; без `--yes` — только смета и остаток.
Кэш — по файлу: имя = <имя>-<хэш промпта, модели и длины>.mp3; есть файл — не платим второй раз.
Права: на платном тарифе ElevenLabs музыка разрешена в коммерческих роликах (elevenlabs.io/music-terms) — запись
в assets.yaml с источником, тарифом и song-id; qa без неё — ❌.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .project import stable_hash

MODELS = ("music_v1", "music_v2", "music_v2_5")
MODEL = "music_v2_5"
CREDITS_PER_MIN = 750  # замер gta6 2026-11-15: 2 трека по 75 с списали 1876 кредитов (кредиты общие с озвучкой)
FORMAT = "mp3_48000_192"
DIR = Path("assets") / "music"
LICENSE = ("ElevenLabs Eleven Music: коммерческое использование на платном тарифе (elevenlabs.io/music-terms), "
           "тариф {tier}")


class MusicUnavailable(RuntimeError):
    pass


@dataclass
class Job:
    name: str
    prompt: str
    model: str
    ms: int
    out: Path

    @property
    def credits(self) -> int:
        return math.ceil(self.ms / 60000 * CREDITS_PER_MIN)


def settings(proj) -> dict:
    return (proj.cfg.get("music") or {}).get("generate") or {}


def length_ms(proj) -> int:
    from .timing import load_timeline
    try:
        tl = load_timeline(proj)
    except (FileNotFoundError, SystemExit):
        raise MusicUnavailable("нет build/timeline.json — сначала python -m studio voice (длина трека = длина ролика)")
    return int(math.ceil(tl["total_frames"] / tl["fps"] * 10)) * 100


def issues(proj) -> list[str]:
    g = settings(proj)
    errs = []
    if g.get("model") is not None and g["model"] not in MODELS:
        errs.append(f"music.generate.model: '{g['model']}' — есть {', '.join(MODELS)}")
    pr = g.get("prompts")
    if not isinstance(pr, dict) or not pr or not all(isinstance(v, str) and v.strip() for v in pr.values()):
        errs.append("music.generate.prompts: нужен словарь {имя: описание трека по-английски}")
    return errs


def plan(proj) -> list[Job]:
    g = settings(proj)
    model, ms = g.get("model") or MODEL, length_ms(proj)
    return [Job(str(k), v.strip(), model, ms,
                proj.root / DIR / f"{k}-{stable_hash([v.strip(), model, ms], 8)}.mp3")
            for k, v in g["prompts"].items()]


def compose(job: Job, ws=None) -> dict:
    """Один платный запрос: трек в job.out (через .part), ответ → {'song_id'}. Ошибки 4xx — без ретраев."""
    import urllib.error
    import urllib.request

    from . import tts
    key = tts._el_key(ws)
    body = {"prompt": job.prompt, "music_length_ms": job.ms, "model_id": job.model, "force_instrumental": True}
    req = urllib.request.Request(f"{tts.EL_API}/music?output_format={FORMAT}", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json",
                                          "Accept": "audio/mpeg"})
    job.out.parent.mkdir(parents=True, exist_ok=True)
    part = job.out.with_name(job.out.name + ".part")
    try:
        with tts._el_urlopen(req, timeout=600) as r:
            part.write_bytes(r.read())
            sid = r.headers.get("song-id") or r.headers.get("x-song-id") or ""
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace").replace(key, "***")[:400]
        hint = {401: "ключ неверный", 402: "не хватает кредитов", 403: "доступ запрещён (тариф/прокси) — не ретраим",
                422: "запрос не принят (промпт с именами артистов или брендов?)", 429: "лимит запросов"}.get(e.code, "")
        raise MusicUnavailable(f"ElevenLabs Music HTTP {e.code} {hint}: {msg}")
    except urllib.error.URLError as e:
        raise MusicUnavailable(f"ElevenLabs недоступен: {e.reason}")
    if part.stat().st_size < 10000:
        part.unlink(missing_ok=True)
        raise MusicUnavailable("ElevenLabs Music вернул пустой файл")
    part.replace(job.out)
    return {"song_id": sid}


def record(proj, job: Job, song_id: str, tier: str) -> dict:
    return {"file": (DIR / job.out.name).as_posix(),
            "source": f"ElevenLabs Music API {job.model}, сгенерировано {dt.date.today().isoformat()}"
                      + (f", song-id {song_id}" if song_id else ""),
            "license": LICENSE.format(tier=tier or "?"), "by": "генерация", "prompt": job.prompt,
            "model": job.model, "seconds": job.ms / 1000, "credits": job.credits}

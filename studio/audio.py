"""Звук: дорожка голоса по таймлайну (сэмпл-точно), процедурная музыкальная подложка, микс.

- Голос кладётся в позицию «кадр начала сцены + t0 строки» -> рассинхрона с видео нет. Дорожка голоса со звуками
  собирается кусками по BLOCK сэмплов и пишется в WAV сразу int16 — весь ролик в RAM не держится (P4.4).
- Музыка: одна бесшовная петля, растягивается на весь ролик (на стыках глав музыка не рвётся); свой трек на главу —
  подложка с кроссфейдом (studio/music.py, ROADMAP C3).
- Подложка приглушается под голосом (sidechain), итог нормализуется по громкости (LUFS),
  сверху лимитер. Уровни проверяет qa.
- Музыка от голоса (`music.under_lu`, `music_relative`): уровень задаётся не сдвигом файла (`level_db` — у плотного
  трека и тихого одна цифра даёт разницу в 10 dB), а в LU относительно голоса в полосе речи 200 Гц–7 кГц — там, где
  музыка маскирует слова и что вообще играет динамик телефона. Приглушение — по сценарию: тайминг строк известен
  заранее, музыка уходит вниз до первого слога и не «качается» в коротких паузах; под речью — провал около 2,5 кГц.
- Промежуточные WAV (голос, сырой микс, приглушённая музыка, итог) — в папке `out`, которую даёт вызывающий
  (assemble — временная, удаляется после склейки). В build/mix/ остаются только кэш петли музыки и levels.json
  (громкость голоса и музыки для qa).
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

from . import sfx as FX, tts as T
from .music import music_loop  # noqa: F401 — прежнее место пэда (ROADMAP C3: studio/music.py)
from .project import Project
from .timing import load_timeline

SR = T.SR


BLOCK = SR * 30  # дорожка голоса собирается кусками по 30 с: весь ролик в RAM не держится (P4.4)


def _voice_lines(proj: Project, tl):
    """Строки озвучки [(сэмпл начала, путь WAV, длина)] в порядке таймлайна."""
    cache = proj.bdir("tts")
    lines = []
    for s in tl["scenes"]:
        base = s["start_frame"] * SR // tl["fps"]
        for L in s["lines"]:
            p = cache / L["wav"]
            with wave.open(str(p), "rb") as w:
                lines.append((base + int(round(L["t0"] * SR)), p, w.getnframes()))
    return lines


def _voice_block(lines, a0, a1, wavs):
    """Голос на сэмплах [a0, a1) — float32; wavs — прочитанные строки, что ещё понадобятся следующим кускам."""
    x = np.zeros(a1 - a0, np.float32)
    for i, (a, p, ln) in enumerate(lines):
        lo, hi = max(a, a0), min(a + ln, a1)
        if lo >= hi:
            continue
        if i not in wavs:
            wavs[i] = T.read_wav(p)
        x[lo - a0:hi - a0] += wavs[i][lo - a:hi - a]
    for i in [i for i in wavs if lines[i][0] + lines[i][2] <= a1]:
        del wavs[i]
    return x


def voice_track(proj: Project, tl, out: Path) -> str:
    """Голос + звук исходников (клип, видео с audio: true) + звуки появления -> out/voice.wav (int16), кусками по BLOCK."""
    n = int(round(tl["total_frames"] * SR / tl["fps"]))
    lines = _voice_lines(proj, tl)
    clips = media_track(proj, tl)
    ev = sfx_events(proj, tl) if proj.cfg.get("sfx", {}).get("enabled", True) else []
    gain = sfx_gain(proj, lines, n) if ev else 0.0
    out = out / "voice.wav"
    wavs = {}
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        for a0 in range(0, n, BLOCK):
            a1 = min(n, a0 + BLOCK)
            x = _voice_block(lines, a0, a1, wavs)
            for a, y in clips:
                lo, hi = max(a, a0), min(a + len(y), a1)
                if lo < hi:
                    x[lo - a0:hi - a0] += y[lo - a:hi - a]
            if ev:
                x += FX.track(a1 - a0, ev, gain, start=a0)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return str(out)


def media_track(proj: Project, tl):
    """Звук исходников сцен (ROADMAP C2: шаблоны media с `audio_clips()` — клип, видео с audio: true) ->
    [(сэмпл начала, float32)]: идёт в дорожку голоса — музыка под ним приглушается, итог нормализуется по LUFS."""
    from . import media as MD, packs as TP
    if not any(hasattr(TP.REGISTRY.get(s.get("template")), "audio_clips") for s in tl["scenes"]):
        return []  # звука исходников нет — prepare (хэш кода шаблонов) не нужен
    from .render import prepare
    tl2, ctx = prepare(proj)
    out = []
    for s in tl2["scenes"]:
        cls = TP.REGISTRY[s["template"]]
        if not hasattr(cls, "audio_clips"):
            continue
        base = s["start_frame"] * SR // tl2["fps"]
        for c in cls(ctx, s, s["state_in"]).audio_clips():
            y = MD.audio(c["file"], c["start"], c["dur"] - c["t"], c["speed"]) * 10 ** (c["gain_db"] / 20)
            y = y[:max(0, int(round((s["dur"] - c["t"]) * SR)))]  # не дольше сцены
            out.append((base + int(round(c["t"] * SR)), y.astype(np.float32)))
    return out


def sfx_events(proj: Project, tl):
    """События звуков из шаблонов (у кого есть sfx_events: шаблоны lab) -> [(t_глобальное, имя)]."""
    from .render import prepare
    from . import packs as TP
    tl2, ctx = prepare(proj)
    ev = []
    for s in tl2["scenes"]:
        tpl = TP.REGISTRY[s["template"]](ctx, s, s["state_in"])
        if hasattr(tpl, "sfx_events"):
            base = s["start_frame"] / tl2["fps"]
            ev += [(base + t, name) for t, name in tpl.sfx_events() if 0 <= t < s["dur"]]
    return sorted(ev)


def sfx_gain(proj: Project, lines, n):
    """Звуки появления на −28…−32 dB относительно голоса (STYLE §10): средний RMS речи — проходом по кускам.
    Своя громкость: sfx.level_db (сдвиг)."""
    ss, k, wavs = 0.0, 0, {}
    for a0 in range(0, n, BLOCK):
        x = _voice_block(lines, a0, min(n, a0 + BLOCK), wavs)
        act = x[np.abs(x) > 1e-3].astype(np.float64)
        ss, k = ss + float(np.sum(act ** 2)), k + len(act)
    rms = math.sqrt(ss / k) if k else 0.05
    return rms * 10 ** (float(proj.cfg.get("sfx", {}).get("level_db", 0)) / 20)


def ff(cmd):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-y"] + cmd, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-800:])
    return r.stderr


def loudness(path, start=None, end=None):
    pre = []
    if start is not None:
        pre = ["-ss", f"{start:.3f}", "-to", f"{end:.3f}"]
    err = ff(pre + ["-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)
    return (float(m[-1]) if m else None), (float(pk[-1]) if pk else None)


def mean_db(path, start, end):
    err = ff(["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(path), "-vn", "-af", "volumedetect",
              "-f", "null", "-"])
    m = re.search(r"mean_volume:\s+(-?[\d.]+) dB", err)
    return float(m.group(1)) if m else None


# ------------------------------------------------------------------ музыка от голоса (music.under_lu)
BAND = "highpass=f=200:poles=2,lowpass=f=7000:poles=2"  # полоса речи: маскировка слов и динамик телефона
REL = {"under_lu": -15.0, "open_lu": -6.0, "hold": 0.9, "carve_db": -4.0, "fade_in": 0.1, "fade_out": 1.5}
LOOKAHEAD, ATTACK, RELEASE_DELAY, RELEASE = 0.06, 0.25, 0.15, 0.8  # с: вниз до слога, вверх — после паузы
CARVE = "equalizer=f=2500:t=q:w=1:g={g:.2f}"  # провал под согласные (≈1,5–4 кГц)


def rel_settings(mc: dict) -> dict:
    """Настройки музыки от голоса: умолчания REL, поверх — заданные в music:."""
    return {k: float(mc[k]) if mc.get(k) is not None else v for k, v in REL.items()}


def band_loudness(path, mono=False):
    """Интегральная громкость в полосе речи (BAND + EBU R128), LUFS; тишина — None. mono — моно-файл меряется так,
    как звучит в стерео-миксе (в оба канала): EBU R128 складывает каналы, и моно без этого на 3 LU тише."""
    err = ff(["-i", str(path), "-vn", "-af", ("pan=stereo|c0=c0|c1=c0," if mono else "") + BAND + ",ebur128",
              "-f", "null", "-"])
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(m[-1]) if m and float(m[-1]) > -69 else None


def speech_regions(spans, hold: float) -> list[tuple[int, int]]:
    """Отрезки речи [(a, b)] в сэмплах; паузы короче hold с склеены — в них музыка не поднимается («качели»)."""
    out = []
    for a, b in sorted(spans):
        if out and a - out[-1][1] < hold * SR:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def duck_curve(regions, a0: int, a1: int) -> np.ndarray:
    """Доля приглушения s ∈ [0, 1] на сэмплах [a0, a1): 1 — под речью. Сценарий известен заранее: музыка уходит
    вниз за LOOKAHEAD до первого слога (sidechain так не умеет — он слышит слог, когда тот уже прозвучал) и
    поднимается через RELEASE_DELAY после паузы; рампы — полукосинус."""
    t = np.arange(a0, a1, dtype=np.float64)
    s = np.zeros(a1 - a0)
    la, at, rd, rl = (int(round(x * SR)) for x in (LOOKAHEAD, ATTACK, RELEASE_DELAY, RELEASE))
    for a, b in regions:
        r0, f1 = a - la - at, b + rd + rl
        if f1 <= a0 or r0 >= a1:
            continue
        s = np.maximum(s, np.minimum(np.clip((t - r0) / at, 0, 1), np.clip((f1 - t) / rl, 0, 1)))
    return 0.5 - 0.5 * np.cos(np.pi * s)


def edge_fade(a0: int, a1: int, n: int, fade_in: float, fade_out: float) -> np.ndarray:
    """Вход и выход музыки по краям ролика (равная мощность)."""
    t = np.arange(a0, a1, dtype=np.float64)
    g = np.ones(a1 - a0)
    if fade_in > 0:
        g *= np.clip(t / (fade_in * SR), 0, 1)
    if fade_out > 0:
        g *= np.clip((n - t) / (fade_out * SR), 0, 1)
    return np.sin(np.pi / 2 * g)


def speech_track(proj: Project, tl, out: Path) -> tuple[str, list[tuple[int, int]]]:
    """Только речь (строки + звук исходников, без звуков появления) -> out/speech.wav и её отрезки в сэмплах:
    по ней меряется громкость голоса и ставится приглушение."""
    n = int(round(tl["total_frames"] * SR / tl["fps"]))
    lines = _voice_lines(proj, tl)
    clips = media_track(proj, tl)
    spans = [(a, a + ln) for a, _, ln in lines] + [(a, a + len(y)) for a, y in clips]
    path = out / "speech.wav"
    wavs = {}
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        for a0 in range(0, n, BLOCK):
            a1 = min(n, a0 + BLOCK)
            x = _voice_block(lines, a0, a1, wavs)
            for a, y in clips:
                lo, hi = max(a, a0), min(a + len(y), a1)
                if lo < hi:
                    x[lo - a0:hi - a0] += y[lo - a:hi - a]
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return str(path), spans


def _read_stereo(w, k: int) -> np.ndarray:
    y = np.frombuffer(w.readframes(k), np.int16).astype(np.float32).reshape(-1, 2) / 32768
    return y if len(y) == k else np.vstack([y, np.zeros((k - len(y), 2), np.float32)])


def music_relative(proj: Project, tl, out: Path, log=print) -> tuple[Path, dict]:
    """Музыка от голоса -> out/music_ducked.wav (стерео) и замеры для levels.json.

    1. Трек (или подложка по главам) на длину ролика: как есть и с провалом CARVE под речь.
    2. Громкость голоса V и трека M в полосе речи; усиление трека под речью — V + under_lu − M, без речи — V + open_lu − M.
    3. Кривая приглушения по отрезкам речи из таймлайна (паузы короче hold склеены), между уровнями — в dB.
    4. Замер: музыка под речью из готовой дорожки, в той же полосе, LU от голоса — это и проверяет qa."""
    from . import music as M
    st = rel_settings(proj.cfg["music"])
    n = int(round(tl["total_frames"] * SR / tl["fps"]))
    D = n / SR
    speech, spans = speech_track(proj, tl, out)
    bed = M.bed(proj, tl, out)
    src = ["-i", str(bed)] if bed else ["-stream_loop", "-1", "-i", str(M.default_file(proj))]
    plain, carved = out / "music_plain.wav", out / "music_carved.wav"
    ff(src + ["-af", f"aformat=sample_rates={SR}:channel_layouts=stereo", "-t", f"{D:.3f}", "-c:a", "pcm_s16le",
              str(plain)])
    if st["carve_db"]:
        ff(["-i", str(plain), "-af", CARVE.format(g=st["carve_db"]), "-c:a", "pcm_s16le", str(carved)])
    else:
        carved = plain
    V, Mb = band_loudness(speech, mono=True), band_loudness(plain)  # голос — как в миксе: моно в оба канала
    if V is None or Mb is None:
        raise SystemExit("music.under_lu: " + ("в ролике нет речи — уровень не от чего считать, уберите under_lu"
                                               if V is None else "трек музыки — тишина"))
    # под речью звучит трек с провалом: его громкость и ставим в under_lu — та же громкость музыки, меньше маскировки
    Mc = band_loudness(carved) if carved != plain else Mb
    under_db, open_db = V + st["under_lu"] - (Mc or Mb), V + st["open_lu"] - Mb
    regions = speech_regions(spans, st["hold"])
    ducked, under = out / "music_ducked.wav", out / "music_under.wav"
    clipped = 0
    with wave.open(str(plain), "rb") as wp, wave.open(str(carved), "rb") as wc, \
            wave.open(str(ducked), "wb") as wd, wave.open(str(under), "wb") as wu:
        for w in (wd, wu):
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        for a0 in range(0, n, BLOCK):
            a1 = min(n, a0 + BLOCK)
            p = _read_stereo(wp, a1 - a0)
            c = _read_stereo(wc, a1 - a0) if carved != plain else p
            s = duck_curve(regions, a0, a1)
            fade = edge_fade(a0, a1, n, st["fade_in"], st["fade_out"])
            g = (10 ** ((open_db + s * (under_db - open_db)) / 20) * fade).astype(np.float32)
            y = (p * (1 - s)[:, None].astype(np.float32) + c * s[:, None].astype(np.float32)) * g[:, None]
            clipped += int(np.count_nonzero(np.abs(y) > 1))
            q = (np.clip(y, -1, 1) * 32767).astype(np.int16)
            wd.writeframes(q.tobytes())
            keep = (s > 0.999) & (fade > 0.999)
            if keep.any():
                wu.writeframes(q[keep].tobytes())
    mu = band_loudness(under)
    info = {"mode": "under_lu", "voice_band": round(V, 1), "music_band": round(Mb, 1),
            "under_lu": st["under_lu"], "open_lu": st["open_lu"], "carve_db": st["carve_db"],
            "under_actual": round(mu - V, 1) if mu is not None else None,
            "gain_db": [round(under_db, 1), round(open_db, 1)], "clipped": clipped}
    log(f"Музыка от голоса (полоса речи): под речью {info['under_actual']} LU (цель {st['under_lu']:+g}), без речи "
        f"{st['open_lu']:+g} LU; трек {Mb:.1f} LUFS → усиление {under_db:+.1f}…{open_db:+.1f} dB"
        + (f"; ⚠️ обрезано {clipped} сэмплов — трек слишком тихий" if clipped else ""))
    return ducked, info


def mix(proj: Project, out: Path, log=print) -> str:
    """Микс в папку out (промежуточные WAV и итог out/mix.wav); громкости голоса и музыки — в build/mix/levels.json."""
    tl = load_timeline(proj)
    D = tl["total_frames"] / tl["fps"]
    md = proj.bdir("mix")
    voice = voice_track(proj, tl, out)
    mc = proj.cfg["music"]
    raw = out / "mix_raw.wav"
    ducked = out / "music_ducked.wav"
    extra = {}
    if mc.get("enabled", True) and mc.get("under_lu") is not None and _voice_lines(proj, tl):
        ducked, extra = music_relative(proj, tl, out, log)
        ff(["-i", voice, "-i", str(ducked), "-filter_complex",
            f"[0:a]aformat=sample_rates={SR}:channel_layouts=mono,pan=stereo|c0=c0|c1=c0[v];"
            f"[1:a]aformat=sample_rates={SR}:channel_layouts=stereo[m];[v][m]amix=inputs=2:normalize=0:duration=first[a]",
            "-map", "[a]", "-t", f"{D:.3f}", "-c:a", "pcm_s16le", str(raw)])
    elif mc.get("enabled", True):
        from . import music as M
        bed = M.bed(proj, tl, out)  # music.by_chapter: подложка уже на всю длину, с кроссфейдами
        src = ["-i", str(bed)] if bed else ["-stream_loop", "-1", "-i", str(M.default_file(proj))]
        lvl = float(mc.get("level_db", -24))
        duck = ("[m][sc]sidechaincompress=threshold=0.02:ratio=5:attack=40:release=700:makeup=1[md];"
                if mc.get("duck", True) else "[m]anull[md];")
        fc = (f"[0:a]aformat=sample_rates={SR}:channel_layouts=mono,pan=stereo|c0=c0|c1=c0,asplit=2[v][sc];"
              f"[1:a]aformat=sample_rates={SR}:channel_layouts=stereo,atrim=0:{D:.3f},asetpts=PTS-STARTPTS,"
              f"volume={lvl}dB,afade=t=in:d=1.2,afade=t=out:st={max(0, D - 2.0):.3f}:d=2.0[m];"
              + duck +
              "[md]asplit=2[md1][md2];[v][md1]amix=inputs=2:normalize=0:duration=first[a]")
        ff(["-i", voice] + src + ["-filter_complex", fc,
            "-map", "[a]", "-t", f"{D:.3f}", "-c:a", "pcm_s16le", str(raw),
            "-map", "[md2]", "-t", f"{D:.3f}", "-c:a", "pcm_s16le", str(ducked)])
    else:
        ff(["-i", voice, "-af", "pan=stereo|c0=c0|c1=c0", "-c:a", "pcm_s16le", str(raw)])
    I, _ = loudness(raw)
    target = float(proj.cfg.get("loudness", -16))
    gain = target - I
    res = out / "mix.wav"
    ff(["-i", str(raw), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.84:level=disabled:attack=5:release=60",
        "-t", f"{D:.3f}", "-c:a", "pcm_s16le", str(res)])
    (md / "levels.json").write_text(json.dumps({
        "voice_lufs": loudness(voice)[0],
        "music_lufs": loudness(ducked)[0] if ducked.exists() else None, **extra}), encoding="utf-8")
    for old in ("voice.wav", "mix_raw.wav", "music_ducked.wav", "mix.wav"):  # от сборок до P4.2
        (md / old).unlink(missing_ok=True)
    log(f"Микс: {res.name}, исходно {I:.1f} LUFS -> цель {target} LUFS (усиление {gain:+.1f} dB)")
    return str(res)

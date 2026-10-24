"""Звук: дорожка голоса по таймлайну (сэмпл-точно), процедурная музыкальная подложка, микс.

- Голос кладётся в позицию «кадр начала сцены + t0 строки» -> рассинхрона с видео нет. Дорожка голоса со звуками
  собирается кусками по BLOCK сэмплов и пишется в WAV сразу int16 — весь ролик в RAM не держится (P4.4).
- Музыка: одна бесшовная петля, растягивается на весь ролик (на стыках глав музыка не рвётся); свой трек на главу —
  подложка с кроссфейдом (studio/music.py, ROADMAP C3).
- Подложка приглушается под голосом (sidechain), итог нормализуется по громкости (LUFS),
  сверху лимитер. Уровни проверяет qa.
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


def mix(proj: Project, out: Path, log=print) -> str:
    """Микс в папку out (промежуточные WAV и итог out/mix.wav); громкости голоса и музыки — в build/mix/levels.json."""
    tl = load_timeline(proj)
    D = tl["total_frames"] / tl["fps"]
    md = proj.bdir("mix")
    voice = voice_track(proj, tl, out)
    mc = proj.cfg["music"]
    raw = out / "mix_raw.wav"
    ducked = out / "music_ducked.wav"
    if mc.get("enabled", True):
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
        "music_lufs": loudness(ducked)[0] if ducked.exists() else None}), encoding="utf-8")
    for old in ("voice.wav", "mix_raw.wav", "music_ducked.wav", "mix.wav"):  # от сборок до P4.2
        (md / old).unlink(missing_ok=True)
    log(f"Микс: {res.name}, исходно {I:.1f} LUFS -> цель {target} LUFS (усиление {gain:+.1f} dB)")
    return str(res)

"""Звук: дорожка голоса по таймлайну (сэмпл-точно), процедурная музыкальная подложка, микс.

- Голос кладётся в позицию «кадр начала сцены + t0 строки» -> рассинхрона с видео нет.
- Музыка: одна бесшовная петля, растягивается на весь ролик (на стыках глав музыка не рвётся).
- Подложка приглушается под голосом (sidechain), итог нормализуется по громкости (LUFS),
  сверху лимитер. Уровни проверяет qa.
"""
from __future__ import annotations

import math
import re
import subprocess

import numpy as np

from . import tts as T
from .project import Project
from .timing import load_timeline

SR = T.SR


def voice_track(proj: Project, tl) -> str:
    n = int(round(tl["total_frames"] * SR / tl["fps"]))
    x = np.zeros(n, np.float32)
    cache = proj.bdir("tts")
    for s in tl["scenes"]:
        base = s["start_frame"] * SR // tl["fps"]
        for L in s["lines"]:
            y = T.read_wav(cache / L["wav"])
            a = base + int(round(L["t0"] * SR))
            b = min(n, a + len(y))
            x[a:b] += y[: b - a]
    if proj.cfg.get("sfx", {}).get("enabled", True):
        x += sfx_track(proj, tl, n, x)
    out = proj.bdir("mix") / "voice.wav"
    T.write_wav(out, x)
    return str(out)


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


def sfx_track(proj: Project, tl, n, voice):
    """Звуки появления на −28…−32 dB относительно голоса (STYLE §10). Своя громкость: sfx.level_db (сдвиг)."""
    from . import sfx as FX
    ev = sfx_events(proj, tl)
    if not ev:
        return np.zeros(n, np.float32)
    act = voice[np.abs(voice) > 1e-3]
    rms = float(np.sqrt(np.mean(act ** 2))) if len(act) else 0.05
    gain = 10 ** (float(proj.cfg.get("sfx", {}).get("level_db", 0)) / 20)
    return FX.track(n, ev, rms * gain)


def music_loop(path, seconds=32.0, seed=5):
    """Тёмный эмбиент-пэд: Am – F – C – G, по 8 с на аккорд, бесшовная петля."""
    n = int(SR * seconds)
    t = np.arange(n, dtype=np.float64) / SR
    chords = [[57, 60, 64, 69], [53, 57, 60, 65], [48, 55, 60, 64], [55, 59, 62, 67]]
    seg = seconds / len(chords)
    out = np.zeros((n, 2), np.float64)
    rng = np.random.default_rng(seed)
    for ci, notes in enumerate(chords):
        c0 = ci * seg
        # окно аккорда с кроссфейдом xf, по кругу; соседние окна в сумме дают 1 (sin² + cos²)
        xf = 2.0
        u = (t - c0 + xf / 2) % seconds
        w = (np.sin(np.pi / 2 * np.clip(u / xf, 0, 1)) ** 2
             * np.sin(np.pi / 2 * np.clip((seg + xf - u) / xf, 0, 1)) ** 2)
        w = np.where(u < seg + xf, w, 0.0)
        for k, m in enumerate(notes):
            f = 440 * 2 ** ((m - 69) / 12)
            f = round(f * seconds) / seconds  # целое число периодов на петлю -> без щелчков
            for det, pan in ((-0.6, 0.3), (0.0, 0.5), (0.7, 0.7)):
                fd = round((f + det) * seconds) / seconds
                p = rng.uniform(0, 6.28)
                s = np.sin(2 * math.pi * fd * t + p) * 0.6 + 0.25 * np.sin(4 * math.pi * fd * t + p)
                out[:, 0] += s * w * (1 - pan) * 0.05
                out[:, 1] += s * w * pan * 0.05
        fb = 440 * 2 ** ((notes[0] - 12 - 69) / 12)
        fb = round(fb * seconds) / seconds
        bass = np.sin(2 * math.pi * fb * t) * w * 0.10
        out += bass[:, None]
    # медленное «дыхание» громкости (тоже целое число периодов)
    lfo = 0.85 + 0.15 * np.sin(2 * math.pi * (4 / seconds) * t)
    out *= lfo[:, None]
    out /= np.abs(out).max() + 1e-9
    out *= 10 ** (-6 / 20)
    pcm = (np.clip(out, -1, 1) * 32767).astype(np.int16)
    import wave
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    return str(path)


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


def mix(proj: Project, log=print) -> str:
    tl = load_timeline(proj)
    D = tl["total_frames"] / tl["fps"]
    md = proj.bdir("mix")
    voice = voice_track(proj, tl)
    mc = proj.cfg["music"]
    raw = md / "mix_raw.wav"
    if mc.get("enabled", True):
        loop = mc.get("file") or str(md / "music_loop.wav")
        if not mc.get("file") and not (md / "music_loop.wav").exists():
            music_loop(loop)
        lvl = float(mc.get("level_db", -24))
        duck = ("[m][sc]sidechaincompress=threshold=0.02:ratio=5:attack=40:release=700:makeup=1[md];"
                if mc.get("duck", True) else "[m]anull[md];")
        fc = (f"[0:a]aformat=sample_rates={SR}:channel_layouts=mono,pan=stereo|c0=c0|c1=c0,asplit=2[v][sc];"
              f"[1:a]aformat=sample_rates={SR}:channel_layouts=stereo,atrim=0:{D:.3f},asetpts=PTS-STARTPTS,"
              f"volume={lvl}dB,afade=t=in:d=1.2,afade=t=out:st={max(0, D - 2.0):.3f}:d=2.0[m];"
              + duck +
              "[md]asplit=2[md1][md2];[v][md1]amix=inputs=2:normalize=0:duration=first[a]")
        ff(["-i", voice, "-stream_loop", "-1", "-i", loop, "-filter_complex", fc,
            "-map", "[a]", "-t", f"{D:.3f}", "-c:a", "pcm_s16le", str(raw),
            "-map", "[md2]", "-t", f"{D:.3f}", "-c:a", "pcm_s16le", str(md / "music_ducked.wav")])
    else:
        ff(["-i", voice, "-af", "pan=stereo|c0=c0|c1=c0", "-c:a", "pcm_s16le", str(raw)])
    I, _ = loudness(raw)
    target = float(proj.cfg.get("loudness", -16))
    gain = target - I
    out = md / "mix.wav"
    ff(["-i", str(raw), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.84:level=disabled:attack=5:release=60",
        "-t", f"{D:.3f}", "-c:a", "pcm_s16le", str(out)])
    log(f"Микс: {out.name}, исходно {I:.1f} LUFS -> цель {target} LUFS (усиление {gain:+.1f} dB)")
    return str(out)

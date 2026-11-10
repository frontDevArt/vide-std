"""Трек студии Etagi кодом: «Toon Drive» — бодрый промо-грув 124 BPM, ля минор (Am–F–C–G), 24 такта ≈ 46 с.

    python studios/etagi/brand/music/make_track.py      → toon-drive.wav (48 кГц, стерео, 16 бит)

Всё синтезируется numpy/scipy: бочка, клэп, хэты, тарелка, бас, пэд (supersaw), арпеджио с дилеем, райзеры и удар
в начале. Лицензия — CC0 (наш код, без сэмплов). Склейки ролика ставит в долю `music.sync: beat` (детектор студии).
"""
from __future__ import annotations

import warnings
import wave
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
from scipy.signal import butter, sosfilt  # noqa: E402

SR = 48000
BPM = 124.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
BARS = 24
N = int(SR * BAR * BARS) + SR * 3
OUT = Path(__file__).resolve().parent / "toon-drive.wav"
rng = np.random.default_rng(13)

# аккорды по тактам (MIDI): бас, пэд
PROG = [(33, (57, 60, 64)), (29, (53, 57, 60)), (36, (55, 60, 64)), (31, (55, 59, 62))]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def filt(x, kind, f, order=2):
    f = np.atleast_1d(f) / (SR / 2)
    return sosfilt(butter(order, f if len(f) > 1 else f[0], btype=kind, output="sos"), x)


def saw(f, n, phase=0.0):
    t = np.arange(n) / SR
    return 2 * ((f * t + phase) % 1.0) - 1


def env(n, a, d, s=0.0, r=0.0, hold=None):
    """ADSR по сэмплам: атака a, спад d до уровня s, держится hold с, отпуск r."""
    t = np.arange(n) / SR
    e = np.where(t < a, t / max(a, 1e-5), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-5)))
    if hold is not None:
        e = e * np.where(t < hold, 1.0, np.exp(-(t - hold) / max(r, 1e-5)))
    return e


def add(buf, x, at, pan=0.0, gain=1.0):
    i = int(round(at * SR))
    if i >= len(buf):
        return
    x = x[: len(buf) - i] * gain
    buf[i:i + len(x), 0] += x * np.sqrt(0.5 * (1 - pan))
    buf[i:i + len(x), 1] += x * np.sqrt(0.5 * (1 + pan))


# ---------------------------------------------------------------- инструменты
def kick():
    n = int(SR * 0.45)
    t = np.arange(n) / SR
    f = 46 + 120 * np.exp(-t / 0.035)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.30)
    click = filt(rng.standard_normal(n), "highpass", 2500) * np.exp(-t / 0.004) * 0.35
    return np.tanh(1.6 * (body + click))


def clap():
    n = int(SR * 0.35)
    t = np.arange(n) / SR
    x = filt(rng.standard_normal(n), "bandpass", (900, 3200))
    e = sum(np.where(t >= o, np.exp(-(t - o) / 0.012), 0) for o in (0, 0.011, 0.022)) * 0.6
    e += np.where(t >= 0.03, np.exp(-(t - 0.03) / 0.11), 0)
    return x * e * 0.9


def hat(open_=False):
    n = int(SR * (0.35 if open_ else 0.08))
    t = np.arange(n) / SR
    return filt(rng.standard_normal(n), "highpass", 7500) * np.exp(-t / (0.16 if open_ else 0.025))


def crash():
    n = int(SR * 2.2)
    t = np.arange(n) / SR
    return filt(rng.standard_normal(n), "highpass", 4500) * np.exp(-t / 0.7)


def riser(dur):
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    out = np.zeros(n)
    hop = 2048
    for i in range(0, n, hop):  # полоса шума едет вверх
        k = i / n
        seg = filt(x[i:i + hop * 2], "bandpass", (300 + 5000 * k ** 2, 900 + 9000 * k ** 2))
        w = np.hanning(len(seg))
        out[i:i + len(seg)] += seg * w
    return out * (t / dur) ** 2


def impact():
    n = int(SR * 2.0)
    t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t / 0.08)) / SR) * np.exp(-t / 0.6)
    noise = filt(rng.standard_normal(n), "lowpass", 3000) * np.exp(-t / 0.25) * 0.4
    return np.tanh(1.3 * (boom + noise))


def bass_note(m, dur):
    n = int(SR * dur)
    x = 0.6 * saw(hz(m), n) + 0.5 * np.sin(2 * np.pi * hz(m) * np.arange(n) / SR)
    x = filt(x, "lowpass", 520, 2)
    return x * env(n, 0.004, 0.18, 0.55, 0.03, hold=dur - 0.03)


def pad_chord(notes, dur):
    n = int(SR * (dur + 0.4))
    x = np.zeros(n)
    for m in notes:
        for d in (-0.11, -0.04, 0.0, 0.05, 0.12):
            x += saw(hz(m) * 2 ** (d / 12), n, rng.random())
    x = filt(x / (5 * len(notes)), "lowpass", 1900, 2)
    return x * env(n, 0.06, 1.0, 0.85, 0.35, hold=dur)


def pluck(m, dur=0.22):
    n = int(SR * dur)
    x = saw(hz(m), n) * 0.7 + saw(hz(m) * 1.004, n) * 0.5
    return filt(x, "lowpass", 3400, 2) * env(n, 0.002, 0.09)


def sidechain(n, kicks, depth=0.65, rel=0.13):
    g = np.ones(n)
    t = np.arange(n) / SR
    for k in kicks:
        i = int(k * SR)
        m = t[i:] - k
        g[i:] = np.minimum(g[i:], 1 - depth * np.exp(-m / rel))
    return g


def main():
    drums, music = np.zeros((N, 2)), np.zeros((N, 2))
    kicks = []
    final_bar = BARS - 2
    for b in range(BARS):
        t0 = b * BAR
        root, chord = PROG[b % 4]
        if b == final_bar:  # финальный удар и хвост пэда
            add(drums, kick(), t0, gain=1.0); add(drums, crash(), t0, gain=0.35); add(drums, impact(), t0, gain=0.55)
            add(music, pad_chord(PROG[0][1], BAR * 1.5), t0, gain=0.9)
            add(music, bass_note(PROG[0][0], BAR), t0, gain=0.9)
            kicks.append(t0)
            break
        for q in range(4):
            tb = t0 + q * BEAT
            add(drums, kick(), tb, gain=1.0); kicks.append(tb)
            if q in (1, 3):
                add(drums, clap(), tb, pan=0.05, gain=0.42)
            add(drums, hat(open_=(q == 3 and b % 2)), tb + BEAT / 2, pan=0.25, gain=0.22 if q == 3 and b % 2 else 0.16)
            if b >= 4:  # шестнадцатые хэты со второй фразы
                for s in (0.25, 0.75):
                    add(drums, hat(), tb + s * BEAT, pan=-0.3, gain=0.07)
        if b % 8 == 0:
            add(drums, crash(), t0, gain=0.28)
        if b in (7, 15):  # райзер и дробь клэпа перед новой фразой
            add(drums, riser(BAR), t0, gain=0.22)
            for s in range(8):
                add(drums, clap(), t0 + 2 * BEAT + s * BEAT / 4, gain=0.12 + 0.03 * s)
        # бас — восьмые, упор на слабую долю
        for e in range(8):
            add(music, bass_note(root + (12 if e % 4 == 3 else 0), BEAT / 2 * 0.9), t0 + e * BEAT / 2,
                gain=0.42 if e % 2 else 0.28)
        add(music, pad_chord(chord, BAR), t0, gain=0.55)
        if b >= 4:  # арпеджио шестнадцатыми с пинг-понг дилеем
            pat = [0, 1, 2, 1, 0, 2, 1, 2, 0, 1, 2, 1, 2, 1, 0, 2]
            for s, k in enumerate(pat):
                m = chord[k] + 12
                ts = t0 + s * BEAT / 4
                add(music, pluck(m), ts, pan=-0.35, gain=0.20)
                add(music, pluck(m), ts + 3 * BEAT / 4, pan=0.45, gain=0.08)
    add(drums, impact(), 0.0, gain=0.6)  # удар на первом кадре
    music *= sidechain(N, kicks)[:, None]
    mix = drums + music
    mix = np.tanh(1.15 * mix) / np.tanh(1.15)
    end = int((final_bar * BAR + BAR * 1.6) * SR)
    mix = mix[:end]
    fade = int(SR * 0.4)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    mix *= 10 ** (-1 / 20) / np.max(np.abs(mix))
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    print(f"✅ {OUT} — {len(mix) / SR:.1f} c, {BPM:g} BPM")


if __name__ == "__main__":
    main()

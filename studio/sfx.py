"""Звуки появления (channel/STYLE.md, раздел 10): pop, tick, whoosh, swish, thud, riser — синтез numpy, свои
(лицензия — assets/sfx/LICENSES.md). Шаблоны отдают события `sfx_events()` -> [(t_локальное, имя)];
дорожка собирается по таймлайну и кладётся на −28…−32 dB относительно голоса.
"""
from __future__ import annotations

import numpy as np

SR = 48000
# уровень события относительно среднего уровня речи (dB), STYLE §10: −28…−32
LEVEL = {"pop": -30, "tick": -32, "swish": -30, "whoosh": -28, "riser": -30, "thud": -34}


def _env(n, a, rel):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * np.exp(-np.maximum(0, t - a) / max(rel, 1e-4) * 4.6)
    return e.astype(np.float32)


def _sweep(f0, f1, dur, kind="sine"):
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    if kind == "tri":
        return (2 / np.pi * np.arcsin(np.sin(ph))).astype(np.float32)
    return np.sin(ph).astype(np.float32)


def _bandnoise(dur, f0, f1, q=1.2, seed=0):
    """Шум с полосой, центр которой едет f0 -> f1 (FFT-фильтр по кускам)."""
    n = int(SR * dur)
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n).astype(np.float32)
    out = np.zeros(n, np.float32)
    hop = 1024
    win = np.hanning(2 * hop).astype(np.float32)
    for i in range(0, n, hop):
        seg = x[i:i + 2 * hop]
        if len(seg) < 2 * hop:
            seg = np.pad(seg, (0, 2 * hop - len(seg)))
        fc = f0 * (f1 / f0) ** min(1, i / max(1, n))
        X = np.fft.rfft(seg * win)
        fr = np.fft.rfftfreq(2 * hop, 1 / SR)
        bw = fc / q
        X *= np.exp(-0.5 * ((fr - fc) / bw) ** 2)
        y = np.fft.irfft(X).astype(np.float32)
        m = min(2 * hop, n - i)
        out[i:i + m] += y[:m]
    return out


def make(name):
    if name == "pop":
        y = _sweep(900, 480, 0.15) * _env(int(SR * 0.15), 0.005, 0.10)
    elif name == "tick":
        y = _sweep(2100, 2100, 0.06, "tri") * _env(int(SR * 0.06), 0.002, 0.03)
    elif name == "whoosh":
        y = _bandnoise(0.6, 300, 2400, 1.2, 1) * _env(int(SR * 0.6), 0.2, 0.35)
    elif name == "swish":
        y = _bandnoise(0.3, 3500, 5000, 0.8, 2) * _env(int(SR * 0.3), 0.02, 0.18)
    elif name == "riser":
        n = int(SR * 0.55)
        y = _bandnoise(0.55, 400, 3600, 3, 3) * (np.linspace(0, 1, n) ** 2.2).astype(np.float32)
        y[-int(SR * 0.04):] *= np.linspace(1, 0, int(SR * 0.04))
    elif name == "thud":
        n = int(SR * 0.45)
        y = _sweep(150, 48, 0.45) * _env(n, 0.004, 0.35)
        y[: int(SR * 0.15)] += 0.3 * _bandnoise(0.15, 300, 300, 0.4, 4) * _env(int(SR * 0.15), 0.002, 0.1)
    else:
        return np.zeros(1, np.float32)
    y = y.astype(np.float32)
    rms = float(np.sqrt(np.mean(y ** 2)) + 1e-9)
    return y / rms  # нормированы по RMS = 1: уровень задаёт LEVEL


_CACHE = {}


def track(n_samples, events, voice_rms, start=0):
    """events: [(t_глобальное, имя)] -> моно дорожка из n_samples сэмплов с сэмпла start (кусок ролика, P4.4).
    voice_rms — средний RMS речи (линейно)."""
    out = np.zeros(n_samples, np.float32)
    for t, name in events:
        if name not in _CACHE:
            _CACHE[name] = make(name)
        a = int(round(t * SR)) - start
        if a >= n_samples or a + len(_CACHE[name]) <= 0:
            continue
        y = _CACHE[name] * voice_rms * 10 ** (LEVEL.get(name, -30) / 20)
        if a < 0:
            y, a = y[-a:], 0
        b = min(n_samples, a + len(y))
        out[a:b] += y[: b - a]
    return out

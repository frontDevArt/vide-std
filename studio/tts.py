"""Синтез речи с кэшем. Бэкенды: rhvoice (офлайн, проверен), edge (онлайн, лучшее качество),
piper (офлайн нейросетевой). Результат всегда: WAV 48 кГц моно 16 бит, тишина по краям срезана.

Кэш: build/tts/<hash>.wav, ключ = бэкенд+голос+темп+текст. Повторный запуск не синтезирует заново.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .project import STUDIO_ROOT, stable_hash

SR = 48000
TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
        "afade=t=in:d=0.008,areverse,afade=t=in:d=0.02,areverse")


class TTSUnavailable(RuntimeError):
    pass


def run(cmd, **kw):
    """Все внешние процессы — с stdin=/dev/null: иначе они «съедают» ввод циклов (урок из логов)."""
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, **kw)


# ---------------------------------------------------------------- backends
def _rhvoice(text, voice, rate, out_raw):
    exe = STUDIO_ROOT / "tools" / "rhvoice" / "rhvoice"
    if not exe.exists():
        raise TTSUnavailable("RHVoice не установлен: bash tools/setup_rhvoice.sh")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text + "\n")
        tp = f.name
    try:
        run([str(exe), voice, str(int(round(rate))), tp, str(out_raw)])
    finally:
        os.unlink(tp)


def _edge(text, voice, rate, out_raw):
    exe = shutil.which("edge-tts")
    if not exe:
        raise TTSUnavailable("edge-tts не найден: pip install edge-tts (нужен интернет)")
    pct = int(round(rate - 100))
    r = run([exe, "--voice", voice, f"--rate={pct:+d}%", "--text", text, "--write-media", str(out_raw)])
    if r.returncode:
        raise TTSUnavailable("edge-tts: " + r.stderr[-300:])


def _piper(text, voice, rate, out_raw):
    exe = shutil.which("piper")
    model = Path(voice)
    if not model.is_absolute():
        model = STUDIO_ROOT / "tools" / "piper-voices" / f"{voice}.onnx"
    if not exe or not model.exists():
        raise TTSUnavailable("piper или модель не найдены (см. docs/TTS.md)")
    r = subprocess.run([exe, "--model", str(model), "--output_file", str(out_raw),
                        "--length_scale", f"{100.0 / rate:.3f}"],
                       input=text, capture_output=True, text=True)
    if r.returncode:
        raise TTSUnavailable("piper: " + r.stderr[-300:])


BACKENDS = {"rhvoice": _rhvoice, "edge": _edge, "piper": _piper}


def probe(tts_cfg) -> str:
    """Проверяет, что синтез реально работает (а не просто «бинарник есть»)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        BACKENDS[tts_cfg["backend"]]("Проверка голоса.", tts_cfg["voice"], 100, tmp / "p.wav")
        if not (tmp / "p.wav").exists() or (tmp / "p.wav").stat().st_size < 2000:
            raise TTSUnavailable(f"{tts_cfg['backend']}: синтез вернул пустой файл")
        return "ok"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- synth + cache
def synth(text: str, tts_cfg: dict, rate: float, cache_dir: Path) -> Path:
    key = stable_hash([tts_cfg["backend"], tts_cfg["voice"], round(float(rate), 1), text], 16)
    out = cache_dir / f"{key}.wav"
    if out.exists() and out.stat().st_size > 1000:
        return out
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw = cache_dir / f"{key}.raw{'.mp3' if tts_cfg['backend'] == 'edge' else '.wav'}"
    BACKENDS[tts_cfg["backend"]](text, tts_cfg["voice"], rate, raw)
    if not raw.exists() or raw.stat().st_size < 1000:
        raise TTSUnavailable(f"Синтез не дал звука для: {text[:60]!r}")
    r = run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", TRIM,
             "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", str(out)])
    raw.unlink(missing_ok=True)
    if r.returncode or not out.exists():
        raise RuntimeError("ffmpeg trim: " + r.stderr[-300:])
    return out


def read_wav(path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def write_wav(path, x: np.ndarray, channels=1):
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def duration(path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def silences(x: np.ndarray, min_len=0.06, rel_db=-34.0):
    """Внутренние паузы [(start, end)] в секундах. Порог относительно пика фразы."""
    hop = int(SR * 0.01)
    n = len(x) // hop
    if n < 3:
        return []
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms / (rms.max() + 1e-9))
    quiet = db < rel_db
    out, i = [], 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            a, b = i * 0.01, j * 0.01
            if b - a >= min_len and a > 0.05 and b < n * 0.01 - 0.05:
                out.append((round(a, 3), round(b, 3)))
            i = j
        else:
            i += 1
    return out

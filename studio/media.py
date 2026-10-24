"""Медиа для шаблонов (ROADMAP C2): фото, кадры видео и звук исходника — через Pillow и ffmpeg, детерминированно.

- `image(path)` — RGBA, кэш на процесс; `cover`/`contain` — вписать в рамку.
- `Video` — кадры видео потоком из ffmpeg (сырые RGB, уже нужного размера, fps ролика, скорость `speed`): кадры
  сцены идут подряд, поток читается последовательно; прыжок назад или далеко вперёд — перезапуск с `-ss`.
  Кадр после конца исходника — последний (стоп-кадр). Весь клип в память не грузится.
- `audio(path, start, dur, speed)` — звук исходника (моно, SR студии, float32) для микса (audio.media_track).
- `probe(path)` — длительность, размер, есть ли звук.
"""
from __future__ import annotations

import functools
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

SR = 48000  # = tts.SR (без импорта tts: модуль рисования)


@functools.lru_cache(maxsize=32)
def _image(path, mtime):
    return Image.open(path).convert("RGBA")


def image(path) -> Image.Image:
    p = Path(path)
    return _image(str(p), p.stat().st_mtime_ns)


def cover(img, w, h, focus=(0.5, 0.5)):
    """Заполнить рамку w×h с обрезкой (focus — какая точка картинки остаётся в кадре, доли)."""
    k = max(w / img.width, h / img.height)
    sw, sh = max(w, round(img.width * k)), max(h, round(img.height * k))
    im = img.resize((sw, sh), Image.LANCZOS)
    x = round((sw - w) * min(1, max(0, focus[0])))
    y = round((sh - h) * min(1, max(0, focus[1])))
    return im.crop((x, y, x + w, y + h))


def contain(img, w, h):
    """Вписать целиком (поля прозрачные)."""
    k = min(w / img.width, h / img.height)
    im = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(im, ((w - im.width) // 2, (h - im.height) // 2))
    return out


def fit(img, w, h, mode="cover", focus=(0.5, 0.5)):
    return contain(img, w, h) if mode == "contain" else cover(img, w, h, focus)


@functools.lru_cache(maxsize=32)
def _probe(path, mtime):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                        "-of", "json", path], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode:
        raise RuntimeError(f"ffprobe {Path(path).name}: {r.stderr.strip()[-300:]}")
    d = json.loads(r.stdout)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    return {"duration": float((d.get("format") or {}).get("duration") or 0),
            "size": (int(v["width"]), int(v["height"])) if v else None,
            "audio": any(s.get("codec_type") == "audio" for s in d.get("streams", []))}


def probe(path) -> dict:
    p = Path(path)
    return _probe(str(p), p.stat().st_mtime_ns)


def is_video(path) -> bool:
    from .assets import VIDEO_EXT
    return str(path).lower().endswith(VIDEO_EXT)


def is_audio(path) -> bool:
    from .assets import AUDIO_EXT
    return str(path).lower().endswith(AUDIO_EXT)


class Video:
    """Кадры видео размером w×h (cover или contain), fps ролика, со скоростью speed от секунды start исходника.
    `frame(k)` — кадр k сцены (t = k / fps) как RGBA."""
    JUMP = 2.0  # с: прыжок вперёд дальше — перезапуск с -ss, а не чтение подряд

    def __init__(self, path, w, h, fps, start=0.0, speed=1.0, mode="cover"):
        self.path, self.w, self.h, self.fps = str(path), int(w), int(h), int(fps)
        self.start, self.speed, self.mode = float(start), float(speed), mode
        info = probe(path)
        self.n_src = max(1, int((info["duration"] - self.start) / self.speed * self.fps))  # кадров до конца исходника
        self.proc, self.k, self.last = None, None, None

    def _open(self, k):
        self.close()
        ss = self.start + k / self.fps * self.speed
        sc = (f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase:flags=bicubic,crop={self.w}:{self.h}"
              if self.mode != "contain" else
              f"scale={self.w}:{self.h}:force_original_aspect_ratio=decrease:flags=bicubic,"
              f"pad={self.w}:{self.h}:(ow-iw)/2:(oh-ih)/2:color=black@0")
        vf = f"setpts=(PTS-STARTPTS)/{self.speed:g},fps={self.fps},{sc},format=rgba"
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{ss:.4f}", "-i", self.path, "-an", "-vf", vf,
                                      "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.k = k

    def _read(self):
        n = self.w * self.h * 4
        buf = self.proc.stdout.read(n) if self.proc else b""
        if len(buf) < n:
            self.close()
            return None
        self.k += 1
        return Image.frombuffer("RGBA", (self.w, self.h), buf, "raw", "RGBA", 0, 1).copy()

    def frame(self, k):
        k = max(0, min(int(k), self.n_src - 1))
        if self.proc is None or self.k is None or k < self.k or k > self.k + self.JUMP * self.fps:
            if self.last is not None and self.last[0] == k:
                return self.last[1]
            self._open(k)
        img = None
        while self.k is not None and self.k <= k:
            nxt = self._read()
            if nxt is None:
                break
            img = nxt
        if img is None:  # исходник кончился раньше оценки — стоп-кадр
            img = self.last[1] if self.last else Image.new("RGBA", (self.w, self.h), (0, 0, 0, 255))
        self.last = (k, img)
        return img

    def close(self):
        if self.proc is not None:
            try:
                self.proc.stdout.close()
                self.proc.kill()
                self.proc.wait()
            except OSError:
                pass
        self.proc, self.k = None, None

    def __del__(self):
        self.close()


def still(path, w, h, mode="cover", at=0.0):
    """Один кадр видео (или картинка) размером w×h — для превью, обложек и screen по картинке."""
    if not is_video(path):
        return fit(image(path), w, h, mode)
    v = Video(path, w, h, 30, at, 1.0, mode)
    try:
        return v.frame(0)
    finally:
        v.close()


def audio(path, start=0.0, dur=None, speed=1.0) -> np.ndarray:
    """Звук исходника: моно float32, SR, от start (с), длиной dur (с итога, после скорости), темп speed (0,5–2)."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{float(start):.4f}", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR)]
    if abs(float(speed) - 1) > 1e-6:
        cmd += ["-af", f"atempo={float(speed):g}"]
    if dur is not None:
        cmd += ["-t", f"{float(dur):.4f}"]
    r = subprocess.run(cmd + ["-f", "f32le", "-"], capture_output=True, stdin=subprocess.DEVNULL)
    if r.returncode:
        raise RuntimeError(f"ffmpeg (звук {Path(path).name}): {r.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(r.stdout, np.float32).copy()


def envelope(x, fps, n=None):
    """Громкость по кадрам (RMS окна кадра, 0..1 от максимума) — для волны клипа."""
    hop = SR // int(fps)
    k = n if n is not None else max(1, len(x) // hop)
    out = np.zeros(k, np.float32)
    for i in range(k):
        seg = x[i * hop:(i + 1) * hop]
        if len(seg):
            out[i] = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))
    m = float(out.max()) if len(out) else 0.0
    return out / m if m > 1e-9 else out

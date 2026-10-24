"""Музыка и ритм (ROADMAP C3): библиотека музыки студии, свой трек на главу с кроссфейдом, доли трека, `sync: beat`.

```yaml
# project.yaml
music:
  file: drive.mp3          # трек: путь от папки проекта, абсолютный или имя в библиотеке студии brand/music/
  by_chapter: {ch02: calm.mp3}   # свой трек на главу (остальные — file), стык — кроссфейд
  crossfade: 2.0           # с, кроссфейд на стыке глав (равная мощность)
  sync: beat               # beat — склейки сцен в долю, bar — в сильную долю (первая доля такта)
  bpm: 120                 # процедурный ритм-трек, если file нет (sync без file)
  meter: 4                 # долей в такте (сильная доля — каждая meter-я)
```
Библиотека — `<студия>/brand/music/` + `music.yaml` (`tracks: [{file, title, source, license, by, bpm}]`); трек проекта —
`assets/` + `assets.yaml` (ROADMAP C2). validate: нет файла — ❌, нет источника или лицензии — ⚠️; qa — ❌.

Доли: онсет-огибающая (спектральный поток, numpy) → темп по автокорреляции → доли динамическим программированием
(Ellis 2007) → уточнение к пику онсета; сильные доли — фаза такта с самым сильным басом (бочкой). Кэш по содержимому
файла — build/mix/beats-<sha1>.json. Трек играет с нуля ролика и зацикливается — сетка долей повторяется с периодом файла.
`sync` двигает склейки сцен к ближайшей доле (timing.layout), речь не режется: сцена не короче своей речи; сценам без
голоса доли трека отдаются как биты (`first_beat`, `at_beat`, `at: 2` — элементы появляются в долю).
QA: доли заново ищутся в звуке готового файла, каждая склейка — не дальше ±1 кадра от доли.
"""
from __future__ import annotations

import json
import math
import subprocess
import wave
from pathlib import Path

import numpy as np
import yaml

from . import assets as AS
from .project import STUDIO_ROOT, stable_hash
from .tts import SR

SYNC = ("beat", "bar")
LIB = Path("brand") / "music"
LIB_FILE = "music.yaml"
HOP, NFFT = 256, 1024  # онсет-огибающая: шаг 5,3 мс при 48 кГц
DETECTOR = 1           # версия детектора — в ключе кэша долей
CROSSFADE = 2.0


def cfg(proj) -> dict:
    return proj.cfg.get("music") or {}


def sync_mode(proj) -> str | None:
    m = cfg(proj)
    return m.get("sync") if m.get("enabled", True) and m.get("sync") in SYNC else None


# ------------------------------------------------------------------ библиотека и файлы
def library_dir(proj) -> Path:
    return proj.ws.root / LIB


def library(proj) -> tuple[dict, list[str]]:
    """brand/music/music.yaml → ({абсолютный путь: запись}, ошибки формата)."""
    d = library_dir(proj)
    f = d / LIB_FILE
    if not f.is_file():
        return {}, []
    try:
        raw = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return {}, [f"{LIB / LIB_FILE}: не читается ({e})"]
    items = raw.get("tracks") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return {}, [f"{LIB / LIB_FILE}: нужен список tracks: [{{file, source, license, by}}]"]
    out, errs = {}, []
    for i, e in enumerate(items):
        if not isinstance(e, dict) or not isinstance(e.get("file"), str):
            errs.append(f"{LIB / LIB_FILE}: запись {i + 1} без file")
            continue
        out[str((d / e["file"]).resolve())] = e
    return out, errs


def resolve(proj, ref) -> Path | None:
    """Файл музыки: абсолютный; от папки проекта (у нарезки — и исходника); имя в библиотеке студии; от корня
    студии (как читал ffmpeg до C3). Нет нигде — None."""
    p = Path(str(ref))
    if p.is_absolute():
        return p if p.is_file() else None
    for c in [r / p for r in AS.roots(proj)] + [library_dir(proj) / p, STUDIO_ROOT / p]:
        if c.is_file():
            return c
    return None


def record(proj, path: Path) -> dict | None:
    """Запись о правах на трек: библиотека студии или assets.yaml проекта."""
    lib, _ = library(proj)
    e = lib.get(str(Path(path).resolve()))
    if e is not None:
        return e
    reg, _ = AS.load(AS.roots(proj))
    for r in AS.roots(proj):
        try:
            k = Path(path).resolve().relative_to(Path(r).resolve()).as_posix()
        except ValueError:
            continue
        if k in reg:
            return reg[k]
    return None


def used(proj) -> list[str]:
    """Ссылки на файлы музыки проекта: file и by_chapter (по порядку, без повторов)."""
    m = cfg(proj)
    refs = [m["file"]] if m.get("file") else []
    bc = m.get("by_chapter")
    refs += [v for v in (bc.values() if isinstance(bc, dict) else []) if isinstance(v, str)]
    return list(dict.fromkeys(refs))


def default_file(proj) -> Path:
    """Основной трек: music.file, иначе процедурный — ритм-трек (при sync) или эмбиент-пэд (как до C3)."""
    m = cfg(proj)
    if m.get("file"):
        p = resolve(proj, m["file"])
        if p is None:
            raise SystemExit(f"music.file: нет файла {m['file']} (путь от папки проекта или имя в {LIB.as_posix()}/)")
        return p
    md = proj.bdir("mix")
    if sync_mode(proj):
        bpm, meter = float(m.get("bpm") or 120), int(m.get("meter") or 4)
        p = md / f"beat_{bpm:g}_{meter}.wav"
        if not p.exists():
            beat_track(p, bpm, meter=meter)
        return p
    p = md / "music_loop.wav"
    if not p.exists():
        music_loop(p)
    return p


def chapter_files(proj, chapters) -> list[Path]:
    """Трек каждой главы по порядку: by_chapter, иначе основной."""
    bc = cfg(proj).get("by_chapter") or {}
    out = []
    for ch in chapters:
        if ch in bc:
            p = resolve(proj, bc[ch])
            if p is None:
                raise SystemExit(f"music.by_chapter.{ch}: нет файла {bc[ch]}")
            out.append(p)
        else:
            out.append(default_file(proj))
    return out


# ------------------------------------------------------------------ процедурный ритм-трек
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
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    return str(path)


def _note(m):
    return 440 * 2 ** ((m - 69) / 12)


def beat_track(path, bpm=120.0, bars=8, meter=4, seed=7):
    """Ритм-трек кодом (CC0): бочка в каждую долю (сильнее — первая доля), малый на 2 и 4, хэт восьмыми, бас и
    аккорд на первую долю (Am – F – C – G). Бесшовная петля: хвосты звуков заворачиваются в начало."""
    spb = 60.0 / bpm
    n = int(round(bars * meter * spb * SR))
    out = np.zeros((n, 2), np.float64)
    rng = np.random.default_rng(seed)
    chords = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]

    def put(a, y, pan=0.5):
        idx = (a + np.arange(len(y))) % n
        np.add.at(out[:, 0], idx, y * (1 - pan) * 2)
        np.add.at(out[:, 1], idx, y * pan * 2)

    def tt(sec):
        return np.arange(int(sec * SR)) / SR

    for k in range(bars * meter):
        a = int(round(k * spb * SR))
        pos = k % meter
        t = tt(0.35)  # бочка: свип 140 → 50 Гц
        f = 50 + 90 * np.exp(-t / 0.035)
        put(a, np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t / 0.11) * (1.0 if pos == 0 else 0.7))
        if meter == 4 and pos in (1, 3):  # малый
            t = tt(0.2)
            put(a, (rng.standard_normal(len(t)) * 0.5 + np.sin(2 * math.pi * 220 * t)) * np.exp(-t / 0.06) * 0.3, 0.45)
        for h in (0, spb / 2):  # хэт восьмыми: короткий шум, верха — разность соседних сэмплов
            t = tt(0.05)
            w = np.diff(rng.standard_normal(len(t) + 1)) * np.exp(-t / 0.012) * 0.07
            put(a + int(round(h * SR)), w, 0.65)
        if pos == 0:
            notes = chords[(k // meter) % len(chords)]
            t = tt(meter * spb * 0.95)
            env = np.minimum(1, t / 0.01) * np.exp(-t / (meter * spb * 0.45))
            put(a, np.sin(2 * math.pi * _note(notes[0] - 24) * t) * env * 0.35)
            for i, m in enumerate(notes):
                put(a, (np.sin(2 * math.pi * _note(m) * t) + 0.3 * np.sin(4 * math.pi * _note(m) * t)) * env * 0.06,
                    0.3 + 0.2 * i)
    out /= np.abs(out).max() + 1e-9
    out *= 10 ** (-3 / 20)
    _write(path, out)
    return str(path)


def _write(path, y):
    pcm = (np.clip(y, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1] if pcm.ndim == 2 else 1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ------------------------------------------------------------------ доли
def decode(path, channels=1) -> np.ndarray:
    """Звук файла (любой формат ffmpeg) → float32 при SR: (n,) или (n, channels)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", str(channels), "-ar", str(SR),
                        "-f", "f32le", "-"], stdin=subprocess.DEVNULL, capture_output=True, check=False)
    if r.returncode:
        raise RuntimeError(f"ffmpeg не прочитал {path}: {r.stderr.decode(errors='replace')[-300:]}")
    x = np.frombuffer(r.stdout, np.float32)
    return x if channels == 1 else x.reshape(-1, channels)


def onset(x) -> tuple[np.ndarray, np.ndarray]:
    """Онсет-огибающие (шаг HOP): спектральный поток всего спектра (лог-амплитуда) и низа (< 150 Гц, линейная
    амплитуда — громкость бочки и баса различает сильную долю)."""
    win = np.hanning(NFFT).astype(np.float32)
    xp = np.concatenate([np.zeros(NFFT // 2, np.float32), np.asarray(x, np.float32), np.zeros(NFFT, np.float32)])
    nf = 1 + len(x) // HOP
    low = int(150 * NFFT / SR) + 1
    full, bass = np.zeros(nf), np.zeros(nf)
    prev = None
    for f0 in range(0, nf, 4096):  # кусками: память не растёт с длиной трека
        f1 = min(nf, f0 + 4096)
        idx = np.arange(f0, f1)[:, None] * HOP + np.arange(NFFT)
        A = np.abs(np.fft.rfft(xp[idx] * win, axis=1))[:, :NFFT // 2]
        S = np.concatenate([np.log1p(100 * A), A[:, :low]], axis=1)
        D = np.maximum(np.diff(S, axis=0, prepend=S[:1] if prev is None else prev[None]), 0)
        full[f0:f1], bass[f0:f1] = D[:, :NFFT // 2].sum(1), D[:, NFFT // 2:].sum(1)
        prev = S[-1]
    return _norm(full), _norm(bass)


def _norm(e):
    w = max(3, int(0.4 * SR / HOP))
    e = np.maximum(e - np.convolve(e, np.ones(w) / w, "same"), 0)
    return e / (e.std() + 1e-9)


def _tempo(env, prior=120.0) -> float:
    """Период доли в кадрах огибающей: автокорреляция × лог-гауссов вес вокруг prior уд/мин."""
    fr = SR / HOP
    n = len(env)
    F = np.fft.rfft(env - env.mean(), 2 * n)
    ac = np.fft.irfft(F * np.conj(F))[:n]
    lags = np.arange(int(fr * 60 / 220), min(n - 1, int(fr * 60 / 50)))
    if len(lags) < 3:
        return fr * 60 / prior
    w = np.exp(-0.5 * (np.log2(fr * 60 / lags / prior) / 0.9) ** 2)
    i = int(np.argmax(ac[lags] * w))
    if 0 < i < len(lags) - 1:  # парабола по соседям — период дробный
        a, b, c = ac[lags[i - 1:i + 2]]
        d = (a - c) / (2 * (a - 2 * b + c)) if a - 2 * b + c else 0.0
        return float(lags[i] + np.clip(d, -0.5, 0.5))
    return float(lags[i])


def _track(env, p, tight=100.0) -> list[int]:
    """Доли динамическим программированием (Ellis 2007): онсеты + штраф за отход от периода p."""
    n = len(env)
    lo, hi = int(round(2 * p)), max(1, int(round(p / 2)))
    off = np.arange(lo, hi - 1, -1)
    pen = -tight * np.log(off / p) ** 2
    score, back = env.astype(np.float64).copy(), np.full(n, -1)
    for t in range(hi, n):
        a = t - lo
        c = score[max(0, a):t - hi + 1] + pen[max(0, -a):]
        j = int(np.argmax(c))
        if c[j] > 0:
            score[t] += c[j]
            back[t] = max(0, a) + j
    end = n - int(p) + int(np.argmax(score[max(0, n - int(p)):]))
    end = max(0, end)
    out = [end]
    while back[out[-1]] >= 0:
        out.append(int(back[out[-1]]))
    out = out[::-1]
    # к началу трека — продолжаем сетку периодом (вступление без онсетов)
    while out[0] - p >= 0:
        out.insert(0, int(round(out[0] - p)))
    return out


def detect(x, meter=4, prior=120.0) -> dict:
    """Доли сигнала: {bpm, beats: [c], down: [c]} — секунды от начала, сильные доли — первые доли тактов."""
    env, bass = onset(x)
    fr = SR / HOP
    if len(env) < fr * 2 or env.max() <= 0:
        return {"bpm": None, "beats": [], "down": []}
    p = _tempo(env, prior)
    frames = _track(env, p)
    beats = []
    for b in frames:  # уточнение к пику онсета ±3 кадра (±16 мс), парабола
        a = max(1, b - 3)
        seg = env[a:min(len(env) - 1, b + 4)]
        if not len(seg) or seg.max() <= 0:
            beats.append(float(b)); continue
        i = a + int(np.argmax(seg))
        y0, y1, y2 = env[i - 1], env[i], env[i + 1]
        d = (y0 - y2) / (2 * (y0 - 2 * y1 + y2)) if y0 - 2 * y1 + y2 else 0.0
        beats.append(i + float(np.clip(d, -0.5, 0.5)))
    beats = [b * HOP / SR for b in beats]
    ib = np.clip(np.round(np.array(beats) * fr).astype(int), 0, len(bass) - 1)
    ph = max(range(min(meter, len(beats))), key=lambda k: float(bass[ib[k::meter]].mean())) if beats else 0
    d = np.diff(beats)
    bpm = 60 / float(np.median(d)) if len(d) else None
    return {"bpm": round(bpm, 2) if bpm else None, "beats": [round(b, 4) for b in beats],
            "down": [round(b, 4) for b in beats[ph::meter]]}


def track_beats(proj, path: Path) -> dict:
    """Доли файла с кэшем по содержимому: build/mix/beats-<sha1>.json (+ length — длина файла, с)."""
    m = cfg(proj)
    meter, prior = int(m.get("meter") or 4), float(m.get("bpm") or 120)
    key = stable_hash([AS.file_hash(path), meter, prior, DETECTOR, HOP, NFFT])
    c = proj.bdir("mix") / f"beats-{key}.json"
    if c.exists():
        return json.loads(c.read_text(encoding="utf-8"))
    x = decode(path)
    d = dict(detect(x, meter, prior), length=round(len(x) / SR, 6), file=Path(path).name)
    c.write_text(json.dumps(d), encoding="utf-8")
    return d


def grid(proj, total: float) -> dict | None:
    """Сетка долей на [0, total] для sync: {mode, bpm, beats, cuts} (cuts — доли или сильные доли по sync).
    Трек зацикливается — доли файла повторяются с периодом его длины. None — sync выключен."""
    mode = sync_mode(proj)
    if not mode:
        return None
    path = default_file(proj)
    d = track_beats(proj, path)
    if not d["beats"]:
        raise SystemExit(f"music.sync: в {path.name} не нашлось долей (тихий или безритмовый трек) — уберите sync "
                         f"или возьмите трек с ритмом")
    L = d["length"]

    def tile(xs):
        out = []
        for k in range(int(total // L) + 2):
            out += [b + k * L for b in xs if b + k * L <= total + 1e-6]
        out = sorted(out)
        return [round(b, 4) for i, b in enumerate(out) if i == 0 or b - out[i - 1] > 0.05]
    beats = tile(d["beats"])
    return {"mode": mode, "bpm": d["bpm"], "file": d["file"], "beats": beats,
            "cuts": beats if mode == "beat" else tile(d["down"])}


def snap(durs, needs, cuts, total=None) -> list[float]:
    """Длительности сцен → склейки в ближайшую долю. total — точная длительность ролика (durs растягиваются до неё
    пропорционально, последняя сцена — до конца) или None (длина по сценам, последняя — своей длины). Склейка — к
    ближайшей доле не раньше start + need (речь сцены не режется) и не позже, чем остаётся место следующим сценам."""
    need = [max(x, 0.25) for x in needs]
    k = total / sum(durs) if total and sum(durs) else 1.0
    cuts = np.asarray(cuts, float)
    out, start, E = [], 0.0, 0.0
    for i, d in enumerate(durs[:-1]):
        E += d * k
        hi = total - sum(need[i + 1:]) if total else math.inf
        c = cuts[(cuts >= start + need[i] - 1e-9) & (cuts <= hi + 1e-9)]
        if not len(c):
            raise SystemExit(f"music.sync: сцене {i + 1} нет доли между концом её речи и местом под следующие сцены "
                             f"— сократите сцены или увеличьте target_duration")
        b = float(c[np.argmin(np.abs(c - E))])
        out.append(b - start)
        start = b
    out.append(total - start if total else max(durs[-1], need[-1]))
    return out


def scene_beats(g: dict, start: float, dur: float, eps: float = 0.02) -> list[dict]:
    """Доли трека внутри сцены как биты (сцены без голоса): время от начала сцены. Склейка стоит в кадре, ближайшем
    к доле, — доля на ±eps от края сцены принадлежит той сцене, что с неё начинается."""
    bs = [b - start for b in g["beats"] if start - eps <= b < start + dur - eps]
    return [{"text": "", "line": None, "music": True, "t0": round(max(0.0, a), 4),
             "t1": round(bs[i + 1] if i + 1 < len(bs) else dur, 4)} for i, a in enumerate(bs)]


def source_key(proj):
    """Что из музыки влияет на тайминг (timing.source_hash) — только при sync: старые проекты хэш не меняют."""
    if not sync_mode(proj):
        return None
    m = cfg(proj)
    f = resolve(proj, m["file"]) if m.get("file") else None
    return [sync_mode(proj), m.get("meter"), m.get("bpm"), AS.file_hash(f) if f else m.get("file")]


# ------------------------------------------------------------------ подложка по главам
def chapter_starts(tl) -> list[tuple[str, float]]:
    out = []
    for s in tl["scenes"]:
        if not out or out[-1][0] != s["chapter"]:
            out.append((s["chapter"], s["start_frame"] / tl["fps"]))
    return out


def bed(proj, tl, out: Path) -> Path | None:
    """Свой трек на главу (music.by_chapter) → out/music_bed.wav (стерео, кусками): каждый трек с начала главы
    (минус полкроссфейда), зациклен; стык — кроссфейд равной мощности music.crossfade с. Соседние главы с одним
    треком — без стыка. Без by_chapter — None (одна петля, как до C3)."""
    if not cfg(proj).get("by_chapter"):
        return None
    starts = chapter_starts(tl)
    files = chapter_files(proj, [c for c, _ in starts])
    n = int(round(tl["total_frames"] * SR / tl["fps"]))
    segs = []  # [(файл, начало, конец)] в сэмплах, одинаковые соседние склеены
    for (ch, t), f in zip(starts, files):
        a = 0 if not segs else int(round(t * SR))
        if segs and segs[-1][0] == f:
            continue
        if segs:
            segs[-1][2] = a
        segs.append([f, a, n])
    xf = int(round(float(cfg(proj).get("crossfade", CROSSFADE)) * SR))
    data = {f: decode(f, 2) for f, _, _ in segs}
    win = []  # окно звучания сегмента [S, E) и фейды
    for i, (f, a, b) in enumerate(segs):
        S = 0 if i == 0 else max(0, a - xf // 2)
        E = n if i == len(segs) - 1 else min(n, b + xf - xf // 2)
        win.append((data[f], S, E, i > 0, i < len(segs) - 1))
    path = out / "music_bed.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        for a0 in range(0, n, SR * 30):
            a1 = min(n, a0 + SR * 30)
            y = np.zeros((a1 - a0, 2), np.float32)
            for x, S, E, fin, fout in win:
                lo, hi = max(S, a0), min(E, a1)
                if lo >= hi or not len(x):
                    continue
                s = np.arange(lo, hi)
                g = np.ones(len(s), np.float32)
                if fin and xf:
                    g *= np.sin(np.pi / 2 * np.clip((s - S) / xf, 0, 1))
                if fout and xf:
                    g *= np.cos(np.pi / 2 * np.clip((s - (E - xf)) / xf, 0, 1))
                y[lo - a0:hi - a0] += x[(s - S) % len(x)] * g[:, None]
            w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


# ------------------------------------------------------------------ validate и qa
def issues(proj) -> tuple[list[str], list[str]]:
    """validate: (ошибки, предупреждения) по музыке проекта."""
    errs, warns = [], []
    m = cfg(proj)
    _, le = library(proj)
    errs += le
    if m.get("sync") is not None and m.get("sync") not in SYNC:
        errs.append(f"music.sync: '{m.get('sync')}' — нет такого режима (есть: {', '.join(SYNC)})")
    if m.get("sync") and not m.get("enabled", True):
        errs.append("music.sync при music.enabled: false — нет трека, не к чему привязывать сцены")
    bc = m.get("by_chapter")
    if bc is not None:
        if not isinstance(bc, dict):
            errs.append("music.by_chapter: нужен словарь {chNN: файл}")
        else:
            chs = [c for c, _ in proj.chapters]
            errs += [f"music.by_chapter.{c}: нет такой главы (есть: {', '.join(chs)})" for c in bc if c not in chs]
            if m.get("sync"):
                errs.append("music.sync с by_chapter: доли ищутся в одном треке — уберите by_chapter или sync")
    xf = m.get("crossfade")
    if xf is not None and (isinstance(xf, bool) or not isinstance(xf, (int, float)) or xf < 0):
        errs.append(f"music.crossfade: секунды ≥ 0, а не {xf!r}")
    for r in used(proj):
        p = resolve(proj, r)
        if p is None:
            errs.append(f"music: нет файла {r} (путь от папки проекта или имя в {LIB.as_posix()}/ студии)")
            continue
        e = record(proj, p)
        if e is None:
            warns.append(f"music: {r} нет ни в {LIB.as_posix()}/{LIB_FILE}, ни в assets.yaml — запишите источник и "
                         f"лицензию (qa без них не пройдёт)")
        elif not all(e.get(x) for x in AS.FIELDS):
            warns.append(f"music: {r} — не заполнено {', '.join(x for x in AS.FIELDS if not e.get(x))}")
    return errs, warns


def qa_license(proj) -> tuple[bool, str] | None:
    """QA «Музыка: источник и лицензия»; None — музыки нет."""
    m = cfg(proj)
    if not m.get("enabled", True):
        return None
    refs = used(proj)
    if not refs:
        return True, "процедурная музыка студии (код, CC0)"
    bad, lic = [], []
    for r in refs:
        p = resolve(proj, r)
        e = record(proj, p) if p else None
        if not e or not all(e.get(x) for x in AS.FIELDS):
            bad.append(r)
        else:
            lic.append(str(e["license"]))
    if bad:
        return False, f"без файла, источника или лицензии: {', '.join(bad)}"
    return True, f"{len(refs)} трек(а); лицензии: {'; '.join(dict.fromkeys(lic))}"


def qa_sync(proj, tl, audio) -> tuple[bool, str] | None:
    """QA «Склейки в долю»: доли ищутся в звуке готового файла (audio), каждая склейка сцен — ±1 кадр от доли.
    None — склеек нет."""
    fps = tl["fps"]
    cuts = [s["start_frame"] / fps for s in tl["scenes"][1:]]
    if not cuts:
        return None
    m = cfg(proj)
    d = detect(decode(audio), int(m.get("meter") or 4), float(m.get("bpm") or 120))
    if not d["beats"]:
        return False, "в звуке итога не нашлось долей"
    B = np.asarray(d["beats"])
    err = [float(np.min(np.abs(B - c))) for c in cuts]
    worst = max(err)
    ok = worst <= 1 / fps + 1e-6
    hint = "" if ok or sync_mode(proj) else "; music.sync: beat — склейки в долю"
    return ok, (f"{len(cuts)} склеек, темп {d['bpm']} уд/мин, макс. отход {worst * 1000:.0f} мс "
                f"(допуск ±1 кадр = {1000 / fps:.0f} мс){hint}")

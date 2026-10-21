"""Синтез речи с кэшем. Бэкенды: rhvoice (офлайн, проверен), edge (онлайн, лучшее качество),
piper (офлайн нейросетевой), elevenlabs (онлайн, платный, таймкоды символов).
Результат всегда: WAV 48 кГц моно 16 бит, тишина по краям срезана.

Кэш: build/tts/<hash>.wav, ключ = бэкенд+голос+темп+текст (+модель, настройки голоса, voice-override
и тексты соседних строк previous_text/next_text для elevenlabs).
Повторный запуск не синтезирует заново. Таймкоды слов (если бэкенд их даёт) — build/tts/<hash>.words.json,
времена уже относительно срезанного WAV.

Ключи — только из окружения или .env в корне студии (он в .gitignore). В лог и в чат ключ не выводится.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import threading
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


def load_env():
    """KEY=VALUE из <студия>/.env -> os.environ (не перетирая уже заданные). Пустые значения пропускаются."""
    f = STUDIO_ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v and k not in os.environ:
            os.environ[k] = v


load_env()


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


EDGE_TIMEOUT = 90  # с на одну строку: обычно 1–3 с


def _try(fn):
    try:
        return True, fn()
    except Exception as e:  # noqa: BLE001
        return False, e


def _edge(text, voice, rate, out_raw):
    pct = int(round(rate - 100))
    try:  # Python API: те же байты звука, плюс таймкоды слов (WordBoundary)
        import edge_tts
    except ImportError:
        edge_tts = None
    if edge_tts is not None:
        def once():
            com = edge_tts.Communicate(text, voice, rate=f"{pct:+d}%", boundary="WordBoundary")
            audio, words = bytearray(), []
            for ch in com.stream_sync():
                if ch["type"] == "audio":
                    audio += ch["data"]
                elif ch["type"] == "WordBoundary":
                    words.append([ch["text"], ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7])
            return bytes(audio), words

        # stream_sync бывает виснет навсегда (сеть оборвалась без ошибки) — общий лимит, поток-демон, 1 повтор
        for attempt in (1, 2):
            box = {}
            th = threading.Thread(target=lambda: box.update(r=_try(once)), daemon=True)
            th.start()
            th.join(EDGE_TIMEOUT)
            if "r" not in box:
                if attempt == 1:
                    continue
                raise TTSUnavailable(f"edge-tts: нет ответа за {EDGE_TIMEOUT} c (дважды) — сеть/сервис")
            ok, val = box["r"]
            if not ok:  # noqa — сеть/сервис: честная ошибка, без молчаливой подмены
                raise TTSUnavailable("edge-tts: " + str(val)[-300:])
            Path(out_raw).write_bytes(val[0])
            _RAW_WORDS[str(out_raw)] = val[1]
            return
    exe = shutil.which("edge-tts")
    if not exe:
        raise TTSUnavailable("edge-tts не найден: pip install edge-tts (нужен интернет)")
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


EL_API = "https://api.elevenlabs.io/v1"
EL_DEFAULTS = {"model": "eleven_multilingual_v2", "stability": 0.5, "similarity_boost": 0.75, "style": 0.0,
               "use_speaker_boost": True}
EL_VOICE_KEYS = ("stability", "similarity_boost", "style", "use_speaker_boost", "speed", "model")  # voice: сцены/строки
EL_SPEED = (0.7, 1.2)  # диапазон speed, который принимает API
_RAW_WORDS = {}  # out_raw -> [[слово, t0, t1]] относительно сырого звука (до срезки тишины)
_EL_CFG = {}  # настройки текущего вызова: проектные + voice-override + previous_text/next_text


def _el_key():
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not k:
        raise TTSUnavailable("нет ключа ElevenLabs: впишите ELEVENLABS_API_KEY в .env (корень студии)")
    return k


def _el_request(path, body=None, method="GET"):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(EL_API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"xi-api-key": _el_key(), "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:  # 401/403/429 — без ретраев, понятная ошибка
        msg = e.read().decode(errors="replace")[:300]
        hint = {400: "неверный запрос (если ругается на previous_text/next_text — tts.context: false)",
                401: "ключ неверный", 403: "доступ запрещён (тариф/прокси) — не ретраим",
                429: "лимит запросов или символов"}.get(e.code, "")
        raise TTSUnavailable(f"ElevenLabs HTTP {e.code} {hint}: {msg}")
    except urllib.error.URLError as e:
        raise TTSUnavailable(f"ElevenLabs недоступен: {e.reason}")


def _elevenlabs(text, voice, rate, out_raw):
    """POST /v1/text-to-speech/{voice_id}/with-timestamps: mp3 + посимвольные времена -> слова."""
    c = dict(EL_DEFAULTS, **_EL_CFG)
    speed = max(EL_SPEED[0], min(EL_SPEED[1], float(c.get("speed") or rate / 100.0)))
    body = {"text": text, "model_id": c["model"],
            "voice_settings": {"stability": c["stability"], "similarity_boost": c["similarity_boost"],
                               "style": c["style"], "use_speaker_boost": c["use_speaker_boost"], "speed": speed}}
    for k in ("previous_text", "next_text"):  # соседние строки: модель держит общую интонацию (платим только за text)
        if c.get(k):
            body[k] = c[k]
    r = _el_request(f"/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128", body, "POST")
    Path(out_raw).write_bytes(base64.b64decode(r["audio_base64"]))
    al = r.get("alignment") or {}
    words, cur = [], None
    for ch, a, b in zip(al.get("characters", []), al.get("character_start_times_seconds", []),
                        al.get("character_end_times_seconds", [])):
        if ch.isspace():
            if cur:
                words.append(cur)
                cur = None
            continue
        if cur is None:
            cur = [ch, a, b]
        else:
            cur[0] += ch
            cur[2] = b
    if cur:
        words.append(cur)
    _RAW_WORDS[str(out_raw)] = words


BACKENDS = {"rhvoice": _rhvoice, "edge": _edge, "piper": _piper, "elevenlabs": _elevenlabs}


def probe(tts_cfg, language="ru") -> str:
    """Проверяет, что синтез реально работает (а не просто «бинарник есть»)."""
    from .lang import profile
    if tts_cfg["backend"] == "elevenlabs":  # бесплатная проверка: ключ и голос, без синтеза (символы платные)
        _el_request("/user")
        if not tts_cfg.get("voice") or tts_cfg["voice"] in ("auto", "env"):
            raise TTSUnavailable("не задан голос ElevenLabs: ELEVENLABS_VOICE_ID в .env или tts.voice")
        _el_request(f"/voices/{tts_cfg['voice']}")
        return "ok"
    tmp = Path(tempfile.mkdtemp())
    try:
        BACKENDS[tts_cfg["backend"]](profile(language)["probe"], tts_cfg["voice"], 100, tmp / "p.wav")
        if not (tmp / "p.wav").exists() or (tmp / "p.wav").stat().st_size < 2000:
            raise TTSUnavailable(f"{tts_cfg['backend']}: синтез вернул пустой файл")
        return "ok"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- synth + cache
def el_call_cfg(tts_cfg: dict, prev=None, nxt=None, voice=None) -> dict:
    """Всё, что уходит в запрос ElevenLabs сверх текста: модель, настройки, override голоса, соседние строки.
    Контекст выключается tts.context: false (например, если модель его не принимает)."""
    c = {k: tts_cfg.get(k, v) for k, v in EL_DEFAULTS.items()}
    c.update({k: v for k, v in (voice or {}).items() if k in EL_VOICE_KEYS})
    if tts_cfg.get("context", True):
        c.update({k: v for k, v in (("previous_text", prev), ("next_text", nxt)) if v})
    return c


def cache_key(text: str, tts_cfg: dict, rate: float, prev=None, nxt=None, voice=None) -> str:
    parts = [tts_cfg["backend"], tts_cfg["voice"], round(float(rate), 1), text]
    if tts_cfg["backend"] == "elevenlabs":  # у офлайн-бэкендов контекста нет — их кэш не трогаем
        parts.append(el_call_cfg(tts_cfg, prev, nxt, voice))
    return stable_hash(parts, 16)


def _lead_silence(raw) -> float:
    """Сколько тишины срежет TRIM в начале (порог −45 dB) — чтобы сдвинуть таймкоды слов."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(raw), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                       stdin=subprocess.DEVNULL, capture_output=True)
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    idx = np.nonzero(np.abs(x) > 10 ** (-45 / 20))[0]
    return float(idx[0]) / SR if len(idx) else 0.0


def synth(text: str, tts_cfg: dict, rate: float, cache_dir: Path, prev=None, nxt=None, voice=None) -> Path:
    """prev/nxt — тексты соседних строк, voice — override настроек голоса (оба только для elevenlabs)."""
    key = cache_key(text, tts_cfg, rate, prev, nxt, voice)
    out = cache_dir / f"{key}.wav"
    if out.exists() and out.stat().st_size > 1000:
        return out
    cache_dir.mkdir(parents=True, exist_ok=True)
    if tts_cfg["backend"] == "elevenlabs":
        _EL_CFG.clear()
        _EL_CFG.update(el_call_cfg(tts_cfg, prev, nxt, voice))
    raw = cache_dir / f"{key}.raw{'.mp3' if tts_cfg['backend'] in ('edge', 'elevenlabs') else '.wav'}"
    BACKENDS[tts_cfg["backend"]](text, tts_cfg["voice"], rate, raw)
    if not raw.exists() or raw.stat().st_size < 1000:
        raise TTSUnavailable(f"Синтез не дал звука для: {text[:60]!r}")
    words = _RAW_WORDS.pop(str(raw), None)
    lead = _lead_silence(raw) if words else 0.0
    r = run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", TRIM,
             "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", str(out)])
    raw.unlink(missing_ok=True)
    if r.returncode or not out.exists():
        raise RuntimeError("ffmpeg trim: " + r.stderr[-300:])
    if words:
        d = duration(out)
        words = [[w, round(max(0.0, a - lead), 3), round(min(d, max(0.0, b - lead)), 3)] for w, a, b in words]
        out.with_suffix(".words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    return out


def load_words(wav):
    """Таймкоды слов от бэкенда для WAV из кэша или None (тогда timing оценивает сам)."""
    p = Path(wav).with_suffix(".words.json")
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


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

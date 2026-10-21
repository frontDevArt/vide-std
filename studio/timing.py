"""Озвучка + раскладка по времени.

Модель: сцена = набор строк (lines). Строка синтезируется целиком (естественная интонация).
'|' внутри строки делит её на «биты» — точки синхронизации анимации и субтитров.
Границы битов: оценка по слогам -> притягивание к ближайшей реальной паузе в аудио.

Длительность сцены = пауза_до + речь + паузы + пауза_после (или min_duration).
Если задан target_duration: подбираем темп в естественном диапазоне, остаток раскладываем
в паузы между сценами и в хвост последней сцены (hold). Речь НИКОГДА не обрезаем.
Всё квантуется в кадры; позиция звука = кадр начала сцены -> рассинхрона нет.
"""
from __future__ import annotations

import difflib
import json
import math
import re

from . import tts as T
from .project import Project, stable_hash
from .textutil import segments, tts_text, display_text, weight, ends_with_comma, word_count
from . import subs as S


def _line_pause(text, pauses):
    return pauses["comma"] if ends_with_comma(text) else pauses["sentence"]


def _split_bounds(seg_texts, dur, sil):
    """Возвращает [(t0, t1)] для каждого сегмента внутри фразы длительностью dur."""
    k = len(seg_texts)
    if k == 1:
        return [(0.0, dur)]
    w = [weight(s) for s in seg_texts]
    tot = sum(w)
    bounds = [(0.0, None)]
    acc = 0.0
    used = set()
    for i in range(k - 1):
        acc += w[i]
        est = dur * acc / tot
        win = max(0.18, min(0.45, dur * 0.12))
        cand = [(j, s) for j, s in enumerate(sil)
                if j not in used and abs((s[0] + s[1]) / 2 - est) <= win]
        if cand:
            # предпочитаем длинную паузу, при равенстве — ближайшую
            j, s = max(cand, key=lambda c: (c[1][1] - c[1][0]) - 0.25 * abs((c[1][0] + c[1][1]) / 2 - est))
            used.add(j)
            a, b = s
        else:
            a = b = est
        bounds[-1] = (bounds[-1][0], a)
        bounds.append((b, None))
    bounds[-1] = (bounds[-1][0], dur)
    return [(round(a, 3), round(b, 3)) for a, b in bounds]


def _norm(w):
    return re.sub(r"[^\w]+", "", w.lower())


def _line_words(segs, bounds, dur, wav):
    """Слова строки с временами [(слово, t0, t1)] относительно начала строки.
    Есть таймкоды бэкенда (ElevenLabs, edge) -> берём их; нет -> оценка по слогам внутри битов."""
    est = []
    for si, (a, b) in enumerate(bounds):
        ws = display_text(segs[si]).split()
        tot = sum(weight(w) for w in ws) or 1.0
        acc = a
        for w in ws:
            d = (b - a) * weight(w) / tot
            est.append([w, round(acc, 3), round(acc + d, 3)])
            acc += d
    real = T.load_words(wav)
    if real:
        A, B = [_norm(w[0]) for w in est], [_norm(w[0]) for w in real]
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, A, B, autojunk=False).get_opcodes():
            if op == "equal":
                for k in range(i2 - i1):
                    est[i1 + k][1:] = [round(max(0.0, real[j1 + k][1]), 3), round(min(dur, real[j1 + k][2]), 3)]
            elif op == "replace" and j2 > j1:  # «66» ↔ «sixty six»: делим отрезок бэкенда поровну
                t0, t1 = real[j1][1], real[j2 - 1][2]
                n = i2 - i1
                for k in range(n):
                    est[i1 + k][1:] = [round(t0 + (t1 - t0) * k / n, 3), round(t0 + (t1 - t0) * (k + 1) / n, 3)]
    return est


def voice_scene(proj: Project, scene: dict, rate: float, cache):
    """Синтез строк сцены. Возвращает «сырую» раскладку без пауз между сценами."""
    lines_out = []
    for raw in scene.get("lines") or []:
        segs = segments(raw)
        wav = T.synth(tts_text(raw), proj.cfg["tts"], rate, cache)
        x = T.read_wav(wav)
        dur = len(x) / T.SR
        sil = T.silences(x)
        bounds = _split_bounds(segs, dur, sil)
        lines_out.append({"text": display_text(raw), "segs": segs, "wav": wav.name,
                          "dur": round(dur, 3), "bounds": bounds,
                          "words": _line_words(segs, bounds, dur, wav),
                          "pause_after": _line_pause(raw, proj.cfg["pauses"])})
    return lines_out


def _all_scenes(proj):
    for ch, data in proj.chapters:
        for sc in data.get("scenes") or []:
            yield ch, sc


def measure(proj: Project, rate: float):
    cache = proj.bdir("tts")
    voiced = []
    for ch, sc in _all_scenes(proj):
        voiced.append((ch, sc, voice_scene(proj, sc, rate, cache)))
    return voiced


def _speech_len(lines):
    if not lines:
        return 0.0
    return sum(l["dur"] for l in lines) + sum(l["pause_after"] for l in lines[:-1])


def base_total(proj, voiced):
    P = proj.cfg["pauses"]
    tot = 0.0
    n = len(voiced)
    for i, (_, sc, lines) in enumerate(voiced):
        head = P["start"] if i == 0 else P["scene"] / 2
        tail = P["end"] if i == n - 1 else P["scene"] / 2
        body = head + _speech_len(lines) + tail + float(sc.get("hold", 0))
        tot += max(body, float(sc.get("min_duration", 0)))
    return tot


def choose_rate(proj: Project, log=print):
    """Темп: число из конфига, либо подбор под target_duration в естественном диапазоне."""
    tcfg = proj.cfg["tts"]
    target = proj.cfg.get("target_duration")
    lo, hi = tcfg.get("rate_range", [98, 125])
    if tcfg.get("rate", "auto") != "auto" or not target:
        r = tcfg["rate"] if tcfg.get("rate") != "auto" else 105
        return float(r), measure(proj, float(r))
    r = float(lo)
    for _ in range(6):
        voiced = measure(proj, r)
        tot = base_total(proj, voiced)
        log(f"  темп {r:.0f}: базовая длительность {tot:.2f} c (цель {target})")
        if tot <= target - 0.15:
            return r, voiced
        if r >= hi:
            break
        speech = sum(_speech_len(v[2]) for v in voiced)
        need = speech - (tot - (target - 0.3))
        r = min(hi, max(r + 1, math.ceil(r * speech / max(need, 0.1))))
    raise SystemExit(f"Текст не помещается в {target} c даже при темпе {hi}. "
                     f"Сократите текст (оценка: {tot:.1f} c) — ускорять дальше неестественно.")


def layout(proj: Project, log=print) -> dict:
    """Полная раскладка проекта -> build/timeline.json (+ субтитры). Идемпотентно, с кэшем TTS."""
    T.probe(proj.cfg["tts"], proj.cfg["language"])
    from . import gfx
    gfx.set_palette(proj.cfg["style"].get("palette", "neon"))  # ширина субтитров — шрифтом стиля
    rate, voiced = choose_rate(proj, log)
    P = proj.cfg["pauses"]
    fps = proj.fps
    n = len(voiced)
    target = proj.cfg.get("target_duration")
    base = base_total(proj, voiced)
    slack = max(0.0, (target - base)) if target else 0.0

    # раскладываем запас: 1) сценам с want_duration (мягкое желание), 2) паузам между сценами
    # (не больше max_extra_gap), 3) остаток — в хвост последней сцены
    want_extra = {}
    if slack:
        for i, (ch, sc, lines) in enumerate(voiced):
            w = float(sc.get("want_duration", 0))
            if w:
                head = P["start"] if i == 0 else P["scene"] / 2
                tail = P["end"] if i == n - 1 else P["scene"] / 2
                body = max(head + _speech_len(lines) + tail + float(sc.get("hold", 0)), float(sc.get("min_duration", 0)))
                if w > body:
                    want_extra[i] = w - body
        tot_w = sum(want_extra.values())
        if tot_w > slack:
            want_extra = {k: v * slack / tot_w for k, v in want_extra.items()}
        slack -= sum(want_extra.values())
    extra_gap = 0.0
    if slack and n > 1:
        extra_gap = min(P["max_extra_gap"], slack * 0.5 / (n - 1))
    tail_extra = slack - extra_gap * (n - 1) if slack else 0.0

    scenes, t = [], 0.0
    for i, (ch, sc, lines) in enumerate(voiced):
        head = P["start"] if i == 0 else P["scene"] / 2 + extra_gap / 2
        tail = P["end"] if i == n - 1 else P["scene"] / 2 + extra_gap / 2
        if i == n - 1:
            tail += tail_extra
        body = head + _speech_len(lines) + tail + float(sc.get("hold", 0))
        d = max(body, float(sc.get("min_duration", 0))) + want_extra.get(i, 0.0)
        head += (d - body) * 0.35 if d > body else 0  # растянутую сцену начинаем чуть позже
        cur = head
        beats, placed, words = [], [], []
        for li, L in enumerate(lines):
            placed.append({"text": L["text"], "wav": L["wav"], "t0": round(cur, 3),
                           "t1": round(cur + L["dur"], 3)})
            for w, a, b in L.get("words") or []:
                words.append({"w": w, "line": li, "t0": round(cur + a, 3), "t1": round(cur + b, 3)})
            for si, (a, b) in enumerate(L["bounds"]):
                beats.append({"text": display_text(L["segs"][si]), "line": li,
                              "t0": round(cur + a, 3), "t1": round(cur + b, 3)})
            cur += L["dur"] + L["pause_after"]
        scenes.append({"chapter": ch, "id": sc["id"], "template": sc.get("template", "statement"),
                       "params": sc.get("params") or {}, "lines": placed, "beats": beats, "words": words,
                       "start": t, "dur": d})
        t += d

    total_frames = int(round(target * fps)) if target else int(round(t * fps))
    # квантуем в кадры
    acc = 0.0
    for i, s in enumerate(scenes):
        f0 = int(round(acc * fps))
        acc += s["dur"]
        f1 = total_frames if i == n - 1 else int(round(acc * fps))
        s["start_frame"], s["n_frames"] = f0, f1 - f0
        shift = s["start"] - f0 / fps  # локальные времена относительно кадра начала
        for L in s["lines"] + s["beats"] + s["words"]:
            L["t0"] = round(L["t0"] + shift, 4); L["t1"] = round(L["t1"] + shift, 4)
        s["start"] = f0 / fps
        s["dur"] = s["n_frames"] / fps
        s["subs"] = S.chunks_for_scene(proj, s)
        s["hash"] = stable_hash([s["template"], s["params"], s["lines"], s["beats"], s["subs"],
                                 s["start_frame"], s["n_frames"]] + ([s["words"]] if s["template"].startswith("lab_") else []))

    words = sum(word_count(l["text"]) for s in scenes for l in s["lines"])
    speech = sum(l["t1"] - l["t0"] for s in scenes for l in s["lines"])
    tl = {"src": source_hash(proj), "fps": fps, "size": proj.size, "rate": rate, "voice": proj.cfg["tts"]["voice"],
          "backend": proj.cfg["tts"]["backend"], "total_frames": total_frames,
          "duration": total_frames / fps, "words": words,
          "wpm_speech": round(words / max(speech, 1e-6) * 60, 1),
          "wpm_overall": round(words / (total_frames / fps) * 60, 1), "scenes": scenes}
    out = proj.build / "timeline.json"
    txt = json.dumps(tl, ensure_ascii=False, indent=1)
    if not out.exists() or out.read_text(encoding="utf-8") != txt:  # не трогаем файл без изменений
        out.write_text(txt, encoding="utf-8")
    S.write_srt(proj, tl)
    return tl


def source_hash(proj: Project) -> str:
    """Хэш всего, что влияет на озвучку и тайминг (а не дата файлов): status сравнивает его."""
    c = proj.cfg
    return stable_hash([c["tts"], c["pauses"], c.get("target_duration"), c["fps"], c["format"], c["subtitles"],
                        [(ch, d) for ch, d in proj.chapters]])


def load_timeline(proj: Project) -> dict:
    p = proj.build / "timeline.json"
    if not p.exists():
        raise SystemExit("Нет build/timeline.json — сначала: python -m studio voice <проект>")
    with open(p, encoding="utf-8") as f:
        return json.load(f)

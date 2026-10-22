"""Субтитры: нарезка по битам речи, перенос максимум в N строк (по реальной ширине шрифта), SRT/VTT."""
from __future__ import annotations

from . import gfx


def font_size(proj):
    W, H = proj.size
    s = proj.cfg["subtitles"].get("size")
    return int(s) if s else int(round(min(W, H) * 0.052))


def max_width(proj):
    W, H = proj.size
    return int(W * (0.86 if W < H else 0.70))


def wrap(text, font, maxw, max_lines=2):
    """Сбалансированный перенос. None — если не помещается в max_lines."""
    words = text.split()
    if not words:
        return []
    if font.getlength(text) <= maxw:
        return [text]
    if max_lines < 2:
        return None
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        wa, wb = font.getlength(a), font.getlength(b)
        if wa <= maxw and wb <= maxw:
            score = max(wa, wb)
            if best is None or score < best[0]:
                best = (score, [a, b])
    if best:
        return best[1]
    if max_lines >= 3:
        for i in range(1, len(words)):
            a = " ".join(words[:i])
            if font.getlength(a) <= maxw:
                rest = wrap(" ".join(words[i:]), font, maxw, max_lines - 1)
                if rest:
                    return [a] + rest
    return None


def _split_long(text, t0, t1, font, maxw, max_lines):
    """Слишком длинный бит делим по словам на части, время — пропорционально длине."""
    words = text.split()
    parts, cur = [], []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and wrap(trial, font, maxw, max_lines) is None:
            parts.append(" ".join(cur)); cur = [w]
        else:
            cur.append(w)
    if cur:
        parts.append(" ".join(cur))
    tot = sum(len(p) for p in parts)
    out, t = [], t0
    for p in parts:
        d = (t1 - t0) * len(p) / tot
        out.append((p, t, t + d)); t += d
    return out


def chunks_for_scene(proj, scene):
    if not proj.cfg["subtitles"].get("enabled", True):
        return []
    f = gfx.font(font_size(proj), "bold")
    maxw = max_width(proj) - int(font_size(proj) * 1.2)
    ml = int(proj.cfg["subtitles"].get("max_lines", 2))
    raw = []
    beats = scene["beats"]
    i = 0
    while i < len(beats):
        b = dict(beats[i])
        # очень короткие биты одной фразы склеиваем, если влезают
        while (i + 1 < len(beats) and beats[i + 1]["line"] == b["line"]
               and (b["t1"] - b["t0"] < 0.45 or beats[i + 1]["t1"] - beats[i + 1]["t0"] < 0.45)
               and wrap(b["text"] + " " + beats[i + 1]["text"], f, maxw, ml)):
            i += 1
            b["text"] += " " + beats[i]["text"]; b["t1"] = beats[i]["t1"]
        if wrap(b["text"], f, maxw, ml) is None:
            raw.extend(_split_long(b["text"], b["t0"], b["t1"], f, maxw, ml))
        else:
            raw.append((b["text"], b["t0"], b["t1"]))
        i += 1
    out = []
    lead = 0.05  # субтитр появляется чуть раньше звука — так воспринимается синхроннее
    for k, (txt, a, b) in enumerate(raw):
        nxt = raw[k + 1][1] - lead - 0.02 if k + 1 < len(raw) else scene["dur"] - 0.05
        end = min(nxt, b + 0.35)
        if nxt - b < 0.3:
            end = nxt  # короткий зазор — держим до следующего, чтобы не мигало
        out.append({"lines": wrap(txt, f, maxw, ml), "t0": round(max(0.0, a - lead), 3),
                    "t1": round(max(end, a + 0.3), 3)})
    return out


def _ts(t, sep=","):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_srt(proj, tl):
    items = []
    for s in tl["scenes"]:
        for c in s["subs"]:
            items.append((s["start"] + c["t0"], s["start"] + c["t1"], "\n".join(c["lines"])))
    d = proj.bdir("final")
    with open(d / f"{proj.slug}.srt", "w", encoding="utf-8", newline="\n") as f:  # LF на любой ОС (golden)
        for i, (a, b, t) in enumerate(items, 1):
            f.write(f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n")
    with open(d / f"{proj.slug}.vtt", "w", encoding="utf-8", newline="\n") as f:
        f.write("WEBVTT\n\n")
        for a, b, t in items:
            f.write(f"{_ts(a, '.')} --> {_ts(b, '.')}\n{t}\n\n")

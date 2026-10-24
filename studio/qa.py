"""Автопроверка финального ролика. Пишет qa/report.md и листы кадров, которые Claude ОБЯЗАН открыть."""
from __future__ import annotations

import json
import subprocess

from PIL import Image, ImageDraw

from . import gfx as G
from . import subs as S
from .audio import loudness, mean_db, ff
from .project import Project
from .timing import load_timeline


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                        "stream=codec_type,codec_name,width,height,r_frame_rate,nb_read_frames,sample_rate,channels,duration"
                        ":format=duration,size", "-of", "json", str(path)], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    return json.loads(r.stdout)


def grab(path, t, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", str(out)],
                   stdin=subprocess.DEVNULL, check=True)
    return Image.open(out).convert("RGB")


def sheet(imgs, labels, cols, out):
    w, h = imgs[0].size
    rows = (len(imgs) + cols - 1) // cols
    sh = Image.new("RGB", (cols * (w + 4), rows * (h + 4)), (50, 50, 50))
    f = G.font(16, "semibold")
    for i, (im, lb) in enumerate(zip(imgs, labels)):
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, w, 24), fill=(0, 0, 0)); d.text((5, 3), lb, font=f, fill=(255, 255, 0))
        sh.paste(im, ((i % cols) * (w + 4), (i // cols) * (h + 4)))
    sh.save(out)
    return out


def subs_top(proj, W, H):
    """Верх полосы субтитров для листа subs_check — доля высоты (render.draw_subs: TikTok-субтитры стоят выше)."""
    if G.SM.active().subs == "tiktok":
        y = 0.52 if H >= W else 0.66
    else:
        y = 0.70 if H >= W else 0.76
    if proj is None or S.bottom_limit(proj) is None:
        return y
    bt = S.band_top(proj)  # у площадки субтитры поднимаются над нижним полем её зоны (ROADMAP B3) — лист за ними
    return min(y, bt - 0.08) if bt is not None else y


def run(proj: Project, log=print, fast=False):
    tl = load_timeline(proj)
    G.apply_style(proj.cfg["style"])  # ширина субтитров — тем шрифтом, что рисуется (B4)
    final = proj.final_path()
    res = []

    def chk(ok, name, detail=""):
        res.append(("PASS" if ok else "FAIL", name, detail))
        log(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")

    def warn(status, name, detail=""):  # WARN — ⚠️ в отчёте, на итог не влияет
        res.append((status, name, detail))
        log(f"[{status}] {name} {detail}")

    def skip(name, why):  # проверка неприменима к ролику — пометка в отчёте, на итог не влияет (B7)
        res.append(("SKIP", name, why))
        log(f"[SKIP] {name} — {why}")

    if not final.exists():
        raise SystemExit("Нет финального файла — сначала assemble")
    fps, D = tl["fps"], tl["total_frames"] / tl["fps"]
    target = proj.cfg.get("target_duration")
    info = probe(final)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    W, H = proj.size
    chk(v["width"] == W and v["height"] == H, "Разрешение", f"{v['width']}×{v['height']}")
    chk(v["r_frame_rate"] == f"{fps}/1", "FPS", v["r_frame_rate"])
    chk(int(v.get("nb_read_frames", 0)) == tl["total_frames"], "Кадры", f"{v.get('nb_read_frames')} из {tl['total_frames']}")
    dur = float(info["format"]["duration"])
    if target:
        chk(abs(dur - target) < 0.02, "Длительность = цель", f"{dur:.3f} c (цель {target})")
    else:
        chk(abs(dur - D) < 0.05, "Длительность", f"{dur:.3f} c")
    chk(bool(a), "Есть звуковая дорожка", (f"{a[0]['codec_name']} {a[0]['sample_rate']} Гц ×{a[0]['channels']}" if a else ""))
    if not fast:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(final), "-f", "null", "-"], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL)
        chk(r.stderr.strip() == "", "Декодируется без ошибок", r.stderr.strip()[:200])

    # --- речь
    lines = [(s["start"] + L["t0"], s["start"] + L["t1"], L["text"], s) for s in tl["scenes"] for L in s["lines"]]
    if lines:
        cut = [x[2] for x in lines if x[1] > x[3]["start"] + x[3]["dur"] + 1e-3]
        chk(not cut and lines[-1][1] <= dur - 0.15, "Слова не обрезаны",
            f"речь кончается в {lines[-1][1]:.2f} c" + (f"; вылезают: {cut}" if cut else ""))
        lo, hi = proj.cfg["tts"].get("rate_range", [98, 125])
        chk(lo - 1 <= tl["rate"] <= hi + 1, "Темп естественный",
            f"rate {tl['rate']:.0f} (диапазон {lo}–{hi}); {tl['wpm_speech']} слов/мин в речи")
    else:
        for n in ("Слова не обрезаны", "Темп естественный"):
            skip(n, "нет речи")
    md = proj.build / "mix"
    I, pk = loudness(final)
    chk(I is not None and abs(I - float(proj.cfg.get("loudness", -16))) < 1.5 and pk < -0.5, "Громкость итога",
        f"{I:.1f} LUFS, пик {pk:.1f} dBFS" if I is not None else "тишина: нет ни речи, ни музыки")
    from .kinds import of as kind_of, qa as kind_checks  # тип ролика (ROADMAP C1): длительность, голос, музыка
    k = kind_of(proj.cfg)
    music_db = mean_db(final, 0, dur) if (k.music or k.source_audio) and not lines else None
    for ok, name, det in kind_checks(proj, tl, dur, music_db, final):
        chk(ok, name, det)
    from .music import qa_license as music_license  # трек из библиотеки или assets/ — с источником и лицензией (C3)
    ml = music_license(proj)
    if ml is None:
        skip("Музыка: источник и лицензия", "музыка выключена")
    else:
        chk(ml[0], "Музыка: источник и лицензия", ml[1])
    from .assets import qa_check as assets_check  # ассеты сцен: файл, источник, лицензия (ROADMAP C2)
    ac = assets_check(proj)
    if ac is None:
        skip("Ассеты: источник и лицензия", "в ролике нет фото, видео и звука из assets/")
    else:
        chk(ac[0], "Ассеты: источник и лицензия", ac[1])
    from .platforms import checks as platform_checks  # выход по профилю площадки (ROADMAP B1)
    platform_checks(proj, info, dur, I, pk, chk, warn)
    if lines:
        if (md / "levels.json").exists():  # P4.2: WAV микса не хранятся, громкости пишет assemble
            lv = json.loads((md / "levels.json").read_text(encoding="utf-8"))
            vI, mI = lv["voice_lufs"], lv["music_lufs"]
        else:  # сборка до P4.2: промежуточные WAV лежат в build/mix/
            vI = loudness(md / "voice.wav")[0]
            mI = loudness(md / "music_ducked.wav")[0] if (md / "music_ducked.wav").exists() else None
        if mI is not None:
            chk(14 <= vI - mI <= 28, "Музыка значительно тише речи, но слышна",
                f"голос {vI:.1f} LUFS, музыка {mI:.1f} LUFS (разница {vI - mI:.1f} LU, норма 14–28)")
        l0 = lines[0]
        sp = mean_db(final, l0[0] + 0.1, min(l0[1], l0[0] + 1.5))
        chk(sp is not None and sp > -32, "Голос слышен в итоговом файле", f"средний уровень первой фразы {sp} dB")
    else:
        skip("Голос слышен в итоговом файле", "нет речи")

    # --- субтитры
    subs = [(s["start"] + c["t0"], s["start"] + c["t1"], c["lines"]) for s in tl["scenes"] for c in s["subs"]]
    no_subs = ("субтитры выключены" if not proj.cfg["subtitles"].get("enabled", True)
               else "нет речи" if not lines else None)
    if no_subs:
        for n in ("Субтитры: строки и ширина", "Субтитры не накладываются друг на друга",
                  "Субтитры не мелькают (>0.55 c)", "Каждая фраза имеет субтитр в момент начала"):
            skip(n, no_subs)
    else:
        _check_subs(proj, chk, subs, lines)

    # --- вёрстка: контент сцены в полях кадра (P1.10; с ROADMAP B2 — ❌)
    from .safezone import qa_check
    qa_check(proj, lambda st, name, det: chk(st == "PASS", name, det))

    # --- листы кадров из ГОТОВОГО файла (заодно доказывает воспроизведение)
    tmp = proj.qa_dir / "_g.png"
    y0 = int(H * subs_top(proj, W, H))
    (proj.qa_dir / "subs_check.png").unlink(missing_ok=True)  # от прошлого прогона с субтитрами
    if subs:
        crops, labels = [], []
        for (a0, a1, ln) in subs[::max(1, len(subs) // 24)]:
            im = grab(final, (a0 + a1) / 2, tmp).crop((0, y0, W, H))
            crops.append(im.resize((W // 2, (H - y0) // 2))); labels.append(f"{(a0 + a1) / 2:.2f}s")
        sheet(crops, labels, 4 if H >= W else 3, proj.qa_dir / "subs_check.png")
    mids = [s["start"] + s["dur"] / 2 for s in tl["scenes"]]
    ms = mids[:: max(1, len(mids) // 24)]
    fr = [grab(final, t, tmp).resize((W // 4, H // 4)) for t in ms]
    sheet(fr, [f"{t:.2f}s" for t in ms], 6 if H >= W else 4, proj.qa_dir / "final_frames.png")
    tmp.unlink(missing_ok=True)

    ok = all(r[0] != "FAIL" for r in res)
    mark = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "WARN": "⚠️"}
    with open(proj.qa_dir / "report.md", "w", encoding="utf-8") as fh:
        fh.write(f"# QA: {proj.slug}\n\nИтог: **{'PASS' if ok else 'FAIL'}**\n\n")
        for st, n, d in res:
            fh.write(f"- {mark[st]} {n} — {d}\n")
        fh.write("\nОткрой глазами: " + ("`qa/subs_check.png`, " if subs else "") + "`qa/final_frames.png`.\n")
    log(("ВСЁ ОК" if ok else "ЕСТЬ ПРОБЛЕМЫ") + f" -> {proj.qa_dir / 'report.md'}")
    return ok


def _check_subs(proj, chk, subs, lines):
    f = G.font(S.font_size(proj), "bold")
    maxw = S.max_width(proj)
    ml = int(proj.cfg["subtitles"].get("max_lines", 2))
    bad = [c for c in subs if not c[2] or len(c[2]) > ml or max(f.getlength(l) for l in c[2]) > maxw]
    chk(not bad, f"Субтитры: не больше {ml} строк и влезают по ширине", f"{len(subs)} шт." + (f"; плохие: {bad[:3]}" if bad else ""))
    ov = [i for i in range(len(subs) - 1) if subs[i][1] > subs[i + 1][0] + 1e-3]
    chk(not ov, "Субтитры не накладываются друг на друга")
    short = [c for c in subs if c[1] - c[0] < 0.55]
    chk(len(short) <= max(1, len(subs) // 10), "Субтитры не мелькают (>0.55 c)", f"коротких: {len(short)}")
    coverage = []
    for (a0, a1, txt, _) in lines:
        cov = any(c[0] <= a0 + 0.15 and c[1] >= a0 + 0.15 for c in subs)
        if not cov:
            coverage.append(txt)
    chk(not coverage, "Каждая фраза имеет субтитр в момент начала", "; ".join(coverage[:3]))

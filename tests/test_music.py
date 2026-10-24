"""ROADMAP C3: музыка и ритм (studio/music.py) — доли трека, склейки в долю (`music.sync`), биты из долей у сцен без
голоса, свой трек на главу с кроссфейдом, библиотека студии и лицензии, QA «Склейки в долю» по звуку итога."""
import shutil
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml

from studio import audio, project, timing, validate
from studio import music as M
from studio.tts import SR

FIX = Path(__file__).parent / "fixtures"
FPS = 30


def _quiet(*_a, **_k):
    pass


def _copy(tmp_path, src, name=None, **music):
    dst = tmp_path / (name or src.name)
    shutil.copytree(src, dst)
    if music:
        p = dst / "project.yaml"
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        d["music"] = {**(d.get("music") or {}), **music}
        p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return dst


def _tone(path, f, sec=3.0):
    t = np.arange(int(sec * SR)) / SR
    y = np.sin(2 * np.pi * f * t) * 0.5
    M._write(path, np.stack([y, y], 1))
    return path


# ------------------------------------------------------------------ детектор долей
@pytest.mark.parametrize("bpm,meter,off", [(120, 4, 0.0), (112, 4, 0.0), (128, 4, 0.23), (95, 3, 0.1)])
def test_detect_beats_within_frame(tmp_path, bpm, meter, off):
    M.beat_track(tmp_path / "b.wav", bpm, meter=meter)
    x = M.decode(tmp_path / "b.wav")
    x = np.concatenate([np.zeros(int(off * SR), np.float32), x, x])
    x = x + np.random.default_rng(1).standard_normal(len(x)).astype(np.float32) * 0.01
    r = M.detect(x, meter)
    spb = 60 / bpm
    truth = off + spb * np.arange(int((len(x) / SR - off) / spb))
    B = np.asarray(r["beats"])
    err = [float(np.min(np.abs(B - t))) for t in truth]
    assert max(err) < 1 / FPS / 2, f"доля дальше полукадра: {max(err) * 1000:.1f} мс"
    assert abs(r["bpm"] - bpm) < 0.5
    D = np.asarray(r["down"])  # сильные доли — первые доли тактов
    assert max(float(np.min(np.abs(D - t))) for t in truth[::meter][1:-1]) < 0.01


def test_detect_silence_has_no_beats():
    assert M.detect(np.zeros(SR * 4, np.float32))["beats"] == []


def test_beat_track_loops_on_beat(tmp_path):
    M.beat_track(tmp_path / "b.wav", 100, bars=2)
    with wave.open(str(tmp_path / "b.wav")) as w:
        assert w.getnframes() == round(2 * 4 * 0.6 * SR)  # ровно 8 долей: петля в долю


# ------------------------------------------------------------------ склейки в долю
def test_snap_to_grid_and_keeps_speech():
    cuts = [i * 0.5 for i in range(41)]
    ds = M.snap([3.1, 2.9, 4.2, 5.0], [0, 3.3, 0, 0], cuts, 20.0)
    ends = np.cumsum(ds)
    assert abs(ends[-1] - 20) < 1e-9
    assert all(min(abs(e - c) for c in cuts) < 1e-9 for e in ends[:-1])
    assert ds[1] >= 3.3  # речь сцены не режется: склейка не раньше конца речи
    with pytest.raises(SystemExit, match="нет доли"):
        M.snap([3, 3], [0, 5], [0, 1, 2, 3], 4.0)
    ds = M.snap([3.1, 2.0], [0, 2.5], cuts, None)  # длина по сценам: последняя — своей длины, не короче речи
    assert ds == [3.0, 2.5]
    ds = M.snap([1, 1, 1], [0, 0, 1.4], cuts, 3.0)  # место под последнюю сцену: склейка раньше ближайшей
    assert ds == [1.0, 0.5, 1.5]


def _music_demo(tmp_path, **music):
    root = _copy(tmp_path, FIX / "kinds" / "music", **music)
    proj = project.load(root)
    return proj, timing.layout(proj, log=_quiet)


def test_music_demo_cuts_on_beats(tmp_path):
    proj, tl = _music_demo(tmp_path)
    B = np.asarray(M.grid(proj, tl["duration"])["beats"])
    assert tl["sync"]["mode"] == "beat" and abs(tl["sync"]["bpm"] - 112) < 0.5
    for s in tl["scenes"][1:]:  # склейка — в кадре, ближайшем к доле (≤ полкадра)
        assert np.min(np.abs(B - s["start_frame"] / FPS)) <= 0.5 / FPS + 1e-6, s["id"]
    for s in tl["scenes"]:  # у сцен без голоса биты — доли трека; субтитров из них нет
        assert s["beats"] and all(b.get("music") for b in s["beats"]) and s["subs"] == []
        for b in s["beats"]:
            assert np.min(np.abs(B - (s["start"] + b["t0"]))) <= 0.5 / FPS + 1e-6
    bul = next(s for s in tl["scenes"] if s["template"] == "bullets")
    from studio import packs
    from studio.render import prepare
    tl2, ctx = prepare(proj)
    s2 = next(s for s in tl2["scenes"] if s["id"] == bul["id"])
    tpl = packs.REGISTRY["bullets"](ctx, s2, s2["state_in"])
    assert tpl.bt(2) == bul["beats"][2]["t0"]  # first_beat: 2 — первый пункт в долю


def test_sync_bar_uses_downbeats(tmp_path):
    proj, tl = _music_demo(tmp_path, sync="bar")
    g = M.grid(proj, tl["duration"])
    D = np.asarray(g["cuts"])
    assert len(D) < len(g["beats"]) / 3
    for s in tl["scenes"][1:]:
        assert np.min(np.abs(D - s["start_frame"] / FPS)) <= 0.5 / FPS + 1e-6


def test_source_hash_only_changes_with_sync(tmp_path):
    a = project.load(_copy(tmp_path, FIX / "fake_tts", "a"))
    b = project.load(_copy(tmp_path, FIX / "fake_tts", "b", level_db=-20))
    c = project.load(_copy(tmp_path, FIX / "fake_tts", "c", sync="beat"))
    assert timing.source_hash(a) == timing.source_hash(b) != timing.source_hash(c)


def test_voiced_sync_never_cuts_speech(tmp_path):
    proj = project.load(_copy(tmp_path, FIX / "fake_tts", sync="beat", bpm=100))
    tl = timing.layout(proj, log=_quiet)
    B = np.asarray(M.grid(proj, tl["duration"])["beats"])
    for s in tl["scenes"]:
        assert all(L["t1"] <= s["dur"] - 0.1 for L in s["lines"])  # речь внутри сцены
        assert not any(b.get("music") for b in s["beats"])  # биты — речь, а не доли
    for s in tl["scenes"][1:]:
        assert np.min(np.abs(B - s["start_frame"] / FPS)) <= 0.5 / FPS + 1e-6


def test_qa_sync_on_mix(tmp_path):
    """QA ищет доли в готовом звуке: ровные склейки — ✅, сдвиг на 3 кадра — ❌."""
    proj, tl = _music_demo(tmp_path)
    out = tmp_path / "mix"
    out.mkdir()
    wav = audio.mix(proj, out, log=_quiet)
    ok, det = M.qa_sync(proj, tl, wav)
    assert ok, det
    bad = dict(tl, scenes=[dict(s, start_frame=s["start_frame"] + (3 if i else 0)) for i, s in enumerate(tl["scenes"])])
    ok, det = M.qa_sync(proj, bad, wav)
    assert not ok, det


def test_kind_music_without_sync_warns(tmp_path):
    root = _copy(tmp_path, FIX / "kinds" / "music")
    p = root / "project.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    del d["music"]["sync"]
    p.write_text(yaml.safe_dump(d), encoding="utf-8")
    rep = validate.check(project.load(root))
    assert rep.ok and any("music.sync" in w for w in rep.warns)


def test_validate_sync_errors(tmp_path):
    e = validate.check(project.load(_copy(tmp_path, FIX / "fake_tts", "a", sync="tempo"))).errs
    assert any("music.sync" in x for x in e)
    e = validate.check(project.load(_copy(tmp_path, FIX / "fake_tts", "b", sync="beat",
                                          by_chapter={"ch01": "x.wav"}))).errs
    assert any("by_chapter" in x and "sync" in x for x in e)


# ------------------------------------------------------------------ свой трек на главу
def test_bed_crossfades_chapter_tracks(tmp_path):
    root = _copy(tmp_path, FIX / "fake_tts")
    (root / "assets").mkdir()
    _tone(root / "assets" / "a.wav", 440)
    _tone(root / "assets" / "b.wav", 660)
    ch2 = yaml.safe_load((root / "script" / "ch01.yaml").read_text(encoding="utf-8"))
    ch2["chapter"] = "ch02"
    (root / "script" / "ch02.yaml").write_text(yaml.safe_dump(ch2), encoding="utf-8")
    p = root / "project.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["chapters"] = ["ch01", "ch02"]
    d["music"] = {"file": "assets/a.wav", "by_chapter": {"ch02": "assets/b.wav"}, "crossfade": 1.0}
    p.write_text(yaml.safe_dump(d), encoding="utf-8")
    proj = project.load(root)
    tl = timing.layout(proj, log=_quiet)
    out = tmp_path / "o"
    out.mkdir()
    y = M.decode(M.bed(proj, tl, out), 2)[:, 0]
    assert abs(len(y) - tl["total_frames"] * SR / FPS) <= 1
    t2 = dict(M.chapter_starts(tl))["ch02"]

    def level(f, a, b):  # амплитуда частоты f на отрезке [a, b) с
        seg = y[int(a * SR):int(b * SR)]
        t = np.arange(len(seg)) / SR
        return abs(np.mean(seg * np.exp(-2j * np.pi * f * t))) * 2
    assert level(440, t2 - 1.5, t2 - 0.6) > 0.4 and level(660, t2 - 1.5, t2 - 0.6) < 0.01
    assert level(660, t2 + 0.6, t2 + 1.5) > 0.4 and level(440, t2 + 0.6, t2 + 1.5) < 0.01
    assert level(440, t2 - 0.1, t2 + 0.1) > 0.2 and level(660, t2 - 0.1, t2 + 0.1) > 0.2  # кроссфейд
    assert Path(audio.mix(proj, out, log=_quiet)).exists()  # микс берёт подложку, а не петлю


# ------------------------------------------------------------------ библиотека и лицензии
def test_library_track_and_license(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    _tone(lib / "drive.wav", 220)
    monkeypatch.setattr(M, "library_dir", lambda proj: lib)
    root = _copy(tmp_path, FIX / "fake_tts", file="drive.wav")
    proj = project.load(root)
    assert M.resolve(proj, "drive.wav") == lib / "drive.wav"
    rep = validate.check(proj)
    assert rep.ok and any("drive.wav" in w and "лицензию" in w for w in rep.warns)
    assert M.qa_license(proj)[0] is False
    (lib / "music.yaml").write_text(yaml.safe_dump({"tracks": [
        {"file": "drive.wav", "source": "код теста", "license": "CC0"}]}, allow_unicode=True), encoding="utf-8")
    rep = validate.check(project.load(root))
    assert not any("drive.wav" in w for w in rep.warns)
    ok, det = M.qa_license(project.load(root))
    assert ok and "CC0" in det
    assert M.qa_license(project.load(_copy(tmp_path, FIX / "fake_tts", "p")))[0]  # процедурная — без вопросов
    e = validate.check(project.load(_copy(tmp_path, FIX / "fake_tts", "m", file="nope.mp3"))).errs
    assert any("nope.mp3" in x for x in e)


def test_project_track_license_via_assets_yaml(tmp_path):
    root = _copy(tmp_path, FIX / "fake_tts", file="assets/song.wav")
    (root / "assets").mkdir()
    _tone(root / "assets" / "song.wav", 330)
    (root / "assets.yaml").write_text(yaml.safe_dump({"assets": [
        {"file": "assets/song.wav", "source": "клиент", "license": "права у клиента"}]}, allow_unicode=True),
        encoding="utf-8")
    ok, det = M.qa_license(project.load(root))
    assert ok and "клиента" in det

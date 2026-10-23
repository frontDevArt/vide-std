"""ROADMAP B4: нарезка — проект `cutdown: {source}` со сценами-ссылками `from:` на исходник; настройки и кэш озвучки
исходника (тот же контекст строк — тот же ключ кэша ElevenLabs), шапка lab и подсветка главы — как в исходнике;
команда `cutdown` выбирает отрезки в пределах площадки и пишет проекты `<исходник>-cut-N/`."""
from pathlib import Path

import pytest
import yaml
from conftest import make_gallery

from studio import cli, config, cutdown, project, tts
from studio.timing import line_jobs


def _write(p: Path, data, text=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text if text is not None else yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                 encoding="utf-8")


def _cut(root: Path, src: str, chapters: dict, **cfg):
    _write(root / "project.yaml", {"cutdown": {"source": src}, "platform": "youtube-shorts", "format": "vertical",
                                   "chapters": list(chapters), **cfg})
    for ch, scenes in chapters.items():
        _write(root / "script" / f"{ch}.yaml", {"chapter": ch, "scenes": scenes})
    return project.load(root)


@pytest.fixture
def gallery(tmp_path):
    return make_gallery(tmp_path / "gal")


def test_schema_knows_cutdown():
    assert config.check({"cutdown": {"source": "x"}}) == []
    assert "cutdown" not in config.DEFAULTS


def test_refs_inherit_source(gallery, tmp_path):
    cut = _cut(tmp_path / "gal-cut", "gal", {
        "ch01": [{"id": "hook", "template": "lab_full_number", "lines": ["Twenty-one days?"]},
                 {"from": "s06"}, {"from": "ch01/s07", "params": {"color": "accent"}}],
        "ch02": [{"from": "s04"}]})
    src = project.load(gallery)
    assert cut.src == gallery.resolve() and cut.bdir("tts") == gallery.resolve() / "build" / "tts"
    assert cut.cfg["tts"] == src.cfg["tts"] and cut.cfg["style"] == src.cfg["style"]  # настройки исходника
    assert cut.cfg["format"] == "vertical" and cut.cfg["platform"] == "youtube-shorts" and cut.size == (1080, 1920)
    (_, d1), (_, d2) = cut.chapters
    s_src = {(ch, s["id"]): s for ch, d in src.chapters for s in d["scenes"]}
    hook, s06, s07 = d1["scenes"]
    assert s06["lines"] == s_src[("ch01", "s06")]["lines"] and s06["template"] == "lab_versus"
    assert s07["params"]["color"] == "accent"  # свои params — поверх
    assert s07["params"]["value"] == s_src[("ch01", "s07")]["params"]["value"]
    # шапка lab копится к началу нарезки: первая lab-сцена (крючок) получает рубрику и шаги из ch01/s02–s05
    ch = hook["params"]["chrome"]
    assert ch["rubric"] == "Myth on Trial" and ch["step"] == 2 and ch["clock"] == "21:15"
    assert d2.get("glow") == "ember"  # подсветка главы исходника
    assert "_ctx" not in hook


def test_line_context_from_source(gallery, tmp_path):
    """Строки сцены-ссылки идут в синтез с соседями из исходника, а не из нарезки."""
    cut = _cut(tmp_path / "gal-cut", "gal", {"ch01": [{"id": "hook", "template": "statement", "lines": ["New line."]},
                                                      {"from": "s06"}, {"from": "s07"}]})
    src = project.load(gallery)
    src_scenes = src.chapters[0][1]["scenes"]
    want = line_jobs(src_scenes)[5] + line_jobs(src_scenes)[6]
    got = [j for sj in line_jobs(cut.chapters[0][1]["scenes"])[1:] for j in sj]
    assert got == want
    assert got[0][2] == "Your phone on the desk pulls on attention, memory and mood."  # prev — из исходника
    hook = line_jobs(cut.chapters[0][1]["scenes"])[0][0]
    assert hook[2] is None and hook[3] == got[0][1]  # новая строка — соседи нарезки


def test_elevenlabs_cache_keys_match(tmp_path):
    """Ключ кэша ElevenLabs включает previous_text/next_text: у нарезки он совпадает с исходником — синтеза нет."""
    src = make_gallery(tmp_path / "el")
    p = src / "project.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "backend: fake\n  voice: auto", "backend: elevenlabs\n  voice: v1\n  model: m1"), encoding="utf-8")
    cut = _cut(tmp_path / "el-cut", "el", {"ch01": [{"from": "s03"}, {"from": "s04"}]})
    sp = project.load(src)
    tc = cut.cfg["tts"]
    assert tc == sp.cfg["tts"] and tc["backend"] == "elevenlabs"

    def keys(proj, ids):
        out = []
        for _, d in proj.chapters[:1]:
            for sc, jobs in zip(d["scenes"], line_jobs(d["scenes"])):
                if sc["id"] in ids:
                    out += [tts.cache_key(t, proj.cfg["tts"], 105, pr, nx, v) for _, t, pr, nx, v in jobs]
        return out
    assert keys(cut, {"s03", "s04"}) == keys(sp, {"s03", "s04"})
    own = "In one study | ninety-six people | tracked a new habit."
    plain = _cut(tmp_path / "el-plain", "el", {"ch01": [{"from": "s03", "lines": [own]}]})
    assert "_ctx" not in plain.chapters[0][1]["scenes"][0]  # свои lines — свой контекст


def test_bad_refs(gallery, tmp_path):
    with pytest.raises(SystemExit, match="нет сцены ch01/s99"):
        _cut(tmp_path / "a", "gal", {"ch01": [{"from": "s99"}]})
    with pytest.raises(SystemExit, match="нужно chNN/sNN"):
        _cut(tmp_path / "b", "gal", {"ch01": [{"from": "a/b/c"}]})


def test_candidates_and_pick():
    S = cutdown.Scene
    sc = [S("ch01", "s01", "lab_chapter", 3, "", 0, [], "карточка главы", 0),
          S("ch01", "s02", "fd_number", 10, "Fifty?", 3, ["цифра", "вопрос"], "", 1),
          S("ch01", "s03", "lab_versus", 10, "", 0, [], "", 2),
          S("ch01", "s04", "lab_verdict", 10, "", 3, ["вердикт"], "", 3),
          S("ch01", "s05", "lab_diagram", 12, "subscribe", 0, [], "призыв исходника", 4),
          S("ch02", "s01", "lab_flow", 25, "", 0, [], "", 5),
          S("ch02", "s02", "lab_hero_stack", 25, "", 2, ["цифра"], "", 6)]
    cands = cutdown.candidates(sc, 20, 40, 30)
    assert cands[0].span == "ch01/s02-s04" and cands[0].dur == 30  # крючок + развязка
    assert all(20 <= c.dur <= 40 for c in cands)
    assert not any(s.skip for c in cands for s in c.scenes)  # без карточек глав и призывов
    assert not any(len({s.chapter for s in c.scenes}) > 1 for c in cands)
    picked = cutdown.pick(cands, 3)
    keys = [(s.chapter, s.id) for c in picked for s in c.scenes]
    assert len(keys) == len(set(keys)) and [c.scenes[0].n for c in picked] == sorted(c.scenes[0].n for c in picked)
    assert cutdown.parse_pick("ch01/s02-s03", sc).span == "ch01/s02-s03"
    with pytest.raises(SystemExit, match="нет сцены"):
        cutdown.parse_pick("ch01/s02-s09", sc)
    gap = cutdown.parse_pick("ch01/s02,s04", sc)  # с пропуском (призыв исходника между ними)
    assert [x.id for x in gap.scenes] == ["s02", "s04"] and gap.span == "ch01/s02,s04" and gap.dur == 20
    with pytest.raises(SystemExit, match="не по порядку"):
        cutdown.parse_pick("ch01/s03,s02", sc)


def test_rate_tags():
    assert cutdown.rate({"template": "lab_chapter"})[2] == "карточка главы"
    assert cutdown.rate({"template": "lab_anchor", "lines": ["Subscribe now."]})[2] == "призыв исходника"
    s, tags, _ = cutdown.rate({"template": "lab_anchor", "lines": ["Does it work?"],
                               "params": {"verdict": {"verdict": "TRUE"}, "source": {"text": "x"}}})
    assert s == 4.5 and tags == ["вердикт", "вопрос", "источник"]


def test_command_end_to_end(tmp_path, capsys):
    """Исходник озвучен → cutdown пишет проект → voice нарезки без нового синтеза → render/assemble/qa ✅ в пределах."""
    from studio import workspace
    (tmp_path / "projects").mkdir()
    with workspace.use(tmp_path):
        src = make_gallery(tmp_path / "projects" / "gal")
        assert cli.main(["voice", str(src)]) == 0
        cache = sorted((src / "build" / "tts").iterdir())
        assert cli.main(["cutdown", str(src), "--to", "youtube-shorts", "--list", "--min", "5", "--max", "30"]) == 0
        assert not (tmp_path / "projects" / "gal-cut-1").exists()  # --list ничего не пишет
        assert cli.main(["cutdown", str(src), "--to", "youtube-shorts", "--pick", "ch01/s06-s08"]) == 0
        dst = tmp_path / "projects" / "gal-cut-1"
        script = (dst / "script" / "ch01.yaml").read_text(encoding="utf-8")
        assert "  - from: s06" in script and "# - id: hook" in script and "# - id: cta" in script
        cut = project.load(dst)
        assert cut.cfg["platform"] == "youtube-shorts" and [s["id"] for s in cut.chapters[0][1]["scenes"]] == \
            ["s06", "s07", "s08"]
        assert cli.main(["validate", str(dst)]) == 0
        assert cli.main(["voice", str(dst)]) == 0
        assert sorted((src / "build" / "tts").iterdir()) == cache  # озвучка — из кэша исходника
        assert not (dst / "build" / "tts").exists()
        assert cli.main(["render", str(dst), "--workers", "2"]) == 0
        assert cli.main(["assemble", str(dst)]) == 0
        assert cli.main(["qa", str(dst), "--fast"]) == 0
        rep = (dst / "qa" / "report.md").read_text(encoding="utf-8")
        assert "✅ Площадка youtube-shorts: кадр — 1080×1920" in rep and "Итог: **PASS**" in rep
        capsys.readouterr()
        assert cli.main(["cutdown", str(src), "--to", "youtube-shorts", "--pick", "ch01/s06-s08"]) == 0
        assert "уже есть" in capsys.readouterr().out  # готовую нарезку без --force не трогаем
        with pytest.raises(SystemExit, match="уже нарезка"):
            cli.main(["cutdown", str(dst), "--to", "tiktok"])


def test_cut_does_not_overwrite_studio_voice_measurement(tmp_path, monkeypatch):
    """Замер темпа нарезки (фрагмент ролика) не перезаписывает замер голоса студии (voices.yaml)."""
    from studio import calibration, voices
    src = make_gallery(tmp_path / "gal")
    cut = _cut(tmp_path / "gal-cut", "gal", {"ch01": [{"from": "s06"}]})
    saved = []
    monkeypatch.setattr(voices, "save_measurement", lambda *a, **k: saved.append(a) or True)
    tl = {"wpm_speech": 150, "rate": 105, "words": 10}
    calibration.calibrate(cut, tl)
    assert saved == [] and (cut.root / "build" / "voice_calibration.json").exists()
    calibration.calibrate(project.load(src), tl)
    assert len(saved) == 1

"""ROADMAP C1: типы роликов (`kind` в project.yaml, studio/kinds.py) — фазы, обязательные поля брифа, проверки
validate/status/qa, ролики без голоса (`tts.backend: none`) и демо-проект на каждый готовый тип
(tests/fixtures/kinds/<тип>/; полная цепочка до QA — `python -m studio selftest --kinds`)."""
import argparse
import shutil
from pathlib import Path

import pytest
import yaml

from studio import calibration, cli, kinds, project, status, timing, tts, validate, workspace
from studio.project import STUDIO_ROOT

DEMOS = Path(__file__).parent / "fixtures" / "kinds"
ROADMAP = {"explainer", "short-hook", "promo", "music", "slideshow", "listicle", "data-story", "tutorial", "clip"}


def _quiet(*_a, **_k):
    pass


def _demo(tmp_path, name, **over):
    dst = tmp_path / name
    shutil.copytree(DEMOS / name, dst)
    if over:
        p = dst / "project.yaml"
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        for k, v in over.items():
            if isinstance(v, dict) and isinstance(data.get(k), dict):
                data[k].update(v)
            else:
                data[k] = v
        p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return dst


def _script(root, scenes):
    (root / "script" / "ch01.yaml").write_text(yaml.safe_dump({"scenes": scenes}, allow_unicode=True),
                                               encoding="utf-8")


def _errs(root):
    return validate.check(project.load(root)).errs


def test_registry_matches_roadmap():
    assert set(kinds.KINDS) == ROADMAP
    for k in kinds.KINDS.values():
        assert k.title and k.hint
        assert k.needs or (DEMOS / k.id / "project.yaml").exists(), f"{k.id}: нет демо и не сказано, чего ждёт"


@pytest.mark.parametrize("kind", sorted(k for k, v in kinds.KINDS.items() if not v.needs))
def test_demo_validates_and_lays_out(tmp_path, kind):
    root = _demo(tmp_path, kind)
    proj = project.load(root)
    assert kinds.of(proj.cfg).id == kind
    rep = validate.check(proj)
    assert rep.ok, rep.errs
    tl = timing.layout(proj, log=_quiet)
    lo, hi = kinds.of(proj.cfg).duration or (0, 1e9)
    assert lo <= tl["duration"] <= hi
    if not kinds.of(proj.cfg).voice:
        assert not any(s["lines"] for s in tl["scenes"])


def test_old_project_is_explainer_and_cfg_unchanged(tmp_path):
    root = _demo(tmp_path, "explainer")
    p = root / "project.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data.pop("kind")
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    cfg = project.load(root).cfg
    assert "kind" not in cfg  # без значения по умолчанию в cfg: ключ кэша рендера старых проектов не меняется
    assert kinds.of(cfg).id == "explainer"


def test_unknown_kind(tmp_path):
    errs = _errs(_demo(tmp_path, "explainer", kind="explaner"))
    assert any("explaner" in e and "explainer" in e for e in errs)


def test_voiced_kind_without_voice_stops(tmp_path):
    errs = _errs(_demo(tmp_path, "explainer", tts={"backend": "none"}))
    assert any("без голоса" in e or "голос" in e for e in errs)


def test_music_with_lines_is_error(tmp_path):
    root = _demo(tmp_path, "music")
    _script(root, [{"id": "s01", "template": "statement", "lines": ["Hello there."], "params": {"text": "Hi"}}])
    errs = _errs(root)
    assert any("lines" in e for e in errs)


def test_music_needs_music(tmp_path):
    errs = _errs(_demo(tmp_path, "music", music={"enabled": False}))
    assert any("music.enabled" in e for e in errs)


def test_short_hook_needs_exact_duration(tmp_path):
    errs = _errs(_demo(tmp_path, "short-hook", target_duration=None))
    assert any("target_duration" in e for e in errs)


def test_short_hook_duration_range(tmp_path):
    errs = _errs(_demo(tmp_path, "short-hook", target_duration=90))
    assert any("15–60" in e for e in errs)


def test_promo_brief_fields(tmp_path):
    root = _demo(tmp_path, "promo")
    p = root / "project.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    del data["brief"]["cta"]
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    errs = _errs(root)
    assert any("brief.cta" in e for e in errs)
    ph = dict((n, ok) for n, ok, _ in status.phases(project.load(root)))
    assert ph["1 Бриф"] is False


def test_listicle_items_match_count(tmp_path):
    errs = _errs(_demo(tmp_path, "listicle", brief={"count": 5}))
    assert any("item" in e for e in errs)


def test_media_kind_files_phase(tmp_path):
    root = _demo(tmp_path, "music", kind="slideshow", brief={"photos": ["assets/a.jpg"]})
    proj = project.load(root)
    rep = validate.check(proj)
    assert any("assets/a.jpg" in e for e in rep.errs)
    assert any("C2" in w for w in rep.warns)
    ph = [n for n, _, _ in status.phases(proj)]
    assert "1б Материалы" in ph


def test_none_backend_probe_and_synth(tmp_path):
    cfg = {"backend": "none", "voice": "none"}
    assert tts.probe(cfg) == "ok"
    with pytest.raises(tts.TTSUnavailable):
        tts.synth("Hello.", cfg, 100, tmp_path)


def test_calibrate_without_speech_is_silent(tmp_path):
    proj = project.load(_demo(tmp_path, "music"))
    tl = timing.layout(proj, log=_quiet)
    assert calibration.calibrate(proj, tl) == []  # раньше: «темп голоса 0 слов/мин … (−100 %)»


def test_qa_checks_duration_and_voice(tmp_path):
    proj = project.load(_demo(tmp_path, "music"))
    tl = timing.layout(proj, log=_quiet)
    res = kinds.qa(proj, tl, dur=tl["duration"], music_db=-20.0)
    assert all(ok for ok, _, _ in res), res
    res = kinds.qa(proj, tl, dur=200.0, music_db=-80.0)
    bad = [n for ok, n, _ in res if not ok]
    assert any("длительность" in n for n in bad) and any("Музыка" in n for n in bad)


@pytest.fixture
def studio_root(tmp_path):
    shutil.copytree(STUDIO_ROOT / "projects" / "_template", tmp_path / "projects" / "_template")
    with workspace.use(tmp_path):
        yield tmp_path


def test_new_kind_music(studio_root):
    a = argparse.Namespace(topic="beat", slug="m", format="vertical", duration=None, lang="en", tts=None, kind="music")
    assert cli.cmd_new(a) == 0
    cfg = yaml.safe_load((studio_root / "projects" / "m" / "project.yaml").read_text(encoding="utf-8"))
    assert cfg["kind"] == "music" and cfg["tts"]["backend"] == "none"
    assert cfg["target_duration"]  # тип с точной длительностью: без --duration — умолчание типа


def test_new_kind_default_explainer(studio_root):
    a = argparse.Namespace(topic="x", slug="e", format="vertical", duration=None, lang="en", tts="fake", kind=None)
    assert cli.cmd_new(a) == 0
    cfg = yaml.safe_load((studio_root / "projects" / "e" / "project.yaml").read_text(encoding="utf-8"))
    assert cfg["kind"] == "explainer" and cfg["tts"]["backend"] == "fake"

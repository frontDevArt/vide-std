"""P1.6 (B8): триггеры `at:` проверяются после voice и в validate — не только print в процессе рендера."""
import shutil
from pathlib import Path

import yaml

from studio import cli, lab, timing
from studio.project import load
from studio.templates import REGISTRY

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"
WORDS = ["The", "median", "of", "66", "days.", "Median’s", "range,", "median,", "not", "mean."]


def _scene(params, template="lab_full_number"):
    return {"chapter": "ch01", "id": "s01", "template": template, "params": params,
            "beats": [{"t0": 0.0, "t1": 1.9}, {"t0": 2.0, "t1": 5.5}],
            "words": [{"w": w, "t0": 0.5 * i, "t1": 0.5 * i + 0.3} for i, w in enumerate(WORDS)]}


def test_resolved_triggers_pass():
    p = {"at": "66", "myth": {"value": 21, "strike_at": "w:median#2"}, "source": {"at": 1},
         "cards": [{"at": "median of"}, {"at": 2.5}, {"at": "1.5s"}, {}, None], "verdict": {"at": True}}
    assert lab.trigger_errors([_scene(p)], REGISTRY) == []


def test_missing_word_with_hint():
    errs = lab.trigger_errors([_scene({"hero": {"at": "medain"}})], REGISTRY)
    assert len(errs) == 1
    e = errs[0]
    assert "ch01/s01" in e and "hero.at" in e and "«medain»" in e and "median" in e  # подсказка — похожее слово


def test_occurrence_beyond_count():
    errs = lab.trigger_errors([_scene({"at": "median#3"})], REGISTRY)
    assert len(errs) == 1 and "вхождений 2" in errs[0]  # «Median’s» — другое слово


def test_nested_paths_and_beats():
    p = {"crowd": {"highlight": [{"at": "median"}, {"at": "nope"}]}, "myth": {"strike_at": 5}}
    errs = lab.trigger_errors([_scene(p)], REGISTRY)
    assert any("crowd.highlight[1].at" in e for e in errs)
    assert any("myth.strike_at" in e and "бит" in e for e in errs)
    assert len(errs) == 2


def test_non_lab_templates_ignored():
    assert lab.trigger_errors([_scene({"at": "nope"}, template="statement")], REGISTRY) == []


def test_template_uses_same_matching():
    # одна логика: то, что check считает найденным, находит и LabTemplate.at — и наоборот
    sc = _scene({})
    tpl = lab.LabTemplate({"W": 1920, "H": 1080, "fps": 30}, {**sc, "dur": 6.0}, {})
    for spec in ("66", "median#2", "median's", "of 66 days.", "nope", "median#4"):
        found = tpl.at(spec, lead=False) is not None
        assert found == (lab.trigger_errors([_scene({"at": spec})], REGISTRY) == [])


def _proj(dst, at):
    shutil.copytree(FIXTURE, dst)
    p = dst / "script" / "ch01.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["scenes"][1]["template"] = "lab_full_number"
    d["scenes"][1]["params"] = {"value": 66, "at": at}
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return dst


def test_voice_and_validate_report_missing(tmp_path, capsys):
    root = _proj(tmp_path / "p", "sixty-sixx")
    assert cli.main(["voice", str(root)]) == 1  # timeline записан, но ❌
    out = capsys.readouterr().out
    assert "❌" in out and "ch01/s02" in out and "«sixty-sixx»" in out and "sixty-six" in out.lower().replace("«sixty-sixx»", "")
    assert (root / "build" / "timeline.json").exists()
    assert cli.main(["validate", str(root)]) == 1
    assert "«sixty-sixx»" in capsys.readouterr().out


def test_voice_ok_and_stale_timeline_not_checked(tmp_path, capsys):
    root = _proj(tmp_path / "p", "sixty-six")
    assert cli.main(["voice", str(root)]) == 0
    assert cli.main(["validate", str(root)]) == 0
    capsys.readouterr()
    # сценарий поменяли после voice: timeline устарел — validate не судит по старым словам
    _proj_edit = root / "script" / "ch01.yaml"
    d = yaml.safe_load(_proj_edit.read_text(encoding="utf-8"))
    d["scenes"][1]["params"]["at"] = "nope"
    _proj_edit.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    assert cli.main(["validate", str(root)]) == 0
    assert "устарел" in capsys.readouterr().out


def test_gallery_has_no_missing_triggers(tmp_path):
    from conftest import make_gallery
    proj = load(make_gallery(tmp_path / "gallery", "vertical"))
    tl = timing.layout(proj, log=lambda *_: None)
    assert lab.trigger_errors(tl["scenes"], REGISTRY) == []

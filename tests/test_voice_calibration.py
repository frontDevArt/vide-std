"""P1.9: калибровка темпа голоса — замер после voice в build/voice_calibration.json, validate берёт его вместо wpm языка."""
import json
import shutil
from pathlib import Path

import yaml

from studio import calibration, cli, project, timing

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"


def _proj(dst, **cfg):
    shutil.copytree(FIXTURE, dst)
    if cfg:
        p = dst / "project.yaml"
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        data.update(cfg)
        p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return project.load(dst)


def _tl(wpm):
    return {"wpm_speech": wpm, "words": 300, "rate": 100}


def test_no_calibration_uses_language(tmp_path):
    proj = _proj(tmp_path / "p")
    assert calibration.wpm(proj) == (155, "язык en")


def test_fast_voice_warns_with_word_budget(tmp_path):
    proj = _proj(tmp_path / "p", target_duration=60)
    warns = calibration.calibrate(proj, _tl(185.0))
    data = json.loads((proj.build / "voice_calibration.json").read_text(encoding="utf-8"))
    assert data["wpm"] == 185.0 and data["table_wpm"] == 155
    assert (data["backend"], data["language"]) == ("fake", "en")
    assert len(warns) == 1
    w = warns[0]
    assert "185" in w and "155" in w and "+19 %" in w
    assert "на 60 c ≈ 185 слов" in w and "не 155" in w
    assert calibration.wpm(proj) == (185.0, "замер голоса fake")


def test_close_pace_no_warning(tmp_path):
    proj = _proj(tmp_path / "p")
    assert calibration.calibrate(proj, _tl(165.0)) == []  # +6,5 % — в пределах 10 %
    assert calibration.wpm(proj)[0] == 165.0


def test_slow_voice_without_target(tmp_path):
    proj = _proj(tmp_path / "p")
    (w,) = calibration.calibrate(proj, _tl(120.0))
    assert "−23 %" in w and "на 60 c ≈ 120 слов" in w  # без цели — бюджет на минуту


def test_calibration_of_other_voice_ignored(tmp_path):
    proj = _proj(tmp_path / "p")
    calibration.calibrate(proj, _tl(185.0))
    proj2 = _proj(tmp_path / "q", language="ru")
    shutil.copytree(proj.build, proj2.build, dirs_exist_ok=True)
    assert calibration.wpm(proj2) == (145, "язык ru")  # замер другого языка/голоса не подходит


def test_validate_uses_calibration(tmp_path, capsys):
    proj = _proj(tmp_path / "p")
    calibration.calibrate(proj, _tl(310.0))  # вдвое быстрее таблицы → оценка вдвое короче
    cli.main(["validate", str(proj.root)])
    out = capsys.readouterr().out
    assert "310 слов/мин, замер голоса fake" in out


def test_voice_writes_calibration(tmp_path, capsys):
    proj = _proj(tmp_path / "p")
    assert cli.main(["voice", str(proj.root)]) == 0
    tl = json.loads((proj.build / "timeline.json").read_text(encoding="utf-8"))
    data = json.loads((proj.build / "voice_calibration.json").read_text(encoding="utf-8"))
    assert data["wpm"] == tl["wpm_speech"]

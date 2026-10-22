"""P1.2 (B2, B11): речь с паузами длиннее target_duration — остановка с «сократите текст», при любом rate."""
import shutil
from pathlib import Path

import pytest
import yaml

from studio import project, timing

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"


def _proj(dst, **cfg):
    shutil.copytree(FIXTURE, dst)
    p = dst / "project.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    for k, v in cfg.items():
        if k == "tts":
            data["tts"].update(v)
        else:
            data[k] = v
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return project.load(dst)


def test_fixed_rate_too_long_stops(tmp_path):
    # B2: rate числом + target короче речи — раньше voice молча сжимал последнюю сцену
    proj = _proj(tmp_path / "p", target_duration=2)
    with pytest.raises(SystemExit) as e:
        timing.layout(proj, log=lambda *_: None)
    msg = str(e.value)
    assert "Сократите текст" in msg and "темпе 105" in msg
    assert not (tmp_path / "p" / "build" / "timeline.json").exists()


def test_fixed_rate_fits(tmp_path):
    proj = _proj(tmp_path / "p", target_duration=60)
    tl = timing.layout(proj, log=lambda *_: None)
    assert tl["duration"] == 60
    for s in tl["scenes"]:
        assert all(L["t1"] <= s["dur"] + 1e-6 for L in s["lines"])


def test_auto_rate_message_names_tried_rate(tmp_path, monkeypatch):
    # B11: за 6 попыток не дошли до потолка — не писать «даже при темпе {hi}»
    proj = _proj(tmp_path / "p", target_duration=5, tts={"rate": "auto", "rate_range": [98, 125]})
    monkeypatch.setattr(timing, "measure", lambda proj, r: [])
    monkeypatch.setattr(timing, "base_total", lambda proj, voiced: 100.0)
    with pytest.raises(SystemExit) as e:
        timing.choose_rate(proj, log=lambda *_: None)
    msg = str(e.value)
    assert "Сократите текст" in msg
    assert "даже при темпе 125" not in msg and "103" in msg


def test_auto_rate_ceiling_message(tmp_path):
    proj = _proj(tmp_path / "p", target_duration=2, tts={"rate": "auto", "rate_range": [98, 125]})
    with pytest.raises(SystemExit) as e:
        timing.choose_rate(proj, log=lambda *_: None)
    assert "даже при темпе 125" in str(e.value)

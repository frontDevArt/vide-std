"""P1.8 (B10): оценка «минут речи» в `status` — по `wpm` языка, а после `voice` — по замеру из `timeline.json`."""
import json
import shutil
from pathlib import Path

import yaml

from studio import project, status, timing

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"


def _proj(dst, **cfg):
    shutil.copytree(FIXTURE, dst)
    if cfg:
        p = dst / "project.yaml"
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        data.update(cfg)
        p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return project.load(dst)


def _report(proj):
    log = []
    status.report(proj, log=log.append)
    return "\n".join(log)


def test_pace_from_language_before_voice(tmp_path):
    proj = _proj(tmp_path / "p")  # en: 155 слов/мин
    words, wpm, src = status.pace(proj)
    assert (wpm, src) == (155, "язык en")
    assert f"~{words / 155:.1f} мин речи" in _report(proj)
    assert "155 слов/мин" in _report(proj)


def test_pace_language_ru(tmp_path):
    proj = _proj(tmp_path / "p", language="ru")
    assert status.pace(proj)[1:] == (145, "язык ru")


def test_pace_measured_after_voice(tmp_path):
    proj = _proj(tmp_path / "p")
    timing.layout(proj, log=lambda *_a, **_k: None)
    tl = json.loads((proj.build / "timeline.json").read_text(encoding="utf-8"))
    words, wpm, src = status.pace(proj)
    assert wpm == tl["wpm_speech"] and src == "замер timeline.json"
    rep = _report(proj)
    assert f"~{words / wpm:.1f} мин речи" in rep
    assert "замер" in rep

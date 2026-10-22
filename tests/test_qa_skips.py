"""P1.5 (B7): QA ролика без субтитров и без речи — проверки пропускаются с пометкой, а не падают."""
import shutil
from pathlib import Path

import yaml

from studio import assemble, project, qa, render, timing

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"


def _proj(dst, scenes, **cfg):
    shutil.copytree(FIXTURE, dst)
    p = dst / "project.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data.update(format="horizontal", **cfg)
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    (dst / "script" / "ch01.yaml").write_text(
        yaml.safe_dump({"chapter": "ch01", "title": "qa", "scenes": scenes}, allow_unicode=True), encoding="utf-8")
    proj = project.load(dst)
    quiet = lambda *_a, **_k: None  # noqa: E731
    timing.layout(proj, log=quiet)
    render.render(proj, workers=2, log=quiet)
    assemble.assemble(proj, log=quiet)
    return proj


def _scene(sid, text, lines=(), **kw):
    return {"id": sid, "template": "statement", "params": {"text": text}, "lines": list(lines), **kw}


def _report(proj):
    return (proj.qa_dir / "report.md").read_text(encoding="utf-8")


def test_qa_without_speech(tmp_path):
    # B7: музыкальный ролик без голоса — qa падал IndexError на lines[-1]
    proj = _proj(tmp_path / "p", [_scene("s01", "Silent", min_duration=1.0),
                                  _scene("s02", "Still silent", min_duration=1.0)])
    log = []
    assert qa.run(proj, log=log.append, fast=True)
    rep = _report(proj)
    assert "❌" not in rep
    assert "⏭️ Слова не обрезаны — нет речи" in rep
    assert "⏭️ Голос слышен в итоговом файле — нет речи" in rep
    assert "⏭️ Каждая фраза имеет субтитр в момент начала — нет речи" in rep
    assert not (proj.qa_dir / "subs_check.png").exists()
    assert (proj.qa_dir / "final_frames.png").exists()


def test_qa_subtitles_disabled(tmp_path):
    # B7: subtitles.enabled: false — qa падал на «каждая фраза имеет субтитр» (и на пустом листе субтитров)
    proj = _proj(tmp_path / "p", [_scene("s01", "Habit", ["Sixty-six days."])],
                 subtitles={"enabled": False}, music={"enabled": False})  # дакинг на 2 с — не про B7
    assert qa.run(proj, log=lambda *_: None, fast=True)
    rep = _report(proj)
    assert "❌" not in rep
    assert "✅ Слова не обрезаны" in rep and "✅ Голос слышен в итоговом файле" in rep
    assert "⏭️ Каждая фраза имеет субтитр в момент начала — субтитры выключены" in rep
    assert not (proj.qa_dir / "subs_check.png").exists()

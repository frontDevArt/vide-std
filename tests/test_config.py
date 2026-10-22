"""P2.1: схема project.yaml — значения по умолчанию прежние, опечатки в ключах видны, старые файлы грузятся."""
from pathlib import Path

import pytest
import yaml

from studio import config, project

ROOT = Path(__file__).resolve().parent.parent

# DEFAULTS из project.py до P2.1 — схема обязана их воспроизвести (golden и ключи кэша от них зависят)
OLD_DEFAULTS = {
    "language": "ru", "fps": 30, "format": "vertical", "target_duration": None,
    "tts": {"backend": "rhvoice", "voice": "auto", "rate": 105, "rate_range": [98, 125]},
    "pauses": {"start": 0.45, "comma": 0.18, "sentence": 0.40, "scene": 0.55, "end": 0.6, "max_extra_gap": 0.45},
    "style": {"palette": "neon", "font": "Inter Display"},
    "music": {"enabled": True, "level_db": -13, "duck": True},
    "sfx": {"enabled": True, "level_db": 0},
    "subtitles": {"enabled": True, "max_lines": 2, "size": None},
    "render": {"workers": None, "crf": 18, "preset": "medium"},
    "loudness": -16,
    "qa": {"safe_margin": 0.04},
    "chapters": [],
}


def test_defaults_unchanged():
    assert config.DEFAULTS == OLD_DEFAULTS
    assert project.DEFAULTS is config.DEFAULTS and project.deep_merge is config.deep_merge


def test_typo_top_level_suggests_nearest():
    w = config.check({"subtitle": {"enabled": False}})
    assert len(w) == 1 and "subtitle" in w[0] and "subtitles?" in w[0]


def test_typo_nested_suggests_nearest():
    w = config.check({"tts": {"backend": "fake", "rat": 100}})
    assert len(w) == 1 and "tts.rat" in w[0] and "tts.rate?" in w[0]


def test_unknown_without_neighbour():
    w = config.check({"zzzz": 1})
    assert w == ["неизвестный ключ zzzz — игнорируется"]


def test_types():
    assert config.check({"fps": "30"}) and config.check({"tts": "fake"})
    assert config.check({"music": {"enabled": 1}})  # не bool
    assert config.check({"fps": True})  # bool — не целое
    assert not config.check({"tts": {"rate": "auto", "voice": None}, "target_duration": 59.5,
                             "style": {"overrides": {"accent2": "#F78FB3"}}})


@pytest.mark.parametrize("path", sorted(str(p) for p in [*ROOT.glob("projects/*/project.yaml"),
                                                           *ROOT.glob("tests/fixtures/*/project.yaml")]))
def test_existing_projects_clean(path):
    with open(path, encoding="utf-8") as f:
        assert config.check(yaml.safe_load(f) or {}) == []


def test_migrate_old_file():
    old = {"title": "x", "fps": 30}
    new = config.migrate(old)
    assert new == {"title": "x", "fps": 30, "schema_version": 1} and "schema_version" not in old
    assert config.migrate({"schema_version": 1}) == {"schema_version": 1}


def test_migrate_rejects_future_and_garbage():
    with pytest.raises(SystemExit):
        config.migrate({"schema_version": config.SCHEMA_VERSION + 1})
    with pytest.raises(SystemExit):
        config.migrate({"schema_version": "1"})


def test_load_warns_and_keeps_cfg(tmp_path, capsys):
    (tmp_path / "project.yaml").write_text("tts: {backend: fake}\nsubtitle: {enabled: false}\n", encoding="utf-8")
    p = project.load(tmp_path)
    assert "subtitles?" in capsys.readouterr().out
    assert p.cfg["schema_version"] == 1 and p.cfg["subtitles"] == OLD_DEFAULTS["subtitles"]
    assert p.cfg["subtitle"] == {"enabled": False}  # неизвестный ключ не выкидываем: только предупреждаем

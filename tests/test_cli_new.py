"""P1.1 (B1): `new` подставляет тему в project.yaml так, что YAML остаётся валидным при любых кавычках."""
import argparse
import shutil

import pytest
import yaml

from studio import cli
from studio.project import STUDIO_ROOT


@pytest.fixture
def studio_root(tmp_path, monkeypatch):
    shutil.copytree(STUDIO_ROOT / "projects" / "_template", tmp_path / "projects" / "_template")
    monkeypatch.setattr(cli, "STUDIO_ROOT", tmp_path)
    return tmp_path


def new(root, topic, **kw):
    a = argparse.Namespace(topic=topic, slug=kw.get("slug", "t"), format=kw.get("format", "vertical"),
                           duration=kw.get("duration"), lang=kw.get("lang", "en"))
    assert cli.cmd_new(a) == 0
    path = root / "projects" / a.slug / "project.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")), path.read_text(encoding="utf-8")


@pytest.mark.parametrize("topic", ['It\'s "fine": yes', "It's fine", 'Say "no"', "a: b # c", "Тема «ёлка»", "\\path"])
def test_new_topic_quotes(studio_root, topic):
    cfg, _ = new(studio_root, topic)
    assert cfg["topic"] == topic


def test_new_keeps_fields_and_comments(studio_root):
    cfg, text = new(studio_root, "x", format="horizontal", duration=30.0, lang="en")
    assert (cfg["language"], cfg["format"], cfg["target_duration"]) == ("en", "horizontal", 30.0)
    assert "# язык озвучки" in text  # комментарии заготовки на месте

"""P1.1 (B1): `new` подставляет тему в project.yaml так, что YAML остаётся валидным при любых кавычках."""
import argparse
import shutil

import pytest
import yaml

from studio import cli
from studio.commands import new as new_cmd
from studio.project import STUDIO_ROOT


@pytest.fixture
def studio_root(tmp_path, monkeypatch):
    shutil.copytree(STUDIO_ROOT / "projects" / "_template", tmp_path / "projects" / "_template")
    monkeypatch.setattr(new_cmd, "STUDIO_ROOT", tmp_path)
    return tmp_path


def new(root, topic, **kw):
    a = argparse.Namespace(topic=topic, slug=kw.get("slug", "t"), format=kw.get("format", "vertical"),
                           duration=kw.get("duration"), lang=kw.get("lang", "en"), tts=kw.get("tts"))
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


# P1.3 (B3): голос по умолчанию — `--tts` или первый доступный на машине; выбор пишется в project.yaml явно

@pytest.fixture
def machine(studio_root, monkeypatch):
    """Машина без голосов: ни ключа, ни edge_tts, ни RHVoice. Тест включает нужное."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    have = {"root": studio_root, "edge": False}
    monkeypatch.setattr(new_cmd, "_has_edge", lambda: have["edge"])
    return have


def _channel(root):
    (root / "channel").mkdir()
    (root / "channel" / "POSITIONING.md").write_text("x", encoding="utf-8")


def _rhvoice(root):
    (root / "tools" / "rhvoice").mkdir(parents=True)
    (root / "tools" / "rhvoice" / "rhvoice").write_text("", encoding="utf-8")


def test_new_tts_flag(machine):
    cfg, text = new(machine["root"], "x", tts="fake")
    assert cfg["tts"]["backend"] == "fake"
    assert "backend: fake" in text


def test_new_tts_channel_with_key(machine, monkeypatch):
    root = machine["root"]
    _channel(root)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    machine["edge"] = True
    cfg, _ = new(root, "x", lang="en")
    assert cfg["tts"]["backend"] == "elevenlabs"


def test_new_tts_key_but_not_channel_language(machine, monkeypatch):
    root = machine["root"]
    _channel(root)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    machine["edge"] = True
    cfg, _ = new(root, "x", lang="ru")  # канал англоязычный: платный голос сам не выбираем
    assert cfg["tts"]["backend"] == "edge"


def test_new_tts_edge_then_rhvoice(machine):
    root = machine["root"]
    _rhvoice(root)
    machine["edge"] = True
    assert new(root, "x", slug="a")[0]["tts"]["backend"] == "edge"
    machine["edge"] = False
    assert new(root, "x", slug="b")[0]["tts"]["backend"] == "rhvoice"


def test_new_tts_none_available_warns(machine, capsys):
    cfg, _ = new(machine["root"], "x")
    assert cfg["tts"]["backend"] == "rhvoice"
    assert "нет доступного голоса" in capsys.readouterr().out

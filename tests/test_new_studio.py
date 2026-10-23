"""ROADMAP A4: `python -m studio new-studio` — студия из заготовки studios/_template: studio.yaml, бренд-кит, CLAUDE.md,
позиционирование для youtube и проект демо стиля, который проходит validate и `demo --no-render`."""
import shutil

import pytest
import yaml

from conftest import ROOT
from studio import brand, cli, project, workspace
from studio.commands import new_studio
from studio.commands.studios import check


@pytest.fixture
def base(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "projects" / "_template", tmp_path / "projects" / "_template")
    monkeypatch.setattr(workspace, "ROOT", tmp_path)
    with workspace.use(tmp_path):
        yield tmp_path


def _yaml(p):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_template_is_not_a_studio():
    assert "_template" not in [w.id for w in workspace.studios()]
    with pytest.raises(SystemExit):
        workspace.studio("_template")


def test_brand_studio(base, capsys):
    assert cli.main(["new-studio", "acme", "--name", 'Acme: "Coffee" #1', "--lang", "en,ru",
                     "--tts", "fake"]) == 0
    d = base / "studios" / "acme"
    ws = workspace.studio("acme")
    assert [w.id for w in workspace.studios()] == ["default", "acme"]
    cfg = _yaml(d / "studio.yaml")
    assert cfg["name"] == 'Acme: "Coffee" #1' and cfg["kind"] == "brand"
    assert cfg["languages"] == ["en", "ru"] and cfg["platforms"] == ["tiktok", "instagram-reels"]
    assert cfg["defaults"]["format"] == "vertical" and cfg["defaults"]["style"]["brand"] == "brand"
    assert cfg["voices"] == {"en": {"backend": "fake"}, "ru": {"backend": "fake"}}
    assert check(ws) == []
    kit = brand.load(d / "brand")
    assert kit["name"] == 'Acme: "Coffee" #1' and kit["subs"] == "tiktok"
    assert not (d / "channel").exists() and not (d / "demo").exists()
    for sub in ("briefs", "research", "output", "brand/fonts"):
        assert (d / sub).is_dir()
    assert "Acme" in (d / "CLAUDE.md").read_text(encoding="utf-8")
    assert "__" not in (d / "CLAUDE.md").read_text(encoding="utf-8")
    # проект демо: стиль из кита студии, сценарий демо проходит validate, demo создаёт <slug>-demo
    p = d / "projects" / "acme-style"
    pr = project.load(p)
    assert pr.cfg["style"]["kit"]["name"] == kit["name"] and pr.cfg["format"] == "vertical"
    assert _yaml(p / "project.yaml")["title"] == 'Acme: "Coffee" #1 style demo'
    assert cli.main(["demo", "acme-style", "--no-render"]) == 0
    assert cli.main(["validate", "acme-style-demo"]) == 0
    assert "❌" not in capsys.readouterr().out


def test_youtube_studio_with_positioning(base):
    assert cli.main(["new-studio", "deep-sea", "--kind", "youtube", "--lang", "ru", "--tts", "fake"]) == 0
    d = base / "studios" / "deep-sea"
    cfg = _yaml(d / "studio.yaml")
    assert cfg["defaults"]["format"] == "horizontal" and cfg["platforms"] == ["youtube", "youtube-shorts"]
    assert workspace.studio("deep-sea").is_channel()
    assert "deep-sea" in (d / "channel" / "POSITIONING.md").read_text(encoding="utf-8")
    assert brand.load(d / "brand")["subs"] == "karaoke"
    demo = _yaml(d / "projects" / "deep-sea-style" / "demo" / "ch01.yaml")
    assert demo["title"] == "демо стиля"


def test_voice_defaults(base, monkeypatch):
    monkeypatch.setattr("studio.commands.new.default_backend", lambda lang: "edge")
    assert cli.main(["new-studio", "acme", "--lang", "en,ru", "--voice", "en-US-GuyNeural"]) == 0
    v = _yaml(base / "studios" / "acme" / "studio.yaml")["voices"]
    assert v == {"en": {"backend": "edge", "voice": "en-US-GuyNeural"},
                 "ru": {"backend": "edge", "voice": "ru-RU-DmitryNeural"}}
    assert cli.main(["new-studio", "paid", "--tts", "elevenlabs"]) == 0
    v = _yaml(base / "studios" / "paid" / "studio.yaml")["voices"]
    assert v == {"en": {"backend": "elevenlabs", "voice": "env:ELEVENLABS_VOICE_ID"}}  # ID — только в .env


@pytest.mark.parametrize("sid", ["Acme", "default", "-x", "a b"])
def test_bad_id(base, sid):
    with pytest.raises(SystemExit):
        cli.main(["new-studio", sid])


def test_exists(base):
    assert cli.main(["new-studio", "acme", "--tts", "fake"]) == 0
    with pytest.raises(SystemExit, match="Уже есть"):
        cli.main(["new-studio", "acme", "--tts", "fake"])


def test_template_from_repo(base):
    assert new_studio.TEMPLATE == ROOT / "studios" / "_template"  # заготовка — из репозитория, а не из base

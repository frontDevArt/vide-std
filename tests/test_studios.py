"""ROADMAP A1: студии как папки — `default` в корне, `studios/<id>/` со studio.yaml; поиск проекта, цепочка настроек,
`.env` студии с запасным корневым, `--studio`, `new --studio`, `python -m studio studios`."""
import argparse
import os
import shutil

import pytest
import yaml

from conftest import ROOT
from studio import cli, project, workspace

NFTM = ROOT / "studios" / "notes-from-the-mind"


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Корень студии во временной папке: default с заготовкой, студия `acme` (brand) и папка без studio.yaml."""
    shutil.copytree(ROOT / "projects" / "_template", tmp_path / "projects" / "_template")
    acme = tmp_path / "studios" / "acme"
    (acme / "projects").mkdir(parents=True)
    (acme / "studio.yaml").write_text(yaml.safe_dump({
        "name": "Acme", "kind": "brand", "languages": ["en"],
        "defaults": {"language": "en", "format": "square", "tts": {"backend": "fake"}}}), encoding="utf-8")
    (tmp_path / "studios" / "junk").mkdir()  # не студия: нет studio.yaml
    monkeypatch.setattr(workspace, "ROOT", tmp_path)
    with workspace.use(tmp_path):
        yield tmp_path


def _project(root, **cfg):
    shutil.copytree(ROOT / "projects" / "_template", root)
    if cfg:
        y = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8"))
        y.update(cfg)
        (root / "project.yaml").write_text(yaml.safe_dump(y, allow_unicode=True), encoding="utf-8")
    return root


def test_studios_list(base):
    ws = workspace.studios()
    assert [w.id for w in ws] == ["default", "acme"]
    assert ws[1].root == base / "studios" / "acme" and ws[1].name == "Acme" and ws[1].config["kind"] == "brand"
    assert ws[1].tools == base / "tools"  # внешние голоса общие
    assert ws[1].template == base / "projects" / "_template"  # своей заготовки нет — общая
    with pytest.raises(SystemExit, match="junk"):
        workspace.studio("junk")


def test_slug_found_in_any_studio(base):
    p = _project(base / "studios" / "acme" / "projects" / "promo")
    assert project.resolve_project("promo") == p
    assert workspace.owner(p).id == "acme"
    with workspace.use(workspace.studio("acme")):
        assert project.resolve_project("promo") == p
    _project(base / "projects" / "promo")  # тот же slug в default: в default без --studio — свой
    assert project.resolve_project("promo") == base / "projects" / "promo"


def test_slug_strict_inside_named_studio(base):
    _project(base / "projects" / "only-default")
    with workspace.use(workspace.studio("acme")), pytest.raises(SystemExit, match="не найден"):
        project.resolve_project("only-default")


def test_slug_ambiguous_between_studios(base):
    (base / "studios" / "beta").mkdir()
    (base / "studios" / "beta" / "studio.yaml").write_text("kind: client\n", encoding="utf-8")
    for sid in ("acme", "beta"):
        _project(base / "studios" / sid / "projects" / "same")
    with pytest.raises(SystemExit, match="нескольких студиях"):
        project.resolve_project("same")


def test_config_chain_defaults_studio_project(base):
    p = base / "studios" / "acme" / "projects" / "promo"
    p.mkdir()  # project.yaml без языка и голоса — их даёт студия (заготовка пишет их явно)
    (p / "project.yaml").write_text("title: x\ntopic: x\nformat: vertical\n", encoding="utf-8")
    cfg = project.load(p).cfg
    assert cfg["language"] == "en" and cfg["tts"]["backend"] == "fake"  # из studio.yaml
    assert cfg["format"] == "vertical"  # project.yaml главнее studio.yaml
    assert cfg["fps"] == 30  # умолчание движка


def test_env_studio_then_root(base, monkeypatch):
    for k in ("A1_KEY", "A1_ROOT_ONLY"):
        monkeypatch.delenv(k, raising=False)
    (base / ".env").write_text("A1_KEY=root\nA1_ROOT_ONLY=1\n", encoding="utf-8")
    (base / "studios" / "acme" / ".env").write_text("A1_KEY=acme\n", encoding="utf-8")
    workspace.load_env(workspace.studio("acme"))
    assert (os.environ["A1_KEY"], os.environ["A1_ROOT_ONLY"]) == ("acme", "1")


def _new(**kw):
    a = argparse.Namespace(topic="t", slug="t", format=None, duration=None, lang=None, tts="fake", **kw)
    assert cli.cmd_new(a) == 0


def test_new_in_studio_takes_its_defaults(base):
    _new(studio="acme")
    y = yaml.safe_load((base / "studios" / "acme" / "projects" / "t" / "project.yaml").read_text(encoding="utf-8"))
    assert (y["language"], y["format"]) == ("en", "square")
    assert workspace.current().root == base  # студия переключалась только на время new


def test_new_default_studio_unchanged(base):
    _new()
    y = yaml.safe_load((base / "projects" / "t" / "project.yaml").read_text(encoding="utf-8"))
    assert (y["language"], y["format"]) == ("ru", "vertical")


def test_cli_studio_flag(base, capsys):
    assert cli.main(["--studio", "acme", "studios"]) == 0
    out = capsys.readouterr().out
    assert "* acme" in out and "  default" in out
    with pytest.raises(SystemExit):
        cli.main(["--studio", "nope", "studios"])


def test_studios_warns_on_bad_kind(base, capsys):
    (base / "studios" / "acme" / "studio.yaml").write_text("kind: shop\ndefaults: {fsp: 30}\n", encoding="utf-8")
    cli.main(["studios"])
    out = capsys.readouterr().out
    assert "kind: 'shop'" in out and "fsp" in out


# Репозиторий: Notes From The Mind перенесена в studios/ (готово, если: `studios` показывает 2 студии, fake-discounts
# находится по slug без --studio, конфиг из studio.yaml не меняет его project.yaml)

def test_repo_has_two_studios(capsys):
    assert [w.id for w in workspace.studios()][:2] == ["default", "notes-from-the-mind"]
    assert cli.main(["studios"]) == 0
    out = capsys.readouterr().out
    assert "notes-from-the-mind" in out and "fake-discounts" in out


def test_repo_fake_discounts_moved():
    p = project.resolve_project("fake-discounts")
    assert p == NFTM / "projects" / "fake-discounts"
    assert workspace.owner(p).id == "notes-from-the-mind" and workspace.owner(p).is_channel()
    assert not (ROOT / "channel").exists() and not (ROOT / "briefs").exists()


def test_repo_nftm_defaults_do_not_change_fake_discounts():
    """defaults студии ⊆ project.yaml fake-discounts с теми же значениями: ключ кэша TTS прежний. Исключение —
    бренд-кит (A2, style.brand): тот же lab данными, кадры те же, ключ рендера — новый (правило 6)."""
    import copy
    from studio.config import deep_merge
    d = copy.deepcopy(workspace.owner(NFTM / "projects" / "fake-discounts").config["defaults"])
    assert d["style"].pop("brand") == "brand"
    user = yaml.safe_load((NFTM / "projects" / "fake-discounts" / "project.yaml").read_text(encoding="utf-8"))
    assert deep_merge(d, user) == deep_merge({}, user)

"""P5.3: справочник шаблонов в docs/SCENE_SPEC.md генерируется из метаданных и не расходится с кодом."""
from pathlib import Path

import pytest

from studio import cli
from studio.packs import REGISTRY, P, reference
from studio.packs.lab.base import LabTemplate

SPEC = Path(__file__).resolve().parents[1] / "docs" / "SCENE_SPEC.md"


def test_scene_spec_block_matches_code():
    block = reference.block_of(SPEC.read_text(encoding="utf-8"))
    assert block is not None, "в SCENE_SPEC.md нет маркеров блока шаблонов"
    assert block == reference.markdown(REGISTRY), \
        "справочник шаблонов в SCENE_SPEC.md устарел: python -m studio templates --md --write"


def test_every_builtin_template_documented():
    md = reference.markdown(REGISTRY)
    for name, cls in REGISTRY.templates().items():
        if name.startswith("project."):
            continue
        assert f"\n### {name}\n" in md
        for k in cls.PARAMS:
            assert f"`{k}`" in md


def test_common_params_listed_once():
    md = reference.markdown(REGISTRY)
    assert md.count("| `neuron` |") == 1  # общий параметр lab — одной таблицей, не в каждом шаблоне
    assert "### Общие параметры `LabTemplate`" in md


def test_cells_escaped():
    assert reference._cell("a|b *x*") == "a\\|b \\*x\\*"
    assert reference._code("A|B") == "`'A\\|B'`"
    assert reference._summary("Ценник; опц. чек. Дальше.") == "Ценник; опц. чек."


def test_replace_block_roundtrip():
    text = f"x\n{reference.BEGIN}\nold\n{reference.END}\ny\n"
    new = reference.replace_block(text, "new\n")
    assert reference.block_of(new) == "new\n"
    assert new.startswith("x\n") and new.endswith(f"{reference.END}\ny\n")
    with pytest.raises(ValueError):
        reference.replace_block("без маркеров", "new\n")


def test_cli_md(capsys):
    assert cli.main(["templates", "--md"]) == 0
    assert capsys.readouterr().out == reference.markdown(REGISTRY)


def test_cli_write_requires_md(capsys):
    assert cli.main(["templates", "--write"]) == 2
    assert "--md" in capsys.readouterr().out


def test_common_detected_by_identity():
    class Fake:
        COMMON = LabTemplate.COMMON
        PARAMS = {"own": P(1), "chrome": LabTemplate.COMMON["chrome"], "keep": P([])}
    assert reference._common(Fake) == ["chrome"]  # переопределённый keep — свой параметр

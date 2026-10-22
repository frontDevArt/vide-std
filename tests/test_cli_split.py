"""P2.3: cli.py распилен на studio/commands/<команда>.py + studio/validate.py; интерфейс CLI прежний."""
import argparse

import pytest

from studio import cli, commands
from studio.project import STUDIO_ROOT


def parser():
    p = argparse.ArgumentParser(prog="python -m studio")
    sp = p.add_subparsers(dest="cmd", required=True)
    for name in commands.NAMES:
        commands.module(name).add(sp)
    return p, sp


def test_every_command_module_has_add_and_run():
    _, sp = parser()
    assert list(sp.choices) == list(commands.NAMES)  # имя модуля = имя подкоманды, порядок как в --help


@pytest.mark.parametrize("name", commands.NAMES)
def test_old_cmd_names(name):
    assert getattr(cli, f"cmd_{name}") is commands.module(name).run


def test_unknown_attr():
    with pytest.raises(AttributeError):
        cli.cmd_nope  # noqa: B018


# прежние флаги: argv → значения (команды и флаги только добавляются, не переименовываются)
ARGV = [
    (["doctor", "--lang", "en"], {"lang": "en"}),
    (["new", "t", "--slug", "s", "--format", "square", "--duration", "30", "--lang", "en", "--tts", "fake"],
     {"topic": "t", "slug": "s", "format": "square", "duration": 30.0, "lang": "en", "tts": "fake"}),
    (["validate", "p"], {"project": "p"}),
    (["voice", "p", "--yes"], {"project": "p", "yes": True}),
    (["stills", "p", "--chapter", "ch01", "--times", "1,2"], {"chapter": "ch01", "times": "1,2"}),
    (["render", "p", "--chapter", "ch02", "--workers", "3", "--force"], {"chapter": "ch02", "workers": 3, "force": True}),
    (["assemble", "p", "--allow-stale"], {"allow_stale": True}),
    (["qa", "p", "--fast"], {"fast": True}),
    (["all", "p", "--workers", "2", "--fast", "--yes"], {"workers": 2, "fast": True, "yes": True}),
    (["status"], {"project": None}),
    (["templates", "p"], {"project": "p"}),
    (["frame", "p", "1.5", "--out", "x.png"], {"t": 1.5, "out": "x.png"}),
    (["demo", "p", "--no-render", "--workers", "1", "--yes"], {"no_render": True, "workers": 1, "yes": True}),
    (["selftest", "--full", "--keep", "--workers", "4"], {"full": True, "keep": True, "workers": 4}),
]


@pytest.mark.parametrize("argv,want", ARGV, ids=[a[0] for a, _ in ARGV])
def test_flags(argv, want):
    a = parser()[0].parse_args(argv)
    assert a.cmd == argv[0]
    assert {k: getattr(a, k) for k in want} == want


def test_file_sizes():
    # строка «Этап 2 готов»: cli.py не длиннее 400 строк
    assert len((STUDIO_ROOT / "studio" / "cli.py").read_text(encoding="utf-8").splitlines()) <= 400

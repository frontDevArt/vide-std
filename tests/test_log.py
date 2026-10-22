"""P2.7: вывод команды — в консоль как раньше и в projects/<slug>/logs/<команда>-<время>.log."""
import sys

import pytest

from conftest import make_gallery
from studio import cli, log


def logs(root, cmd):
    return sorted((root / "logs").glob(f"{cmd}-*.log"))


def test_project_command_log_equals_console(tmp_path, capsys):
    root = make_gallery(tmp_path / "g")
    assert cli.main(["validate", str(root)]) == 0
    out = capsys.readouterr().out
    [p] = logs(root, "validate")
    text = p.read_text(encoding="utf-8")
    assert out and out in text  # всё, что ушло в консоль, есть в логе
    assert text.startswith(f"# python -m studio validate {root}\n")
    assert sys.stdout is not None and not isinstance(sys.stdout, log.Tee)  # потоки восстановлены


def test_read_only_commands_have_no_log(tmp_path, capsys):
    root = make_gallery(tmp_path / "g")
    cli.main(["status", str(root)])
    cli.main(["templates", str(root)])
    assert not (root / "logs").exists()


def test_no_project_goes_to_root_logs(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(["validate", str(tmp_path / "nope")])
    [p] = sorted(log.ROOT_LOGS.glob("validate-*.log"))
    assert "Проект не найден" in p.read_text(encoding="utf-8")


def test_traceback_logged_and_reraised(tmp_path):
    with pytest.raises(ZeroDivisionError):
        with log.session("boom", tmp_path):
            print("до ошибки")
            1 / 0
    [p] = logs(tmp_path, "boom")
    text = p.read_text(encoding="utf-8")
    assert "до ошибки" in text and "ZeroDivisionError" in text


def test_same_second_and_prune(tmp_path, monkeypatch):
    monkeypatch.setattr(log, "KEEP", 3)
    for i in range(5):
        with log.session("x", tmp_path) as p:
            print(i)
    kept = logs(tmp_path, "x")
    assert len(kept) == 3
    assert sorted(p.read_text(encoding="utf-8").split("\n")[2] for p in kept) == ["2", "3", "4"]

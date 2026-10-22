"""P2.8: пути данных студии — только из studio/workspace.py; по умолчанию раскладка прежняя (корень студии)."""
import ast
import re
import shutil

import pytest

from conftest import ROOT
from studio import project, workspace

STUDIO = ROOT / "studio"


def test_default_layout_is_studio_root():
    ws = workspace.current()
    assert workspace.ROOT == project.STUDIO_ROOT == ROOT
    assert (ws.projects, ws.channel, ws.briefs, ws.research, ws.env, ws.tools) == (
        ROOT / "projects", ROOT / "channel", ROOT / "briefs", ROOT / "research", ROOT / ".env", ROOT / "tools")
    assert ws.template == ROOT / "projects" / "_template" and ws.project("x") == ROOT / "projects" / "x"


def test_no_data_paths_outside_workspace():
    """`STUDIO_ROOT / "projects"` и подобное склеивает только workspace.py."""
    pat = re.compile(r'(ROOT|parent\.parent)\s*/\s*"(projects|channel|briefs|research|logs|tools|\.env)"')
    bad = [f"{f.relative_to(ROOT)}:{i}" for f in STUDIO.rglob("*.py") if f.name != "workspace.py"
           for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
           if pat.search(line) and not line.lstrip().startswith("#")]
    assert bad == []


def test_workspace_imports_nothing_from_studio():
    tree = ast.parse((STUDIO / "workspace.py").read_text(encoding="utf-8"))
    mods = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert all(n.level == 0 for n in ast.walk(tree) if isinstance(n, ast.ImportFrom))
    assert not [m for m in mods if m.startswith("studio")]


def test_use_switches_projects(tmp_path):
    shutil.copytree(ROOT / "projects" / "_template", tmp_path / "projects" / "demo-slug")
    with workspace.use(tmp_path) as ws:
        assert ws.projects == tmp_path / "projects"
        assert project.resolve_project("demo-slug") == tmp_path / "projects" / "demo-slug"
        assert project.load("demo-slug").root == tmp_path / "projects" / "demo-slug"
        assert not ws.is_channel()
    assert workspace.current().projects == ROOT / "projects"  # восстановлено
    with pytest.raises(SystemExit):
        project.resolve_project("demo-slug")


def test_use_overrides_one_path(tmp_path):
    with workspace.use(workspace.current(), logs=tmp_path) as ws:
        assert ws.logs == tmp_path and ws.projects == ROOT / "projects"


def test_load_env_from_workspace(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("# c\nP28_A=1\nP28_B='two'\nP28_EMPTY=\nP28_SET=new\n", encoding="utf-8")
    for k in ("P28_A", "P28_B", "P28_EMPTY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("P28_SET", "old")
    with workspace.use(tmp_path):
        workspace.load_env()
    import os
    assert (os.environ["P28_A"], os.environ["P28_B"], os.environ["P28_SET"]) == ("1", "two", "old")
    assert "P28_EMPTY" not in os.environ


def test_tts_load_env_is_old_name():
    from studio import tts
    assert tts.load_env is workspace.load_env

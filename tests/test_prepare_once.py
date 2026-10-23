"""P3.5: `prepare()` один раз на команду — внутри `render.prepare_once()` результат считается один раз на (проект, draft),
вне его — каждый вызов заново (тесты правят код и стиль между вызовами)."""
from types import SimpleNamespace

import pytest

from conftest import make_gallery
from studio import audio, cli, project, render, timing


@pytest.fixture(scope="module")
def voiced(tmp_path_factory):
    proj = project.load(make_gallery(tmp_path_factory.mktemp("once") / "gallery", "vertical"))
    timing.layout(proj, log=lambda *_: None)
    return proj


@pytest.fixture
def computed(monkeypatch):
    """Сколько раз prepare посчитал по-настоящему: [(проект, draft)]."""
    calls = []
    real = render._prepare

    def spy(proj, draft=False):
        calls.append((proj.root, draft))
        return real(proj, draft)
    monkeypatch.setattr(render, "_prepare", spy)
    return calls


def test_without_scope_every_call_computes(voiced, computed):
    render.prepare(voiced)
    render.prepare(voiced)
    assert len(computed) == 2


def test_scope_computes_once_and_returns_same(voiced, computed):
    ref, rctx = render._prepare(voiced)
    with render.prepare_once():
        a, actx = render.prepare(voiced)
        b, bctx = render.prepare(voiced)
    assert len(computed) == 2  # ref + один раз в scope
    assert a == b == ref
    assert {k: v for k, v in actx.items() if k != "style"} == {k: v for k, v in rctx.items() if k != "style"}
    assert render._ONCE is None  # кэш живёт только в scope


def test_scope_returns_copies(voiced, computed):
    with render.prepare_once():
        a, ctx = render.prepare(voiced)
        a["scenes"][0]["key"] = "испорчено"
        a["scenes"][0]["state_in"]["feed_offset"] = 99.0
        ctx["W"] = 1
        b, bctx = render.prepare(voiced)
    assert b["scenes"][0]["key"] != "испорчено" and b["scenes"][0]["state_in"]["feed_offset"] != 99.0
    assert bctx["W"] != 1 and len(computed) == 1


def test_draft_cached_separately(voiced, computed):
    with render.prepare_once():
        full, _ = render.prepare(voiced)
        draft, dctx = render.prepare(voiced, draft=True)
        render.prepare(voiced, draft=True)
    assert computed == [(voiced.root, False), (voiced.root, True)]
    assert full["scenes"][0]["key"] != draft["scenes"][0]["key"] and dctx["preset"] == render.DRAFT_PRESET


def test_changed_inputs_recompute(tmp_path, computed):
    # voice внутри одной команды (`all`) переписывает timeline.json, правка cfg в процессе — тоже новые входы
    proj = project.load(make_gallery(tmp_path / "g", "square"))
    timing.layout(proj, log=lambda *_: None)
    with render.prepare_once():
        render.prepare(proj)
        proj.cfg["render"]["crf"] = proj.cfg["render"]["crf"] + 1
        k2 = render.prepare(proj)[0]["scenes"][0]["key"]
        tl = proj.build / "timeline.json"
        tl.write_text(tl.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        k3 = render.prepare(proj)[0]["scenes"][0]["key"]
    assert len(computed) == 3 and k2 == k3


def test_sfx_events_reuse_prepare(voiced, computed):
    # assemble: prepare + mix → sfx_events (свой prepare) — в одной команде считается один раз
    with render.prepare_once():
        tl, _ = render.prepare(voiced)
        ev = audio.sfx_events(voiced, tl)
    assert len(computed) == 1
    assert ev == audio.sfx_events(voiced, tl)  # вне scope — тот же результат


def test_cli_command_runs_in_scope(voiced, computed):
    def run(a):
        render.prepare(voiced)
        render.prepare(voiced)
        return 0
    assert cli._run(SimpleNamespace(run=run), SimpleNamespace()) == 0
    assert len(computed) == 1 and render._ONCE is None

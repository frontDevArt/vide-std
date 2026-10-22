"""P2.6: прогресс и кривые в studio/anim.py; gfx.prog и motion.prog — алиасы; пакет lab без циклов импорта."""
import pytest

from studio import anim as A, codehash as C, gfx, lab, motion


def test_span_and_ramp_semantics():
    # span — конец отрезка, ramp — длительность: одинаковый вызов (t, 1, 3) даёт разное
    assert A.span(2, 1, 3) == 0.5
    assert A.ramp(2, 1, 3) == pytest.approx(1 / 3)
    assert A.span(0, 1, 3) == 0.0 and A.span(9, 1, 3) == 1.0
    assert A.ramp(0, 1, 3) == 0.0 and A.ramp(9, 1, 3) == 1.0
    # вырожденные: ступенька в начале
    assert (A.span(0.9, 1, 1), A.span(1, 1, 1)) == (0.0, 1.0)
    assert (A.ramp(0.9, 1, 0), A.ramp(1, 1, 0)) == (0.0, 1.0)


def test_old_names_are_aliases():
    assert gfx.prog is A.span and motion.prog is A.ramp
    for name in ("clamp", "lerp", "eo", "eio", "eob", "ei"):
        assert getattr(gfx, name) is getattr(A, name), name
    for name in ("clamp", "lerp", "ease_out_expo", "ease_in_out", "ease_in", "spring"):
        assert getattr(motion, name) is getattr(A, name), name
    assert motion._bezier is A.bezier
    assert lab.trigger_errors.__module__ == "studio.packs.lab.check"


def test_curves_ends():
    for f in (A.eo, A.eio, A.eob, A.ei, A.ease_out_expo, A.ease_in_out, A.ease_in, A.spring):
        assert f(0) == pytest.approx(0, abs=1e-9) and f(1) == pytest.approx(1), f
    assert A.eob(0.6) > 1 and max(A.spring(x / 100) for x in range(100)) > 1.05  # перелёт


def _cycles(files):
    g = {C._module_name(f): set(C._imports(str(f), f.stat().st_mtime_ns)) for f in files}
    out = []

    def walk(n, path):
        for m in g.get(n, ()):
            if m in path:
                out.append(path[path.index(m):])
            elif m in g:
                walk(m, path + [m])
    for n in g:
        walk(n, [n])
    return out


def test_no_import_cycles_in_drawing_code():
    # __init__.py пакетов импортируют свои модули по построению — их не считаем
    files = [f for f in C.STUDIO.rglob("*.py") if f.name != "__init__.py"
             and f.stem not in ("project", "tts")]  # project → tts (ленивый load_env) — P2.8
    assert _cycles(files) == []

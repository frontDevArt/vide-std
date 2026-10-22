"""P0.3: motion — CSS cubic-bezier и пружина (STYLE §6)."""
import pytest

from studio import motion as M

GRID = [i / 200 for i in range(201)]


def _reference(p1x, p1y, p2x, p2y, x, n=20000):
    """Независимая сверка: плотная выборка параметрической кривой + линейная интерполяция."""
    def b(a1, a2, u):
        return 3 * a1 * u * (1 - u) ** 2 + 3 * a2 * u * u * (1 - u) + u ** 3
    prev = (0.0, 0.0)
    for i in range(1, n + 1):
        u = i / n
        cur = (b(p1x, p2x, u), b(p1y, p2y, u))
        if cur[0] >= x:
            k = (x - prev[0]) / (cur[0] - prev[0]) if cur[0] > prev[0] else 0.0
            return prev[1] + (cur[1] - prev[1]) * k
        prev = cur
    return 1.0


@pytest.mark.parametrize("f, pts", [
    (M.ease_out_expo, (0.16, 1, 0.3, 1)),
    (M.ease_in_out, (0.65, 0, 0.35, 1)),
    (M.ease_in, (0.7, 0, 0.84, 0)),
])
def test_bezier_matches_css(f, pts):
    for x in GRID:
        assert f(x) == pytest.approx(_reference(*pts, x), abs=1e-3), x


@pytest.mark.parametrize("f", [M.ease_out_expo, M.ease_in_out, M.ease_in])
def test_bezier_ends_clamp_monotonic(f):
    assert f(0) == 0.0 and f(1) == 1.0 and f(-3) == 0.0 and f(7) == 1.0
    ys = [f(x) for x in GRID]
    assert all(b >= a - 1e-9 for a, b in zip(ys, ys[1:]))


def test_bezier_known_values():
    # якоря: кривая поменялась — поменялось движение всех роликов
    assert M.ease_out_expo(0.5) == pytest.approx(0.97178, abs=1e-5)
    assert M.ease_in_out(0.25) == pytest.approx(0.07080, abs=1e-5)
    assert M.ease_in(0.5) == pytest.approx(0.02822, abs=1e-5)
    assert M._bezier(0, 0, 1, 1)(0.37) == pytest.approx(0.37, abs=1e-6)  # линейная


def test_ease_in_out_symmetric():
    for x in GRID:
        assert M.ease_in_out(x) + M.ease_in_out(1 - x) == pytest.approx(1.0, abs=1e-4)


def test_spring():
    assert M.spring(0) == 0.0 and M.spring(-1) == 0.0 and M.spring(1) == 1.0 and M.spring(2) == 1.0
    ys = [M.spring(x) for x in GRID]
    peak = max(ys)
    # перелёт ~10 % в первой половине (докстринг говорит «≈108 % около 0,45»; фактически 110,6 % около 0,36)
    assert 1.10 < peak < 1.11
    assert 0.33 < GRID[ys.index(peak)] < 0.38
    assert abs(M.spring(0.995) - 1) < 0.01  # к концу затухла: без скачка на x = 1


def test_prog_and_clamp():
    assert M.clamp(-1) == 0.0 and M.clamp(2) == 1.0 and M.clamp(5, 0, 10) == 5
    assert M.prog(1.5, 1.0, 1.0) == 0.5 and M.prog(0, 1, 1) == 0.0 and M.prog(9, 1, 1) == 1.0
    assert M.prog(1.0, 1.0, 0) == 1.0 and M.prog(0.99, 1.0, 0) == 0.0  # нулевая длительность — ступенька
    assert M.fr(M.F_LEAD) == pytest.approx(4 / 30)

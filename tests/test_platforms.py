"""ROADMAP B1: профили площадок — `python -m studio platforms`, `platform:` в project.yaml, validate по площадке,
qa готового файла по профилю, безопасная зона площадки с её интерфейсом, `new --platform`, проверки `studios`."""
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import ROOT, make_gallery
from studio import assemble, cli, config, platforms, project, qa, render, safezone, timing, validate, workspace
from studio.commands.studios import check as check_studio

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"
quiet = lambda *_a, **_k: None  # noqa: E731


def _proj(dst, **cfg):
    shutil.copytree(FIXTURE, dst)
    p = dst / "project.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data.update(cfg)
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return project.load(dst)


# --- профили ----------------------------------------------------------------------------------------------------

def test_initial_set():
    assert list(platforms.PLATFORMS) == ["youtube", "youtube-shorts", "tiktok", "instagram-reels", "instagram-feed",
                                         "square", "ad-6", "ad-15", "ad-30"]


@pytest.mark.parametrize("p", platforms.PLATFORMS.values(), ids=lambda p: p.id)
def test_profile_sane(p):
    assert p.formats and all(platforms.size(f) for f in p.formats)
    assert p.min_dur is None or p.max_dur is None or p.min_dur < p.max_dur
    z = p.safe
    assert all(0 <= x < 0.5 for x in (z.top, z.bottom, z.left, z.right))
    for u in p.ui:
        x0, y0, x1, y1 = u.box
        assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
    assert p.source and p.note
    assert all(48000 % f == 0 for f in p.fps)  # студия рендерит только делители 48000 (project.load)


def test_known_limits():
    # сверено с документацией 2026-10-23 (studio/platforms.py): Shorts и Reels — до 3 мин, реклама — по длине
    P = platforms.PLATFORMS
    assert P["youtube-shorts"].max_dur == 180 and P["youtube-shorts"].formats == ("vertical", "square")
    assert P["instagram-reels"].max_dur == 180
    assert (P["instagram-reels"].safe.top, P["instagram-reels"].safe.bottom) == (0.14, 0.35)
    assert [P[f"ad-{n}"].max_dur for n in (6, 15, 30)] == [6, 15, 30]
    assert P["youtube"].burn_subs is False and P["tiktok"].burn_subs is True
    assert platforms.size("portrait") == (1080, 1350)


def test_get_suggests():
    with pytest.raises(KeyError, match="tiktok"):
        platforms.get("tiktk")


def test_command_table(capsys):
    assert cli.main(["platforms"]) == 0
    out = capsys.readouterr().out
    for pid in platforms.PLATFORMS:
        assert f"\n{pid} " in out
    assert "9:16 1080×1920" in out and "4:5 1080×1350" in out and "≤ 3 мин" in out


def test_command_detail(capsys):
    assert cli.main(["platforms", "instagram-reels"]) == 0
    out = capsys.readouterr().out
    assert "14/35/6/6 %" in out and "источник:" in out and "сверено" in out
    assert cli.main(["platforms", "tiktk"]) == 2
    assert "может быть, tiktok" in capsys.readouterr().out


def test_schema_knows_platform():
    assert config.check({"platform": "tiktok"}) == []
    assert config.check({"platform": None}) == []
    assert "platform" not in config.DEFAULTS  # без ключа — проверки по площадке нет


# --- validate ---------------------------------------------------------------------------------------------------

def test_validate_platform(tmp_path):
    rep = validate.check(_proj(tmp_path / "ok", platform="tiktok"))
    assert not [e for e in rep.errs if "platform" in e]
    rep = validate.check(_proj(tmp_path / "fmt", platform="youtube-shorts", format="horizontal"))
    assert any("youtube-shorts — формат horizontal не подходит, нужен vertical или square" in e for e in rep.errs)
    rep = validate.check(_proj(tmp_path / "typo", platform="tiktk"))
    assert any("нет площадки 'tiktk'" in e for e in rep.errs)
    rep = validate.check(_proj(tmp_path / "long", platform="ad-6", format="square", target_duration=10))
    assert any("ad-6 — длительность 10 c больше предела площадки 6 c" in w for w in rep.warns)
    rep = validate.check(_proj(tmp_path / "none"))
    assert not [x for x in rep.errs + rep.warns if "platform" in x]


# --- qa готового файла ------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built(tmp_path_factory):
    dst = tmp_path_factory.mktemp("pf") / "p"
    _proj(dst, format="horizontal")
    scenes = [{"id": "s01", "template": "statement", "params": {"text": "Habit"},
               "lines": ["People say | it takes three weeks to build a habit."]},
              {"id": "s02", "template": "statement", "params": {"text": "Myth"},
               "lines": ["Sixty-six days, on average. | The verdict: myth."]}]
    (dst / "script" / "ch01.yaml").write_text(yaml.safe_dump({"chapter": "ch01", "title": "pf", "scenes": scenes}),
                                             encoding="utf-8")
    proj = project.load(dst)
    timing.layout(proj, log=quiet)
    render.render(proj, workers=2, log=quiet)
    assemble.assemble(proj, log=quiet)
    return proj


def _qa(proj, pid):
    proj.cfg["platform"] = pid
    try:
        ok = qa.run(proj, log=quiet, fast=True)
    finally:
        proj.cfg.pop("platform")
    return ok, (proj.qa_dir / "report.md").read_text(encoding="utf-8")


def test_qa_youtube_passes(built):
    ok, rep = _qa(built, "youtube")
    assert ok
    for name in ("кадр", "FPS", "длительность", "кодеки"):
        assert f"✅ Площадка youtube: {name}" in rep
    assert "✅ Площадка youtube: громкость" in rep  # −16 LUFS тише нормы −14: площадка не поднимет, но и не режет
    assert "Площадка youtube: субтитры" not in rep  # YouTube — субтитры файлом


def test_qa_wrong_frame_fails(built):
    ok, rep = _qa(built, "youtube-shorts")
    assert not ok
    assert "❌ Площадка youtube-shorts: кадр — 1920×1080 (нужно 9:16, 1:1)" in rep


def test_qa_too_long_for_ad(built):
    ok, rep = _qa(built, "ad-6")
    assert not ok and "❌ Площадка ad-6: длительность" in rep and "✅ Площадка ad-6: кадр" in rep


def test_qa_without_platform_unchanged(built):
    assert qa.run(built, log=quiet, fast=True)
    assert "Площадка" not in (built.qa_dir / "report.md").read_text(encoding="utf-8")


def test_qa_bitrate_and_subs_warn_only(built):
    built.cfg["subtitles"]["enabled"] = False
    try:
        ok, rep = _qa(built, "ad-15")
    finally:
        built.cfg["subtitles"]["enabled"] = True
    assert "Площадка ad-15: битрейт" in rep
    assert "⚠️ Площадка ad-15: субтитры" in rep
    assert "❌ Площадка ad-15" not in rep.replace("❌ Площадка ad-15: длительность", "")  # битрейт и субтитры — ⚠️


# --- безопасная зона площадки -----------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def vertical(tmp_path_factory):
    root = make_gallery(tmp_path_factory.mktemp("pfz") / "vertical", "vertical")
    proj = project.load(root)
    timing.layout(proj, log=quiet)
    return proj


def test_zone_without_platform(vertical):
    need, ui = safezone.zone(vertical)
    assert set(need.values()) == {0.04} and ui == ()


def test_zone_of_platform(vertical):
    vertical.cfg["platform"] = "tiktok"
    try:
        need, ui = safezone.zone(vertical)
        issues = safezone.scan(vertical)
    finally:
        vertical.cfg.pop("platform")
    assert need == {"left": 0.05, "top": 0.08, "right": 0.05, "bottom": 0.2} and ui[0].name == "колонка кнопок справа"
    assert safezone.scan(vertical) == []  # поля 4 % — чисто
    assert issues == []  # зона площадки строже, но lab (B2) и телефонные шаблоны (B2.1) свёрстаны в ней


def test_ui_hit_message():
    from studio.platforms import UI
    col = UI("колонка кнопок справа", (0.86, 0.35, 1.0, 0.80))
    assert safezone._hits((900, 800, 1000, 900), col, 1080, 1920)      # правый край 1000 > 0,86 × 1080
    assert not safezone._hits((100, 800, 900, 900), col, 1080, 1920)   # левее колонки
    assert not safezone._hits((900, 100, 1000, 300), col, 1080, 1920)  # выше колонки
    i = {"chapter": "ch01", "id": "s01", "template": "x", "margins": {"left": 0.1, "top": 0.1, "right": 0.02, "bottom": 0.5},
         "bad": ["справа"], "ui": [col.name], "need": {"left": 0.05, "top": 0.08, "right": 0.05, "bottom": 0.2}}
    m = safezone.message(i)
    assert "справа 2 % из 5 %" in m and "под интерфейсом площадки — колонка кнопок справа" in m


def test_qa_check_label(vertical):
    res = []
    vertical.cfg["platform"] = "youtube-shorts"
    try:
        safezone.qa_check(vertical, lambda st, name, det: res.append((st, name, det)))
    finally:
        vertical.cfg.pop("platform")
    (st, name, det), = res
    assert (st, name) == ("PASS", "Контент в безопасной зоне")  # с B2.1 и телефон в зоне Shorts
    assert det == "зона youtube-shorts: поля в/н/л/п 8/20/5/5 % + интерфейс"
    vertical.cfg["platform"], vertical.cfg["qa"]["safe_margin"] = "youtube-shorts", 0.3
    try:
        res.clear()
        safezone.qa_check(vertical, lambda st, name, det: res.append((st, name, det)))
    finally:
        vertical.cfg.pop("platform"); vertical.cfg["qa"]["safe_margin"] = 0.04
    (st, name, det), = res
    assert st == "FAIL" and det.startswith("ch")  # нарушение — ❌ с перечнем сцен


def test_subs_check_band_follows_style(monkeypatch):
    from types import SimpleNamespace
    from studio import gfx as G
    monkeypatch.setattr(G.SM, "active", lambda: SimpleNamespace(subs="karaoke"))
    assert qa.subs_top(None, 1080, 1920) == 0.70 and qa.subs_top(None, 1920, 1080) == 0.76  # как до B1
    monkeypatch.setattr(G.SM, "active", lambda: SimpleNamespace(subs="tiktok"))
    assert qa.subs_top(None, 1080, 1920) == 0.52  # TikTok-субтитры стоят на 0,66 высоты — лист их не режет (A4)


# --- new и studios ----------------------------------------------------------------------------------------------

@pytest.fixture
def base(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "projects" / "_template", tmp_path / "projects" / "_template")
    monkeypatch.setattr(workspace, "ROOT", tmp_path)
    with workspace.use(tmp_path):
        yield tmp_path


def _cfg(p):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_new_with_platform(base):
    assert cli.main(["new", "x", "--slug", "yt", "--platform", "youtube", "--tts", "fake", "--lang", "en"]) == 0
    c = _cfg(base / "projects" / "yt" / "project.yaml")
    assert (c["platform"], c["format"]) == ("youtube", "horizontal")  # формат — по площадке
    assert cli.main(["new", "x", "--slug", "feed", "--platform", "instagram-feed", "--tts", "fake"]) == 0
    assert _cfg(base / "projects" / "feed" / "project.yaml")["format"] == "portrait"  # 4:5 (ROADMAP B2)
    assert cli.main(["new", "x", "--slug", "plain", "--tts", "fake"]) == 0
    assert _cfg(base / "projects" / "plain" / "project.yaml")["platform"] is None
    with pytest.raises(SystemExit, match="формат horizontal не подходит"):
        cli.main(["new", "x", "--slug", "bad", "--platform", "tiktok", "--format", "horizontal", "--tts", "fake"])
    with pytest.raises(SystemExit, match="может быть, tiktok"):
        cli.main(["new", "x", "--slug", "typo", "--platform", "tiktk", "--tts", "fake"])


def test_new_studio_rejects_unknown_platform(base):
    with pytest.raises(SystemExit, match="нет площадки 'tik-tok'"):
        cli.main(["new-studio", "acme", "--platforms", "tik-tok", "--tts", "fake"])
    assert not (base / "studios" / "acme").exists()


def test_studios_checks_platforms(base):
    d = base / "studios" / "acme"
    d.mkdir(parents=True)
    (d / "studio.yaml").write_text(yaml.safe_dump({"name": "Acme", "kind": "brand",
                                                   "platforms": ["tiktok", "reels"]}), encoding="utf-8")
    warns = check_studio(workspace.studio("acme"))
    assert any("нет площадки 'reels'" in w for w in warns)
    assert not any("tiktok" in w.split("—")[0] for w in warns)


def test_real_studios_use_known_platforms():
    for ws in workspace.studios():
        assert not [w for w in check_studio(ws) if w.startswith("platforms")], ws.id

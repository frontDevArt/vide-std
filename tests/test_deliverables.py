"""ROADMAP B3: несколько выходов из одного проекта (`deliverables`) — общие сценарий и озвучка, у каждого выхода свои
формат, timeline.json, рендер, QA и финал output/<slug>/<выход>.mp4; субтитры — над нижним полем зоны площадки."""
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image

from studio import cli, config, platforms, project, render, safezone, subs, timing, validate
from studio.packs.commerce.elements import HOLE_Y

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"
quiet = lambda *_a, **_k: None  # noqa: E731


def _proj(dst, **cfg):
    shutil.copytree(FIXTURE, dst)
    p = dst / "project.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data.update(cfg)
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return project.load(dst)


# --- проект и выходы --------------------------------------------------------------------------------------------

def test_schema_knows_deliverables():
    assert config.check({"deliverables": ["youtube", "tiktok"]}) == []
    assert "deliverables" not in config.DEFAULTS


def test_outputs_and_paths(tmp_path):
    proj = _proj(tmp_path / "p", format="horizontal", deliverables=["youtube", "tiktok", "instagram-feed"])
    assert proj.outputs == ["youtube", "tiktok", "instagram-feed"]
    yt, tt, ig = proj.targets()
    assert (yt.cfg["format"], tt.cfg["format"], ig.cfg["format"]) == ("horizontal", "vertical", "portrait")
    assert tt.cfg["platform"] == "tiktok" and tt.size == (1080, 1920) and tt.outputs == []
    assert proj.cfg["format"] == "horizontal" and "platform" not in proj.cfg  # исходный cfg не тронут
    root = tmp_path / "p"
    assert tt.build == root / "build" / "tiktok" and tt.qa_dir == root / "qa" / "tiktok"
    assert tt.bdir("tts") == root / "build" / "tts" == yt.bdir("tts")  # озвучка общая
    assert tt.final_path() == root / "output" / "p" / "tiktok.mp4"  # проект вне projects/ студии
    assert [o.out for o in proj.targets("tiktok")] == ["tiktok"]
    with pytest.raises(SystemExit, match="нет в deliverables"):
        proj.targets("youtube-shorts")


def test_square_kept_where_platform_accepts_it(tmp_path):
    proj = _proj(tmp_path / "p", format="square", deliverables=["youtube-shorts", "tiktok"])
    assert [o.cfg["format"] for o in proj.targets()] == ["square", "vertical"]


def test_without_deliverables_unchanged(tmp_path):
    proj = _proj(tmp_path / "p")
    assert proj.outputs == [] and proj.targets() == [proj]
    assert proj.build == tmp_path / "p" / "build" and proj.final_path() == tmp_path / "p" / "build" / "final" / "p.mp4"


def test_final_in_studio_output(tmp_path, monkeypatch):
    from studio import workspace
    (tmp_path / "projects").mkdir()
    with workspace.use(tmp_path):
        proj = _proj(tmp_path / "projects" / "clip", deliverables=["tiktok"])
        assert proj.output("tiktok").final_path() == tmp_path / "output" / "clip" / "tiktok.mp4"


def test_validate_deliverables(tmp_path):
    rep = validate.check(_proj(tmp_path / "ok", deliverables=["youtube", "tiktok"]))
    assert rep.ok, rep.errs
    rep = validate.check(_proj(tmp_path / "typo", deliverables=["youtube", "tiktk"]))
    assert any("deliverables: нет площадки 'tiktk'" in e for e in rep.errs)
    rep = validate.check(_proj(tmp_path / "ad", format="square", target_duration=10, deliverables=["ad-6"]))
    assert any("ad-6 — длительность 10 c больше предела площадки 6 c" in w for w in rep.warns)


# --- субтитры по зоне площадки ----------------------------------------------------------------------------------

def test_subs_band_without_platform_unchanged(tmp_path):
    proj = _proj(tmp_path / "p", format="vertical")
    assert subs.bottom_limit(proj) is None
    half = subs.font_size(proj) * (2 * 1.2 + 0.8) / 2
    assert subs.band_top(proj) == round(0.835 - half / 1920, 4)  # как до B3
    assert subs.max_width(proj) == int(1080 * 0.86)


def test_subs_above_reels_bottom(tmp_path):
    reels = _proj(tmp_path / "p", format="vertical", deliverables=["instagram-reels"]).output("instagram-reels")
    assert subs.bottom_limit(reels) == 0.65
    half = subs.font_size(reels) * (2 * 1.2 + 0.8) / 2 / 1920
    assert subs.band_top(reels) + 2 * half <= 0.65 + 1e-4
    # нарисованная плашка — выше нижних 35 %
    img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    scene = {"subs": [{"lines": ["Sixty-six days, on average."], "t0": 0.0, "t1": 2.0}], "words": []}
    render.draw_subs(img, scene, 1.0, subs.font_size(reels), 1080, 1920, bottom=subs.bottom_limit(reels))
    assert img.getchannel("A").getbbox()[3] <= 0.65 * 1920


def test_subs_narrower_than_tiktok_buttons(tmp_path):
    tt = _proj(tmp_path / "p", format="vertical", deliverables=["tiktok"]).output("tiktok")
    assert subs.max_width(tt) == int(1080 * (1 - 2 * 0.14))  # колонка кнопок справа — в боковых полях зоны
    assert subs.bottom_limit(tt) == 0.8


# --- сквозной прогон: голос один раз, два выхода -----------------------------------------------------------------

@pytest.fixture(scope="module")
def built(tmp_path_factory):
    dst = tmp_path_factory.mktemp("dl") / "p"
    _proj(dst, format="horizontal", deliverables=["youtube", "instagram-reels"])
    scenes = [{"id": "s01", "template": "statement", "params": {"text": "Habit"},
               "lines": ["People say | it takes three weeks to build a habit."]},
              {"id": "s02", "template": "statement", "params": {"text": "Myth"},
               "lines": ["Sixty-six days, on average. | The verdict: myth."]}]
    (dst / "script" / "ch01.yaml").write_text(yaml.safe_dump({"chapter": "ch01", "title": "dl", "scenes": scenes}),
                                             encoding="utf-8")
    assert cli.main(["voice", str(dst)]) == 0
    assert cli.main(["render", str(dst), "--workers", "2"]) == 0
    assert cli.main(["assemble", str(dst)]) == 0
    return project.load(dst)


def test_voice_once_layout_per_output(built):
    root = built.root
    wavs = sorted(p.name for p in (root / "build" / "tts").glob("*.wav"))
    assert len(wavs) == 2 and not (root / "build" / "youtube" / "tts").exists()
    yt, rl = (timing.load_timeline(o) for o in built.targets())
    assert yt["size"] == [1920, 1080] and rl["size"] == [1080, 1920]
    assert [s["start_frame"] for s in yt["scenes"]] == [s["start_frame"] for s in rl["scenes"]]  # тайминг речи общий
    assert not (root / "build" / "timeline.json").exists()


def test_outputs_assembled_and_qa(built, capsys):
    out = built.root / "output" / "p"
    assert sorted(p.name for p in out.iterdir()) == ["instagram-reels.mp4", "instagram-reels.srt", "instagram-reels.vtt",
                                                    "youtube.mp4", "youtube.srt", "youtube.vtt"]
    assert cli.main(["qa", str(built.root), "--fast"]) == 0
    rep = (built.root / "qa" / "instagram-reels" / "report.md").read_text(encoding="utf-8")
    assert "✅ Площадка instagram-reels: кадр — 1080×1920" in rep and "Итог: **PASS**" in rep
    assert (built.root / "qa" / "youtube" / "report.md").exists()
    assert (built.root / "qa" / "instagram-reels" / "subs_check.png").exists()


def test_out_flag_one_output(built, capsys):
    assert cli.main(["render", str(built.root), "--out", "youtube"]) == 0
    assert "== выход" not in capsys.readouterr().out  # один выход — без заголовков
    with pytest.raises(SystemExit, match="нет в deliverables"):
        cli.main(["render", str(built.root), "--out", "tiktok"])


def test_status_per_output(built, capsys):
    assert cli.main(["status", str(built.root)]) == 0
    out = capsys.readouterr().out
    assert "Выходы youtube 1920×1080, instagram-reels 1080×1920" in out
    assert "✅ 7 Сборка [youtube]" in out and "✅ 7 Сборка [instagram-reels]" in out


def test_frame_deliverable(built, tmp_path):
    png = tmp_path / "f.png"
    assert cli.main(["frame", str(built.root), "1.0", "--out", str(png), "--deliverable", "instagram-reels"]) == 0
    assert Image.open(png).size == (1080, 1920)


# --- commerce в высоком кадре -----------------------------------------------------------------------------------

def test_price_tag_hangs_inside_zone(tmp_path):
    """Бирка висит на гвоздике у верха зоны (верёвка не уходит за кадр) — в 16:9 и в 9:16 зоны TikTok."""
    from studio.packs import REGISTRY
    for fmt, deliv in (("horizontal", "youtube"), ("vertical", "tiktok")):
        o = _proj(tmp_path / fmt, format=fmt, deliverables=[deliv]).output(deliv)
        ctx = {"W": o.size[0], "H": o.size[1], "fps": 30, "language": "en",
               "safe": platforms.layout_zone(o.cfg), "subs_top": subs.band_top(o)}
        sc = {"chapter": "ch01", "id": "s01", "dur": 4.0, "start_frame": 0, "beats": [{"t0": 0.0, "t1": 4.0}],
              "words": [], "params": {"tag": {"was": "$199", "now": "$99", "x": 960, "y": 200, "at": 0},
                                      "receipt": {"lines": [{"text": "A|$1", "at": 0.5}]}}}
        tpl = REGISTRY["commerce.price_tag"](ctx, sc, {})
        tpl.setup()
        for t in (0.0, 0.12, 1.5, 3.5):
            box = safezone.content_box(ctx, tpl, sc, t)
            if box:
                zn, (W, H) = ctx["safe"], o.size  # поля зоны (без запаса 1 % рамки шаблона), как у qa
                assert box[1] >= zn["top"] * H and box[0] >= zn["left"] * W and box[2] <= (1 - zn["right"]) * W,                     (fmt, t, box)
        assert tpl.tag_pose(0.0)[1] == pytest.approx(tpl.pivot_y() + HOLE_Y * tpl.z)  # падает от гвоздика


def test_status_final_outside_project(tmp_path):
    """D2 (найдено на серии): у выхода проекта студии финал — output/<slug>/ в корне студии, вне папки проекта;
    status/batch падали на relative_to."""
    from studio import status, workspace
    with workspace.use(tmp_path):
        proj = _proj(tmp_path / "projects" / "p", deliverables=["tiktok"])
        out = proj.targets()[0]
        fin = out.final_path()
        assert fin == tmp_path / "output" / "p" / "tiktok.mp4"
        fin.write_bytes(b"")
        det = dict((n, d) for n, _, d in status.phases(out))["7 Сборка"]
        assert det == str(Path("output") / "p" / "tiktok.mp4")

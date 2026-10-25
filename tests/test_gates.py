"""ROADMAP D4: ворота качества — бриф avoid / done_means и правила студии (studio.yaml: quality) в validate и qa,
визуальный QA: контраст палитры, мелькание, плотность текста."""
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from studio import assemble, gates, project, qa, render, timing, validate, workspace

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"
quiet = lambda *_a, **_k: None  # noqa: E731


def _write(dst, scenes, studio=None, **cfg):
    """Проект из фикстуры fake_tts; studio — studio.yaml студии-владельца (studios/acme/)."""
    if studio is not None:
        (dst / "studio.yaml").parent.mkdir(parents=True, exist_ok=True)
        (dst / "studio.yaml").write_text(yaml.safe_dump(studio, allow_unicode=True), encoding="utf-8")
        root = dst / "projects" / "p"
    else:
        root = dst / "p"
    shutil.copytree(FIXTURE, root)
    y = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8"))
    y.update(format="horizontal", **cfg)
    (root / "project.yaml").write_text(yaml.safe_dump(y, allow_unicode=True), encoding="utf-8")
    (root / "script" / "ch01.yaml").write_text(
        yaml.safe_dump({"chapter": "ch01", "title": "t", "scenes": scenes}, allow_unicode=True), encoding="utf-8")
    return project.load(root)


def _sc(sid, tpl="statement", lines=("Hello there.",), **params):
    return {"id": sid, "template": tpl, "lines": list(lines), "params": params}


def _errs(proj):
    return validate.check(proj).errs


def test_rules_merge_studio_and_project(tmp_path):
    studio = {"name": "Acme", "kind": "brand", "quality": {
        "avoid": [{"max_words_on_screen": 6}, "стоковые улыбки"], "done_means": [{"logo_in_final": True}]}}
    proj = _write(tmp_path / "studios" / "acme", [_sc("s01", text="Hi")], studio=studio,
                  avoid=[{"max_words_on_screen": 9}, {"words": ["cure"]}],
                  done_means=["каждое слово читается на телефоне", {"logo_in_final": False}])
    rules, eyes, errs = gates.collect(proj)
    assert not errs
    assert rules == {"max_words_on_screen": 9, "words": ["cure"], "logo_in_final": False}  # проект главнее
    assert gates.active(rules) == {"max_words_on_screen": 9, "words": ["cure"]}  # false — выключено
    assert eyes == [("avoid", "стоковые улыбки"), ("done_means", "каждое слово читается на телефоне")]


def test_rule_format_errors(tmp_path):
    proj = _write(tmp_path, [_sc("s01", text="Hi")],
                  avoid=[{"max_word_on_screen": 6}, {"final_hold": 1.5}, {"max_words_on_screen": "six"}, 3],
                  done_means=[{"final_hold": 1.5}])
    errs = _errs(proj)
    assert any("нет правила 'max_word_on_screen' — может, max_words_on_screen?" in e for e in errs)
    assert any("final_hold — правило раздела done_means, а не avoid" in e for e in errs)
    assert any("max_words_on_screen: 'six' — нужно целое" in e for e in errs)
    assert any("avoid: 3 — строка (проверить глазами) или правило" in e for e in errs)
    assert not any(e.startswith("done_means") for e in errs)


def test_max_words_on_screen(tmp_path):
    # критерий D4: нарушение «больше N слов» ловится validate с понятным сообщением
    proj = _write(tmp_path, [_sc("s01", text="Short *line*"),
                             _sc("s02", text="This statement has far too many words on screen", sub="and more")],
                  avoid=[{"max_words_on_screen": 6}])
    errs = _errs(proj)
    bad = [e for e in errs if "слов" in e and "в кадре" in e]
    assert len(bad) == 1 and bad[0].startswith("ch01/s02: в кадре 11 слов (бриф avoid: не больше 6)")
    assert "This statement" in bad[0]


def test_forbidden_words(tmp_path):
    proj = _write(tmp_path, [_sc("s01", lines=["This pill is a | cure."], text="Science"),
                             _sc("s02", lines=["Nothing here."], text="Guaranteed results"),
                             _sc("s03", lines=["Secure the curious cat."], text="Fine")],
                  avoid=[{"words": ["cure", "guaranteed"]}])
    errs = [e for e in _errs(proj) if "в списке avoid" in e]
    assert errs == ["ch01/s01: «cure» — в списке avoid (озвучка: «This pill is a  cure.»)",
                    "ch01/s02: «guaranteed» — в списке avoid (кадр: «Guaranteed results»)"]  # secure/curious — нет


def test_numbers_need_source(tmp_path):
    src = {"label": "STUDY", "text": "Lally et al., 2010"}
    scenes = [
        _sc("s01", "lab_full_number", value=66, caption="days"),                       # ❌ нет источника
        _sc("s02", "lab_full_number", value=66, caption="days", source=src, keep=["source"]),
        _sc("s03", "lab_full_number", value=20, caption="days"),                       # источник пережил склейку
        _sc("s04", "statement", text="Only 1 in 3"),                                   # ❌ цифра в надписи
        {**_sc("s05", "statement", text="Up to 95%"), "cite": "s02"},                  # источник показан в s02
        {**_sc("s06", "statement", text="Up to 9"), "cite": "s04"},                    # ❌ у s04 источника нет
        _sc("s07", "lab_chapter", title="Part 2"),                                     # нумерация глав — не цифра
        _sc("s08", "statement", text="No numbers"),
    ]
    proj = _write(tmp_path, scenes, avoid=[{"numbers_without_source": True}])
    bad = [e for e in _errs(proj) if "источник" in e]
    assert [e.split(":")[0] for e in bad] == ["ch01/s01", "ch01/s04", "ch01/s06"]
    assert "value = 66" in bad[0] and "params.source {label, text} или cite:" in bad[0]
    assert "Only 1 in 3" in bad[1] and "у той сцены нет источника" in bad[2]


def test_studio_rule_from_studio_yaml(tmp_path):
    # критерий D4: правила студии берутся из studio.yaml (канал: «у каждой цифры источник»)
    studio = {"name": "Acme", "kind": "youtube", "quality": {"avoid": [{"numbers_without_source": True}]}}
    proj = _write(tmp_path / "studios" / "acme", [_sc("s01", "lab_full_number", value=7, caption="x")], studio=studio)
    assert proj.ws.id == "acme"
    assert any(e.startswith("ch01/s01: цифры в кадре без источника") for e in _errs(proj))
    proj2 = _write(tmp_path / "solo", [_sc("s01", "lab_full_number", value=7, caption="x")])
    assert not any("источник" in e for e in _errs(proj2))  # без правила — как раньше


def test_logo_and_cta_in_final(tmp_path):
    rules = {"done_means": [{"logo_in_final": True}, {"cta_in_final": True}]}
    plain = _write(tmp_path / "a", [_sc("s01", text="Hi"), _sc("s02", "outro", text="Bye")], **rules)
    errs = _errs(plain)
    assert any(e.startswith("финал (ch01/s01 (core.statement), ch01/s02 (core.outro)) без логотипа") for e in errs)
    assert any("без призыва — done_means: cta_in_final" in e for e in errs)
    good = _write(tmp_path / "b", [_sc("s01", "outro", lines=["Shop now at acme."], text="Shop *now*"),
                                   {**_sc("s02", "media.logo_sting", lines=[], text="ACME"), "min_duration": 1.5}],
                  brief={"cta": "Shop now"}, **rules)
    assert not [e for e in _errs(good) if "финал" in e]
    end = _write(tmp_path / "c", [_sc("s01", "cta_end", title="Thanks", button="Follow")], **rules)
    errs = [e for e in _errs(end) if "финал" in e]
    assert len(errs) == 1 and "без логотипа" in errs[0]  # cta_end без логотипа и бренд-кита — призыв есть, лого нет


def test_final_hold():
    tl = {"scenes": [{"start": 0, "dur": 3.0, "lines": [{"t0": 0.4, "t1": 2.5}]},
                     {"start": 3.0, "dur": 2.0, "lines": [{"t0": 0.2, "t1": 1.4}]}]}
    assert gates.final_hold(tl) == pytest.approx(0.6)
    name, bad = gates.timeline_issue({"final_hold": 1.5}, tl)
    assert name == "Финал держится ≥ 1.5 c" and "держится 0.60 c" in bad[0] and "hold: 1.0" in bad[0]
    assert gates.timeline_issue({"final_hold": 0.5}, tl)[1] == []
    assert gates.timeline_issue({}, tl) is None


def test_palette_contrast():
    from studio import style
    for pal in style.PALETTES:
        assert gates.palette_contrast(style.Style(pal).pal)[0], pal
    for mood in style.MOODS:
        assert gates.palette_contrast(style.Style("lab", mood).pal)[0], mood
    bad = dict(style.PALETTES["lab"], dim=(40, 44, 56))
    ok, det = gates.palette_contrast(bad)
    assert not ok and "dim #282C38" in det and "нужно ≥ 3" in det
    assert gates.contrast((255, 255, 255), (0, 0, 0)) == pytest.approx(21)


def test_flashes_series():
    fps = 30
    calm = [0.1] * 60 + [0.9] * 60 + [0.1] * 60  # две склейки — не вспышки
    assert gates.flashes(calm, fps) <= 1
    strobe = [(0.9 if (i // 3) % 2 else 0.05) for i in range(90)]  # 5 Гц
    assert gates.flashes(strobe, fps) == 5
    soft = [0.3 + (0.05 if (i // 3) % 2 else 0) for i in range(90)]  # перепад < 10 % — не вспышка
    assert gates.flashes(soft, fps) == 0


def test_flash_check_on_video(tmp_path):
    out = tmp_path / "strobe.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=2",
                    "-vf", "geq=lum='if(mod(floor(N/3),2),235,16)':cb=128:cr=128", "-pix_fmt", "yuv420p", str(out)],
                   stdin=subprocess.DEVNULL, check=True)
    ok, det = gates.flash_check(out, 30)
    assert not ok and "5 вспышек" in det


@pytest.fixture
def built(tmp_path):
    def make(scenes, **cfg):
        proj = _write(tmp_path, scenes, music={"enabled": False}, **cfg)
        timing.layout(proj, log=quiet)
        render.render(proj, workers=2, log=quiet)
        assemble.assemble(proj, log=quiet)
        return proj
    return make


def test_qa_report_gates(built):
    proj = built([_sc("s01", text="Habit", lines=["Sixty-six days."]), _sc("s02", text="Done", lines=["Done."])],
                 avoid=["стоковые улыбки", {"max_words_on_screen": 4}],
                 done_means=["каждое слово читается на телефоне", {"final_hold": 5}])
    assert not qa.run(proj, log=quiet, fast=True)  # final_hold 5 c — ❌
    rep = (proj.qa_dir / "report.md").read_text(encoding="utf-8")
    assert "✅ Бриф: не больше 4 слов в кадре — нарушений нет" in rep
    assert "❌ Финал держится ≥ 5 c — финальный кадр держится" in rep
    assert "✅ Контраст текста к фону — худший" in rep
    assert "✅ Без мелькания (≤ 3 вспышек в секунду)" in rep
    assert "Плотность текста в кадре" not in rep  # предел из брифа — своя строка
    assert "## Проверить глазами (бриф и студия)" in rep
    assert "- [ ] Избегать: стоковые улыбки" in rep and "- [ ] Готово, если: каждое слово читается на телефоне" in rep


def test_qa_without_rules_has_visual_checks(built):
    proj = built([_sc("s01", text="Habit", lines=["Sixty-six days."])])
    assert qa.run(proj, log=quiet, fast=True)
    rep = (proj.qa_dir / "report.md").read_text(encoding="utf-8")
    assert "✅ Плотность текста в кадре — до 1 слов в сцене (ch01/s01), предел 20" in rep
    assert "Бриф:" not in rep and "Проверить глазами" not in rep


def test_nftm_studio_rule():
    # канал Notes From The Mind: «у каждой цифры источник» — правило студии в studio.yaml
    ws = workspace.studio("notes-from-the-mind")
    q = ws.config.get("quality") or {}
    assert {"numbers_without_source": True} in q.get("avoid", [])

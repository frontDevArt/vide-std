"""ROADMAP D3: перевод — проект `<исходник>-<язык>` с листом translation.yaml; project.yaml и script/*.yaml перевода —
производные (исходник + лист + overrides); сценарий пишется, только когда лист заполнен и проверки пройдены."""
import pytest
import yaml
from conftest import make_gallery

from studio import cli, config, lang, project, validate
from studio import translate as T


@pytest.fixture
def gallery(tmp_path):
    return make_gallery(tmp_path / "gal")


def _sheet(dst):
    return yaml.safe_load((dst / T.SHEET).read_text(encoding="utf-8"))


def _fill(dst, fn=lambda kind, s: f"ES {s}" if kind != "at" else s):
    """«Перевод» по правилу fn(вид, строка): по умолчанию «ES …» — биты, цифры и слова-триггеры на месте."""
    d = _sheet(dst)
    for e in d["project"]:
        e["es"] = fn("text", e["en"])
    for block in d["scenes"].values():
        for k, lst in block.items():
            for e in lst:
                e["es"] = fn(k, e["en"])
    (dst / T.SHEET).write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return d


def test_kind_of_param_strings():
    assert T.kind(("title",), "Myth on Trial") == "text"
    assert T.kind(("chrome", "steps", 0), "CLAIM") == "text"
    assert T.kind(("labels", 0, "at"), "ritual") == "at"
    assert T.kind(("tag", "strike_at"), "w:cheaper#2") == "at"
    assert T.kind(("at",), "1.5s") is None                              # секунды — не слово
    assert T.kind(("source", "text"), "Juliano & Griffiths, 2004") is None  # источник не переводим
    assert T.kind(("source", "label"), "REVIEW") == "text"
    assert T.kind(("source",), "Lally et al., 2010") is None
    assert T.kind(("study", "authors"), "Rogers et al.") is None
    assert T.kind(("color",), "accent") is None and T.kind(("verdict", "verdict"), "MYTH") is None
    assert T.kind(("chrome", "number"), "№ 01") is None                 # без букв — нечего переводить
    assert T.kind(("caption",), "assets/photo.png") is None


def test_schema_knows_translation():
    assert config.check({"translation": {"source": "x", "from": "en"}}) == []


def test_ui_labels_by_language():
    assert lang.ui("en", "study") == "STUDY" and lang.ui("ru", "study") == "STUDY"  # ru — как до D3 (golden)
    assert lang.ui("es", "study") == "ESTUDIO" and lang.ui("xx", "source") == "SOURCE"
    assert lang.verdict_word("es", "half-true") == "MEDIA VERDAD" and lang.verdict_word("en", "MYTH") == "MYTH"
    assert lang.ui("es", "chapter_of").format(n=2, total=5) == "capítulo 2 de 5"


def test_create_then_apply(gallery, capsys):
    dst = gallery.parent / "gal-es"
    assert cli.main(["translate", str(gallery), "--to", "es"]) == 1  # лист пуст — сценария нет
    assert "осталось" in capsys.readouterr().out
    assert (dst / T.SHEET).exists() and not (dst / "script").exists()
    user = yaml.safe_load((dst / "project.yaml").read_text(encoding="utf-8"))
    assert user["language"] == "es" and user["translation"] == {"source": "gal", "from": "en"}
    assert user["tts"]["voice"] == "auto" and user["tts"]["backend"] == "fake"
    d = _sheet(dst)
    lines = [e["en"] for b in d["scenes"].values() for e in b.get("lines", [])]
    src = project.load(gallery)
    assert len(lines) == sum(len(s.get("lines") or []) for _, c in src.chapters for s in c["scenes"])

    _fill(dst)
    assert cli.main(["translate", str(dst)]) == 0  # по самому переводу
    es = project.load(dst)
    assert es.cfg["language"] == "es" and es.cfg["tts"]["voice"] == "fake"
    assert es.cfg["title"] == "ES gallery fixture"
    pairs = [(a, b) for (_, ca), (_, cb) in zip(src.chapters, es.chapters) for a, b in zip(ca["scenes"], cb["scenes"])]
    assert len(pairs) == sum(len(c["scenes"]) for _, c in src.chapters)
    for a, b in pairs:
        assert b["template"] == a["template"]
        for la, lb in zip(a.get("lines") or [], b.get("lines") or []):
            assert T._lines({"lines": [lb]})[0] == "ES " + T._lines({"lines": [la]})[0]
        for (pa, va), (pb, vb) in zip(T.walk(a.get("params") or {}), T.walk(b.get("params") or {})):
            assert pa == pb
            assert vb == (f"ES {va}" if T.kind(pa, va) == "text" else va)  # числа, источники, триггеры — как были
    assert validate.check(es).ok, validate.check(es).errs


def test_resync_keeps_translations(gallery):
    dst = gallery.parent / "gal-es"
    T.sync(gallery, dst, "es")
    _fill(dst)
    T.sync(gallery, dst)
    s = gallery / "script" / "ch01.yaml"
    text = s.read_text(encoding="utf-8")
    first = yaml.safe_load(text)["scenes"][0]
    old = T._lines(first)[0]
    s.write_text(text.replace(old, old + " Again", 1), encoding="utf-8")
    _, r = T.sync(gallery, dst)
    assert [w for w, _ in r.missing] == [f"ch01/{first['id']}"]   # только изменённая строка
    assert r.total - len(r.missing) > 50


def test_checks(gallery):
    dst = gallery.parent / "gal-es"
    T.sync(gallery, dst, "es")

    def bad(kind, s):
        if kind == "lines":
            return "ES " + s.replace("|", "", 1) if "|" in s else "Сцена " + s
        if kind == "at":
            return "palabra" if any(c.isalpha() for c in s) else s
        return "ES " + "".join("7" if c.isdigit() else c for c in s)
    _fill(dst, bad)
    _, r = T.sync(gallery, dst)
    msgs = "\n".join(r.errs)
    assert not r.done and not (dst / "script").exists()
    assert "битов «|»" in msgs and "кириллица" in msgs and "триггер at «palabra»" in msgs and "цифры не те" in msgs


def test_overrides(gallery):
    dst = gallery.parent / "gal-es"
    T.sync(gallery, dst, "es", tts="edge")
    d = _fill(dst)
    sid = next(k for k in d["scenes"] if "/" in k)
    d["overrides"]["scenes"][sid] = {"params": {"color": "accent2"}, "hold": 0.5}
    (dst / T.SHEET).write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    _, r = T.sync(gallery, dst)
    assert r.done
    user = yaml.safe_load((dst / "project.yaml").read_text(encoding="utf-8"))
    assert user["tts"]["backend"] == "edge" and "voice" not in user["tts"]  # голос — профиля языка (es, edge)
    assert project.load(dst).cfg["tts"]["voice"] == lang.default_voice("es", "edge")
    ch, s_id = sid.split("/")
    sc = next(s for s in yaml.safe_load((dst / "script" / f"{ch}.yaml").read_text(encoding="utf-8"))["scenes"]
              if s["id"] == s_id)
    assert sc["params"]["color"] == "accent2" and sc["hold"] == 0.5


def test_refuses_cutdown_and_same_language(gallery, tmp_path):
    with pytest.raises(SystemExit, match="уже на языке"):
        T.sync(gallery, tmp_path / "x", "en")
    (tmp_path / "cut").mkdir()
    (tmp_path / "cut" / "project.yaml").write_text("cutdown: {source: gal}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="нарезка"):
        T.sync(tmp_path / "cut", tmp_path / "y", "es")

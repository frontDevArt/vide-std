"""P2.5: ключ кэша рендера — по импортам кода шаблона, а не по ручному списку файлов."""
import pytest

from conftest import ROOT, make_gallery
from studio import codehash as C, packs as TP, project, render, timing

STUDIO = ROOT / "studio"


def _edit(monkeypatch, path):
    """Подменить содержимое файла для хэша: как будто файл поправили."""
    path = path.resolve()
    real = C._read
    monkeypatch.setattr(C, "_read", lambda f: real(f) + (b"\n# edit" if f == path else b""))


@pytest.fixture(scope="module")
def gallery(tmp_path_factory):
    proj = project.load(make_gallery(tmp_path_factory.mktemp("gallery") / "horizontal", "horizontal"))
    timing.layout(proj, log=lambda *_: None)
    return proj


def _keys(proj):
    tl, _ = render.prepare(proj)
    return {(s["chapter"], s["id"]): (TP.REGISTRY.canonical(s["template"]), s["key"]) for s in tl["scenes"]}


def _stale(before, after):
    return {before[i][0].split(".")[0] for i in before if before[i][1] != after[i][1]}


@pytest.mark.parametrize("pack", ["core", "phone", "lab"])
def test_every_pack_file_stales_its_scenes(pack, gallery, monkeypatch):
    before = _keys(gallery)
    for f in sorted((STUDIO / "packs" / pack).glob("*.py")):
        with monkeypatch.context() as m:
            _edit(m, f)
            stale = _stale(before, _keys(gallery))
        if f.name == "check.py":  # проверка триггеров для validate/voice — не рисует
            assert stale == set(), f
            continue
        assert pack in stale, f
        if f.name != "background.py":  # фон lab рисует render для всех сцен стиля lab
            assert stale == {pack}, f


def test_commerce_does_not_stale_other_packs(gallery, monkeypatch):
    # P2.9: commerce построен на lab, но lab от него не зависит — сцены галереи (без commerce) не устаревают
    before = _keys(gallery)
    for f in sorted((STUDIO / "packs" / "commerce").glob("*.py")):
        with monkeypatch.context() as m:
            _edit(m, f)
            assert _stale(before, _keys(gallery)) == set(), f


def test_drawing_core_stales_everything(gallery, monkeypatch):
    before = _keys(gallery)
    for name in ("anim.py", "gfx.py", "motion.py", "style.py", "subs.py", "render.py"):
        with monkeypatch.context() as m:
            _edit(m, STUDIO / name)
            assert _stale(before, _keys(gallery)) == {"core", "phone", "lab"}, name


def test_data_modules_do_not_stale(gallery, monkeypatch):
    # их результат уже в хэше сцены (тайминг, тексты) — перерендер не нужен
    before = _keys(gallery)
    for name in ("tts.py", "timing.py", "validate.py", "cli.py", "qa.py"):
        with monkeypatch.context() as m:
            _edit(m, STUDIO / name)
            assert _stale(before, _keys(gallery)) == set(), name


def test_new_module_found_by_import(tmp_path):
    # новый модуль рисования не надо вносить в список: его находит импорт
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "x.py").write_text("def f():\n    from studio.packs.lab import elements\n")
    files = C.base_files(tmp_path)
    assert (STUDIO / "packs" / "lab" / "elements.py").resolve() in files
    assert (tmp_path / "templates" / "x.py").resolve() in files


def test_project_templates_stale_all_scenes(gallery, monkeypatch):
    # проектный шаблон может подменить функцию пакета (studio.lab._li = …): он в ключе каждой сцены
    tdir = gallery.root / "templates"
    tdir.mkdir(exist_ok=True)
    (tdir / "extra.py").write_text("X = 1\n")
    try:
        before = _keys(gallery)
        _edit(monkeypatch, tdir / "extra.py")
        assert _stale(before, _keys(gallery)) == {"core", "phone", "lab"}
    finally:
        (tdir / "extra.py").unlink()


def test_code_hash_old_name():
    assert render.code_hash is C.code_hash
    assert len(C.code_hash()) == 10

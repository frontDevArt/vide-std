"""ROADMAP C5.6: QA «Картинки: файлы и лицензия» (imagegen.qa_check) — каждый файл кадра (картинка, база и слои
раскладки, вырезанный объект) и каждая запись assets/images/ в assets.yaml на месте и с источником и лицензией.
Сеть не нужна: картинки — fake."""
import yaml
from test_images_command import SCENE, SUBJECT, _root
from test_images_schema import _proj

from studio import cli, imagegen, project


def _made(tmp_path, image):
    root = _root(tmp_path, image=image)
    assert cli.main(["images", str(root)]) == 0
    return root


def test_disabled_or_no_requests_skipped(tmp_path):
    assert imagegen.qa_check(project.load(_proj(tmp_path / "a"))) is None
    assert imagegen.qa_check(project.load(_proj(tmp_path / "b", images={"enabled": True, "backend": "fake"}))) is None


def test_all_frame_files_present_and_licensed(tmp_path):
    root = _made(tmp_path, [SCENE])
    proj = project.load(root)
    used = imagegen.used_files(proj)
    assert any(f.endswith(".layers/base.png") for f in used) and len(used) == 4  # картинка, база, 2 слоя
    ok, detail, fakes = imagegen.qa_check(proj)
    assert ok and "лицензии" in detail and len(fakes) == 4  # заглушки — ⚠️ в отчёте


def test_missing_file_and_license_fail(tmp_path):
    root = _made(tmp_path, [{"prompt": "an empty room", "role": "bg"}, SUBJECT])
    proj = project.load(root)
    cut = next(f for f in imagegen.used_files(proj) if f.endswith(".cut.png"))
    (root / cut).unlink()
    ok, detail, _ = imagegen.qa_check(proj)
    assert not ok and "нет файла" in detail and "python -m studio images" in detail
    assert cli.main(["images", str(root)]) == 0  # вернули файл
    reg = root / "assets.yaml"
    data = yaml.safe_load(reg.read_text(encoding="utf-8"))
    for e in data["assets"]:
        e.pop("license")
    reg.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    ok, detail, _ = imagegen.qa_check(project.load(root))
    assert not ok and "лицензии" in detail

"""P2.4: пакеты шаблонов — пространства имён, алиасы, коллизии, форматы, типы параметров, совместимость входов."""
import subprocess
import sys

import pytest

from conftest import ROOT, make_gallery
from studio import cli, lab, templates
from studio.packs import REGISTRY, Param, Template, TemplateNameError, load_project_templates, template
from studio.packs.registry import P, Registry, namespace_of

OLD = {  # плоские имена до P2.4 → полное имя
    "title": "core.title", "statement": "core.statement", "bullets": "core.bullets", "counter": "core.counter",
    "outro": "core.outro", "phone_lock": "phone.lock", "phone_feed": "phone.feed", "cards": "phone.cards",
    "questions": "phone.questions", "phone_close": "phone.close",
    **{f"lab_{n}": f"lab.{n}" for n in ("hero_stack", "crowd", "verdict", "full_number", "versus", "flow", "diagram",
                                         "chapter")},
}


NEW = {"commerce.price_tag", "commerce.number"}  # P2.9: новые шаблоны, старых имён у них нет


def test_old_names_are_aliases():
    assert set(REGISTRY.templates()) == set(OLD.values()) | NEW
    for old, full in OLD.items():
        assert REGISTRY.canonical(old) == full and REGISTRY[old] is REGISTRY[full]
        assert REGISTRY[full].NAME == full and old in REGISTRY[full].ALIASES


def test_packs_by_module():
    for full, cls in REGISTRY.templates().items():
        ns = full.split(".")[0]
        assert cls.__module__.startswith(f"studio.packs.{ns}") and cls.NAMESPACE == ns
    assert namespace_of("project_tpl_money") == "project" and namespace_of("studio.packs.lab.hero") == "lab"


def test_formats_and_typed_params():
    for full, cls in REGISTRY.templates().items():
        assert cls.FORMATS == (("horizontal",) if full.startswith(("lab.", "commerce.")) else ("vertical", "horizontal", "square"))
        assert cls.PARAMS and all(isinstance(p, Param) for p in cls.PARAMS.values())
    assert REGISTRY["lab_full_number"].PARAMS["at"].check("w:median") is None
    assert REGISTRY["counter"].PARAMS["to"].check("сто") == "ожидается число, а не str"
    assert REGISTRY["phone_feed"].PARAMS["counter"].check(1) == "ожидается да/нет, а не int"
    assert REGISTRY["statement"].PARAMS["icon"].check(None) is None  # None = «не задано»
    assert P(1).check(True) == "ожидается число, а не bool"


def test_collisions():
    r = Registry()
    a, b = type("A", (), {"__module__": "x"}), type("B", (), {"__module__": "y"})
    r.add(a, "core.a", ("a",))
    r.add(type("A", (), {"__module__": "x"}), "core.a", ("a",))  # тот же шаблон заново (перезагрузка) — можно
    with pytest.raises(TemplateNameError, match="уже есть"):
        r.add(b, "core.a")
    with pytest.raises(TemplateNameError, match="занято"):
        r.add(b, "project.a", ("a",))
    r.drop_namespace("core")
    assert len(r) == 0


def test_project_template_cannot_shadow_builtin():
    with pytest.raises(TemplateNameError, match="'title' занято"):
        template("title")(type("T", (Template,), {"__module__": "project_tpl_t"}))
    assert REGISTRY["title"] is REGISTRY["core.title"]
    REGISTRY.drop_namespace("project")


def test_project_namespace(tmp_path):
    d = tmp_path / "templates"
    d.mkdir()
    (d / "my.py").write_text('from studio.templates import Template, template\n\n'
                             '@template("big_quote", params={"text": ""})\nclass BigQuote(Template):\n    pass\n',
                             encoding="utf-8")
    load_project_templates(tmp_path)
    load_project_templates(tmp_path)  # повторная загрузка (рендер, воркеры) — не коллизия
    assert REGISTRY.canonical("big_quote") == "project.big_quote"
    assert REGISTRY["big_quote"].PARAMS["text"] == Param((str,), "", "")
    load_project_templates(tmp_path / "other")  # другой проект: шаблоны прошлого убраны
    assert "big_quote" not in REGISTRY


def test_old_imports():
    # входы, которыми пользуются шаблоны проектов и тесты
    assert templates.Template is Template and templates.REGISTRY is REGISTRY and templates.plural(2, ["a", "b"]) == "b"
    assert lab.LabTemplate is REGISTRY["lab_flow"].__mro__[1] and callable(lab.trigger_errors)
    assert lab.LabBackground and lab.apply_camera and lab.C and lab._ss_canvas and lab.SS == 3


def test_lab_patch_reaches_package():
    # money.py подменяет studio.lab._li — подмена должна дойти до line_icon в пакете
    from studio.packs.lab import elements
    base = lab._li
    try:
        lab._li = lambda name, d, s, c, w: base(name, d, s, c, w) if name != "zz" else True
        assert elements._li is lab._li
        elements.line_icon("zz", 40)
    finally:
        lab._li = base
    assert elements._li is base


def test_fake_discounts_templates():
    load_project_templates(ROOT / "projects" / "fake-discounts")
    try:
        assert REGISTRY.canonical("fd_number") == "project.fd_number"
        assert REGISTRY.canonical("lab_anchor") == "project.lab_anchor"
        assert set(REGISTRY["fd_number"].PARAMS) == set(REGISTRY["lab_full_number"].PARAMS)
    finally:
        REGISTRY.drop_namespace("project")


def test_validate_types_formats_and_names(tmp_path, capsys):
    root = make_gallery(tmp_path / "g", "vertical")
    f = root / "script" / "ch01.yaml"
    s = f.read_text(encoding="utf-8")
    s = s.replace("template: lab_chapter", "template: lab.chapter", 1)  # полное имя работает
    f.write_text(s, encoding="utf-8")
    assert cli.main(["validate", str(root)]) == 0
    out = capsys.readouterr().out
    assert "format: vertical — шаблоны свёрстаны под другой формат: lab.chapter (horizontal)" in out
    f.write_text(s.replace("template: lab.chapter", "template: lab_chaptr", 1), encoding="utf-8")
    assert cli.main(["validate", str(root)]) == 1
    assert "нет шаблона 'lab_chaptr' — может, lab_chapter" in capsys.readouterr().out


def test_validate_param_type(tmp_path):
    from studio import project, validate
    root = make_gallery(tmp_path / "g")
    proj = project.load(root)
    sc = next(s for _, d in proj.chapters for s in d["scenes"] if s["template"] == "lab_chapter")
    sc["params"]["number"] = "one"
    r = validate.check(proj)
    assert any("lab_chapter.number = 'one' — ожидается число, а не str" in w for w in r.warns), r.warns


def test_no_cycle_templates_lab():
    # пакеты импортируются без studio.templates / studio.lab (старый цикл templates ↔ lab); отдельный процесс —
    # чистый sys.modules
    code = ("import sys, studio.packs; "
            "assert 'studio.templates' not in sys.modules and 'studio.lab' not in sys.modules, sorted(sys.modules)")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)

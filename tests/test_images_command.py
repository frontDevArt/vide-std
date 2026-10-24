"""ROADMAP C5.4: команда `images` — смета, «да» (--yes), стоп по budget_usd, баланс Kie до и после, кэш (повтор
бесплатен), учёт в assets.yaml, вырезание rembg. Сеть и rembg подменены: ни одного платного вызова."""
import subprocess

import yaml
from PIL import Image
from test_images_schema import _proj

from studio import assets, cli, imagegen, project

SCENE = {"prompt": "a cozy bedroom at night", "role": "scene", "layers": ["room", "bed"]}
SUBJECT = {"prompt": "a desk lamp", "role": "subject"}


def _root(tmp_path, backend="fake", image=None, **images):
    return _proj(tmp_path, images={"enabled": True, "style": "flat vector", "backend": backend, **images},
                 image=[SCENE, {"prompt": "same, lamp on", "role": "state_b"}] if image is None else image)


def _reg(root):
    return assets.load(root)[0]


def test_disabled_is_noop(tmp_path, capsys):
    assert cli.main(["images", str(_proj(tmp_path))]) == 0
    assert "выключены" in capsys.readouterr().out


def test_fake_generates_registers_and_caches(tmp_path, capsys, monkeypatch):
    root = _root(tmp_path)
    (root / "assets.yaml").write_text("# ручная запись\nassets:\n  - {file: assets/x.png, source: s, license: l}\n",
                                      encoding="utf-8")
    assert cli.main(["images", str(root)]) == 0
    out = capsys.readouterr().out
    assert "сделать 3" in out and "assets.yaml: +5" in out  # картинка, база + 2 слоя, state_b
    proj = project.load(root)
    assert imagegen.missing(proj) == []
    text = (root / "assets.yaml").read_text(encoding="utf-8")
    assert text.startswith("# ручная запись")  # ручное и комментарии не тронуты
    reg = _reg(root)
    files = [k for k in reg if k.startswith(imagegen.DIR)]
    assert len(files) == 5 and all(reg[k]["license"] == imagegen.FAKE_LICENSE for k in files)
    assert "flat vector" in reg[files[0]]["prompt"] and "credits" not in reg[files[0]]
    calls = []
    monkeypatch.setattr(imagegen, "generate", lambda *a, **k: calls.append(a))
    assert cli.main(["images", str(root)]) == 0  # повтор — из кэша, записи не дублируются
    out = capsys.readouterr().out
    assert calls == [] and "в кэше 3, сделать 0" in out and "assets.yaml: +0" in out


def _kie(monkeypatch, balance=(1000.0, 963.04)):
    monkeypatch.setenv("KIE_API_KEY", "sk-secret-123")
    bal = list(balance)
    calls = {"balance": 0, "gen": []}

    def kie_balance(ws=None):
        calls["balance"] += 1
        return bal.pop(0) if len(bal) > 1 else bal[0]

    def generate(proj, job, ws=None):  # вместо сети — fake-файлы с ценой и задачей Kie
        calls["gen"].append((job.step, job.model))
        st = dict(proj.cfg["images"], backend="fake")
        job.out.parent.mkdir(parents=True, exist_ok=True)
        imagegen._fake(proj, job, st, ws)
        return {"credits": job.credits, "task": f"t{len(calls['gen'])}", "files": [job.out]}

    monkeypatch.setattr(imagegen, "kie_balance", kie_balance)
    monkeypatch.setattr(imagegen, "generate", generate)
    return calls


def test_kie_needs_yes(tmp_path, capsys, monkeypatch):
    calls = _kie(monkeypatch)
    root = _root(tmp_path, "kie")
    assert cli.main(["images", str(root)]) == 3
    out = capsys.readouterr().out
    assert "Смета: 36.96 кредитов ≈ $0.18" in out and "--yes" in out
    assert calls == {"balance": 0, "gen": []} and not (root / "assets.yaml").exists()


def test_kie_over_budget_stops_even_with_yes(tmp_path, capsys, monkeypatch):
    calls = _kie(monkeypatch)
    assert cli.main(["images", str(_root(tmp_path, "kie", budget_usd=0.1)), "--yes"]) == 3
    assert "больше images.budget_usd" in capsys.readouterr().out and calls["gen"] == []


def test_kie_yes_generates_with_balance_and_license(tmp_path, capsys, monkeypatch):
    calls = _kie(monkeypatch)
    root = _root(tmp_path, "kie")
    assert cli.main(["images", str(root), "--yes"]) == 0
    out = capsys.readouterr().out
    assert calls["balance"] == 2 and "Баланс Kie: 1000 → 963.04" in out and "sk-secret" not in out
    assert [s for s, _ in calls["gen"]] == ["image", "layers", "image"]
    reg = _reg(root)
    k0 = imagegen.plan(project.load(root))[0].key
    e = reg[f"{imagegen.DIR}/{k0}.png"]
    assert e["license"].startswith("Google Gemini API terms") and e["model"] == "nano-banana-2"
    assert e["credits"] == 12 and e["usd"] == 0.06 and e["task"] == "t1"
    base = reg[f"{imagegen.DIR}/{k0}.layers/base.png"]
    assert "ByteDance" in base["license"] and base["credits"] == 12.96
    assert "credits" not in reg[f"{imagegen.DIR}/{k0}.layers/1.png"]  # цена раскладки — одна, у базы
    assert "sk-secret" not in (root / "assets.yaml").read_text(encoding="utf-8")


def test_kie_low_balance_stops(tmp_path, capsys, monkeypatch):
    calls = _kie(monkeypatch, balance=(10.0,))
    assert cli.main(["images", str(_root(tmp_path, "kie")), "--yes"]) == 3
    assert "пополните" in capsys.readouterr().out and calls["gen"] == []


def test_kie_error_reports_and_keeps_done(tmp_path, capsys, monkeypatch):
    calls = _kie(monkeypatch)
    ok = imagegen.generate

    def flaky(proj, job, ws=None):
        if job.step == "layers":
            raise imagegen.ImagesUnavailable("Kie code 402 нет кредитов")
        return ok(proj, job, ws)
    monkeypatch.setattr(imagegen, "generate", flaky)
    root = _root(tmp_path, "kie")
    assert cli.main(["images", str(root), "--yes"]) == 2
    out = capsys.readouterr().out
    assert "402" in out and calls["balance"] == 2  # баланс после — и при ошибке
    assert len(_reg(root)) == 1  # сделанная картинка учтена, повтор её не оплатит


def test_rembg_cutout_runs_local_venv(tmp_path, capsys, monkeypatch):
    calls = _kie(monkeypatch, balance=(1000.0, 988.0))
    monkeypatch.setattr(imagegen, "generate", _gen_with_real_local(calls))
    exe = tmp_path / "python.exe"
    monkeypatch.setattr(imagegen, "rembg_python", lambda: exe)
    seen = []

    def fake_run(cmd, **kw):
        seen.append((cmd, kw.get("stdin")))
        Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    root = _root(tmp_path, "kie", image=SUBJECT)
    assert cli.main(["images", str(root), "--yes"]) == 0
    assert "Смета: 12 кредитов" in capsys.readouterr().out  # rembg бесплатно
    (cmd, stdin), = seen
    assert cmd[:3] == [str(exe), "-I", "-c"] and cmd[4] == imagegen.REMBG_MODEL and stdin == subprocess.DEVNULL
    k = imagegen.plan(project.load(root))[0].key
    cut = _reg(root)[f"{imagegen.DIR}/{k}.cut.png"]
    assert "rembg" in cut["source"] and "Apache-2.0" in cut["license"] and "credits" not in cut
    assert not list((root / imagegen.DIR).glob("*.part*"))


def _gen_with_real_local(calls):
    fake_gen = imagegen.generate  # подменённый _kie: сеть → fake

    def gen(proj, job, ws=None):
        if job.local:
            return imagegen.rembg_cut(proj, job)
        return fake_gen(proj, job, ws)
    return gen


def test_rembg_failure_is_clear(tmp_path, monkeypatch):
    root = _root(tmp_path, "none", image=SUBJECT)
    proj = project.load(root)
    img, cut = imagegen.plan(proj)
    img.out.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(img.out)
    monkeypatch.setattr(imagegen, "rembg_python", lambda: tmp_path / "python.exe")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    try:
        imagegen.generate(proj, cut)  # backend none — rembg всё равно локально по готовому файлу
    except imagegen.ImagesUnavailable as e:
        assert "boom" in str(e)
    else:
        raise AssertionError("ждали ImagesUnavailable")


def test_none_lists_missing_files(tmp_path, capsys):
    root = _root(tmp_path, "none")
    assert cli.main(["images", str(root)]) == 1
    out = capsys.readouterr().out
    assert out.count("положите готовый файл") == 3 and "сами" in out  # все недостающие разом, не по одному


def test_register_rewrites_when_assets_not_last(tmp_path):
    root = _root(tmp_path)
    (root / "assets.yaml").write_text("assets:\n  - {file: a.png, source: s, license: l}\nnote: x\n", encoding="utf-8")
    proj = project.load(root)
    n = imagegen.register(proj, [{"file": "assets/images/k.png", "source": "s", "license": "l"}])
    data = yaml.safe_load((root / "assets.yaml").read_text(encoding="utf-8"))
    assert n == 1 and data["note"] == "x" and [e["file"] for e in data["assets"]] == ["a.png", "assets/images/k.png"]

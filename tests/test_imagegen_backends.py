"""ROADMAP C5.3: бэкенды картинок — план и смета, fake (офлайн PNG), none, kie (задача → опрос; ошибка с HTTP 200 по
полю code; 403 без ретраев; загрузка своих картинок). Сеть подменена: ни одного настоящего запроса и денег."""
import io
import json
import urllib.error

import pytest
from PIL import Image

from studio import imagegen, project
from test_images_schema import _proj

SCENE = {"prompt": "a cozy bedroom at night", "role": "scene", "layers": ["room", "bed"]}
IMAGES = {"enabled": True, "style": "flat vector", "backend": "fake"}


def _load(tmp_path, images=None, image=None):
    return project.load(_proj(tmp_path, images={**IMAGES, **(images or {})},
                              image=[SCENE, {"prompt": "same, lamp on", "role": "state_b"}] if image is None else image))


def test_plan_and_estimate(tmp_path):
    proj = _load(tmp_path, {"backend": "kie"})
    jobs = imagegen.plan(proj)
    assert [(j.step, j.model) for j in jobs] == [("image", "nano-banana-2"),
                                                 ("layers", "seedream/5-flash-layer-decomposition"),
                                                 ("image", "nano-banana-2")]
    assert jobs[2].base == jobs[0].key  # state_b правит первую картинку сцены
    est = imagegen.estimate(proj)
    assert est["credits"] == 12 + 12.96 + 12 and est["usd"] == round(36.96 / 200, 4)
    assert not est["over"] and est["unpriced"] == [] and est["cached"] == 0
    assert imagegen.estimate(project.load(_proj(tmp_path / "b", images={**IMAGES, "backend": "kie", "budget_usd": 0.1},
                                                image=SCENE)))["over"]


def test_estimate_unpriced_and_local_cutout(tmp_path):
    proj = _load(tmp_path, {"backend": "kie", "model": "google/nano-banana", "cutout": "kie"},
                 image=[{"prompt": "a lamp", "role": "subject"}, {"prompt": "lamp on", "role": "state_b"}])
    jobs = imagegen.plan(proj)
    assert [(j.step, j.model) for j in jobs] == [("image", "google/nano-banana"),
                                                 ("cutout", "recraft/remove-background"),
                                                 ("image", "google/nano-banana-edit")]  # с картинкой-входом — edit
    est = imagegen.estimate(proj)
    assert est["credits"] == 4 + 2 * imagegen.UNPRICED  # без замера — с запасом, не ноль
    assert est["unpriced"] == ["google/nano-banana-edit", "recraft/remove-background"]
    rembg = imagegen.plan(_load(tmp_path / "r", {"backend": "kie"}, image={"prompt": "a lamp", "role": "subject"}))
    assert rembg[1].local and imagegen.estimate(_load(tmp_path / "r2", {"backend": "kie"},
                                                      image={"prompt": "a lamp", "role": "subject"}))["credits"] == 12
    assert imagegen.estimate(_load(tmp_path / "f"))["credits"] == 0  # fake бесплатно


def test_unknown_model_is_clear_error(tmp_path):
    with pytest.raises(imagegen.ImagesUnavailable, match="imagegen.MODELS"):
        imagegen.plan(_load(tmp_path, {"model": "midjourney"}))


def test_fake_generates_deterministic_pngs(tmp_path):
    a, b = _load(tmp_path / "a"), _load(tmp_path / "b")
    for proj in (a, b):
        for j in imagegen.plan(proj):
            assert imagegen.generate(proj, j)["credits"] == 0
    assert imagegen.missing(a) == [] and imagegen.estimate(a)["todo"] == []  # повтор — ничего не делать
    ja, jb = imagegen.plan(a), imagegen.plan(b)
    assert ja[0].out.read_bytes() == jb[0].out.read_bytes()
    assert ja[0].out.read_bytes() != ja[2].out.read_bytes()  # state_b — другая картинка
    im = Image.open(ja[0].out)
    assert im.size == (768, 432)  # horizontal 16:9, длинная сторона FAKE_SIDE
    meta = json.loads(ja[1].out.read_text(encoding="utf-8"))
    assert meta["base"] == "base.png" and [x["name"] for x in meta["layers"]] == ["room", "bed"]
    for x in meta["layers"]:
        lay = Image.open(ja[1].out.parent / x["file"])
        assert lay.mode == "RGBA" and all(0 <= v <= 1 for v in x["box"])
    sub = _load(tmp_path / "s", image={"prompt": "a lamp", "role": "subject"})
    for j in imagegen.plan(sub):
        imagegen.generate(sub, j)
    cut = Image.open(imagegen.cut_path(sub, imagegen.plan(sub)[0].key))
    assert cut.mode == "RGBA" and cut.getpixel((0, 0))[3] == 0 and cut.size == (768, 768)


def test_none_backend_asks_for_files(tmp_path):
    proj = _load(tmp_path, {"backend": "none"})
    with pytest.raises(imagegen.ImagesUnavailable, match="assets/images/"):
        imagegen.generate(proj, imagegen.plan(proj)[0])


# ---------------------------------------------------------------- kie с подменённой сетью
def _png(size=(64, 36), mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, (10, 20, 30) if mode == "RGB" else (10, 20, 30, 0)).save(buf, format="PNG")
    return buf.getvalue()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeKie:
    """Сервер Kie в памяти: отвечает по URL, пишет журнал запросов."""

    def __init__(self, states=("generating", "success"), result=None, create=None, files=None):
        self.calls, self.states, self.create = [], list(states), create
        self.result = result or {"resultUrls": ["https://tmp.example/out.png"]}
        self.files = files or {}

    def __call__(self, req, timeout):
        url = req.full_url
        self.calls.append((req.get_method(), url, req.data, dict(req.header_items())))
        if url.startswith(imagegen.KIE_API + "/jobs/createTask"):
            if self.create:
                return self.create(req)
            return self._json({"code": 200, "data": {"taskId": "t1"}})
        if "/jobs/recordInfo" in url:
            st = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            if isinstance(st, Exception):
                raise st
            d = {"state": st, "creditsConsumed": 12}
            if st == "success":
                d["resultJson"] = json.dumps(self.result)
            if st == "fail":
                d.update(failCode="500", failMsg="bad prompt")
            return self._json({"code": 200, "data": d})
        if url == imagegen.KIE_UPLOAD:
            return self._json({"code": 200, "data": {"downloadUrl": f"https://tmp.example/up{len(self.calls)}.png"}})
        if url.endswith("/chat/credit"):
            return self._json({"code": 200, "data": 1234.5})
        if url in self.files:
            return _Resp(self.files[url])
        return _Resp(_png())

    @staticmethod
    def _json(obj):
        return _Resp(json.dumps(obj).encode())

    def bodies(self, part):
        return [json.loads(c[2]) for c in self.calls if part in c[1] and c[2]]


@pytest.fixture
def kie(monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "sk-secret-123")
    monkeypatch.setattr(imagegen, "_sleep", lambda s: None)
    monkeypatch.setattr(imagegen, "_UPLOADS", {})

    def use(server):
        monkeypatch.setattr(imagegen, "_urlopen", server)
        return server
    return use


def test_kie_image_task_poll_download(tmp_path, kie):
    srv = kie(FakeKie())
    proj = _load(tmp_path, {"backend": "kie"}, image={"prompt": "a cozy bedroom at night."})
    job = imagegen.plan(proj)[0]
    r = imagegen.generate(proj, job)
    assert r["credits"] == 12 and r["task"] == "t1" and Image.open(job.out).format == "PNG"
    body = srv.bodies("createTask")[0]
    assert body == {"model": "nano-banana-2", "input": {"prompt": "a cozy bedroom at night. flat vector",
                                                        "aspect_ratio": "16:9", "output_format": "png",
                                                        "resolution": "2K"}}
    auth = [c[3].get("Authorization") for c in srv.calls if "kie.ai" in c[1]]
    assert auth and all(a == "Bearer sk-secret-123" for a in auth)
    assert not list(job.out.parent.glob("*.part"))


def test_kie_state_b_and_reference_upload(tmp_path, kie):
    srv = kie(FakeKie())
    proj = _load(tmp_path, {"backend": "kie", "reference": "ref.png"},
                 image=[{"prompt": "room"}, {"prompt": "room, lamp on", "role": "state_b"}])
    (proj.root / "ref.png").write_bytes(_png())
    for j in imagegen.plan(proj):
        imagegen.generate(proj, j)
    ups = [c for c in srv.calls if c[1] == imagegen.KIE_UPLOAD]
    assert len(ups) == 2  # референс один раз (кэш загрузок), база state_b — отдельно
    assert b'name="file"; filename="ref.png"' in ups[0][2] and "multipart/form-data" in ups[0][3]["Content-type"]
    second = srv.bodies("createTask")[1]["input"]
    assert len(second["image_input"]) == 2 and second["image_input"][1] == srv.bodies("createTask")[0]["input"][
        "image_input"][0]  # база первой, референс вторым


def test_kie_klein_seed_and_aspect_fallback(tmp_path, kie):
    srv = kie(FakeKie())
    proj = project.load(_proj(tmp_path, images={**IMAGES, "backend": "kie", "model": "flux-3/klein-text-to-image"},
                              image={"prompt": "room", "variant": 3}))
    proj.cfg["format"] = "portrait"  # 4:5 у klein нет → ближайший 3:4
    imagegen.generate(proj, imagegen.plan(proj)[0])
    inp = srv.bodies("createTask")[0]["input"]
    assert inp["seed"] == 3 and inp["aspect_ratio"] == "3:4"


def test_kie_layers_writes_base_layers_json(tmp_path, kie):
    result = {"resultObject": {"layers_data": [
        {"z_index": 0, "url": "https://tmp.example/base.png"},
        {"z_index": 1, "url": "https://tmp.example/l1.png", "name": "room",
         "bounding_box": {"normalized": [583, 92, 781, 618]}},
        {"z_index": 2, "url": "https://tmp.example/l2.png", "name": "bed",
         "bounding_box": {"normalized": [428, 645, 785, 919]}}]}}
    srv = kie(FakeKie(result=result, files={"https://tmp.example/l1.png": _png(mode="RGBA")}))
    proj = _load(tmp_path, {"backend": "kie"}, image=SCENE)
    img, lay = imagegen.plan(proj)
    imagegen._save_png(_png(), img.out.parent.mkdir(parents=True, exist_ok=True) or img.out)
    r = imagegen.generate(proj, lay)
    meta = json.loads(lay.out.read_text(encoding="utf-8"))
    assert meta["base"] == "base.png" and [x["file"] for x in meta["layers"]] == ["1.png", "2.png"]
    assert meta["layers"][0]["box"] == [0.583, 0.092, 0.781, 0.618]
    assert Image.open(lay.out.parent / "1.png").mode == "RGBA" and len(r["files"]) == 3
    inp = srv.bodies("createTask")[0]["input"]
    assert inp["prompt"] == "Separate into layers: room; bed." and inp["image_url"].startswith("https://tmp.example/up")


def test_kie_error_with_http_200_by_code(tmp_path, kie):
    srv = kie(FakeKie(create=lambda req: FakeKie._json({"code": 402, "msg": "Credits insufficient"})))
    proj = _load(tmp_path, {"backend": "kie"}, image={"prompt": "room"})
    with pytest.raises(imagegen.ImagesUnavailable, match="402 нет кредитов"):
        imagegen.generate(proj, imagegen.plan(proj)[0])
    assert len(srv.calls) == 1 and not imagegen.plan(proj)[0].out.exists()


def test_kie_403_no_retry_and_key_hidden(tmp_path, kie):
    def deny(req):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b"denied for sk-secret-123"))
    srv = kie(FakeKie(create=deny))
    proj = _load(tmp_path, {"backend": "kie"}, image={"prompt": "room"})
    with pytest.raises(imagegen.ImagesUnavailable) as e:
        imagegen.generate(proj, imagegen.plan(proj)[0])
    assert "403" in str(e.value) and "не ретраим" in str(e.value) and "sk-secret-123" not in str(e.value)
    assert len(srv.calls) == 1


def test_kie_task_fail_and_timeout(tmp_path, kie, monkeypatch):
    kie(FakeKie(states=("generating", "fail")))
    proj = _load(tmp_path, {"backend": "kie"}, image={"prompt": "room"})
    with pytest.raises(imagegen.ImagesUnavailable, match="упала: 500 bad prompt"):
        imagegen.generate(proj, imagegen.plan(proj)[0])
    kie(FakeKie(states=("generating",)))
    t = iter(range(0, 10000, 300))
    monkeypatch.setattr(imagegen, "_clock", lambda: next(t))
    with pytest.raises(imagegen.ImagesUnavailable, match="нет результата за 600 с"):
        imagegen.generate(proj, imagegen.plan(proj)[0])


def test_kie_poll_retries_transient_then_gives_up(tmp_path, kie):
    blip = urllib.error.URLError("reset")
    srv = kie(FakeKie(states=[blip, blip, "success"]))
    proj = _load(tmp_path, {"backend": "kie"}, image={"prompt": "room"})
    assert imagegen.generate(proj, imagegen.plan(proj)[0])["credits"] == 12
    assert len(srv.bodies("createTask")) == 1  # задачу не пересоздаём
    kie(FakeKie(states=[blip]))
    with pytest.raises(imagegen.ImagesUnavailable, match="3 сбоя опроса"):
        imagegen.kie_task("nano-banana-2", {"prompt": "x"})


def test_kie_no_key(tmp_path, monkeypatch):
    monkeypatch.setattr(imagegen.workspace, "secret", lambda name, ws=None: "")
    with pytest.raises(imagegen.ImagesUnavailable, match="KIE_API_KEY"):
        imagegen.kie_balance()


def test_kie_balance(kie):
    kie(FakeKie())
    assert imagegen.kie_balance() == 1234.5

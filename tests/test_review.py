"""ROADMAP D1: ревью с комментариями по таймкодам — review/comments.json, страница на 127.0.0.1, `render --scenes`.
Готово, если: 2 комментария → правка входов этих сцен → в логе рендера только эти сцены."""
import json
import threading
import urllib.error
import urllib.request

import pytest
import yaml

from conftest import make_gallery
from studio import cli, project, render, review, timing


@pytest.fixture(scope="module")
def voiced(tmp_path_factory):
    root = make_gallery(tmp_path_factory.mktemp("review") / "gallery", "vertical")
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    return proj


@pytest.fixture
def fresh(voiced):
    review.path(voiced).unlink(missing_ok=True)
    yield voiced
    review.path(voiced).unlink(missing_ok=True)


def test_comment_binds_to_scene(fresh):
    sc = review.scenes(fresh)
    s = sc[3]
    c = review.add(fresh, s["start"] + 0.5, "  bigger title  ", 0.4, 1.7)
    assert (c["chapter"], c["scene"], c["scene_t"], c["text"]) == (s["chapter"], s["id"], 0.5, "bigger title")
    assert (c["x"], c["y"], c["status"], c["id"]) == (0.4, 1.0, "open", "c1")  # точка обрезана в кадр
    end = sc[-1]["start"] + sc[-1]["dur"]
    assert review.add(fresh, end + 3, "after the end")["scene"] == sc[-1]["id"]
    d = json.loads(review.path(fresh).read_text(encoding="utf-8"))
    assert [c["id"] for c in d["comments"]] == ["c1", "c2"] and d["status"] == "draft"
    with pytest.raises(ValueError):
        review.add(fresh, 1.0, "   ")


def test_status_and_prompt(fresh):
    sc = review.scenes(fresh)
    a = review.add(fresh, sc[5]["start"] + 0.2, "slower")
    b = review.add(fresh, sc[1]["start"] + 0.1, "wrong colour", 0.5, 0.25)
    with pytest.raises(ValueError, match="открытых"):
        review.set_status(fresh, "approved")
    txt = review.prompt(fresh)
    assert txt.index("[c2]") < txt.index("[c1]")  # в порядке ролика
    assert "точка кадра 0.50×0.25" in txt and f"script/{sc[1]['chapter']}.yaml" in txt
    want = f"{sc[1]['chapter']}/{sc[1]['id']},{sc[5]['chapter']}/{sc[5]['id']}"
    assert txt.endswith(f"Сцены: {want}")
    review.update(fresh, a["id"], status="done")
    review.update(fresh, b["id"], status="done")
    assert review.set_status(fresh, "approved")["approved"]
    assert "нет" in review.prompt(fresh)
    review.add(fresh, 1.0, "one more")  # новый комментарий — версия снова черновик
    assert review.load(fresh)["status"] == "draft" and "approved" not in review.load(fresh)
    review.delete(fresh, "c3")
    with pytest.raises(KeyError):
        review.delete(fresh, "c3")


@pytest.fixture
def server(fresh, tmp_path):
    vid = tmp_path / "v.mp4"
    vid.write_bytes(bytes(range(256)) * 40)  # содержимое серверу всё равно — проверяем Range
    srv = review.make_server(fresh, 0, vid)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield srv, review.url(srv), vid
    srv.shutdown()
    srv.server_close()


def _req(url, method="GET", body=None, headers=None):
    h = {"Content-Type": "application/json"} if body is not None else {}
    h.update(headers or {})
    r = urllib.request.Request(url, method=method, headers=h,
                               data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def test_server_api(server, fresh):
    srv, u, vid = server
    assert srv.server_address[0] == "127.0.0.1"
    code, _, page = _req(u)
    assert code == 200 and b"<video" in page
    st = json.loads(_req(u + "api/state")[2])
    assert st["project"] == "gallery" and st["status"] == "draft" and len(st["scenes"]) == 18
    s = st["scenes"][2]
    code, _, body = _req(u + "api/comments", "POST", {"t": s["start"] + 0.3, "x": 0.1, "y": 0.9, "text": "move up"})
    c = json.loads(body)
    assert code == 200 and c["scene"] == s["id"]
    assert _req(u + "api/comments", "POST", {"t": 1, "text": ""})[0] == 400
    assert _req(u + f"api/comments/{c['id']}", "POST", {"status": "done"})[0] == 200
    assert _req(u + "api/status", "POST", {"status": "approved"})[0] == 200
    assert json.loads(_req(u + "api/state")[2])["status"] == "approved"
    assert "move up" not in _req(u + "api/prompt")[2].decode()  # закрытый не попадает в текст для Claude
    assert _req(u + f"api/comments/{c['id']}", "DELETE", {})[0] == 200
    assert _req(u + "api/comments/c99", "POST", {"status": "done"})[0] == 404


def test_server_guards(server):
    _, u, _ = server
    # запись без JSON (так шлёт форма чужой страницы) — отказ
    r = urllib.request.Request(u + "api/comments", method="POST", data=b"t=1&text=x",
                               headers={"Content-Type": "application/x-www-form-urlencoded"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(r, timeout=10)
    assert e.value.code == 400
    assert _req(u + "api/state", headers={"Host": "evil.example:80"})[0] == 403  # DNS-rebinding
    assert _req(u + "../project.yaml")[0] == 404


def test_server_video_range(server):
    _, u, vid = server
    data = vid.read_bytes()
    code, h, body = _req(u + "video.mp4", headers={"Range": "bytes=100-199"})
    assert code == 206 and body == data[100:200] and h["Content-Range"] == f"bytes 100-199/{len(data)}"
    code, _, body = _req(u + "video.mp4", headers={"Range": "bytes=-10"})
    assert code == 206 and body == data[-10:]
    code, h, body = _req(u + "video.mp4")
    assert code == 200 and body == data and h["Accept-Ranges"] == "bytes"
    assert _req(u + "video.mp4", headers={"Range": f"bytes={len(data) + 5}-"})[0] == 416


def test_no_video_hint(fresh):
    with pytest.raises(SystemExit, match="--draft"):
        review.make_server(fresh, 0)


def test_pick_scenes(voiced):
    tl, _ = render.prepare(voiced)
    assert render.pick_scenes(tl, "ch01/s01, ch02/s03") == {("ch01", "s01"), ("ch02", "s03")}
    with pytest.raises(SystemExit, match="ch09/s01"):
        render.pick_scenes(tl, "ch09/s01")


def test_two_comments_rerender_only_their_scenes(tmp_path, capsys):
    """Критерий D1: 2 комментария → правка входов их сцен (/review-fix) → в логе рендера только эти сцены."""
    root = make_gallery(tmp_path / "gallery", "vertical")
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    render.render(proj, log=lambda *_: None, draft=True)
    sc = {(s["chapter"], s["id"]): s for s in review.scenes(proj)}
    review.add(proj, sc[("ch02", "s07")]["start"] + 0.4, "count to fifty", 0.5, 0.5)
    review.add(proj, sc[("ch02", "s09")]["start"] + 0.2, "other icon", 0.5, 0.4)
    assert cli.main(["review", str(root), "--list"]) == 0
    listed = capsys.readouterr().out
    assert "Сцены: ch02/s07,ch02/s09" in listed
    # правка входов, как её делает /review-fix: только params этих сцен
    f = root / "script" / "ch02.yaml"
    d = yaml.safe_load(f.read_text(encoding="utf-8"))
    for s in d["scenes"]:
        if s["id"] == "s07":
            s["params"]["to"] = 50
        if s["id"] == "s09":
            s["params"]["icon"] = "clock"
    f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    assert cli.main(["voice", str(root)]) == 0  # тайминг из сценария (озвучка — из кэша)
    assert cli.main(["render", str(root), "--draft", "--scenes", "ch02/s07,ch02/s09"]) == 0
    log = sorted((root / "logs").glob("render-*.log"))[-1].read_text(encoding="utf-8")
    rendered = [l.split(":")[0].strip().split(" ")[0] for l in log.splitlines() if " кадров за " in l]
    assert sorted(set(rendered)) == ["s07", "s09"], log
    assert "Сцены: ch02/s07, ch02/s09" in log and "Устарели" not in log
    tl, _ = render.prepare(project.load(root), draft=True)
    assert all(render.is_fresh(proj, s) for s in tl["scenes"])  # соседей правка не задела
    assert cli.main(["review", str(root), "--done", "c1,c2", "--status", "approved"]) == 0
    assert review.load(proj)["status"] == "approved"

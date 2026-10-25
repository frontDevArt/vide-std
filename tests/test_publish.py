"""ROADMAP E1: публикация вручную — карточка загрузки, ворота, отметка в published.yaml, --list, status."""
import json
import shutil
import threading
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from studio import cli, deliver, project, publish, status, youtube

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"
SCENES = [{"id": "s01", "template": "statement", "params": {"text": "Habit"},
           "lines": ["People say it takes three weeks to build a habit."]}]


def _pass(t):
    t.qa_dir.mkdir(parents=True, exist_ok=True)
    (t.qa_dir / "report.md").write_text("# QA\n\nИтог: **PASS**\n", encoding="utf-8")  # qa целиком — долго


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    dst = tmp_path_factory.mktemp("pub") / "p"
    shutil.copytree(FIXTURE, dst)
    data = yaml.safe_load((dst / "project.yaml").read_text(encoding="utf-8"))
    data.update(format="horizontal", deliverables=["youtube", "tiktok"],
                package={"title": "Habits", "description": "Checked.", "hashtags": ["habits"]})
    (dst / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    (dst / "script" / "ch01.yaml").write_text(
        yaml.safe_dump({"chapter": "ch01", "title": "Habits", "scenes": SCENES}), encoding="utf-8")
    for cmd in (["voice", str(dst)], ["render", str(dst), "--workers", "2"], ["assemble", str(dst)]):
        assert cli.main(cmd) == 0
    return project.load(dst)


def test_card_gates_without_qa(built, capsys):
    assert cli.main(["publish", str(built.root), "--out", "youtube"]) == 1  # QA не запускался
    out = capsys.readouterr().out
    assert "❌ QA: не запускался" in out and "Не публиковать" in out
    assert not publish.path(built).exists()
    assert cli.main(["publish", str(built.root), "--out", "youtube", "--done",
                     "--url", "https://youtu.be/abc"]) == 1
    assert not publish.path(built).exists()  # непроверенное не отмечается


def test_card_and_record(built, capsys):
    for o in ("youtube", "tiktok"):
        _pass(built.output(o))
    assert cli.main(["publish", str(built.root)]) == 0
    out = capsys.readouterr().out
    assert "studio.youtube.com" in out and "tiktokstudio/upload" in out
    assert "youtube.cover.jpg" in out and "youtube.srt" in out and "Altered or synthetic content" in out
    assert "Название: Habits" in out and "youtube.checklist.md" in out and "--done --url" in out
    # сданная версия: запись ссылается на неё по sha1 файла
    assert deliver.deliver(built, log=lambda *_: None) == 1
    assert cli.main(["publish", str(built.root), "--out", "youtube", "--done", "--url",
                     "https://www.youtube.com/watch?v=abc", "--at", "2026-10-25 18:00", "--note", "первый"]) == 0
    recs = publish.load(built)
    assert len(recs) == 1
    r = recs[0]
    assert (r["out"], r["platform"], r["date"], r["version"], r["file"], r["note"]) == \
        ("youtube", "youtube", "2026-10-25 18:00", 1, "youtube.mp4", "первый")
    assert r["sha1"] and r["duration"] > 0 and "forced" not in r
    assert publish.path(built).read_text(encoding="utf-8").startswith("# Публикации проекта")
    # та же ссылка — обновление, а не дубль
    assert cli.main(["publish", str(built.root), "--out", "youtube", "--done", "--url",
                     "https://www.youtube.com/watch?v=abc", "--at", "2026-10-25 19:00"]) == 0
    assert [x["date"] for x in publish.load(built)] == ["2026-10-25 19:00"]
    capsys.readouterr()
    assert cli.main(["publish", str(built.root), "--out", "youtube"]) == 0
    assert "Уже опубликовано: 2026-10-25 19:00" in capsys.readouterr().out


def test_record_checks_url_and_platform(built, capsys):
    tt = built.output("tiktok")
    _pass(tt)
    with pytest.raises(SystemExit, match="https://"):
        publish.record(tt, "tiktok.com/@me/video/1", log=lambda *_: None)
    with pytest.raises(SystemExit, match="ГГГГ-ММ-ДД"):
        publish.record(tt, "https://www.tiktok.com/@me/video/1", at="завтра", log=lambda *_: None)
    assert publish.record(tt, "https://youtu.be/x", log=lambda *_: None) is None  # ссылка не той площадки
    with pytest.raises(SystemExit, match="--out"):  # два выхода — какой опубликован, сказать явно
        cli.main(["publish", str(built.root), "--done", "--url", "https://www.tiktok.com/@me/video/1"])
    r = publish.record(tt, "https://youtu.be/x", force=True, log=lambda *_: None)
    assert r["forced"] and "TikTok" in r["forced"][0]
    r = publish.record(tt, "https://www.tiktok.com/@me/video/1", log=lambda *_: None)
    assert r["version"] == 1 and r["platform"] == "tiktok"


def test_list_and_status(built, capsys):
    capsys.readouterr()
    assert cli.main(["publish", str(built.root), "--list"]) == 0
    out = capsys.readouterr().out
    assert "youtube → youtube: https://www.youtube.com/watch?v=abc (v1)" in out and "⚠️ --force" in out
    status.report(built)
    assert "Публикация: youtube 2026-10-25" in capsys.readouterr().out


def test_status_unpublished(tmp_path, capsys):
    shutil.copytree(FIXTURE, tmp_path / "p")
    assert publish.summary(project.load(tmp_path / "p")).startswith("не опубликован")


# ---------------------------------------------------------------- ROADMAP E2: YouTube Data API (без сети)
class FakeYT:
    """Подмена youtube._http: токен, канал, сессия загрузки (первый PUT обрывается 503), обложка 403;
    как живой YouTube 2026-10-25 — videos.list отметку ИИ не отдаёт никогда, videos.update возвращает её в ответе
    (`sticky=False` — не возвращает: отметка не встала)."""

    def __init__(self):
        self.calls, self.puts, self.sticky, self.ai = [], 0, True, None
        self.status = {"uploadStatus": "processed", "privacyStatus": "private", "license": "youtube",
                       "embeddable": True, "publicStatsViewable": True, "madeForKids": False,
                       "selfDeclaredMadeForKids": False}

    def __call__(self, method, url, headers=None, data=None, timeout=120):
        headers = headers or {}
        body = data.read() if hasattr(data, "read") else data
        self.calls.append((method, url, headers, body))
        if url == youtube.TOKEN_URL:
            f = dict(x.split("=", 1) for x in body.decode().split("&"))
            if f.get("refresh_token") == "bad":
                return 400, {}, b'{"error": "invalid_grant"}'
            return 200, {}, json.dumps({"access_token": "AT", "refresh_token": "RT",
                                        "scope": " ".join(youtube.SCOPES)}).encode()
        if url.startswith(youtube.CHANNELS_URL):
            return 200, {}, b'{"items": [{"id": "UC1", "snippet": {"title": "Notes"}}]}'
        if url.startswith(youtube.UPLOAD_URL):
            return 200, {"location": "https://upload.test/session"}, b""
        if url == "https://upload.test/session":
            if headers.get("Content-Range", "").startswith("bytes */"):
                return 308, {"range": "bytes=0-99"}, b""
            self.puts += 1
            if self.puts == 1:
                return 503, {}, b""
            return 201, {}, b'{"id": "vid1"}'
        if url.startswith(youtube.VIDEOS_URL) and method == "GET":
            return 200, {}, json.dumps({"items": [{"id": "vid1", "status": self.status}]}).encode()
        if url.startswith(youtube.VIDEOS_URL) and method == "PUT":
            new = json.loads(body)["status"]
            self.ai = new.pop("containsSyntheticMedia")  # что ответили; list его не отдаёт
            self.status = dict(new, uploadStatus="processed", madeForKids=False)
            echo = dict(new, uploadStatus="processed", **({"containsSyntheticMedia": self.ai} if self.sticky else {}))
            return 200, {}, json.dumps({"id": "vid1", "status": echo}).encode()
        if url.startswith(youtube.THUMB_URL):
            return 403, {}, b'{"error": {"errors": [{"reason": "forbidden"}], "message": "no"}}'
        raise AssertionError(url)


@pytest.fixture
def yt(tmp_path, monkeypatch):
    sec = tmp_path / "client_secret_x.json"
    sec.write_text(json.dumps({"installed": {"client_id": "CID", "client_secret": "CS"}}), encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRETS", str(sec))
    tok = tmp_path / ".env.youtube.json"
    monkeypatch.setattr(youtube, "token_path", lambda ws: tok)
    fake = FakeYT()
    monkeypatch.setattr(youtube, "_http", fake)
    monkeypatch.setattr(youtube, "_sleep", lambda s: None)
    return fake, tok


def test_api_auth_loopback(built, yt):
    fake, tok = yt

    def browse(url):  # «браузер»: Google переадресует на 127.0.0.1 с кодом и тем же state
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert q["code_challenge_method"] == "S256" and youtube.SCOPES[0] in q["scope"]
        threading.Thread(target=lambda: urllib.request.urlopen(
            f"{q['redirect_uri']}/?code=C0DE&state={q['state']}", timeout=10).read()).start()

    rec = youtube.auth(built.ws, log=lambda *_: None, browse=browse, wait=20)
    assert rec["channel_title"] == "Notes" and json.loads(tok.read_text(encoding="utf-8"))["refresh_token"] == "RT"
    ex = fake.calls[0][3].decode()
    assert "code=C0DE" in ex and "code_verifier=" in ex and "grant_type=authorization_code" in ex
    assert tok.name.startswith(".env.")  # в .gitignore по шаблону .env.*


def test_api_card_and_upload(built, yt, capsys):
    fake, tok = yt
    yo = built.output("youtube")
    _pass(yo)
    assert cli.main(["publish", str(built.root), "--out", "youtube", "--api", "youtube"]) == 1
    assert "вход не выполнен" in capsys.readouterr().out and not fake.calls
    old = {"refresh_token": "RT", "channel_id": "UC1", "channel_title": "Notes", "scope": "youtube.upload youtube.readonly"}
    tok.write_text(json.dumps(old), encoding="utf-8")
    assert cli.main(["publish", str(built.root), "--out", "youtube", "--api", "youtube"]) == 1  # вход E2 v1: без update
    assert "отметку ИИ не поставить" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="не загружаю"):
        youtube.upload(yo, log=lambda *_: None)
    tok.write_text(json.dumps(dict(old, scope=" ".join(youtube.SCOPES))), encoding="utf-8")
    assert cli.main(["publish", str(built.root), "--api", "youtube"]) == 0  # tiktok пропущен: только YouTube
    out = capsys.readouterr().out
    assert "Канал: «Notes»" in out and "Видимость: private" in out
    assert "Отметка ИИ (containsSyntheticMedia): нет — графика нарисована кодом" in out  # голос fake, без генератора
    assert "--api youtube --yes" in out and "tiktok" not in out and not fake.calls  # карточка ничего не шлёт
    with pytest.raises(SystemExit, match="только у --privacy private"):
        cli.main(["publish", str(built.root), "--api", "youtube", "--privacy", "unlisted", "--at", "2099-01-01 10:00"])
    assert cli.main(["publish", str(built.root), "--out", "youtube", "--api", "youtube", "--yes"]) == 0
    out = capsys.readouterr().out
    init = next(c for c in fake.calls if c[1].startswith(youtube.UPLOAD_URL))
    body = json.loads(init[3])
    assert body["snippet"]["title"] == "Habits" and body["snippet"]["description"].startswith("Checked.")
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                              "containsSyntheticMedia": False}  # «нет» — тоже явным ответом
    size = (yo.output_dir() / "youtube.mp4").stat().st_size
    resume = [c for c in fake.calls if c[1] == "https://upload.test/session" and c[3]][-1]
    assert resume[2]["Content-Range"] == f"bytes 100-{size - 1}/{size}" and len(resume[3]) == size - 100
    assert "докачка" in out and "обложка не загружена" in out and "загружен (private)" in out
    assert "✅ отметка ИИ-контента: нет" in out
    upd = json.loads(next(c for c in fake.calls if c[0] == "PUT" and c[1].startswith(youtube.VIDEOS_URL))[3])
    assert upd["id"] == "vid1" and upd["status"]["containsSyntheticMedia"] is False
    assert upd["status"]["privacyStatus"] == "private" and "uploadStatus" not in upd["status"]  # видимость сохранена
    assert fake.ai is False and "containsSyntheticMedia" not in fake.status  # list поле не отдаёт — верим ответу update
    r = publish.of(built, "youtube")[-1]
    assert (r["url"], r["via"], r["privacy"], r["video_id"], r["ai_label"], r["ai_confirmed"]) == \
        ("https://www.youtube.com/watch?v=vid1", "api", "private", "vid1", False, True)
    assert "Bearer" not in out and "AT" not in out.split()  # токены не печатаются
    # YouTube не вернул ответ — громкий ❌, код 1, ai_confirmed: false; --check — то же для загруженных
    fake.sticky, fake.puts = False, 0
    assert cli.main(["publish", str(built.root), "--out", "youtube", "--api", "youtube", "--yes"]) == 1
    assert "ОТМЕТКА ИИ-КОНТЕНТА НЕ ПОДТВЕРЖДЕНА (нужно: нет)" in capsys.readouterr().out
    assert publish.of(built, "youtube")[-1]["ai_confirmed"] is False
    assert cli.main(["publish", str(built.root), "--api", "youtube", "--check"]) == 1
    # правило изменилось (человек: package.ai_label: true) — --check меняет ответ на «да»
    fake.sticky = True
    capsys.readouterr()
    built.cfg.setdefault("package", {})["ai_label"] = True
    try:
        assert youtube.check(built) is True
    finally:
        del built.cfg["package"]["ai_label"]
    assert "отметка ИИ — ДА (изменена); package.ai_label: true" in capsys.readouterr().out and fake.ai is True
    r = publish.of(built, "youtube")[-1]
    assert (r["ai_label"], r["ai_confirmed"]) == (True, True)


def test_ai_label_rules(built, monkeypatch):
    """Отметка ИИ — по правилам, а не всегда: рисованное + синтетический диктор → нет."""
    from studio import imagegen, package
    yo, tt = built.output("youtube"), built.output("tiktok")
    assert package.ai_label(yo)[0] is False and package.ai_label(tt)[0] is False  # голос fake — не реалистичный
    for t in (yo, tt):
        t.cfg["tts"]["backend"] = "elevenlabs"
    assert package.ai_label(yo)[0] is False  # YouTube: синтетический диктор без подражания человеку — нет
    need, why = package.ai_label(tt)
    assert need and "реалистичный синтетический голос" in why  # TikTok: реалистичный ИИ-голос — да
    monkeypatch.setattr(imagegen, "requests", lambda p: [("ch01/s01", {"prompt": "x"})])
    yo.cfg["images"] = {"enabled": True, "backend": "kie"}
    need, why = package.ai_label(yo)
    assert need and "генератора" in why
    yo.cfg["images"]["backend"] = "fake"  # процедурные PNG — не ИИ
    assert package.ai_label(yo)[0] is False
    yo.cfg["package"]["ai_label"] = True  # решение человека важнее (клон голоса, ИИ-музыка, реалистичная сцена)
    assert package.ai_label(yo) == (True, "package.ai_label: true — решение человека")
    tt.cfg["package"]["ai_label"] = False
    assert package.ai_label(tt)[0] is False


def test_api_refuses(built, yt):
    fake, tok = yt
    with pytest.raises(SystemExit, match="--done"):
        cli.main(["publish", str(built.root), "--api", "youtube", "--done", "--url", "https://youtu.be/x"])
    tok.write_text(json.dumps({"refresh_token": "bad"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="--auth"):
        youtube.access(built.ws)
    with pytest.raises(SystemExit, match="прошло"):
        youtube.meta(built.output("youtube"), at="2001-01-01 10:00")
    (built.output("youtube").qa_dir / "report.md").unlink()  # QA не PASS — не загружаем
    assert youtube.upload(built.output("youtube"), log=lambda *_: None) is None
    assert not [c for c in fake.calls if c[1].startswith(youtube.UPLOAD_URL)]

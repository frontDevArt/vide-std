"""ROADMAP E3: аналитика студии — ролики из published.yaml, цифры (YouTube API без сети, CSV Studio, руками),
analytics/videos.yaml и REPORT.md с выводами для радара."""
import json
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from studio import analytics, cli, workspace, youtube

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"
YT = "https://www.youtube.com/watch?v=vidA"


def _project(root: Path, slug: str, rubric: str | None, platform: str, fmt: str, line: str, pub: list[dict]):
    d = root / "projects" / slug
    shutil.copytree(FIXTURE, d)
    data = yaml.safe_load((d / "project.yaml").read_text(encoding="utf-8"))
    data.update(format=fmt, platform=platform, package={"title": slug.title()})
    (d / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    params = {"text": "x", **({"chrome": {"rubric": rubric}} if rubric else {})}
    sc = [{"id": "s01", "template": "statement", "params": params, "lines": [line]},
          {"id": "s02", "template": "statement", "params": {"text": "y", "verdict": {"verdict": "myth"}},
           "lines": ["The verdict: myth."]}]
    (d / "script" / "ch01.yaml").write_text(yaml.safe_dump({"chapter": "ch01", "scenes": sc}), encoding="utf-8")
    (d / "published.yaml").write_text(yaml.safe_dump(pub), encoding="utf-8")


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "studio"
    (root / "projects").mkdir(parents=True)
    (root / "studio.yaml").write_text("name: Test Channel\nkind: youtube\n", encoding="utf-8")
    _project(root, "habits", "Myth on Trial", "youtube", "horizontal", "People say | it takes *three weeks*.",
             [{"out": None, "platform": "youtube", "url": YT, "date": "2026-10-01 18:00", "duration": 540.0,
               "via": "api", "privacy": "public", "video_id": "vidA"}])
    _project(root, "sleep", "Everyday Brain", "youtube-shorts", "vertical", "You don't need eight hours.",
             [{"out": None, "platform": "youtube-shorts", "url": "https://youtube.com/shorts/vidB",
               "date": "2026-10-10 12:00", "duration": 40.0}])
    _project(root, "coffee", None, "tiktok", "vertical", "Coffee wakes you up?",
             [{"out": None, "platform": "tiktok", "url": "https://www.tiktok.com/@n/video/123",
               "date": "2026-10-12 09:00", "duration": 35.0}])
    (root / "projects" / "draft").mkdir()  # без project.yaml — не проект
    with workspace.use(workspace.Workspace.at(root, id="test")) as w:
        yield w


def test_collect_and_offline_report(ws):
    rows = analytics.videos(ws)
    by = {r["project"]: r for r in rows}
    assert set(by) == {"habits", "sleep", "coffee"}
    h = by["habits"]
    assert (h["rubric"], h["verdict"], h["video_id"], h["hook"]) == \
        ("Myth on Trial", "MYTH", "vidA", "People say it takes three weeks.")
    assert by["sleep"]["video_id"] == "vidB" and by["coffee"]["video_id"] is None and by["coffee"]["rubric"] is None
    assert analytics.video_id("https://youtu.be/abc?t=3") == "abc"
    assert cli.main(["analytics"]) == 0
    rep = (ws.root / "analytics" / "REPORT.md").read_text(encoding="utf-8")
    assert "Цифр пока нет" in rep and "| [habits](" + YT + ")" in rep and "Что зашло" not in rep
    assert (ws.root / "analytics" / "videos.yaml").read_text(encoding="utf-8").startswith("# Цифры роликов студии")


class FakeAPI:
    """youtube._http: токен, Analytics API (по роликам и кривая удержания), Reporting API (задание, отчёты, CSV)."""

    def __init__(self):
        self.calls, self.jobs, self.reports = [], [], []

    def __call__(self, method, url, headers=None, data=None, timeout=120):
        self.calls.append((method, url))
        if url == youtube.TOKEN_URL:
            return 200, {}, b'{"access_token": "AT"}'
        if url.startswith(analytics.ANALYTICS_URL):
            q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
            assert q["ids"] == "channel==MINE" and q["startDate"] == "2026-10-01"
            if q["dimensions"] == "video":
                assert q["filters"] == "video==vidA,vidB"
                heads = ["video"] + list(analytics.API)
                return 200, {}, json.dumps({"columnHeaders": [{"name": h} for h in heads],
                                            "rows": [["vidA", 1200, 3000, 150, 27.8, 40, 6, 9]]}).encode()
            if q["filters"] == "video==vidB":
                return 200, {}, json.dumps({"columnHeaders": [], "rows": []}).encode()
            curve = [[i / 100, 1.0 - i / 200] for i in range(1, 101)]  # 99.5 % … 50 %
            return 200, {}, json.dumps({"columnHeaders": [{"name": "elapsedVideoTimeRatio"},
                                                          {"name": "audienceWatchRatio"}], "rows": curve}).encode()
        if url == analytics.REPORTING_URL + "/jobs" and method == "GET":
            return 200, {}, json.dumps({"jobs": self.jobs}).encode()
        if url == analytics.REPORTING_URL + "/jobs" and method == "POST":
            self.jobs.append({"id": "J1", "reportTypeId": analytics.REACH})
            return 200, {}, b'{"id": "J1"}'
        if url.startswith(analytics.REPORTING_URL + "/jobs/J1/reports"):
            return 200, {}, json.dumps({"reports": self.reports}).encode()
        if url.startswith("https://dl.test/"):
            day = url.rsplit("/", 1)[1]
            imp, ctr = (1000, 0.05) if day == "d1" else (3000, 0.03)
            return 200, {}, (f"date,channel_id,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
                             f"2026100{day[-1]},UC1,vidA,{imp},{ctr}\n").encode()
        raise AssertionError(url)


@pytest.fixture
def api(ws, tmp_path, monkeypatch):
    sec = tmp_path / "client_secret.json"
    sec.write_text(json.dumps({"installed": {"client_id": "CID", "client_secret": "CS"}}), encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRETS", str(sec))
    tok = tmp_path / ".env.youtube.json"
    monkeypatch.setattr(youtube, "token_path", lambda w: tok)
    monkeypatch.setattr(analytics, "today", lambda: "2026-10-25")
    fake = FakeAPI()
    monkeypatch.setattr(youtube, "_http", fake)
    return fake, tok


def test_fetch_youtube(ws, api, capsys):
    fake, tok = api
    tok.write_text(json.dumps({"refresh_token": "RT", "scope": " ".join(youtube.SCOPES[:2])}), encoding="utf-8")
    with pytest.raises(SystemExit, match="analytics --auth"):  # вход E2 без права на аналитику
        cli.main(["analytics", "--fetch"])
    assert not fake.calls
    tok.write_text(json.dumps({"refresh_token": "RT", "scope": " ".join(youtube.SCOPES)}), encoding="utf-8")
    assert cli.main(["analytics", "--fetch"]) == 0
    out = capsys.readouterr().out
    assert "задание отчёта показов создано" in out and fake.jobs  # CTR — со следующего раза
    by = {r["project"]: r for r in analytics.stored(ws).values()}
    m = by["habits"]["metrics"]
    assert (m["views"], m["avg_view_s"], m["avg_view_pct"], m["likes"], m["subs"]) == (1200, 150, 27.8, 40, 9)
    assert m["ret_3s"] == 99.5 and m["ret_50"] == 75 and m["ret_end"] == 52.5 and "ctr" not in m
    assert by["sleep"]["metrics"]["views"] == 0  # нет в ответе — пока без просмотров
    assert by["habits"]["sources"]["views"] == "api 2026-10-25" and by["coffee"]["metrics"] == {}  # tiktok — не API
    assert all(m != "PUT" for m, _ in fake.calls)  # только чтение
    # отчёты показов появились: CTR — взвешенный по показам, скачанное — в кэше
    fake.reports = [{"id": "r1", "downloadUrl": "https://dl.test/d1"}, {"id": "r2", "downloadUrl": "https://dl.test/d2"}]
    assert cli.main(["analytics", "--fetch"]) == 0
    m = {r["project"]: r for r in analytics.stored(ws).values()}["habits"]["metrics"]
    assert m["impressions"] == 4000 and m["ctr"] == 3.5  # (50 + 90) / 4000
    fake.calls.clear()
    assert cli.main(["analytics", "--fetch"]) == 0
    assert not [u for _, u in fake.calls if u.startswith("https://dl.test/")]


def test_import_csv_and_manual(ws, tmp_path, capsys):
    f = tmp_path / "Table data.csv"
    f.write_text("Content,Video title,Video publish time,Duration,Views,Watch time (hours),Subscribers,"
                 "Impressions,Impressions click-through rate (%),Average view duration,Average percentage viewed (%)\n"
                 "Total,,,,2000,60,12,50000,4.2,,\n"
                 "vidA,Habits,\"Oct 1, 2026\",540,1500,50,10,30000,5.1,0:02:40,29.6\n"
                 ",Sleep,\"Oct 10, 2026\",40,500,10,2,20000,2.9,0:00:31,77.5\n"
                 "zzz,Someone else,,,1,0,0,1,0,0:00:01,1\n", encoding="utf-8-sig")
    assert cli.main(["analytics", "--import", str(f)]) == 0
    out = capsys.readouterr().out
    assert "2 ролик(ов)" in out and "пропущены): zzz" in out
    by = {r["project"]: r for r in analytics.stored(ws).values()}
    a, b = by["habits"]["metrics"], by["sleep"]["metrics"]  # sleep — по названию
    assert (a["views"], a["ctr"], a["avg_view_s"], a["avg_view_pct"], a["watch_min"], a["impressions"]) == \
        (1500, 5.1, 160, 29.6, 3000, 30000)
    assert b["views"] == 500 and b["avg_view_s"] == 31 and by["habits"]["sources"]["ctr"] == \
        f"csv Table data.csv {analytics.today()}"
    with pytest.raises(SystemExit, match="метрика=число"):
        cli.main(["analytics", "--set", "https://www.tiktok.com/@n/video/123", "views=много"])
    with pytest.raises(SystemExit, match="нет среди опубликованных"):
        cli.main(["analytics", "--set", "https://www.tiktok.com/@n/video/999", "views=1"])
    assert cli.main(["analytics", "--set", "https://www.tiktok.com/@n/video/123", "views=4100",
                     "avg_view_pct=61", "ret_3s=88"]) == 0
    by = {r["project"]: r for r in analytics.stored(ws).values()}
    assert by["coffee"]["metrics"] == {"views": 4100, "avg_view_pct": 61, "ret_3s": 88}
    assert by["habits"]["metrics"]["views"] == 1500  # цифры копятся между запусками
    rep = (ws.root / "analytics" / "REPORT.md").read_text(encoding="utf-8")
    assert "## Что зашло" in rep and "### Рубрики" in rep and "| Myth on Trial ⚠️ мало данных | 1 | 1 500 |" in rep
    assert "| Shorts ≤ 1 мин ⚠️ мало данных | 2 | 2 300 |" in rep  # медиана 500 и 4100
    assert "Больше всего просмотров: coffee (без рубрики, Shorts ≤ 1 мин) — 4 100, досмотр 61 %" in rep
    assert "Лучшая длина: Shorts ≤ 1 мин — медиана 2 300 просмотров (n=2) против 1 500 у «5–15 мин» (n=1)" in rep
    assert "Лучший хук: «Coffee wakes you up?» (coffee) — 88 % зрителей на 3-й секунде" in rep
    assert "Роликов с цифрами 3 (< 3)" not in rep
    capsys.readouterr()
    assert cli.main(["analytics", "--list"]) == 0
    assert "coffee → tiktok: просмотры 4 100, досмотр 61 %, на 3-й секунде 88 %" in capsys.readouterr().out


def test_published_record_gone_keeps_numbers(ws):
    rows = analytics.videos(ws)
    analytics._put(rows[0], {"views": 7}, "manual")
    analytics.save(ws, rows)
    (ws.root / "projects" / rows[0]["project"] / "published.yaml").write_text("[]\n", encoding="utf-8")
    again = {r["url"]: r for r in analytics.videos(ws)}
    assert again[rows[0]["url"]]["metrics"] == {"views": 7}

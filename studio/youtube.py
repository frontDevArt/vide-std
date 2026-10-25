"""Публикация через API (ROADMAP E2): YouTube Data API v3 — загрузка выхода приватным черновиком одной командой.

Студия загружает только после явного «да» человека в чате: `publish <проект> --out <выход> --api youtube` — карточка
(канал, название, видимость, время, отметка ИИ), `… --yes` — загрузка. Видимость по умолчанию `private`; `--at` —
отложенная публикация (`status.publishAt`, только у private). После загрузки — запись в `published.yaml` (E1).

Доступ — OAuth-клиент Google типа «Desktop» (Google Cloud → YouTube Data API v3 → Credentials):
- `YOUTUBE_CLIENT_SECRETS=<путь к client_secret_*.json>` (или `YOUTUBE_CLIENT_ID` + `YOUTUBE_CLIENT_SECRET`) —
  в `.env` студии или корня, через `workspace.secret`;
- `publish <проект> --api youtube --auth` — вход в браузере (PKCE, ответ на 127.0.0.1), refresh-токен и канал —
  в `.env.youtube.json` рядом с `.env` студии (в .gitignore по `.env.*`): у каждой студии свой канал.
Отметка ИИ (`status.containsSyntheticMedia`) — по правилу `package.ai_label` (да — реалистичное, что можно принять
за настоящее; нет — рисованная анимация и синтетический диктор), и «нет» тоже отвечается явно. Поставила ли её
videos.insert — не узнать (videos.list поле не отдаёт), поэтому после загрузки её ставит `videos.update` (видимость и
прочие поля status сохраняются), и она считается стоящей, только если YouTube вернул то же значение в ответе update;
нет — ❌ и код 1. `--check` — то же для уже загруженных роликов проекта. Токены никуда не печатаются. Сеть — только `urllib` (без google-api-python-client): `_http` подменяют тесты.
Квота (docs videos.insert, 2026-10): загрузка — 1 единица из корзины «Video Uploads», 100 загрузок в сутки.
TikTok и Instagram через API не загружаем: доступ к публикации даётся после проверки приложения площадкой — вручную (E1).
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import http.server
import json
import secrets
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from . import package, workspace
from .project import Project

# force-ssl — чтение канала и videos.update: отметку ИИ после videos.insert не подтвердить (videos.list её не отдаёт),
# поэтому её всегда ставим update и проверяем по его ответу (`disclose`)
SCOPES = ("https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl")
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
MUTABLE = ("privacyStatus", "embeddable", "license", "publicStatsViewable", "publishAt", "selfDeclaredMadeForKids")
STUDIO_AI = ("YouTube Studio → «Контент» → ролик → «Подробнее» → «AI use» / «Altered or synthetic content» → "
             "ответ как в карточке → сохранить")
PRIVACY = ("private", "unlisted", "public")
CATEGORY = "22"  # People & Blogs — умолчание YouTube; своё — package.category (27 — Education)
TRIES = 6        # попыток докачки после обрыва / 5xx


def supports(t: Project) -> bool:
    return package.platform(t)[0].id.startswith("youtube")


# ---------------------------------------------------------------- сеть
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # 308 Resume Incomplete — ответ протокола, а не переадресация
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _http(method: str, url: str, headers: dict | None = None, data=None, timeout: float = 120):
    """(статус, заголовки с ключами в нижнем регистре, тело). Ошибки HTTP — тоже ответ, обрыв — OSError."""
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with _opener.open(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def _sleep(s: float):
    time.sleep(s)


def _error(st: int, body: bytes, what: str) -> SystemExit:
    try:
        e = json.loads(body or b"{}")
    except ValueError:
        e = {}
    err = e.get("error")
    if isinstance(err, dict):
        reason = ",".join(x.get("reason", "") for x in err.get("errors") or []) or err.get("status", "")
        msg = f"{reason}: {err.get('message', '')}".strip(": ")
    else:
        msg = f"{err or ''} {e.get('error_description', '')}".strip()
    return SystemExit(f"YouTube API, {what}: HTTP {st}" + (f" — {msg}" if msg else ""))


def _form(url: str, fields: dict, what: str) -> dict:
    st, _, b = _http("POST", url, {"Content-Type": "application/x-www-form-urlencoded"}, urlencode(fields).encode())
    if st != 200:
        if b"invalid_grant" in (b or b""):
            raise SystemExit("YouTube: вход отозван или истёк (у приложения в статусе «Testing» токен живёт 7 дней) — "
                             "заново: python -m studio publish <проект> --api youtube --auth")
        raise _error(st, b, what)
    return json.loads(b)


# ---------------------------------------------------------------- доступ
def client(ws: workspace.Workspace) -> tuple[str, str]:
    """(client_id, client_secret) OAuth-клиента «Desktop» студии."""
    f = workspace.secret("YOUTUBE_CLIENT_SECRETS", ws)
    if f:
        p = Path(f).expanduser()
        if not p.is_file():
            raise SystemExit(f"YOUTUBE_CLIENT_SECRETS: нет файла {p}")
        d = json.loads(p.read_text(encoding="utf-8"))
        if "installed" not in d:
            raise SystemExit(f"{p.name}: нужен OAuth-клиент типа «Desktop app» (в файле — {', '.join(d) or 'пусто'})")
        return d["installed"]["client_id"], d["installed"]["client_secret"]
    cid, sec = workspace.secret("YOUTUBE_CLIENT_ID", ws), workspace.secret("YOUTUBE_CLIENT_SECRET", ws)
    if cid and sec:
        return cid, sec
    raise SystemExit("нет OAuth-клиента YouTube: впишите YOUTUBE_CLIENT_SECRETS=<путь к client_secret_*.json> в .env "
                     "студии или корня (имя — в .env.example)")


def token_path(ws: workspace.Workspace) -> Path:
    return ws.env.with_name(".env.youtube.json")


def token(ws: workspace.Workspace) -> dict:
    f = token_path(ws)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def channel(access: str) -> dict:
    st, _, b = _http("GET", CHANNELS_URL + "?part=snippet&mine=true", {"Authorization": f"Bearer {access}"})
    if st != 200:
        raise _error(st, b, "канал")
    items = json.loads(b).get("items") or []
    if not items:
        raise SystemExit("YouTube: у аккаунта нет канала — создайте его на youtube.com и войдите заново")
    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}


def auth(ws: workspace.Workspace, log=print, browse=webbrowser.open, wait: float = 300) -> dict:
    """Вход в Google в браузере (loopback + PKCE): refresh-токен и канал → token_path(ws)."""
    cid, sec = client(ws)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got: dict = {}

    class Reply(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            if "code" in q or "error" in q:
                got.update(q)
            ok = q.get("state") == state and "code" in q
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(("Готово, окно можно закрыть." if ok else "Вход не выполнен — см. терминал.").encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Reply)
    srv.timeout = 1
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = AUTH_URL + "?" + urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent", "code_challenge": challenge,
        "code_challenge_method": "S256", "state": state})
    log(f"🔑 Вход в YouTube для студии {ws.id}: откройте ссылку и выберите аккаунт канала (ждём {int(wait)} с)\n{url}")
    browse(url)
    end = time.monotonic() + wait
    try:
        while not got and time.monotonic() < end:
            srv.handle_request()
    finally:
        srv.server_close()
    if not got:
        raise SystemExit("YouTube: вход не завершён за отведённое время")
    if got.get("state") != state:
        raise SystemExit("YouTube: ответ входа не от этого запроса (state) — повторите --auth")
    if "error" in got:
        raise SystemExit(f"YouTube: вход отклонён — {got['error']}")
    tok = _form(TOKEN_URL, {"code": got["code"], "client_id": cid, "client_secret": sec, "redirect_uri": redirect,
                            "grant_type": "authorization_code", "code_verifier": verifier}, "вход")
    if not tok.get("refresh_token"):
        raise SystemExit("YouTube: Google не выдал refresh-токен — уберите доступ приложения в myaccount.google.com/"
                         "permissions и повторите --auth")
    ch = channel(tok["access_token"])
    rec = {"refresh_token": tok["refresh_token"], "scope": tok.get("scope", " ".join(SCOPES)),
           "channel_id": ch["id"], "channel_title": ch["title"],
           "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    f = token_path(ws)
    f.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✅ YouTube: канал «{ch['title']}» ({ch['id']}) — вход сохранён в {f.name} (в .gitignore)")
    return rec


def access(ws: workspace.Workspace) -> str:
    rt = token(ws).get("refresh_token")
    if not rt:
        raise SystemExit("YouTube: вход не выполнен — python -m studio publish <проект> --api youtube --auth")
    cid, sec = client(ws)
    return _form(TOKEN_URL, {"refresh_token": rt, "client_id": cid, "client_secret": sec,
                             "grant_type": "refresh_token"}, "обновление токена")["access_token"]


# ---------------------------------------------------------------- ролик
def _when(at: str | None) -> str | None:
    """«ГГГГ-ММ-ДД ЧЧ:ММ» местного времени → RFC 3339 для publishAt; в прошлом — ошибка."""
    if not at:
        return None
    try:
        dt = datetime.datetime.strptime(at, "%Y-%m-%d %H:%M").astimezone()
    except ValueError:
        raise SystemExit(f"--at: время как «ГГГГ-ММ-ДД ЧЧ:ММ», получено: {at!r}")
    if dt <= datetime.datetime.now().astimezone():
        raise SystemExit(f"--at {at}: время уже прошло — отложенная публикация только в будущем")
    return dt.isoformat(timespec="seconds")


def meta(t: Project, privacy: str = "private", at: str | None = None) -> tuple[dict, list[str]]:
    """Ресурс video для videos.insert из пакета выхода: (тело, предупреждения)."""
    if privacy not in PRIVACY:
        raise SystemExit(f"--privacy: {' | '.join(PRIVACY)}, получено: {privacy!r}")
    when = _when(at)
    if when and privacy != "private":
        raise SystemExit("--at: отложенная публикация только у --privacy private (YouTube откроет ролик сам в срок)")
    pk = package.settings(t)
    title, text = package.texts(t)
    warns = []
    if any(c in title + text for c in "<>"):  # API отклоняет «<» и «>» в названии и описании
        warns.append("«<» и «>» в названии или описании заменены на «‹ ›» — YouTube их не принимает")
        title, text = (s.replace("<", "‹").replace(">", "›") for s in (title, text))
    lang = t.cfg["language"]
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": bool(pk.get("made_for_kids", False)),
              "containsSyntheticMedia": package.ai_label(t)[0]}
    if when:
        status["publishAt"] = when
    body = {"snippet": {"title": title, "description": text, "categoryId": str(pk.get("category", CATEGORY)),
                        "defaultLanguage": lang, "defaultAudioLanguage": lang},
            "status": status}
    return body, warns


def card(t: Project, privacy: str = "private", at: str | None = None, log=print) -> bool:
    """Карточка загрузки через API: что уйдёт на канал. True — можно загружать (ворота пройдены, вход есть)."""
    from .publish import gates
    errs, warns = gates(t, log=lambda *_: None)
    nm = package.name(t)
    video = t.output_dir() / f"{nm}.mp4"
    ch = token(t.ws)
    log(f"📤 {nm} → YouTube API: {video}")
    if not ch.get("refresh_token"):
        errs.append(f"вход не выполнен — python -m studio publish {t.slug} --api youtube --auth")
    elif not can_disclose(ch):
        errs.append("вход без права менять ролик — отметку ИИ не поставить и не проверить; войти заново: "
                    f"python -m studio publish {t.slug} --api youtube --auth")
    if not errs:
        body, w = meta(t, privacy, at)
        warns += w
        st = body["status"]
        log(f"  Канал: «{ch['channel_title']}» ({ch['channel_id']}), студия {t.ws.id}")
        log(f"  Название: {body['snippet']['title']}")
        log(f"  Описание: {len(body['snippet']['description'])} символов из {nm}.description.md")
        log(f"  Видимость: {privacy}" + (f", публикация {at} ({st['publishAt']})" if at else "")
            + f"; категория {body['snippet']['categoryId']}, язык {body['snippet']['defaultLanguage']}")
        log(f"  Файл: {video.name}, {video.stat().st_size / 2**20:.1f} МБ; обложка {nm}.cover.jpg")
        log(f"  Отметка ИИ (containsSyntheticMedia): {'ДА' if st['containsSyntheticMedia'] else 'нет'} — "
            f"{package.ai_label(t)[1]}; ставится и подтверждается после загрузки")
        log(f"  Для детей: {'да' if st['selfDeclaredMadeForKids'] else 'нет'}")
    for x in errs:
        log(f"  ❌ {x}")
    for x in warns:
        log(f"  ⚠️ {x}")
    if errs:
        log("  Не загружать: сначала исправить ❌.")
        return False
    log("  Загрузить — только после «да» в чате: python -m studio publish " + t.slug
        + (f" --out {t.out}" if t.out else "") + " --api youtube --yes"
        + (f" --privacy {privacy}" if privacy != "private" else "") + (f' --at "{at}"' if at else ""))
    return True


def can_disclose(tok: dict) -> bool:
    return SCOPES[1] in (tok.get("scope") or "").split()


def status(tok: str, vid: str) -> dict:
    st, _, b = _http("GET", VIDEOS_URL + "?" + urlencode({"part": "status", "id": vid}),
                     {"Authorization": f"Bearer {tok}"})
    if st != 200:
        raise _error(st, b, "чтение ролика")
    items = json.loads(b).get("items") or []
    if not items:
        raise SystemExit(f"YouTube: ролик {vid} не найден на канале (удалён?)")
    return items[0]["status"]


def disclose(tok: str, vid: str, value: bool, log=print) -> bool:
    """Ответ «ИИ-контент: да/нет» на ролике — всегда videos.update. True — YouTube вернул то же значение в ответе update.
    Чтением не проверить: videos.list поле не возвращает никогда (живой прогон 2026-10-25: update отвечает
    `containsSyntheticMedia: true`, list сразу после — без поля; так же у github.com/onjoroge1/ai-video-gen/pull/188,
    где Studio показала «AI use: Yes»). Глазами — Studio, это последнее слово."""
    cur = status(tok, vid)
    # update перезаписывает изменяемые поля status: всё, что есть, отправляем обратно, иначе видимость сбросится
    new = {k: cur[k] for k in MUTABLE if k in cur}
    new["containsSyntheticMedia"] = value
    st, _, b = _http("PUT", VIDEOS_URL + "?part=status", {"Authorization": f"Bearer {tok}",
                     "Content-Type": "application/json; charset=UTF-8"},
                     json.dumps({"id": vid, "status": new}).encode())
    if st != 200:
        log(f"  ❌ отметка ИИ: {_error(st, b, 'videos.update').code}")
        return False
    got = json.loads(b or b"{}").get("status") or {}
    after = status(tok, vid)
    if after.get("privacyStatus") != cur.get("privacyStatus"):
        log(f"  ❌ видимость изменилась: {cur.get('privacyStatus')} → {after.get('privacyStatus')} — проверить в Studio")
        return False
    return got.get("containsSyntheticMedia") is value  # «нет» — тоже только явным false в ответе


def _send(session: str, video: Path, tok: str, log=print) -> dict:
    """Тело ролика в сессию resumable upload; обрыв и 5xx — запрос принятого и докачка остатка."""
    size, off = video.stat().st_size, 0
    for n in range(TRIES):
        hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4", "Content-Length": str(size - off)}
        if off:
            hdr["Content-Range"] = f"bytes {off}-{size - 1}/{size}"
        try:
            with open(video, "rb") as f:
                f.seek(off)
                st, _, b = _http("PUT", session, hdr, f, timeout=300)
        except OSError as e:
            st, b = None, str(e).encode()
        if st in (200, 201):
            return json.loads(b)
        if st is not None and st not in (308, 500, 502, 503, 504):
            raise _error(st, b, "загрузка")
        log(f"  ⚠️ загрузка прервана ({st or b.decode(errors='replace')}) — докачка, попытка {n + 2} из {TRIES}")
        _sleep(min(2 ** n, 30))
        st, h, b = _http("PUT", session, {"Authorization": f"Bearer {tok}", "Content-Length": "0",
                                          "Content-Range": f"bytes */{size}"}, b"")
        if st in (200, 201):
            return json.loads(b)
        if st == 404:
            raise SystemExit("YouTube: сессия загрузки истекла — запустите загрузку заново")
        if st != 308:
            raise _error(st, b, "проверка загрузки")
        rng = h.get("range")
        off = int(rng.rsplit("-", 1)[1]) + 1 if rng else 0
    raise SystemExit(f"YouTube: загрузка не удалась за {TRIES} попыток")


def upload(t: Project, privacy: str = "private", at: str | None = None, log=print) -> dict | None:
    """Загрузить выход на канал студии (вызывать только после «да» человека). Запись в published.yaml."""
    from . import publish
    errs, warns = publish.gates(t, log=lambda *_: None)
    if errs:
        log("❌ Не загружено:\n" + "\n".join(f"  ❌ {x}" for x in errs))
        return None
    body, w = meta(t, privacy, at)
    for x in warns + w:
        log(f"  ⚠️ {x}")
    ws = t.ws
    if not can_disclose(token(ws)):
        raise SystemExit("YouTube: вход без права менять ролик — отметку ИИ не поставить и не проверить, не загружаю; "
                         f"войти заново: python -m studio publish {t.slug} --api youtube --auth")
    tok = access(ws)
    nm = package.name(t)
    video = t.output_dir() / f"{nm}.mp4"
    st, h, b = _http("POST", UPLOAD_URL + "?" + urlencode({"uploadType": "resumable", "part": "snippet,status"}),
                     {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                      "X-Upload-Content-Length": str(video.stat().st_size), "X-Upload-Content-Type": "video/mp4"},
                     json.dumps(body, ensure_ascii=False).encode())
    if st != 200 or not h.get("location"):
        raise _error(st, b, "начало загрузки")
    log(f"⏫ {video.name} ({video.stat().st_size / 2**20:.1f} МБ) → «{token(ws).get('channel_title', '?')}»…")
    vid = _send(h["location"], video, tok, log)["id"]
    url = f"https://www.youtube.com/watch?v={vid}"
    cover = t.output_dir() / f"{nm}.cover.jpg"
    if cover.exists():
        st, _, b = _http("POST", THUMB_URL + "?" + urlencode({"videoId": vid}),
                         {"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"}, cover.read_bytes())
        if st != 200:
            log(f"  ⚠️ обложка не загружена ({_error(st, b, 'обложка').code}) — свою обложку YouTube разрешает "
                f"каналу, подтверждённому по телефону; поставить вручную в studio.youtube.com")
    extra = {"via": "api", "privacy": privacy, "video_id": vid}
    if at:
        extra["publish_at"] = at
    ai = body["status"]["containsSyntheticMedia"]
    extra["ai_label"] = ai
    extra["ai_confirmed"] = ok = disclose(tok, vid, ai, log)
    word = "ДА" if ai else "нет"
    log(f"  ✅ отметка ИИ-контента: {word} (подтверждено ответом videos.update; глазами — Studio → ролик → «AI use»)"
        if ok else f"  ❌ ОТМЕТКА ИИ-КОНТЕНТА НЕ ПОДТВЕРЖДЕНА (нужно: {word}) — до открытия ролика: {STUDIO_AI}; "
        f"потом: python -m studio publish {t.slug} --api youtube --check")
    return publish.record(t, url, note=f"YouTube API: {privacy}" + (f", публикация {at}" if at else ""),
                          extra=extra, log=log)


def check(proj: Project, log=print) -> bool:
    """Ролики проекта, загруженные через API: отметка ИИ — по правилу `package.ai_label` сейчас (да или явное нет),
    через videos.update с подтверждением; запись `ai_label` / `ai_confirmed` в published.yaml."""
    from . import publish
    recs = publish.load(proj)
    mine = [r for r in recs if r.get("via") == "api" and r.get("video_id")]
    if not mine:
        log(f"У {proj.slug} нет роликов, загруженных через API")
        return True
    if not can_disclose(token(proj.ws)):
        raise SystemExit("YouTube: вход без права менять ролик — войти заново: "
                         f"python -m studio publish {proj.slug} --api youtube --auth")
    tok = access(proj.ws)
    bad = 0
    for r in mine:
        t = proj.output(r["out"]) if r.get("out") else proj
        ai, why = package.ai_label(t)
        changed = r.get("ai_label") is not None and r["ai_label"] != ai
        r["ai_label"], r["ai_confirmed"] = ai, (ok := disclose(tok, r["video_id"], ai, log))
        bad += not ok
        word = "ДА" if ai else "нет"
        log(f"  {'✅' if ok else '❌'} {r['url']} ({r.get('privacy')}): отметка ИИ — {word}"
            + (" (изменена)" if changed else "") + f"; {why}" + ("" if ok else f" — НЕ подтверждена: {STUDIO_AI}"))
    publish._save(proj, recs)
    return not bad

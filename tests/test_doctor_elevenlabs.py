"""P1.7 (B9): `doctor` бесплатно проверяет ElevenLabs (/user, /voices/{id}), если ключ есть. Ключ не печатается.
Сеть не трогаем: `tts._el_urlopen` подменён."""
import argparse
import io
import json
import urllib.error

import pytest

from studio import cli, tts

KEY = "sk_test_0123456789abcdef"


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def net(monkeypatch):
    """Фальшивый API: ответы по пути; calls — список (путь, ключ из заголовка)."""
    calls, routes = [], {}

    def urlopen(req, timeout=None):
        path = req.full_url.removeprefix(tts.EL_API)
        calls.append((path, req.get_header("Xi-api-key")))
        code, body = routes.get(path, (404, {"detail": "not found"}))
        if code != 200:
            raise urllib.error.HTTPError(req.full_url, code, "err", {}, io.BytesIO(json.dumps(body).encode()))
        return Resp(json.dumps(body).encode())

    monkeypatch.setattr(tts, "_el_urlopen", urlopen)
    monkeypatch.setattr(tts, "probe", lambda *a, **k: (_ for _ in ()).throw(tts.TTSUnavailable("офлайн-тест")))
    monkeypatch.setattr(tts, "load_env", lambda: None)  # настоящий .env в тест не попадает
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    return calls, routes


def doctor(capsys):
    code = cli.cmd_doctor(argparse.Namespace(lang="en"))
    return code, capsys.readouterr().out


def el_line(out):
    return [ln for ln in out.splitlines() if "ElevenLabs" in ln]


USER = {"subscription": {"tier": "creator", "character_count": 12000, "character_limit": 100000}}


def test_no_key_no_requests(net, capsys):
    calls, _ = net
    code, out = doctor(capsys)
    assert calls == []
    assert el_line(out) and "⬜" in el_line(out)[0]
    assert "❌" not in el_line(out)[0]  # без ключа ElevenLabs не валит doctor


def test_key_and_voice_ok(net, capsys, monkeypatch):
    calls, routes = net
    monkeypatch.setenv("ELEVENLABS_API_KEY", KEY)
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "v123")
    routes.update({"/user": (200, USER), "/voices/v123": (200, {"name": "Brian"})})
    code, out = doctor(capsys)
    assert [p for p, _ in calls] == ["/user", "/voices/v123"] and all(k == KEY for _, k in calls)
    ln = el_line(out)[0]
    assert "✅" in ln and "Brian" in ln and "88000" in ln.replace(" ", "")  # остаток символов
    assert KEY not in out


def test_bad_key_fails_without_printing_it(net, capsys, monkeypatch):
    _, routes = net
    monkeypatch.setenv("ELEVENLABS_API_KEY", KEY)
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "v123")
    routes["/user"] = (401, {"detail": f"invalid api key {KEY}"})  # даже если API вернёт ключ в теле
    code, out = doctor(capsys)
    assert code == 1
    ln = el_line(out)[0]
    assert "❌" in ln and "401" in ln
    assert KEY not in out


def test_key_without_voice(net, capsys, monkeypatch):
    calls, routes = net
    monkeypatch.setenv("ELEVENLABS_API_KEY", KEY)
    routes["/user"] = (200, USER)
    code, out = doctor(capsys)
    assert [p for p, _ in calls] == ["/user"]
    assert code == 1 and "ELEVENLABS_VOICE_ID" in el_line(out)[0]


def test_unknown_voice(net, capsys, monkeypatch):
    _, routes = net
    monkeypatch.setenv("ELEVENLABS_API_KEY", KEY)
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "nope")
    routes["/user"] = (200, USER)
    code, out = doctor(capsys)
    assert code == 1 and "404" in el_line(out)[0]

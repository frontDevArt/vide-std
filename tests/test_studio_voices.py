"""ROADMAP A3: голос, языки и секреты на студию — свой `.env` студии главнее окружения и корневого, голоса по языкам
в studio.yaml (`voices:`), замеры темпа в `voices.yaml` студии, политика акцентов `max_accents`.
Готово, если: две студии с разными голосами ElevenLabs собирают ролик без правок project.yaml, кэш TTS не смешивается.
Сеть не трогаем: `tts._el_urlopen` подменён, «звук» — WAV из fake-синтеза."""
import argparse
import base64
import io
import json
import os
import shutil

import pytest
import yaml

from conftest import ROOT
from studio import calibration, cli, project, tts, voices, workspace

KEYS = {"acme": "sk_acme_0123456789", "beta": "sk_beta_9876543210"}
VOICES = {"acme": "voiceAcme000000000001", "beta": "voiceBeta000000000002"}


def _studio(base, sid, **cfg):
    d = base / "studios" / sid
    (d / "projects").mkdir(parents=True)
    (d / "studio.yaml").write_text(yaml.safe_dump({"name": sid, "kind": "client", "languages": ["en"], **cfg}),
                                   encoding="utf-8")
    return d


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Корень во временной папке: две студии-клиента с голосом ElevenLabs из своего `.env`."""
    shutil.copytree(ROOT / "projects" / "_template", tmp_path / "projects" / "_template")
    for sid in KEYS:
        d = _studio(tmp_path, sid, defaults={"language": "en", "format": "square"},
                    voices={"en": {"backend": "elevenlabs", "voice": "env:ELEVENLABS_VOICE_ID", "rate": 100},
                            "ru": {"backend": "fake"}})
        (d / ".env").write_text(f"ELEVENLABS_API_KEY={KEYS[sid]}\nELEVENLABS_VOICE_ID={VOICES[sid]}\n", encoding="utf-8")
    for k in ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "ELEVENLABS_MODEL_ID", "A3_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(workspace, "ROOT", tmp_path)
    with workspace.use(tmp_path):
        yield tmp_path


# ---------------------------------------------------------------- секреты
def test_secret_studio_env_then_process_then_root(base, monkeypatch):
    acme = workspace.studio("acme")
    (base / ".env").write_text("A3_KEY=root\n", encoding="utf-8")
    assert workspace.secret("A3_KEY", acme) == "root" and workspace.secret_source("A3_KEY", acme) == "корневой .env"
    monkeypatch.setenv("A3_KEY", "shell")
    assert workspace.secret("A3_KEY", acme) == "shell" and workspace.secret_source("A3_KEY", acme) == "окружение"
    (base / "studios" / "acme" / ".env").write_text("A3_KEY=acme\n", encoding="utf-8")
    assert workspace.secret("A3_KEY", acme) == "acme" and workspace.secret_source("A3_KEY", acme) == "свой .env"
    assert workspace.secret("A3_KEY", workspace.studio(None, base)) == "shell"  # default: окружение → .env, как раньше
    assert workspace.secret("NOPE", acme) == "" and workspace.secret_source("NOPE", acme) == "нет"


def test_secret_ignores_values_injected_by_load_env(base):
    """load_env кладёт .env первой студии в os.environ — для второй студии это не «окружение»."""
    workspace.load_env(workspace.studio("acme"))
    assert os.environ["ELEVENLABS_API_KEY"] == KEYS["acme"]
    assert workspace.secret("ELEVENLABS_API_KEY", workspace.studio("beta")) == KEYS["beta"]
    (base / "studios" / "beta" / ".env").unlink()
    assert workspace.secret("ELEVENLABS_API_KEY", workspace.studio("beta")) == ""  # не ключ acme из os.environ


# ---------------------------------------------------------------- голос по языку
def _new(sid, lang=None, slug="promo"):
    a = argparse.Namespace(topic="t", slug=slug, format=None, duration=None, lang=lang, tts=None, studio=sid)
    assert cli.cmd_new(a) == 0
    return workspace.studio(sid).project(slug)


def test_same_project_yaml_two_voices(base):
    pa, pb = _new("acme"), _new("beta")
    assert (pa / "project.yaml").read_text(encoding="utf-8") == (pb / "project.yaml").read_text(encoding="utf-8")
    a, b = project.load(pa).cfg["tts"], project.load(pb).cfg["tts"]
    assert (a["backend"], a["voice"], a["rate"]) == ("elevenlabs", VOICES["acme"], 100)
    assert (b["backend"], b["voice"], b["rate"]) == ("elevenlabs", VOICES["beta"], 100)
    assert KEYS["acme"] not in json.dumps(a) and KEYS["beta"] not in json.dumps(b)  # ключ в cfg не попадает


def test_voice_layer_by_language_and_precedence(base):
    p = _new("acme", lang="ru", slug="ru")
    assert project.load(p).cfg["tts"]["backend"] == "fake"  # voices.ru
    p = _new("acme", slug="own")
    y = yaml.safe_load((p / "project.yaml").read_text(encoding="utf-8"))
    y["tts"].update(voice="myVoice", rate=104)  # своё в project.yaml главнее голоса студии
    (p / "project.yaml").write_text(yaml.safe_dump(y), encoding="utf-8")
    t = project.load(p).cfg["tts"]
    assert (t["voice"], t["rate"]) == ("myVoice", 104)
    y["tts"] = {"backend": "fake", "voice": "auto"}  # другой бэкенд — голос студии не применяется целиком
    (p / "project.yaml").write_text(yaml.safe_dump(y), encoding="utf-8")
    t = project.load(p).cfg["tts"]
    assert (t["backend"], t["voice"], t["rate"]) == ("fake", "fake", 105)


def test_default_studio_unchanged(base):
    a = argparse.Namespace(topic="t", slug="plain", format=None, duration=None, lang=None, tts="fake")
    assert cli.cmd_new(a) == 0
    t = project.load(base / "projects" / "plain").cfg["tts"]
    assert (t["backend"], t["voice"], t["rate"]) == ("fake", "fake", "auto")


# ---------------------------------------------------------------- синтез: свой ключ, свой голос, свой кэш
class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def net(tmp_path, monkeypatch):
    """Фальшивый ElevenLabs: calls — (путь, ключ из заголовка); синтез отвечает WAV из fake-синтеза."""
    calls = []
    wav = tmp_path / "tone.wav"
    tts._fake("Hello there friend.", 100, wav)
    audio = base64.b64encode(wav.read_bytes()).decode()

    def urlopen(req, timeout=None):
        path = req.full_url.removeprefix(tts.EL_API)
        calls.append((path, req.get_header("Xi-api-key")))
        if "/text-to-speech/" in path:
            return Resp(json.dumps({"audio_base64": audio, "alignment": None}).encode())
        return Resp(json.dumps({"name": "v", "subscription": {}}).encode())

    monkeypatch.setattr(tts, "_el_urlopen", urlopen)
    return calls


def _script(p):
    (p / "script").mkdir(exist_ok=True)
    (p / "script" / "ch01.yaml").write_text(yaml.safe_dump({"scenes": [
        {"id": "s1", "template": "statement", "params": {"text": "Hello"}, "lines": ["Hello there friend."]}]}),
        encoding="utf-8")
    y = yaml.safe_load((p / "project.yaml").read_text(encoding="utf-8"))
    y["chapters"] = ["ch01"]
    (p / "project.yaml").write_text(yaml.safe_dump(y), encoding="utf-8")


def test_two_studios_voice_own_key_and_cache(base, net, capsys):
    pa, pb = _new("acme"), _new("beta")
    for p in (pa, pb):
        _script(p)
    for sid in KEYS:
        assert cli.main(["--studio", sid, "voice", "promo", "--yes"]) == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    for k in KEYS.values():
        assert k not in out  # секреты никогда не выводятся
    synth = [(path, key) for path, key in net if "/text-to-speech/" in path]
    assert {(path.split("/")[2], key) for path, key in synth} == {(VOICES[s], KEYS[s]) for s in KEYS}
    ta = {f.name for f in (pa / "build" / "tts").glob("*.wav")}
    tb = {f.name for f in (pb / "build" / "tts").glob("*.wav")}
    assert ta and tb and not ta & tb  # кэш TTS не смешивается: голос в ключе кэша
    n = len(net)
    assert cli.main(["--studio", "acme", "voice", "promo", "--yes"]) == 0
    assert not [c for c in net[n:] if "/text-to-speech/" in c[0]]  # повтор — из кэша, без платного синтеза


def test_cache_key_differs_by_voice_not_by_api_key():
    cfg = {"backend": "elevenlabs", "rate": 100}
    ka = tts.cache_key("Hi.", {**cfg, "voice": VOICES["acme"]}, 100)
    kb = tts.cache_key("Hi.", {**cfg, "voice": VOICES["beta"]}, 100)
    assert ka != kb


# ---------------------------------------------------------------- замеры темпа на студию
def test_calibration_saved_per_studio_and_used_by_new_project(base):
    pa = _new("acme")
    proj = project.load(pa)
    calibration.calibrate(proj, {"wpm_speech": 183.0, "rate": 100, "words": 120})
    data = yaml.safe_load((base / "studios" / "acme" / "voices.yaml").read_text(encoding="utf-8"))
    (m,) = data["measured"]
    assert (m["language"], m["backend"], m["wpm"], m["project"]) == ("en", "elevenlabs", 183.0, "promo")
    assert m["voice"] == voices.voice_hash(VOICES["acme"]) and VOICES["acme"] not in json.dumps(data)
    fresh = project.load(_new("acme", slug="next"))  # новый проект той же студии: замер с первого validate
    assert calibration.wpm(fresh) == (183.0, "замер голоса elevenlabs в студии acme")
    other = project.load(_new("beta"))  # у другой студии — другой голос: таблица языка
    assert calibration.wpm(other)[1] == "язык en"
    calibration.calibrate(proj, {"wpm_speech": 180.0, "rate": 100, "words": 120})  # обновляется, а не копится
    assert [r["wpm"] for r in yaml.safe_load((base / "studios" / "acme" / "voices.yaml")
                                             .read_text(encoding="utf-8"))["measured"]] == [180.0]


def test_calibration_not_saved_for_fake_or_default(base):
    assert not voices.save_measurement(workspace.studio("acme"), "en", "fake", "fake", 150)
    assert not voices.save_measurement(workspace.studio(None, base), "en", "piper", "x", 150)
    assert not (base / "voices.yaml").exists() and not (base / "studios" / "acme" / "voices.yaml").exists()


# ---------------------------------------------------------------- акценты и проверка studio.yaml
def test_max_accents_policy(base):
    from studio.validate import check
    p = _new("acme")
    lines = [{"text": f"Line {i}.", "voice": {"style": 0.3}} for i in range(2)]
    (p / "script").mkdir(exist_ok=True)
    (p / "script" / "ch01.yaml").write_text(yaml.safe_dump({"scenes": [
        {"id": "s1", "template": "statement", "params": {"text": "x"}, "lines": lines}]}), encoding="utf-8")
    y = yaml.safe_load((p / "project.yaml").read_text(encoding="utf-8"))
    y["chapters"] = ["ch01"]
    (p / "project.yaml").write_text(yaml.safe_dump(y), encoding="utf-8")

    def accent_warns():
        return [w for w in check(project.load(p)).warns if "акцент" in w]

    assert not accent_warns()  # 2 — по умолчанию можно
    cfg = yaml.safe_load((base / "studios" / "acme" / "studio.yaml").read_text(encoding="utf-8"))
    cfg["max_accents"] = 1
    (base / "studios" / "acme" / "studio.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    assert accent_warns() and "не больше 1" in accent_warns()[0]


def test_studios_command_checks_voices_without_secrets(base, capsys):
    cfg = yaml.safe_load((base / "studios" / "beta" / "studio.yaml").read_text(encoding="utf-8"))
    cfg["voices"]["xx"] = {"backend": "edge", "vioce": "x"}
    cfg["max_accents"] = -1
    (base / "studios" / "beta" / "studio.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    (base / "studios" / "beta" / ".env").write_text(f"ELEVENLABS_API_KEY={KEYS['beta']}\n", encoding="utf-8")
    assert cli.main(["studios"]) == 0
    out = capsys.readouterr().out
    assert "voices.xx: язык" in out and "vioce" in out and "max_accents" in out
    assert "voices.en: ELEVENLABS_VOICE_ID не задан" in out
    assert "голоса: en elevenlabs, ru fake" in out and "ключ ElevenLabs: свой .env" in out
    for k in list(KEYS.values()) + list(VOICES.values()):
        assert k not in out


def test_repo_nftm_voices():
    ws = workspace.studio("notes-from-the-mind")
    assert voices.layer(ws, "en") == {"backend": "elevenlabs", "voice": "env:ELEVENLABS_VOICE_ID", "rate": 100}
    assert voices.max_accents(ws) == 2
    assert not [w for w in voices.check(ws) if "не задан" not in w]  # без .env в тестах — только «не задан»

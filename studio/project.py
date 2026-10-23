"""Загрузка проекта ролика: project.yaml + script/*.yaml, пути build/qa."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import DEFAULTS, deep_merge, migrate, check  # DEFAULTS, deep_merge — старые имена
from . import brand, voices, workspace
from .workspace import ROOT as STUDIO_ROOT  # старое имя; пути данных — workspace.current()
VERSION = "0.3.0"

FORMATS = {
    "vertical": (1080, 1920),
    "horizontal": (1920, 1080),
    "square": (1080, 1080),
    "portrait": (1080, 1350),  # 4:5 — лента Instagram (ROADMAP B2)
}


def stable_hash(obj, n=12) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


@dataclass
class Project:
    root: Path
    cfg: dict
    chapters: list = field(default_factory=list)  # [(chapter_id, data)]

    # ---- paths
    @property
    def build(self) -> Path:
        p = self.root / "build"; p.mkdir(exist_ok=True); return p

    @property
    def qa_dir(self) -> Path:
        p = self.root / "qa"; p.mkdir(exist_ok=True); return p

    def bdir(self, *parts) -> Path:
        p = self.build.joinpath(*parts); p.mkdir(parents=True, exist_ok=True); return p

    @property
    def size(self):
        return FORMATS[self.cfg["format"]]

    @property
    def fps(self) -> int:
        return int(self.cfg["fps"])

    @property
    def slug(self) -> str:
        return self.root.name

    @property
    def ws(self) -> "workspace.Workspace":
        """Студия проекта: её `.env` (ключ и голос), `voices.yaml` (замеры темпа), правила."""
        return workspace.owner(self.root)

    def final_path(self) -> Path:
        return self.bdir("final") / f"{self.slug}.mp4"


def load(root) -> Project:
    root = Path(root).resolve()
    if not (root / "project.yaml").exists():
        try:
            root = resolve_project(root.name)  # slug: текущая студия, без --studio — все студии
        except SystemExit:
            pass  # пусть open ниже скажет, какого файла нет
    with open(root / "project.yaml", encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}
    for w in check(user):  # опечатка в ключе не должна молча игнорироваться (studio/config.py)
        print(f"⚠️  project.yaml: {w}")
    ws = workspace.owner(root)  # студия проекта (ROADMAP A1): её defaults и .env
    studio_defaults = ws.config.get("defaults") or {}
    for w in check(studio_defaults):
        print(f"⚠️  {ws.root.name}/studio.yaml, defaults: {w}")
    user, studio_defaults = migrate(user), migrate(studio_defaults)
    # голос студии для языка проекта (ROADMAP A3): DEFAULTS → defaults → voices[язык] → project.yaml
    lang = user.get("language") or studio_defaults.get("language") or DEFAULTS["language"]
    vl, ut = voices.merge_user(voices.layer(ws, lang), user.get("tts"))
    if "tts" in user:
        user["tts"] = ut
    cfg = deep_merge(DEFAULTS, deep_merge(studio_defaults, deep_merge({"tts": vl} if vl else {}, user)))
    cfg = brand.resolve(cfg, ws.root)  # style.brand → style.kit (ROADMAP A2)
    if 48000 % int(cfg["fps"]):
        raise SystemExit("fps должен делить 48000 (24/25/30/60)")
    tc = cfg["tts"]
    for k in ("voice", "model"):  # env:ИМЯ — из .env студии (свой голос клиента)
        if k in tc:
            tc[k] = voices.resolve_env(tc[k], ws)
    if tc["backend"] == "elevenlabs" and tc.get("voice") in (None, "auto", "env"):
        # голос студии — ELEVENLABS_VOICE_ID: свой .env студии, иначе корневой (ID голоса — не секрет, ключ — секрет)
        tc["voice"] = workspace.secret("ELEVENLABS_VOICE_ID", ws)
    if tc["backend"] == "elevenlabs" and not tc.get("model"):
        # модель студии — ELEVENLABS_MODEL_ID; входит в ключ кэша (tts.cache_key)
        if workspace.secret("ELEVENLABS_MODEL_ID", ws):
            tc["model"] = workspace.secret("ELEVENLABS_MODEL_ID", ws)
    if cfg["tts"]["backend"] == "fake" and cfg["tts"].get("voice") in (None, "auto"):
        cfg["tts"]["voice"] = "fake"  # голос не нужен; не берём из LANGS, чтобы doctor не считал fake «синтезом»
    if cfg["tts"].get("voice") in (None, "auto"):
        from .lang import default_voice
        v = default_voice(cfg["language"], cfg["tts"]["backend"])
        if not v:
            raise SystemExit(f"Нет голоса по умолчанию для языка '{cfg['language']}' и бэкенда "
                             f"{cfg['tts']['backend']}: укажите tts.voice в project.yaml")
        cfg["tts"]["voice"] = v
    proj = Project(root, cfg)
    for ch in cfg.get("chapters") or []:
        p = root / "script" / f"{ch}.yaml"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                proj.chapters.append((ch, yaml.safe_load(f) or {}))
    return proj


def resolve_project(arg: str | None) -> Path:
    """Аргумент может быть путём или slug из projects/ рабочей области (studio/workspace.py).
    Slug не в текущей студии и она `default` (нет `--studio`) — ищем во всех студиях.
    Без аргумента — текущий каталог."""
    if not arg:
        cwd = Path(os.getcwd())
        if (cwd / "project.yaml").exists():
            return cwd
        raise SystemExit("Укажите проект: python -m studio <cmd> projects/<slug>")
    p = Path(arg)
    if (p / "project.yaml").exists():
        return p.resolve()
    ws = workspace.current()
    q = ws.project(arg)
    if (q / "project.yaml").exists():
        return q
    if ws.id == workspace.DEFAULT and ws.root.resolve() == workspace.ROOT.resolve():
        found = workspace.find(arg)
        if len(found) == 1:
            return found[0]
        if found:
            ids = ", ".join(workspace.owner(f).id for f in found)
            raise SystemExit(f"Проект {arg} есть в нескольких студиях ({ids}): python -m studio --studio <id> …")
    raise SystemExit(f"Проект не найден: {arg}")

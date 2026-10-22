"""Загрузка проекта ролика: project.yaml + script/*.yaml, пути build/qa."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import DEFAULTS, deep_merge, migrate, check  # DEFAULTS, deep_merge — старые имена

STUDIO_ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.3.0"

FORMATS = {
    "vertical": (1080, 1920),
    "horizontal": (1920, 1080),
    "square": (1080, 1080),
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

    def final_path(self) -> Path:
        return self.bdir("final") / f"{self.slug}.mp4"


def load(root) -> Project:
    root = Path(root).resolve()
    if (root / "project.yaml").exists() is False and (STUDIO_ROOT / "projects" / str(root.name)).exists():
        root = STUDIO_ROOT / "projects" / root.name
    with open(root / "project.yaml", encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}
    for w in check(user):  # опечатка в ключе не должна молча игнорироваться (studio/config.py)
        print(f"⚠️  project.yaml: {w}")
    cfg = deep_merge(DEFAULTS, migrate(user))
    if 48000 % int(cfg["fps"]):
        raise SystemExit("fps должен делить 48000 (24/25/30/60)")
    if cfg["tts"]["backend"] == "elevenlabs" and cfg["tts"].get("voice") in (None, "auto", "env"):
        from .tts import load_env
        load_env()  # голос канала — ELEVENLABS_VOICE_ID в .env (ID голоса — не секрет, ключ — секрет)
        cfg["tts"]["voice"] = os.environ.get("ELEVENLABS_VOICE_ID", "")
    if cfg["tts"]["backend"] == "elevenlabs" and not cfg["tts"].get("model"):
        from .tts import load_env
        load_env()  # модель канала — ELEVENLABS_MODEL_ID в .env; входит в ключ кэша (tts.cache_key)
        if os.environ.get("ELEVENLABS_MODEL_ID", "").strip():
            cfg["tts"]["model"] = os.environ["ELEVENLABS_MODEL_ID"].strip()
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
    """Аргумент может быть путём или slug из projects/. Без аргумента — текущий каталог."""
    if not arg:
        cwd = Path(os.getcwd())
        if (cwd / "project.yaml").exists():
            return cwd
        raise SystemExit("Укажите проект: python -m studio <cmd> projects/<slug>")
    p = Path(arg)
    if (p / "project.yaml").exists():
        return p.resolve()
    q = STUDIO_ROOT / "projects" / arg
    if (q / "project.yaml").exists():
        return q
    raise SystemExit(f"Проект не найден: {arg}")

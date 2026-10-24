"""Загрузка проекта ролика: project.yaml + script/*.yaml, пути build/qa.

Выходы (ROADMAP B3): `deliverables: [youtube, tiktok]` в project.yaml — один сценарий и одна озвучка (`build/tts/`),
а формат, раскладка субтитров, `timeline.json`, рендер и QA — у каждого выхода свои (`Project.output`: `build/<выход>/`,
`qa/<выход>/`, финал — `output/<slug>/<выход>.mp4` в корне студии). Без `deliverables` — один выход в `build/`, как раньше.

Нарезка (ROADMAP B4, studio/cutdown.py; загрузка — studio/cutrefs.py): `cutdown: {source: <slug>}` — настройки
исходника под своими, сцены `from: chNN/sNN` — ссылки на сцены исходника, озвучка — кэш исходника (`Project.src`)."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import DEFAULTS, FORMATS, deep_merge, migrate, check  # DEFAULTS, deep_merge, FORMATS — старые имена
from . import brand, voices, workspace
from .workspace import ROOT as STUDIO_ROOT  # старое имя; пути данных — workspace.current()
VERSION = "0.3.0"



def stable_hash(obj, n=12) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


@dataclass
class Project:
    root: Path
    cfg: dict
    chapters: list = field(default_factory=list)  # [(chapter_id, data)]
    out: str | None = None  # выход (площадка из deliverables, ROADMAP B3); None — проект без выходов
    src: Path | None = None  # исходник нарезки (ROADMAP B4): его build/tts/ — кэш озвучки нарезки

    # ---- paths
    @property
    def build(self) -> Path:
        p = self.root / "build"
        if self.out:
            p = p / self.out
        p.mkdir(parents=True, exist_ok=True); return p

    @property
    def qa_dir(self) -> Path:
        p = self.root / "qa"
        if self.out:
            p = p / self.out
        p.mkdir(parents=True, exist_ok=True); return p

    def bdir(self, *parts) -> Path:
        # озвучка общая для всех выходов: build/tts/, а не build/<выход>/tts/; у нарезки — build/tts/ исходника
        base = (self.src or self.root) / "build" if parts[:1] == ("tts",) else self.build
        p = base.joinpath(*parts); p.mkdir(parents=True, exist_ok=True); return p

    # ---- выходы (ROADMAP B3)
    @property
    def outputs(self) -> list[str]:
        """Площадки из `deliverables` (у выхода — пусто: выход не делится дальше)."""
        d = self.cfg.get("deliverables") or []
        return [] if self.out else [d] if isinstance(d, str) else list(d)

    def output(self, oid: str) -> "Project":
        """Выход `oid`: тот же сценарий и озвучка, площадка — `oid`, формат — проекта, если площадка его принимает,
        иначе основной формат площадки; свои build/<oid>/ и qa/<oid>/."""
        from .platforms import get
        try:
            p = get(oid)
        except KeyError as e:
            raise SystemExit(f"deliverables: {e.args[0]}")
        cfg = copy.deepcopy(self.cfg)
        cfg["platform"] = oid
        if cfg["format"] not in p.formats:
            cfg["format"] = p.formats[0]
        return Project(self.root, cfg, self.chapters, oid, self.src)

    def targets(self, out: str | None = None) -> list["Project"]:
        """Что собирает команда: `--out <выход>` — этот выход; без флага — все выходы, без deliverables — сам проект."""
        if out:
            if out not in self.outputs:
                raise SystemExit(f"Выхода {out} нет в deliverables проекта: {', '.join(self.outputs) or 'их нет'}")
            return [self.output(out)]
        return [self.output(o) for o in self.outputs] or [self]

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

    def output_dir(self) -> Path:
        """Папка выходов проекта: output/<slug>/ в корне студии; проект вне projects/ студии (тесты, чужая папка) —
        output/<slug>/ внутри самого проекта."""
        ws = self.ws
        base = ws.root if ws.projects.resolve() == self.root.parent.resolve() else self.root
        return base / "output" / self.slug

    def final_path(self) -> Path:
        """Финал: build/final/<slug>.mp4, у выхода — output/<slug>/<выход>.mp4 в корне студии (рядом .srt/.vtt)."""
        if self.out:
            d = self.output_dir()
            d.mkdir(parents=True, exist_ok=True)
            return d / f"{self.out}.mp4"
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
    src = src_user = None
    if isinstance(user.get("cutdown"), dict) and user["cutdown"].get("source"):  # нарезка (ROADMAP B4)
        from . import cutrefs
        src = cutrefs.source_root(root, str(user["cutdown"]["source"]), resolve_project)
        src_user = migrate(cutrefs.read_yaml(src / "project.yaml"))
        user = cutrefs.inherit(src_user, user)
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
    if cfg["tts"]["backend"] == "none":  # ролик без голоса (ROADMAP C1, studio/kinds.py): синтеза нет
        cfg["tts"]["voice"] = "none"
    if cfg["tts"]["backend"] == "fake" and cfg["tts"].get("voice") in (None, "auto"):
        cfg["tts"]["voice"] = "fake"  # голос не нужен; не берём из LANGS, чтобы doctor не считал fake «синтезом»
    if cfg["tts"].get("voice") in (None, "auto"):
        from .lang import default_voice
        v = default_voice(cfg["language"], cfg["tts"]["backend"])
        if not v:
            raise SystemExit(f"Нет голоса по умолчанию для языка '{cfg['language']}' и бэкенда "
                             f"{cfg['tts']['backend']}: укажите tts.voice в project.yaml")
        cfg["tts"]["voice"] = v
    proj = Project(root, cfg, src=src)
    for ch in cfg.get("chapters") or []:
        p = root / "script" / f"{ch}.yaml"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                proj.chapters.append((ch, yaml.safe_load(f) or {}))
    if src:
        from . import cutrefs
        proj.chapters = cutrefs.resolve(proj.chapters, cutrefs.source_chapters(src, src_user), src.name)
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

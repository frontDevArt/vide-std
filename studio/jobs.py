"""Очередь задач студии (ROADMAP D2): одна на машину, лог на задачу, возобновление после прерывания.

Задача — команда студии (`python -m studio <argv>`), например `all <путь проекта> --yes`. Лежит файлом
`jobs/<id>.json` в корне студии (не в git): id — время постановки, порядок id = порядок выполнения. Статусы:
`queued` → `running` → `done` (код 0) | `failed`. Вывод задачи — `jobs/<id>.log` (команда пишет и свой лог проекта).

Исполнитель один на машину: `jobs/runner.lock` с PID. Замок живого процесса — второй исполнитель не стартует;
замок мёртвого (выключили свет, закрыли окно) — снимается, а его задачи `running` снова `queued`: команды студии
кэшируют всё сделанное (озвучка, сцены), повтор продолжает с места обрыва. Ctrl+C — текущая задача снова `queued`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .workspace import ROOT

DIR = ROOT / "jobs"
STATUSES = ("queued", "running", "done", "failed")
ACTIVE = ("queued", "running")


def _dir(d=None) -> Path:
    return Path(d) if d else DIR


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _save(job, d=None):
    p = _dir(d) / f"{job['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.part")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def load(d=None) -> list[dict]:
    """Все задачи по порядку постановки."""
    out = []
    for p in sorted(_dir(d).glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):  # недописанный файл чужого процесса — пропустить до следующего чтения
            continue
    return out


def get(jid, d=None) -> dict:
    p = _dir(d) / f"{jid}.json"
    if not p.exists():
        raise KeyError(jid)
    return json.loads(p.read_text(encoding="utf-8"))


def log_path(job, d=None) -> Path:
    return _dir(d) / f"{job['id']}.log"


def add(argv, title="", d=None) -> tuple[dict, bool]:
    """Поставить команду в очередь. Та же команда уже ждёт или идёт — вернуть её (второй раз не ставится).
    → (задача, новая ли)."""
    argv = [str(x) for x in argv]
    for j in load(d):
        if j["argv"] == argv and j["status"] in ACTIVE:
            return j, False
    jid = time.strftime("%Y%m%d-%H%M%S")
    n, taken = 1, {p.stem for p in _dir(d).glob("*.json")}
    while f"{jid}-{n:02d}" in taken:
        n += 1
    job = {"id": f"{jid}-{n:02d}", "argv": argv, "title": title or " ".join(argv), "status": "queued",
           "created": _now(), "started": None, "finished": None, "rc": None, "runs": 0}
    _save(job, d)
    return job, True


def retry(jid, d=None) -> dict:
    """Упавшую (или сделанную) задачу — снова в очередь."""
    j = get(jid, d)
    if j["status"] in ACTIVE:
        return j
    j.update(status="queued", rc=None, finished=None)
    _save(j, d)
    return j


def clear(d=None, statuses=("done",)) -> int:
    """Убрать задачи с этими статусами (и их логи). → сколько убрано."""
    n = 0
    for j in load(d):
        if j["status"] in statuses:
            (_dir(d) / f"{j['id']}.json").unlink(missing_ok=True)
            log_path(j, d).unlink(missing_ok=True)
            n += 1
    return n


# ---------------------------------------------------------------- исполнитель
def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":  # os.kill(pid, 0) на Windows не проверка, а TerminateProcess
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def runner_pid(d=None) -> int | None:
    """PID живого исполнителя или None."""
    f = _dir(d) / "runner.lock"
    try:
        pid = int(f.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return None
    return pid if _alive(pid) else None


def _lock(d=None) -> bool:
    """Занять замок исполнителя. Чужой живой — False; мёртвый — снять."""
    f = _dir(d) / "runner.lock"
    f.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(f, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if runner_pid(d):
                return False
            f.unlink(missing_ok=True)  # замок мёртвого процесса
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            h.write(str(os.getpid()))
        return True
    return False


def _unlock(d=None):
    f = _dir(d) / "runner.lock"
    try:
        if int(f.read_text(encoding="utf-8").strip() or 0) == os.getpid():
            f.unlink()
    except (OSError, ValueError):
        pass


def _resume(d=None, log=print, poll=5.0) -> int:
    """`running` без живого исполнителя (обрыв) → снова `queued`. Процесс задачи пережил исполнителя (убили только
    его) — дождаться конца: два рендера одного проекта разом портят build/."""
    n = 0
    for j in load(d):
        if j["status"] == "running":
            if j.get("pid") and _alive(j["pid"]):
                log(f"… {j['id']} {j['title']}: процесс {j['pid']} ещё работает без исполнителя — ждём")
                while _alive(j["pid"]):
                    time.sleep(poll)
            j["status"] = "queued"
            _save(j, d)
            log(f"↻ {j['id']} {j['title']} — прервана, снова в очереди")
            n += 1
    return n


def command(argv) -> list[str]:
    """Как запускается задача: та же студия тем же Python."""
    return [sys.executable, "-m", "studio", *argv]


def run(d=None, log=print, cmd=None) -> dict | None:
    """Выполнить очередь до конца (задачи, поставленные по ходу, тоже). → счётчики {done, failed} или None,
    если уже работает другой исполнитель."""
    if not _lock(d):
        log(f"Очередь уже выполняет процесс {runner_pid(d)} — новые задачи он возьмёт сам.")
        return None
    res = {"done": 0, "failed": 0}
    cmd = cmd or command
    try:
        _resume(d, log)
        while True:
            nxt = next((j for j in load(d) if j["status"] == "queued"), None)
            if nxt is None:
                break
            ok = _run_one(nxt, d, log, cmd)
            res["done" if ok else "failed"] += 1
    finally:
        _unlock(d)
    return res


def _run_one(job, d, log, cmd) -> bool:
    job.update(status="running", started=_now(), finished=None, rc=None, runs=job.get("runs", 0) + 1)
    _save(job, d)
    lp = log_path(job, d)
    log(f"▶ {job['id']} {job['title']}  (лог: {lp})")
    t0 = time.time()
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    with open(lp, "a", encoding="utf-8") as fh:
        fh.write(f"=== {_now()} запуск {job['runs']}: {' '.join(job['argv'])}\n")
        fh.flush()
        p = subprocess.Popen(cmd(job["argv"]), cwd=ROOT, stdin=subprocess.DEVNULL, stdout=fh,
                             stderr=subprocess.STDOUT, env=env)
        job["pid"] = p.pid
        _save(job, d)
        try:
            rc = p.wait()
        except BaseException:  # Ctrl+C: задачу не терять — снова в очередь, процесс остановить
            p.kill()
            p.wait()
            job.update(status="queued", started=None)
            _save(job, d)
            fh.write(f"=== {_now()} прервано\n")
            raise
        fh.write(f"=== {_now()} код {rc}\n")
    job.update(status="done" if rc == 0 else "failed", rc=rc, finished=_now())
    _save(job, d)
    log(f"{'✅' if rc == 0 else '❌'} {job['id']} код {rc} за {time.time() - t0:.0f} c")
    return rc == 0


def table(jobs) -> str:
    if not jobs:
        return "Очередь пуста."
    mark = {"queued": "⏳", "running": "▶", "done": "✅", "failed": "❌"}
    rows = [f"{mark[j['status']]} {j['id']}  {j['status']:<7}  {j['title']}"
            + (f"  (код {j['rc']})" if j["status"] == "failed" else "") for j in jobs]
    return "\n".join(rows)

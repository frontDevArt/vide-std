"""ROADMAP D2: очередь задач — одна на машину, лог на задачу, возобновление после прерывания (studio/jobs.py).
Задачи — заглушка `python -c` с кодом выхода, без рендера."""
import json
import subprocess
import sys

import pytest

from studio import jobs


def stub(argv):
    """Задача `["exit", "N"]` — процесс с кодом N, печатает свой argv в лог."""
    return [sys.executable, "-c", "import sys; print('job', sys.argv[1:]); sys.exit(int(sys.argv[2]))", *argv]


def test_add_dedups_active(tmp_path):
    a, new_a = jobs.add(["exit", "0"], d=tmp_path)
    b, new_b = jobs.add(["exit", "0"], d=tmp_path)
    c, _ = jobs.add(["exit", "1"], d=tmp_path)
    assert new_a and not new_b and a["id"] == b["id"] != c["id"]
    assert [j["id"] for j in jobs.load(tmp_path)] == [a["id"], c["id"]]  # порядок постановки


def test_run_logs_and_statuses(tmp_path):
    ok, _ = jobs.add(["exit", "0"], title="good", d=tmp_path)
    bad, _ = jobs.add(["exit", "3"], title="bad", d=tmp_path)
    out = []
    assert jobs.run(tmp_path, log=out.append, cmd=stub) == {"done": 1, "failed": 1}
    st = {j["id"]: j for j in jobs.load(tmp_path)}
    assert (st[ok["id"]]["status"], st[ok["id"]]["rc"]) == ("done", 0)
    assert (st[bad["id"]]["status"], st[bad["id"]]["rc"]) == ("failed", 3)
    log = jobs.log_path(bad, tmp_path).read_text(encoding="utf-8")
    assert "job ['exit', '3']" in log and "код 3" in log
    assert not (tmp_path / "runner.lock").exists()  # замок снят
    # повтор упавшей: снова в очередь, лог дописывается; та же команда, пока упала, ставится заново
    jobs.retry(bad["id"], tmp_path)
    assert jobs.get(bad["id"], tmp_path)["status"] == "queued"
    jobs.run(tmp_path, log=out.append, cmd=stub)
    j = jobs.get(bad["id"], tmp_path)
    assert j["runs"] == 2 and jobs.log_path(j, tmp_path).read_text(encoding="utf-8").count("запуск") == 2
    assert jobs.clear(tmp_path) == 1 and jobs.clear(tmp_path, ("failed",)) == 1 and jobs.load(tmp_path) == []
    assert not list(tmp_path.glob("*.log"))


def test_resume_after_crash(tmp_path):
    """Обрыв: замок мёртвого процесса и задача `running` — новый исполнитель снимает замок и делает её снова."""
    j, _ = jobs.add(["exit", "0"], d=tmp_path)
    j.update(status="running", runs=1)
    (tmp_path / f"{j['id']}.json").write_text(json.dumps(j), encoding="utf-8")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (tmp_path / "runner.lock").write_text(str(dead.pid), encoding="utf-8")
    assert jobs.runner_pid(tmp_path) is None
    out = []
    assert jobs.run(tmp_path, log=out.append, cmd=stub) == {"done": 1, "failed": 0}
    assert any("прервана" in x for x in out)
    assert jobs.get(j["id"], tmp_path)["runs"] == 2


def test_one_runner_per_machine(tmp_path):
    """Живой исполнитель — второй не стартует, задачи не трогает."""
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (tmp_path / "runner.lock").write_text(str(p.pid), encoding="utf-8")
        j, _ = jobs.add(["exit", "0"], d=tmp_path)
        out = []
        assert jobs.run(tmp_path, log=out.append, cmd=stub) is None
        assert jobs.runner_pid(tmp_path) == p.pid and "уже выполняет" in out[0]
        assert jobs.get(j["id"], tmp_path)["status"] == "queued"
    finally:
        p.kill()
        p.wait()


def test_interrupt_requeues(tmp_path, monkeypatch):
    """Ctrl+C во время задачи: процесс остановлен, задача снова `queued`, замок снят."""
    j, _ = jobs.add(["exit", "0"], d=tmp_path)

    class Popen:
        pid = 0

        def __init__(self, *a, **k):
            self.killed = False

        def wait(self):
            if not self.killed:
                raise KeyboardInterrupt
            return -9

        def kill(self):
            self.killed = True

    monkeypatch.setattr(jobs.subprocess, "Popen", Popen)
    with pytest.raises(KeyboardInterrupt):
        jobs.run(tmp_path, log=lambda *_: None, cmd=stub)
    assert jobs.get(j["id"], tmp_path)["status"] == "queued"
    assert not (tmp_path / "runner.lock").exists()


def test_resume_waits_for_orphan(tmp_path):
    """Убили только исполнителя, процесс задачи ещё идёт — новый исполнитель ждёт его конца, потом повторяет."""
    orphan = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])
    j, _ = jobs.add(["exit", "0"], d=tmp_path)
    j.update(status="running", pid=orphan.pid)
    (tmp_path / f"{j['id']}.json").write_text(json.dumps(j), encoding="utf-8")
    out = []
    jobs._resume(tmp_path, log=out.append, poll=0.1)
    assert orphan.poll() is not None and "ждём" in out[0]
    assert jobs.get(j["id"], tmp_path)["status"] == "queued"

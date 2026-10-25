"""Ревью с комментариями по таймкодам (ROADMAP D1): `python -m studio review <проект>`.

Локальная страница (stdlib `http.server`, только 127.0.0.1): видео черновика (`assemble --draft`, иначе финал),
список сцен из timeline.json. Клик по видео — пауза и комментарий: секунда ролика, сцена, точка кадра (доли W×H)
→ `review/comments.json` в папке проекта (у выхода B3 — `review/<выход>/`). Это вход проекта, как script/: лежит в git.
Кнопка «Скопировать для Claude» — текст открытых комментариев; статус версии `draft` → `approved`.
`/review-fix` читает `review --list`, правит входы, рендерит `render --draft --scenes <сцены>` и закрывает `--done`.

Защита локального сервера: только 127.0.0.1, заголовок Host — свой адрес (DNS-rebinding), запись — только
`Content-Type: application/json` (чужая страница так не пошлёт без CORS-preflight, а его сервер не принимает).
"""
from __future__ import annotations

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .timing import load_timeline

STATUSES = ("draft", "approved")
HOST = "127.0.0.1"
PORT = 8765
MAX_TEXT = 2000


# ---------------------------------------------------------------- данные
def path(proj) -> Path:
    d = proj.root / "review"
    if proj.out:
        d = d / proj.out
    return d / "comments.json"


def load(proj) -> dict:
    p = path(proj)
    if not p.exists():
        return {"status": "draft", "comments": []}
    d = json.loads(p.read_text(encoding="utf-8"))
    d.setdefault("status", "draft")
    d.setdefault("comments", [])
    return d


def save(proj, data):
    p = path(proj)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def scenes(proj) -> list[dict]:
    """Сцены для страницы и привязки комментариев: глава, id, шаблон, начало и длительность в ролике, текст."""
    tl = load_timeline(proj)
    return [{"chapter": s["chapter"], "id": s["id"], "template": s["template"], "start": round(s["start"], 3),
             "dur": round(s["dur"], 3), "text": " ".join(l.get("text", "") for l in s.get("lines") or [])}
            for s in tl["scenes"]]


def scene_at(sc, t):
    """Сцена, на которую приходится секунда t ролика (после конца — последняя)."""
    for s in sc:
        if s["start"] <= t < s["start"] + s["dur"]:
            return s
    return sc[-1] if sc and t >= sc[-1]["start"] else (sc[0] if sc else None)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def add(proj, t, text, x=None, y=None, sc=None) -> dict:
    """Новый комментарий на секунде t ролика (x, y — точка кадра в долях 0..1). Версия снова `draft`."""
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        raise ValueError("пустой комментарий")
    t = float(t)
    s = scene_at(sc if sc is not None else scenes(proj), t)
    if s is None:
        raise ValueError("в ролике нет сцен")
    d = load(proj)
    n = max([int(c["id"][1:]) for c in d["comments"] if re.fullmatch(r"c\d+", c.get("id", ""))] + [0]) + 1
    c = {"id": f"c{n}", "t": round(t, 2), "chapter": s["chapter"], "scene": s["id"],
         "scene_t": round(max(0.0, t - s["start"]), 2), "text": text, "status": "open", "created": _now()}
    if x is not None and y is not None:
        c["x"], c["y"] = round(min(1.0, max(0.0, float(x))), 3), round(min(1.0, max(0.0, float(y))), 3)
    d["comments"].append(c)
    d["status"] = "draft"
    d.pop("approved", None)
    save(proj, d)
    return c


def update(proj, cid, **fields) -> dict:
    """Поменять текст или статус (`open` / `done`) комментария."""
    d = load(proj)
    for c in d["comments"]:
        if c["id"] == cid:
            if "text" in fields:
                text = (fields["text"] or "").strip()[:MAX_TEXT]
                if not text:
                    raise ValueError("пустой комментарий")
                c["text"] = text
            if "status" in fields:
                if fields["status"] not in ("open", "done"):
                    raise ValueError(f"статус комментария: open | done, не {fields['status']}")
                c["status"] = fields["status"]
                if c["status"] == "done":
                    c["done"] = _now()
                else:
                    c.pop("done", None)
            save(proj, d)
            return c
    raise KeyError(cid)


def delete(proj, cid):
    d = load(proj)
    keep = [c for c in d["comments"] if c["id"] != cid]
    if len(keep) == len(d["comments"]):
        raise KeyError(cid)
    d["comments"] = keep
    save(proj, d)


def set_status(proj, status) -> dict:
    """Статус версии: `approved` — только без открытых комментариев."""
    if status not in STATUSES:
        raise ValueError(f"статус версии: {' | '.join(STATUSES)}")
    d = load(proj)
    if status == "approved" and open_comments(d):
        raise ValueError(f"открытых комментариев: {len(open_comments(d))} — сначала правки")
    d["status"] = status
    if status == "approved":
        d["approved"] = _now()
    else:
        d.pop("approved", None)
    save(proj, d)
    return d


def open_comments(d) -> list[dict]:
    return [c for c in d["comments"] if c.get("status", "open") == "open"]


def scene_ids(comments) -> list[str]:
    """Сцены комментариев в порядке ролика без повторов: ['ch01/s02', …] — для `render --scenes`."""
    out = []
    for c in sorted(comments, key=lambda c: c["t"]):
        k = f"{c['chapter']}/{c['scene']}"
        if k not in out:
            out.append(k)
    return out


def _mmss(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def prompt(proj) -> str:
    """Текст для Claude: открытые комментарии с привязкой к сцене, файлам сценария и точке кадра."""
    d = load(proj)
    oc = sorted(open_comments(d), key=lambda c: c["t"])
    name = proj.slug + (f" (выход {proj.out})" if proj.out else "")
    if not oc:
        return f"Ревью {name}: открытых комментариев нет (версия: {d['status']})."
    lines = [f"Ревью {name}: открытых комментариев — {len(oc)}. Поправь входы (script/*.yaml, project.yaml) "
             f"только этих сцен и перерендери их (/review-fix {proj.slug}).", ""]
    for c in oc:
        pt = f", точка кадра {c['x']:.2f}×{c['y']:.2f} (доли ширины×высоты)" if "x" in c else ""
        lines.append(f"- [{c['id']}] {_mmss(c['t'])} — {c['chapter']}/{c['scene']} (script/{c['chapter']}.yaml, "
                     f"{c['scene_t']:.2f} c от начала сцены{pt}): {c['text']}")
    lines += ["", f"Сцены: {','.join(scene_ids(oc))}"]
    return "\n".join(lines)


def video(proj) -> Path | None:
    """Что смотреть: черновик сборки (build/final/<slug>.draft.mp4), иначе финал."""
    draft = proj.build / "final" / f"{proj.slug}.draft.mp4"
    if draft.exists():
        return draft
    final = proj.final_path()
    return final if final.exists() else None


# ---------------------------------------------------------------- сервер
class _Handler(BaseHTTPRequestHandler):
    proj = None
    video = None
    allowed = ()

    def log_message(self, fmt, *args):  # без строки на каждый запрос (видео идёт кусками Range)
        pass

    # -- ответы
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _error(self, code, msg):
        self._json({"error": msg}, code)

    def _host_ok(self):
        if self.headers.get("Host", "") not in self.allowed:
            self._error(403, "чужой Host")
            return False
        return True

    def _body(self):
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise ValueError("нужен Content-Type: application/json")
        n = int(self.headers.get("Content-Length") or 0)
        if n > 64 * 1024:
            raise ValueError("слишком большой запрос")
        return json.loads(self.rfile.read(n) or b"{}")

    # -- GET
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return
        p = self.path.split("?", 1)[0]
        if p == "/":
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if p == "/video.mp4":
            return self._video()
        if p == "/api/state":
            d = load(self.proj)
            return self._json({"project": self.proj.slug, "out": self.proj.out, "status": d["status"],
                               "approved": d.get("approved"), "comments": d["comments"], "scenes": scenes(self.proj),
                               "video": self.video.name, "size": list(self.proj.size),
                               "fps": self.proj.fps})
        if p == "/api/prompt":
            return self._send(200, prompt(self.proj).encode("utf-8"), "text/plain; charset=utf-8")
        self._error(404, "нет такого адреса")

    def _video(self):
        size = self.video.stat().st_size
        a, b = 0, size - 1
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        code, extra = 200, {"Accept-Ranges": "bytes"}
        if m and (m[1] or m[2]):
            if m[1]:
                a, b = int(m[1]), min(int(m[2]) if m[2] else size - 1, size - 1)
            else:  # bytes=-N — последние N байт
                a = max(0, size - int(m[2]))
            if a > b:
                return self._send(416, b"", "text/plain", {"Content-Range": f"bytes */{size}"})
            code, extra["Content-Range"] = 206, f"bytes {a}-{b}/{size}"
        n = b - a + 1
        self.send_response(code)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(n))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(self.video, "rb") as f:
            f.seek(a)
            while n > 0:
                chunk = f.read(min(n, 1 << 20))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):  # браузер перемотал и бросил запрос
                    return
                n -= len(chunk)

    # -- запись
    def _write(self, fn):
        if not self._host_ok():
            return
        try:
            self._json(fn())
        except KeyError as e:
            self._error(404, f"нет комментария {e.args[0]}")
        except (ValueError, TypeError) as e:
            self._error(400, str(e))

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        if p == "/api/comments":
            def fn():
                b = self._body()
                return add(self.proj, b["t"], b.get("text"), b.get("x"), b.get("y"))
            return self._write(fn)
        m = re.fullmatch(r"/api/comments/(c\d+)", p)
        if m:
            def fn():
                b = self._body()
                return update(self.proj, m[1], **{k: b[k] for k in ("text", "status") if k in b})
            return self._write(fn)
        if p == "/api/status":
            return self._write(lambda: set_status(self.proj, self._body().get("status")))
        self._host_ok() and self._error(404, "нет такого адреса")

    def do_DELETE(self):
        m = re.fullmatch(r"/api/comments/(c\d+)", self.path.split("?", 1)[0])
        if not m:
            return self._host_ok() and self._error(404, "нет такого адреса")

        def fn():
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                raise ValueError("нужен Content-Type: application/json")
            delete(self.proj, m[1])
            return {"deleted": m[1]}
        self._write(fn)


def make_server(proj, port=PORT, vid=None) -> ThreadingHTTPServer:
    """Сервер ревью на 127.0.0.1:port (0 — свободный порт). Видео — vid или `video(proj)`."""
    vid = vid or video(proj)
    if vid is None:
        raise SystemExit(f"Нечего смотреть: нет {proj.build / 'final' / (proj.slug + '.draft.mp4')} и финала. Сначала:\n"
                         f"  python -m studio render {proj.slug} --draft   (в фоне)\n"
                         f"  python -m studio assemble {proj.slug} --draft")
    handler = type("Handler", (_Handler,), {"proj": proj, "video": Path(vid)})
    srv = ThreadingHTTPServer((HOST, port), handler)
    real = srv.server_address[1]
    handler.allowed = (f"{HOST}:{real}", f"localhost:{real}")
    return srv


def url(srv) -> str:
    return f"http://{HOST}:{srv.server_address[1]}/"


# ---------------------------------------------------------------- страница
PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ревью</title>
<style>
:root{--bg:#0f1115;--panel:#181b22;--line:#2a2f3a;--text:#e8eaf0;--dim:#9aa3b2;--acc:#4fd1c5;--warn:#f6ad55;--ok:#68d391}
@media (prefers-color-scheme: light){:root{--bg:#f5f6f8;--panel:#fff;--line:#dde1e7;--text:#1a1d24;--dim:#5b6472;--acc:#0f8f86;--warn:#c05621;--ok:#2f855a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,sans-serif}
header{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line)}
header h1{font-size:16px;margin:0 auto 0 0}.badge{padding:2px 10px;border-radius:999px;border:1px solid var(--line)}
.badge.draft{color:var(--warn)}.badge.approved{color:var(--ok)}
button{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:6px 12px;cursor:pointer;font:inherit}
button.primary{background:var(--acc);border-color:var(--acc);color:#000}button:disabled{opacity:.45;cursor:default}
main{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:16px;padding:16px}
@media (max-width:900px){main{grid-template-columns:1fr}}
.stage{position:relative;align-self:start;background:#000;border-radius:10px;overflow:hidden}
video{display:block;width:100%;max-height:78vh;cursor:crosshair}
.pin{position:absolute;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;border:2px solid var(--warn);
 background:rgba(246,173,85,.25);color:#fff;font-size:11px;display:flex;align-items:center;justify-content:center;pointer-events:none}
.hint{color:var(--dim);font-size:12px;padding:6px 2px}
aside{display:flex;flex-direction:column;gap:12px;min-width:0}
.box{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px}
.box h2{font-size:13px;margin:0 0 8px;color:var(--dim);font-weight:600}
#form textarea{width:100%;min-height:70px;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px;font:inherit}
#form .meta{color:var(--dim);font-size:12px;margin-bottom:6px}#form .row{display:flex;gap:8px;margin-top:6px}
.c{border-top:1px solid var(--line);padding:8px 0}.c:first-of-type{border-top:0}
.c .head{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--dim)}.c .head a{color:var(--acc);cursor:pointer}
.c.done .txt{text-decoration:line-through;color:var(--dim)}.c .txt{margin:4px 0;white-space:pre-wrap;overflow-wrap:anywhere}
.c .acts{display:flex;gap:6px}.c .acts button{padding:2px 8px;font-size:12px}
.sc{display:grid;grid-template-columns:70px 1fr;gap:6px;padding:4px 6px;border-radius:6px;cursor:pointer;font-size:12px}
.sc:hover{background:var(--line)}.sc.on{outline:1px solid var(--acc)}.sc .t{color:var(--dim)}
.sc .n{color:var(--warn);margin-left:4px}#scenes{max-height:40vh;overflow:auto}
#toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--acc);color:#000;padding:8px 14px;border-radius:8px;display:none}
</style></head><body>
<header><h1 id="title">Ревью</h1><span id="status" class="badge"></span>
<button id="copy">Скопировать для Claude</button><button id="approve" class="primary">Утвердить версию</button></header>
<main><div><div class="stage" id="stage"><video id="v" src="/video.mp4" controls preload="metadata"></video></div>
<div class="hint">Клик по кадру — пауза и комментарий к этой секунде и точке. Пробел — пауза, ←/→ — кадр назад/вперёд.</div></div>
<aside><div class="box" id="form" hidden><h2>Новый комментарий</h2><div class="meta" id="fmeta"></div>
<textarea id="ftext" placeholder="Что поправить в этом месте?"></textarea>
<div class="row"><button class="primary" id="fsave">Сохранить</button><button id="fcancel">Отмена</button></div></div>
<div class="box"><h2 id="chead">Комментарии</h2><div id="comments"></div></div>
<div class="box"><h2>Сцены</h2><div id="scenes"></div></div></aside></main>
<div id="toast"></div>
<script>
const $=s=>document.querySelector(s),v=$('#v');let S={comments:[],scenes:[],fps:30},draft=null;
const mmss=t=>Math.floor(t/60)+':'+(t%60).toFixed(2).padStart(5,'0');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(m){const e=$('#toast');e.textContent=m;e.style.display='block';clearTimeout(e._t);e._t=setTimeout(()=>e.style.display='none',2200)}
async function api(method,url,body){const r=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
 const j=await r.json();if(!r.ok){toast(j.error||r.status);throw j}return j}
async function refresh(){S=await (await fetch('/api/state')).json();render()}
function sceneAt(t){return S.scenes.find(s=>t>=s.start&&t<s.start+s.dur)||S.scenes[S.scenes.length-1]}
function render(){
 $('#title').textContent='Ревью: '+S.project+(S.out?' · '+S.out:'')+' · '+S.video;
 const st=$('#status');st.textContent=S.status==='approved'?'утверждено '+(S.approved||''):'черновик';st.className='badge '+S.status;
 const open=S.comments.filter(c=>c.status!=='done');$('#approve').disabled=S.status==='approved'||open.length>0;
 $('#approve').title=open.length?'Сначала закройте открытые комментарии':'';
 $('#chead').textContent='Комментарии · открыто '+open.length+' из '+S.comments.length;
 const cs=[...S.comments].sort((a,b)=>a.t-b.t);
 $('#comments').innerHTML=cs.length?cs.map(c=>`<div class="c ${c.status==='done'?'done':''}"><div class="head"><b>${c.id}</b>
  <a data-seek="${c.t}">${mmss(c.t)}</a><span>${c.chapter}/${c.scene}</span></div><div class="txt">${esc(c.text)}</div>
  <div class="acts"><button data-tog="${c.id}">${c.status==='done'?'Открыть снова':'Готово'}</button><button data-del="${c.id}">Удалить</button></div></div>`).join('')
  :'<div class="hint">Пока нет. Кликните по кадру.</div>';
 const cnt={};open.forEach(c=>{const k=c.chapter+'/'+c.scene;cnt[k]=(cnt[k]||0)+1});
 $('#scenes').innerHTML=S.scenes.map(s=>{const k=s.chapter+'/'+s.id;return `<div class="sc" data-seek="${s.start}" data-k="${k}">
  <span class="t">${mmss(s.start)}</span><span><b>${k}</b> ${esc(s.template)}${cnt[k]?'<span class="n">● '+cnt[k]+'</span>':''}<br>${esc(s.text)}</span></div>`}).join('');
 pins()}
function box(){const r=v.getBoundingClientRect(),vw=v.videoWidth||S.size[0],vh=v.videoHeight||S.size[1];
 const k=Math.min(r.width/vw,r.height/vh);const w=vw*k,h=vh*k;return {r,w,h,x0:(r.width-w)/2,y0:(r.height-h)/2}}
function pins(){document.querySelectorAll('.pin').forEach(e=>e.remove());const b=box(),t=v.currentTime;
 S.comments.filter(c=>c.status!=='done'&&c.x!=null&&Math.abs(c.t-t)<0.6).forEach(c=>{const e=document.createElement('div');e.className='pin';
  e.textContent=c.id.slice(1);e.style.left=(b.x0+c.x*b.w)+'px';e.style.top=(b.y0+c.y*b.h)+'px';$('#stage').appendChild(e)});
 if(draft&&draft.x!=null){const e=document.createElement('div');e.className='pin';e.textContent='+';e.style.left=(b.x0+draft.x*b.w)+'px';e.style.top=(b.y0+draft.y*b.h)+'px';$('#stage').appendChild(e)}
 const s=sceneAt(t);document.querySelectorAll('.sc').forEach(e=>e.classList.toggle('on',s&&e.dataset.k===s.chapter+'/'+s.id))}
v.addEventListener('click',e=>{const b=box(),px=e.clientX-b.r.left-b.x0,py=e.clientY-b.r.top-b.y0;
 if(px<0||py<0||px>b.w||py>b.h||e.clientY>b.r.bottom-48)return; e.preventDefault();v.pause();const t=v.currentTime,s=sceneAt(t);
 draft={t,x:Math.min(1,Math.max(0,px/b.w)),y:Math.min(1,Math.max(0,py/b.h))};
 $('#fmeta').textContent=mmss(t)+' · '+(s?s.chapter+'/'+s.id:'')+' · точка '+draft.x.toFixed(2)+'×'+draft.y.toFixed(2);
 $('#form').hidden=false;$('#ftext').focus();pins()});
$('#fsave').onclick=async()=>{const text=$('#ftext').value.trim();if(!text)return toast('Пустой комментарий');
 await api('POST','/api/comments',{...draft,text});$('#ftext').value='';$('#form').hidden=true;draft=null;await refresh();toast('Сохранено')};
$('#fcancel').onclick=()=>{$('#form').hidden=true;draft=null;pins()};
$('#ftext').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey))$('#fsave').click()});
document.addEventListener('click',async e=>{const t=e.target.closest('[data-seek],[data-tog],[data-del]');if(!t)return;
 if(t.dataset.seek!=null){v.currentTime=+t.dataset.seek+0.001;return}
 if(t.dataset.tog){const c=S.comments.find(c=>c.id===t.dataset.tog);await api('POST','/api/comments/'+c.id,{status:c.status==='done'?'open':'done'});return refresh()}
 if(t.dataset.del&&confirm('Удалить '+t.dataset.del+'?')){await api('DELETE','/api/comments/'+t.dataset.del);refresh()}});
$('#copy').onclick=async()=>{const txt=await (await fetch('/api/prompt')).text();
 try{await navigator.clipboard.writeText(txt);toast('Скопировано — вставьте в чат Claude')}catch(_){prompt('Скопируйте:',txt)}};
$('#approve').onclick=async()=>{if(confirm('Утвердить эту версию?')){await api('POST','/api/status',{status:'approved'});refresh()}};
document.addEventListener('keydown',e=>{if(e.target.tagName==='TEXTAREA')return;
 if(e.key===' '){e.preventDefault();v.paused?v.play():v.pause()}
 if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();v.pause();v.currentTime+=(e.key==='ArrowLeft'?-1:1)/S.fps}});
v.addEventListener('timeupdate',pins);v.addEventListener('seeked',pins);window.addEventListener('resize',pins);v.addEventListener('loadedmetadata',pins);
refresh();
</script></body></html>
"""

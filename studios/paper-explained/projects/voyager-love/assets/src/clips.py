"""voyager-love: оживить арты сцен видеомоделью Kie (платно — только после «да» пользователя).

python studios/paper-explained/projects/voyager-love/assets/src/clips.py --plan          # смета, без денег
python studios/paper-explained/projects/voyager-love/assets/src/clips.py --yes s01 [s03…]  # генерация

Вход — арт сцены из кэша `images` (assets/images/<ключ>.png, role bg 9:16). Выход — assets/video/<сцена>.mp4 и кадры
assets/video/<сцена>/001.jpg… (24 к/с, 1080 по ширине) для ленты `.flip` (common.js). Задача Kie записывается в
assets/video/pending.json сразу после создания (деньги списаны): повтор докачивает её, а не платит заново.
Модель — Hailuo 2.3 Standard, 6 с, 1080P: 50 кредитов (200 = $1) за клип (kie.ai/hailuo-2-3, 2026-11-15)."""
import json
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).parent
PROJ = SRC.parents[1]
ROOT = PROJ.parents[3]
sys.path.insert(0, str(ROOT))
from studio import imagegen  # noqa: E402
from studio.project import load  # noqa: E402

MODEL, CREDITS = "hailuo/2-3-image-to-video-standard", 50
VID = PROJ / "assets" / "video"
PENDING = VID / "pending.json"
# движение: медленное, без новых предметов и без смены кадра — арт должен остаться узнаваемым
MOTION = {
    "s01": "Slow cinematic drift: the space probe glides very slowly toward the camera and turns a few degrees, the golden "
           "disc on its side catches a soft moving glint of light, stars twinkle faintly, gentle parallax of distant stars. "
           "Smooth, calm, no camera shake, no cuts, no new objects.",
    "s03": "Night time-lapse: the milky way and stars rotate slowly across the sky above the radio dish, a soft warm light "
           "pulses gently at the center of the dish as if sending a signal upward. Static tripod camera, smooth, no cuts.",
    "s05": "The golden record turns slowly under the stylus, light ripples across the fine grooves, soft golden bokeh drifts "
           "in the background, very slow push-in. Smooth, no cuts, no new objects.",
    "s06": "Quiet night interior: the desk lamp light flickers very softly, the coiled telephone cord sways slightly, distant "
           "city lights twinkle through the window, a very slow push-in toward the telephone. Smooth, no people, no cuts.",
    "s07": "The ink pens of the vintage EEG machine move rapidly and draw wavy brain wave lines as the paper chart scrolls "
           "steadily to the left, analog needle dials tremble, warm lamp light. Static camera, smooth, no people, no cuts.",
    "s10": "The golden record floats and rotates slowly in space, starlight glints sweep across its surface, the warm halo "
           "breathes softly, stars drift with gentle parallax, very slow push-in. Smooth, calm, no cuts, no new objects.",
}


def art_of(proj):
    return {w.split("#")[0].split("/")[1]: imagegen.path(proj, k) for w, _r, k in imagegen.keys(proj)}


def frames(scene):
    mp4, out = VID / f"{scene}.mp4", VID / scene
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.jpg"):
        f.unlink()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf", "fps=24,scale=1080:-2", "-q:v", "3",
                    str(out / "%03d.jpg")], check=True, stdin=subprocess.DEVNULL)
    n = len(list(out.glob("*.jpg")))
    print(f"{scene}: {n} кадров → {out.relative_to(PROJ)}")
    return n


def main(argv):
    proj = load(PROJ)
    arts = art_of(proj)
    scenes = [a for a in argv if not a.startswith("--")] or list(MOTION)
    todo = [s for s in scenes if not (VID / f"{s}.mp4").exists()]
    print(f"Клипы: {MODEL}, 6 с, 1080P. Сделать {len(todo)} из {len(scenes)}: {' '.join(todo) or '—'}; "
          f"смета {len(todo) * CREDITS} кредитов ≈ ${len(todo) * CREDITS / 200:.2f}")
    if "--yes" not in argv:
        print("Платная генерация не запущена: --yes после «да» пользователя.")
        return
    VID.mkdir(parents=True, exist_ok=True)
    pend = json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else {}
    print(f"Баланс Kie до: {imagegen.kie_balance():.1f} кредитов")
    for s in todo:
        png = arts.get(s)
        if not png or not png.exists():
            print(f"{s}: нет арта в кэше ({png}) — сначала images --yes")
            continue
        tid = pend.get(s)
        if not tid:
            url = imagegen.kie_upload(png)
            inp = {"prompt": MOTION[s], "image_url": url, "duration": "6", "resolution": "1080P"}
            tid = imagegen.kie_create(MODEL, inp)
            pend[s] = tid
            PENDING.write_text(json.dumps(pend, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{s}: задача {tid}")
        res = imagegen.kie_wait(tid, MODEL, timeout=900, poll=8)
        urls = (res.get("result") or {}).get("resultUrls") or []
        if not urls:
            print(f"{s}: нет resultUrls в ответе: {res}")
            continue
        (VID / f"{s}.mp4").write_bytes(imagegen._download(urls[0]))
        pend.pop(s, None)
        PENDING.write_text(json.dumps(pend, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{s}: готово, {res.get('credits')} кредитов")
        frames(s)
    print(f"Баланс Kie после: {imagegen.kie_balance():.1f} кредитов")


if __name__ == "__main__":
    if "--frames" in sys.argv:
        for s in [a for a in sys.argv[1:] if not a.startswith("--")]:
            frames(s)
    else:
        main(sys.argv[1:])

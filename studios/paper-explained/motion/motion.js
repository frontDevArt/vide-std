// Набор моушн-приёмов «На бумаге» — общий код страниц web.html (шпаргалка — README.md рядом).
// Подключать ПОСЛЕ common.js ролика и ДО скрипта его мира. Время — только из window.seek(t): студия ставит кадр,
// common.js двигает CSS-анимации, мы дорисовываем следом. Поэтому всё здесь — чистая функция t: ни таймеров, ни
// requestAnimationFrame (кроме просмотра страницы без студии).
// Даёт: 1) счётчик [data-count]; 2) window.motion — время слов, перевод точки сцены в точку кадра, плавности,
//       случайность с сидом и onFrame(fn): свой рисунок на каждый кадр (canvas мира ролика).
(function () {
  const S = window.SCENE || { W: 1080, H: 1920, dur: 6, area: { x0: 151, y0: 154, x1: 929, y1: 1536 }, words: [] };
  const W = S.W, H = S.H, D = S.dur || 6;
  // та же посадка .stage, что в common.js: точка сцены (px внутри .scene) → точка кадра. Нужна, чтобы пометки
  // в вёрстке (пилюля, кольцо) попадали на предмет, нарисованный на canvas во весь кадр
  const a = S.area, aw = a.x1 - a.x0, ah = a.y1 - a.y0, K = Math.min(aw / 780, ah / 1380) * 0.96;
  const SX = a.x0 + (aw - 780 * K) / 2, SY = a.y0 + (ah - 1380 * K) / 2;
  const fx = (x) => SX + K * x, fy = (y) => SY + K * (200 + y);

  const words = (S.words || []).map(w => ({ w: w.w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, ''), t: w.t0 }));
  // когда: секунды | "слово[:сдвиг]" (как data-at: сначала точное слово, потом по началу) | "end:-0.4" (от конца сцены)
  const when = (k, dflt) => {
    if (typeof k === 'number') return k;
    if (k == null || k === '') return dflt;
    const [w, off] = String(k).split(':');
    if (w === 'end') return D + (+off || 0);
    const w0 = w.toLowerCase(), hit = words.find(x => x.w === w0) || words.find(x => x.w.startsWith(w0));
    return (hit ? hit.t : dflt) + (+off || 0);
  };
  const cl = (p) => Math.max(0, Math.min(1, p));
  const lerp = (a0, b0, p) => a0 + (b0 - a0) * p;
  const eo = (p) => 1 - Math.pow(1 - cl(p), 3);                                                         // быстро → медленно
  const eio = (p) => { p = cl(p); return p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; };   // медленно → быстро → медленно
  const rng = (seed) => { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };
  const hash = (i, j, n) => { let h = (i * 374761393 + j * 668265263 + n * 2147483647) | 0; h = (h ^ (h >>> 13)) * 1274126177 | 0; return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };

  // ── приём: счётчик. <div class="count" data-count='{"to": 650000000, "at": "слово[:сдвиг]", "dd": 1.35, "from": 1}'>1</div>
  //    Число растёт по экспоненте (в логарифме, быстро → медленно): цифры мелькают, как у настоящего счётчика; разряды — тонким пробелом.
  const counters = Array.from(document.querySelectorAll('[data-count]')).map(el => {
    const c = JSON.parse(el.dataset.count);
    return { el, from: c.from || 1, to: c.to, t0: when(c.at, 0), dd: c.dd || 1, last: null };
  });
  const fmt = (v) => String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

  const hooks = [];
  function frame(t) {
    t = Math.max(0, Math.min(D, t));
    hooks.forEach(fn => fn(t));
    counters.forEach(c => {
      const p = (t - c.t0) / c.dd;
      const v = p <= 0 ? c.from : p >= 1 ? c.to : Math.round(Math.exp(lerp(Math.log(c.from), Math.log(c.to), eo(p))));
      if (v !== c.last) { c.el.textContent = fmt(v); c.last = v; }
    });
  }
  const prev = window.seek;
  window.seek = (t) => { if (prev) prev(t); frame(t); };
  window.motion = { S, W, H, D, K, fx, fy, when, cl, lerp, eo, eio, rng, hash, onFrame: (fn) => { hooks.push(fn); fn(0); } };
  frame(0);
  if (!window.SCENE) { const t0 = performance.now(); (function loop() { frame(((performance.now() - t0) / 1000) % D); requestAnimationFrame(loop); })(); }
})();

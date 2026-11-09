// Paper Explained — общий ход сцены web.html.
// 1) .stage 780×960 вписывается в рабочую зону кадра (SCENE.area, CSS px) по центру.
// 2) Рваные края: data-torn="tb" (верх/низ), "lr", "all" — clip-path многоугольником с зазубринами (сид — номер элемента).
// 3) Время «на двойках»: студия зовёт window.seek(t), мы ставим всем анимациям t, округлённое вниз до 1/12 с, а свой
//    обход анимаций студии гасим (document.getAnimations → []). Без студии (просмотр в браузере) всё идёт как обычно.
// 4) «Кипение» бумаги: элементы с data-boil чуть дрожат раз в 1/6 с (translate/rotate не мешают transform анимаций).
// 5) Подписи (шаблон paper_page): слова озвучки кусками по 1–2 строки внизу сцены, звучащее слово — под маркером.
(function () {
  const S = window.SCENE || { W: 1080, H: 1920, area: { x0: 151, y0: 154, x1: 929, y1: 1536 } };
  const a = S.area, aw = a.x1 - a.x0, ah = a.y1 - a.y0;
  const st = document.querySelector('.stage');
  const k = Math.min(aw / 780, ah / 1380) * 0.96;  // запас 4 %: тени, скотч и «кипение» не выходят за зону
  st.style.left = (a.x0 + (aw - 780 * k) / 2) + 'px';
  st.style.top = (a.y0 + (ah - 1380 * k) / 2) + 'px';
  st.style.transform = 'scale(' + k + ')';

  // подписи: куски не длиннее CAP символов, граница — и на смене бита
  const CAP = 30, Wd = S.words || [], bt = (S.beats || []).map(b => b.t0);
  const beatOf = (t) => bt.reduce((i, b0, j) => (t >= b0 - 1e-3 ? j : i), 0);
  // слова бита делятся на ровные куски: n = ceil(длина / CAP), без «сирот» в одно слово
  const byBeat = [];
  Wd.forEach((w, i) => { const b = beatOf(w.t0); (byBeat[b] = byBeat[b] || []).push(i); });
  const chunks = [];
  byBeat.forEach((ids, b) => {
    if (!ids) return;
    const len = ids.reduce((s, i) => s + Wd[i].w.length + 1, -1), n = Math.ceil(len / CAP), goal = len / n;
    const first = chunks.length;  // первый кусок этого бита
    let c = null, acc = 0;
    ids.forEach(i => {
      const made = chunks.length - first;  // кусков бита уже начато
      if (!c || (made < n && acc >= goal * made - 2)) { c = { beat: b, idx: [], text: '' }; chunks.push(c); }
      c.idx.push(i); c.text = c.text ? c.text + ' ' + Wd[i].w : Wd[i].w; acc += Wd[i].w.length + 1;
    });
  });
  const caps = document.createElement('div'); caps.className = 'caps'; st.appendChild(caps);
  chunks.forEach(c => {
    c.el = document.createElement('div'); c.el.className = 'chunk';
    c.spans = c.idx.map(i => { const s = document.createElement('span'); s.textContent = Wd[i].w; c.el.appendChild(s);
                                c.el.appendChild(document.createTextNode(' ')); return s; });
    caps.appendChild(c.el);
  });
  function captions(t) {
    let cur = -1;
    chunks.forEach((c, j) => { if (t >= Wd[c.idx[0]].t0 - 0.05) cur = j; });
    chunks.forEach((c, j) => {
      c.el.style.display = j === cur ? 'block' : 'none';
      if (j !== cur) return;
      c.idx.forEach((i, n) => {
        const w = Wd[i], next = Wd[i + 1];
        const on = t >= w.t0 - 0.02 && (!next || t < next.t0 - 0.02 || n === c.idx.length - 1 && t < w.t1 + 0.4);
        const p = Math.max(0, Math.min(1, (t - w.t0 + 0.02) / 0.14));
        c.spans[n].style.backgroundSize = on ? (p * 100).toFixed(1) + '% 74%' : '0% 74%';
      });
    });
  }

  function rng(seed) { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

  document.querySelectorAll('[data-torn]').forEach((el, i) => {
    const r = rng(9173 + i * 101), sides = el.dataset.torn, depth = +(el.dataset.depth || 7);
    const step = 2.2, pts = [];
    const j = (on) => (on ? r() * depth : 0);
    const top = /t|all/.test(sides), bot = /b|all/.test(sides), lft = /l|all/.test(sides), rgt = /r|all/.test(sides);
    for (let x = 0; x <= 100; x += step) pts.push([x, j(top) * 100 / el.offsetHeight]);
    for (let y = 0; y <= 100; y += step * el.offsetWidth / el.offsetHeight) pts.push([100 - j(rgt) * 100 / el.offsetWidth, y]);
    for (let x = 100; x >= 0; x -= step) pts.push([x, 100 - j(bot) * 100 / el.offsetHeight]);
    for (let y = 100; y >= 0; y -= step * el.offsetWidth / el.offsetHeight) pts.push([j(lft) * 100 / el.offsetWidth, y]);
    el.style.clipPath = 'polygon(' + pts.map(p => p[0].toFixed(2) + '% ' + p[1].toFixed(2) + '%').join(',') + ')';
  });

  // data-at="слово[:сдвиг]" — элемент стартует со слова озвучки (SCENE.words, первое совпадение по началу слова)
  const words = (S.words || []).map(w => ({ w: w.w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, ''), t: w.t0 }));
  document.querySelectorAll('[data-at]').forEach(el => {
    const [word, off] = el.dataset.at.split(':');
    const hit = words.find(x => x.w.startsWith(word.toLowerCase()));
    if (hit) el.style.setProperty('--d', (hit.t + (+off || 0)).toFixed(3) + 's');
  });

  const FPS2 = 12;
  const all = document.getAnimations.bind(document);
  document.getAnimations = () => [];
  const boil = Array.from(document.querySelectorAll('[data-boil]'));
  window.seek = (t) => {
    captions(t);  // подписи — по точному времени речи, не шагом
    const q = Math.floor(t * FPS2 + 1e-4) / FPS2;
    for (const an of all()) { an.pause(); an.currentTime = q * 1000; }
    const n = Math.floor(t * 6);
    boil.forEach((el, i) => {
      const r = rng(n * 7919 + i * 131 + 1); const amp = +(el.dataset.boil || 1);
      el.style.translate = ((r() - .5) * 1.4 * amp).toFixed(2) + 'px ' + ((r() - .5) * 1.4 * amp).toFixed(2) + 'px';
      el.style.rotate = ((r() - .5) * .35 * amp).toFixed(3) + 'deg';
    });
  };
})();

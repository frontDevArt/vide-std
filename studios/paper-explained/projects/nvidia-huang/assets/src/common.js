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
  const CAP = 30, Wd = S.words || [], Bs = S.beats || [];
  // слово — в бит, с которым дольше пересекается: начало слова по разметке ElevenLabs бывает раньше границы бита
  // (смычка «К» в «Клод» беззвучна — граница по паузе встаёт на взрыв), по одному t0 оно уезжало в прошлый кусок
  const beatOf = (w) => {
    let best = -1, ov = 0;
    Bs.forEach((b, j) => { const o = Math.min(b.t1, w.t1) - Math.max(b.t0, w.t0); if (o > ov) { ov = o; best = j; } });
    return best >= 0 ? best : Bs.reduce((i, b, j) => (w.t0 >= b.t0 - 1e-3 ? j : i), 0);
  };
  // слова бита делятся на ровные куски: n = ceil(длина / CAP), без «сирот» в одно слово
  const byBeat = [];
  Wd.forEach((w, i) => { const b = beatOf(w); (byBeat[b] = byBeat[b] || []).push(i); });
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
    c.spans = c.idx.map((i, n) => { const s = document.createElement('span'); s.textContent = Wd[i].w; c.el.appendChild(s);
                                const nx = c.idx[n + 1], glue = nx !== undefined && /^[^\p{L}\p{N}]+$/u.test(Wd[nx].w);  // тире не висит одно на строке
                                c.el.appendChild(document.createTextNode(glue ? ' ' : ' ')); return s; });
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
  // (voice-clone: сначала точное совпадение — «голос» не цепляется за «голосовых», потом по началу слова)
  document.querySelectorAll('[data-at]').forEach(el => {
    const [word, off] = el.dataset.at.split(':'), w0 = word.toLowerCase();
    const hit = words.find(x => x.w === w0) || words.find(x => x.w.startsWith(w0));
    if (hit) el.style.setProperty('--d', (hit.t + (+off || 0)).toFixed(3) + 's');
  });
  // время слова: сначала точное совпадение («мам» ≠ «маме»), потом по началу слова
  const wordT = (w0, dflt) => { w0 = w0.toLowerCase(); const hit = words.find(x => x.w === w0) || words.find(x => x.w.startsWith(w0));
                               return hit ? hit.t : dflt; };

  // ── motion-test (2026-11-11): новые движения ──
  // 7) Камера (.cam): окно — картинка сцены (0…780 × 0…data-bottom px) с рваными краями со всех сторон: слои при
  //    наезде уходят за край бумажного окна, а не под интерфейс площадки и не за поля кадра (qa «безопасная зона»).
  document.querySelectorAll('.cam').forEach((el, i) => {
    const r = rng(4242 + i), L = 2, R = 778, T = 2, B = +(el.dataset.bottom || 966), dp = 9, pts = [];
    for (let x = L; x < R; x += 11) pts.push([x, T + r() * dp]);
    for (let y = T; y < B; y += 11) pts.push([R - r() * dp, y]);
    for (let x = R; x > L; x -= 11) pts.push([x, B - r() * dp]);
    for (let y = B; y > T; y -= 11) pts.push([L + r() * dp, y]);
    el.style.clipPath = 'polygon(' + pts.map(p => p[0].toFixed(1) + 'px ' + p[1].toFixed(1) + 'px').join(',') + ')';
  });

  // 8) Волна голосового: data-wave="N" — N столбиков с постоянным рисунком (--h0, сид — номер волны)
  document.querySelectorAll('[data-wave]').forEach((el, i) => {
    const r = rng(777 + i * 13 + (+el.dataset.seed || 0)), n = +el.dataset.wave;
    for (let j = 0; j < n; j++) {
      const b = document.createElement('i');
      const h = .22 + .78 * Math.pow(Math.sin(Math.PI * (j + .5) / n), .5) * (.35 + .65 * r());
      b.dataset.h0 = h.toFixed(3); b.style.setProperty('--h', h.toFixed(3)); el.appendChild(b);
    }
  });

  // 9) Речь: data-talk="слово[~слово2]" — с этого слова до конца сцены (или до слова2) элемент «говорит»: --m 0…1 — открытия рта по гласным
  //    звучащего слова (piper и ElevenLabs дают время слов), шагом 1/12 с. У волны (data-wave) прыгают столбики.
  const VOW = /[аеёиоуыэюяaeiouy]/gi;
  const talkers = Array.from(document.querySelectorAll('[data-talk]')).map(el => {
    const [a, b] = el.dataset.talk.split('~');
    return { el, t0: wordT(a, 0), t1: b ? wordT(b, 1e9) - 0.02 : 1e9, bars: el.dataset.wave ? Array.from(el.children) : null };
  });
  const mouth = (t) => {
    const w = (S.words || []).find(x => t >= x.t0 && t < x.t1 && /[\p{L}\p{N}]/u.test(x.w));
    if (!w) return 0;
    const n = Math.max(1, (w.w.match(VOW) || []).length), ph = (t - w.t0) / Math.max(.05, w.t1 - w.t0) * n;
    return Math.pow(Math.abs(Math.sin(Math.PI * ph)), .6);
  };

  // 10) Ксерокопия: data-misprint="слово" — поверх краски две её копии (синяя и терракотовая, только тёмное — светлое
  //     и бумага прозрачны) со сдвигом; до слова сдвиг едва заметен, со слова — сбит; дрожит раз в 1/6 с.
  const mps = [];
  if (document.querySelector('[data-misprint]')) {
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    defs.setAttribute('width', '0'); defs.setAttribute('height', '0'); defs.style.position = 'absolute';
    const tint = (id, c) => `<filter id="${id}" color-interpolation-filters="sRGB"><feColorMatrix values="0 0 0 0 ${c[0]}  0 0 0 0 ${c[1]}  0 0 0 0 ${c[2]}  -.34 -.34 -.34 1 0"/></filter>`;
    defs.innerHTML = tint('mpB', [.30, .47, .62]) + tint('mpT', [.80, .36, .28]);
    document.body.appendChild(defs);
    document.querySelectorAll('[data-misprint]').forEach(el => {
      const layers = ['t', 'b'].map(c => {
        const cl = el.cloneNode(true); cl.removeAttribute('data-misprint'); cl.classList.add('mp', c);
        el.parentNode.insertBefore(cl, el.nextSibling); return cl;
      });
      mps.push({ t0: wordT(el.dataset.misprint, 0), layers });
    });
  }

  // ── free-reset (2026-11-12): камера-экскурсия по большой картинке ──
  // 11) data-tour='[[когда, cx, cy, s, dd?, звук?], …]' на элементе .tour (transform-origin 0 0, содержимое — в своих
  //     px): точка (cx, cy) встаёт в центр окна (data-view="x y", по умолчанию 390 480 — центр картинки сцены) с зумом s.
  //     когда — секунды, "слово[:сдвиг]" или "end:-0.4" (от конца сцены). Переход к остановке — dd с (умолч. .6),
  //     ход «медленно — быстро — медленно», зум — в логарифме (наезд ровный). Камера идёт шагом 1/12 с, как всё.
  //     Звук перехода — whoosh (6-й элемент: своё имя или "none"); у первой остановки звука нет.
  const when = (k) => {
    if (typeof k === 'number') return k;
    const [w, off] = String(k).split(':');
    return (w === 'end' ? (S.dur || 0) : wordT(w, 0)) + (+off || 0);
  };
  const ease3 = (p) => (p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
  const lerpCam = (a, b, p) => { const e = ease3(Math.max(0, Math.min(1, p)));
    return { x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e, s: Math.exp(Math.log(a.s) + (Math.log(b.s) - Math.log(a.s)) * e) }; };
  const tours = Array.from(document.querySelectorAll('[data-tour]')).map(el => {
    const v = (el.dataset.view || '390 480').split(/\s+/).map(Number);
    const stops = JSON.parse(el.dataset.tour).map(s => ({ t: when(s[0]), x: s[1], y: s[2], s: s[3], dd: s[4] == null ? .6 : s[4], snd: s[5] }))
      .sort((a, b) => a.t - b.t);
    stops[0].from = stops[0];  // где была камера в момент старта каждой остановки
    for (let i = 1; i < stops.length; i++) { const p = stops[i - 1]; stops[i].from = lerpCam(p.from, p, p.dd > 0 ? (stops[i].t - p.t) / p.dd : 1); }
    stops.slice(1).forEach(s => {
      if (s.snd === 'none') return;
      const k = document.createElement('i');
      k.style.cssText = `position: absolute; width: 0; height: 0; animation: appear .01s linear ${Math.max(0, s.t).toFixed(3)}s both`;
      k.dataset.sfx = s.snd || 'whoosh'; st.appendChild(k);
    });
    return { el, v, stops };
  });
  const tourAt = (tr, t) => {
    const ss = tr.stops; let i = 0;
    while (i + 1 < ss.length && t >= ss[i + 1].t) i++;
    const s = ss[i];
    return i === 0 && t < s.t ? s : lerpCam(s.from, s, s.dd > 0 ? (t - s.t) / s.dd : 1);
  };

  const FPS2 = 12;
  const all = document.getAnimations.bind(document);
  document.getAnimations = () => [];

  // 6) Звуки под движение (шаблон web.html → studio/sfx.py): старт CSS-анимации → бумажный звук по её имени.
  //    data-sfx="имя" или "none" на элементе — своё. Декор (точки, кресты, кольца, тонкие линии) — без звука;
  //    одинаковые звуки ближе GAP — один (стопка фишек не трещит).
  const SFX = { drop: 'paper', slideL: 'slide', slideR: 'slide', rise: 'slide', pop: 'flick', fly: 'flick',
                slam: 'stamp', strike: 'marker', draw: 'marker', grow: 'tick', appear: 'tick',
                dolly: 'whoosh', travel: 'swish', tape: 'slide', printIn: 'slide', flapOpen: 'paper', up: 'slide',
                fall: 'swish', unfoldT: 'paper', unfoldB: 'paper' };
  const GAP = { tick: 0.07, flick: 0.08 };
  window.sfx = () => {
    const ev = [];
    for (const an of all()) {
      const el = an.effect && an.effect.target;
      if (!el) continue;
      let name = el.dataset && el.dataset.sfx;
      if (!name) {
        name = SFX[an.animationName];
        if (!name || el.closest('.rings, .dot, .cross')) continue;
        if (an.animationName === 'draw' && parseFloat(getComputedStyle(el).strokeWidth) < 4) continue;
      }
      if (name !== 'none') ev.push([an.effect.getTiming().delay / 1000, name]);
    }
    ev.sort((a, b) => a[0] - b[0]);
    const last = {}, out = [];
    for (const [t, n] of ev) {
      if (t - (n in last ? last[n] : -9) < (GAP[n] || 0.1)) continue;
      last[n] = t; out.push([+t.toFixed(3), n]);
    }
    return out;
  };
  const boil = Array.from(document.querySelectorAll('[data-boil]'));
  window.seek = (t) => {
    captions(t);  // подписи — по точному времени речи, не шагом
    const q = Math.floor(t * FPS2 + 1e-4) / FPS2;
    for (const an of all()) { an.pause(); an.currentTime = q * 1000; }
    tours.forEach(tr => {
      const c = tourAt(tr, q);
      tr.el.style.transform = `translate(${(tr.v[0] - c.x * c.s).toFixed(2)}px, ${(tr.v[1] - c.y * c.s).toFixed(2)}px) scale(${c.s.toFixed(4)})`;
    });
    const n = Math.floor(t * 6);
    boil.forEach((el, i) => {
      const r = rng(n * 7919 + i * 131 + 1); const amp = +(el.dataset.boil || 1);
      el.style.translate = ((r() - .5) * 1.4 * amp).toFixed(2) + 'px ' + ((r() - .5) * 1.4 * amp).toFixed(2) + 'px';
      el.style.rotate = ((r() - .5) * .35 * amp).toFixed(3) + 'deg';
    });
    talkers.forEach((tk, i) => {
      const m = q >= tk.t0 && q < tk.t1 ? mouth(q) : 0;
      tk.el.style.setProperty('--m', m.toFixed(3));
      if (!tk.bars) return;
      const r = rng(Math.round(q * 12) * 977 + i * 31 + 5);
      tk.bars.forEach(b => {
        const h0 = +b.dataset.h0, h = m > .04 ? Math.max(.12, Math.min(1, h0 * (.3 + 1.25 * m * (.3 + .7 * r())))) : h0;
        b.style.setProperty('--h', h.toFixed(3));
      });
    });
    mps.forEach((mp, i) => {
      const a = t >= mp.t0 ? 7 : 1.6;
      mp.layers.forEach((L, j) => {
        const r = rng(n * 613 + i * 71 + j * 7 + 3), s = j ? -1 : 1;
        L.style.translate = (s * a * .7 + (r() - .5) * a * .7).toFixed(1) + 'px ' + (-s * a * .35 + (r() - .5) * a * .6).toFixed(1) + 'px';
      });
    });
  };
})();

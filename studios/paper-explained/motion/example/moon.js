// motion-moon-demo (2026-11-16): мир демо на canvas — Луна-герой, лунная поверхность, поле телевизоров.
// Образец «мира ролика» для набора motion/: рисунок — чистая функция времени сцены, зовётся из M.onFrame.
// Стыки сцен без склейки держатся на одной картинке: «лунный кадр» = текстура с центром в (MX, MY) и масштабом SURF.
//   m01 mode=moon     — диск Луны растёт до RBIG и закрывает кадр → это и есть лунный кадр;
//   m02 mode=surface  — лунный кадр, медленный наезд data-s0 → data-s1;
//   m03 mode=tv       — тот же лунный кадр показан на экране телевизора: отъезд из экрана, поле телевизоров, нырок обратно;
//   m04 mode=surface  — снова лунный кадр.
(function () {
  const M = window.motion;  // общий набор студии (motion/motion.js): время слов, точки сцены → кадр, плавности
  const { W, H, D, fx, fy, when, cl, lerp, eo, eio, rng, hash } = M;

  // ── общие числа мира (одинаковы во всех сценах — на них держатся стыки) ──
  const MX = fx(360), MY = fy(580);       // центр Луны в кадре
  const R0 = 350, RBIG = 1650;            // радиус Луны-героя и радиус, закрывающий кадр
  const SURF = RBIG / 1400;               // масштаб текстуры в «лунном кадре»
  const DIM = 0.66;                       // затемнение лунного кадра под текст
  const IRIS = 0.6;                       // раскрытие Луны в конце m01, с
  const NIGHT = '5, 7, 15';

  // ── текстура Луны: 2800×2800 единиц мира, нарисована один раз вдвое мельче ──
  const TEX = 1400, tex = document.createElement('canvas'); tex.width = tex.height = TEX;
  (function () {
    const g = tex.getContext('2d'), r = rng(1969);
    const base = g.createRadialGradient(TEX * .42, TEX * .4, 40, TEX / 2, TEX / 2, TEX * .78);
    base.addColorStop(0, '#DEDBD3'); base.addColorStop(.55, '#ACA9A2'); base.addColorStop(1, '#74726D');
    g.fillStyle = base; g.fillRect(0, 0, TEX, TEX);
    for (let i = 0; i < 11; i++) {  // моря
      const x = r() * TEX, y = r() * TEX, R = 90 + r() * 230, m = g.createRadialGradient(x, y, 0, x, y, R);
      m.addColorStop(0, 'rgba(66, 66, 72, .46)'); m.addColorStop(.7, 'rgba(66, 66, 72, .22)'); m.addColorStop(1, 'rgba(66, 66, 72, 0)');
      g.fillStyle = m; g.fillRect(x - R, y - R, 2 * R, 2 * R);
    }
    for (let i = 0; i < 170; i++) {  // кратеры: тёмная чаша, светлое дно со сдвигом, блик и тень на кромке
      const x = r() * TEX, y = r() * TEX, R = 4 + Math.pow(r(), 2.4) * 60;
      g.beginPath(); g.arc(x, y, R, 0, 7); g.fillStyle = 'rgba(58, 56, 54, .36)'; g.fill();
      g.beginPath(); g.arc(x + R * .14, y + R * .16, R * .85, 0, 7); g.fillStyle = 'rgba(208, 205, 197, .38)'; g.fill();
      g.lineWidth = Math.max(1, R * .1);
      g.strokeStyle = 'rgba(244, 242, 234, .45)'; g.beginPath(); g.arc(x, y, R, 3.5, 5.6); g.stroke();
      g.strokeStyle = 'rgba(36, 34, 32, .42)'; g.beginPath(); g.arc(x, y, R, .4, 2.4); g.stroke();
    }
  })();
  const drawTex = (g, cx, cy, sc) => { const d = 2800 * sc; g.drawImage(tex, cx - d / 2, cy - d / 2, d, d); };

  const starList = (function () { const r = rng(77), out = []; for (let i = 0; i < 170; i++) out.push([r() * W, r() * H, .6 + r() * 1.7, r() * 6.28, r()]); return out; })();
  function stars(g, t) {
    for (const [x, y, sz, ph, warm] of starList) {
      g.globalAlpha = .35 + .65 * (.5 + .5 * Math.sin(t * 1.3 + ph));
      g.fillStyle = warm > .85 ? '#FFE7A3' : warm < .12 ? '#BFE6FF' : '#FFFFFF';
      g.beginPath(); g.arc(x, y - t * 4, sz, 0, 7); g.fill();
    }
    g.globalAlpha = 1;
  }

  // ── m01: Луна-герой; в конце сцены раскрывается на весь кадр и темнеет до «лунного кадра» ──
  function drawMoon(g, t) {
    g.fillStyle = `rgb(${NIGHT})`; g.fillRect(0, 0, W, H);
    stars(g, t);
    const p = cl((t - (D - IRIS)) / IRIS), q = p * p;
    const r = Math.exp(lerp(Math.log(R0 + 4 * Math.sin(t * .9)), Math.log(RBIG), q));
    const halo = g.createRadialGradient(MX, MY, r * .92, MX, MY, r * 1.6);
    halo.addColorStop(0, `rgba(205, 220, 255, ${.3 * (1 - p)})`); halo.addColorStop(1, 'rgba(205, 220, 255, 0)');
    g.fillStyle = halo; g.fillRect(0, 0, W, H);
    g.save(); g.beginPath(); g.arc(MX, MY, r, 0, 7); g.clip();
    drawTex(g, MX, MY, r / 1400);
    const sh = g.createRadialGradient(MX - r * .32, MY - r * .34, r * .25, MX, MY, r);  // объём шара: тень к краю
    sh.addColorStop(0, `rgba(${NIGHT}, 0)`); sh.addColorStop(.72, `rgba(${NIGHT}, ${.3 * (1 - q)})`); sh.addColorStop(1, `rgba(${NIGHT}, ${.86 * (1 - q)})`);
    g.fillStyle = sh; g.fillRect(MX - r, MY - r, 2 * r, 2 * r);
    g.restore();
    if (q > 0) { g.fillStyle = `rgba(${NIGHT}, ${DIM * q})`; g.fillRect(0, 0, W, H); }
  }

  // ── m02, m04: лунный кадр с медленным наездом ──
  function drawSurface(g, t, s0, s1) {
    drawTex(g, MX, MY, SURF * lerp(s0, s1, cl(t / D)));
    g.fillStyle = `rgba(${NIGHT}, ${DIM})`; g.fillRect(0, 0, W, H);
  }

  // ── m03: поле телевизоров. Мир: телевизор-герой в (0, 0), экран x −66…38, y −45…33 (4:3), сетка 210×200 «кирпичом» ──
  const SF = H / 78;                                        // экран героя во весь кадр по высоте
  const CAM = {
    full: { s: SF, fx: -14, fy: -6, ax: W / 2, ay: H / 2 },  // кадр = экран героя
    hero: { s: 4.0, fx: 0, fy: 6, ax: fx(360), ay: fy(560) },
    many: { s: 1.0, fx: 0, fy: 6, ax: fx(360), ay: fy(560) },
    dots: { s: 0.2, fx: 0, fy: 6, ax: fx(360), ay: fy(560) },
  };
  const mix = (c0, c1, p) => ({ s: Math.exp(lerp(Math.log(c0.s), Math.log(c1.s), p)), fx: lerp(c0.fx, c1.fx, p), fy: lerp(c0.fy, c1.fy, p),
                                ax: lerp(c0.ax, c1.ax, p), ay: lerp(c0.ay, c1.ay, p) });
  function camAt(t, tA, tB) {
    const DIVE = 0.6;
    if (t >= D - DIVE) { const p = cl((t - (D - DIVE)) / DIVE); return mix(CAM.dots, CAM.full, p * p); }
    if (t >= tB) return mix(CAM.many, CAM.dots, eio((t - tB) / 1.15));
    if (t >= tA) return mix(CAM.hero, CAM.many, eio((t - tA) / .55));
    return mix(CAM.full, CAM.hero, eo((t - .04) / .7));
  }
  function rr(g, x, y, w, h, r) { g.beginPath(); g.roundRect(x, y, w, h, Math.min(r, w / 2, h / 2)); }
  function tvSet(g, c, wx, wy, lit, alpha, screen) {
    const s = c.s, X = c.ax + s * (wx - c.fx), Y = c.ay + s * (wy - c.fy);
    if (X < -100 * s || X > W + 100 * s || Y < -110 * s || Y > H + 110 * s) return;
    g.globalAlpha = alpha;
    if (s < .22) {  // точка: один светящийся экран
      g.fillStyle = `rgba(200, 228, 255, ${.12 + .88 * lit * lit})`;  // разная яркость: поле мерцает, а не лежит растром
      g.fillRect(X - 60 * s, Y - 42 * s, 96 * s, 74 * s);
      g.globalAlpha = 1; return;
    }
    if (s >= .45) {  // ножки и усы антенны
      g.lineCap = 'round'; g.strokeStyle = '#2A1B12'; g.lineWidth = 6 * s;
      g.beginPath(); g.moveTo(X - 50 * s, Y + 68 * s); g.lineTo(X - 62 * s, Y + 90 * s); g.moveTo(X + 50 * s, Y + 68 * s); g.lineTo(X + 62 * s, Y + 90 * s); g.stroke();
      g.strokeStyle = '#B9B4A8'; g.lineWidth = 2.6 * s;
      g.beginPath(); g.moveTo(X - 4 * s, Y - 60 * s); g.lineTo(X - 36 * s, Y - 100 * s); g.moveTo(X + 4 * s, Y - 60 * s); g.lineTo(X + 32 * s, Y - 106 * s); g.stroke();
    }
    const wood = g.createLinearGradient(0, Y - 60 * s, 0, Y + 70 * s); wood.addColorStop(0, '#74503A'); wood.addColorStop(1, '#3F281B');
    g.fillStyle = wood; rr(g, X - 80 * s, Y - 60 * s, 160 * s, 130 * s, 14 * s); g.fill();
    if (s >= .45) {
      g.fillStyle = '#15151A'; rr(g, X - 72 * s, Y - 52 * s, 118 * s, 92 * s, 11 * s); g.fill();
      g.fillStyle = '#CFC9BC'; g.beginPath(); g.arc(X + 62 * s, Y - 28 * s, 8 * s, 0, 7); g.arc(X + 62 * s, Y - 4 * s, 8 * s, 0, 7); g.fill();
      g.strokeStyle = 'rgba(20, 14, 10, .7)'; g.lineWidth = 2.4 * s; g.beginPath();
      for (let i = 0; i < 4; i++) { g.moveTo(X + 52 * s, Y + (20 + i * 8) * s); g.lineTo(X + 72 * s, Y + (20 + i * 8) * s); }
      g.stroke();
    }
    const x0 = X - 66 * s, y0 = Y - 45 * s, sw = 104 * s, sh = 78 * s;
    if (screen) {
      screen(x0, y0, sw, sh);
    } else {
      if (s >= .45) { g.shadowColor = 'rgba(160, 205, 255, .8)'; g.shadowBlur = 14 * s; }
      const b = .55 + .45 * lit;
      g.fillStyle = `rgb(${Math.round(150 * b + 40)}, ${Math.round(185 * b + 40)}, ${Math.round(215 * b + 40)})`;
      rr(g, x0, y0, sw, sh, 9 * s); g.fill(); g.shadowBlur = 0;
    }
    g.globalAlpha = 1;
  }
  function drawTv(g, t, tA, tB, m3) {
    const c = camAt(t, tA, tB), s = c.s, u = s / SF;
    const room = g.createLinearGradient(0, 0, 0, H); room.addColorStop(0, '#060912'); room.addColorStop(.6, '#0B1226'); room.addColorStop(1, '#070A14');
    g.fillStyle = room; g.fillRect(0, 0, W, H);
    // соседи проявляются при отъезде: на крупном плане герой один
    const others = cl((3.6 - s) / 1.2);
    if (others > 0) {
      const CW = 210, CH = 200, n = Math.floor(t * 7);
      const j0 = Math.floor(((0 - c.ay) / s + c.fy - 110) / CH), j1 = Math.ceil(((H - c.ay) / s + c.fy + 110) / CH);
      for (let j = j0; j <= j1; j++) {
        const off = (j & 1) ? CW / 2 : 0;
        const i0 = Math.floor(((0 - c.ax) / s + c.fx - off - 100) / CW), i1 = Math.ceil(((W - c.ax) / s + c.fx - off + 100) / CW);
        for (let i = i0; i <= i1; i++) {
          if (i === 0 && j === 0) continue;
          tvSet(g, c, i * CW + off, j * CH, hash(i, j, n), others, null);
        }
      }
    }
    // свет героя на полу и сам герой: на экране — тот же «лунный кадр», что фон соседних сцен
    const HX = c.ax + s * (0 - c.fx), HY = c.ay + s * (0 - c.fy);
    if (s > .6) {
      g.save(); g.translate(HX, HY + 92 * s); g.scale(1, .28);  // пятно света на полу — сплюснутый круг
      const fl = g.createRadialGradient(0, 0, 0, 0, 0, 170 * s);
      fl.addColorStop(0, `rgba(170, 200, 240, ${.3 * (1 - others * .7)})`); fl.addColorStop(1, 'rgba(170, 200, 240, 0)');
      g.fillStyle = fl; g.beginPath(); g.arc(0, 0, 170 * s, 0, 7); g.fill(); g.restore();
    }
    tvSet(g, c, 0, 0, 1, 1, (x0, y0, sw, sh) => {
      g.save(); rr(g, x0, y0, sw, sh, 9 * s * cl((14 - s) / 6)); g.clip();
      drawTex(g, x0 + (MX + (SF * 104 - W) / 2) * u, y0 + MY * u, SURF * m3 * u);
      g.fillStyle = `rgba(${NIGHT}, ${DIM})`; g.fillRect(x0, y0, sw, sh);
      const tvLook = cl((9 - s) / 4);  // признаки «это телевизор» гаснут при наезде во весь кадр
      if (tvLook > 0) {
        g.fillStyle = `rgba(190, 220, 255, ${.16 * tvLook})`; g.fillRect(x0, y0, sw, sh);  // холодное свечение кинескопа
        if (s >= 1.5) {
          g.fillStyle = `rgba(0, 0, 0, ${.2 * tvLook})`;
          for (let y = y0; y < y0 + sh; y += Math.max(3, 2 * s)) g.fillRect(x0, y, sw, Math.max(1, s * .7));  // строки развёртки
          g.fillStyle = `rgba(255, 255, 255, ${.92 * tvLook})`; g.font = `600 ${7.4 * s}px Oswald, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'alphabetic';
          g.fillText('LIVE FROM THE MOON', x0 + sw / 2, y0 + sh - 8 * s);
          g.fillStyle = `rgba(255, 70, 70, ${tvLook * (Math.floor(t * 2) % 2 ? 1 : .35)})`; g.beginPath(); g.arc(x0 + 12 * s, y0 + 11 * s, 3.2 * s, 0, 7); g.fill();
        }
        const vg = g.createRadialGradient(x0 + sw / 2, y0 + sh / 2, sh * .3, x0 + sw / 2, y0 + sh / 2, sw * .75);
        vg.addColorStop(0, 'rgba(0, 0, 0, 0)'); vg.addColorStop(1, `rgba(0, 0, 0, ${.55 * tvLook})`);
        g.fillStyle = vg; g.fillRect(x0, y0, sw, sh);
      }
      g.restore();
    });
    // среди точек герой остаётся виден: кольцо маркера
    const ring = cl((.55 - s) / .3) * cl((D - .6 - t) / .15);
    if (ring > 0) {
      g.strokeStyle = `rgba(255, 138, 60, ${ring})`; g.lineWidth = 5; g.shadowColor = 'rgba(255, 138, 60, .9)'; g.shadowBlur = 16;
      g.beginPath(); g.arc(HX - 14 * s, HY - 6 * s, 30 + 70 * s, 0, 7); g.stroke(); g.shadowBlur = 0;
    }
  }

  const cv = document.querySelector('canvas.world');
  let g = null, mode = '', tA = 0, tB = 0, s0 = 1, s1 = 1;
  if (cv) {
    cv.width = W; cv.height = H; cv.style.width = W + 'px'; cv.style.height = H + 'px';
    g = cv.getContext('2d'); mode = cv.dataset.mode || 'surface';
    s0 = +(cv.dataset.s0 || 1); s1 = +(cv.dataset.s1 || s0);
    tA = when(cv.dataset.a, D * .35); tB = when(cv.dataset.b, D * .5);
  }

  M.onFrame((t) => {
    if (!g) return;
    g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1; g.shadowBlur = 0;
    if (mode === 'moon') drawMoon(g, t); else if (mode === 'tv') drawTv(g, t, tA, tB, s0); else drawSurface(g, t, s0, s1);
  });
})();

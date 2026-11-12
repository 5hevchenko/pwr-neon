"use strict";
// ============================================================
//  Эффекты выигрыша: дождь из монет и звёзд, большой выигрыш с растущей суммой
//  coinShower(el, n) — монетки фонтаном из элемента; bigWin(pay, x) — полноэкранный «БОЛЬШОЙ / МЕГА / ЭПИЧЕСКИЙ»
// ============================================================
const BW = (() => {
  const XTR = new Path2D("M10.83,3.80 Q12.00,1.70 13.17,3.80 L14.93,6.97 Q15.47,7.93 16.55,8.14 L20.11,8.84 Q22.46,9.30 20.83,11.06 L18.36,13.72 Q17.61,14.52 17.74,15.62 L18.18,19.22 Q18.47,21.60 16.29,20.59 L13.00,19.06 Q12.00,18.60 11.00,19.06 L7.71,20.59 Q5.53,21.60 6.03,19.25 L6.68,16.20 Q6.79,15.71 7.26,15.53 L13.20,13.30 L6.54,13.52 Q6.04,13.54 5.68,13.19 L3.29,10.95 Q1.54,9.30 3.89,8.84 L7.45,8.14 Q8.53,7.93 9.07,6.97 L10.83,3.80Z");
  const S = 64;   // размер спрайта
  const sprite = draw => { const c = document.createElement("canvas"); c.width = c.height = S; draw(c.getContext("2d")); return c; };
  const coin = sprite(g => {
    const r = S / 2 - 2;
    let gr = g.createRadialGradient(S * .38, S * .32, 2, S / 2, S / 2, r);
    gr.addColorStop(0, "#fff6c2"); gr.addColorStop(.45, "#ffcf3d"); gr.addColorStop(1, "#c77d00");
    g.fillStyle = gr; g.beginPath(); g.arc(S / 2, S / 2, r, 0, 7); g.fill();
    g.lineWidth = 3; g.strokeStyle = "#a35f00"; g.stroke();
    g.beginPath(); g.arc(S / 2, S / 2, r - 7, 0, 7); g.lineWidth = 2; g.strokeStyle = "rgba(255,248,210,.75)"; g.stroke();
    g.save(); g.translate(S / 2 - 15, S / 2 - 15); g.scale(30 / 24, 30 / 24);
    g.fillStyle = "#e69500"; g.fill(XTR); g.translate(-.6, -.8); g.fillStyle = "#fff0a8"; g.fill(XTR); g.restore();
  });
  const star = sprite(g => {
    g.save(); g.scale(S / 24, S / 24);
    const gr = g.createLinearGradient(5, 0, 17, 24); gr.addColorStop(0, "#ffe680"); gr.addColorStop(.55, "#ffc233"); gr.addColorStop(1, "#ff9d0a");
    g.shadowColor = "rgba(255,190,40,.9)"; g.shadowBlur = 3; g.fillStyle = gr; g.fill(XTR); g.restore();
  });
  const spark = sprite(g => {
    const gr = g.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
    gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(.25, "rgba(255,230,140,.9)"); gr.addColorStop(1, "rgba(255,200,60,0)");
    g.fillStyle = gr; g.fillRect(0, 0, S, S);
  });

  let cv, cx, P = [], raf = 0, last = 0, spawners = [];
  function ensure() {
    if (cv && cv.isConnected) return;
    cv = document.createElement("canvas"); cv.className = "bw-fx"; document.body.appendChild(cv);
    cx = cv.getContext("2d"); size(); addEventListener("resize", size);
  }
  function size() { if (!cv) return; const d = Math.min(devicePixelRatio || 1, 2); cv.width = innerWidth * d; cv.height = innerHeight * d; cx.setTransform(d, 0, 0, d, 0, 0); }
  function add(x, y, vx, vy, kind, sz) {
    if (P.length > 420) return;
    P.push({ x, y, vx, vy, k: kind, s: sz, r: Math.random() * 6.3, vr: (Math.random() - .5) * .25, f: Math.random() * 6.3, vf: .12 + Math.random() * .2, life: 1, fade: kind === spark ? .02 + Math.random() * .02 : 0 });
  }
  const pick = () => Math.random() < .62 ? coin : star;
  function tick(t) {
    const dt = Math.min(2.5, (t - (last || t)) / 16.67); last = t;
    for (const s of spawners) s.acc += s.rate * dt;
    spawners = spawners.filter(s => {
      while (s.acc >= 1) { s.acc--; s.fn(); }
      return t < s.until;
    });
    cx.clearRect(0, 0, innerWidth, innerHeight);
    const H0 = innerHeight + 80;
    P = P.filter(p => {
      p.vy += .32 * dt; p.vx *= Math.pow(.995, dt); p.x += p.vx * dt; p.y += p.vy * dt; p.r += p.vr * dt; p.f += p.vf * dt;
      if (p.fade) p.life -= p.fade * dt;
      if (p.y > H0 || p.life <= 0) return false;
      cx.save(); cx.globalAlpha = Math.max(0, p.life); cx.translate(p.x, p.y); cx.rotate(p.r);
      if (p.k === coin) cx.scale(Math.max(.12, Math.abs(Math.cos(p.f))), 1);   // монетка вертится ребром
      else if (p.k === star) cx.scale(.85 + .15 * Math.cos(p.f), 1);
      if (p.k === spark) cx.globalCompositeOperation = "lighter";
      cx.drawImage(p.k, -p.s / 2, -p.s / 2, p.s, p.s); cx.restore();
      return true;
    });
    if (P.length || spawners.length) raf = requestAnimationFrame(tick); else { raf = 0; last = 0; cv.remove(); }
  }
  function run() { if (!raf) raf = requestAnimationFrame(tick); }
  // фонтан из точки
  function fountain(x, y, n, power = 1) {
    ensure();
    for (let i = 0; i < n; i++) {
      const a = -Math.PI / 2 + (Math.random() - .5) * 1.5, v = (9 + Math.random() * 9) * power;
      add(x, y, Math.cos(a) * v, Math.sin(a) * v, pick(), 22 + Math.random() * 18);
      if (i % 3 === 0) add(x, y, Math.cos(a) * v * .8, Math.sin(a) * v * .8, spark, 18 + Math.random() * 20);
    }
    run();
  }
  // дождь сверху + фонтаны снизу на время ms
  function rain(ms, rate) {
    ensure();
    const until = performance.now() + ms;
    spawners.push({ until, rate, acc: 0, fn: () => add(Math.random() * innerWidth, -40, (Math.random() - .5) * 2, 2 + Math.random() * 4, pick(), 24 + Math.random() * 22) });
    spawners.push({ until, rate: rate * .55, acc: 0, fn: () => {
      const side = Math.random() < .5, x = side ? -10 : innerWidth + 10, a = side ? -1.05 - Math.random() * .4 : -Math.PI + 1.05 + Math.random() * .4, v = 15 + Math.random() * 8;
      add(x, innerHeight * .9, Math.cos(a) * v, Math.sin(a) * v, pick(), 26 + Math.random() * 20);
    } });
    spawners.push({ until, rate: rate * .4, acc: 0, fn: () => add(Math.random() * innerWidth, Math.random() * innerHeight * .6, 0, -1, spark, 14 + Math.random() * 26) });
    run();
  }
  function stop() { spawners = []; }
  return { fountain, rain, stop };
})();

// выигрыш в мини-игре: монетки по размеру икса + большой экран от x5
function winFx(el, pay, bet) {
  const x = bet ? pay / bet : 0;
  if (el) coinShower(el, Math.min(70, 14 + x * 5));
  if (x >= 5) return bigWin(pay, x);
}
function coinShower(el, n = 40) {
  if (window.LITE) n = Math.ceil(n / 3);
  const r = el && el.getBoundingClientRect ? el.getBoundingClientRect() : { left: innerWidth / 2, width: 0, top: innerHeight / 2, height: 0 };
  BW.fountain(r.left + r.width / 2, r.top + r.height * .6, n);
}

// уровни большого выигрыша (в иксах от ставки)
const BW_TIERS = [[5, "БОЛЬШОЙ ВЫИГРЫШ", "big"], [20, "МЕГА ВЫИГРЫШ", "mega"], [75, "ЭПИЧЕСКИЙ ВЫИГРЫШ", "epic"]];
function bigWin(pay, x, tierX = x, o = {}) {   // tierX — от чего считать уровень (ALL IN празднуем сильнее); o.gift — id выпавшего подарка для карточки
  return new Promise(resolve => {
    const top = BW_TIERS.filter(t => tierX >= t[0]).length;
    if (!top) { resolve(); return; }
    const dur = [0, 2600, 4200, 6000][top];
    const ov = document.createElement("div");
    ov.className = "bw-ov";
    ov.innerHTML = `<div class="bw-rays"></div><div class="bw-box"><div class="bw-t" id="bw-t"></div><div class="bw-n"><span class="xtr-big">⭐</span><b id="bw-n">0</b></div><div class="bw-x">x${x >= 100 ? Math.round(x) : x.toFixed(1).replace(".", ",")}</div>${typeof shareBtns === "function" ? shareBtns() : ""}<div class="bw-tap">нажми, чтобы продолжить</div></div>`;
    document.body.appendChild(ov);
    requestAnimationFrame(() => ov.classList.add("on"));
    BW.rain(dur + 600, [0, 1.2, 2, 3.2][top] / (window.LITE ? 3 : 1));
    const tEl = ov.querySelector("#bw-t"), nEl = ov.querySelector("#bw-n");
    let tier = -1, done = false, t0 = performance.now(), lastH = 0;
    const setTier = i => {
      if (i === tier) return; tier = i;
      ov.className = "bw-ov on " + BW_TIERS[i][2];
      tEl.textContent = BW_TIERS[i][1]; tEl.classList.remove("pop"); void tEl.offsetWidth; tEl.classList.add("pop");
      H.ok(); document.body.classList.remove("bw-shake"); void document.body.offsetWidth; document.body.classList.add("bw-shake");
    };
    const finish = () => {
      if (done) return; done = true;
      nEl.textContent = fmt(pay); setTier(top - 1); ov.classList.add("end");
      arm(ov.querySelector(".bw-share") ? 7000 : 2200);
    };
    let closeT = 0;
    const arm = ms => { clearTimeout(closeT); closeT = setTimeout(close, ms); };
    const close = () => { if (!ov.isConnected) return; BW.stop(); ov.classList.remove("on"); setTimeout(() => ov.remove(), 400); document.body.classList.remove("bw-shake"); resolve(); };
    ov.addEventListener("click", e => {
      const b = e.target.closest(".bw-share button");
      if (!b) return done ? close() : finish();
      clearTimeout(closeT);   // игрок делится: экран не закрываем у него из-под пальца
      shareWin(b.dataset.to, { pay, gift: o.gift }, b).finally(() => arm(5000));
    });
    (function step(t) {
      if (done || !ov.isConnected) return;
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 2.2), cur = pay * e;
      nEl.textContent = fmt(cur);
      let i = 0; while (i + 1 < top && cur / pay * tierX >= BW_TIERS[i + 1][0]) i++;
      setTier(i);
      if (t - lastH > 110) { H.imp("light"); lastH = t; }
      if (k >= 1) finish(); else requestAnimationFrame(step);
    })(t0);
    starify(ov);
  });
}

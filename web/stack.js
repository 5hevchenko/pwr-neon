"use strict";
// ============================================================
//  «Стопка» — игра на ловкость без ставок: тап ставит блок на башню, свисающее отрезается.
//  Недельный турнир (stack.py). Движение блока — целочисленная формула, та же, что на сервере:
//  сервер пересчитывает башню по присланным тапам, поэтому нарисовать себе рекорд нельзя.
// ============================================================
const STK_ICON = "data:image/svg+xml," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><defs>
<linearGradient id="a" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#ffe27a"/><stop offset="1" stop-color="#ff9d2e"/></linearGradient>
<linearGradient id="b" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#7ce0ff"/><stop offset="1" stop-color="#3a7dff"/></linearGradient>
<linearGradient id="c" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#ff8ad0"/><stop offset="1" stop-color="#d93d8f"/></linearGradient></defs>
<rect x="14" y="66" width="68" height="18" rx="4" fill="url(#b)"/><rect x="45" y="66" width="6" height="18" fill="#fff" opacity=".55"/>
<rect x="20" y="46" width="58" height="18" rx="4" fill="url(#c)"/><rect x="46" y="46" width="6" height="18" fill="#fff" opacity=".55"/>
<rect x="24" y="26" width="44" height="18" rx="4" fill="url(#a)"/><rect x="43" y="26" width="6" height="18" fill="#fff" opacity=".6"/>
<path d="M46 26c-6-10-16-8-12-1 2 3 8 2 12 1zm0 0c6-10 16-8 12-1-2 3-8 2-12 1z" fill="#fff" opacity=".9"/></svg>`);
ICONS.play = ICONS.play || '<path d="M7 4.5v15l12.5-7.5z" fill="currentColor" stroke-linejoin="round"/>';
GAMES.push({ id: "stack", t: "Стопка", s: "Ставь блоки ровно — турнир на ловкость, без ставок", imgUrl: STK_ICON, k: ["#2ec4ff", "#0b1d4a"], chips: ["бесплатно", "турнир недели"] });
WIDE_GAMES.add("stack");
GAME_OPEN.stack = () => openStack();
GAME_SECTIONS.splice(1, 0, ["Ловкость", "target", ["stack"]]);
GAME_NAMES.stack = ["target", "Стопка"];

const STK = { d: null, run: null, busy: false };
const STK_BH = 24;   // высота этажа, px

// позиция левого края блока i через e мс после появления — бит в бит как simulate() в stack.py
function stkX(c, off, i, w, e) {
  const d = c.F + 2 * c.OVER - w, p = Math.max(c.PMIN, c.P0 - c.PSTEP * i);
  const s = (Math.floor(off * 2 * d / 10000) + Math.floor(e * 2 * d / p)) % (2 * d);
  return -c.OVER + (s < d ? s : 2 * d - s);
}
const stkLeft = s => { const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600); return d ? `${d} д ${h} ч` : `${h} ч ${Math.floor(s % 3600 / 60)} мин`; };

async function openStack() {
  const el = openSheet(`<div class="stk-head"><img src="${STK_ICON}" alt=""><div><h2>Стопка</h2><span>Ставь блоки точно друг на друга. Чем выше башня — тем выше в турнире</span></div></div>
    <div class="stk-stats" id="stk-stats"></div>
    <div class="stk-play" id="stk-play">
      <canvas id="stk-cv"></canvas>
      <div class="stk-score" id="stk-score">0</div>
      <div class="stk-pop" id="stk-pop"></div>
      <div class="stk-ov" id="stk-ov"></div>
    </div>
    <div id="stk-info">${emptyHTML("hourglass", "Загружаем турнир…")}</div>`, "stk-s");
  el._onClose = () => { STK.run = null; };
  stkScene(el);
  stkOverlay("start");
  await stkLoad();
}

async function stkLoad(d) {
  if (!d) { try { d = await api("stack"); } catch (e) { return; } }
  STK.d = d;
  const st = $("#stk-stats"), info = $("#stk-info"); if (!st || !info) return;
  st.innerHTML = `<div><span>Рекорд недели</span><b>${d.week || "—"}</b></div><div><span>Место</span><b>${d.rank ? "#" + d.rank : "—"}</b></div><div><span>Лучший</span><b>${d.best || "—"}</b></div>`;
  const row = (x, i, extra) => `<div class="stk-row${x.user.id === ME.id ? " me" : ""}"><i class="stk-pl p${i + 1}">${i + 1}</i>${avaHTML(x.user, 30)}<span class="grow">${esc(x.user.name)}</span>${extra || ""}<b>${x.score}</b></div>`;
  info.innerHTML = `<div class="sec-t">${ic("trophy")}Призы недели<em class="stk-end">ещё ${stkLeft(d.endsIn)}</em></div>
    <div class="stk-prz">${d.prizes.map((p, i) => `<div class="${i < 3 ? "t" + (i + 1) : ""}"><span>${i + 1}</span><b>${short(p)} ⭐</b></div>`).join("")}</div>
    <p class="stk-rule">${ic("lock")}Приз — только от <b>${d.min} этажей</b> и с ${d.minLevel} уровня. Новичку столько не построить: блоки ускоряются с каждым этажом, тренируйся</p>
    <div class="sec-t">${ic("users")}Топ недели</div>
    <div class="box stk-top">${d.top.length ? d.top.map((x, i) => row(x, i, x.score >= d.min && i < d.prizes.length ? `<em>+${short(d.prizes[i])}</em>` : "")).join("") : `<div class="hint stk-none">Пока никто не играл — стань первым</div>`}</div>
    ${d.last && d.last.length ? `<div class="sec-t">${ic("award")}Победители прошлой недели</div><div class="box stk-top">${d.last.map((x, i) => row(x, i, `<em>+${short(x.prize)}</em>`)).join("")}</div>` : ""}
    <div class="disc">Без ставок и бесплатно — сколько угодно попыток. В зачёт идёт лучший результат недели (пн–вс по Москве). Результат проверяет сервер.</div>`;
  starify(info);
}

// ---------------- сцена ----------------
function stkScene(el) {
  const cv = el.querySelector("#stk-cv"), box = el.querySelector("#stk-play");
  const S = { cv, ctx: cv.getContext("2d"), box, w: 0, h: 0, dpr: 1, cam: 0, raf: 0, bg: null, falls: [], flash: 0 };
  const size = () => {
    const r = box.getBoundingClientRect(); if (!r.width) return;
    S.dpr = Math.min(2, devicePixelRatio || 1); S.w = r.width; S.h = r.height;
    cv.width = Math.round(S.w * S.dpr); cv.height = Math.round(S.h * S.dpr);
    S.ctx.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
    S.bg = null; stkDraw();
  };
  STK.S = S;
  requestAnimationFrame(size);
  if (window.ResizeObserver) { const ro = new ResizeObserver(size); ro.observe(box); el._ro = ro; const oc = el._onClose; el._onClose = () => { ro.disconnect(); oc && oc(); }; }
  box.addEventListener("pointerdown", e => { if (e.button > 0) return; e.preventDefault(); stkTap(e.timeStamp); });
}

// звёзды на фоне рисуем один раз в офскрин-канвас (дёшево на каждом кадре)
function stkBg(S) {
  const c = document.createElement("canvas"); c.width = S.cv.width; c.height = S.cv.height;
  const x = c.getContext("2d"); x.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
  for (let i = 0; i < 60; i++) {
    const r = Math.random();
    x.globalAlpha = .18 + r * .5; x.fillStyle = r > .85 ? "#ffe9b0" : "#fff";
    x.beginPath(); x.arc(Math.random() * S.w, Math.random() * S.h, .5 + r * 1.1, 0, 7); x.fill();
  }
  return c;
}

// ---------------- вид: объёмные коробки (косоугольная проекция). Логика по-прежнему одномерная — по x ----------------
const STK_DX = 16, STK_DY = 9;   // глубина коробки на экране: вправо-вверх
const stkSc = (S, c) => (S.w - STK_DX - 8) / (c.F + 2 * c.OVER);   // масштаб с запасом под боковую грань
const stkPal = i => { const h = (205 + i * 4.5) % 360; return { top: `hsl(${h} 88% 70%)`, front: `hsl(${h} 78% 55%)`, frontLo: `hsl(${h} 74% 44%)`, side: `hsl(${h} 70% 36%)` }; };

// коробка-подарок: передняя грань x..x+w, y..y+h, сверху и справа — грани глубины
function stkBox(ctx, x, y, w, pal, alpha = 1, h = STK_BH) {
  if (w <= 0) return;
  ctx.globalAlpha = alpha;
  // верх
  ctx.fillStyle = pal.top;
  ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + STK_DX, y - STK_DY); ctx.lineTo(x + w + STK_DX, y - STK_DY); ctx.lineTo(x + w, y); ctx.closePath(); ctx.fill();
  // бок
  ctx.fillStyle = pal.side;
  ctx.beginPath(); ctx.moveTo(x + w, y); ctx.lineTo(x + w + STK_DX, y - STK_DY); ctx.lineTo(x + w + STK_DX, y - STK_DY + h); ctx.lineTo(x + w, y + h); ctx.closePath(); ctx.fill();
  // перед
  const g = ctx.createLinearGradient(0, y, 0, y + h); g.addColorStop(0, pal.front); g.addColorStop(1, pal.frontLo);
  ctx.fillStyle = g; ctx.fillRect(x, y, w, h);
  // лента подарка: по переду и по верху, если коробка достаточно широкая
  if (w > 22) {
    const rw = Math.min(8, w * .1), rx = x + w / 2 - rw / 2;
    ctx.fillStyle = "rgba(255,255,255,.42)"; ctx.fillRect(rx, y, rw, h);
    ctx.fillStyle = "rgba(255,255,255,.5)";
    ctx.beginPath(); ctx.moveTo(rx, y); ctx.lineTo(rx + STK_DX, y - STK_DY); ctx.lineTo(rx + rw + STK_DX, y - STK_DY); ctx.lineTo(rx + rw, y); ctx.closePath(); ctx.fill();
  }
  // тонкие грани — читается объём даже на одном цвете
  ctx.strokeStyle = "rgba(255,255,255,.22)"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(x + .5, y + .5); ctx.lineTo(x + w - .5, y + .5); ctx.stroke();
  ctx.strokeStyle = "rgba(0,0,0,.18)";
  ctx.beginPath(); ctx.moveTo(x, y + h - .5); ctx.lineTo(x + w, y + h - .5); ctx.stroke();
  ctx.globalAlpha = 1;
}

function stkDraw(now) {
  const S = STK.S; if (!S || !S.w) return;
  const ctx = S.ctx, run = STK.run, c = run ? run.cfg : { F: 1000, OVER: 160, W0: 340 };
  const sc = stkSc(S, c), px = x => (x + c.OVER) * sc;
  const n = run ? run.tower.length - 1 : 0;
  // камера плавно едет за верхушкой: верхний блок держим на ~55% высоты
  const want = Math.max(0, (n + 2) * STK_BH - S.h * .55);
  S.cam += (want - S.cam) * .14;
  // фон: спокойная ночь, с высотой медленно уходит в фиолетовый
  const hb = 225 + Math.min(60, n * .8);
  const g = ctx.createLinearGradient(0, 0, 0, S.h);
  g.addColorStop(0, `hsl(${hb + 20} 55% 9%)`); g.addColorStop(1, `hsl(${hb} 58% 21%)`);
  ctx.fillStyle = g; ctx.fillRect(0, 0, S.w, S.h);
  if (!S.bg) S.bg = stkBg(S);
  const sh = (S.cam * .25) % S.h;
  ctx.drawImage(S.bg, 0, sh - S.h, S.w, S.h); ctx.drawImage(S.bg, 0, sh, S.w, S.h);
  const yOf = k => S.h - 34 - (k + 1) * STK_BH + S.cam;
  const tower = run ? run.tower : [[(c.F - c.W0) / 2, c.W0]];
  // мягкое свечение у верхушки
  const tt = tower[tower.length - 1], gx = px(tt[0] + tt[1] / 2) + STK_DX / 2, gy = yOf(tower.length - 1);
  const rg = ctx.createRadialGradient(gx, gy, 0, gx, gy, S.w * .55);
  rg.addColorStop(0, `hsla(${(205 + n * 4.5) % 360} 90% 65% / .22)`); rg.addColorStop(1, "hsla(0 0% 0% / 0)");
  ctx.fillStyle = rg; ctx.fillRect(0, 0, S.w, S.h);
  // пьедестал: широкая тёмная плита с тенью
  const by = yOf(-1);
  if (by < S.h + STK_BH) {
    const pw = c.W0 * 1.35 * sc, pxl = px(c.F / 2) - pw / 2;
    ctx.fillStyle = "rgba(0,0,0,.35)"; ctx.beginPath(); ctx.ellipse(pxl + pw / 2 + STK_DX / 2, by + STK_BH + 6, pw * .62, 9, 0, 0, 7); ctx.fill();
    stkBox(ctx, pxl, by, pw, { top: "#3b4565", front: "#2a3150", frontLo: "#1d2340", side: "#161b33" }, 1, S.h - by + 40);
  }
  const k0 = Math.max(0, Math.floor((S.cam - 40) / STK_BH) - 1);
  for (let k = k0; k < tower.length; k++) { const y = yOf(k); if (y > S.h + STK_DY) continue; if (y < -STK_BH - STK_DY) break; stkBox(ctx, px(tower[k][0]), y, tower[k][1] * sc, stkPal(k)); }
  // едущий блок + его тень на башне
  if (run && run.live) {
    const e = Math.max(0, Math.floor((now || performance.now()) - run.t0)), w = tt[1];
    const mx = px(stkX(c, run.off[n], n + 1, w, e)), my = yOf(n + 1);
    stkBox(ctx, mx, my, w * sc, stkPal(n + 1));
  }
  // отрезанные куски кувыркаются вниз
  S.falls = S.falls.filter(f => f.y < S.h + 80 && f.a > .02);
  for (const f of S.falls) {
    f.vy += .55; f.y += f.vy; f.x += f.vx || 0; f.rot = (f.rot || 0) + (f.vr || 0); f.a *= .975;
    ctx.save(); ctx.translate(f.x + f.w / 2, f.y + STK_BH / 2); ctx.rotate(f.rot);
    stkBox(ctx, -f.w / 2, -STK_BH / 2, f.w, f.pal || stkPal(f.i || 0), f.a); ctx.restore();
  }
  if (S.flash > .01) {   // вспышка «идеально»: светящаяся рамка по верхней грани
    const y = yOf(tower.length - 1), x = px(tt[0]), w = tt[1] * sc, grow = (1 - S.flash) * 10;
    ctx.strokeStyle = `rgba(255,248,214,${S.flash})`; ctx.lineWidth = 2.5; ctx.shadowColor = "#fff6c8"; ctx.shadowBlur = 12 * S.flash;
    ctx.beginPath(); ctx.moveTo(x - grow, y + grow * .3); ctx.lineTo(x + STK_DX - grow * .3, y - STK_DY - grow * .5); ctx.lineTo(x + w + STK_DX + grow, y - STK_DY - grow * .5); ctx.lineTo(x + w + grow * .3, y + grow * .3); ctx.closePath(); ctx.stroke();
    ctx.shadowBlur = 0;
    S.flash *= .9;
  }
}

function stkLoop() {
  const S = STK.S; if (!S || !S.cv.isConnected) return;
  cancelAnimationFrame(S.raf);
  const f = now => {
    if (!S.cv.isConnected) return;
    stkDraw(now);
    const busy = (STK.run && STK.run.live) || S.falls.length || S.flash > .01 || Math.abs(S.cam - Math.max(0, ((STK.run ? STK.run.tower.length : 1) + 1) * STK_BH - S.h * .55)) > .5;
    if (busy) S.raf = requestAnimationFrame(f); else S.raf = 0;   // в покое кадры не крутим
  };
  S.raf = requestAnimationFrame(f);
}

// ---------------- партия ----------------
async function stkStart() {
  if (STK.busy) return;
  STK.busy = true;
  let r;
  try { r = await post("stack/start"); } catch (e) { STK.busy = false; return; } finally { STK.busy = false; }
  if (!$("#stk-cv")) return;
  const c = r.cfg;
  STK.run = { id: r.id, off: r.off, cfg: c, tower: [[(c.F - c.W0) / 2, c.W0]], taps: [], streak: 0, perfect: 0, live: true, t0: performance.now() + 450 };
  STK.S.falls = []; STK.S.flash = 0;
  $("#stk-score").textContent = "0"; $("#stk-score").classList.add("on");
  stkOverlay(null);
  H.imp("medium");
  stkLoop();
}

function stkTap(ts) {
  const run = STK.run; if (!run || !run.live) return;
  const c = run.cfg, t = ts && ts > 0 && Math.abs(ts - performance.now()) < 1000 ? ts : performance.now();
  const e = Math.round(t - run.t0);
  if (e < c.MIN_E) return;   // слишком рано после прошлого блока — тап не считаем
  if (e > 60000) return stkOver();
  const n = run.tower.length - 1, [pl, pw] = run.tower[n], i = n + 1, w = pw;
  const x = stkX(c, run.off[n], i, w, e);
  run.taps.push(e); run.t0 += e;
  const S = STK.S, sc = stkSc(S, c), y = S.h - 34 - (i + 1) * STK_BH + S.cam;
  if (Math.abs(x - pl) <= c.PERFECT) {
    run.streak++; run.perfect++;
    const nw = run.streak >= c.GROW_AFTER ? Math.min(c.W0, pw + c.GROW) : pw;
    run.tower.push([pl, nw]);
    S.flash = 1; H.ok();
    stkPop(run.streak >= c.GROW_AFTER ? "Идеально! +ширина" : run.streak > 1 ? `Идеально ×${run.streak}` : "Идеально!");
  } else {
    const lo = Math.max(x, pl), hi = Math.min(x + w, pl + pw);
    if (hi - lo <= 0) {   // мимо башни — блок падает целиком
      S.falls.push({ x: (x + c.OVER) * sc, y, w: w * sc, vy: 0, vx: x < pl ? -1.2 : 1.2, vr: x < pl ? -.05 : .05, a: 1, i });
      return stkOver();
    }
    // отрезанный кусок
    const cutX = x < pl ? x : hi, cutW = w - (hi - lo);
    if (cutW > 0) S.falls.push({ x: (cutX + c.OVER) * sc, y, w: cutW * sc, vy: -1.5, vx: x < pl ? -1.4 : 1.4, vr: x < pl ? -.06 : .06, a: 1, i });
    run.tower.push([lo, hi - lo]); run.streak = 0;
    H.imp("light");
  }
  const sEl = $("#stk-score"); sEl.textContent = run.tower.length - 1; sEl.classList.remove("bump"); void sEl.offsetWidth; sEl.classList.add("bump");
  stkLoop();
}

function stkPop(text) {
  const p = $("#stk-pop"); if (!p) return;
  p.textContent = text; p.classList.remove("on"); void p.offsetWidth; p.classList.add("on");
}

async function stkOver() {
  const run = STK.run; if (!run || !run.live) return;
  run.live = false; H.err();
  const score = run.tower.length - 1;
  stkLoop();
  stkOverlay("wait", score);
  let r = null;
  for (let a = 0; a < 3 && !r; a++) { try { r = await post("stack/finish", { id: run.id, taps: run.taps }); } catch (e) { if (e && e.status && e.status !== "dup") break; await sleep(800); } }
  if (STK.run !== run || !$("#stk-ov")) return;
  if (!r) return stkOverlay("over", score, { err: true });
  stkOverlay("over", r.score, r);
  if (r.newBest && r.score) { H.ok(); burstAt($("#stk-score")); }
  stkLoad(r);
}

function stkOverlay(kind, score, r) {
  const ov = $("#stk-ov"); if (!ov) return;
  if (!kind) { ov.className = "stk-ov"; ov.innerHTML = ""; return; }
  const d = STK.d;
  ov.className = "stk-ov on";
  if (kind === "start") ov.innerHTML = `<div class="stk-card start"><b class="stk-big">Тапни, чтобы поставить блок</b>
      <span>Что свисает — отрезается. Ровно в край — «идеально»: три подряд расширяют блок</span>
      <button class="btn gold" data-act="stk-go">${ic("play")}Играть</button></div>`;
  else if (kind === "wait") ov.innerHTML = `<div class="stk-card"><span>Этажей</span><b class="stk-big">${score}</b><span>Проверяем результат…</span></div>`;
  else {
    const left = d ? Math.max(0, d.min - (r.week || 0)) : 0;
    ov.innerHTML = `<div class="stk-card"><span>${r.rejected ? "Результат не засчитан" : r.err ? "Нет связи — результат не отправлен" : r.newBest && score ? "Новый рекорд недели!" : "Этажей"}</span>
      <b class="stk-big">${score}</b>
      ${!r.err && !r.rejected ? `<span>${r.rank ? `Место в турнире: <b>#${r.rank}</b>` : ""}${left ? `${r.rank ? " · " : ""}до призовой зоны ещё ${left}` : ""}</span>` : ""}
      <button class="btn gold" data-act="stk-go">${ic("refresh")}Ещё раз</button></div>`;
  }
}

Object.assign(ACT, { "stk-go": () => stkStart() });

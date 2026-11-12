"use strict";
// ============================================================
//  Джекпот на подарки, рулетка, сеты коллекций, история цен
// ============================================================
GAMES.splice(2, 0, { id: "jroul", t: "Джекпот", s: "Кидай подарки в общий банк — колесо решит, кто заберёт всё", img: "Heart Locket", k: ["#ff3d6e", "#3d0418"], chips: ["на подарки", "PvP"] });
GAMES.push({ id: "rlt", t: "Рулетка", s: "Красное, чёрное, числа и дюжины", img: "Crystal Ball", k: ["#d6283f", "#2a0309"], chips: ["x36 на число"] });
WIDE_GAMES.add("jroul");
Object.assign(GAME_OPEN, { jroul: () => openJR(), rlt: () => openRL() });
const SEG_COL = ["#4aa8ff", "#ff6fb5", "#ffc53d", "#35d07f", "#a77bff", "#ff8a3d", "#2fd6ff", "#ff5c5c"];

// ============================================================ ДЖЕКПОТ НА ПОДАРКИ
let JR = null, jrPoll = null, jrAnimated = 0, jrAngle = 0, jrRevealed = 0, jrRound = 0;   // jrRevealed — раунд, победитель которого уже показан
async function openJR() {
  const el = openSheet(`${gameHead("Heart Locket", "Джекпот", "Кидай подарки в банк — колесо решит, кто заберёт всё", "jroul")}
    <div class="jrw"><canvas id="jr-cv" width="600" height="600"></canvas><div class="jrptr"></div>
      <div class="jrc" id="jr-c"></div></div>
    <div class="jrhist" id="jr-h"></div>
    <div class="betp">
      <button class="btn cta gold" data-act="jr-gifts">${ic("gift")}Поставить подарки</button>
      <div class="jrst"><label class="amtf"><span>⭐</span><input id="jr-amt" inputmode="numeric" value="500"></label><button class="btn ghost" data-act="jr-stars">Поставить звёзды</button></div>

    </div>
    <div class="sec-t">Участники <span id="jr-n"></span></div><div id="jr-p"></div>`, "jr-s");
  el._onClose = () => clearInterval(jrPoll);
  jrAnimated = 0; jrRevealed = 0; jrRound = 0; jrAngle = 0;
  await jrLoad();
  clearInterval(jrPoll); jrPoll = setInterval(() => el.isConnected ? bgOff() || jrLoad() : clearInterval(jrPoll), 1200);
}
async function jrLoad() {
  try { JR = await api("jroul"); } catch (e) { return; }
  JR.off = JR.now - Date.now() / 1000;
  jrDraw();
}
function jrDraw() {
  const cv = $("#jr-cv"); if (!cv || !JR) return;
  const ps = JR.players, total = JR.total || 1;
  if (JR.id !== jrRound) { jrRound = JR.id; cv.style.transform = "none"; jrAngle = 0; }   // новый раунд — колесо с нуля вместе с новым содержимым
  const shown = JR.status === "open" || jrRevealed === JR.id;   // победителя показываем только после остановки колеса
  const wk = JR.id + "|" + ps.map(p => p.id + ":" + p.value).join(",");
  if ((jrAnimated !== JR.id || JR.status === "open") && cv._wk !== wk) { cv._wk = wk; jrWheel(cv, ps, total); }   // колесо — только если поменялись ставки; во время вращения не трогаем
  if (JR.status !== "open" && jrAnimated !== JR.id) jrSpin();
  jrInfo(shown);
}
function jrWheel(cv, ps, total) {
  const c = cv.getContext("2d"), R = 300;
  c.clearRect(0, 0, 600, 600);
  if (!ps.length) { c.beginPath(); c.arc(R, R, R - 10, 0, 6.283); c.arc(R, R, R - 90, 0, 6.283, true); c.fillStyle = "rgba(255,255,255,.07)"; c.fill("evenodd"); }
  let a0 = -Math.PI / 2;
  ps.forEach((p, i) => {
    const a1 = a0 + p.value / total * Math.PI * 2;
    c.beginPath(); c.arc(R, R, R - 10, a0, a1); c.arc(R, R, R - 90, a1, a0, true); c.closePath();
    c.fillStyle = SEG_COL[i % SEG_COL.length]; c.fill();
    c.strokeStyle = "#141420"; c.lineWidth = 4; c.stroke();     // зазор между секторами
    a0 = a1;
  });
}
// HTML меняем только если он реально другой: иначе опрос раз в 1,2 с пересоздавал картинки подарков — мигание и рывки
const jrSet = (el, h) => { if (el && el._h !== h) { el._h = h; el.innerHTML = h; starify(el); } };
function jrInfo(shown) {
  const ps = JR.players, t = Date.now() / 1000 + (JR.off || 0);
  let center;
  if (JR.status === "open") {
    const left = JR.deadline ? Math.max(0, Math.ceil(JR.deadline - t)) : null;
    center = `<span>Банк</span><b>⭐ ${short(JR.total)}</b><em>${left != null ? `розыгрыш через ${left}с` : ps.length ? "ждём второго игрока" : "сделай первую ставку"}</em>`;
  } else if (!shown) {
    center = `<span>Крутим…</span><b>⭐ ${short(JR.total)}</b><em>${ps.length} ${plural(ps.length, ["игрок", "игрока", "игроков"])}</em>`;
  } else {
    const w = ps.find(p => p.id === JR.winner);
    center = `<span>Победитель</span><b class="jr-wn">${w ? (w.id === ME.id ? "Ты!" : esc(w.name)) : "…"}</b><em>${w ? `+⭐ ${short(JR.total)} · шанс ${w.chance}%` : ""}</em>`;
  }
  jrSet($("#jr-c"), center);
  $("#jr-n").textContent = ps.length ? `${ps.length} · ⭐ ${fmt(JR.total)}` : "";
  jrSet($("#jr-p"), ps.length ? ps.map((p, i) => `<div class="jrp${shown && JR.winner === p.id ? " jrp-won" : ""}"><i style="background:${SEG_COL[i % SEG_COL.length]}"></i>${avaHTML(p, 34)}
      <div class="grow"><div class="t">${p.id === ME.id ? "Ты" : esc(p.name)}</div><div class="s">⭐ ${fmt(p.value)}${p.stars ? ` · звёзды ${short(p.stars)}` : ""}</div></div>
      <div class="jrg">${p.gifts.slice(0, 4).map(g => `<div>${giftHTML(g, { lite: true, plain: true })}</div>`).join("")}${p.gifts.length > 4 ? `<span>+${p.gifts.length - 4}</span>` : ""}</div>
      <b class="jrch">${p.chance}%</b></div>`).join("") : emptyHTML("gift", "Банк пуст — закинь подарки первым"));
  jrSet($("#jr-h"), (JR.history || []).map(h => `<div data-act="profile" data-id="${h.id}">${avaHTML(h, 28)}<span>⭐ ${short(h.total)}</span><small>${h.chance}%</small></div>`).join(""));
}
async function jrSpin() {
  jrAnimated = JR.id;
  const id = JR.id, cv = $("#jr-cv"), target = 360 * 6 - JR.ticket * 360, dur = (JR.spin || 7) * 1000 - 600;
  // зашёл посреди вращения — продолжаем с нужного места, а не крутим заново
  const elapsed = JR.spinAt ? Math.max(0, (Date.now() / 1000 + (JR.off || 0) - JR.spinAt) * 1000) : 0;
  const t0 = performance.now() - Math.min(elapsed, dur);
  cv.style.willChange = "transform";
  let last = 0;
  await new Promise(done => (function f(now) {
    if (!cv.isConnected || JR.id !== id) return done();
    const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 4), a = target * e;
    cv.style.transform = `rotate(${a}deg)`;
    if (a - last > 12) { last = a; H.sel(); }
    k < 1 ? requestAnimationFrame(f) : done();
  })(performance.now()));
  cv.style.willChange = "";
  if (!cv.isConnected || JR.id !== id) return;
  jrAngle = target; jrRevealed = id;
  jrInfo(true);
  const c = $("#jr-c"); if (c) { c.classList.remove("rev"); void c.offsetWidth; c.classList.add("rev"); }
  if (elapsed >= dur) return;   // открыли окно уже после остановки — без салюта
  if (JR.winner === ME.id) { H.ok(); burstAt(cv); setTimeout(() => burstAt(cv), 300); toast(`Джекпот твой! ⭐ ${fmt(JR.total)}`, "ok"); loadMe(); MYP = null; }
  else if (JR.players.some(p => p.id === ME.id)) H.err();
}

// ============================================================ РУЛЕТКА (европейская)
const RL_ORDER = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26];
const RL_RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);
const RL = { chip: 50, bets: {}, busy: false, angle: 0, hist: [] };
const rlCol = n => n === 0 ? "g" : RL_RED.has(n) ? "r" : "b";
function openRL() {
  RL.busy = false; RL.bets = {};
  openSheet(`${gameHead("Crystal Ball", "Рулетка", "Красное, чёрное, числа и дюжины", "rlt")}
    <div class="rlw"><canvas id="rl-cv" width="600" height="600"></canvas><div class="rlptr"></div><div class="rlc" id="rl-c"><b>?</b></div></div>
    <div class="rlhist" id="rl-h"></div>
    <div class="rlchips">${[10, 50, 100, 500, 1000].map(v => `<button data-act="rl-chip" data-v="${v}" class="${RL.chip === v ? "on" : ""}">${short(v)}</button>`).join("")}</div>
    <div class="rlboard" id="rl-b"></div>
    <div class="betp"><div class="btns" style="margin:0"><button class="btn ghost" data-act="rl-clear">${ic("x")}Очистить</button><button class="btn ghost" data-act="rl-dbl">×2</button></div>
      <button class="btn cta gold" id="rl-go" data-act="rl-spin">Крутить</button></div>
    `, "rl-s");
  rlWheel(); rlBoard();
}
function rlWheel() {
  const cv = $("#rl-cv"); if (!cv) return;
  const c = cv.getContext("2d"), R = 300, n = 37, step = Math.PI * 2 / n;
  c.clearRect(0, 0, 600, 600);
  RL_ORDER.forEach((num, i) => {
    const a0 = -Math.PI / 2 + i * step - step / 2;
    c.beginPath(); c.moveTo(R, R); c.arc(R, R, R - 6, a0, a0 + step); c.closePath();
    c.fillStyle = num === 0 ? "#139a52" : RL_RED.has(num) ? "#c8203a" : "#1c1c26"; c.fill();
    c.strokeStyle = "rgba(255,215,120,.5)"; c.lineWidth = 2; c.stroke();
    c.save(); c.translate(R, R); c.rotate(a0 + step / 2 + Math.PI / 2);
    c.fillStyle = "#fff"; c.font = "800 22px -apple-system,Segoe UI,sans-serif"; c.textAlign = "center"; c.fillText(num, 0, -R + 38); c.restore();
  });
  c.beginPath(); c.arc(R, R, R - 70, 0, 6.283); c.fillStyle = "#2a1a0a"; c.fill();
  c.beginPath(); c.arc(R, R, R - 70, 0, 6.283); c.strokeStyle = "#c88a00"; c.lineWidth = 8; c.stroke();
}
const rlKey = (t, v) => t + ":" + (v ?? "");
const rlTotal = () => Object.values(RL.bets).reduce((s, b) => s + b.a, 0);
function rlBoard(win = []) {
  const b = $("#rl-b"); if (!b) return;
  const chip = (t, v) => { const x = RL.bets[rlKey(t, v)]; return x ? `<em>${short(x.a)}</em>` : ""; };
  const cell = (t, v, label, cls = "") => `<button class="rc ${cls}${win.includes(rlKey(t, v)) ? " win" : ""}" data-act="rl-bet" data-t="${t}" data-v="${v ?? ""}">${label}${chip(t, v)}</button>`;
  let nums = "";
  for (let r = 0; r < 12; r++) for (let c = 1; c <= 3; c++) { const n = r * 3 + c; nums += cell("num", n, n, rlCol(n)); }
  b.innerHTML = `${cell("num", 0, "0", "g zero")}<div class="rnums">${nums}</div>
    <div class="rrow">${cell("dozen", 0, "1–12")}${cell("dozen", 1, "13–24")}${cell("dozen", 2, "25–36")}</div>
    <div class="rrow">${cell("low", null, "1–18")}${cell("even", null, "Чёт")}${cell("red", null, "<i class='rd'></i>")}${cell("black", null, "<i class='bk'></i>")}${cell("odd", null, "Нечет")}${cell("high", null, "19–36")}</div>`;
  const go = $("#rl-go"); if (go && !RL.busy) go.textContent = rlTotal() ? `Крутить · ⭐ ${fmt(rlTotal())}` : "Поставь фишки на поле";
}
async function rlSpin() {
  if (RL.busy) return;
  const bets = Object.values(RL.bets);
  if (!bets.length) return toast("Поставь фишки на поле");
  if (rlTotal() > ME.stars) return toast("Не хватает звёзд ⭐");
  RL.busy = true; $("#rl-go").disabled = true;
  setStars(ME.stars - rlTotal());
  let r;
  try { r = await post("rlt", { bets }); } catch (e) { RL.busy = false; const g = $("#rl-go"); if (g) g.disabled = false; loadMe(); return; }
  if (!$("#rl-cv")) { RL.busy = false; loadMe(); return; }   // окно закрыли, пока шла ставка — иначе RL.busy залипнет
  const cv = $("#rl-cv"), idx = RL_ORDER.indexOf(r.n), seg = 360 / 37;
  const target = 360 - idx * seg + (Math.random() - .5) * seg * .5, start = RL.angle - RL.angle % 360, end = start + 360 * 5 + target, t0 = performance.now();
  $("#rl-c").innerHTML = "<b>…</b>";
  let lastSeg = -1;
  await new Promise(done => (function f(now) {
    const k = Math.min(1, (now - t0) / 4200), e = 1 - Math.pow(1 - k, 4), a = RL.angle + (end - RL.angle) * e;
    cv.style.transform = `rotate(${a}deg)`;
    const s = Math.floor(a / seg); if (s !== lastSeg) { lastSeg = s; H.sel(); }
    k < 1 && cv.isConnected ? requestAnimationFrame(f) : done();
  })(t0));
  RL.angle = end;
  RL.busy = false;
  if (!cv.isConnected) { loadMe(); return; }
  $("#rl-go").disabled = false;
  $("#rl-c").innerHTML = `<b class="${rlCol(r.n)}">${r.n}</b>`;
  RL.hist = [r.n, ...RL.hist].slice(0, 14);
  $("#rl-h").innerHTML = RL.hist.map(n => `<span class="${rlCol(n)}">${n}</span>`).join("");
  const winKeys = r.win.map(i => rlKey(bets[i].t, bets[i].v));
  rlBoard(winKeys);
  setStars(r.stars);
  const net = r.pay - rlTotal();
  if (r.pay > 0) { (net >= 0 ? H.ok : H.imp)("medium"); toast(net >= 0 ? `+⭐ ${fmt(r.pay)}` : `Вернулось ⭐ ${fmt(r.pay)}`, net >= 0 ? "ok" : ""); if (net > 0) { burstAt(cv); winFx(null, r.pay, rlTotal()); } }
  else { H.err(); toast("Мимо — ставки сгорели", "err"); }
  afterLevelUp(r.levelup);
}

// ============================================================ ИСТОРИЯ ЦЕН (маркет, выбранная коллекция)
async function priceHistory(col) {
  const box = $("#mk-hist"); if (!box) return;
  const d = await api("market/history?col=" + enc(col)); if (!$("#mk-hist")) return;
  const pts = d.days.map((x, i) => ({ i, ...x })), withP = pts.filter(p => p.avg != null);
  const vals = withP.map(p => p.avg), maxN = Math.max(1, ...pts.map(p => p.n));
  const last7 = d.days.slice(-7).filter(x => x.avg != null), avg7 = last7.length ? Math.round(last7.reduce((s, x) => s + x.avg * x.n, 0) / last7.reduce((s, x) => s + x.n, 0)) : null;
  const sold = pts.reduce((s, p) => s + p.n, 0);
  const W = 340, Hc = 110, padL = 6, padR = 6, padT = 12, padB = 8;
  const lo = vals.length ? Math.min(...vals) * .9 : 0, hi = vals.length ? Math.max(...vals) * 1.1 : 1;
  const X = i => padL + i / 13 * (W - padL - padR), Y = v => padT + (1 - (v - lo) / Math.max(1, hi - lo)) * (Hc - padT - padB);
  // линия рвётся на днях без продаж
  let path = "", pen = false;
  pts.forEach(p => { if (p.avg == null) { pen = false; return; } path += `${pen ? "L" : "M"}${X(p.i).toFixed(1)},${Y(p.avg).toFixed(1)}`; pen = true; });
  const bw = (W - padL - padR) / 14 - 2;
  box.innerHTML = `<div class="ph">
    <div class="ph-h"><img src="${A.orig(col, 64)}" alt=""><div><b>${esc(col)}</b><span>Средняя цена продажи за 14 дней</span></div></div>
    <div class="ph-k"><div><span>Флор сейчас</span><b>${d.floor ? "⭐ " + fmt(d.floor) : "—"}</b></div><div><span>Средняя за 7 дн.</span><b>${avg7 ? "⭐ " + fmt(avg7) : "—"}</b></div><div><span>Продаж</span><b>${sold}</b></div></div>
    ${withP.length ? `<svg class="ph-c" viewBox="0 0 ${W} ${Hc}" preserveAspectRatio="none">
      <line x1="${padL}" x2="${W - padR}" y1="${Y(lo / .9 * 1)}" y2="${Y(lo / .9 * 1)}" class="gl"/>
      <path d="${path}" class="ln"/>
      ${withP.map(p => `<circle cx="${X(p.i)}" cy="${Y(p.avg)}" r="4" class="pt"/><rect x="${X(p.i) - 12}" y="0" width="24" height="${Hc}" class="hit" data-i="${p.i}"/>`).join("")}
    </svg>
    <svg class="ph-v" viewBox="0 0 ${W} 28" preserveAspectRatio="none">${pts.map(p => p.n ? `<rect x="${X(p.i) - bw / 2}" y="${28 - p.n / maxN * 26}" width="${bw}" height="${p.n / maxN * 26}" rx="2"/>` : "").join("")}</svg>
    <div class="ph-tip" id="ph-tip">Нажми на точку, чтобы увидеть день</div>`
      : `<div class="hint ph-empty">Продаж этой коллекции ещё не было — ориентир по ценности: ⭐ ${fmt(d.base)}</div>`}
  </div>`;
  box.querySelectorAll(".hit").forEach(h => h.onclick = () => {
    const p = pts[+h.dataset.i]; H.sel();
    box.querySelectorAll(".pt").forEach(c => c.classList.toggle("on", +c.getAttribute("cx") === X(p.i)));
    $("#ph-tip").innerHTML = `${new Date(p.day * 1000).toLocaleDateString("ru", { day: "numeric", month: "short" })}: средняя <b>⭐ ${fmt(p.avg)}</b> · мин. ⭐ ${fmt(p.min)} · продаж ${p.n}`;
  });
}
const _lm = loadMarket;
loadMarket = async function () {
  await _lm();
  const list = $("#mk-list"); if (!list) return;
  if (MK.col) { if (!$("#mk-hist")) list.insertAdjacentHTML("beforebegin", `<div id="mk-hist"></div>`); priceHistory(MK.col); }
  else $("#mk-hist") && $("#mk-hist").remove();
};

// ============================================================ СЕТЫ: награды за разные модели коллекции
let SETS = null;
const _ri = renderInventory;
renderInventory = async function () { SETS = await api("sets").catch(() => null); return _ri(); };
const _di = drawInventory;
drawInventory = function () {
  _di();
  if (INV.mode !== "cols" || !SETS) return;
  document.querySelectorAll("#v-inv .colrow").forEach(row => {
    const col = row.dataset.v, s = SETS.sets[col]; if (!s) return;
    const pills = s.tiers.map(t => {
      const st = t.claimed ? "done" : s.have >= t.tier ? "ready" : "lock";
      return `<span class="tierp ${st}" ${st === "ready" ? `data-act="set-claim" data-col="${esc(col)}" data-tier="${t.tier}"` : ""}>${st === "done" ? ic("check") : ""}${t.tier} мод.${st === "done" ? "" : ` · ⭐ ${short(t.reward)}`}</span>`;
    }).join("");
    row.querySelector(".grow").insertAdjacentHTML("beforeend", `<div class="tiers">${pills}</div>`);
  });
  const head = document.querySelector("#v-inv .hint");
  if (head && SETS) head.innerHTML = `Собирай разные модели: за 5, 10 и 25 моделей одной коллекции — награда звёздами. Получено наград: <b>${SETS.claimed}</b>`;
};

// ------------------------------------------------------------ действия
Object.assign(ACT, {
  "jr-gifts": () => pickGifts("В джекпот", { max: 10 }, async gs => {
    const r = await post("jroul/bet", { gifts: gs.map(g => g.id) }); setStars(r.stars); H.ok(); toast("Подарки в банке", "ok"); JR = { ...r, history: JR && JR.history }; JR.off = JR.now - Date.now() / 1000; jrDraw(); MYP = null;
  }),
  "jr-stars": async () => {
    const stars = betVal("jr-amt"); if (stars > ME.stars) return toast("Не хватает звёзд ⭐");
    const r = await post("jroul/bet", { stars }); setStars(r.stars); H.ok(); JR = { ...r, history: JR && JR.history }; JR.off = JR.now - Date.now() / 1000; jrDraw();
  },
  "rl-chip": el => { RL.chip = +el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); },
  "rl-bet": el => {
    if (RL.busy) return;
    const t = el.dataset.t, v = el.dataset.v === "" ? null : +el.dataset.v, k = rlKey(t, v);
    RL.bets[k] = RL.bets[k] ? { ...RL.bets[k], a: RL.bets[k].a + RL.chip } : { t, v, a: RL.chip };
    H.sel(); rlBoard();
  },
  "rl-clear": () => { if (RL.busy) return; RL.bets = {}; H.sel(); rlBoard(); },
  "rl-dbl": () => { if (RL.busy) return; Object.values(RL.bets).forEach(b => b.a *= 2); H.sel(); rlBoard(); },
  "rl-spin": () => rlSpin(),
  "set-claim": async el => {
    const r = await post("sets/claim", { col: el.dataset.col, tier: +el.dataset.tier });
    setStars(r.stars); H.ok(); toast(`Награда за сет: +⭐ ${fmt(r.reward)}`, "ok"); burstAt(el);
    renderInventory();
  },
});

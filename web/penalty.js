"use strict";
// ============================================================
//  «Пенальти» — серия ударов: тапни угол ворот, вратарь прыгает. Гол — икс растёт, сейв — ставка сгорает. Забрать можно после любого гола.
// ============================================================
const PN_MODES = [["easy", "Новичок", "#35d07f"], ["mid", "Профи", "#ffc53d"], ["hard", "Легенда", "#ff4d5e"]];
// центры 5 зон в долях ворот: верх-лево, верх-право, центр, низ-лево, низ-право (как на сервере)
const PN_Z = [[.15, .3], [.85, .3], [.5, .26], [.15, .74], [.85, .74]];
// футбольный мяч: центральный пятиугольник и пять у края
function pnBall(xmlns) {
  const pent = (cx, cy, r, rot) => Array.from({ length: 5 }, (_, i) => { const a = (rot + i * 72) * Math.PI / 180; return `${(cx + r * Math.cos(a)).toFixed(1)} ${(cy + r * Math.sin(a)).toFixed(1)}`; }).join(" L");
  const edge = Array.from({ length: 5 }, (_, i) => { const a = (-90 + 36 + i * 72) * Math.PI / 180; return `<path d="M${pent(47 * Math.cos(a), 47 * Math.sin(a), 15, -90 + 36 + i * 72 + 180)}Z" fill="#1b1d26"/>`; }).join("");
  const seams = Array.from({ length: 5 }, (_, i) => { const a = (-90 + i * 72) * Math.PI / 180; return `M${(17 * Math.cos(a)).toFixed(1)} ${(17 * Math.sin(a)).toFixed(1)}L${(34 * Math.cos(a)).toFixed(1)} ${(34 * Math.sin(a)).toFixed(1)}`; }).join("");
  return `<svg ${xmlns ? 'xmlns="http://www.w3.org/2000/svg"' : 'class="pn-bsvg"'} viewBox="-52 -52 104 104"><defs>
    <radialGradient id="pnb${xmlns ? "c" : ""}" cx=".36" cy=".3" r=".8"><stop offset="0" stop-color="#fff"/><stop offset=".6" stop-color="#e9ecf3"/><stop offset="1" stop-color="#8b91a1"/></radialGradient>
    <clipPath id="pnc${xmlns ? "c" : ""}"><circle r="48"/></clipPath></defs>
    <circle r="48" fill="url(#pnb${xmlns ? "c" : ""})"/>
    <g clip-path="url(#pnc${xmlns ? "c" : ""})"><path d="M${pent(0, 0, 17, -90)}Z" fill="#1b1d26"/>${edge}<path d="${seams}" stroke="#1b1d26" stroke-width="2.6" fill="none"/></g>
    <circle r="48" fill="none" stroke="rgba(0,0,0,.25)" stroke-width="1.5"/><ellipse cx="-16" cy="-20" rx="13" ry="8" transform="rotate(-35 -16 -20)" fill="#fff" opacity=".5"/></svg>`;
}
// вратарь: стойка с разведёнными руками, салатовая форма, крупные перчатки
const PN_KEEPER = `<svg viewBox="0 0 80 100" class="pn-ksvg"><defs>
  <linearGradient id="pnj" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e6ff6a"/><stop offset="1" stop-color="#6fb800"/></linearGradient>
  <radialGradient id="pnh" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#f6cfa6"/><stop offset="1" stop-color="#c98c5e"/></radialGradient></defs>
  <ellipse cx="40" cy="97" rx="22" ry="3" fill="rgba(0,0,0,.35)"/>
  <path d="M34 68 30 93M46 68l4 25" stroke="#c6ff3d" stroke-width="6.5" stroke-linecap="round"/>
  <path d="M34 68l-1 8M46 68l1 8" stroke="#f0c39a" stroke-width="5.5" stroke-linecap="round"/>
  <ellipse cx="29" cy="94.5" rx="5.5" ry="3" fill="#111"/><ellipse cx="51" cy="94.5" rx="5.5" ry="3" fill="#111"/>
  <path d="M28 56h24l2 14H43l-3-4-3 4H26Z" fill="#141722"/>
  <path d="M30 35 13 20M50 35l17-15" stroke="url(#pnj)" stroke-width="8" stroke-linecap="round"/>
  <path d="M27 33q13-7 26 0l2 25H25Z" fill="url(#pnj)"/>
  <path d="M27 33q13-7 26 0" fill="none" stroke="#141722" stroke-width="2.4"/>
  <path d="M30 44h20M29 50h22" stroke="rgba(20,23,34,.25)" stroke-width="2"/>
  <text x="40" y="49" font-size="10" font-weight="900" text-anchor="middle" fill="#141722" font-family="Arial,sans-serif">1</text>
  <g class="pn-glove"><circle cx="11" cy="17" r="7" fill="#fff"/><path d="M5 14a7 7 0 0 1 12 0" fill="#ff7a1a"/><circle cx="11" cy="17" r="7" fill="none" stroke="#c9ced8" stroke-width="1"/></g>
  <g class="pn-glove"><circle cx="69" cy="17" r="7" fill="#fff"/><path d="M63 14a7 7 0 0 1 12 0" fill="#ff7a1a"/><circle cx="69" cy="17" r="7" fill="none" stroke="#c9ced8" stroke-width="1"/></g>
  <circle cx="40" cy="22" r="8.5" fill="url(#pnh)"/><path d="M31.5 21a8.5 8.5 0 0 1 17 0c-3-3-8-4.5-17 0Z" fill="#2b1a10"/></svg>`;
GAMES.push({ id: "penalty", t: "Пенальти", s: "Бей в угол — каждый гол растит икс. Вратарь взял — ставка сгорела", imgUrl: "data:image/svg+xml," + encodeURIComponent(pnBall(true)), k: ["#2fbf5a", "#05210f"], chips: ["новинка", "до x5000"] });
WIDE_GAMES.add("penalty");
GAME_OPEN.penalty = () => openPenalty();
AR_NEW.push("penalty");
GAME_NAMES.penalty = ["ball", "Пенальти"];

let PNS = null, pnMode = "mid", pnBusy = false, pnLastZ = -1, pnSeries = [];
async function openPenalty() {
  pnBusy = false; pnSeries = [];
  const el = openSheet(`<div class="ghead">${gpfBtn("penalty")}<img src="${GAMES.find(g => g.id === "penalty").imgUrl}" alt=""><div><h2>Пенальти</h2><span>Бей в угол и не останавливайся</span></div></div>
    <div class="ar-stage pn-stage" id="pn-stage">
      <div class="pn-lights"><i></i><i></i></div>
      <div class="pn-crowd" id="pn-crowd"><div class="pn-fans"></div><div class="pn-fans b"></div></div>
      <div class="pn-pitch"><div class="pn-grass"></div></div>
      <svg class="pn-lines" viewBox="0 0 100 100" preserveAspectRatio="none"><path d="M6 61.5-14 100M94 61.5 114 100M25 61.5 21 72H79L75 61.5" fill="none" stroke="rgba(255,255,255,.5)" stroke-width=".7" vector-effect="non-scaling-stroke"/></svg>
      <div class="pn-goal" id="pn-goal">
        <svg class="pn-net" viewBox="0 0 230 100" preserveAspectRatio="none"><defs>
          <pattern id="pnn" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><path d="M0 0H9M0 0V9" stroke="rgba(255,255,255,.32)" stroke-width="1"/></pattern>
          <linearGradient id="pnd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity=".55"/><stop offset="1" stop-color="#000" stop-opacity=".15"/></linearGradient></defs>
          <rect width="230" height="100" fill="url(#pnd)"/><rect width="230" height="100" fill="url(#pnn)"/>
          <path d="M18 14H212M18 14 4 100M212 14l14 86" stroke="rgba(255,255,255,.28)" stroke-width="1.2" fill="none"/></svg>
        <div class="pn-keeper" id="pn-keeper">${PN_KEEPER}</div>
        ${PN_Z.map(([x, y], i) => `<button class="pn-z" data-act="pn-kick" data-z="${i}" style="left:${x * 100}%;top:${y * 100}%"><i></i></button>`).join("")}
        <svg class="pn-frame" viewBox="0 0 230 100" preserveAspectRatio="none"><path d="M3.5 100V3.5H226.5V100" fill="none" stroke="#fff" stroke-width="5" vector-effect="non-scaling-stroke"/></svg>
      </div>
      <div class="pn-spot"></div>
      <div class="pn-ball" id="pn-ball">${pnBall()}</div>
      <div class="pn-hint">Тапни в угол ворот — это удар</div>
      <div class="pn-goaltxt" id="pn-gt">ГОЛ!</div>
      <div class="pn-kicks" id="pn-kicks"></div>
      <div class="ar-hud pn-hud"><div class="ar-x dim" id="pn-x">x1,00</div><div class="ar-sub" id="pn-sub"></div></div>
    </div>
    <div class="ar-ladder" id="pn-lad"></div>
    <div class="betp">
      <div class="seg ar-seg" id="pn-mode">${PN_MODES.map(([k, t, c]) => `<button data-act="pn-mode" data-v="${k}" style="--c:${c}" class="${pnMode === k ? "on" : ""}"><i></i>${t}</button>`).join("")}</div>
      <div id="pn-bet">${betHTML("pn-amt")}</div>
      <div class="ar-btns" id="pn-btns"></div>
    </div>
    <details class="rules" style="margin-top:12px"><summary>${ic("award")}Как играть</summary><div id="pn-rules"></div></details>`, "pn-s");
  el._onClose = () => { pnBusy = false; };
  PNS = await api("penalty").catch(() => null);
  if (!PNS || !$("#pn-stage")) return;
  if (PNS.active) { pnMode = PNS.mode; pnSeries = Array(PNS.step).fill(1); }
  $("#pn-mode").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === pnMode));
  $("#pn-rules").innerHTML = `Сделай ставку и тапни угол ворот — это удар. Перед каждым ударом вратарь закрывает часть ворот: «Новичок» — 1 зону из 5 (гол в ${PNS.chance.easy}% случаев),
    «Профи» — 2 (${PNS.chance.mid}%), «Легенда» — 3 (${PNS.chance.hard}%). Куда бить — не важно, шанс одинаковый.
    Каждый гол увеличивает множитель, забрать выигрыш можно после любого гола. Вратарь взял — ставка сгорает. Забил все ${PNS.kicks} — выплата автоматически. Возврат игроку — ${String(PNS.rtp).replace(".", ",")}%.`;
  pnPaint();
}
const pnTable = () => PNS.active ? PNS.table : PNS.modes[pnMode];
function pnPaint() {
  if (!PNS || !$("#pn-stage")) return;
  const k = PNS.active ? PNS.step : 0, t = pnTable(), mode = PNS.active ? PNS.mode : pnMode;
  const x = $("#pn-x"); x.textContent = arX(PNS.active ? PNS.mult : 1); x.className = "ar-x" + (PNS.active && k ? "" : " dim");
  $("#pn-sub").innerHTML = `<span class="ar-pill">${ic("trend")}Гол <b>${t[k] ? arX(t[k]) : "—"}</b></span><span class="ar-pill">${ic("ball")}Шанс <b>${PNS.chance[mode]}%</b></span>`;
  $("#pn-lad").innerHTML = t.map((m, i) => `<div class="ar-step${i < k - 1 ? " done" : ""}${PNS.active && i === k - 1 ? " cur" : ""}${i === k ? " nx" : ""}"><b>${arX(m)}</b><span>${i + 1} гол</span></div>`).join("");
  const cur = $("#pn-lad").children[Math.max(0, k - 2)]; if (cur) $("#pn-lad").scrollLeft = cur.offsetLeft - 8;
  $("#pn-kicks").innerHTML = Array.from({ length: PNS.kicks }, (_, i) => `<i class="${pnSeries[i] === 1 ? "g" : pnSeries[i] === 0 ? "x" : ""}"></i>`).join("");
  pnUI();
}
function pnUI() {
  const b = $("#pn-btns"); if (!b || !PNS) return;
  const on = PNS.active;
  $("#pn-bet").style.display = on ? "none" : "";
  $("#pn-mode").querySelectorAll("button").forEach(x => x.disabled = on);
  $("#pn-stage").classList.toggle("busy", pnBusy);
  $("#pn-stage").classList.toggle("live", on);
  b.innerHTML = on
    ? `<button class="btn cta gold ar-two" data-act="pn-kick" data-z="r" ${pnBusy ? "disabled" : ""}><b>${ic("ball")}Бить</b><small>до ${PNS.next ? arX(PNS.next) : "—"}</small></button>
       <button class="btn cta green ar-two" data-act="pn-cash" ${!PNS.step || pnBusy ? "disabled" : ""}><b>Забрать</b><small>⭐ ${short(PNS.bet * PNS.mult)}</small></button>`
    : `<button class="btn cta gold" data-act="pn-kick" data-z="r" ${pnBusy ? "disabled" : ""}>${ic("ball")} Бить</button>`;
  starify(b);
}
// координаты центра зоны относительно сцены
function pnZonePt(z) {
  const st = $("#pn-stage").getBoundingClientRect(), g = $("#pn-goal").getBoundingClientRect();
  return [g.left - st.left + g.width * PN_Z[z][0], g.top - st.top + g.height * PN_Z[z][1]];
}
function pnDive(z) {
  const g = $("#pn-goal"), kp = $("#pn-keeper"), gw = g.clientWidth, gh = g.clientHeight, [zx, zy] = PN_Z[z];
  const dx = (zx - .5) * gw * .72, dy = (zy - .62) * gh, rot = zx < .5 ? (zy > .5 ? -84 : -58) : zx > .5 ? (zy > .5 ? 84 : 58) : 0;
  kp.style.transform = `translate(${dx.toFixed(1)}px,${dy.toFixed(1)}px) rotate(${rot}deg)${zx === .5 ? " scale(1.06)" : ""}`;
  kp.classList.add("dive");
}
async function pnKick(z) {
  if (pnBusy || !PNS) return;
  if (z < 0) z = pnLastZ >= 0 && Math.random() < .5 ? pnLastZ : Math.floor(Math.random() * 5);
  pnLastZ = z;
  pnBusy = true;
  if (!PNS.active) {   // первый удар серии — сначала ставка
    const bet = betVal("pn-amt");
    if (bet > ME.stars) { pnBusy = false; return toast("Не хватает звёзд ⭐"); }
    pnUI();
    try { const r = await post("penalty/start", { bet, mode: pnMode }); setStars(r.stars); afterLevelUp(r.levelup); PNS = { ...PNS, ...r }; pnSeries = []; }
    catch (e) { pnBusy = false; pnUI(); return; }
    if (!$("#pn-stage")) { pnBusy = false; return; }
    pnPaint();
  }
  pnUI();
  const st = $("#pn-stage"), ball = $("#pn-ball"), kp = $("#pn-keeper");
  st.querySelectorAll(".ar-banner").forEach(b => b.remove());
  st.querySelectorAll(".pn-z").forEach(e => e.classList.toggle("aim", +e.dataset.z === z));
  kp.classList.add("set"); H.imp("light");
  let r;
  try { [r] = await Promise.all([post("penalty/kick", { zone: z }), sleep(240)]); } catch (e) { pnBusy = false; kp.classList.remove("set"); pnUI(); return; }
  if (!$("#pn-stage")) { pnBusy = false; return; }
  kp.classList.remove("set");
  // удар: мяч дугой в зону, вратарь прыгает одновременно
  const b0 = ball.getBoundingClientRect(), s = st.getBoundingClientRect(), [tx, ty] = pnZonePt(z);
  const bx = b0.left - s.left + b0.width / 2, by = b0.top - s.top + b0.height / 2, dx = tx - bx, dy = ty - by, curl = (Math.random() - .5) * 40;
  SND.kick(); H.imp("medium");
  setTimeout(() => $("#pn-stage") && pnDive(r.dive), 70);
  await ball.animate([{ transform: "translate(-50%,-50%) scale(1) rotate(0)" },
    { transform: `translate(calc(-50% + ${dx * .5 + curl}px),calc(-50% + ${dy * .62 - 26}px)) scale(.68) rotate(320deg)`, offset: .5 },
    { transform: `translate(calc(-50% + ${dx}px),calc(-50% + ${dy}px)) scale(.44) rotate(620deg)` }], { duration: 430, easing: "cubic-bezier(.25,.6,.35,1)", fill: "forwards" }).finished;
  if (!$("#pn-stage")) { pnBusy = false; return; }
  // показать зоны, которые закрывал вратарь
  st.querySelectorAll(".pn-z").forEach(e => e.classList.toggle("cov", r.cover.includes(+e.dataset.z)));
  if (r.goal) {
    pnSeries.push(1);
    SND.net(); SND.crowd(r.step >= 5 || r.auto); H.imp("heavy");
    const bulge = document.createElement("i"); bulge.className = "pn-bulge"; bulge.style.cssText = `left:${tx}px;top:${ty}px`; st.appendChild(bulge); setTimeout(() => bulge.remove(), 900);
    arSparks(st, tx, ty, 18, ["#c6ff3d", "#fff", "#ffd76a"], 90);
    $("#pn-crowd").classList.remove("roar"); void $("#pn-crowd").offsetWidth; $("#pn-crowd").classList.add("roar");
    pnFlashes(st);
    const gt = $("#pn-gt"); gt.classList.remove("on"); void gt.offsetWidth; gt.classList.add("on");
    if (r.pay != null) { await sleep(500); return pnDone(r); }
    PNS = { ...PNS, ...r };
    pnPaint(); arBump($("#pn-x"));
    await sleep(750);
  } else {
    pnSeries.push(0);
    SND.save(); H.err(); arShake(st);
    await ball.animate([{ transform: `translate(calc(-50% + ${dx}px),calc(-50% + ${dy}px)) scale(.44) rotate(620deg)`, opacity: 1 },
      { transform: `translate(calc(-50% + ${dx + (tx > s.width / 2 ? -1 : 1) * 80}px),calc(-50% + ${dy + 110}px)) scale(.6) rotate(200deg)`, opacity: 0 }],
      { duration: 520, easing: "cubic-bezier(.2,.7,.4,1)", fill: "forwards" }).finished;
    if (!$("#pn-stage")) { pnBusy = false; return; }
    const x = $("#pn-x"); x.textContent = "СЕЙВ"; x.className = "ar-x bad"; arBump(x);
    setStars(r.stars);
    PNS = { ...PNS, active: false };
    $("#pn-kicks").innerHTML = Array.from({ length: PNS.kicks }, (_, i) => `<i class="${pnSeries[i] === 1 ? "g" : pnSeries[i] === 0 ? "x" : ""}"></i>`).join("");
    arBanner(st, "lose", `Вратарь взял ${pnSeries.length}-й удар`, `−⭐ ${fmt(r.bet)}`);
    await sleep(1700);
    if (!$("#pn-stage")) { pnBusy = false; return; }
    PNS = await api("penalty"); pnSeries = [];
  }
  pnReset();
  pnBusy = false; pnPaint();
}
// вспышки фотоаппаратов на трибуне
function pnFlashes(st) {
  const c = $("#pn-crowd"); if (!c) return;
  for (let i = 0; i < 7; i++) {
    const f = document.createElement("i"); f.className = "pn-flash";
    f.style.cssText = `left:${5 + Math.random() * 90}%;top:${15 + Math.random() * 60}%;animation-delay:${Math.random() * .5}s`;
    c.appendChild(f); setTimeout(() => f.remove(), 1200);
  }
}
// вратарь на место, мяч — на точку
function pnReset() {
  const ball = $("#pn-ball"), kp = $("#pn-keeper"); if (!ball) return;
  ball.getAnimations().forEach(a => a.cancel());
  ball.classList.remove("back"); void ball.offsetWidth; ball.classList.add("back");
  kp.classList.remove("dive"); kp.style.transform = "";
  $("#pn-stage").querySelectorAll(".pn-z").forEach(e => e.classList.remove("cov", "aim"));
}
async function pnCash() {
  if (pnBusy || !PNS.active || !PNS.step) return;
  pnBusy = true; pnUI();
  try { await pnDone(await post("penalty/cashout")); } catch (e) { pnBusy = false; pnUI(); }
}
async function pnDone(r) {
  setStars(r.stars); H.ok();
  PNS = { ...PNS, ...r, active: false };
  const st = $("#pn-stage"); if (!st) { pnBusy = false; return; }
  const x = $("#pn-x"); x.textContent = arX(r.mult); x.className = "ar-x good"; arBump(x);
  arBanner(st, "win", r.auto ? `Все ${PNS.kicks} в сетке!` : `Забил ${r.step} подряд`, `+⭐ ${fmt(r.pay)}`, arX(r.mult));
  coinShower(st, Math.min(70, 12 + r.mult * 4));
  if (r.mult >= 5) await bigWin(r.pay, r.mult);
  await sleep(1600);
  if (!$("#pn-stage")) { pnBusy = false; return; }
  PNS = await api("penalty"); pnSeries = [];
  pnReset(); pnBusy = false; pnPaint();
}
Object.assign(ACT, {
  "pn-mode": el => { if (PNS && PNS.active) return; pnMode = el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); if (PNS) pnPaint(); },
  "pn-kick": el => pnKick(el.dataset.z === "r" ? -1 : +el.dataset.z),
  "pn-cash": () => pnCash(),
});

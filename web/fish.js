"use strict";
// ============================================================
//  «Рыбалка» — заброс → поклёвка → вываживание. Множитель растёт, пока не порвётся леска; вытащи вовремя.
//  Время и точку обрыва знает только сервер; клиент рисует и раз в ~0,4 с спрашивает, не сорвалась ли.
// ============================================================
GAMES.push({ id: "fish", t: "Рыбалка", s: "Подсеки и тяни, пока леска держит — не жадничай", imgUrl: "", k: ["#2ec5ff", "#06182e"], chips: ["новинка", "до x1000"] });
GAMES[GAMES.length - 1].imgUrl = "data:image/svg+xml," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs>
  <linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b1f5a"/><stop offset=".55" stop-color="#ff7a59"/><stop offset=".56" stop-color="#0d4a6e"/><stop offset="1" stop-color="#051a2c"/></linearGradient></defs>
  <rect x="4" y="4" width="112" height="112" rx="26" fill="url(#s)"/><circle cx="60" cy="62" r="14" fill="#ffd2a0"/><rect x="4" y="62" width="112" height="54" fill="#0b3d5c" opacity=".92"/>
  <path d="M30 62h60" stroke="#ffd2a0" stroke-width="3" opacity=".6"/><path d="M40 72h40M48 82h24" stroke="#ffd2a0" stroke-width="2" opacity=".35"/>
  <path d="M8 116 L84 30" stroke="#2a1a10" stroke-width="5" stroke-linecap="round"/><path d="M84 30 Q96 60 92 84" stroke="#e8eef8" stroke-width="1.2" fill="none"/>
  <ellipse cx="92" cy="88" rx="5" ry="7" fill="#ff3b4e"/><path d="M87 88h10" stroke="#fff" stroke-width="3"/></svg>`);
WIDE_GAMES.add("fish");
GAME_OPEN.fish = () => openFish();
AR_NEW.push("fish");
GAME_NAMES.fish = ["fish", "Рыбалка"];

// удочка: шарнир внизу слева; кончик двигаем сами (изгиб рисуем кривой)
let FSH = null, fsPhase = "idle", fsBiteAt = 0, fsRaf = 0, fsPolling = false, fsAuto = false, fsBusy = false, fsLastPoll = 0, fsBob = { x: 0, y: 0 };
async function openFish() {
  fsStop();
  const el = openSheet(`<div class="ghead">${gpfBtn("fish")}<img src="${GAMES.find(g => g.id === "fish").imgUrl}" alt=""><div><h2>Рыбалка</h2><span>Подсеки и вытащи, пока леска держит</span></div></div>
    <div class="ar-stage fs-stage" id="fs-stage">
      <div class="fs-sky"><i class="fs-sun"></i></div><div class="fs-mnt b"></div><div class="fs-mnt f"></div><div class="fs-pines"></div>
      <div class="fs-water"><i class="fs-glit"></i><i class="fs-wave"></i></div>
      <div class="fs-fish" id="fs-fish"></div>
      <svg class="fs-rig" id="fs-rig"><path class="fs-rod" id="fs-rod"/><path class="fs-rodh" id="fs-rodh"/><path class="fs-line" id="fs-line"/><circle class="fs-reel" id="fs-reel" r="7"/></svg>
      <div class="fs-bob" id="fs-bob"><i></i></div>
      <div class="ar-hud"><div class="ar-x dim" id="fs-x">x1,00</div><div class="ar-sub" id="fs-sub"></div></div>
      <div class="fs-tens" id="fs-tens"><span>Натяжение</span><div><i id="fs-tbar"></i></div></div>
    </div>
    <div class="betp">
      <div id="fs-bet">${betHTML("fs-amt")}
        <div class="auto"><button class="sw${fsAuto ? " on" : ""}" id="fs-sw" data-act="fs-auto"></button><span style="flex:1">Автовывод</span>
          <label class="autof"><input id="fs-auto" inputmode="decimal" value="2.00"><span>x</span></label></div></div>
      <button class="btn cta gold" id="fs-btn" data-act="fs-btn">Забросить</button>
    </div>
    <details class="rules" style="margin-top:12px"><summary>${ic("award")}Как играть</summary><div id="fs-rules"></div></details>`, "fs-s");
  el._onClose = () => fsStop();
  fsPhase = "idle";
  requestAnimationFrame(() => { fsLayout(); fsLoop(); });
  FSH = await api("fish").catch(() => null);
  if (!FSH || !$("#fs-stage")) return;
  $("#fs-rules").innerHTML = `Ставишь и забрасываешь удочку. После поклёвки рыба тянет — множитель растёт, а леска может порваться в любой момент.
    Жми «Вытащить», чтобы забрать ставку × множитель, или включи автовывод. Чем дольше тянешь, тем выше риск: дотянуть до x2 удаётся примерно в ${Math.round(FSH.rtp / 2)}% забросов, до x10 — в ${Math.round(FSH.rtp / 10)}%. Возврат игроку — ${String(FSH.rtp).replace(".", ",")}%.`;
  if (FSH.active) fsResume(FSH);
  else if (FSH.lost || FSH.won) fsShowEnd(FSH, true);
  fsUI();
}
function fsStop() { cancelAnimationFrame(fsRaf); fsRaf = 0; fsBusy = false; fsPolling = false; }
// геометрия сцены: шарнир удочки, точка поплавка на воде
const fsGeo = () => { const st = $("#fs-stage"); return st ? { W: st.clientWidth, H: st.clientHeight, bx: st.clientWidth * .66, by: st.clientHeight * .7 } : null; };
function fsLayout() { const g = fsGeo(); if (!g) return; $("#fs-rig").setAttribute("viewBox", `0 0 ${g.W} ${g.H}`); }
const fsX = () => Math.exp(FSH.k * Math.max(0, (performance.now() - fsBiteAt) / 1000));
// кадр: удочка (изгиб от натяжения), леска, поплавок, множитель, натяжение
function fsLoop() {
  const g = fsGeo(); if (!g) return fsStop();
  const now = performance.now(), t = now / 1000;
  let tension = 0, x = 1;
  if (fsPhase === "reel" && FSH) { x = fsX(); tension = Math.min(1, Math.log(x) / Math.log(12)); }
  // удочка: из угла вверх-вправо; кончик клонится к воде по натяжению и дрожит
  const ax = 18, ay = g.H + 4, len = Math.min(g.W * .78, 330), shake = fsPhase === "reel" ? Math.sin(t * 31) * (1.5 + tension * 4) : 0;
  const ang = (fsPhase === "cast" ? -78 : -54) + tension * 26 + (fsPhase === "wait" ? Math.sin(t * 1.3) * 1.2 : 0);
  const bend = (fsPhase === "reel" ? .18 + tension * .32 : .06) * len;
  const rad = ang * Math.PI / 180, tx = ax + Math.cos(rad) * len, ty = ay + Math.sin(rad) * len + bend + shake;
  const cx = ax + Math.cos(rad) * len * .55, cy = ay + Math.sin(rad) * len * .55;
  $("#fs-rod").setAttribute("d", `M${ax} ${ay} Q${cx} ${cy} ${tx} ${ty}`);
  $("#fs-rodh").setAttribute("d", `M${ax} ${ay} L${ax + Math.cos(rad) * 70} ${ay + Math.sin(rad) * 70}`);
  const rl = $("#fs-reel"); rl.setAttribute("cx", ax + Math.cos(rad) * 48 + 7); rl.setAttribute("cy", ay + Math.sin(rad) * 48 + 4);
  // поплавок
  let bx = g.bx, by = g.by;
  if (fsPhase === "idle") { bx = tx; by = ty + 46; }
  if (fsPhase === "end-lost") by += Math.sin(t * 2) * 2;
  if (fsPhase === "wait") { by += Math.sin(t * 2.6) * 2.2 + (Math.random() < .006 ? 4 : 0); }
  if (fsPhase === "reel") { bx += Math.sin(t * 2.3) * (16 + tension * 26) + Math.sin(t * 7.1) * 4; by += 8 + Math.sin(t * 9) * 2 + tension * 4; bx -= tension * g.W * .12; }
  if (fsPhase === "flying") { bx = fsBob.x; by = fsBob.y; }
  if (fsPhase === "drift") { fsBob.x += .25; bx = fsBob.x; by = g.by + Math.sin(t * 2) * 2; }
  const bob = $("#fs-bob"); bob.style.transform = `translate(${bx}px,${by}px)`;
  bob.classList.toggle("under", fsPhase === "reel");
  // леска: провисает в ожидании, натянута при вываживании
  const sag = fsPhase === "reel" ? 2 : fsPhase === "idle" ? 0 : 26;
  $("#fs-line").setAttribute("d", fsPhase === "end-lost"
    ? `M${tx} ${ty} q ${-6} 30 ${-2} 60`
    : `M${tx} ${ty} Q${(tx + bx) / 2} ${Math.max(ty, by) + sag} ${bx} ${by - 4}`);
  // рыба под водой
  const f = $("#fs-fish"); f.classList.toggle("on", fsPhase === "reel");
  if (fsPhase === "reel") f.style.transform = `translate(${bx - 30 + Math.sin(t * 3) * 10}px,${by + 18}px) scaleX(${Math.cos(t * 2.3) > 0 ? 1 : -1})`;
  if (fsPhase === "reel") {
    const xe = $("#fs-x"); xe.textContent = arX(Math.floor(x * 100) / 100);
    $("#fs-tbar").style.width = (92 - tension * 92) + "%"; $("#fs-tens").classList.toggle("hot", tension > .55);
    if (FSH.bet) { const b = $("#fs-btn"); if (b) b.innerHTML = `Вытащить ⭐ ${short(FSH.bet * x)}`, starify(b); }
    SND.reel();
    if (fsAuto && FSH.auto && x >= FSH.auto && now - fsLastPoll > 150) fsCheck();
    else if (now - fsLastPoll > 420) fsCheck();
  }
  if (fsPhase === "wait" && now >= fsBiteAt) fsBite();
  fsRaf = requestAnimationFrame(fsLoop);
}
function fsUI() {
  const b = $("#fs-btn"); if (!b) return;
  const on = fsPhase === "wait" || fsPhase === "reel" || fsPhase === "cast";
  $("#fs-bet").style.display = on ? "none" : "";
  b.className = "btn cta " + (fsPhase === "reel" ? "green" : fsPhase === "wait" || fsPhase === "cast" ? "ar-dark" : "gold");
  b.disabled = fsPhase === "wait" || fsPhase === "cast" || fsBusy;
  if (fsPhase === "wait" || fsPhase === "cast") b.textContent = "Ждём поклёвку…";
  else if (fsPhase !== "reel") b.textContent = "Забросить";
  const sub = $("#fs-sub"); if (!sub) return;
  sub.innerHTML = fsPhase === "wait" || fsPhase === "cast" ? `<span class="ar-pill">${ic("hourglass")}Ждём поклёвку…</span>`
    : fsPhase === "reel" ? `<span class="ar-pill">${ic("fish")}Тянем!</span>${FSH.auto ? `<span class="ar-pill">Автовывод <b>${arX(FSH.auto)}</b></span>` : ""}`
    : `<span class="ar-pill">${ic("fish")}Ставка ⭐ ${short(betVal("fs-amt") || 0)}</span>`;
  starify(sub);
  $("#fs-tens").classList.toggle("on", fsPhase === "reel");
}
async function fsCast() {
  if (fsBusy || !FSH) return;
  const bet = betVal("fs-amt");
  if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
  const auto = fsAuto ? Math.max(1.01, parseFloat(String($("#fs-auto").value).replace(",", ".")) || 2) : null;
  fsBusy = true; fsUI();
  let r;
  try { r = await post("fish/cast", { bet, auto }); } catch (e) { fsBusy = false; fsUI(); return; }
  fsBusy = false;
  setStars(r.stars); afterLevelUp(r.levelup);
  if (!$("#fs-stage")) return;
  FSH = { ...FSH, ...r };
  $("#fs-stage").querySelectorAll(".ar-banner").forEach(b => b.remove());
  const x = $("#fs-x"); x.textContent = "x1,00"; x.className = "ar-x dim";
  // заброс: удочка назад, поплавок летит дугой и шлёпается в воду
  fsPhase = "cast"; fsUI(); SND.cast(); H.imp("medium");
  const g = fsGeo(), rod = $("#fs-rod").getPointAtLength ? $("#fs-rod") : null;
  const p0 = rod ? rod.getPointAtLength(rod.getTotalLength()) : { x: 40, y: 80 };
  await sleep(160);
  fsPhase = "flying";
  const T = 620, s0 = performance.now();
  await new Promise(res => {
    const step = now => {
      const k = Math.min(1, (now - s0) / T);
      fsBob.x = p0.x + (g.bx - p0.x) * k; fsBob.y = p0.y + (g.by - p0.y) * k - Math.sin(k * Math.PI) * 90;
      if (k < 1 && $("#fs-stage")) requestAnimationFrame(step); else res();
    };
    requestAnimationFrame(step);
  });
  if (!$("#fs-stage")) return;
  fsSplash(g.bx, g.by, false); SND.splash(false);
  fsBiteAt = performance.now() + Math.max(.3, r.bite) * 1000 - T - 160;
  fsPhase = "wait"; fsUI();
}
function fsResume(r) {
  fsBiteAt = performance.now() + r.bite * 1000;
  fsPhase = r.bite > 0 ? "wait" : "reel";
  fsUI();
}
function fsBite() {
  const g = fsGeo(); if (!g) return;
  fsPhase = "reel"; fsLastPoll = performance.now();
  fsSplash(g.bx, g.by, true); SND.bite(); H.imp("heavy");
  const x = $("#fs-x"); x.className = "ar-x"; arBump(x);
  arBanner($("#fs-stage"), "", "Поклёвка", "Клюёт!", "Тяни — и вытаскивай вовремя");
  fsUI();
}
async function fsCheck() {
  fsLastPoll = performance.now();
  if (fsPolling || fsBusy) return;
  fsPolling = true;
  try {
    const r = await api("fish");
    if (r.lost || r.won) fsShowEnd(r);
    else if (r.active && fsPhase === "reel") fsBiteAt = performance.now() - r.elapsed * 1000;   // подтягиваем часы к серверу
  } catch (e) {}
  fsPolling = false;
}
async function fsReel() {
  if (fsPhase !== "reel" || fsBusy) return;
  fsBusy = true; H.imp("medium");
  try { const r = await post("fish/reel"); fsBusy = false; fsShowEnd(r); } catch (e) { fsBusy = false; fsCheck(); }
}
function fsShowEnd(r, silent) {
  const st = $("#fs-stage"); if (!st) return;
  if (r.stars != null) setStars(r.stars);
  const g = fsGeo(), x = $("#fs-x");
  $("#fs-fish").classList.remove("on");
  if (r.won) {
    fsPhase = "idle";
    x.textContent = arX(r.mult); x.className = "ar-x good"; if (!silent) arBump(x);
    if (!silent) {
      H.ok(); SND.splash(true); fsSplash(g.bx - 20, g.by, true);
      const c = document.createElement("div"); c.className = "fs-catch"; c.style.cssText = `left:${g.bx - 40}px;top:${g.by - 40}px`;
      c.innerHTML = `<div class="fs-cg">${giftHTML(r.gift, { lite: true, plain: true })}</div>`;
      st.appendChild(c); setTimeout(() => c.remove(), 2600);
      coinShower(st, Math.min(70, 12 + r.mult * 4));
      if (r.mult >= 5) bigWin(r.pay, r.mult);
    }
    arBanner(st, "win", `Улов · ${esc(r.gift ? r.gift.col : "")}`, `+⭐ ${fmt(r.pay)}`, arX(r.mult));
  } else {
    fsPhase = "end-lost";
    x.textContent = arX(r.bust); x.className = "ar-x bad"; if (!silent) arBump(x);
    if (!silent) { H.err(); SND.snap(); arShake(st); }
    arBanner(st, "lose", `Леска порвалась на ${arX(r.bust)}`, `−⭐ ${fmt(r.bet)}`);
    setTimeout(() => { if (fsPhase === "end-lost") { fsBob.x = g.bx; fsPhase = "drift"; } }, 500);
    setTimeout(() => { if (fsPhase === "drift") { fsPhase = "idle"; fsUI(); } }, 2600);
  }
  fsUI();
}
function fsSplash(x, y, big) {
  const st = $("#fs-stage"); if (!st) return;
  for (let i = 0; i < (big ? 3 : 2); i++) { const r = document.createElement("i"); r.className = "fs-ring"; r.style.cssText = `left:${x}px;top:${y}px;animation-delay:${i * .18}s`; st.appendChild(r); setTimeout(() => r.remove(), 1600); }
  if (!window.LITE) for (let i = 0; i < (big ? 18 : 8); i++) {
    const d = document.createElement("i"), a = -Math.PI / 2 + (Math.random() - .5) * 2.2, v = (big ? 60 : 30) + Math.random() * (big ? 70 : 30);
    d.className = "fs-drop"; d.style.cssText = `left:${x}px;top:${y}px;--dx:${Math.cos(a) * v}px;--dy:${Math.sin(a) * v}px`;
    st.appendChild(d); setTimeout(() => d.remove(), 900);
  }
}
Object.assign(ACT, {
  "fs-btn": () => fsPhase === "reel" ? fsReel() : fsCast(),
  "fs-auto": el => { fsAuto = !fsAuto; el.classList.toggle("on", fsAuto); H.sel(); },
});

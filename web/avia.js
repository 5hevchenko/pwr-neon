"use strict";
// ============================================================
//  «Самолётик» — самолёт летит по облакам: «+0,1…+1», «×2–×5», ракеты делят пополам; в конце посадка на корабль.
//  Графика — системные эмодзи (выглядят одинаково аккуратно на всех телефонах) + CSS-облака и небо.
// ============================================================
// плоская векторная графика: самолёт (смотрит вправо), авианосец, ракета
const AV_PLANE = `<svg viewBox="0 0 100 50" class="avpl" xmlns="http://www.w3.org/2000/svg">
  <path d="M46 22L39 11h8l13 11z" fill="#c8263a"/>
  <path d="M14 28L3 31.5 18 33z" fill="#d9dfeb"/>
  <path d="M16 24L8 6h11l14 15z" fill="#ff4757"/>
  <path d="M14 26c0-5 8-8 18-8h48c10 0 16 4 16 8s-6 8-16 8H32c-10 0-18-3-18-8z" fill="#f6f8fc"/>
  <path d="M15 28c3 4 9 6 17 6h48c8 0 13-2.5 15-6z" fill="#dfe5f0"/>
  <path d="M22 29.5h66" stroke="#ff4757" stroke-width="2.4" stroke-linecap="round"/>
  <path d="M78 20.2h8.5c3.5.6 6.5 2.6 7.8 5H79z" fill="#2b3a67"/><path d="M81 21.6h5" stroke="#8fb0ff" stroke-width="1.4" stroke-linecap="round"/>
  <g fill="#9fb3dc"><circle cx="48" cy="24.5" r="1.6"/><circle cx="54" cy="24.5" r="1.6"/><circle cx="60" cy="24.5" r="1.6"/><circle cx="66" cy="24.5" r="1.6"/><circle cx="72" cy="24.5" r="1.6"/></g>
  <path d="M44 29L30 47h12l22-18z" fill="#ff4757"/><path d="M44 29l-3 4h17l5-4z" fill="#c8263a" opacity=".55"/>
  <rect x="44" y="35" width="11" height="5" rx="2.5" fill="#b9c2d6"/></svg>`;
const AV_SHIP = `<svg viewBox="0 0 170 56" class="avshp" xmlns="http://www.w3.org/2000/svg">
  <path d="M4 22h162l-12 28H18z" fill="#3d4a6b"/><path d="M10 36h150l-3 6H13z" fill="#e84a5f" opacity=".9"/>
  <rect x="0" y="17" width="170" height="7" rx="2" fill="#5b6788"/>
  <path d="M8 20.5h120" stroke="#ffd23f" stroke-width="1.4" stroke-dasharray="9 7"/>
  <rect x="134" y="2" width="18" height="16" rx="2" fill="#4a5678"/><rect x="137" y="5" width="12" height="4" rx="1" fill="#9fdcff"/>
  <rect x="141" y="-3" width="3" height="6" fill="#4a5678"/></svg>`;
const AV_ROCKET = `<svg viewBox="0 0 48 20" class="avrk"><path d="M10 6h26c5 0 9 2 11 4-2 2-6 4-11 4H10z" fill="#eef1f7"/><path d="M36 6c5 0 9 2 11 4-2 2-6 4-11 4z" fill="#ff4757"/>
  <path d="M10 6L3 1h6l6 5zM10 14l-7 5h6l6-5z" fill="#8892a8"/><rect x="18" y="8.6" width="12" height="2.8" rx="1.4" fill="#c4cbe0"/></svg>`;
function avIcon() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3b5bdb"/><stop offset=".7" stop-color="#a16ae8"/><stop offset="1" stop-color="#ff9a5a"/></linearGradient></defs>
    <rect width="128" height="128" rx="30" fill="url(#g)"/><circle cx="96" cy="30" r="12" fill="#fff3c8"/>
    <g transform="translate(14 44) scale(1)">${AV_PLANE.replace(/<svg[^>]*>|<\/svg>/g, "")}</g></svg>`;
  return "data:image/svg+xml," + encodeURIComponent(svg);
}
GAMES.push({ id: "avia", t: "Самолётик", s: "Собирай иксы на облаках и посади самолёт на корабль", imgUrl: avIcon(), k: ["#ff9a5a", "#1b2a6b"], chips: ["новинка", "до x250"] });
WIDE_GAMES.add("avia");
GAME_OPEN.avia = () => openAvia();
GAME_SECTIONS[0][2].splice(1, 0, "avia");
GAME_NAMES.avia = ["rocket", "Самолётик"];

let avBusy = false, avFast = false;
const AV_STEP = 120, AV_X0 = 170, AV_H = 300;   // X0 — место для стартового авианосца слева
const avLabel = s => s.t === "add" ? "+" + String(s.v).replace(".", ",") : s.t === "mul" ? "×" + s.v : AV_ROCKET;
const avK = k => "×" + (k >= 100 ? Math.round(k) : k.toFixed(2).replace(".", ","));
function openAvia() {
  avBusy = false;
  openSheet(`<div class="ghead">${gpfBtn("avia")}<img src="${GAMES.find(g => g.id === "avia").imgUrl}" alt=""><div><h2>Самолётик</h2><span>Собирай иксы и посади самолёт на корабль</span></div></div>
    <div class="avsc" id="av-sc">
      <div class="avstars"></div><div class="avmoon"></div><div class="avfar"></div>
      <div class="avspeed" id="av-spd"></div><div class="avworld" id="av-w"></div>
      <div class="avsea"><i></i></div>
      <div class="avhud" id="av-hud"><b id="av-k">×1,00</b><span id="av-win">выигрыш при посадке</span></div>
    </div>
    <div class="wres" id="av-res">Делай ставку и взлетай</div>
    <div class="betp">${betHTML("av-amt")}
      <div class="dgbtns"><button class="btn cta gold" id="av-btn" data-act="av-go">Взлететь</button><button class="ufast${avFast ? " on" : ""}" data-act="av-fast">${ic("trend")}Быстро</button></div></div>
    <details class="rules" style="margin-top:12px"><summary>${ic("award")}Как играть</summary><div>Самолёт пролетает 6–12 облаков. На облаках — бонусы к счётчику:
      <b>+0,1 … +1</b> ставки и множители <b>×2 … ×5</b>. Облако с <b>ракетой</b> делит счётчик пополам. В конце самолёт заходит на посадку:
      сел на корабль — получаешь ставку × счётчик (до ×250), промахнулся — всё сгорает. Посадка удаётся примерно в каждом третьем полёте.</div></details>`, "av-s");
  avScene(null);
  $("#av-amt").addEventListener("input", () => avHud(1));
  avHud(1);
}
function avScene(path) {
  const w = $("#av-w"); if (!w) return;
  const n = path ? path.length : 0;
  // облака «ступеньками»: три высоты, чтобы полёт выглядел как прыжки
  const ys = path ? path.map((_, i) => [70, 120, 95, 150, 80, 135][i % 6] + (Math.random() * 16 - 8)) : [];
  w.style.width = AV_X0 + (n + 4) * AV_STEP + 300 + "px";
  w.innerHTML = (path ? path.map((s, i) => `<div class="avc" style="left:${AV_X0 + (i + 1) * AV_STEP - 55}px;top:${ys[i]}px" id="av-c${i}">
      <i class="puff"></i><b>?</b></div>`).join("") : "") +
    `<div class="avship start" style="left:${AV_X0 - 120}px">${AV_SHIP}<i class="wake"></i></div>
     <div class="avship" id="av-ship">${AV_SHIP}<i class="wake"></i></div>
     <div class="avplane" id="av-p"><i class="trail"></i><span>${AV_PLANE}</span></div>`;
  w._ys = ys;
  $("#av-ship").style.left = AV_X0 + (n + 2) * AV_STEP + "px";
  avMove(AV_X0 - 70, 207, 0, true);   // стоит на палубе стартового авианосца
}
function avMove(x, y, tilt, instant, dur) {
  const p = $("#av-p"), w = $("#av-w"), sc = $("#av-sc"); if (!p) return Promise.resolve();
  const d = instant ? 0 : (dur || .6) * (avFast ? .5 : 1);
  p.style.transition = `transform ${d}s cubic-bezier(.45,.05,.35,1)`;
  p.style.transform = `translate(${x}px,${y}px)`;
  p.style.setProperty("--tilt", tilt + "deg");
  w.style.transition = `transform ${d}s cubic-bezier(.45,.05,.35,1)`;
  w.style.transform = `translateX(${-Math.max(0, x - sc.clientWidth * .32)}px)`;
  return sleep(d * 1000);
}
function avHud(k, cls) {
  const hud = $("#av-hud"); if (!hud) return;
  $("#av-k").textContent = avK(k);
  $("#av-win").innerHTML = cls === "burn" ? "сгорело" : `при посадке ⭐ ${fmt(betVal("av-amt") * k)}`;
  hud.className = "avhud " + (cls || "");
  if (cls && cls !== "burn") { void hud.offsetWidth; hud.classList.add("pop"); }
  starify($("#av-win"));
}
function avFloat(text, cls) {   // всплывающая цифра над самолётом
  const p = $("#av-p"); if (!p) return;
  const f = document.createElement("b"); f.className = "avfloat " + cls; f.textContent = text;
  p.appendChild(f); setTimeout(() => f.remove(), 900);
}
async function avGo() {
  if (avBusy) return;
  const bet = betVal("av-amt");
  if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
  avBusy = true; $("#av-btn").disabled = true;
  setStars(ME.stars - bet);
  let r;
  try { r = await post("avia", { bet }); } catch (e) { avBusy = false; const b = $("#av-btn"); if (b) b.disabled = false; loadMe(); return; }
  try {   // окно закрыли посреди полёта — элементов уже нет; раунд всё равно завершаем, иначе avBusy залипнет
  $("#av-res").className = "wres"; $("#av-res").textContent = "Полёт…";
  avScene(r.path); avHud(1);
  const ys = $("#av-w")._ys, n = r.path.length;
  const shipX = AV_X0 + (n + 2) * AV_STEP;
  // разбег по палубе и взлёт
  await avMove(AV_X0 - 10, 205, -4);
  $("#av-p").classList.add("fly"); $("#av-sc").classList.add("flying");
  let prevY = 205;
  for (let i = 0; i < n; i++) {
    if (!$("#av-w")) return avEnd(r, bet);
    const s = r.path[i], x = AV_X0 + (i + 1) * AV_STEP - 43, y = ys[i] - 26;
    await avMove(x, y, Math.max(-18, Math.min(18, (y - prevY) / 3)));
    prevY = y;
    // облако раскрывается только при касании — заранее не видно ни множителей, ни ракет
    const c = $("#av-c" + i); if (c) { c.classList.add("hit", s.t); c.querySelector("b").textContent = avLabel(s); }
    if (s.t === "rocket") {
      H.err(); avHud(s.k, "bad"); avFloat("÷2", "bad");
      const p = $("#av-p"); p.classList.add("boom"); setTimeout(() => p && p.classList.remove("boom"), 600);
    } else { H.imp(s.t === "mul" ? "medium" : "light"); avHud(s.k, s.t === "mul" ? "mul" : "good"); avFloat(avLabel(s), s.t); }
    await sleep(avFast ? 80 : 220);
  }
  if (!$("#av-w")) return avEnd(r, bet);
  $("#av-sc").classList.remove("flying");
  // заход на посадку
  // заход на посадку одинаковый при любом исходе — заранее не видно, сядет или нет
  await avMove(shipX - 150, 180, 8);
  if (r.landed) {
    await avMove(shipX + 16, 207, 0);
    $("#av-p").classList.remove("fly"); $("#av-p").classList.add("landed"); H.ok();
  } else {
    // промах — «не дотянул»: задирает нос, теряет скорость и падает почти вертикально, с зазором до кормы.
    // (падение носом на корму выглядело как «чуть не сел», а перелёт над палубой — как издёвка; самолёт 86 px)
    await avMove(shipX - 143, 192, -12, false, .5);
    await avMove(shipX - 139, 212, 18, false, .45);
    await avMove(shipX - 136, 262, 64, false, .7);
    const sc = $("#av-sc"), pr = $("#av-p").getBoundingClientRect(), sr = sc.getBoundingClientRect();
    sc.style.setProperty("--sx", pr.left - sr.left + pr.width / 2 + "px"); sc.classList.add("splash");
    $("#av-p").classList.add("sunk"); H.err();
  }
  avEnd(r, bet);
  } catch (e) { if (avBusy) avEnd(r, bet); }
}
async function avEnd(r, bet) {
  avBusy = false;
  const btn = $("#av-btn"); if (btn) btn.disabled = false;
  setStars(r.stars);
  const res = $("#av-res");
  if (res) {
    if (r.landed) { res.className = "wres win"; res.textContent = `Посадка! ${avK(r.k)} · +⭐ ${fmt(r.pay)}`; avHud(r.k, "mul"); coinShower($("#av-sc"), Math.min(70, 10 + r.k * 4)); }
    else { res.className = "wres lose"; res.textContent = `Мимо корабля — ${avK(r.k)} сгорели`; avHud(r.k, "burn"); }
  }
  setTimeout(() => { const sc = $("#av-sc"); if (sc) sc.classList.remove("splash"); }, 1000);
  if (r.landed && r.k >= 5) await bigWin(r.pay, r.k);
  afterLevelUp(r.levelup);
}
Object.assign(ACT, {
  "av-go": () => avGo(),
  "av-fast": el => { avFast = !avFast; el.classList.toggle("on", avFast); H.sel(); },
});

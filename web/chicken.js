"use strict";
// ============================================================
//  «Курица» — перебеги дорогу: каждая полоса — шанс попасть под машину, множитель растёт, забрать можно в любой момент
// ============================================================
GAMES.push({ id: "chicken", t: "Курица", s: "Перебеги дорогу и не попади под машину", imgUrl: "", k: ["#ffcf3d", "#3a2a00"], chips: ["новинка", "до x10 000"] });
WIDE_GAMES.add("chicken");
GAME_OPEN.chicken = () => openChicken();
GAME_SECTIONS[0][2].splice(1, 0, "chicken");
GAME_NAMES.chicken = ["flame", "Курица"];

const CK_MODES = [["easy", "Лёгкий"], ["mid", "Средний"], ["hard", "Сложный"], ["hell", "Хардкор"]];
const CK_CARS = ["#ff3b4e", "#2f8cff", "#ffc21a", "#20c46b", "#8f5cff", "#ff7a1a", "#e9ecf2", "#1fc8e0"];
// курица и машины — инлайн SVG (свои, без внешних картинок)
const CK_HEN = `<svg viewBox="0 0 80 80" class="hen"><defs>
  <radialGradient id="ckb" cx=".38" cy=".3" r=".8"><stop offset="0" stop-color="#fff"/><stop offset=".7" stop-color="#f1efe9"/><stop offset="1" stop-color="#d6d2c8"/></radialGradient>
  <linearGradient id="ckc" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff5a5a"/><stop offset="1" stop-color="#d81f3a"/></linearGradient>
  <linearGradient id="ckk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffd23f"/><stop offset="1" stop-color="#ff9500"/></linearGradient></defs>
  <ellipse cx="40" cy="73" rx="17" ry="4" fill="rgba(0,0,0,.35)"/>
  <path d="M33 60l-3 11h-5M47 60l3 11h5" stroke="url(#ckk)" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  <path d="M14 44c-6-1-9-9-4-13 2 4 6 5 9 4" fill="#e9e5dc"/>
  <ellipse cx="38" cy="47" rx="22" ry="17" fill="url(#ckb)"/>
  <path d="M24 46c5 7 15 8 22 2-4 9-17 11-22-2z" fill="#e2ddd2"/>
  <circle cx="49" cy="27" r="13" fill="url(#ckb)"/>
  <path d="M41 16c0-6 5-8 7-4 1-5 7-5 7 0 3-3 7 0 4 4l-17 2z" fill="url(#ckc)"/>
  <path d="M61 26l10 3.5-10 3.5z" fill="url(#ckk)"/><path d="M61 29.5h10" stroke="#e08600" stroke-width=".8"/>
  <path d="M59 34c3 3 2 8-2 8-1-3 0-6 2-8z" fill="url(#ckc)"/>
  <ellipse cx="54" cy="24" rx="3" ry="3.4" fill="#1b1b22"/><circle cx="55" cy="22.8" r="1.1" fill="#fff"/>
  <path d="M51 18.5q3-1.6 6 0" stroke="#1b1b22" stroke-width="1.2" fill="none" stroke-linecap="round"/></svg>`;
const CK_CAR = c => `<svg viewBox="0 0 44 80" class="car"><defs><linearGradient id="cg${c.slice(1)}" x1="0" x2="1"><stop offset="0" stop-color="${c}" stop-opacity=".75"/><stop offset=".5" stop-color="${c}"/><stop offset="1" stop-color="${c}" stop-opacity=".75"/></linearGradient></defs>
  <ellipse cx="22" cy="44" rx="20" ry="36" fill="rgba(0,0,0,.35)"/>
  <rect x="3" y="6" width="38" height="70" rx="12" fill="url(#cg${c.slice(1)})"/>
  <rect x="3" y="6" width="38" height="70" rx="12" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="1.5"/>
  <path d="M9 22q13-6 26 0l-2 12H11z" fill="#1d2433"/><path d="M12 24q10-4 20 0" stroke="rgba(255,255,255,.35)" stroke-width="1.6" fill="none"/>
  <rect x="11" y="36" width="22" height="20" rx="5" fill="rgba(255,255,255,.12)"/>
  <path d="M11 58h22l2 9q-13 4-26 0z" fill="#1d2433"/>
  <rect x="6" y="70" width="9" height="4" rx="2" fill="#fff6c8"/><rect x="29" y="70" width="9" height="4" rx="2" fill="#fff6c8"/>
  <rect x="6" y="8" width="8" height="3" rx="1.5" fill="#ff4f5e"/><rect x="30" y="8" width="8" height="3" rx="1.5" fill="#ff4f5e"/>
  <rect x="1" y="26" width="3" height="7" rx="1.5" fill="#222"/><rect x="40" y="26" width="3" height="7" rx="1.5" fill="#222"/></svg>
  <i class="beam"></i>`;
GAMES[GAMES.length - 1].imgUrl = "data:image/svg+xml," + encodeURIComponent(CK_HEN.replace('class="hen"', 'xmlns="http://www.w3.org/2000/svg"'));

let CK = null, ckMode = "mid", ckBusy = false, ckCars = null;
async function openChicken() {
  ckBusy = false;
  openSheet(`<div class="ghead">${gpfBtn("chicken")}<img src="${GAMES.find(g => g.id === "chicken").imgUrl}" alt=""><div><h2>Курица</h2><span>Перебеги дорогу — каждая полоса умножает ставку</span></div></div>
    <div class="ckroad" id="ck-road"><div class="ckworld" id="ck-w"></div></div>
    <div class="wres" id="ck-res">Выбери сложность и ставку</div>
    <div class="betp">
      <div class="seg" id="ck-mode">${CK_MODES.map(([k, t]) => `<button data-act="ck-mode" data-v="${k}" class="${ckMode === k ? "on" : ""}">${t}</button>`).join("")}</div>
      <div id="ck-bet">${betHTML("ck-amt")}</div>
      <div class="ckbtns" id="ck-btns"></div>
    </div>
    <details class="rules" style="margin-top:12px"><summary>${ic("award")}Как играть</summary><div id="ck-rules"></div></details>`, "ck-s");
  CK = await api("chicken");
  if (CK.active) ckMode = CK.mode;
  $("#ck-rules").innerHTML = `Ставишь и ведёшь курицу через ${CK.lanes} полос. Риск попасть под машину растёт с каждой полосой: первые — почти безопасные, дальние — опасные (${CK_MODES.map(([k, t]) => `${t.toLowerCase()}: ${String(CK.riskFrom ? CK.riskFrom[k] : CK.risk[k]).replace(".", ",")}% → ${CK.riskTo ? CK.riskTo[k] : CK.risk[k]}%`).join(", ")}).
    Каждая пройденная полоса увеличивает множитель (на крышке люка). Забери выигрыш, когда захочешь, — или рискни дальше. Перешла всю дорогу — выплата автоматически.`;
  ckDraw(); ckUI();
  ckAmbient();
}
function ckTable() { return CK.active ? CK.table : CK.modes[ckMode]; }
function ckDraw(deadAt) {
  const w = $("#ck-w"); if (!w || !CK) return;   // CK ещё грузится — сложность могли переключить раньше
  const t = ckTable(), step = CK.active ? CK.step : 0;
  w.innerHTML = `<div class="cklane side start"><div class="ckgrass"></div><div class="ckhen" id="ck-hen">${CK_HEN}</div></div>` +
    t.map((m, i) => `<div class="cklane${i < step ? " done" : ""}${i === step && CK.active ? " next" : ""}${deadAt === i + 1 ? " dead" : ""}" data-i="${i + 1}">
      <div class="ckcars"></div><div class="ckbar"><i></i><i></i></div><div class="ckman"><span>x${m >= 100 ? short(m) : m.toFixed(2).replace(".", ",")}</span></div></div>`).join("") +
    `<div class="cklane side finish"><div class="ckflag"></div><b>ФИНИШ</b></div>`;
  ckPlaceHen(deadAt ? deadAt : step, !deadAt);
}
function ckPlaceHen(i, smooth = true) {
  const hen = $("#ck-hen"), w = $("#ck-w"), road = $("#ck-road"); if (!hen || !w) return;
  const lanes = w.children, lane = lanes[i]; if (!lane) return;
  hen.style.transition = smooth ? "transform .38s cubic-bezier(.3,1.3,.5,1)" : "none";
  if (smooth) { hen.classList.remove("hop"); void hen.offsetWidth; hen.classList.add("hop"); clearTimeout(hen._hop); hen._hop = setTimeout(() => hen.classList.remove("hop"), 420); }
  hen.style.transform = `translateX(${lane.offsetLeft + lane.offsetWidth / 2 - lanes[0].offsetLeft - lanes[0].offsetWidth / 2}px)`;
  const x = Math.max(0, lane.offsetLeft - road.clientWidth / 2 + lane.offsetWidth / 2);
  w.style.transform = `translateX(${-Math.min(x, w.scrollWidth - road.clientWidth)}px)`;
}
function ckUI() {
  if (!CK) return;
  const b = $("#ck-btns"); if (!b) return;
  const on = CK.active;
  $("#ck-bet").style.display = on ? "none" : "";
  $("#ck-mode").querySelectorAll("button").forEach(x => x.disabled = on);
  if (on) {
    b.innerHTML = `<button class="btn cta gold ar-two" data-act="ck-step" ${ckBusy ? "disabled" : ""}><b>Вперёд</b><small>до x${CK.next ? CK.next.toFixed(2).replace(".", ",") : "—"}</small></button>
      <button class="btn cta green ar-two" data-act="ck-cash" ${!CK.step || ckBusy ? "disabled" : ""}><b>Забрать</b><small>⭐ ${fmt(CK.bet * CK.mult)}</small></button>`;
    $("#ck-res").className = "wres"; $("#ck-res").textContent = CK.step ? `x${CK.mult.toFixed(2).replace(".", ",")} · ставка ⭐ ${fmt(CK.bet)}` : "Курица на старте — вперёд!";
  } else b.innerHTML = `<button class="btn cta gold" data-act="ck-start">Начать</button>`;
}
// машины проезжают по непройденным полосам для атмосферы
function ckAmbient() {
  clearInterval(ckCars);
  ckCars = setInterval(() => {
    const w = $("#ck-w"); if (!w) return clearInterval(ckCars);
    const lanes = [...w.querySelectorAll(".cklane:not(.side):not(.done):not(.next)")];
    if (!lanes.length || Math.random() < .35) return;
    ckCar(lanes[Math.random() * lanes.length | 0], .9 + Math.random() * .9);
  }, 450);
}
function ckCar(lane, dur, hit) {
  const box = lane.querySelector(".ckcars"); if (!box) return;
  const c = document.createElement("div");
  c.className = "ckcar" + (hit ? " hit" : ""); c.innerHTML = CK_CAR(CK_CARS[Math.random() * CK_CARS.length | 0]);
  c.style.animationDuration = dur + "s";
  box.appendChild(c); setTimeout(() => c.remove(), dur * 1000 + 50);
}
async function ckStart() {
  const bet = betVal("ck-amt");
  if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
  const r = await post("chicken/start", { bet, mode: ckMode });
  setStars(r.stars); H.imp("medium");
  CK = { ...CK, ...r }; ckDraw(); ckUI(); afterLevelUp(r.levelup);
}
async function ckStep() {
  if (ckBusy || !CK.active) return;
  ckBusy = true; ckUI();
  let r;
  try { r = await post("chicken/step"); } catch (e) { ckBusy = false; ckUI(); return; }
  try {   // окно закрыли во время анимации — не оставляем ckBusy навсегда
  const lanes = $("#ck-w").children;
  if (r.dead) {   // машина влетает в полосу, курицу сбивает
    ckPlaceHen(r.dead);
    await sleep(250);
    ckCar(lanes[r.dead], .45, true);
    await sleep(230);
    H.err(); $("#ck-hen").classList.add("splat"); lanes[r.dead].classList.add("dead");
    ckFeathers($("#ck-hen"));
    CK = { ...CK, active: false };
    $("#ck-res").className = "wres lose"; $("#ck-res").textContent = `Сбили на ${r.dead} полосе — −⭐ ${fmt(r.bet)}`;
    setStars(r.stars);
    await sleep(1100);
    ckBusy = false; if (!$("#ck-w")) return; CK = await api("chicken"); ckDraw(); ckUI(); $("#ck-res").className = "wres lose"; $("#ck-res").textContent = `Сбили на ${r.dead} полосе — −⭐ ${fmt(r.bet)}`;
    return;
  }
  H.imp("light");
  if (r.pay != null) return ckDone(r);
  CK = { ...CK, ...r };
  ckDraw(); ckBusy = false; ckUI();
  } catch (e) { ckBusy = false; if (r.dead || r.pay != null) CK = { ...CK, active: false }; }
}
async function ckCash() {
  if (ckBusy || !CK.active || !CK.step) return;
  ckBusy = true;
  try { ckDone(await post("chicken/cashout")); } catch (e) { ckBusy = false; ckUI(); }
}
async function ckDone(r) {
  setStars(r.stars); H.ok();
  CK = { ...CK, ...r, active: false }; ckBusy = false;
  if (!$("#ck-w")) return;
  ckPlaceHen(r.step);
  $("#ck-res").className = "wres win"; $("#ck-res").textContent = `x${r.mult.toFixed(2).replace(".", ",")} · +⭐ ${fmt(r.pay)}`;
  coinShower($("#ck-road"), Math.min(70, 10 + r.mult * 4));
  ckBusy = false;
  if (r.mult >= 5) await bigWin(r.pay, r.mult);
  if (!$("#ck-w")) return;
  CK = await api("chicken"); ckDraw(); ckUI();
  $("#ck-res").className = "wres win"; $("#ck-res").textContent = `x${r.mult.toFixed(2).replace(".", ",")} · +⭐ ${fmt(r.pay)}`;
}
function ckFeathers(el) {
  const r = el.getBoundingClientRect();
  for (let i = 0; i < 14; i++) {
    const f = document.createElement("i"); f.className = "ckfeather";
    f.style.left = r.left + r.width / 2 + "px"; f.style.top = r.top + r.height / 2 + "px";
    f.style.setProperty("--dx", (Math.random() - .5) * 160 + "px"); f.style.setProperty("--dy", (Math.random() - .8) * 140 + "px"); f.style.setProperty("--r", Math.random() * 720 + "deg");
    document.body.appendChild(f); setTimeout(() => f.remove(), 1300);
  }
}
Object.assign(ACT, {
  "ck-mode": el => { if (CK && CK.active) return; ckMode = el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); ckDraw(); },
  "ck-start": () => ckStart(),
  "ck-step": () => ckStep(),
  "ck-cash": () => ckCash(),
});

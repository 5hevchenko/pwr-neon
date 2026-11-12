"use strict";
// ============================================================
//  «Кран» — автомат с клешнёй: выбери подарок, опусти клешню, удержит — получишь ставку × множитель
// ============================================================
GAMES.push({ id: "claw", t: "Кран", s: "Подцепи подарок клешнёй — чем дороже приз, тем сложнее удержать", img: "Toy Bear", k: ["#ff4fa0", "#2a0730"], chips: ["новинка", "до x100"] });
WIDE_GAMES.add("claw");
GAME_OPEN.claw = () => openClaw();
GAME_SECTIONS[0][2].splice(1, 0, "claw");
GAME_NAMES.claw = ["gift", "Кран"];

let CLW = null, clwSel = 0, clwBusy = false;
// клешня: каретка на рельсе → трос → корпус с двумя лапами (лапы поворачиваются классом .shut)
const CL_CLAW = `<svg viewBox="0 0 80 70" class="cl-hand"><defs>
  <linearGradient id="clm" x1="0" x2="1"><stop offset="0" stop-color="#8a90a3"/><stop offset=".45" stop-color="#f4f6fb"/><stop offset="1" stop-color="#6d7385"/></linearGradient></defs>
  <rect x="28" y="0" width="24" height="16" rx="5" fill="url(#clm)"/><circle cx="40" cy="18" r="6" fill="#4b5062"/>
  <g class="cl-arm l"><path d="M37 18 L18 36 Q12 48 22 60 L26 57 Q19 47 24 39 L40 24Z" fill="url(#clm)"/></g>
  <g class="cl-arm r"><path d="M43 18 L62 36 Q68 48 58 60 L54 57 Q61 47 56 39 L40 24Z" fill="url(#clm)"/></g></svg>`;

async function openClaw() {
  const el = openSheet(`${gameHead("Toy Bear", "Кран", "Подцепи подарок клешнёй", "claw")}<div id="cl-body">${emptyHTML("hourglass", "Включаем автомат…")}</div>`, "cl-s");
  el._cl = true;
  el._t = setInterval(() => el.isConnected ? clPanelPaint() : clearInterval(el._t), 400);   // ½ ×2 MAX меняют ставку без события input
  el._onClose = () => clearInterval(el._t);
  CLW = await api("claw").catch(() => null);
  if (!CLW || !el.isConnected) return;
  clwSel = Math.min(clwSel, CLW.lineup.length - 1);
  fillClaw(el);
}
// раскладка призов горкой: передний ряд крупнее и ниже, задний — между ними, мельче и выше (в % ширины пола)
function clPos(i) {
  const n = CLW.lineup.length, f = Math.ceil(n / 2), back = n - f;
  if (i < f) return { x: (i + .5) / f * 100, row: 0 };
  const k = i - f;
  return { x: (k + 1) / (back + 1) * 100, row: 1 };
}
const clX = i => 22 + clPos(i).x * .75;   // в % ширины стекла (пол — от 22% до 97%)
const clName = c => esc(c).replace(/'/g, "’");
function clMachine() {
  const n = CLW.lineup.length, f = Math.ceil(n / 2);
  return `<div class="cl-cab">
    <div class="cl-sign"><i class="cl-bulbs"></i><span>GIFT</span><b>CLAW</b><i class="cl-bulbs"></i></div>
    <div class="cl-glass" id="cl-glass" style="--f:${f}">
      <div class="cl-wall"></div>
      <div class="cl-rail"><i></i><i></i></div>
      <div class="cl-car" id="cl-car" style="left:${clX(clwSel)}%"><i class="cl-cable" id="cl-cable"></i><div class="cl-claw" id="cl-claw">${CL_CLAW}</div></div>
      <div class="cl-chute"><div class="cl-hole">${ic("gift")}</div></div>
      <div class="cl-floor">${CLW.lineup.map((x, i) => { const p = clPos(i); return `<button class="cl-prize r${p.row}${i === clwSel ? " on" : ""}${x.m >= 10 ? " big" : ""}" data-act="cl-pick" data-i="${i}"
          style="left:${p.x}%;--r:${((i * 37) % 11) - 5}deg"><i class="cl-mark">${ic("chev")}</i>
          <div class="cl-gift">${giftHTML(x.gift, { lite: true, plain: true })}</div><em>x${String(x.m).replace(".", ",")}</em></button>`; }).join("")}</div>
      <div class="cl-shine"></div>
    </div>
    <div class="cl-base"><span>ВЫБЕРИ ПРИЗ И ЖМИ «ХВАТАЙ»</span></div>
  </div>`;
}
function clPanel() {
  const x = CLW.lineup[clwSel], bet = Math.max(0, betVal("cl-amt") || 0);
  return `<div class="cl-pick">
      <div class="cl-pg">${giftHTML(x.gift, { lite: true, plain: true })}</div>
      <div class="cl-pt"><b>${clName(x.gift.col)}</b><span>приз <em class="${x.m >= 10 ? "g" : ""}">x${String(x.m).replace(".", ",")}</em> · выигрыш ⭐ ${fmt(Math.floor(bet * x.m))}</span></div>
      <div class="cl-pc ${x.p >= 50 ? "hi" : x.p < 10 ? "lo" : ""}"><b>${String(x.p).replace(".", ",")}%</b><span>шанс</span></div>
    </div>`;
}
function fillClaw(el) {
  el = el || SHEETS.find(s => s._cl); if (!el || !CLW) return;
  const keepBet = document.getElementById("cl-amt") ? betVal("cl-amt") : 100;
  el.querySelector("#cl-body").innerHTML = `${clMachine()}
    <div id="cl-panel"></div>
    <div class="betp">${betHTML("cl-amt", keepBet)}
      <div class="cl-btns"><button class="btn cta gold" id="cl-go" data-act="cl-go">Хватай!</button>
        <button class="btn ghost cl-sh" data-act="cl-shuf">${ic("refresh")}</button></div>
</div>`;
  clPanelPaint();
}
function clPanelPaint() { const p = document.getElementById("cl-panel"); if (!p || !CLW) return; const h = clPanel(); if (p._h !== h) { p._h = h; p.innerHTML = h; } }
function clSelect(i) {
  if (clwBusy || !CLW) return;
  clwSel = (i + CLW.lineup.length) % CLW.lineup.length; H.sel();
  document.querySelectorAll(".cl-prize").forEach((b, k) => b.classList.toggle("on", k === clwSel));
  const car = document.getElementById("cl-car"); if (car) car.style.left = clX(clwSel) + "%";
  clPanelPaint();
}

async function clPlay() {
  if (clwBusy || !CLW) return;
  const bet = betVal("cl-amt");
  if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
  clwBusy = true;
  const go = $("#cl-go"); if (go) go.disabled = true;
  try {
    const r = await post("claw/play", { bet, idx: clwSel });
    setStars(ME.stars - bet);
    await clAnimate(r);
    setStars(r.stars);
    if (r.win) { H.ok(); toast(`Поймал! +⭐ ${fmt(r.pay)} · x${String(r.m).replace(".", ",")}`, "ok"); burstAt($(".cl-chute") || $("#cl-glass")); }
    else { H.err(); toast("Сорвался… попробуй ещё", "err"); }
    if (r.levelup) afterLevelUp(r.levelup);
    CLW = { ...CLW, ...r }; clwSel = Math.min(clwSel, CLW.lineup.length - 1);
    fillClaw();
  } finally { clwBusy = false; const g = $("#cl-go"); if (g) g.disabled = false; }
}
// сама анимация: всё по времени через CSS-переходы, проверяем, что шторка ещё открыта
async function clAnimate(r) {
  const glass = $("#cl-glass"), car = $("#cl-car"), claw = $("#cl-claw"), cable = $("#cl-cable");
  const prize = document.querySelectorAll(".cl-prize")[r.idx];
  if (!glass || !prize) return;
  const gr = glass.getBoundingClientRect(), pr = prize.getBoundingClientRect(), cr = claw.getBoundingClientRect();
  const drop = Math.max(40, pr.top - cr.bottom + 34);   // насколько опустить клешню, чтобы обхватить приз
  car.style.left = clX(r.idx) + "%"; await sleep(450);
  H.imp("light");
  claw.style.transition = cable.style.transition = "transform .75s cubic-bezier(.45,0,.55,1), height .75s cubic-bezier(.45,0,.55,1)";
  claw.style.transform = `translateY(${drop}px)`; cable.style.height = `calc(var(--cable) + ${drop}px)`; await sleep(780);
  claw.classList.add("shut"); H.imp("medium"); await sleep(260);
  // приз «прилипает» к клешне: переносим его координаты в систему клешни
  const ghost = prize.querySelector(".cl-gift").cloneNode(true);
  ghost.className = "cl-gift cl-held"; claw.appendChild(ghost); prize.classList.add("taken");
  const lift = (sec, y) => { claw.style.transition = cable.style.transition = `transform ${sec}s cubic-bezier(.45,0,.55,1), height ${sec}s cubic-bezier(.45,0,.55,1)`;
    claw.style.transform = `translateY(${y}px)`; cable.style.height = `calc(var(--cable) + ${y}px)`; };
  if (r.win) {
    lift(.9, 0); await sleep(920);
    car.style.left = "11%"; await sleep(650);
    claw.classList.remove("shut"); ghost.classList.add("fall-chute"); H.imp("heavy"); await sleep(650);
  } else {
    const y = Math.round(drop * (1 - r.slip));
    lift(.9 * r.slip + .15, y); await sleep((.9 * r.slip + .15) * 1000);
    ghost.remove(); prize.classList.remove("taken"); prize.classList.add("drop-back");
    claw.classList.add("wobble"); H.imp("light");
    lift(.6, 0); await sleep(400); claw.classList.remove("shut", "wobble"); await sleep(300);
  }
}

Object.assign(ACT, {
  "cl-pick": el => clSelect(+el.dataset.i),
  "cl-mv": el => clSelect(clwSel + +el.dataset.v),
  "cl-go": () => clPlay(),
  "cl-shuf": async () => { if (clwBusy) return; const r = await post("claw/shuffle").catch(() => null); if (!r) return; H.sel(); CLW = { ...CLW, ...r }; fillClaw(); },
});

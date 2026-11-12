"use strict";
// ============================================================
//  Автоигра: Пёсики, Слоты (N спинов), Мины (открыть K клеток), Башня (K этажей), Курица (до полосы K).
//  Стоп: закончились раунды, не хватает звёзд, крупный выигрыш (по желанию), закрыли игру или нажали «Стоп».
// ============================================================
const AUTO_CFG = {
  dogs: { sel: "#dg-btn", sheet: "dogs-s", target: null },
  slots: { sel: "#sl-btn", sheet: "slots-s", target: null },
  mines: { sel: "#m-btn", sheet: "mines-s", target: ["Открывать клеток", [1, 2, 3, 5, 8], 3] },
  tower: { sel: "#tw-btn", sheet: "tower-s", target: ["Подниматься этажей", [1, 2, 3, 5, 8], 3] },
  chicken: { sel: "#ck-btns", sheet: "ck-s", target: ["Идти до полосы", [2, 3, 5, 8, 12], 5] },
};
let AUTO = { on: false };
const autoSheet = g => SHEETS.find(s => s.classList.contains(AUTO_CFG[g].sheet));
const waitFor = async (cond, ms = 15000) => { const t = Date.now(); while (!cond() && Date.now() - t < ms) await sleep(80); };

// кнопка «Авто» в каждой игре: добавляем после открытия экрана
if (!GAME_OPEN.mines && typeof openMines === "function") GAME_OPEN.mines = () => openMines();   // мины открывались мимо GAME_OPEN
for (const g of Object.keys(AUTO_CFG)) {
  const orig = GAME_OPEN[g]; if (!orig) continue;
  GAME_OPEN[g] = async (...a) => { await orig(...a); autoInject(g); };
}
function autoInject(g) {
  const s = autoSheet(g); if (!s || s.querySelector(".auto-row")) return;
  const anchor = s.querySelector(AUTO_CFG[g].sel); if (!anchor) return;
  const host = g === "chicken" ? anchor : anchor.closest(".dgbtns") || anchor;
  host.insertAdjacentHTML("afterend", `<div class="auto-row"><button class="auto-btn" data-act="auto-open" data-g="${g}">${ic("refresh")}<span>Автоигра</span></button></div>`);
  autoPaint();
}
function autoPaint() {
  document.querySelectorAll(".auto-btn").forEach(b => {
    const run = AUTO.on && AUTO.game === b.dataset.g;
    b.classList.toggle("run", run);
    b.innerHTML = run ? `${ic("x")}<span>Стоп · осталось ${AUTO.left}</span>` : `${ic("refresh")}<span>Автоигра</span>`;
  });
}
function autoSettings(g) {
  const c = AUTO_CFG[g], st = { n: 10, stopBig: true, k: c.target ? c.target[2] : 0 };
  const el = openSheet(`<h2 class="gtitle">Автоигра</h2>
    <div class="sec-t" style="margin-top:0">Сколько раундов</div>
    <div class="seg" id="au-n">${[10, 25, 50, 100].map(n => `<button data-act="au-n" data-v="${n}" class="${n === 10 ? "on" : ""}">${n}</button>`).join("")}</div>
    ${c.target ? `<div class="sec-t">${c.target[0]}</div><div class="seg" id="au-k">${c.target[1].map(n => `<button data-act="au-k" data-v="${n}" class="${n === c.target[2] ? "on" : ""}">${n}</button>`).join("")}</div>` : ""}
    <div class="auto" style="margin-top:6px"><button class="sw on" id="au-big" data-act="au-big"></button><span style="flex:1">Остановиться на выигрыше от ×10</span></div>
    <button class="btn gold cta" data-act="au-go" data-g="${g}" style="margin-top:14px">${ic("refresh")}Запустить</button>
    <div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Ставка — как в игре. Автоигра остановится, если не хватит звёзд или ты закроешь игру.</div>`);
  el._au = st;
}
function autoStop(msg) {
  if (!AUTO.on) return;
  AUTO.on = false; autoPaint();
  if (msg) toast(msg);
}
async function autoRun(g, st) {
  AUTO = { on: true, game: g, left: st.n, k: st.k, stopBig: st.stopBig };
  autoPaint(); H.imp("medium");
  while (AUTO.on && AUTO.left > 0) {
    const s = autoSheet(g); if (!s || !s.isConnected) return autoStop();
    const bet = { dogs: () => betVal("dg-amt") * dgN, slots: () => betVal("sl-amt") * slN, mines: () => betVal("m-amt"), tower: () => betVal("tw-amt"), chicken: () => betVal("ck-amt") }[g]();
    if (bet > ME.stars) return autoStop("Автоигра: не хватает звёзд");
    const s0 = ME.stars;
    try { await AUTO_ROUND[g](); } catch (e) { return autoStop(); }
    await waitFor(() => !document.querySelector(".bw-ov"), 20000);   // ждём, пока закончится экран большого выигрыша
    if (!AUTO.on) break;
    AUTO.left--; autoPaint();
    const x = (ME.stars - s0 + bet) / Math.max(1, bet);
    if (AUTO.stopBig && x >= 10) return autoStop(`Автоигра остановлена: выигрыш ×${x.toFixed(1)}`);
    await sleep(450);
  }
  autoStop(AUTO.left ? "" : "Автоигра завершена");
}
const AUTO_ROUND = {
  dogs: async () => { await waitFor(() => !dgBusy); await dgSpin(); await waitFor(() => !dgBusy); },
  slots: async () => { await waitFor(() => !slBusy); await slSpin(); },
  mines: async () => {
    if (!MS.active) await minesBtn();
    for (let i = 0; i < AUTO.k && MS.active && AUTO.on; i++) {
      const free = [...Array(25).keys()].filter(c => !(MS.opened || []).includes(c));
      await mineClick(free[Math.random() * free.length | 0]); await sleep(260);
    }
    if (MS.active && (MS.opened || []).length) await minesBtn();
  },
  tower: async () => {
    if (!TW.active) await twBtn();
    for (let i = 0; i < AUTO.k && TW.active && AUTO.on; i++) {
      await twStep(Math.random() * TW_N[TW.mode] | 0); await sleep(300);
    }
    if (TW.active && (TW.picks || []).length) await twBtn();
  },
  chicken: async () => {
    if (!CK.active) await ckStart();
    while (CK.active && CK.step < AUTO.k && AUTO.on) { await ckStep(); await waitFor(() => !ckBusy); await sleep(150); }
    if (CK.active && CK.step) { await ckCash(); await waitFor(() => !ckBusy); }
  },
};
Object.assign(ACT, {
  "auto-open": el => { const g = el.dataset.g; if (AUTO.on && AUTO.game === g) return autoStop("Автоигра остановлена"); if (AUTO.on) return toast("Автоигра уже идёт в другой игре"); autoSettings(g); },
  "au-n": el => { topSheet()._au.n = +el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); },
  "au-k": el => { topSheet()._au.k = +el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); },
  "au-big": el => { const st = topSheet()._au; st.stopBig = !st.stopBig; el.classList.toggle("on", st.stopBig); H.sel(); },
  "au-go": el => { const st = topSheet()._au; closeSheet(); autoRun(el.dataset.g, st); },
});

"use strict";
// ============================================================
//  «Пёсики» — слот 5×3: будки-вайлды, лапки → фриспины с липкими вайлдами.
//  1, 2 или 4 автомата крутятся одновременно; бонусы разыгрываются по очереди.
// ============================================================
ICONS.paw = '<circle cx="5.5" cy="10" r="2.2"/><circle cx="9.5" cy="5.5" r="2.2"/><circle cx="14.5" cy="5.5" r="2.2"/><circle cx="18.5" cy="10" r="2.2"/><path d="M12 11.5c-3 0-6 3.5-6 6.2C6 19.8 7.6 21 9.6 21c1 0 1.6-.5 2.4-.5s1.4.5 2.4.5c2 0 3.6-1.2 3.6-3.3 0-2.7-3-6.2-6-6.2z"/>';
const DOGHOUSE = A.model("Jack-in-the-Box", "Doghouse", 256);
GAMES.push({ id: "dogs", t: "Пёсики", s: "До 4 автоматов сразу, будки-вайлды и фриспины", imgUrl: DOGHOUSE, k: ["#ff8a3d", "#3d1a05"], chips: ["x4 автомата", "до x5000"] });
WIDE_GAMES.add("dogs");
GAME_OPEN.dogs = () => openDogs();

let DG = null, dgBusy = false, dgFast = false, dgN = 1;
const DG_W = 10, DG_S = 11, LOWC = ["#4aa8ff", "#35d07f", "#a77bff", "#ff8a3d", "#ff4f7a"];
const DG_START = [[5, 2, 7], [3, 10, 1], [9, 6, 0], [1, 10, 4], [8, 2, 6]];
function dgSym(s, mult) {
  if (s === DG_W) return `<div class="dc wild"><img src="${DOGHOUSE}" alt="">${mult ? `<b>x${mult}</b>` : ""}</div>`;
  if (s === DG_S) return `<div class="dc scat"><span>${ic("paw")}</span><i>БОНУС</i></div>`;
  if (s < 5) return `<div class="dc low" style="--c:${LOWC[s]}"><span>${DG.low[s]}</span></div>`;
  const [col, model] = DG.dogs[s - 5];
  return `<div class="dc dog t${s - 5}"><img src="${A.model(col, model, 128)}" alt=""></div>`;
}
const dgBoard = m => `<div class="dgb" id="dg-b${m}"><div class="dg-lights"></div><div class="dgreels" id="dg-r${m}"></div>
  <svg class="dglines" id="dg-l${m}" viewBox="0 0 500 300" preserveAspectRatio="none"></svg><div class="dgban" id="dg-ban${m}"></div><div class="dgwin" id="dg-w${m}"></div></div>`;

async function openDogs() {
  dgBusy = false;
  openSheet(`${gameHead("Jack-in-the-Box", "Пёсики", "Будки-вайлды и фриспины", "dogs")}
    <div class="dgwrap" id="dg-wrap"></div>
    <div class="dginfo"><div><span>Выигрыш</span><b id="dg-win">—</b></div><div><span>Фриспины</span><b id="dg-fs">—</b></div></div>
    <div class="betp">
      <div class="mn" style="margin:0 0 10px"><span>Автоматы</span><div class="quick" id="dg-n">${[1, 2, 4].map(n => `<button data-act="dg-n" data-v="${n}" class="${dgN === n ? "on" : ""}">x${n}</button>`).join("")}</div></div>
      ${betHTML("dg-amt")}
      <div class="dgbtns"><button class="btn cta gold" id="dg-btn" data-act="dg-spin">Крутить</button><button class="ufast${dgFast ? " on" : ""}" data-act="dg-fast">${ic("trend")}Быстро</button></div>
      <div class="dgbuy" id="dg-buy"></div></div>
    <details class="rules" style="margin-top:12px"><summary>${ic("award")}Как играть и выплаты</summary><div id="dg-pay"></div></details>`, "dogs-s");
  DG = await api("dogs");   // выплаты зависят от возврата в админке — не кэшируем
  const head = document.querySelector(".dogs-s .ghead img"); if (head) head.src = DOGHOUSE;
  dgBuild();
  $("#dg-amt").addEventListener("input", dgBtnText);
  $("#dg-pay").innerHTML = `3+ одинаковых символа слева направо на одной из 20 линий. <b>Будка</b> заменяет любой символ (кроме лапки) и умножает выигрыш линии на x2 или x3 — иксы перемножаются.
    Лапки дают фриспины: <b>3 лапки — ${(DG.freeBy || {})[3] || DG.free}, 4 — ${(DG.freeBy || {})[4] || DG.free}, 5 и больше — ${(DG.freeBy || {})[5] || DG.free}</b>. Все будки во фриспинах прилипают до конца бонуса.
    Можно крутить <b>2 или 4 автомата сразу</b> — ставка на каждый, бонусы разыгрываются по очереди.
    <div class="dgpt">${DG.pay.map((p, i) => `<div>${dgSym(i)}<span>${p.map((x, k) => `${k + 3}× <b>x${x}</b>`).join("<br>")}</span></div>`).reverse().join("")}</div>
    <div style="margin-top:6px">Выплаты указаны в ставках на один автомат. Максимальный выигрыш — x5000.</div>`;
}
function dgBuild() {
  const w = $("#dg-wrap"); if (!w || !DG) return;
  w.className = "dgwrap n" + dgN;
  w.innerHTML = Array.from({ length: dgN }, (_, m) => dgBoard(m)).join("");
  for (let m = 0; m < dgN; m++) dgDraw(m, DG_START.map((c, r) => DG_START[(r + m) % 5]), []);
  dgBtnText();
}
function dgBtnText() {
  const b = $("#dg-btn"); if (b && !dgBusy) b.textContent = dgN > 1 ? `Крутить x${dgN} · ⭐ ${short(betVal("dg-amt") * dgN)}` : "Крутить";
  const y = $("#dg-buy"); if (!y || !DG || !DG.buy) return;
  const bet = betVal("dg-amt");
  y.innerHTML = Object.entries(DG.buy).map(([sc, k]) => `<button data-act="dg-buy" data-v="${sc}" ${dgBusy ? "disabled" : ""}><span>${ic("paw")}Купить ${DG.freeBy[sc]} фриспинов</span><b>⭐ ${fmt(bet * k)}</b></button>`).join("");
  starify(y);
}
function dgDraw(m, grid, wilds) {
  const wm = {}; (wilds || []).forEach(([r, c, x]) => wm[r + "," + c] = x);
  $("#dg-r" + m).innerHTML = grid.map((col, r) => `<div class="dreel"><div class="dstrip" id="dg-s${m}-${r}">${col.map((s, c) => dgSym(s, wm[r + "," + c])).join("")}</div></div>`).join("");
}
async function dgSpinReels(m, fr, fast) {
  const H0 = $(`#dg-r${m} .dc`).getBoundingClientRect().height + 5;
  const wm = {}; fr.wilds.forEach(([r, c, x]) => wm[r + "," + c] = x);
  $("#dg-l" + m).innerHTML = "";
  document.querySelectorAll(`#dg-r${m} .dc.hit`).forEach(e => e.classList.remove("hit"));
  $("#dg-b" + m).classList.add("spin");
  await Promise.all(fr.grid.map((col, r) => new Promise(done => {
    const strip = $(`#dg-s${m}-${r}`), n = fast ? 6 : 12 + r * 4 + m, d = fast ? .45 + r * .08 : 1 + r * .22 + m * .06;
    let h = col.map((s, c) => dgSym(s, wm[r + "," + c])).join("");
    for (let k = 0; k < n; k++) h += dgSym(Math.random() * 10 | 0);
    strip.innerHTML = h;
    strip.style.transition = "none"; strip.style.transform = `translateY(${-n * H0}px)`;
    void strip.offsetWidth;
    strip.style.transition = `transform ${d}s cubic-bezier(.2,.8,.25,1.03)`;
    strip.style.transform = "translateY(0)";
    setTimeout(() => { if (m === 0 && (!fast || r === 4)) H.imp("light"); done(); }, d * 1000);
  })));
  const b = $("#dg-b" + m); if (!b) return;
  b.classList.remove("spin");
  // убрать «хвосты» лент, оставить ровно 3 видимых символа
  fr.grid.forEach((col, r) => { const s = $(`#dg-s${m}-${r}`); if (s) { s.style.transition = "none"; s.style.transform = "none"; s.innerHTML = col.map((x, c) => dgSym(x, wm[r + "," + c])).join(""); } });
  if (fr.wins.length) {
    const cols = ["#ffd76a", "#4cf0a0", "#ff6fb5", "#5aa8ff", "#ff8a3d"];
    $("#dg-l" + m).innerHTML = fr.wins.map((w, i) => {
      const pts = DG.lines[w.line].slice(0, w.n).map((row, r) => `${r * 100 + 50},${row * 100 + 50}`).join(" ");
      return `<polyline points="${pts}" style="--c:${cols[i % cols.length]};animation-delay:${i * 120}ms"/>`;
    }).join("");
    fr.wins.forEach(w => DG.lines[w.line].slice(0, w.n).forEach((row, r) => {
      const cell = $(`#dg-s${m}-${r}`).children[row]; if (cell) cell.classList.add("hit");
    }));
  }
}
function dgBanner(m, html, cls = "") { const b = $("#dg-ban" + m); if (b) { b.className = "dgban on " + cls; b.innerHTML = html; } }
function dgWinTag(m, pay, bet) {
  const w = $("#dg-w" + m); if (!w) return;
  if (!pay) { w.className = "dgwin"; return; }
  const x = pay / bet;
  w.className = "dgwin on" + (x >= 5 ? " big" : x < 1 ? " meh" : "");
  w.innerHTML = `+⭐ ${short(pay)}`; starify(w);
}

async function dgSpin(buy) {   // buy — сколько лапок покупаем (3 или 4), иначе обычный спин
  if (dgBusy || !DG) return;
  if (buy && dgN > 1) { dgN = 1; document.querySelectorAll("#dg-n button").forEach(b => b.classList.toggle("on", b.dataset.v === "1")); dgBuild(); }
  const bet = betVal("dg-amt"), n = dgN, cost = buy ? bet * DG.buy[buy] : bet * n;
  if (cost > ME.stars) return toast("Не хватает звёзд ⭐");
  if (buy && !await confirmM(`Купить ${DG.freeBy[buy]} фриспинов?`, `Ставка ⭐ ${fmt(bet)} на спин, цена бонуса ⭐ ${fmt(cost)}.`, "Купить")) return;
  dgBusy = true; $("#dg-btn").disabled = true;
  document.querySelectorAll("#dg-n button").forEach(b => b.disabled = true);
  setStars(ME.stars - cost); dgBtnText(); BAL_HOLD++;
  for (let m = 0; m < n; m++) { $("#dg-ban" + m).className = "dgban"; dgWinTag(m, 0); $("#dg-b" + m).classList.remove("dim", "free", "won"); }
  $("#dg-fs").textContent = "—"; $("#dg-win").textContent = "—";
  let r;
  try { r = await post(buy ? "dogs/buy" : "dogs", buy ? { bet, scat: +buy } : { bet, n }); } catch (e) { dgEnd(); loadMe(); return; }
  try {   // окно закрыли посреди спина — всё равно dgEnd, иначе залипнут dgBusy и баланс (BAL_HOLD)
  const rounds = r.rounds || [r];
  let acc = 0;
  const addWin = pay => { if (!pay) return; acc += pay; $("#dg-win").textContent = "⭐ " + fmt(acc); };
  // 1) базовые спины всех автоматов одновременно
  await Promise.all(rounds.map(async (rd, m) => {
    const fr = rd.frames[0];
    await dgSpinReels(m, fr, dgFast);
    if (!$("#dg-b" + m)) return;
    if (rd.scatters >= 3) document.querySelectorAll(`#dg-r${m} .dc.scat`).forEach(e => e.classList.add("hit"));
    if (fr.pay) { addWin(fr.pay); dgWinTag(m, fr.pay, bet); $("#dg-b" + m).classList.add("won"); H.imp("medium"); coinShower($("#dg-b" + m), Math.min(60, 8 + fr.pay / bet * 6)); }
  }));
  if (!$("#dg-wrap")) return dgEnd(r, cost);
  await sleep(rounds.some(rd => rd.frames[0].wins.length) ? (dgFast ? 450 : 800) : 150);
  // 2) бонусы — по очереди, остальные автоматы приглушаем
  for (let m = 0; m < rounds.length; m++) {
    const rd = rounds[m];
    if (rd.frames.length < 2 || !$("#dg-wrap")) continue;
    if (n > 1) document.querySelectorAll(".dgwrap .dgb").forEach((b, i) => b.classList.toggle("dim", i !== m));
    const b = $("#dg-b" + m);
    b.scrollIntoView({ behavior: "smooth", block: "center" });
    H.ok(); dgBanner(m, `${ic("paw")}<b>${rd.frames.length - 1} ФРИСПИНОВ!</b><span>${rd.scatters} ${plural(rd.scatters, ["лапка", "лапки", "лапок"])} · будки прилипают</span>`, rd.scatters >= 4 ? "bonus big" : "bonus");
    coinShower(b, 50); await sleep(1700); $("#dg-ban" + m).className = "dgban";
    b.classList.add("free");
    let bonus = rd.frames[0].pay;
    for (let i = 1; i < rd.frames.length; i++) {
      const fr = rd.frames[i];
      if (!$("#dg-b" + m)) break;
      $("#dg-fs").textContent = (n > 1 ? `автомат ${m + 1}: ` : "") + `${fr.left} осталось`;
      await dgSpinReels(m, fr, true);
      if (fr.pay) { bonus += fr.pay; addWin(fr.pay); dgWinTag(m, bonus, bet); H.imp("medium"); coinShower(b, Math.min(50, 6 + fr.pay / bet * 5)); }
      await sleep(fr.wins.length ? (dgFast ? 450 : 800) : 220);
    }
    if (!$("#dg-b" + m)) break;
    b.classList.remove("free");
    dgWinTag(m, rd.pay, bet);
    $("#dg-fs").textContent = "бонус сыгран";
  }
  document.querySelectorAll(".dgwrap .dgb").forEach(b => b.classList.remove("dim"));
  dgEnd(r, cost);
  } catch (e) { if (dgBusy) dgEnd(r, cost); }
}
async function dgEnd(r, spent) {
  dgBusy = false; BAL_HOLD = Math.max(0, BAL_HOLD - 1);
  const btn = $("#dg-btn");
  if (btn) { btn.disabled = false; document.querySelectorAll("#dg-n button").forEach(b => b.disabled = false); dgBtnText(); }
  if (!r) return;
  setStars(r.stars);
  const total = r.total != null ? r.total : r.pay;
  if (!$("#dg-wrap")) { afterLevelUp(r.levelup); return; }
  $("#dg-win").textContent = total ? "⭐ " + fmt(total) : "—";
  const x = total / spent;
  if (x >= 5) await bigWin(total, x);
  else if (total > spent) { H.ok(); toast(`x${x.toFixed(2)} · +⭐ ${fmt(total)}`, "ok"); coinShower($("#dg-wrap"), 40); }
  else if (total > 0) H.imp("medium");
  else H.err();
  afterLevelUp(r.levelup);
}
Object.assign(ACT, {
  "dg-spin": () => dgSpin(),
  "dg-buy": el => dgSpin(el.dataset.v),
  "dg-fast": el => { dgFast = !dgFast; el.classList.toggle("on", dgFast); H.sel(); },
  "dg-n": el => { if (dgBusy) return; dgN = +el.dataset.v; H.sel(); document.querySelectorAll("#dg-n button").forEach(b => b.classList.toggle("on", b === el)); dgBuild(); },
});

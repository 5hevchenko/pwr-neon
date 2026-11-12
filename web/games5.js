"use strict";
// ============================================================
//  Сейф, ставка на банк, аукцион банка, бизнесы клана
// ============================================================
const svgUrl = s => "data:image/svg+xml," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">${s}</svg>`);
const LD_ICON = svgUrl('<g stroke="#ffd9a8" stroke-width="5" stroke-linecap="round"><path d="M22 6 16 58M46 6l-6 52"/><path stroke-width="4.5" d="M20 16h25M19 27h25M18 38h25M17 49h25"/></g>');
const CR_ICON = svgUrl('<circle cx="32" cy="34" r="25" fill="#ffc53d"/><path d="M32 34V9a25 25 0 0 1 21.7 12.5z" fill="#4f8cff"/><path d="M32 34l21.7-12.5a25 25 0 0 1 0 25z" fill="#2fd08a"/><path d="M32 34l21.7 12.5A25 25 0 0 1 32 59z" fill="#ff8a3d"/><path d="M32 34V59a25 25 0 0 1-21.7-12.5z" fill="#ff4f7b"/><path d="M32 34 10.3 46.5a25 25 0 0 1 0-25z" fill="#9b6bff"/><circle cx="32" cy="34" r="7" fill="#fff"/><path d="M32 2l6 11H26z" fill="#fff"/>');
GAMES.push(
  { id: "carousel", t: "Карусель", s: "", imgUrl: CR_ICON, k: ["#ff4f7b", "#3a0a2a"], chips: [] },
  { id: "safe", t: "Сейф", s: "", img: "Money Pot", k: ["#3a7bd5", "#0b2348"], chips: [] },
  { id: "ladder", t: "Лестница", s: "", imgUrl: LD_ICON, k: ["#ff8a3d", "#45170a"], chips: [] },
  { id: "bankbet", t: "Ставка на банк", s: "", img: "Stellar Rocket", k: ["#16c88d", "#07382a"], chips: [] },
  { id: "auction", t: "Аукцион банка", s: "", img: "Swiss Watch", k: ["#9b6bff", "#2a1560"], chips: [] },
);
GCAT.carousel = "top"; GCAT.ladder = "fast"; GCAT.safe = "fast"; GCAT.bankbet = "fast"; GCAT.auction = "gifts";

// ---------------- сейф ----------------
const SFG = { st: null, code: ["", "", ""], busy: false };
const sfCells = (code, marks) => code.split("").map((d, i) => `<i class="${marks[i] ? "ok" : ""}">${d}</i>`).join("");
async function openSafe() {
  openSheet(`${gameHead("Money Pot", "Сейф", "", "safe")}<div id="sf-body">${emptyHTML("hourglass", "Загружаем…")}</div>`, "sf-s");
  try { SFG.st = await api("safe"); } catch (e) { return; }
  SFG.code = SFG.st.active ? sfLocked(SFG.st).map(d => d == null ? "" : d) : ["", "", ""];
  sfDraw();
}
function sfDraw() {
  const b = $("#sf-body"), s = SFG.st; if (!b || !s) return;
  const pot = `<div class="sf-pot"><span>Общий фонд</span><b>⭐ ${fmt(s.pot || 0)}</b><small>заберёт открывший за 1–2 попытки</small></div>`;
  if (!s.active) {
    const done = s.code != null;
    b.innerHTML = `${pot}${done ? `<div class="wres ${s.won ? "win" : "lose"}">${s.won ? `Сейф открыт: +⭐ ${fmt(s.pay)}${s.potWon ? ` (фонд ⭐ ${fmt(s.potWon)})` : ""}` : `Не вышло. Код был ${esc(s.code)}`}</div>` : ""}
      <div class="sf-table">${s.mults.map((m, i) => `<div><span>${i + 1} поп.</span><b>x${m}</b></div>`).join("")}</div>
      <div class="betp">${betHTML("sf-bet", 100)}<button class="btn cta" data-act="sf-start">Начать</button></div>
      <details class="rules"><summary>${ic("award")}Как играть</summary><div>Код из 3 цифр. У тебя 5 попыток: после каждой видно, какие позиции угаданы. Чем быстрее откроешь, тем выше множитель.</div></details>`;
    starify(b); return;
  }
  const locked = sfLocked(s), pos = sfPos(s), wrong = new Set(s.tries.filter(t => !t.marks[pos]).map(t => t.code[pos]));
  const ready = SFG.code.every(d => d !== "");
  b.innerHTML = `${pot}
    <div class="sf-tries">${s.tries.map((x, i) => `<div class="sf-row"><span>${i + 1}</span><div class="sf-cells">${sfCells(x.code, x.marks)}</div><em>x${s.mults[i]}</em></div>`).join("")}</div>
    <div class="sf-code">${[0, 1, 2].map(i => `<i class="${locked[i] != null ? "ok" : i === pos ? "cur" : ""}">${esc(SFG.code[i])}</i>`).join("")}</div>
    <div class="sf-pad">${["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "<"].map(k => k === "" ? "<span></span>" : k === "<"
      ? `<button data-act="sf-key" data-v="<" aria-label="Стереть">${ic("back")}</button>`
      : `<button data-act="sf-key" data-v="${k}" class="${wrong.has(k) ? "off" : ""}">${k}</button>`).join("")}</div>
    <button class="btn cta sf-go" data-act="sf-try" ${ready && !SFG.busy ? "" : "disabled"}>Попытка ${s.tries.length + 1} из 5 · x${s.mults[s.tries.length]}</button>`;
  starify(b);
}
// угаданные позиции зафиксированы, вводить их заново не нужно
function sfLocked(s) { const l = [null, null, null]; (s.tries || []).forEach(t => t.marks.forEach((m, i) => { if (m) l[i] = t.code[i]; })); return l; }
function sfPos(s) { const l = sfLocked(s); for (let i = 0; i < 3; i++) if (l[i] == null && SFG.code[i] === "") return i; return -1; }

// ---------------- лестница ----------------
const LD = { st: null, busy: false, hint: null, last: null };
async function openLadder() {
  openSheet(`<div class="ghead">${gpfBtn("ladder")}<img src="${LD_ICON}" alt=""><div><h2>Лестница</h2></div></div><div id="ld-body">${emptyHTML("hourglass", "Загружаем…")}</div>`, "ld-s");
  LD.hint = null; LD.last = null;
  try { LD.st = await api("ladder"); } catch (e) { return; }
  ldDraw();
}
function ldDraw() {
  const b = $("#ld-body"), s = LD.st; if (!b || !s) return;
  const at = s.step || 0;
  const rows = s.mults.map((m, i) => { const k = i + 1, cls = k <= at ? "done" : k === at + 1 && s.active ? "cur" : "";
    return `<div class="ld-rung ${cls}"><b>x${m}</b><i></i><span>${k === at + 1 && s.active ? "Ты здесь" : k}</span></div>`; }).reverse().join("");
  const res = s.lost ? `<div class="wres lose">Обрыв на ступени ${s.step + 1}</div>` : s.won ? `<div class="wres win">+⭐ ${fmt(s.pay)}</div>` : "";
  if (!s.active) {
    b.innerHTML = `${res}<div class="ld-ladder">${rows}</div><div class="betp">${betHTML("ld-bet", 100)}<button class="btn cta" data-act="ld-start">Начать</button></div>
      <details class="rules"><summary>${ic("award")}Как играть</summary><div>На каждой из 10 ступеней две двери: за одной шаг вверх, за другой обрыв и потеря ставки. Забрать выигрыш можно после любой ступени. Подсказка показывает верную дверь и стоит 105% от суммы на кону.</div></details>`;
    starify(b); return;
  }
  b.innerHTML = `<div class="ld-ladder">${rows}</div>
    <div class="ld-doors">${[0, 1].map(d => `<button class="ld-door${LD.hint === d ? " hint" : ""}" data-act="ld-pick" data-v="${d}" ${LD.busy ? "disabled" : ""}><span class="ld-panel"></span><span class="ld-panel"></span><i></i><b>${LD.hint === d ? "Верная" : d ? "Правая" : "Левая"}</b></button>`).join("")}</div>
    <div class="ld-acts">
      <button class="btn ghost" data-act="ld-hint" ${LD.hint !== null || LD.busy ? "disabled" : ""}>Подсказка ⭐ ${short(s.hintCost)}</button>
      <button class="btn cta" data-act="ld-cash" ${s.step && !LD.busy ? "" : "disabled"}>${s.step ? `Забрать ⭐ ${short(s.win)}` : "Выбери дверь"}</button></div>`;
  starify(b);
}

// ---------------- ставка на банк ----------------
let BBT = null;
const bbHour = h => new Date(h * 3600000).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", hour12: false });
async function openBankBet() {
  openSheet(`${gameHead("Stellar Rocket", "Ставка на банк", "", "bankbet")}<div id="bb-body">${emptyHTML("hourglass", "Загружаем…")}</div>`, "bb-s");
  bbSide = null; bbAmt = null;
  try { BBT = await api("bankbet"); } catch (e) { return; }
  bbDraw();
}
const BB_ARROW = { up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V6M6 12l6-6 6 6" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v13M6 12l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' };
let bbSide = null, bbAmt = null, bbClock = null;
function bbDraw() {
  const b = $("#bb-body"), d = BBT; if (!b || !d) return;
  const prev = $("#bb-amt"); if (prev) bbAmt = betVal("bb-amt");
  const tot = d.up + d.down, pct = tot ? Math.round(d.up / tot * 100) : 50;
  const k = (me, other) => me && other ? "x" + (1 + other / me * (1 - d.rake)).toFixed(2) : "—";
  const my = d.mine.find(x => x.hour === d.hour), side = my ? my.side : bbSide;
  const nowSign = d.netNow > 0 ? "up" : d.netNow < 0 ? "down" : "";
  const card = (v, t, pool, x) => `<button class="bb-card ${v}${side === v ? " on" : ""}" data-act="bb-side" data-v="${v}" ${my && my.side !== v ? "disabled" : ""}>
      <span class="bb-ic">${BB_ARROW[v]}</span><b>${t}</b><strong>${x}</strong><small>в пуле ⭐ ${short(pool)}</small></button>`;
  b.innerHTML = `<div class="bb-hero">
      <span>Банк сейчас</span><b>⭐ ${fmt(d.bank)}</b>
      <em class="${nowSign}">${d.netNow ? (d.netNow > 0 ? "+" : "−") + short(Math.abs(d.netNow)) : "0"} за этот час</em>
    </div>
    <div class="bb-round"><span>Раунд ${bbHour(d.hour)}–${bbHour(d.hour + 1)}</span><b id="bb-clock">${clock(d.startsIn)}</b><small>до старта</small></div>
    <div class="bb-sides">${card("up", "Вырастет", d.up, k(d.up, d.down))}${card("down", "Упадёт", d.down, k(d.down, d.up))}</div>
    <div class="bb-bar" aria-hidden="true"><i style="width:${pct}%"></i></div>
    <div class="bb-pct"><span>${pct}%</span><small>${tot ? `весь пул ⭐ ${short(tot)}` : "пул пока пустой"}</small><span>${100 - pct}%</span></div>
    ${my ? `<div class="bb-mine">Твоя ставка ⭐ ${fmt(d.mine.filter(x => x.hour === d.hour).reduce((t, x) => t + x.amount, 0))} на «${my.side === "up" ? "вырастет" : "упадёт"}»</div>` : ""}
    <div class="betp">${betHTML("bb-amt", bbAmt || d.min)}
      <button class="btn cta" data-act="bb-bet" ${side ? "" : "disabled"}>${side ? (my ? "Добавить к ставке" : `Поставить на «${side === "up" ? "вырастет" : "упадёт"}»`) : "Выбери исход"}</button></div>
    ${d.history.length ? `<div class="sec-t">Прошлые раунды</div><div class="bb-hist">${d.history.map(x => `<div class="${x.side || ""}"><i>${x.side ? BB_ARROW[x.side] : "="}</i><b>${x.net > 0 ? "+" : x.net < 0 ? "−" : ""}${short(Math.abs(x.net))}</b><small>${bbHour(x.hour)}</small></div>`).join("")}</div>` : ""}
    <details class="rules"><summary>${ic("award")}Как играть</summary><div>Ставки принимаются на следующий час. Победители делят ставки проигравших, банк берёт ${Math.round(d.rake * 100)}%. Изменение банка считается без операций участников раунда. Нет соперников или банк не изменился: ставка возвращается.</div></details>`;
  starify(b);
  clearInterval(bbClock);
  const t0 = Date.now(), left = d.startsIn;
  bbClock = setInterval(() => { const c = $("#bb-clock"); if (!c) return clearInterval(bbClock); const v = left - (Date.now() - t0) / 1000; if (v <= 0) { clearInterval(bbClock); openBankBetReload(); } else c.textContent = clock(v); }, 1000);
}
async function openBankBetReload() { try { BBT = await api("bankbet"); bbSide = null; bbDraw(); } catch (e) {} }

// ---------------- аукцион ----------------
let AUC = null;
async function openAuction() {
  openSheet(`${gameHead("Swiss Watch", "Аукцион банка", "", "")}<div id="au-body">${emptyHTML("hourglass", "Загружаем…")}</div>`, "au-s");
  try { AUC = await api("auction"); } catch (e) { return; }
  auDraw();
}
function auDraw() {
  const b = $("#au-body"), l = AUC && AUC.lot; if (!b) return;
  if (!l) { b.innerHTML = emptyHTML("gift", "Лота пока нет: хранилище банка пустое"); return; }
  b.innerHTML = `<div class="au-lot">${giftHTML(l.gift, { lite: true, plain: true })}<b>${esc(l.gift.col)}</b><span>${esc(l.gift.model)}</span></div>
    <div class="fstats"><div><span>Ценность</span><b>⭐ ${short(l.value)}</b></div><div><span>Ставка</span><b>⭐ ${short(l.top)}</b><em>${l.mine ? "твоя" : ""}</em></div></div>
    <p class="hint">До конца ${clock(l.left)}. Деньги победителя идут в банк, перебитая ставка возвращается.</p>
    <div class="betp">${betHTML("au-amt", l.next)}<button class="btn cta" data-act="au-bid" ${l.mine ? "disabled" : ""}>${l.mine ? "Твоя ставка первая" : `Поставить от ⭐ ${fmt(l.next)}`}</button></div>`;
  starify(b);
}

// ---------------- бизнесы клана ----------------
async function openClanBiz() {
  const el = openSheet(`<h2 class="gtitle">Бизнесы клана</h2><div id="cb-body">${emptyHTML("hourglass", "Загружаем…")}</div>`, "cb-s");
  try { cbDraw(await api("clans/biz")); } catch (e) { if (el.isConnected) closeSheet(); }
}
function cbDraw(d) {
  const b = $("#cb-body"); if (!b) return;
  const ready = d.items.reduce((s, x) => s + x.ready, 0);
  b.innerHTML = `<div class="fstats"><div><span>Казна</span><b>⭐ ${short(d.bank)}</b></div><div><span>Готово</span><b>⭐ ${short(ready)}</b></div></div>
    <button class="btn cta fwide" data-act="cb-collect" ${ready ? "" : "disabled"}>Забрать в казну</button>
    <div class="sec-t">Бизнесы</div><div class="box">${d.items.map(x => `<div class="cb-row"><div><b>${esc(x.name)}${x.level ? ` · ур. ${x.level}` : ""}</b><small>⭐ ${short(x.income)} в час</small></div>
      ${d.can && x.cost != null ? `<button class="btn sm ghost" data-act="cb-buy" data-id="${x.id}">${x.level ? "Улучшить" : "Купить"} ⭐ ${short(x.cost)}</button>` : ""}</div>`).join("")}</div>
    <p class="hint">Покупает глава или казначей. Доход копится до 24 часов и идёт в казну клана.</p>`;
  starify(b);
}

Object.assign(GAME_OPEN, { ladder: openLadder, safe: openSafe, bankbet: openBankBet, auction: openAuction });
Object.assign(ACT, {
  "sf-start": async () => {
    const bet = betVal("sf-bet"); SFG.code = ["", "", ""];
    try { const r = await post("safe/start", { bet }); SFG.st = r; if (r.stars != null) setStars(r.stars); sfDraw(); } catch (e) {}
  },
  "sf-key": el => {
    const s = SFG.st; if (!s || !s.active || SFG.busy) return;
    const l = sfLocked(s), v = el.dataset.v;
    if (v === "<") { for (let i = 2; i >= 0; i--) if (l[i] == null && SFG.code[i] !== "") { SFG.code[i] = ""; break; } }
    else { const p = sfPos(s); if (p < 0) return; SFG.code[p] = v; }
    H.sel(); sfDraw();
  },
  "sf-try": async () => {
    if (SFG.busy) return; const code = SFG.code.join("");
    if (code.length !== 3) return toast("Введи 3 цифры");
    SFG.busy = true;
    try {
      const r = await post("safe/try", { code }); SFG.st = r;
      if (r.stars != null) setStars(r.stars);
      if (r.won) { H.ok(); coinShower($("#sf-body"), 40); }
      SFG.code = r.active ? sfLocked(r).map(d => d == null ? "" : d) : ["", "", ""];
    } catch (e) {} finally { SFG.busy = false; sfDraw(); }
  },
  "ld-start": async () => { try { const r = await post("ladder/start", { bet: betVal("ld-bet") }); LD.st = r; LD.hint = null; setStars(r.stars); ldDraw(); } catch (e) {} },
  "ld-pick": async el => {
    if (LD.busy) return; LD.busy = true;
    try {
      const r = await post("ladder/pick", { door: +el.dataset.v }); LD.st = r; LD.hint = null;
      if (r.lost) H.err && H.err(); else H.ok();
      if (r.stars != null) setStars(r.stars);
      if (r.won) coinShower($("#ld-body"), 40);
    } catch (e) {} finally { LD.busy = false; ldDraw(); }
  },
  "ld-hint": async () => {
    if (!await confirmM("Купить подсказку?", `Покажем верную дверь за ⭐ ${fmt(LD.st.hintCost)}.`, "Купить")) return;
    try { const r = await post("ladder/hint"); LD.hint = r.door; setStars(r.stars); ldDraw(); } catch (e) {}
  },
  "ld-cash": async () => { try { const r = await post("ladder/cashout"); LD.st = r; LD.hint = null; setStars(r.stars); H.ok(); coinShower($("#ld-body"), 30); ldDraw(); } catch (e) {} },
  "bb-side": el => { bbSide = el.dataset.v; H.sel(); bbDraw(); },
  "bb-bet": async () => {
    const my = BBT.mine.find(x => x.hour === BBT.hour), side = my ? my.side : bbSide; if (!side) return;
    try { BBT = await post("bankbet", { side, amount: betVal("bb-amt") }); if (BBT.stars != null) setStars(BBT.stars); H.ok(); toast("Ставка принята", "ok"); bbDraw(); } catch (e) {}
  },
  "au-bid": async () => {
    try { AUC = await post("auction/bid", { id: AUC.lot.id, amount: betVal("au-amt") }); if (AUC.stars != null) setStars(AUC.stars); H.ok(); auDraw(); } catch (e) {}
  },
  "clan-biz": () => openClanBiz(),
  "cb-buy": async el => { try { cbDraw(await post(`clans/biz/${el.dataset.id}/buy`)); H.ok(); } catch (e) {} },
  "cb-collect": async () => { try { const r = await post("clans/biz/collect"); cbDraw(r); toast(`В казну: ⭐ ${fmt(r.got)}`, "ok"); } catch (e) {} },
  "biz-mgr": async el => {
    pickGift("Управляющий", async g => {
      if (!await confirmM("Нанять управляющего?", `Подарок ${g.col} будет работать 7 дней и сгорит в конце срока.`, "Нанять")) return;
      try { const r = await post(`biz/${el.dataset.id}/manager`, { gid: g.id }); toast(`Управляющий даёт +${r.bonus}%`, "ok"); if (typeof loadInc === "function") loadInc(); } catch (e) {}
    });
  },
});

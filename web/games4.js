"use strict";
// ============================================================
//  Краш-дуэль, «Больше/меньше» (Hi-Lo), крафт подарков
// ============================================================
ICONS.play = '<path d="M7 4.5v15l12-7.5z"/>';
GAMES.push(
  { id: "hilo", t: "Больше/меньше", s: "Угадай, следующая карта выше или ниже — иксы копятся", img: "Clover Pin", k: ["#1fb86b", "#062b19"], chips: ["до x1000", "забери в любой момент"] },
  { id: "craft", t: "Крафт", s: "Сожги 3–10 подарков — получи один, иногда сильно дороже", img: "Magic Potion", k: ["#a35bff", "#22093f"], chips: ["до x2,5 суммы"] },
);
Object.assign(GAME_OPEN, { hilo: () => openHL(), craft: () => openCraft() });
GAME_SECTIONS.find(s => s[0] === "Подарки")[2].push("craft");
GAME_SECTIONS.find(s => s[0] === "Классика")[2].unshift("hilo");
DGAMES.crash = ["rocket", "Краш", "Ракета общая: кто заберёт позже, но до взрыва — тот победил"];

// ------------------------------------------------------------ краш-дуэль
let CD = null, cdPoll = null, cdRaf = null, cdOff = 0;
async function openCD(id) {
  H.imp("light");
  const el = openSheet(`<div id="cd-body">${emptyHTML("hourglass", "Загружаем дуэль…")}</div>`, "cd-s");
  el._cd = id;
  el._onClose = () => { clearInterval(cdPoll); cancelAnimationFrame(cdRaf); };
  await loadCD(id);
  clearInterval(cdPoll);
  cdPoll = setInterval(() => el.isConnected ? bgOff() || loadCD(id) : clearInterval(cdPoll), 500);
  cancelAnimationFrame(cdRaf); cdRaf = requestAnimationFrame(cdFrame);
}
async function loadCD(id) {
  let d; try { d = await api("cduel/" + id); } catch (e) { return; }
  const was = CD; CD = d; cdOff = d.now - Date.now() / 1000;
  const s = SHEETS.find(x => x._cd === id); if (!s) return;
  if (!s.querySelector(".cd-arena") || (was && was.status !== d.status) || (was && (was.readyA !== d.readyA || was.readyB !== d.readyB || !!was.start !== !!d.start))) fillCD(s);
  else cdPlayers(s);
  if (was && was.status === "live" && d.status !== "live") cdResult(s);
}
const cdNow = () => Date.now() / 1000 + cdOff;
const cdMult = () => CD && CD.start ? Math.exp(CD.k * Math.max(0, cdNow() - CD.start)) : 1;
function cdPlayer(u, cash, ready, side) {
  const st = CD.status !== "live" ? (cash ? `забрал x${cash.toFixed(2)}` : "не успел") : !CD.start ? (ready ? "готов" : "ждём…") : cash ? `забрал x${cash.toFixed(2)}` : "в полёте";
  const cls = cash ? "cash" : CD.status !== "live" ? "bust" : CD.start ? "fly" : ready ? "ready" : "";
  return `<div class="cd-p ${cls}${CD.winner === u.id ? " win" : ""}" data-side="${side}">${avaHTML(u, 56, { lv: true })}<b>${esc(u.name)}</b><span>${st}</span></div>`;
}
function cdPlayers(s) {
  const box = s.querySelector(".cd-ps"); if (!box) return;
  box.innerHTML = cdPlayer(CD.a, CD.ca, CD.readyA, "a") + `<div class="vs">VS</div>` + cdPlayer(CD.b, CD.cb, CD.readyB, "b");
  const mine = CD.me === "a" ? CD.ca : CD.cb, btn = s.querySelector("#cd-btn");
  if (btn && CD.start && CD.status === "live") btn.disabled = !!mine || cdNow() < CD.start;
}
function fillCD(s) {
  const myReady = CD.me === "a" ? CD.readyA : CD.readyB;
  s.querySelector("#cd-body").innerHTML = `
    <h2 class="gtitle">Краш-дуэль</h2>
    <div class="cd-ps"></div>
    <div class="bank">Банк <b>⭐ ${fmt(CD.stake * 2)}</b> · победителю ⭐ ${fmt(CD.pay)}</div>
    <div class="cd-arena"><canvas id="cd-cv"></canvas><div class="cd-m" id="cd-m">x1.00</div><div class="cd-sub" id="cd-sub"></div></div>
    ${CD.status !== "live" ? `<div class="dres ${CD.winner === ME.id ? "win" : CD.winner ? "lose" : ""}" id="cd-res"></div>
        <div class="btns"><button class="btn ghost" data-act="close">Закрыть</button><button class="btn" data-act="cd-again">${ic("target")}Ещё дуэль</button></div>`
      : !CD.start ? `<button class="btn cta ${myReady ? "ghost" : "gold"}" data-act="cd-ready" ${myReady ? "disabled" : ""}>${myReady ? "Ждём соперника…" : `${ic("rocket")}Готов`}</button>
        <div class="hint" style="text-align:center;font-size:12.5px;margin-top:8px">Ракета взлетит через 3 секунды после того, как оба нажмут «Готов». Не готовы за ${Math.ceil(CD.readyLeft / 60)} мин — ставки вернутся.</div>`
      : `<button class="btn cta gold" id="cd-btn" data-act="cd-cash">Забрать</button>
        <div class="hint" style="text-align:center;font-size:12.5px;margin-top:8px">Побеждает тот, кто заберёт позже — но до взрыва. Оба не успели — ставки вернутся.</div>`}`;
  cdPlayers(s);
  if (CD.status !== "live") cdResult(s, true);
}
function cdResult(s, quiet) {
  const r = s.querySelector("#cd-res"); if (!r) return fillCD(s);
  const won = CD.winner === ME.id;
  r.textContent = CD.winner == null ? (CD.status === "expired" ? "Соперник не пришёл — ставки вернулись" : "Ничья — ставки вернулись") : won ? `Победа! +⭐ ${fmt(CD.pay)}` : "Поражение";
  if (!quiet) { if (won) { H.ok(); burstAt(r); } else if (CD.winner) H.err(); setStars(CD.stars); loadMe(); }
}
function cdFrame() {
  cdRaf = requestAnimationFrame(cdFrame);
  const cv = $("#cd-cv"); if (!cv || !CD) return;
  const d = Math.min(devicePixelRatio || 1, 2), W = cv.clientWidth, Hh = cv.clientHeight;
  if (cv.width !== Math.round(W * d)) { cv.width = W * d; cv.height = Hh * d; }
  const c = cv.getContext("2d"); c.setTransform(d, 0, 0, d, 0, 0); c.clearRect(0, 0, W, Hh);
  const over = CD.status !== "live", t = cdNow();
  let m = over ? (CD.cp || 1) : cdMult();
  const mEl = $("#cd-m"), sub = $("#cd-sub");
  if (!CD.start && !over) { mEl.textContent = "x1.00"; sub.textContent = "ждём готовности"; return; }
  if (!over && t < CD.start) { mEl.textContent = (CD.start - t).toFixed(1); sub.textContent = "старт через"; return; }
  // кривая полёта: время по X, множитель по Y (лог-масштаб)
  const dur = Math.max(6, Math.log(m) / CD.k * 1.15), top = Math.max(2, m * 1.25);
  const X = tt => 12 + tt / dur * (W - 30), Y = mm => Hh - 14 - Math.log(mm) / Math.log(top) * (Hh - 34);
  c.beginPath(); c.moveTo(X(0), Y(1));
  const end = Math.log(m) / CD.k;
  for (let i = 1; i <= 60; i++) { const tt = end * i / 60; c.lineTo(X(tt), Y(Math.exp(CD.k * tt))); }
  c.strokeStyle = over ? "#ff5c5c" : "#ffc233"; c.lineWidth = 3; c.lineJoin = "round"; c.stroke();
  // отметки «забрал»
  for (const [cash, u] of [[CD.ca, CD.a], [CD.cb, CD.b]]) if (cash) {
    const tt = Math.log(cash) / CD.k; c.fillStyle = "#4cf0a0"; c.beginPath(); c.arc(X(tt), Y(cash), 6, 0, 6.283); c.fill();
    c.fillStyle = "#fff"; c.font = "700 11px system-ui"; c.fillText(u.name.slice(0, 10), X(tt) + 8, Y(cash) - 8);
  }
  mEl.textContent = "x" + m.toFixed(2);
  mEl.className = "cd-m" + (over ? " boom" : m >= 2 ? " hot" : "");
  sub.textContent = over ? `взорвалась на x${(CD.cp || 1).toFixed(2)}` : "в полёте";
  const btn = $("#cd-btn"); if (btn && !over) { const mine = CD.me === "a" ? CD.ca : CD.cb; btn.innerHTML = mine ? `Забрал x${mine.toFixed(2)}` : `Забрать x${m.toFixed(2)}`; }
}
// живые дуэли — сверху списка дуэлей
const _fillDuels = fillDuels;
fillDuels = async function (el) {
  await _fillDuels(el);
  const d = await loadDuels(); if (!d || !d.live || !d.live.length || !el.isConnected) return;
  el.querySelector("#d-lists").insertAdjacentHTML("afterbegin", `<div class="sec-t">${ic("rocket")}Краш-дуэли сейчас</div>` + d.live.map(x => {
    const o = x.me === "a" ? x.b : x.a;
    return `<div class="dcard"><div class="dleft">${avaHTML(o, 36)}<div class="grow"><div class="t">${esc(o.name)}</div><div class="s"><span class="dgame">${ic("rocket")}Краш</span> · ⭐ ${fmt(x.stake)}</div></div></div>
      <div class="dright"><button class="btn sm gold" data-act="cd-open" data-id="${x.id}">Играть</button></div></div>`;
  }).join(""));
};

// ------------------------------------------------------------ больше / меньше
let HL = null, hlBusy = false;
const SUITS = ["♠", "♥", "♦", "♣"], RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"];
const hlCard = (c, s, cls = "") => `<div class="hl-card ${s === 1 || s === 2 ? "red" : ""} ${cls}"><b>${RANKS[c - 1]}</b><i>${SUITS[s]}</i><b class="br">${RANKS[c - 1]}</b></div>`;
async function openHL() {
  const el = openSheet(`${gameHead("Clover Pin", "Больше/меньше", "Угадай следующую карту — иксы копятся", "hilo")}<div id="hl-body">${emptyHTML("hourglass", "Загружаем…")}</div>`, "hl-s");
  el._hl = true;
  HL = await api("hilo").catch(() => ({ active: false }));
  fillHL(el);
}
function fillHL(el, last) {
  el = el || SHEETS.find(s => s._hl); if (!el) return;
  const b = el.querySelector("#hl-body");
  if (!HL.active) {
    b.innerHTML = `${last ? `<div class="hl-table">${hlCard(last.card, last.suit, last.res === "lose" ? "lose" : "win")}</div>
        <div class="dres ${last.res === "lose" ? "lose" : "win"}">${last.res === "lose" ? `Мимо: −⭐ ${fmt(last.bet)}` : `Забрал ⭐ ${fmt(last.pay)} · x${(+last.mult).toFixed(2)}`}</div>` :
      `<div class="hl-table">${hlCard(13, 0, "back")}</div>`}
      <div class="betp">${betHTML("hl-amt", 100)}<button class="btn cta gold" data-act="hl-start">${ic("play")}Начать</button>
</div>`;
    return;
  }
  const o = HL.odds, hist = HL.hist.slice(-8);
  b.innerHTML = `
    <div class="hl-hist">${hist.map(([c, s, r]) => `<span class="${r === "x" ? "x" : r === "skip" ? "sk" : r ? "ok" : ""}">${RANKS[c - 1]}${SUITS[s]}</span>`).join("")}</div>
    <div class="hl-table">${hlCard(HL.card, HL.suit, "deal")}</div>
    <div class="hl-mult"><span>Сейчас</span><b>x${HL.mult.toFixed(2)}</b><em>⭐ ${fmt(HL.win)}</em></div>
    <div class="hl-btns">
      <button class="btn hl-hi" data-act="hl-go" data-v="hi" ${o.hi.m ? "" : "disabled"}>${ic("up")}<span><b>Выше или так же</b><small>${o.hi.m ? `${Math.round(o.hi.p * 100)}% · x${o.hi.m}` : "—"}</small></span></button>
      <button class="btn hl-lo" data-act="hl-go" data-v="lo" ${o.lo.m ? "" : "disabled"}>${ic("down")}<span><b>Ниже или так же</b><small>${o.lo.m ? `${Math.round(o.lo.p * 100)}% · x${o.lo.m}` : "—"}</small></span></button>
    </div>
    <div class="hl-row"><button class="btn ghost" data-act="hl-go" data-v="skip">${ic("refresh")}Пропустить</button>
      <button class="btn green" data-act="hl-cash" ${HL.mult > 1 ? "" : "disabled"}>Забрать ⭐ ${fmt(HL.win)}</button></div>
    <div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Ставка ⭐ ${fmt(HL.bet)}</div>`;
}

// ------------------------------------------------------------ крафт
let CR = { gifts: [], col: null, busy: false };
function openCraft() {
  CR = { gifts: [], col: null, busy: false };
  const el = openSheet(`${gameHead("Magic Potion", "Крафт", "3–10 подарков → 1 подарок выбранной коллекции", "craft")}<div id="cr-body"></div>`, "cr-s");
  el._cr = true;
  fillCraft(el);
}
function fillCraft(el) {
  el = el || SHEETS.find(s => s._cr); if (!el) return;
  const total = CR.gifts.reduce((s, g) => s + g.value, 0);
  const cols = [...new Set(CR.gifts.map(g => g.col))];
  if (!cols.includes(CR.col)) CR.col = cols[0] || null;
  el.querySelector("#cr-body").innerHTML = `
    <div class="cr-pot">${CR.gifts.length ? CR.gifts.map(g => `<div class="cr-g">${giftHTML(g, { lite: true, plain: true })}</div>`).join("") : `<div class="hint bk-empty">Выбери от 3 до 10 своих подарков</div>`}</div>
    <button class="btn ghost" style="width:100%" data-act="cr-pick">${ic("plus")}${CR.gifts.length ? "Изменить выбор" : "Выбрать подарки"}</button>
    ${CR.gifts.length ? `<div class="cr-sum"><span>Сумма ценностей</span><b>⭐ ${fmt(total)}</b></div>
      <div class="fx-lbl">Во что крафтим</div>
      <div class="fx-coins sm">${cols.map(c => `<button data-act="cr-col" data-v="${esc(c)}" class="${c === CR.col ? "on" : ""}"><img src="${A.orig(c, 64)}" alt="" style="width:22px;height:22px;object-fit:contain">${esc(c)}</button>`).join("")}</div>` : ""}
    <div class="cr-odds"><div><b>72%</b><span>⭐ ${total ? short(Math.round(total * .55)) + "–" + short(Math.round(total * .9)) : "×0,55–0,9"}</span></div>
      <div class="mid"><b>23%</b><span>⭐ ${total ? short(Math.round(total * .95)) + "–" + short(Math.round(total * 1.5)) : "×0,95–1,5"}</span></div>
      <div class="top"><b>5%</b><span>⭐ ${total ? short(Math.round(total * 1.5)) + "–" + short(Math.round(total * 2.5)) : "×1,5–2,5"}</span></div></div>
    <button class="btn cta gold" data-act="cr-go" ${CR.gifts.length >= 3 ? "" : "disabled"}>${ic("flame")}Скрафтить${CR.gifts.length ? ` ${CR.gifts.length} → 1` : ""}</button>
`;
}

// ------------------------------------------------------------ действия
const _duelAcc = ACT["duel-acc"];
Object.assign(ACT, {
  "duel-acc": async el => {
    const r0 = await post(`duels/${el.dataset.id}/accept`);
    if (r0.live) { setStars(r0.stars); refreshDuels(); return openCD(r0.live); }
    playDuel(r0);
  },
  "cd-open": el => openCD(+el.dataset.id),
  "cd-ready": async el => { el.disabled = true; H.imp("medium"); await post(`cduel/${topSheet()._cd}/ready`).catch(() => {}); loadCD(topSheet()._cd); },
  "cd-cash": async el => {
    el.disabled = true; H.imp("heavy");
    const id = topSheet()._cd;
    try { const r = await post(`cduel/${id}/cash`); const mine = r.me === "a" ? r.ca : r.cb; if (mine) toast(`Забрал x${mine.toFixed(2)}`, "ok"); else toast("Не успел — ракета взорвалась", "err"); } catch (e) {}
    loadCD(id);
  },
  "cd-again": () => { closeSheet(); DUEL.game = "crash"; if (!SHEETS.some(s => s._duels)) openDuels(); },
  "hl-start": async () => {
    const bet = betVal("hl-amt"); if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
    const r = await post("hilo/start", { bet }); HL = r; setStars(r.stars); H.imp("medium"); fillHL(); if (r.levelup) afterLevelUp(r.levelup);
  },
  "hl-go": async el => {
    if (hlBusy || !HL || !HL.active) return; hlBusy = true;   // ход и «Забрать» не идут параллельно
    try {
      const r = await post("hilo/guess", { dir: el.dataset.v });
      if (r.res === "lose") { HL = { active: false }; H.err(); fillHL(null, { ...r, res: "lose" }); setStars(r.stars); }
      else if (r.res === "max") { HL = { active: false }; H.ok(); fillHL(null, { ...r, res: "max" }); setStars(r.stars); burstAt($("#hl-body")); if (r.mult >= 5) bigWin(r.pay, r.mult); }
      else { HL = r; r.res === "skip" ? H.sel() : H.ok(); fillHL(); }
    } finally { hlBusy = false; }
  },
  "hl-cash": async () => {
    if (hlBusy || !HL || !HL.active) return; hlBusy = true;
    try {
      const r = await post("hilo/cashout"); setStars(r.stars); H.ok();
      fillHL(null, { res: "cash", card: HL.card, suit: HL.suit, pay: r.pay, mult: r.mult }); burstAt($("#hl-body")); HL = { active: false }; if (r.mult >= 5) bigWin(r.pay, r.mult);
    } finally { hlBusy = false; }
  },
  "cr-pick": () => pickGifts("Для крафта", { max: 10, pre: CR.gifts }, list => { CR.gifts = list; fillCraft(); }),
  "cr-col": el => { CR.col = el.dataset.v; H.sel(); fillCraft(); },
  "cr-go": async el => {
    if (CR.busy || CR.gifts.length < 3) return;
    if (!await confirmM("Скрафтить?", `${CR.gifts.length} ${plural(CR.gifts.length, ["подарок сгорит", "подарка сгорят", "подарков сгорят"])}. Взамен — один подарок ${esc(CR.col)}.`, "Крафт")) return;
    CR.busy = true; el.disabled = true;
    try {
      const pot = $(".cr-pot"); pot.classList.add("burn"); H.imp("heavy"); await sleep(900);
      const r = await post("craft", { gids: CR.gifts.map(g => g.id), col: CR.col });
      const up = r.k >= 1;
      up ? H.ok() : H.imp("light");
      CR.gifts = []; fillCraft();
      openGift({ g: r.gift, mine: true });
      setStars(r.stars);
      toast(`${up ? "Повезло" : "Готово"}: ⭐ ${fmt(r.gift.value)}${r.bonus ? ` + ⭐ ${fmt(r.bonus)} доплаты` : ""} из ⭐ ${fmt(r.total)} · x${String(r.k).replace(".", ",")}`, up ? "ok" : "");
      if (up) burstAt($("#cr-body"));
    } finally { CR.busy = false; }
  },
});
// ссылка из бота: ?cduel=ID — сразу открыть краш-дуэль
(function () {
  const id = +new URLSearchParams(location.search).get("cduel");
  if (!id) return;
  const t = setInterval(() => { if (ME) { clearInterval(t); openCD(id); } }, 300);
})();

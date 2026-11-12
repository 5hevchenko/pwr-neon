"use strict";
// ============================================================
//  Карты: блэкджек (с дилером и «21» с друзьями) и «101»
// ============================================================
GAMES.push(
  { id: "blackjack", t: "Блэкджек", s: "Против дилера или «21» с друзьями", img: "Vintage Cigar", k: ["#1fb86a", "#05301a"], chips: ["x2.5 за BJ", "с друзьями"] },
  { id: "101", t: "101", s: "Карточная игра на 2–4 — скинь карты первым", img: "Jester Hat", k: ["#e8485f", "#3d0612"], chips: ["2–4 игрока"] });
Object.assign(GAME_OPEN, { blackjack: () => openBJ(), "101": () => openTables("101") });

// ------------------------------------------------------------ карта
const SUIT_P = {
  H: '<path d="M12 21s-7.5-4.6-9.6-9.3A5.4 5.4 0 0 1 12 5.6a5.4 5.4 0 0 1 9.6 6.1C19.5 16.4 12 21 12 21z"/>',
  D: '<path d="M12 2.2 20.3 12 12 21.8 3.7 12z"/>',
  S: '<path d="M12 2.2C9.4 5.8 3.3 9 3.3 13.8a4.5 4.5 0 0 0 7.6 3.3L9.8 21.8h4.4l-1.1-4.7a4.5 4.5 0 0 0 7.6-3.3C20.7 9 14.6 5.8 12 2.2z"/>',
  C: '<path d="M12 2.6a4.1 4.1 0 0 0-3.7 5.9 4.1 4.1 0 1 0 2.7 7.2l-1.2 6.1h4.4L13 15.7a4.1 4.1 0 1 0 2.7-7.2A4.1 4.1 0 0 0 12 2.6z"/>',
};
const suitSVG = (s, cls = "") => `<svg class="suit ${cls}" viewBox="0 0 24 24">${SUIT_P[s]}</svg>`;
const SUIT_NAME = { S: "Пики", H: "Червы", D: "Бубны", C: "Трефы" };
function cardHTML(c, o = {}) {
  if (!c || c === "??") return `<div class="pc back${o.sm ? " sm" : ""}"></div>`;
  const r = c[0] === "T" ? "10" : c[0], s = c[1], red = s === "H" || s === "D";
  return `<div class="pc${red ? " red" : ""}${o.sm ? " sm" : ""}${o.cls ? " " + o.cls : ""}"${o.act ? ` data-act="${o.act}" data-card="${c}"` : ""} style="${o.style || ""}">
    <span class="pr">${r}${suitSVG(s)}</span>${suitSVG(s, "big")}<span class="pr b">${r}${suitSVG(s)}</span></div>`;
}
const handHTML = (cards, o = {}) => `<div class="hand${o.fan ? " fan" : ""}">${cards.map((c, i) => cardHTML(c, { ...o, style: o.fan ? `--i:${i - (cards.length - 1) / 2}` : "", cls: o.cls && o.cls(c) })).join("")}</div>`;

// ============================================================ БЛЭКДЖЕК против дилера
let BJ = { active: false }, bjBusy = false, bjTab = "dealer";
async function openBJ() {
  bjBusy = false;
  const el = openSheet(`${gameHead("Vintage Cigar", "Блэкджек", "Набери 21 или больше дилера, но без перебора", "cards")}
    <div class="seg" style="margin-bottom:12px">${[["dealer", "box", "С дилером"], ["friends", "users", "«21» с друзьями"]].map(([k, i, t]) => `<button data-act="bj-tab" data-v="${k}" class="${bjTab === k ? "on" : ""}">${ic(i)}${t}</button>`).join("")}</div>
    <div id="bj-body"></div>`, "bj-s");
  el._bj = true;
  bjTabDraw();
}
async function bjTabDraw() {
  const b = $("#bj-body"); if (!b) return;
  if (bjTab === "friends") { b.innerHTML = tablesHTML("21"); return loadTables("21"); }
  b.innerHTML = `
    <div class="felt">
      <div class="fl"><span>Дилер</span></div><div id="bj-d" class="hrow"></div>
      <div class="bjres" id="bj-res"></div>
      <div id="bj-p" class="hrow"></div><div class="fl"><span>Ты</span></div>
    </div>
    <div class="betp" id="bj-ctl"></div>
`;
  BJ = await api("bj");
  bjDraw();
}
// очки — круглый значок справа от карт: 21 золотой, перебор красный
const bjScore = v => v == null || v === "" ? "" : `<b class="bjsc${+v > 21 ? " bust" : +v === 21 ? " bj21" : ""}">${v}</b>`;
function bjDraw(res) {
  if (!$("#bj-d")) return;
  const act = BJ.active;
  $("#bj-d").innerHTML = (BJ.dealer ? handHTML(BJ.dealer) : handHTML(["??", "??"])) + bjScore(BJ.dealer ? BJ.dv : null);
  $("#bj-p").innerHTML = (BJ.player ? handHTML(BJ.player) : handHTML(["??", "??"])) + bjScore(BJ.player ? BJ.pv : null);
  const R = { win: ["Победа!", "win"], blackjack: ["Блэкджек!", "win"], push: ["Ничья", "meh"], lose: ["Дилер выиграл", "lose"], bust: ["Перебор", "lose"] }[res];
  $("#bj-res").innerHTML = R ? `<span class="${R[1]}">${R[0]}${BJ.pay ? ` · ⭐ ${fmt(BJ.pay)}` : ""}</span>` : "";
  $("#bj-ctl").innerHTML = act
    ? `<div class="btns" style="margin:0"><button class="btn cta gold" data-act="bj" data-v="hit">${ic("plus")}Ещё</button><button class="btn cta green" data-act="bj" data-v="stand">Хватит</button></div>
       ${BJ.player.length === 2 ? `<button class="btn ghost" style="margin-top:8px" data-act="bj" data-v="double">Удвоить · ⭐ ${fmt(BJ.bet)}</button>` : ""}`
    : `${betHTML("bj-amt")}<button class="btn cta gold" data-act="bj-deal">Раздать</button>`;
}
async function bjAct(a) {
  if (bjBusy) return; bjBusy = true;
  try {
    if (a === "deal") {
      const bet = betVal("bj-amt"); if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
      BJ = await post("bj/start", { bet }); H.imp("medium"); setStars(BJ.stars);
      afterLevelUp(BJ.levelup);
    } else {
      BJ = await post("bj/" + a); H.sel();
    }
    bjDraw(BJ.result);
    if (BJ.result) {
      setStars(BJ.stars);
      if (BJ.result === "win" || BJ.result === "blackjack") { H.ok(); burstAt($("#bj-res")); } else if (BJ.result !== "push") H.err();
    }
  } finally { bjBusy = false; }
}

// ============================================================ СТОЛЫ с друзьями («21», «101»)
const TB = { stake: 200, maxp: 2, pub: true, invite: [], kind: "stars" };
const RULES_101 = `<details class="rules"><summary>${ic("award")}Правила 101</summary><div>
  Колода 36 карт, у каждого по 5. Ходи картой той же масти или того же достоинства, что верхняя. Нечем ходить — возьми карту, потом можно пасовать.
  <b>6</b> — нужно покрыть своей же картой (масть шестёрки, другая 6 или дама). <b>7</b> — следующий берёт 1 и пропускает ход.
  <b>8</b> — следующий берёт 2 и пропускает. <b>Туз</b> — следующий пропускает ход. <b>Дама</b> — кладётся на что угодно, ты выбираешь масть.
  <b>Король пик</b> — следующий берёт 4 и пропускает. Кто первым скинул все карты — забирает банк.</div></details>`;
function openTables(game) {
  H.imp("light");
  const el = openSheet(`${gameHead(game === "101" ? "Jester Hat" : "Vintage Cigar", game === "101" ? "101" : "Двадцать одно", "Играй с друзьями — победитель забирает банк", "cards")}
    ${game === "101" ? RULES_101 : ""}<div id="tb-body">${tablesHTML(game)}</div>`, "tables-s");
  el._tables = game;
  loadTables(game);
}
function tablesHTML(game) {
  return `<div class="dnew">
      <div class="dsub">Новый стол «${game === "101" ? "101" : "21"}»</div>
      <div class="seg" style="margin-bottom:10px">${[["stars", "wallet", "На звёзды"], ["gifts", "gift", "На подарки"]].map(([k, i, t]) => `<button data-act="tb-kind" data-v="${k}" class="${TB.kind === k ? "on" : ""}">${ic(i)}${t}</button>`).join("")}</div>
      <div class="mn" style="margin:0 0 10px"><span>Игроков</span><div class="quick">${[2, 3, 4].map(n => `<button data-act="tb-maxp" data-v="${n}" class="${TB.maxp === n ? "on" : ""}">${n}</button>`).join("")}</div></div>
      <div class="dopp" id="tb-inv"></div>
      <div id="tb-stake">${TB.kind === "gifts" ? "" : betHTML("tb-amt", TB.stake)}</div>
      <button class="btn cta gold" data-act="tb-new" data-g="${game}">${ic(TB.kind === "gifts" ? "gift" : "plus")}${TB.kind === "gifts" ? "Выбрать подарки и создать" : "Создать стол"}</button>
      <div class="hint" style="font-size:12px;text-align:center;margin-top:8px">${TB.kind === "gifts"
        ? "Каждый кладёт подарки (не меньше 80% ценности ставки хозяина), победитель забирает все."
        : `Ставка с каждого игрока, победитель забирает банк (комиссия ${feeP("room", .05)}).`} На ход — 45 секунд.</div>
    </div><div id="tb-lists">${emptyHTML("hourglass", "Загружаем столы…")}</div>`;
}
function tbInvDraw() {
  const o = $("#tb-inv"); if (!o) return;
  o.innerHTML = `<div class="row" style="padding:0"><span class="dany">${ic(TB.invite.length ? "userCheck" : "users")}</span><div class="grow">
    <div class="t">${TB.invite.length ? "Позвать: " + TB.invite.map(u => esc(u.name)).join(", ") : "Открытый стол"}</div><div class="s">${TB.invite.length ? "закрытый — только приглашённые" : "сядет любой игрок"}</div></div>
    ${TB.invite.length ? `<button class="ibtn" data-act="tb-noinv">${ic("x")}</button>` : `<button class="btn sm ghost" data-act="tb-pick">${ic("userPlus")}Друзья</button>`}</div>`;
}
async function loadTables(game) {
  tbInvDraw();
  const d = await api("rooms"), box = $("#tb-lists"); if (!box) return;
  const f = l => l.filter(x => x.game === game);
  const row = (x, btn) => `<div class="dcard"><div class="dleft" data-act="room" data-id="${x.id}">${avaHTML(x.host, 36)}<div class="grow"><div class="t">${esc(x.host.name)}</div>
    <div class="s">${x.count}/${x.maxp} игроков · ${x.kind === "gifts" ? `${ic("gift")}подарки ~⭐ ${short(x.stake)}` : `⭐ ${fmt(x.stake)}`}${x.status === "playing" ? " · идёт игра" : ""}</div></div></div><div class="dright">${btn}</div></div>`;
  const sec = (t, i, l, btn, empty) => `<div class="sec-t">${ic(i)}${t}</div>` + (l.length ? l.map(x => row(x, btn(x))).join("") : `<div class="hint dempty">${empty}</div>`);
  box.innerHTML =
    (f(d.mine).length ? sec("Твои столы", "grid", f(d.mine), x => `<button class="btn sm" data-act="room" data-id="${x.id}">Открыть</button>`, "") : "") +
    (f(d.invites).length ? sec("Тебя зовут", "userPlus", f(d.invites), x => `<button class="btn sm green" data-act="tb-join" data-id="${x.id}" data-kind="${x.kind}" data-stake="${x.stake}">Сесть</button>`, "") : "") +
    sec("Открытые столы", "users", f(d.open), x => `<button class="btn sm green" data-act="tb-join" data-id="${x.id}" data-kind="${x.kind}" data-stake="${x.stake}">Сесть</button>`, "Свободных столов нет — создай свой и позови друзей");
}
async function refreshTables() { for (const s of SHEETS) { if (s._tables) loadTables(s._tables); if (s._bj && bjTab === "friends") loadTables("21"); } }

// ------------------------------------------------------------ сам стол
let ROOM = null, roomPoll = null, roomBusy = false;
async function openRoom(id) {
  H.imp("light"); roomKey = ""; roomHand = new Set();
  const el = openSheet(`<div id="room">${emptyHTML("hourglass", "Садимся за стол…")}</div>`, "room-s");
  el._room = id;
  el._onClose = () => { clearInterval(roomPoll); ROOM = null; refreshTables(); loadMe(); };
  await roomLoad(id);
  clearInterval(roomPoll);
  roomPoll = setInterval(() => { if (el.isConnected && !bgOff() && ROOM && ROOM.status !== "done" && ROOM.status !== "cancelled") roomLoad(id); }, 1300);
}
async function roomLoad(id) {
  if (roomBusy) return;
  try { const v = await api("rooms/" + id); roomSet(v); } catch (e) { clearInterval(roomPoll); }
}
let roomKey = "", roomHand = new Set();
function roomSet(v) {
  const key = JSON.stringify({ ...v, now: 0, deadline: 0, stars: 0 });
  if (key === roomKey && ROOM) {   // поменялся только таймер
    ROOM.now = v.now; ROOM.deadline = v.deadline;
    const left = v.deadline ? Math.max(0, Math.round(v.deadline - v.now)) : 0;
    document.querySelectorAll("#room .tmr").forEach(e => e.textContent = left + "с");
    const yt = $("#room .yourturn"); if (yt) yt.innerHTML = `${ic("clock")}Твой ход · ${left}с`;
    return;
  }
  roomKey = key;
  const prevTurn = ROOM && ROOM.turn, prevStatus = ROOM && ROOM.status;
  ROOM = v;
  if (v.turn === ME.id && prevTurn !== ME.id && v.status === "playing") { H.imp("heavy"); toast("Твой ход!"); }
  if (v.status === "done" && prevStatus === "playing") {
    const won = v.result.winners.includes(ME.id);
    won ? (H.ok(), setTimeout(() => burstAt($("#room")), 100)) : H.err();
    loadMe();
  }
  roomDraw();
}
function roomDraw() {
  const box = $("#room"), v = ROOM; if (!box || !v) return;
  const me = v.players.find(p => p.id === ME.id), myTurn = v.turn === ME.id && v.status === "playing";
  const left = v.deadline ? Math.max(0, Math.round(v.deadline - v.now)) : 0;
  const seat = p => `<div class="seat${v.turn === p.id ? " turn" : ""}${p.left ? " left" : ""}${v.result && v.result.winners.includes(p.id) ? " won" : ""}">
      ${avaHTML(p, 46)}<b>${p.id === ME.id ? "Ты" : esc(p.name)}</b>
      ${v.game === "101" && p.count != null ? `<div class="backs">${Array.from({ length: Math.min(p.count, 7) }, (_, i) => `<i style="--i:${i - (Math.min(p.count, 7) - 1) / 2}"></i>`).join("")}</div><span class="cnt">${p.count} ${plural(p.count, ["карта", "карты", "карт"])}</span>` : ""}
      ${v.game === "21" && p.cards && p.id !== ME.id ? `<div class="mini">${p.cards.map(c => cardHTML(c, { sm: true })).join("")}</div><span class="cnt">${p.value != null ? p.value : ""}${p.done ? " · стоп" : ""}</span>` : ""}
      ${v.turn === p.id ? `<span class="tmr">${left}с</span>` : ""}</div>`;
  let center = "";
  if (v.status === "waiting") {
    center = `<div class="wait"><b>Ждём игроков ${v.players.length}/${v.maxp}</b><span>Банк растёт с каждым игроком</span>
      <div class="btns">${v.host === ME.id ? `<button class="btn cta gold" data-act="rm" data-v="start" ${v.players.length < 2 ? "disabled" : ""}>Начать игру</button>` : `<button class="btn ghost" disabled>Ждём, пока хозяин начнёт</button>`}</div>
      <div class="btns"><button class="btn ghost" data-act="rm-inv">${ic("userPlus")}Позвать друга</button><button class="btn red" data-act="rm" data-v="${v.host === ME.id ? "cancel" : "leave"}">${v.host === ME.id ? "Отменить стол" : "Встать"}</button></div></div>`;
  } else if (v.game === "21") {
    center = me && me.cards ? `<div class="felt sm"><div class="fl"><span>Твоя рука</span></div><div class="hrow">${handHTML(me.cards)}${bjScore(me.value)}</div></div>` : "";
    if (myTurn) center += `<div class="btns"><button class="btn cta gold" data-act="rm-act" data-v="hit">${ic("plus")}Ещё</button><button class="btn cta green" data-act="rm-act" data-v="stand">Хватит</button></div>`;
  } else {
    const SU = v.suit, last = (v.log || []).slice(-1)[0];
    const cardTxt = t => esc(t).replace(/([6-9TJQKA])([SHDC])/g, (m, r, s) => `<i class="${s === "H" || s === "D" ? "red" : ""}">${r === "T" ? "10" : r}${suitSVG(s)}</i>`).replace(/→ ([SHDC])/, (m, s) => "→ " + SUIT_NAME[s]);
    center = `<div class="felt t101">
      <div class="pile"><div class="discard">${cardHTML(v.top)}</div><div class="deckc"><div class="pc back"></div><div class="pc back"></div><span>${v.deck != null ? v.deck : ""}</span></div></div>
      <div class="cursuit ${SU === "H" || SU === "D" ? "red" : ""}">${suitSVG(SU)}${SUIT_NAME[SU]}</div>
      ${v.must ? `<div class="alert6">Покрой шестёрку — масть ${SUIT_NAME[SU].toLowerCase()}, шестёрка или дама</div>` : ""}
      <div class="lastmv">${last ? cardTxt(last) : "Первый ход — масть или достоинство верхней карты"}</div></div>`;
    if (v.status === "playing" && v.hand) {
      const n = v.hand.length, W = Math.min(innerWidth, 520) - 32, cw = 62;
      const ov = n > 1 ? Math.max(6, Math.min(cw - 14, (n * cw - W) / (n - 1) + 4)) : 0;
      center += `<div class="hand101${myTurn ? " live" : ""}" style="--ov:${n * cw > W ? ov : 6}px">${v.hand.map(c =>
        cardHTML(c, { act: myTurn ? "rm-play" : "", cls: roomHand.size && !roomHand.has(c) ? "new" : "" })).join("")}</div>`;
      roomHand = new Set(v.hand);
      if (myTurn) center += `<div class="btns">
        <button class="btn ${v.playable.length && !v.must ? "ghost" : "cta"}" data-act="rm-act" data-v="draw" ${v.drew && !v.must ? "disabled" : ""}>${ic("plus")}Взять карту</button>
        <button class="btn ghost" data-act="rm-act" data-v="pass" ${!v.drew || v.must ? "disabled" : ""}>Пас</button></div>`;
    }
  }
  if (v.status === "done") {
    const won = v.result.winners.includes(ME.id);
    center += `<div class="rres ${won ? "win" : "lose"}">${won ? (v.kind === "gifts" ? `Победа! Подарки банка твои` : `Победа! +⭐ ${fmt(v.result.share)}`) : `Победил ${v.players.filter(p => v.result.winners.includes(p.id)).map(p => esc(p.name)).join(", ")}`}</div>
      <div class="btns"><button class="btn ghost" data-act="close">Закрыть</button><button class="btn cta gold" data-act="rm-again">${ic("refresh")}Новый стол</button></div>`;
  } else if (v.status === "cancelled") center += `<div class="rres lose">Стол отменён, ставки вернулись</div>`;
  const potBox = v.kind === "gifts" && v.potGifts && v.potGifts.length ? `<div class="potg">${v.potGifts.slice(0, 12).map(g => `<div data-act="gift" data-k="${reg({ g })}">${giftHTML(g, { lite: true, plain: true })}</div>`).join("")}${v.potGifts.length > 12 ? `<span>+${v.potGifts.length - 12}</span>` : ""}</div>` : "";
  box.innerHTML = `<div class="rhead"><h2>${esc(v.title)}</h2><span>${v.kind === "gifts" ? `${ic("gift")}Игра на подарки` : `Ставка ⭐ ${fmt(v.stake)}`}</span></div>
    <div class="potbar"><span>Банк стола</span><b>⭐ ${fmt(v.pot)}</b></div>${potBox}
    <div class="seats">${v.players.filter(p => p.id !== ME.id || v.status === "waiting" || v.game === "21" && false).map(seat).join("")}</div>
    ${myTurn ? `<div class="yourturn">${ic("clock")}Твой ход · ${left}с</div>` : v.status === "playing" ? `<div class="theirturn">Ходит ${esc((v.players.find(p => p.id === v.turn) || {}).name || "")}</div>` : ""}
    ${center}
    ${v.status === "playing" && v.players.some(p => p.id === ME.id && !p.left) ? `<button class="btn ghost giveup" data-act="rm" data-v="leave">Сдаться</button>` : ""}`;
}
async function roomPost(path, body = {}) {
  if (roomBusy) return; roomBusy = true;
  try { const v = await post(`rooms/${ROOM.id}/${path}`, body); roomSet(v); if (v.stars != null) setStars(v.stars); return v; }
  finally { roomBusy = false; }
}
function pickSuit() {
  return modal(`<h3>Какую масть заказываешь?</h3><div class="suits">${"SHDC".split("").map(s => `<button data-m="ok" data-s="${s}" class="${s === "H" || s === "D" ? "red" : ""}">${suitSVG(s)}<span>${SUIT_NAME[s]}</span></button>`).join("")}</div>`)
    .then(v => v && window._suitPicked);
}
document.addEventListener("click", e => { const b = e.target.closest("[data-s]"); if (b) window._suitPicked = b.dataset.s; }, true);

// ------------------------------------------------------------ действия
Object.assign(ACT, {
  "bj-tab": el => { bjTab = el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); bjTabDraw(); },
  "bj-deal": () => bjAct("deal"),
  bj: el => bjAct(el.dataset.v),
  "tb-maxp": el => { TB.maxp = +el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); },
  "tb-noinv": () => { TB.invite = []; tbInvDraw(); },
  "tb-pick": async () => {
    const fr = await api("friends");
    openSheet(`<h2 class="gtitle">Кого позвать?</h2>${fr.friends.length ? `<div class="box">${fr.friends.map(u => `<div class="row tap" data-act="tb-inv-add" data-k="${reg(u)}">${avaHTML(u, 40, { lv: true })}<div class="grow"><div class="t">${esc(u.name)}</div><div class="s">${u.level} уровень</div></div>${ic("plus", "dim")}</div>`).join("")}</div>`
      : emptyHTML("users", "Друзей пока нет — добавь их в разделе «Друзья»")}`);
  },
  "tb-inv-add": el => { const u = REG.get(el.dataset.k); if (!TB.invite.some(x => x.id === u.id)) TB.invite.push(u); TB.maxp = Math.max(TB.maxp, Math.min(4, TB.invite.length + 1)); closeSheet(); H.sel(); tbInvDraw(); },
  "tb-kind": el => {
    TB.kind = el.dataset.v; H.sel();
    const s = topSheet(), g = s._tables || "21";
    const body = s.querySelector("#tb-body") || s.querySelector("#bj-body");
    if (body) { body.innerHTML = tablesHTML(g); loadTables(g); }
  },
  "tb-new": async el => {
    const game = el.dataset.g, base = { game, maxp: TB.maxp, public: !TB.invite.length, invite: TB.invite.map(u => u.id) };
    const create = async extra => {
      const r = await post("rooms", { ...base, ...extra });
      setStars(r.stars); H.ok(); TB.invite = [];
      openRoom(r.id);
    };
    if (TB.kind === "gifts") return pickGifts("Подарки в банк стола", { max: 10 }, gs => create({ kind: "gifts", gifts: gs.map(g => g.id) }));
    const stake = betVal("tb-amt"); if (stake > ME.stars) return toast("Не хватает звёзд ⭐");
    TB.stake = stake;
    create({ stake });
  },
  "tb-join": async el => {
    const id = +el.dataset.id;
    const join = async extra => { const v = await post(`rooms/${id}/join`, extra || {}); setStars(v.stars); H.ok(); openRoom(id); };
    if (el.dataset.kind === "gifts") return pickGifts("Твои подарки в банк", { max: 10, min: Math.ceil(+el.dataset.stake * .8) }, gs => join({ gifts: gs.map(g => g.id) }));
    join();
  },
  room: el => openRoom(+el.dataset.id),
  rm: async el => {
    const a = el.dataset.v;
    if (a === "leave" && ROOM.status === "playing" && !await confirmM("Сдаться?", "Ставка останется в банке, а ты выйдешь из игры.", "Сдаться")) return;
    await roomPost(a);
    if (a === "leave" || a === "cancel") { toast(a === "cancel" ? "Стол отменён, ставки вернулись" : "Ты вышел из-за стола"); closeSheet(); }
  },
  "rm-act": el => roomPost("act", { a: el.dataset.v }).then(() => H.sel()),
  "rm-play": async el => {
    const card = el.dataset.card;
    if (!ROOM.playable.includes(card)) {
      H.err(); el.classList.remove("nope"); void el.offsetWidth; el.classList.add("nope");
      const top = ROOM.top, r = x => x === "T" ? "10" : x;
      return toast(ROOM.must ? `Шестёрку кроют ${SUIT_NAME[ROOM.suit].toLowerCase()}, шестёркой или дамой` : `Нужна масть «${SUIT_NAME[ROOM.suit]}», достоинство ${r(top[0])} или дама`);
    }
    let suit = null;
    if (card[0] === "Q") { suit = await pickSuit(); if (!suit) return; }
    await roomPost("act", { a: "play", card, suit }); H.imp("light");
  },
  "rm-link": () => {
    const url = `https://t.me/share/url?url=${enc(ROOM.link)}&text=${enc(`Садись со мной за «${ROOM.title}» 🃏`)}`;
    if (inTg) tg.openTelegramLink(url); else { navigator.clipboard?.writeText(ROOM.link); toast("Ссылка скопирована"); }
  },
  "rm-inv": async () => {
    const fr = await api("friends");
    openSheet(`<h2 class="gtitle">За стол</h2><button class="btn" style="margin-bottom:12px" data-act="rm-link">${ic("send")}Отправить ссылку в чат</button>${fr.friends.length ? `<div class="box">${fr.friends.map(u => `<div class="row tap" data-act="rm-share" data-id="${u.id}">${avaHTML(u, 40)}<div class="grow"><div class="t">${esc(u.name)}</div></div>${ic("send", "dim")}</div>`).join("")}</div>` : emptyHTML("users", "Друзей пока нет")}`);
  },
  "rm-share": async el => { await post(`rooms/${ROOM.id}/invite`, { to: +el.dataset.id }).catch(() => {}); closeSheet(); toast("Приглашение отправлено", "ok"); },
  "rm-again": () => { const g = ROOM.game; closeSheet(); if (g === "101") { if (!SHEETS.some(s => s._tables)) openTables("101"); } else if (!SHEETS.some(s => s._bj || s._tables)) openTables("21"); },
});

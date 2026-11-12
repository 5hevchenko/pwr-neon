"use strict";
// ============================================================
//  Битва кейсов: 2–4 игрока открывают одинаковые кейсы, у кого сумма больше — забирает всё
// ============================================================
ICONS.bot = '<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 4v4M9 13h.01M15 13h.01M9 17h6"/><circle cx="12" cy="3" r="1"/>';
GAMES.push({ id: "battle", t: "Битва кейсов", s: "Открывайте кейсы против соперников — победитель забирает все подарки", img: "Loot Bag", k: ["#ff4f6d", "#2a0b3d"], chips: ["PvP", "1×1 · 4 игрока"] });
WIDE_GAMES.add("battle");
GAME_OPEN.battle = () => openBattles();
GAME_SECTIONS[0][2].splice(1, 0, "battle");
GAME_NAMES.battle = ["swap", "Битва кейсов"];

let BT = null, btPoll = null, BTN = { cid: null, rounds: 1, slots: 2 };
const btCost = b => b.cost;
const btSlotHTML = (p, i) => p ? `<div class="bt-pl${p.bot ? " bot" : ""}">${p.bot ? `<span class="bt-botava">${ic("bot")}</span>` : avaHTML(p, 30)}</div>`
  : `<div class="bt-pl empty"><span>?</span></div>`;

async function openBattles() {
  const el = openSheet(`<div class="bt-hero"><div class="bt-hero-bg"></div><span class="bt-swords">${ic("swap")}</span><h2>Битва кейсов</h2>
      <span>Открывайте одинаковые кейсы — у кого дороже, тот забирает <b>все</b> подарки</span>
      <button class="btn gold" data-act="bt-new" style="margin-top:12px">${ic("plus")}Создать битву</button></div>
    <div id="bt-list">${emptyHTML("hourglass", "Загружаем…")}</div>`, "bt-s");
  el._onClose = () => { clearInterval(btPoll); btPoll = null; };
  await btLoad();
  clearInterval(btPoll); btPoll = setInterval(() => { if (SHEETS.some(s => s.classList.contains("bt-s"))) bgOff() || btLoad(); else { clearInterval(btPoll); btPoll = null; } }, 3000);
}
async function btLoad() {
  try { BT = await api("battles"); } catch (e) { return; }
  const box = $("#bt-list"); if (!box) return;
  const card = b => {
    const host = b.host === ME.id, cs = CASE_COL[b.cid] || ["#555", "#222"];
    return `<div class="bt-card" style="--k1:${cs[0]};--k2:${cs[1]}" data-act="bt-open" data-id="${b.id}">
      <div class="bt-case"><img src="${A.orig(b.case.cover, 128)}" alt=""><b>${b.rounds > 1 ? "×" + b.rounds : ""}</b></div>
      <div class="grow"><div class="t">${esc(b.case.title)}</div><div class="bt-slots">${b.players.map(btSlotHTML).join('<i class="vs">vs</i>')}</div></div>
      <div class="bt-cost"><span>${host ? "твоя" : "вход"}</span><b>⭐ ${short(b.cost)}</b></div></div>`;
  };
  box.innerHTML = `
    ${BT.open.length ? `<div class="sec-t">${ic("flame")}Открытые битвы · ${BT.open.length}</div><div class="bt-list">${BT.open.map(card).join("")}</div>`
      : `<div class="empty" data-i="swap"><span class="eic">${ic("swap")}</span><span class="etx"><b>Открытых битв нет</b>Создай свою — соперник придёт, или позови бота</span></div>`}
    ${BT.mine.length ? `<div class="sec-t">${ic("clock")}Мои последние</div><div class="box">${BT.mine.map(b => {
      const won = b.result && b.result.winner === ME.id;
      return `<div class="row tap" data-act="bt-open" data-id="${b.id}"><img class="spi" style="width:36px;height:36px;margin:0" src="${A.orig(b.case.cover, 64)}" alt="">
        <div class="grow"><div class="t">${esc(b.case.title)} ${b.rounds > 1 ? "×" + b.rounds : ""}</div><div class="s">${b.slots} игрока · вход ⭐ ${short(b.cost)}</div></div>
        <b class="${won ? "tw" : "tl"}">${won ? "+⭐ " + short(b.result.total) : "−⭐ " + short(b.cost)}</b></div>`;
    }).join("")}</div>` : ""}
    <div class="disc">Свободные места можно отдать боту — он открывает те же кейсы. Если победишь бота, его подарки тоже твои. Не нашлись соперники за 30 минут — ставка вернётся.</div>`;
  starify(box);
}

// ------------------------------------------------------------ создание
function btNewSheet() {
  if (!BT) return;
  BTN.cid = BTN.cid && BT.cases.some(c => c.id === BTN.cid) ? BTN.cid : (BT.cases.find(c => c.level <= ME.lv.level) || BT.cases[0]).id;
  const el = openSheet(`<h2 class="gtitle">Новая битва</h2>
    <div class="sec-t" style="margin-top:0">Кейс</div>
    <div class="bt-pick" id="bt-pick">${BT.cases.map(c => { const cs = CASE_COL[c.id] || ["#555", "#222"];
      return `<button data-act="btn-case" data-v="${c.id}" class="${c.id === BTN.cid ? "on" : ""}" style="--k1:${cs[0]};--k2:${cs[1]}"><img src="${A.orig(c.cover, 96)}" alt=""><b>${esc(c.title)}</b><span>⭐ ${short(c.price)}</span></button>`; }).join("")}</div>
    <div class="sec-t">Раундов</div><div class="seg" id="bt-r">${BT.rounds.map(n => `<button data-act="btn-r" data-v="${n}" class="${BTN.rounds === n ? "on" : ""}">${n}</button>`).join("")}</div>
    <div class="sec-t" style="margin-top:4px">Игроков</div><div class="seg" id="bt-s">${BT.slots.map(n => `<button data-act="btn-s" data-v="${n}" class="${BTN.slots === n ? "on" : ""}">${n === 2 ? "1 × 1" : n + " игрока"}</button>`).join("")}</div>
    <button class="btn gold cta" data-act="btn-go" id="bt-go" style="margin-top:14px"></button>
    <div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Каждый открывает выбранный кейс столько раз, сколько раундов. Победитель забирает подарки всех.</div>`);
  btNewText(); starify(el);
}
function btNewText() {
  const c = BT.cases.find(x => x.id === BTN.cid), b = $("#bt-go"); if (!c || !b) return;
  b.innerHTML = `${ic("swap")}Создать · ⭐ ${fmt(c.price * BTN.rounds)}`; starify(b);
}

// ------------------------------------------------------------ экран битвы
async function openBattle(id) {
  const el = openSheet(emptyHTML("hourglass", "Загружаем битву…"), "bt-v");
  el._bid = id;
  const draw = async () => {
    let b; try { b = await api("battles/" + id); } catch (e) { return; }
    if (!el.isConnected) return;
    if (b.status === "done" && el._shown !== b.id) { el._shown = b.id; return btReveal(el, b); }
    if (b.status === "done") return;
    const host = b.host === ME.id, inIt = b.players.some(p => p && p.id === ME.id);
    replaceSheet(el, btArena(b, false) + `<div class="bt-act">${b.status === "cancelled" ? `<div class="hint" style="text-align:center">Битва отменена, ставки возвращены</div>`
      : host ? `<div class="btns"><button class="btn gold" style="flex:2" data-act="bt-bot" data-id="${b.id}">${ic("users")}Позвать бота</button><button class="btn ghost" style="flex:1" data-act="bt-cancel" data-id="${b.id}">Отменить</button></div>
        <div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Ждём соперников… Боты займут все свободные места, и битва начнётся сразу.</div>`
      : inIt ? `<div class="hint" style="text-align:center">Ты в битве — ждём остальных</div>`
      : `<button class="btn gold cta" data-act="bt-join" data-id="${b.id}">${ic("swap")}Вступить · ⭐ ${fmt(b.cost)}</button>`}</div>`);
    starify(el);
  };
  el._draw = draw;
  await draw();
  const t = setInterval(() => { if (!el.isConnected) return clearInterval(t); if (!el._revealing && el._shown == null) draw(); }, 2000);
}
function btArena(b, reveal) {
  const n = b.slots, cs = CASE_COL[b.cid] || ["#555", "#222"];
  return `<div class="bt-head" style="--k1:${cs[0]};--k2:${cs[1]}"><img src="${A.orig(b.case.cover, 128)}" alt=""><div><b>${esc(b.case.title)}</b><span>${b.rounds} ${plural(b.rounds, ["раунд", "раунда", "раундов"])} · вход ⭐ ${fmt(b.cost)}</span></div>
      <div class="bt-pot"><span>Банк</span><b id="bt-pot">⭐ ${reveal ? "0" : short(b.cost * n)}</b></div></div>
    <div class="bt-arena n${n}">${b.players.map((p, i) => `<div class="bt-col" id="bt-c${i}">
        <div class="bt-who">${p ? (p.bot ? `<span class="bt-botava big">${ic("bot")}</span>` : avaHTML(p, 42)) : `<span class="bt-wait"><i></i></span>`}
          <b>${p ? esc(p.bot ? "Бот" : p.name) : "Ждём…"}</b><em id="bt-t${i}">⭐ 0</em></div>
        <div class="bt-rounds">${Array.from({ length: b.rounds }, (_, r) => `<div class="bt-cell" id="bt-${i}-${r}"></div>`).join("")}</div>
      </div>${i < n - 1 ? `<i class="bt-vs">VS</i>` : ""}`).join("")}</div>`;
}
async function btReveal(el, b) {
  el._revealing = true;
  replaceSheet(el, btArena(b, true) + `<div class="bt-act" id="bt-res"></div>`);
  starify(el);
  if (!CASES.length) CASES = await api("cases").catch(() => []);
  const pool = ((CASES.find(c => c.id === b.cid) || {}).items || []).map(x => x.col);
  const R = b.result, totals = b.players.map(() => 0);
  let pot = 0;
  for (let r = 0; r < b.rounds; r++) {
    if (!el.isConnected) return;
    await Promise.all(b.players.map(async (_, i) => {
      const cell = el.querySelector(`#bt-${i}-${r}`), g = R.drops[i][r]; if (!cell) return;
      // мини-рулетка: вертикальная лента случайных подарков кейса → выпавший
      const items = Array.from({ length: 14 }, () => pool[Math.random() * pool.length | 0] || g.col);
      cell.innerHTML = `<div class="bt-spin"><div class="bt-strip">${items.map(c => `<img src="${A.orig(c, 64)}" alt="">`).join("")}<img src="${A.model(g.col, g.model, 64)}" alt=""></div></div>`;
      const strip = cell.querySelector(".bt-strip"), H0 = cell.clientHeight;
      strip.style.transform = "translateY(0)"; void strip.offsetWidth;
      strip.style.transition = `transform ${1.5 + i * .12}s cubic-bezier(.15,.8,.25,1)`;
      strip.style.transform = `translateY(${-14 * H0}px)`;
      await sleep((1.5 + i * .12) * 1000);
      if (!cell.isConnected) return;
      cell.innerHTML = `<div class="bt-drop t-${tier(g)}">${giftHTML(g, { lite: true, plain: true })}<span>⭐ ${short(g.value)}</span></div>`;
      totals[i] += g.value; pot += g.value;
      const t = el.querySelector("#bt-t" + i); if (t) { t.textContent = "⭐ " + fmt(totals[i]); t.classList.remove("pop"); void t.offsetWidth; t.classList.add("pop"); }
      const p = el.querySelector("#bt-pot"); if (p) p.textContent = "⭐ " + short(pot);
      starify(cell);
    }));
    H.imp("medium");
    // лидер раунда подсвечен
    const lead = totals.indexOf(Math.max(...totals));
    el.querySelectorAll(".bt-col").forEach((c, i) => c.classList.toggle("lead", i === lead));
    await sleep(450);
  }
  if (!el.isConnected) return;
  const ws = R.winSlot, me = R.winner === ME.id;
  el.querySelectorAll(".bt-col").forEach((c, i) => { c.classList.remove("lead"); c.classList.add(i === ws ? "win" : "lose"); });
  const winCol = el.querySelector("#bt-c" + ws);
  if (winCol) winCol.querySelector(".bt-who").insertAdjacentHTML("afterbegin", `<span class="bt-crown">${ic("crown")}</span>`);
  const res = el.querySelector("#bt-res");
  const wp = b.players[ws];
  res.innerHTML = `<div class="bt-final ${me ? "win" : "lose"}"><b>${me ? "Победа! Все подарки твои" : wp && wp.bot ? "Победил бот" : `Победил ${esc(wp ? wp.name : "соперник")}`}</b>
      <span>Банк битвы ⭐ ${fmt(R.total)}</span></div>
    <div class="btns"><button class="btn ghost" data-act="bt-again" data-cid="${b.cid}" data-r="${b.rounds}" data-s="${b.slots}">${ic("refresh")}Ещё раз</button>${me ? `<button class="btn gold" data-act="tab-inv">${ic("bag")}В сумку</button>` : ""}</div>`;
  starify(res);
  el._revealing = false;
  if (me) { H.ok(); burstAt(winCol); if (R.total >= b.cost * 2.5) bigWin(R.total, R.total / b.cost); } else H.err();
  loadMe();
}
Object.assign(ACT, {
  "bt-new": () => btNewSheet(),
  "btn-case": el => { BTN.cid = el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); btNewText(); },
  "btn-r": el => { BTN.rounds = +el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); btNewText(); },
  "btn-s": el => { BTN.slots = +el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); },
  "btn-go": async () => {
    const c = BT.cases.find(x => x.id === BTN.cid);
    if (c.price * BTN.rounds > ME.stars) return toast("Не хватает звёзд ⭐");
    const r = await post("battles", { cid: BTN.cid, rounds: BTN.rounds, slots: BTN.slots }); setStars(r.stars); H.ok();
    closeSheet(); btLoad(); openBattle(r.id);
  },
  "bt-open": el => openBattle(+el.dataset.id),
  "bt-join": async el => {
    const r = await post(`battles/${el.dataset.id}/join`); setStars(r.stars); H.imp("heavy");
    const s = topSheet(); if (s && s._draw) s._draw(); btLoad();
  },
  "bt-bot": async el => { await post(`battles/${el.dataset.id}/bot`); H.imp("heavy"); const s = topSheet(); if (s && s._draw) s._draw(); btLoad(); },
  "bt-cancel": async el => {
    if (!await confirmM("Отменить битву?", "Ставка вернётся на баланс.", "Отменить")) return;
    const r = await post(`battles/${el.dataset.id}/cancel`); setStars(r.stars); toast("Битва отменена"); closeSheet(); btLoad();
  },
  "bt-again": el => { BTN = { cid: el.dataset.cid, rounds: +el.dataset.r, slots: +el.dataset.s }; closeSheet(); btNewSheet(); },
  "tab-inv": () => { while (SHEETS.length) closeSheet(); setTab("inv"); },
});

"use strict";
// ============================================================
//  Дуэли 1 на 1: монетка и кости
// ============================================================
const DUEL = { game: "coin", to: null };
let DGAMES = { coin: ["coins", "Монетка", "50/50 — кому повезёт"], dice: ["box", "Кости", "У кого сумма двух кубиков больше"] };

async function loadDuels() { try { return await api("duels"); } catch (e) { return null; } }
function duelsHTML(d) {
  if (!d || !d.incoming.length) return "";
  return `<div class="sec-t">${ic("target")}Тебя вызывают на дуэль</div>${d.incoming.map(duelCard).join("")}`;
}
function duelCard(x) {
  const mineA = x.a.id === ME.id, other = mineA ? x.b : x.a, [gi, gt] = DGAMES[x.game];
  let right = "", res = "";
  if (x.status === "open") {
    if (mineA) right = `<button class="btn sm ghost" data-act="duel-cancel" data-id="${x.id}">Отменить</button>`;
    else right = `${x.b ? `<button class="ibtn red" data-act="duel-dec" data-id="${x.id}">${ic("x")}</button>` : ""}<button class="btn sm green" data-act="duel-acc" data-id="${x.id}">Принять</button>`;
  } else {
    const won = x.winner === ME.id;
    res = x.winner == null ? `<span class="hint">ничья</span>` : `<span class="${won ? "tw" : "tl"}">${won ? "+⭐ " + short(x.pay - x.stake) : "−⭐ " + short(x.stake)}</span>`;
  }
  const who = other ? avaHTML(other, 36) : `<span class="dany">${ic("users")}</span>`;
  return `<div class="dcard"><div class="dleft" ${other ? `data-act="profile" data-id="${other.id}"` : ""}>${who}<div class="grow"><div class="t">${other ? esc(other.name) : "Любой игрок"}</div>
    <div class="s"><span class="dgame">${ic(gi)}${gt}</span> · ⭐ ${fmt(x.stake)}</div></div></div><div class="dright">${res}${right}</div></div>`;
}

async function openDuels(to = null) {
  H.imp("light");
  DUEL.to = to ? await api("user/" + to).catch(() => null) : null;
  const el = openSheet(`${gameHead("Light Sword", "Дуэли", "Играй 1 на 1 — победитель забирает банк", "duel")}
    <div class="dnew">
      <div class="seg" id="d-game">${Object.entries(DGAMES).map(([k, [i, t]]) => `<button data-act="duel-game" data-v="${k}" class="${DUEL.game === k ? "on" : ""}">${ic(i)}${t}</button>`).join("")}</div>
      <div class="dsub" id="d-sub">${DGAMES[DUEL.game][2]}</div>
      <div class="dopp" id="d-opp"></div>
      ${betHTML("d-amt", 500)}
      <button class="btn cta gold" data-act="duel-go">${ic("target")}Бросить вызов</button>

    </div>
    <div id="d-lists">${emptyHTML("hourglass", "Загружаем…")}</div>`, "duels-s");
  el._duels = true;
  drawOpp();
  fillDuels(el);
}
function drawOpp() {
  const o = $("#d-opp"); if (!o) return;
  o.innerHTML = DUEL.to
    ? `<div class="row" style="padding:0">${avaHTML(DUEL.to, 36, { lv: true })}<div class="grow"><div class="t">${esc(DUEL.to.name)}</div><div class="s">личный вызов</div></div><button class="ibtn" data-act="duel-any">${ic("x")}</button></div>`
    : `<div class="row" style="padding:0"><span class="dany">${ic("users")}</span><div class="grow"><div class="t">Открытый вызов</div><div class="s">примет любой игрок</div></div><button class="btn sm ghost" data-act="duel-pick">${ic("userPlus")}Друг</button></div>`;
}
async function fillDuels(el) {
  const d = await loadDuels(); if (!d || !el.isConnected) return;
  const sec = (title, icon, list, empty) => `<div class="sec-t">${ic(icon)}${title}</div>` + (list.length ? list.map(duelCard).join("") : `<div class="hint dempty">${empty}</div>`);
  el.querySelector("#d-lists").innerHTML =
    (d.incoming.length ? sec("Вызывают тебя", "target", d.incoming, "") : "") +
    sec("Открытые вызовы", "users", d.lobby, "Пока никто не бросил открытый вызов — будь первым") +
    (d.mine.length ? sec("Твои вызовы", "hourglass", d.mine, "") : "") +
    (d.history.length ? sec("История", "clock", d.history, "") : "");
}
async function refreshDuels() { for (const s of SHEETS) if (s._duels) fillDuels(s); refreshFriends(); }

// ------------------------------------------------------------ анимация дуэли
const DIE = n => `<div class="die">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map(i => `<i class="${({ 1: [5], 2: [1, 9], 3: [1, 5, 9], 4: [1, 3, 7, 9], 5: [1, 3, 5, 7, 9], 6: [1, 3, 4, 6, 7, 9] })[n].includes(i) ? "on" : ""}"></i>`).join("")}</div>`;
async function playDuel(r) {
  const A = r.a, B = r.b, coin = r.game === "coin";
  const el = openSheet(`<div class="arena">
      <div class="fighter" id="f-a">${avaHTML(A, 76, { lv: true })}<b>${esc(A.name)}</b><div class="dice" id="d-a"></div></div>
      <div class="vs">VS</div>
      <div class="fighter" id="f-b">${avaHTML(B, 76, { lv: true })}<b>${esc(B.name)}</b><div class="dice" id="d-b"></div></div>
    </div>
    <div class="bank">Банк <b>⭐ ${fmt(r.stake * 2)}</b></div>
    ${coin ? `<div class="coin3d"><div class="coin" id="coin"><div class="face fa">${avaHTML(A, 120)}</div><div class="face fb">${avaHTML(B, 120)}</div></div></div>` : `<div class="dicebox" id="dbox"></div>`}
    <div class="dres" id="dres">&nbsp;</div>
    <div class="btns"><button class="btn ghost" data-act="close">Закрыть</button><button class="btn" data-act="duel-again">${ic("target")}Ещё дуэль</button></div>`, "arena-s");
  await sleep(400);
  if (coin) {
    const side = r.ra[0], c = $("#coin");
    c.style.transition = "transform 2.6s cubic-bezier(.15,.75,.25,1)";
    c.style.transform = `rotateY(${360 * 7 + (side ? 180 : 0)}deg)`;
    for (let i = 0; i < 14; i++) { await sleep(150 + i * 10); H.sel(); }
    await sleep(500);
  } else {
    const da = $("#d-a"), db_ = $("#d-b");
    for (let i = 0; i < 16; i++) {
      da.innerHTML = DIE(1 + Math.random() * 6 | 0) + DIE(1 + Math.random() * 6 | 0);
      db_.innerHTML = DIE(1 + Math.random() * 6 | 0) + DIE(1 + Math.random() * 6 | 0);
      H.sel(); await sleep(70 + i * 8);
    }
    da.innerHTML = r.ra.map(DIE).join("") + `<span>${r.ra[0] + r.ra[1]}</span>`;
    db_.innerHTML = r.rb.map(DIE).join("") + `<span>${r.rb[0] + r.rb[1]}</span>`;
    await sleep(300);
  }
  if (!el.isConnected) return;
  const won = r.winner === ME.id, winA = r.winner === A.id;
  $(winA ? "#f-a" : "#f-b").classList.add("winner");
  $(winA ? "#f-b" : "#f-a").classList.add("loser");
  const res = $("#dres");
  res.className = "dres " + (won ? "win" : "lose");
  res.textContent = won ? `Победа! +⭐ ${fmt(r.pay)}` : "Поражение";
  if (won) { H.ok(); burstAt(res); } else H.err();
  setStars(r.stars); loadMe(); refreshDuels();
}

// ------------------------------------------------------------ действия
Object.assign(ACT, {
  "duel-new": el => openDuels(+el.dataset.id),
  "duel-game": el => { DUEL.game = el.dataset.v; H.sel(); document.querySelectorAll("#d-game button").forEach(b => b.classList.toggle("on", b === el)); $("#d-sub").textContent = DGAMES[DUEL.game][2]; },
  "duel-any": () => { DUEL.to = null; H.sel(); drawOpp(); },
  "duel-pick": async () => {
    const fr = await api("friends");
    openSheet(`<h2 class="gtitle">Кого вызываем?</h2>${fr.friends.length ? `<div class="box">${fr.friends.map(u => `<div class="row tap" data-act="duel-to" data-id="${u.id}">${avaHTML(u, 40, { lv: true })}<div class="grow"><div class="t">${esc(u.name)}</div><div class="s">${u.level} уровень</div></div>${ic("chev", "dim")}</div>`).join("")}</div>`
      : emptyHTML("users", "Друзей пока нет — добавь их в разделе «Друзья»")}`);
  },
  "duel-to": async el => { DUEL.to = await api("user/" + el.dataset.id); closeSheet(); H.sel(); drawOpp(); },
  "duel-go": async () => {
    const stake = betVal("d-amt");
    if (stake > ME.stars) return toast("Не хватает звёзд ⭐");
    const r = await post("duels", { game: DUEL.game, stake, to: DUEL.to ? DUEL.to.id : null });
    setStars(r.stars); H.ok(); toast(DUEL.to ? `Вызов отправлен: ${DUEL.to.name}` : "Открытый вызов создан");
    refreshDuels();
  },
  "duel-acc": async el => {
    const r0 = await post(`duels/${el.dataset.id}/accept`);
    playDuel(r0);
  },
  "duel-dec": async el => { await post(`duels/${el.dataset.id}/decline`); H.sel(); toast("Вызов отклонён"); loadMe(); refreshDuels(); },
  "duel-cancel": async el => { await post(`duels/${el.dataset.id}/cancel`); H.sel(); toast("Вызов отменён, ставка вернулась"); loadMe(); refreshDuels(); },
  "duel-again": () => { closeSheet(); if (!SHEETS.some(s => s._duels)) openDuels(); },
});

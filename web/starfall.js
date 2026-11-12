"use strict";
// ============================================================
//  «Звездопад» — общая шкала: игроки вкладывают звёзды, при заполнении один получает подарок от 50 000 ⭐
// ============================================================
GAMES.push({ id: "starfall", t: "Звездопад", s: "Заполните шкалу вместе — один заберёт подарок от ⭐ 50 000", img: "Precious Peach", k: ["#7c6bff", "#140c3a"], chips: ["общая шкала", "подарок от 50K"] });
WIDE_GAMES.add("starfall");
GAME_OPEN.starfall = () => openStarfall();
GAME_SECTIONS[0][2].splice(2, 0, "starfall");
GAME_NAMES.starfall = ["sparkles", "Звездопад"];

let SF = null, sfPoll = null, sfRound = 0;
async function openStarfall() {
  const el = openSheet(`<div class="sfhero"><div class="sfsky"></div>
      <div class="sfprize" id="sf-prize"></div>
      <h2>Звездопад</h2><span id="sf-sub">Заполните шкалу вместе — один из участников заберёт подарок</span>
      <div class="sfbar"><i id="sf-fill"><em>${ic("sparkles")}</em></i><div class="sfticks">${"<s></s>".repeat(9)}</div></div>
      <div class="sfnums"><b id="sf-pct">0%</b><span id="sf-txt">—</span></div></div>
    <div class="dginfo"><div><span>Твой вклад</span><b id="sf-mine">—</b></div><div><span>Твой шанс</span><b id="sf-ch">—</b></div></div>
    <div class="betp">${betHTML("sf-amt", 500)}<button class="btn cta gold" data-act="sf-bet" id="sf-btn">Вложить</button></div>
    <div class="sec-t">Участники раунда <span id="sf-n"></span></div><div class="box" id="sf-top"></div>
    <div class="sec-t">Последние победители</div><div class="box" id="sf-last"></div>
    <details class="rules" style="margin-top:12px"><summary>${ic("award")}Как играть</summary><div id="sf-rules"></div></details>`, "sf-s");
  el._onClose = () => { clearInterval(sfPoll); sfPoll = null; };
  await sfLoad(true);
  clearInterval(sfPoll); sfPoll = setInterval(() => bgOff() || sfLoad(), 4000);
}
async function sfLoad(first) {
  const prev = SF;
  try { SF = await api("starfall"); } catch (e) { return; }
  if (!$("#sf-fill")) return;
  // раунд закрылся, пока смотрели — показываем, кто забрал
  if (prev && prev.id !== SF.id && SF.last[0] && SF.last[0].id === prev.id && prev.mine) sfWinner(SF.last[0], prev.mine);
  sfPaint(first);
}
function sfPaint(first) {
  const p = Math.min(100, SF.filled / SF.target * 100);
  $("#sf-fill").style.width = p + "%";
  $("#sf-txt").textContent = `⭐ ${fmt(SF.filled)} из ${fmt(SF.target)} · осталось ⭐ ${fmt(Math.max(0, SF.target - SF.filled))}`;
  $("#sf-pct").textContent = Math.floor(p) + "%";
  $("#sf-fill").classList.toggle("hot", p >= 80);
  $("#sf-mine").textContent = SF.mine ? "⭐ " + fmt(SF.mine) : "—";
  $("#sf-ch").textContent = SF.mine ? SF.chance.toString().replace(".", ",") + "%" : "—";
  $("#sf-n").textContent = SF.players ? `· ${SF.players}` : "";
  if (first || !$("#sf-prize").children.length) {
    $("#sf-prize").innerHTML = SF.prizes.map((g, i) => `<img src="${A.model(g.col, g.model, 256)}" style="--i:${i}" alt="">`).join("") + `<em>от ⭐ ${short(SF.prizeMin)}</em>`;
    $("#sf-rules").innerHTML = `Каждый вкладывает звёзды в общую шкалу на ⭐ ${fmt(SF.target)}. Когда она заполняется, один из участников получает случайный дорогой подарок ценностью ⭐ ${short(SF.prizeMin)}–${short(SF.prizeMax)} (Precious Peach, Mighty Arm, кубки…).
      Шанс выиграть — твоя доля в шкале. В одном раунде можно вложить до ⭐ ${fmt(SF.cap)}. Новый раунд начинается сразу.`;
  }
  $("#sf-top").innerHTML = SF.top.length ? SF.top.map(u => `<div class="row tap" data-act="profile" data-id="${u.id}">${avaHTML(u, 34)}<div class="grow"><div class="t">${esc(u.name)}${u.id === ME.id ? " <span class='pill'>ты</span>" : ""}</div>
    <div class="s">⭐ ${fmt(u.amount)}</div></div><b class="num">${u.chance.toString().replace(".", ",")}%</b></div>`).join("") : `<div class="hint" style="padding:14px">Пока никто не вложил — будь первым</div>`;
  $("#sf-last").innerHTML = SF.last.length ? SF.last.map(x => `<div class="row tap" data-act="profile" data-id="${x.user.id}">${x.gift ? `<img class="spi" style="width:38px;height:38px;margin:0" src="${A.model(x.gift.col, x.gift.model, 64)}" alt="">` : ""}
    <div class="grow"><div class="t">${esc(x.user.name)}</div><div class="s">${x.gift ? esc(x.gift.col) + " · ⭐ " + fmt(x.gift.value) : ""}</div></div></div>`).join("") : `<div class="hint" style="padding:14px">Ещё никто не выигрывал</div>`;
  starify($("#sf-txt"));
}
async function sfWinner(x, stake) {
  const me = x.user.id === ME.id;
  if (me && x.gift) { H.ok(); await bigWin(x.gift.value, x.gift.value / Math.max(1, stake), 75, { gift: x.gift.id }); }
  else modal(`<h3>🌠 Шкала заполнена!</h3><p class="hint" style="margin:0 0 12px"><b>${esc(x.user.name)}</b> забирает ${x.gift ? esc(x.gift.col) + " · ⭐ " + fmt(x.gift.value) : "подарок"}. Новый раунд уже идёт.</p><button class="btn gold" data-m="ok">Ещё раз</button>`);
}
async function sfBet() {
  const amount = betVal("sf-amt");
  if (amount > ME.stars) return toast("Не хватает звёзд ⭐");
  const btn = $("#sf-btn"); btn.disabled = true;
  try {
    const r = await post("starfall/bet", { amount });
    setStars(r.stars); H.imp("medium"); coinShower($("#sf-fill"), 18);
    toast(`+⭐ ${fmt(r.added)} в шкалу`, "ok");
    await sfLoad();   // если шкала заполнилась этим вкладом — sfLoad сам покажет победителя
    afterLevelUp(r.levelup);
  } catch (e) {} finally { if (btn.isConnected) btn.disabled = false; }
}
Object.assign(ACT, { "sf-bet": () => sfBet() });

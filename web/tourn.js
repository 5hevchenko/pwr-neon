"use strict";
// ============================================================
//  Турниры (каждые 3 дня, tourn.py): баннер в «Играх» и экран с таблицами лидеров
// ============================================================
let TR = null, trTab = 0;
const _rgTr = renderGames;
renderGames = function () {
  _rgTr();
  const v = $("#v-games"); if (!v || v.querySelector(".tr-bar")) return;
  api("tournaments").then(d => {
    TR = d; if (!v.isConnected || v.querySelector(".tr-bar")) return;
    const left = Math.max(0, d.weekEnds - Date.now() / 1000), dd = Math.floor(left / 86400), hh = Math.floor(left % 86400 / 3600);
    const bar = `<button class="tr-bar" data-act="tourn"><span class="tr-cup">${ic("trophy")}</span><div class="grow"><b>Турниры</b>
      <span>${d.items.map(i => esc(i.title)).join(" · ")} — фонд ⭐ ${short(d.items[0].pool)} в каждом</span></div><em>${dd ? dd + " д " : ""}${hh} ч</em>${ic("chev")}</button>`;
    const anchor = v.querySelector(".prib, .evrib");
    anchor ? anchor.insertAdjacentHTML("afterend", bar) : v.insertAdjacentHTML("afterbegin", bar);
  }).catch(() => {});
};
async function openTourn() {
  const el = openSheet(emptyHTML("hourglass", "Загружаем турниры…"), "tr-s");
  TR = await api("tournaments").catch(() => TR); if (!TR || !el.isConnected) return;
  trPaint(el);
}
function trPaint(el) {
  const t = TR.items[trTab], left = Math.max(0, TR.weekEnds - Date.now() / 1000);
  const top3 = [t.top[1], t.top[0], t.top[2]];
  replaceSheet(el, `<div class="tr-hero"><span class="tr-cup big">${ic("trophy")}</span><h2>Турниры</h2>
      <span>Кто больше всех заработает в игре за ${TR.days || 3} ${plural(TR.days || 3, ["день", "дня", "дней"])} — забирает приз. Участвуют все, взноса нет.</span>
      <div class="tr-time">до итогов ${Math.floor(left / 86400)} д ${Math.floor(left % 86400 / 3600)} ч</div></div>
    <div class="seg">${TR.items.map((x, i) => `<button data-act="tr-tab" data-v="${i}" class="${i === trTab ? "on" : ""}">${esc(x.title)}</button>`).join("")}</div>
    <div class="tr-pool"><div><span>Призовой фонд</span><b>⭐ ${fmt(t.pool)}</b></div><div class="tr-shares">${TR.shares.map((s, i) => `<i><b>${i + 1}</b>⭐ ${short(t.pool * s)}</i>`).join("")}</div></div>
    ${t.top.length ? `<div class="podium">${top3.map((r, i) => r ? `<div class="p${[2, 1, 3][i]}" data-act="profile" data-id="${r.id}">${avaHTML(r, 54, { lv: true })}
        <div class="nm">${nameHTML(r)}</div><div class="sc">+⭐ ${short(r.score)}</div><div class="pl"><span class="tw">приз ⭐ ${short(r.prize)}</span></div><div class="ped">${[2, 1, 3][i]}</div></div>` : "<div></div>").join("")}</div>
      ${t.top.length > 3 ? `<div class="box">${t.top.slice(3).map((r, i) => `<div class="row tap" data-act="profile" data-id="${r.id}"><span class="place">${i + 4}</span>${avaHTML(r, 34)}
        <div class="grow"><div class="t">${nameHTML(r)}</div>${r.prize ? `<div class="s tw">приз ⭐ ${short(r.prize)}</div>` : ""}</div><b class="num">+⭐ ${short(r.score)}</b></div>`).join("")}</div>` : ""}`
      : emptyHTML("trophy", "Пока никто не в плюсе — займи первое место!")}
    <div class="tr-me"><span>Ты</span><b>${t.me.place ? t.me.place + " место" : "вне рейтинга"}</b><em class="${t.me.score >= 0 ? "tw" : "tl"}">${t.me.score >= 0 ? "+" : "−"}⭐ ${short(Math.abs(t.me.score))}</em>
      <button class="btn sm gold" data-act="tr-play" data-g="${t.game}">Играть</button></div>
    ${TR.last.length ? `<div class="sec-t">${ic("award")}Прошлые турниры</div><div class="box">${TR.last.map(l => `<div class="row kv"><div class="grow"><div class="t">${esc((GAMES.find(g => g.id === l.game) || {}).t || l.game)}</div><div class="s">${l.result[0] ? `1 место: ${esc(l.result[0].name)}` : "Победителя нет"}</div></div><b>⭐ ${short((l.result[0] || {}).prize || 0)}</b></div>`).join("")}</div>` : ""}
    <div class="disc">Следующий турнир: ${TR.next.map(esc).join(" и ")}. Новый — каждые ${TR.days || 3} ${plural(TR.days || 3, ["день", "дня", "дней"])}, счёт — чистый выигрыш в игре с начала турнира. Призы приходят автоматически.</div>`);
  starify(el);
}
Object.assign(ACT, {
  tourn: () => openTourn(),
  "tr-tab": el => { trTab = +el.dataset.v; H.sel(); trPaint(topSheet()); },
  "tr-play": el => { const g = el.dataset.g; closeSheet(); if (GAME_OPEN[g]) GAME_OPEN[g](); else if (g === "crash") openCrash(); else if (g === "mines") openMines(); },
});

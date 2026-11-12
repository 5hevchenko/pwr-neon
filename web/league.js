"use strict";
// ============================================================
//  Лиги недели — группа из 30 игроков своей лиги: верх поднимается, низ вылетает, топ-3 получает звёзды
// ============================================================
// цвета щита: светлый, основной, тёмный, камень
const LG_COL = [["#ffd9b8", "#cd7f4a", "#5e2c10", "#ff9a5a"], ["#ffffff", "#b8c4d2", "#4f5b6c", "#e3ecf8"], ["#fff3c0", "#ffc53d", "#7a4f00", "#ffe680"],
  ["#d6fff8", "#4fd8c6", "#0e5f58", "#b8fff4"], ["#dcefff", "#6aa8ff", "#1f3a9e", "#b0d8ff"], ["#ffd6f5", "#ff4fc3", "#4d1599", "#ffa8ea"]];
// гербовый щит: металл, кант, гранёный камень; число звёздочек сверху = номер лиги, у Легенды — корона
function lgEmblem(t, id = "") {
  const [a, b, c, g] = LG_COL[t], k = "lg" + t + id;
  const stars = t >= 5 ? `<path d="M34 9l6 6 10-11 10 11 6-6-3 13H37Z" fill="url(#${k}m)" stroke="${c}" stroke-width="1.5" stroke-linejoin="round"/>`
    : Array.from({ length: t + 1 }, (_, i) => { const x = 50 + (i - t / 2) * 10; return `<path d="M${x} 3l1.9 3.9 4.3.6-3.1 3 .7 4.3-3.8-2-3.8 2 .7-4.3-3.1-3 4.3-.6Z" fill="${a}" stroke="${c}" stroke-width=".8"/>`; }).join("");
  return `<svg viewBox="0 0 100 116" class="lg-svg"><defs>
    <linearGradient id="${k}m" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset=".45" stop-color="${b}"/><stop offset="1" stop-color="${c}"/></linearGradient>
    <linearGradient id="${k}i" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c}"/><stop offset="1" stop-color="${b}"/></linearGradient>
    <radialGradient id="${k}g" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#fff"/><stop offset=".35" stop-color="${g}"/><stop offset="1" stop-color="${c}"/></radialGradient>
    <clipPath id="${k}c"><path d="M50 14 88 28v34c0 25-17 41-38 49-21-8-38-24-38-49V28Z"/></clipPath></defs>
    ${stars}
    <path d="M50 14 88 28v34c0 25-17 41-38 49-21-8-38-24-38-49V28Z" fill="url(#${k}m)"/>
    <path d="M50 21 81 33v29c0 21-14 34-31 41-17-7-31-20-31-41V33Z" fill="url(#${k}i)"/>
    <path d="M50 21 81 33v29c0 21-14 34-31 41-17-7-31-20-31-41V33Z" fill="none" stroke="${a}" stroke-opacity=".55" stroke-width="1.4"/>
    <g transform="translate(50 60)"><path d="M0-24 20-6 0 26-20-6Z" fill="url(#${k}g)"/><path d="M0-24 8-6H-8Z" fill="#fff" opacity=".55"/>
      <path d="M-20-6H20M-8-6 0 26 8-6" fill="none" stroke="${c}" stroke-opacity=".45" stroke-width="1"/></g>
    <g clip-path="url(#${k}c)"><rect class="lg-shine" x="-60" y="0" width="34" height="120" fill="#fff" opacity=".28" transform="skewX(-20)"/></g></svg>`;
}
TOPK.splice(0, 0, ["league", "shield", "Лига"]);
const lgLeft = ends => { const s = Math.max(0, ends - Date.now() / 1000), d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return d ? `${d} д ${h} ч` : h ? `${h} ч ${m} мин` : `${m} мин`; };
const _rtLeague = renderTop;
renderTop = async function () {
  if (topKind !== "league") return _rtLeague();
  const v = $("#v-top");
  v.innerHTML = `${topNavHTML()}<div id="lg-body">${emptyHTML("hourglass", "Загружаем…")}</div>`;
  const d = await api("league").catch(() => null); if (!d || TAB !== "top" || topKind !== "league") return;
  const t = d.tier, n = d.rows ? d.rows.length : 0, me = d.rows ? d.rows.findIndex(r => r.id === ME.id) + 1 : 0, pr = d.prizes[t];
  let h = `<div class="lg-hero" style="--a:${LG_COL[t][1]};--b:${LG_COL[t][2]}">
      <div class="lg-emb">${lgEmblem(t, "h")}</div>
      <div class="lg-ht"><span>Лига недели</span><b>${d.tiers[t]}</b>
        <em>${d.joined ? `<i>${me}</i> место из ${n}` : "ты ещё не в группе"}</em>
        <small>${ic("clock")}итоги через ${lgLeft(d.ends)}</small></div></div>
    <div class="lg-ladder">${d.tiers.map((nm, i) => `<div class="${i === t ? "on" : i < t ? "done" : ""}">${lgEmblem(i, "l")}<span>${nm}</span></div>`).join("")}</div>
    <div class="lg-prz">${pr.map((p, i) => `<div class="p${i + 1}"><i>${i + 1}</i><span>место</span><b>⭐ ${short(p)}</b></div>`).join("")}</div>`;
  if (!d.joined) {
    h += `<div class="lg-join">${ic("games")}<div><b>Сыграй в любую игру</b><span>и попадёшь в группу из ${30} игроков своей лиги. Неделя — и лучшие поднимаются выше.</span></div>
      <button class="btn gold sm" data-act="lg-play">Играть</button></div>`;
  } else {
    const row = (r, i) => `<div class="row tap lg-row${r.id === ME.id ? " me" : ""}${i < d.up ? " up" : ""}${d.down && i >= n - d.down ? " down" : ""}" data-act="profile" data-id="${r.id}">
      <span class="lg-pl${i < 3 ? " m" + (i + 1) : ""}">${i + 1}</span>${avaHTML(r, 34)}<div class="grow"><div class="t">${nameHTML(r)}${r.id === ME.id ? " <span class='pill'>ты</span>" : ""}</div></div>
      <b class="num">${fmt(r.pts)}<small> очк.</small></b></div>`;
    let rows = "";
    d.rows.forEach((r, i) => {
      if (i === 0 && d.up) rows += `<div class="lg-zone up">${ic("trend")}Зона повышения · топ-${d.up} → ${d.tiers[Math.min(t + 1, 5)]}</div>`;
      if (d.up && i === d.up) rows += `<div class="lg-cut"></div>`;
      if (d.down && i === n - d.down) rows += `<div class="lg-zone down">${ic("chev")}Зона вылета → ${d.tiers[Math.max(t - 1, 0)]}</div>`;
      rows += row(r, i);
    });
    h += `<div class="box lg-list">${rows}</div>`;
  }
  h += `<details class="rules" style="margin-top:12px"><summary>${ic("award")}Как работают лиги</summary><div>Лиг шесть: ${d.tiers.join(" → ")}. Каждую неделю игроки одной лиги делятся на группы до 30 человек — попадаешь в группу, как только сыграл в любую игру.
    Очки — как в сезоне: оборот в играх, но с одной ставки засчитывается не больше ⭐ 10 000 (1 очко за ⭐ 100), так что решает активность, а не одна огромная ставка.
    В понедельник в 03:00 по Москве итоги: верх группы поднимается в лигу выше, низ опускается, топ-3 получают звёзды — в старших лигах больше, а все призы умножаются на курс банка (банк растёт — призы больше). Не играл неделю — остаёшься в своей лиге.</div></details>`;
  $("#lg-body").innerHTML = h;
  starify($("#lg-body"));
  if (d.last) lgResult(d.last, d.tiers);
};
// итоги прошлой недели: щит было → стало, место, приз
function lgResult(r, tiers) {
  const up = r.newtier > r.tier, down = r.newtier < r.tier;
  const el = openSheet(`<div class="lg-res ${up ? "up" : down ? "down" : ""}">
      <span class="lg-rk">Итоги недели</span>
      <div class="lg-rem">${up || down ? `<div class="old">${lgEmblem(r.tier, "ro")}</div>${ic(up ? "trend" : "chev")}` : ""}<div class="new">${lgEmblem(r.newtier, "rn")}</div></div>
      <b class="lg-rt">${up ? `Повышение: ${tiers[r.newtier]}!` : down ? `Вылет: ${tiers[r.newtier]}` : `Остаёшься: ${tiers[r.newtier]}`}</b>
      <p>${r.place} место из ${r.size} в лиге «${tiers[r.tier]}» · ${fmt(r.pts)} очк.</p>
      ${r.reward ? `<div class="lg-rw">+⭐ ${fmt(r.reward)}</div>` : ""}
      <button class="btn gold" data-act="lg-ok">${up ? "Вперёд" : "Понятно"}</button></div>`, "lg-rs");
  starify(el);
  el._onClose = () => post("league/seen").catch(() => {});
  if (up || r.reward) setTimeout(() => { H.ok(); if (el.isConnected) coinShower(el.querySelector(".lg-res"), r.reward ? 40 : 20); }, 450);
}
Object.assign(ACT, {
  "lg-play": () => setTab("games"),
  "lg-ok": () => closeSheet(),
});
// итоги прошлой недели показываем и без захода в «Топ» — один раз за запуск
setTimeout(async () => {
  if (typeof ME === "undefined" || !ME) return;
  const d = await api("league").catch(() => null);
  if (d && d.last && !SHEETS.length) lgResult(d.last, d.tiers);
}, 5000);

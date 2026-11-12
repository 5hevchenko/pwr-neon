"use strict";
// ============================================================ акция «щедрые выходные»: тонкая полоска над кейсами и играми + метки на кейсах
let PROMO_SEEN = null;
function promoLeft(p) {
  if (!p.until) return "";
  const s = Math.max(0, p.until - Date.now() / 1000), d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return d ? `${d} д ${h} ч` : h ? `${h} ч ${m} мин` : `${m} мин`;
}
const promoRib = () => ME && ME.promo ? `<button class="prib" data-act="promo-info"><span class="prib-i">${ic("sparkles")}</span><b>${esc(ME.promo.title)}</b><span class="prib-s">шансы выше${ME.promo.until ? " · ещё " + promoLeft(ME.promo) : ""}</span>${ic("chev")}</button>` : "";
function promoSync() {   // цены кейсов зависят от акции — перезагружаем при смене
  const k = ME && ME.promo ? "on" : "off";
  if (PROMO_SEEN !== null && PROMO_SEEN !== k) CASES = [];
  PROMO_SEEN = k;
}
const NEW_CASES = new Set(["coin", "cute", "tech", "peachhunt", "night", "caphunt", "sport", "royal"]), NEW_UNTIL = Date.UTC(2026, 9, 17);
const _rcP = renderCases;
renderCases = async function () {
  promoSync();
  await _rcP();
  const v = $("#v-cases"); if (!v) return;
  if (ME.promo && !v.querySelector(".prib")) v.insertAdjacentHTML("afterbegin", promoRib());
  v.querySelectorAll(".case[data-id]").forEach(el => {
    const c = CASES.find(x => x.id === el.dataset.id); if (!c) return;
    const pr = el.querySelector(".pr");
    if (pr && c.full > c.price && !pr.querySelector("s")) { pr.insertAdjacentHTML("afterbegin", `<s>${short(c.full)}</s>`); el.classList.add("sale"); }
    if (NEW_CASES.has(c.id) && Date.now() < NEW_UNTIL && !el.querySelector(".newtag")) el.insertAdjacentHTML("beforeend", `<span class="newtag">NEW</span>`);
    if ((c.id.endsWith("hunt") || c.id === "coin") && !el.querySelector(".hunttag")) {   // кейсы-охоты: шанс на топ-подарок прямо на карточке
      const top = c.items.find(x => x.col === c.cover);
      el.classList.add("hunt");
      if (top) el.insertAdjacentHTML("beforeend", `<span class="hunttag">${ic("target")}${top.p < .1 ? "1 к " + fmt(Math.round(100 / top.p)) : String(top.p).replace(".", ",") + "%"}</span>`);
    }
    if (c.keys && !el.querySelector(".keytag")) el.insertAdjacentHTML("beforeend", `<span class="keytag">${ic("lock")}${c.keys}</span>`);
  });
};
const _rgP = renderGames;
renderGames = function () {
  _rgP();
  const v = $("#v-games");
  if (v && ME.promo && !v.querySelector(".prib")) v.insertAdjacentHTML("afterbegin", promoRib());
};
Object.assign(ACT, {
  "promo-info": () => {
    const p = ME.promo; if (!p) return;
    H.sel();
    modal(`<h3>${ic("sparkles")} ${esc(p.title)}</h3><p class="hint" style="margin:0 0 12px">${p.until ? `Банк щедрый до конца воскресенья — ещё ${promoLeft(p)}.` : "Сегодня банк щедрый."}</p>
      <div class="box" style="margin-bottom:14px">${p.perks.map(x => `<div class="row kv"><span class="tw">${ic("check")}</span><div class="grow">${esc(x)}</div></div>`).join("")}</div>
      <button class="btn gold" data-m="ok">Играть</button>`);
  },
});

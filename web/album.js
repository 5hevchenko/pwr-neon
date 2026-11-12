"use strict";
// ============================================================
//  Альбом коллекций: все коллекции, собранные — цветные; награды за каждые 10
// ============================================================
let AL = null, alFilter = "all";
const _riAlbum = renderInventory;
renderInventory = async function () {
  await _riAlbum();
  const v = $("#v-inv"); if (!v || v.querySelector(".al-bar")) return;
  AL = await api("album").catch(() => null); if (!AL || TAB !== "inv") return;
  const ready = AL.tiers.filter(t => !t.claimed && AL.eligible >= t.need).length;
  v.insertAdjacentHTML("afterbegin", `<button class="al-bar" data-act="album">${ic("layers")}<div class="grow"><b>Альбом коллекций</b>
      <div class="al-mini"><i style="width:${AL.count / AL.total * 100}%"></i></div></div><span class="al-cnt">${AL.count}/${AL.total}</span>${ready ? `<em>${ready}</em>` : ""}${ic("chev")}</button>`);
};
async function openAlbum() {
  const el = openSheet(emptyHTML("hourglass", "Листаем альбом…"), "al-s");
  AL = await api("album").catch(() => null); if (!AL || !el.isConnected) return;
  alPaint(el);
}
function alPaint(el) {
  const next = AL.tiers.find(t => !t.claimed);
  const list = AL.cols.filter(c => alFilter === "all" || (alFilter === "have" ? c.have : !c.have));
  replaceSheet(el, `<div class="al-hero"><div class="al-ring" style="--p:${AL.count / AL.total * 100}"><b>${AL.count}</b><span>из ${AL.total}</span></div>
      <div><h2>Альбом коллекций</h2><span>Собирай подарки разных коллекций — каждые 10 дают награду.${AL.eligible < AL.count ? ` Засчитано ${AL.eligible}: новые подарки — через сутки.` : ""}</span></div></div>
    <div class="al-tiers">${AL.tiers.map(t => { const ok = AL.eligible >= t.need;
      return `<div class="al-t${t.claimed ? " got" : ok ? " ready" : ""}"><b>${t.need}</b><span>${t.key ? `ключ «${esc(t.key)}»` : `⭐ ${short(t.stars)}`}</span>
        ${t.claimed ? `<i>${ic("check")}</i>` : ok ? `<button class="btn sm gold" data-act="al-claim" data-v="${t.need}">Забрать</button>` : `<small>ещё ${t.need - AL.eligible}</small>`}</div>`; }).join("")}</div>
    <div class="seg" style="margin-top:12px">${[["all", "Все"], ["have", "Собрано"], ["miss", "Не хватает"]].map(([k, t]) => `<button data-act="al-f" data-v="${k}" class="${alFilter === k ? "on" : ""}">${t}</button>`).join("")}</div>
    <div class="al-grid">${list.map(c => `<div class="al-c${c.have ? " have" : ""}${c.have && !c.aged ? " fresh" : ""}"><img src="${A.orig(c.col, 128)}" loading="lazy" alt="">
      <b>${esc(c.col)}</b><span>${c.have ? `${c.have}/${c.models} моделей` : `⭐ ${short(c.base)}`}</span></div>`).join("")}</div>
    ${next ? `<div class="disc">Следующая награда — за ${next.need} коллекций. Не хватающие подарки ищи в кейсах и на витрине маркета.</div>` : ""}`);
  starify(el);
}
Object.assign(ACT, {
  album: () => openAlbum(),
  "al-f": el => { alFilter = el.dataset.v; H.sel(); alPaint(topSheet()); },
  "al-claim": async el => {
    const r = await post("album/claim", { need: +el.dataset.v }); setStars(r.stars); H.ok();
    toast(r.key ? `Ключ «${r.key}» — открывай кейс бесплатно!` : `+⭐ ${fmt(r.reward)}`, "ok"); burstAt(el);
    if (r.key) CASES = [];
    AL = await api("album"); alPaint(topSheet());
  },
});

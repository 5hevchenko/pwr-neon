"use strict";
// ============================================================
//  Маркет v2: вкладки «Витрина казино» · «Скупка» · «Игроки» · «Мои». Витрина и скупка — маркет-мейкер казино.
// ============================================================
let MKT = "shop", MKS = null, mkTick = null;
const _renderMarketOrig = renderMarket;
const MKT_TABS = [["shop", "store", "Витрина"], ["orders", "coins", "Скупка"], ["players", "users", "Игроки"], ["mine", "tag", "Мои"]];
const mkTabs = () => `<div class="mk2-tabs">${MKT_TABS.map(([k, i, t]) => `<button data-act="mkt" data-v="${k}" class="${MKT === k ? "on" : ""}">${ic(i)}${t}</button>`).join("")}</div>`;
const mkLeft = s => { s = Math.max(0, Math.floor(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}`; };

renderMarket = async function () {
  clearInterval(mkTick);
  const v = $("#v-market");
  if (MKT === "players" || MKT === "mine") {
    MK.mine = MKT === "mine" ? 1 : 0;
    await _renderMarketOrig();
    if (!v.querySelector(".mk2-tabs")) v.insertAdjacentHTML("afterbegin", mkTabs());
    return;
  }
  v.innerHTML = mkTabs() + `<div id="mk2">${emptyHTML("hourglass", "Загружаем…")}</div>`;
  try { MKS = await api("mkshop"); } catch (e) { return; }
  if (TAB !== "market") return;
  MKS._off = MKS.now - Date.now() / 1000;
  MKT === "shop" ? mkShopPaint() : mkOrdersPaint();
  mkTick = setInterval(() => {
    const el = $("#mk2-left"); if (!el || TAB !== "market") return clearInterval(mkTick);
    const left = MKS.refresh - (Date.now() / 1000 + MKS._off);
    el.textContent = mkLeft(left);
    if (left <= 0) { clearInterval(mkTick); renderMarket(); }
  }, 1000);
};

function mkShopPaint() {
  const box = $("#mk2"); if (!box) return;
  const lots = MKS.shop, jack = lots[0], rest = lots.slice(1);
  const card = (g, big) => `<div class="mk2-lot${big ? " big" : ""}${g.sold ? " sold" : ""} t-${tier(g)}">
      <div class="mk2-g">${giftHTML(g, { lite: true })}${g.sold ? `<span class="mk2-sold">Продано</span>` : ""}</div>
      <div class="mk2-info"><b>${esc(g.col)}</b><span>${esc(g.model)} · ${pct(g.mp)}</span>
        <div class="mk2-meta"><span>ценность ⭐ ${short(g.value)}</span><span class="tw">+⭐ ${short(Math.round(giftPerHour(g) * 24))}/день</span></div>
        <button class="btn sm gold" data-act="mk2-buy" data-id="${g.id}" ${g.sold ? "disabled" : ""}>${g.sold ? "Продано" : `Купить · ⭐ ${short(g.price)}`}</button></div></div>`;
  box.innerHTML = `<div class="mk2-hero shop"><div><b>Витрина банка</b><span>Конкретные подарки — без рулетки. Бери нужную модель для сета, витрины или дохода.</span></div>
      <div class="mk2-timer"><span>обновится через</span><b id="mk2-left">${mkLeft(MKS.refresh - MKS.now)}</b></div></div>
    ${jack ? card(jack, true) : ""}
    <div class="mk2-grid">${rest.map(g => card(g)).join("")}</div>
    <div class="disc">Цена на витрине — ценность подарка +${Math.round((MKS.markup - 1) * 100)}%. Каждый лот в единственном экземпляре: кто первый купил, того и подарок. Звёзды уходят в банк игры.</div>`;
  startLottie(box); starify(box);
}

function mkOrdersPaint() {
  const box = $("#mk2"); if (!box) return;
  box.innerHTML = `<div class="mk2-hero orders"><div><b>Скупка банка</b><span>Банк покупает эти коллекции дороже, чем мгновенная продажа (${sellP()}). Заказы ограничены — успей.</span></div>
      <div class="mk2-timer"><span>новые через</span><b id="mk2-left">${mkLeft(MKS.refresh - MKS.now)}</b></div></div>
    ${MKS.orders.map(o => { const left = o.qty - o.filled, done = left <= 0;
      return `<div class="mk2-ord${done ? " done" : ""}">
        <div class="mk2-oh"><img src="${A.orig(o.col, 96)}" alt=""><div class="grow"><b>${esc(o.col)}</b><span>любая модель · база ⭐ ${short(o.base)}</span></div>
          <div class="mk2-pct"><b>${Math.round(o.pct * 100)}%</b><span>ценности</span></div></div>
        <div class="mk2-prog"><i style="width:${o.filled / o.qty * 100}%"></i><span>${done ? "заказ выполнен" : `нужно ещё ${left} из ${o.qty}`}</span></div>
        ${done ? "" : o.mine.length ? `<div class="mk2-mine">${o.mine.map(g => `<div class="mk2-mg">${giftHTML(g, { lite: true, plain: true })}
            <button class="btn sm green" data-act="mk2-sell" data-o="${o.id}" data-g="${g.id}" data-p="${Math.floor(g.value * o.pct)}">⭐ ${short(Math.floor(g.value * o.pct))}</button></div>`).join("")}</div>`
          : `<div class="hint mk2-none">У тебя нет таких подарков — загляни в кейсы или на витрину</div>`}
      </div>`; }).join("")}
    <div class="disc">Сравни: мгновенная продажа банку — ${sellP()} ценности. В скупке — 100–110%.</div>`;
  starify(box);
}

Object.assign(ACT, {
  mkt: el => { MKT = el.dataset.v; H.sel(); renderMarket(); },
  "mk2-buy": async el => {
    const g = MKS.shop.find(x => x.id === +el.dataset.id); if (!g) return;
    if (g.price > ME.stars) return toast("Не хватает звёзд ⭐");
    if (!await confirmM("Купить с витрины?", `${esc(g.col)} «${esc(g.model)}» за ⭐ ${fmt(g.price)}`, "Купить")) return;
    const r = await post(`mkshop/${g.id}/buy`); setStars(r.stars); H.ok();
    const img = el.closest(".mk2-lot")?.querySelector(".gift > img");
    if (img && typeof flyToBag === "function") flyToBag(img);
    burstAt(el, r.gift); g.sold = true; setTimeout(mkShopPaint, 60); toast("Подарок в сумке!", "ok");
  },
  "mk2-sell": async el => {
    const p = +el.dataset.p;
    if (!await confirmM("Продать банку?", `Получишь ⭐ ${fmt(p)} — это больше, чем мгновенная продажа.`, "Продать")) return;
    const r = await post(`mkorders/${el.dataset.o}/sell`, { gid: +el.dataset.g }); setStars(r.stars); H.ok(); toast(`+⭐ ${fmt(r.pay)}`, "ok"); coinShower(el, 24);
    MKS = await api("mkshop"); MKS._off = MKS.now - Date.now() / 1000; mkOrdersPaint();
  },
});

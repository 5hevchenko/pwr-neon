"use strict";
// ============================================================
//  Крипта: стейкинг, обмен монет, фьючерсы с плечом
// ============================================================
ICONS.lock2 = '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>';
ICONS.up = '<path d="M12 19V5M5 12l7-7 7 7"/>';
ICONS.down = '<path d="M12 5v14M19 12l-7 7-7-7"/>';
ICONS.swap2 = '<path d="M7 7h11l-3-3M17 17H6l3 3"/>';
let cxView = "market", FX = null, fxAsset = "BTC", fxLev = 10, fxMargin = 500, fxPoll = null, stTick = null;
const YEAR = 365 * 86400;

// ------------------------------------------------------------ переключатель разделов вкладки
const cxSegHTML = () => `<div class="seg cx-seg">${[["market", "trend", "Рынок"], ["stake", "lock2", "Стейкинг"], ["fut", "flame", "Фьючерсы"]]
  .map(([k, i, t]) => `<button data-act="cx-view" data-v="${k}" class="${k === cxView ? "on" : ""}">${ic(i)}${t}</button>`).join("")}</div>`;
const _fillMarket = fillCX;
fillCX = function () {
  const v = $("#v-crypto");
  if (!v || !CX) return;
  if (cxView === "market") { _fillMarket(); v.insertAdjacentHTML("afterbegin", cxSegHTML()); }
  else if (cxView === "stake") fillStake(v);
  else fillFut(v);
};
const _rCx = TAB_RENDER.crypto;
TAB_RENDER.crypto = async function () {
  await _rCx();
  clearInterval(fxPoll);
  fxPoll = setInterval(() => { if (TAB !== "crypto") return clearInterval(fxPoll); if (cxView === "fut" && !bgOff()) loadFX(); }, 5000);
  if (cxView === "fut") loadFX();
};

// ------------------------------------------------------------ стейкинг
function stEarned(a) {   // накоплено прямо сейчас (между запросами досчитываем по ставке)
  if (!a.staked && !a.earned) return 0;
  return (a.earned || 0) + (a.staked || 0) * a.apy * Math.min(Date.now() / 1000 - CX._t, a.stakeLeft ?? 1e9) / YEAR;   // копится максимум сутки
}
function fillStake(v) {
  CX._t = CX._t || Date.now() / 1000;
  const list = CX.assets, staked = list.filter(a => a.staked > 0 || a.earned > 0);
  const inStake = staked.reduce((s, a) => s + a.staked * (a.price || 0), 0);
  const perDay = staked.reduce((s, a) => s + a.staked * (a.price || 0) * a.apy / 365, 0);
  const totalEarned = staked.reduce((s, a) => s + (a.stakeTotal || 0) * (a.price || 0), 0);
  v.innerHTML = cxSegHTML() + `
    <div class="sthero">
      <span class="cx-lbl">В стейкинге</span><b class="cx-tot">⭐ ${fmt(Math.round(inStake))}</b>
      <div class="st-row"><div><span>Доход в день</span><b>+⭐ ${fmt1(perDay)}</b></div><div><span>Накоплено</span><b data-st="all">⭐ 0</b></div><div><span>Заработано всего</span><b>⭐ ${fmt1(totalEarned)}</b></div></div>
      <button class="btn cta st-claim" data-act="st-claim" ${staked.length ? "" : "disabled"}>${ic("coins")}Забрать награды</button>
    </div>
    <div class="sec-t">${ic("lock2")}Ставки на монеты</div>
    <div class="box">${list.map(a => `<div class="row tap cxrow" data-act="cx-open" data-id="${a.id}" data-to="stake">${coinBadge(a)}
      <div class="grow"><div class="t">${esc(a.name)} <span class="apy">${String(+(a.apy * 100 / 365).toFixed(1)).replace(".", ",")}% в день</span></div>
        <div class="s">${a.staked ? `застейкано ${qtyFmt(a.staked)} ${a.id}` : a.qty ? `в кошельке ${qtyFmt(a.qty)} — можно застейкать` : "в день · копится до суток"}</div></div>
      <div class="st-act">${a.staked || a.earned ? `<b class="tw" data-st="${a.id}">+${qtyFmt(stEarned(a))}</b><span class="hint">${a.id} накоплено</span>` : ""}
        ${a.qty ? `<button class="btn sm green" data-act="st-quick" data-id="${a.id}">${ic("lock2")}Застейкать</button>` : a.staked ? `<button class="btn sm ghost" data-act="st-qout" data-id="${a.id}">Вывести</button>` : `<button class="btn sm ghost" data-act="cx-open" data-id="${a.id}">Купить</button>`}</div></div>`).join("")}</div>
    ${list.some(a => a.qty) ? `<div class="hint st-tip">${ic("info")}Монеты в кошельке ещё не работают — жми «Застейкать», и они начнут приносить проценты</div>` : ""}
    <div class="disc">Застейканные монеты лежат в стейкинге и каждую секунду приносят ещё монет — от 0,7% (USDT) до 6% в день. Награда копится до суток: забирай её каждый день, иначе начисление встанет. Цена монеты при этом продолжает меняться вместе с рынком. Вывести можно в любой момент, без штрафа. Монеты и звёзды игровые.</div>`;
  stPaint();
}
function stPaint() {
  if (!CX || cxView !== "stake" || TAB !== "crypto") return;
  let all = 0;
  for (const a of CX.assets) {
    const e = stEarned(a); all += e * (a.price || 0);
    const el = document.querySelector(`[data-st="${a.id}"]`); if (el) el.textContent = "+" + qtyFmt(e);
  }
  const t = document.querySelector('[data-st="all"]'); if (t) t.textContent = "⭐ " + fmt1(all);
}
clearInterval(stTick); stTick = setInterval(stPaint, 1000);
const _lCX = loadCX;
loadCX = async function () { await _lCX(); if (CX) CX._t = Date.now() / 1000; };

// ------------------------------------------------------------ фьючерсы
async function loadFX() {
  try { FX = await api("futures"); } catch (e) { return; }
  if (TAB === "crypto" && cxView === "fut") fillFut($("#v-crypto"));
}
const fxA = () => FX && (FX.assets.find(a => a.id === fxAsset) || FX.assets[0]);
const liqOf = (side, price, lev) => side === "long" ? price * (1 - .9 / lev) : price * (1 + .9 / lev);
function fillFut(v) {
  if (!FX) { v.innerHTML = cxSegHTML() + emptyHTML("hourglass", "Загружаем фьючерсы…"); loadFX(); return; }
  const a = fxA(), st = FX.stats;
  fxMargin = Math.max(0, Math.min(fxMargin, Math.max(FX.min, ME.stars)));
  const keepY = scrollY;
  v.innerHTML = cxSegHTML() + `
    <div class="fx-coins">${FX.assets.map(c => `<button data-act="fx-coin" data-v="${c.id}" class="${c.id === a.id ? "on" : ""}">${coinBadge(c, 22)}${c.id}</button>`).join("")}</div>
    <div class="fx-card">
      <div class="fx-top">${coinBadge(a, 40)}<div class="grow"><b>${esc(a.name)}</b><span>${a.id} · фьючерс</span></div>
        <div class="fx-px"><b>⭐ ${pxFmt(a.price)}</b><em class="${a.change >= 0 ? "up" : "dn"}">${pctFmt(a.change)}</em></div></div>
      ${spark(a.spark, a.change >= 0, 320, 56)}
      <div class="fx-lbl">Плечо</div>
      <div class="fx-levs">${FX.levs.map(l => `<button data-act="fx-lev" data-v="${l}" class="${l === fxLev ? "on" : ""}${l >= 25 ? " hot" : ""}">x${l}</button>`).join("")}</div>
      <div class="fx-lbl">Маржа</div>
      <div class="ca-in fx-in"><span>⭐</span><input id="fx-m" type="number" inputmode="numeric" value="${fxMargin}"><small id="fx-sz"></small></div>
      <div class="quick">${[100, 500, 1000, 5000].map(n => `<button data-act="fx-m" data-v="${n}">${short(n)}</button>`).join("")}<button data-act="fx-m" data-v="max">MAX</button></div>
      <div class="fx-info" id="fx-info"></div>
      <div class="fx-btns"><button class="btn fx-long" data-act="fx-open" data-v="long">${ic("up")}<span><b>Лонг</b><small>на рост</small></span></button>
        <button class="btn fx-short" data-act="fx-open" data-v="short">${ic("down")}<span><b>Шорт</b><small>на падение</small></span></button></div>
    </div>
    <div class="sec-t">${ic("flame")}Открытые позиции${FX.positions.length ? ` · ${FX.positions.length}` : ""}</div>
    ${FX.positions.length ? FX.positions.map(posHTML).join("") : `<div class="box"><div class="hint bk-empty">Открой лонг, если думаешь, что цена вырастет, или шорт — если упадёт</div></div>`}
    <div class="fx-stats"><div><span>Итог сделок</span><b class="${st.pnl >= 0 ? "tw" : "tl"}">${st.pnl >= 0 ? "+" : "−"}⭐ ${short(Math.abs(st.pnl))}</b></div>
      <div><span>Сделок</span><b>${st.trades}</b></div><div><span>В плюс</span><b>${st.trades ? Math.round(st.wins / st.trades * 100) : 0}%</b></div></div>
    ${FX.history.length ? `<div class="sec-t">${ic("clock")}История</div><div class="box">${FX.history.map(h => { const c = FX.assets.find(x => x.id === h.asset) || { id: h.asset, color: "#888", glyph: "?" }; return `<div class="row">${coinBadge(c, 32)}
      <div class="grow"><div class="t">${h.asset} <span class="fx-side ${h.side}">${h.side === "long" ? "Лонг" : "Шорт"} x${h.lev}</span></div><div class="s">${h.status === "liq" ? "ликвидирована" : "закрыта"} · ⭐ ${pxFmt(h.entry)} → ${pxFmt(h.mark)}</div></div>
      <b class="${h.pnl >= 0 ? "tw" : "tl"}">${h.pnl >= 0 ? "+" : "−"}⭐ ${short(Math.abs(h.pnl))}</b></div>`; }).join("")}</div>` : ""}
    ${FX.top.length ? `<div class="sec-t">${ic("crown")}Лучшие трейдеры</div><div class="box">${FX.top.map((u, i) => `<div class="row tap" data-act="profile" data-id="${u.id}"><span class="place p${i + 1}">${i + 1}</span>${avaHTML(u, 34)}
      <div class="grow"><div class="t">${esc(u.name)}</div></div><b class="tw">+⭐ ${short(u.pnl)}</b></div>`).join("")}</div>` : ""}
    <div class="disc">Фьючерс — ставка на движение цены с плечом: при x10 цена +1% даёт +10% к марже, −1% — минус 10%. Когда убыток съест 90% маржи, позицию ликвидируют, маржа сгорает. Комиссия ${String(FX.fee * 100).replace(".", ",")}% от объёма при открытии и закрытии. Курсы реальные (OKX), всё на игровых звёздах.</div>`;
  scrollTo(0, keepY);
  const inp = $("#fx-m");
  inp.oninput = () => { fxMargin = Math.max(0, Math.floor(+inp.value || 0)); fxInfo(); };
  fxInfo();
}
function fxInfo() {
  const a = fxA(), el = $("#fx-info"); if (!a || !el) return;
  const size = fxMargin * fxLev, fee = Math.ceil(size * FX.fee);
  $("#fx-sz").textContent = `объём ⭐ ${short(size)}`;
  el.innerHTML = `<div><span>Ликвидация лонга</span><b class="tl">⭐ ${pxFmt(liqOf("long", a.price, fxLev))}</b></div>
    <div><span>Ликвидация шорта</span><b class="tl">⭐ ${pxFmt(liqOf("short", a.price, fxLev))}</b></div>
    <div><span>Цена +1% даст</span><b class="tw">+⭐ ${fmt(Math.round(size * .01))}</b></div>
    <div><span>Комиссия</span><b>⭐ ${fmt(fee)}</b></div>`;
  document.querySelectorAll("[data-act=fx-open]").forEach(b => b.disabled = fxMargin < FX.min);
}
function posHTML(p) {
  const c = FX.assets.find(x => x.id === p.asset) || { id: p.asset, color: "#888", glyph: "?" };
  // насколько близко ликвидация: 0 — только открыли, 100 — сгорит
  const risk = Math.max(0, Math.min(100, -p.pnl / (p.margin * .9) * 100));
  return `<div class="fx-pos ${p.pnl >= 0 ? "win" : "lose"}">
    <div class="fp-h">${coinBadge(c, 32)}<div class="grow"><b>${p.asset}</b> <span class="fx-side ${p.side}">${p.side === "long" ? "Лонг" : "Шорт"} x${p.lev}</span><small>маржа ⭐ ${fmt(p.margin)}</small></div>
      <div class="fp-pnl"><b>${p.pnl >= 0 ? "+" : "−"}⭐ ${fmt(Math.abs(Math.round(p.pnl)))}</b><em>${pctFmt(p.roe)}</em></div></div>
    <div class="fp-g"><div><span>Вход</span><b>${pxFmt(p.entry)}</b></div><div><span>Сейчас</span><b>${pxFmt(p.mark)}</b></div><div><span>Ликвидация</span><b class="tl">${pxFmt(p.liq)}</b></div></div>
    ${risk > 0 ? `<div class="fp-risk"><span>до ликвидации</span><div class="cbar"><div style="width:${risk}%"></div></div><b>${Math.round(100 - risk)}%</b></div>` : ""}
    <button class="btn ${p.pnl >= 0 ? "green" : "ghost"} fp-close" data-act="fx-close" data-id="${p.id}">Закрыть · ${p.pnl >= 0 ? "+" : "−"}⭐ ${fmt(Math.abs(Math.round(p.pnl)))}</button></div>`;
}

// ------------------------------------------------------------ карточка монеты: обмен и стейкинг
const _caForm = caForm;
caForm = function (el, soft) {
  const f = el.querySelector("#ca-form"); if (!f || !CA) return;
  if (cxSide !== "swap") return _caForm(el, soft);
  const a = CA, others = (CX ? CX.assets : []).filter(x => x.id !== a.id);
  if (!a.qty) { f.innerHTML = `<div class="hint" style="font-size:13px;text-align:center;padding:8px 0">Менять пока нечего — сначала купи ${a.id}</div>`; return; }
  CA._to = CA._to && CA._to !== a.id ? CA._to : (a.id === "USDT" ? "BTC" : "USDT");
  const to = others.find(x => x.id === CA._to) || others[0];
  const got = p => a.qty * p / 100 * a.price * (1 - a.swapFee) / (to.price || 1);
  f.innerHTML = `<div class="fx-lbl">Получить</div><div class="fx-coins sm">${others.map(c => `<button data-act="sw-to" data-v="${c.id}" class="${c.id === to.id ? "on" : ""}">${coinBadge(c, 20)}${c.id}</button>`).join("")}</div>
    <div class="ca-sell">${[25, 50, 100].map(p => `<button class="btn ghost" data-act="sw-go" data-v="${p}"><b>${p === 100 ? "Всё" : p + "%"}</b><span>≈ ${qtyFmt(got(p))} ${to.id}</span></button>`).join("")}</div>
    <div class="hint" style="font-size:12px;margin-top:8px;text-align:center">${ic("swap2")} ${a.id} → ${to.id} по рыночному курсу, комиссия ${String(a.swapFee * 100).replace(".", ",")}%</div>`;
};
const _fillCA = fillCA;
fillCA = function (el) {
  _fillCA(el);
  if (!CA || !el.isConnected) return;
  const seg = el.querySelector(".ca-trade .seg");
  if (seg && !seg.querySelector('[data-v="swap"]')) {
    seg.insertAdjacentHTML("beforeend", `<button data-act="ca-side" data-v="swap" class="${cxSide === "swap" ? "on" : ""}">Обмен</button>`);
    if (cxSide === "swap") caForm(el);
  }
  const tr = el.querySelector(".ca-trade");
  if (tr && !el.querySelector(".ca-stake")) tr.insertAdjacentHTML("afterend", `<div class="inccard ca-stake" style="margin-top:10px">${stakeCardHTML()}</div>`);
  if (el._to === "stake") { el._to = null; setTimeout(() => el.querySelector(".ca-stake")?.scrollIntoView({ behavior: "smooth", block: "center" }), 250); }
};
function stakeCardHTML() {
  const a = CA, e = a.earned || 0;
  return `<div class="cas-h"><span class="pic g">${ic("lock2")}</span><div class="grow"><b>Стейкинг ${a.id}</b><span>${String(+(a.apy * 100 / 365).toFixed(1)).replace(".", ",")}% в день · копится до суток — забирай каждый день</span></div></div>
    ${a.staked || e ? `<div class="bks-top"><div><span>Застейкано</span><b>${qtyFmt(a.staked)}</b></div><div><span>Накоплено</span><b class="tw">+${qtyFmt(e)}</b></div><div><span>В день</span><b>+${qtyFmt(a.staked * a.apy / 365)}</b></div></div>` : ""}
    ${a.qty ? `<div class="ca-sell">${[50, 100].map(p => `<button class="btn ghost" data-act="st-put" data-v="${p}"><b>${p === 100 ? "Всё" : p + "%"}</b><span>${qtyFmt(a.qty * p / 100)} ${a.id}</span></button>`).join("")}
      <button class="btn ghost" data-act="st-out" ${a.staked || e ? "" : "disabled"}><b>Вывести</b><span>всё + награда</span></button></div>`
      : a.staked || e ? `<button class="btn ghost" style="width:100%" data-act="st-out"><b>Вывести всё + награду</b></button>` : `<div class="hint" style="font-size:13px">Купи ${a.id}, и монеты можно будет положить в стейкинг</div>`}`;
}
const _paintCALive = paintCALive;
paintCALive = function (el) { _paintCALive(el); const s = el.querySelector(".ca-stake"); if (s) s.innerHTML = stakeCardHTML(); };

async function refreshAll() { if (CA) await loadCA(CA.id); await loadCX(); }
Object.assign(ACT, {
  "cx-view": el => { cxView = el.dataset.v; H.sel(); fillCX(); if (cxView === "fut") loadFX(); },
  "cx-open": el => { openCA(el.dataset.id).then(() => {}); const s = topSheet(); if (s && el.dataset.to) s._to = el.dataset.to; },
  "st-claim": async el => {
    el.disabled = true;
    try { const r = await post("crypto/stake/claim"); H.ok(); toast(`Награды в кошельке · ≈ ⭐ ${fmt1(r.value)}`, "ok"); burstAt(el); } finally { el.disabled = false; }
    loadCX();
  },
  "st-quick": async el => { el.disabled = true; try { const r = await post(`crypto/${el.dataset.id}/stake`, { pct: 100 }); H.ok(); toast(`${qtyFmt(r.qty)} ${el.dataset.id} в стейкинге`, "ok"); burstAt(el); } finally { el.disabled = false; } loadCX(); },
  "st-qout": async el => { el.disabled = true; try { const r = await post(`crypto/${el.dataset.id}/unstake`); H.ok(); toast(`Выведено ${qtyFmt(r.qty)} ${el.dataset.id}`, "ok"); } finally { el.disabled = false; } loadCX(); },
  "st-put": async el => { const r = await post(`crypto/${CA.id}/stake`, { pct: +el.dataset.v }); H.ok(); toast(`${qtyFmt(r.qty)} ${CA.id} в стейкинге`, "ok"); refreshAll(); },
  "st-out": async () => { const r = await post(`crypto/${CA.id}/unstake`); H.ok(); toast(`Выведено ${qtyFmt(r.qty)} ${CA.id}`, "ok"); refreshAll(); },
  "sw-to": el => { CA._to = el.dataset.v; H.sel(); caForm(topSheet()); },
  "sw-go": async el => { el.disabled = true; try { const r = await post(`crypto/${CA.id}/swap`, { to: CA._to, pct: +el.dataset.v }); H.ok(); toast(`Получено ${qtyFmt(r.got)} ${r.to}`, "ok"); } finally { el.disabled = false; } refreshAll(); },
  "fx-coin": el => { fxAsset = el.dataset.v; H.sel(); fillFut($("#v-crypto")); },
  "fx-lev": el => { fxLev = +el.dataset.v; H.sel(); document.querySelectorAll(".fx-levs button").forEach(b => b.classList.toggle("on", b === el)); fxInfo(); },
  "fx-m": el => { fxMargin = el.dataset.v === "max" ? Math.max(0, Math.floor(ME.stars / (1 + fxLev * FX.fee)) - 1) : +el.dataset.v; H.sel(); $("#fx-m").value = fxMargin; fxInfo(); },
  "fx-open": async el => {
    if (fxMargin > ME.stars) return toast("Не хватает звёзд ⭐");
    el.disabled = true;
    try {
      const r = await post("futures/open", { asset: fxA().id, side: el.dataset.v, lev: fxLev, margin: fxMargin });
      setStars(r.stars); H.imp("heavy"); toast(`${el.dataset.v === "long" ? "Лонг" : "Шорт"} ${fxA().id} x${fxLev} открыт · ликвидация ⭐ ${pxFmt(r.liq)}`, "ok");
    } finally { el.disabled = false; }
    loadFX();
  },
  "fx-close": async el => {
    el.disabled = true;
    try {
      const r = await post(`futures/${el.dataset.id}/close`);
      setStars(r.stars);
      if (r.status === "liq") { H.err(); toast("Позицию ликвидировало", "err"); }
      else if (r.pnl >= 0) { H.ok(); toast(`Закрыто в плюс · +⭐ ${fmt(r.pnl)}`, "ok"); burstAt(el); }
      else { H.imp("light"); toast(`Закрыто · −⭐ ${fmt(-r.pnl)}`, "err"); }
    } finally { el.disabled = false; }
    loadFX();
  },
});

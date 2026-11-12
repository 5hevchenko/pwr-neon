"use strict";
// ============================================================
//  Крипто-биржа: реальные курсы, торговля игровыми звёздами
// ============================================================
let CX = null, CA = null, cxRange = "1d", cxSide = "buy", cxAmt = 1000;

// цена в звёздах: крупные — целыми, мелкие — с нужным числом знаков
const pxFmt = v => v == null ? "—" : v >= 1000 ? fmt(Math.round(v)) : v >= 1 ? v.toFixed(2).replace(".", ",") : v.toPrecision(3).replace(".", ",");
const usdFmt = v => v == null ? "" : "$" + (v >= 1000 ? fmt(Math.round(v)) : v >= 1 ? v.toFixed(2) : v.toPrecision(3));
const qtyFmt = v => !v ? "0" : v >= 1000 ? fmt(Math.round(v)) : v >= 1 ? (+v.toFixed(4)).toString().replace(".", ",") : v.toLocaleString("en", { maximumSignificantDigits: 4, useGrouping: false }).replace(".", ",");
const pctFmt = v => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2).replace(".", ",") + "%";
// логотип монеты (PNG в web/coins), пока грузится — цветной кружок со знаком
const coinBadge = (a, s = 40) => `<span class="cbadge" style="--c:${a.color};--s:${s}px">${a.glyph}<img src="coins/${a.id}.png?v=1" alt="" onerror="this.remove()"></span>`;
// мини-график за 24 ч: линия цвета роста/падения + лёгкая заливка
function spark(vals, up, w = 64, h = 26) {
  if (!vals || vals.length < 2) return `<svg class="spark" viewBox="0 0 ${w} ${h}"></svg>`;
  const lo = Math.min(...vals), hi = Math.max(...vals), sp = hi - lo || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(1)},${(2 + (1 - (v - lo) / sp) * (h - 4)).toFixed(1)}`).join(" ");
  return `<svg class="spark ${up ? "up" : "dn"}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polygon points="0,${h} ${pts} ${w},${h}"/><polyline points="${pts}"/></svg>`;
}

let cxPoll = null;
async function loadCX() {
  try { CX = await api("crypto"); } catch (e) { return; }
  if (TAB === "crypto") fillCX();
}
// вкладка «Крипта»: портфель, рынок, топ; пока вкладка открыта — курсы каждые 10 с
TAB_RENDER.crypto = async function () {
  const v = $("#v-crypto");
  if (!CX) v.innerHTML = emptyHTML("hourglass", "Загружаем курсы…");
  await loadCX();
  clearInterval(cxPoll);
  cxPoll = setInterval(() => TAB === "crypto" ? bgOff() || loadCX() : clearInterval(cxPoll), 10000);
};
let CX_PREV = {};
function fillCX() {
  const v = $("#v-crypto");
  if (!CX || !v) return;
  // какие монеты подорожали/подешевели с прошлого обновления — подсветим строки
  const moved = {};
  CX.assets.forEach(a => { const p = CX_PREV[a.id]; if (p && a.price && Math.abs(a.price - p) / p > 1e-6) moved[a.id] = a.price > p ? "fl-up" : "fl-dn"; CX_PREV[a.id] = a.price; });
  const pl = CX.total - CX.cost, mine = CX.assets.filter(a => a.qty && a.value >= 0.5).sort((x, y) => y.value - x.value);
  const movers = [...CX.assets].filter(a => a.id !== "USDT").sort((x, y) => y.change - x.change);
  const best = movers[0], worst = movers[movers.length - 1];
  const mover = (a, t) => `<div class="cxmv tap" data-act="cx-open" data-id="${a.id}"><div class="cxmv-h">${coinBadge(a, 30)}<span>${t}</span></div>
    <b>${a.id}</b><em class="${a.change >= 0 ? "up" : "dn"}">${pctFmt(a.change)}</em>${spark(a.spark, a.change >= 0, 120, 34)}</div>`;
  v.innerHTML = `
    <div class="cxhero2">
      <span class="cx-lbl">Портфель</span>
      <b class="cx-tot">⭐ ${fmt(Math.round(CX.total))}</b>
      ${CX.cost ? `<div class="cx-pl ${pl >= 0 ? "up" : "dn"}">${ic("trend")}${pl >= 0 ? "+" : "−"}⭐ ${fmt(Math.abs(Math.round(pl)))} · ${pctFmt(pl / CX.cost * 100)} <span>за всё время</span></div>` : ""}
      ${mine.length ? `<div class="cx-alloc">${mine.map(a => `<i style="flex:${a.value};--c:${a.color}"></i>`).join("")}</div>
        <div class="cx-leg">${mine.slice(0, 4).map(a => `<span><i style="--c:${a.color}"></i>${a.id} ${Math.round(a.value / CX.total * 100)}%</span>`).join("")}</div>`
        : `<p class="cx-empty">Курсы настоящие — с биржи OKX. Купи монету за звёзды и следи, как рынок двигает твой портфель.</p>
           <button class="btn cta cx-start" data-act="cx-open" data-id="GRAM">${coinBadge(CX.assets.find(a => a.id === "GRAM"), 24)}Купить Gram</button>`}
    </div>
    <div class="cxmvs">${mover(best, "Лучший за 24 ч").replace('class="cxmv ', 'class="cxmv best ')}${mover(worst, "Худший за 24 ч").replace('class="cxmv ', 'class="cxmv worst ')}</div>
    ${mine.length ? `<div class="sec-t">${ic("wallet")}Мои монеты</div>
      <div class="box">${mine.map(a => { const p = a.value - a.cost; return `<div class="row tap cxrow" data-act="cx-open" data-id="${a.id}">${coinBadge(a)}
        <div class="grow"><div class="t">${esc(a.name)}</div><div class="s">${qtyFmt(a.qty)} ${a.id}</div></div>
        <div class="cx-px"><b>⭐ ${fmt(Math.round(a.value))}</b><span class="${p >= 0 ? "tw" : "tl"}">${p >= 0 ? "+" : "−"}${short(Math.abs(Math.round(p)))} · ${pctFmt(a.cost ? p / a.cost * 100 : 0)}</span></div></div>`; }).join("")}</div>` : ""}
    <div class="sec-t">${ic("trend")}Рынок</div>
    <div class="box">${CX.assets.map(a => `<div class="row tap cxrow ${moved[a.id] || ""}" data-act="cx-open" data-id="${a.id}">${coinBadge(a)}
      <div class="grow cx-nm"><div class="t">${esc(a.name)}</div><div class="s">${a.id} · ${usdFmt(a.usd)}</div></div>
      ${spark(a.spark, a.change >= 0)}
      <div class="cx-px"><b>⭐ ${pxFmt(a.price)}</b><em class="${a.change >= 0 ? "up" : "dn"}">${pctFmt(a.change)}</em></div></div>`).join("")}</div>
    ${CX.top.length ? `<div class="sec-t">${ic("crown")}Крупнейшие портфели</div>
      <div class="box">${CX.top.map((u, i) => `<div class="row tap" data-act="profile" data-id="${u.id}"><span class="place p${i + 1}">${i + 1}</span>${avaHTML(u, 34)}
        <div class="grow"><div class="t">${esc(u.name)}</div></div><b>⭐ ${short(u.value)}</b></div>`).join("")}</div>` : ""}
    <div class="disc">Курсы реальные (OKX), обновляются каждые 10 секунд, графики — за 24 часа. 1 ⭐ = $${String(CX.starUsd).replace(".", ",")}. Комиссия ${String(CX.fee * 100).replace(".", ",")}% с каждой сделки. Монеты игровые: вывести или перевести их на настоящий кошелёк нельзя. ${esc(ME.disclaimer)}</div>`;
}

// ------------------------------------------------------------ монета
async function openCA(id) {
  H.imp("light");
  const el = openSheet(`<div id="ca-body">${emptyHTML("hourglass", "Загружаем график…")}</div>`, "ca-s");
  el._ca = id;
  await loadCA(id);
  el._t = setInterval(() => el.isConnected ? bgOff() || loadCA(id, true) : clearInterval(el._t), 10000);
}
async function loadCA(id, soft) {
  try { CA = await api(`crypto/${id}?r=${cxRange}`); } catch (e) { return; }
  for (const s of SHEETS) if (s._ca === id) soft && s.querySelector(".ca-trade") ? paintCALive(s) : fillCA(s);
}
function caChart(pts, color) {
  if (pts.length < 2) return `<div class="hint bk-empty">График недоступен</div>`;
  const W = 320, Hc = 150, vs = pts.map(p => p[1]), lo = Math.min(...vs), hi = Math.max(...vs), span = hi - lo || hi * 0.01 || 1;
  const X = i => i / (pts.length - 1) * W, Y = v => 8 + (1 - (v - lo) / span) * (Hc - 16);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
  return `<div class="ca-ch" data-n="${pts.length}"><svg viewBox="0 0 ${W} ${Hc}" preserveAspectRatio="none">
      <defs><linearGradient id="cag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".35"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
      <path d="${line}L${W},${Hc}L0,${Hc}Z" fill="url(#cag)"/><path d="${line}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
      <line class="ca-x" x1="0" x2="0" y1="0" y2="${Hc}" vector-effect="non-scaling-stroke"/></svg>
    <div class="ca-tip"></div><span class="ca-hi">${pxFmt(hi)}</span><span class="ca-lo">${pxFmt(lo)}</span></div>`;
}
// перекрестие: палец/мышь над графиком показывает цену и время
function caBindChart(el) {
  const box = el.querySelector(".ca-ch"); if (!box || !CA) return;
  const pts = CA.chart, line = box.querySelector(".ca-x"), tip = box.querySelector(".ca-tip");
  const show = e => {
    const r = box.getBoundingClientRect(), k = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    const i = Math.round(k * (pts.length - 1)), p = pts[i], x = i / (pts.length - 1) * 320;
    line.setAttribute("x1", x); line.setAttribute("x2", x); box.classList.add("hov");
    const d = new Date(p[0] * 1000);
    tip.innerHTML = `<b>⭐ ${pxFmt(p[1])}</b><span>${d.toLocaleDateString("ru", { day: "numeric", month: "short" })} ${d.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}</span>`;
    tip.style.left = Math.max(4, Math.min(r.width - tip.offsetWidth - 4, k * r.width - tip.offsetWidth / 2)) + "px";
  };
  box.onpointermove = show; box.onpointerdown = show;
  box.onpointerleave = () => box.classList.remove("hov");
}
function caHold() {
  const v = CA.qty * (CA.price || 0), pl = v - CA.cost;
  return CA.qty ? `<div class="bks-top"><div><span>У тебя</span><b>${qtyFmt(CA.qty)}</b></div><div><span>Стоимость</span><b>⭐ ${short(Math.round(v))}</b></div>
      <div><span>Прибыль</span><b class="${pl >= 0 ? "tw" : "tl"}">${pl >= 0 ? "+" : "−"}${short(Math.abs(Math.round(pl)))}</b></div></div>
      <div class="bks-row"><span>Средняя цена покупки</span><b>⭐ ${pxFmt(CA.cost / CA.qty)}</b></div>` : `<div class="hint" style="font-size:13px">У тебя пока нет ${CA.id}. Купи на звёзды — дальше всё решает рынок.</div>`;
}
function fillCA(el) {
  if (!CA || !el.isConnected) return;
  const a = CA;
  el.querySelector("#ca-body").innerHTML = `
    <div class="cahead">${coinBadge(a, 52)}<div class="grow"><h2>${esc(a.name)} <span class="cx-sym">${a.id}</span></h2>
      <div class="ca-live"><b>⭐ ${pxFmt(a.price)}</b><em class="${a.change >= 0 ? "up" : "dn"}">${pctFmt(a.change)}</em></div><span class="ca-usd">${usdFmt(a.usd)} · за 24 ч</span></div></div>
    <div class="seg ca-rng">${[["1d", "День"], ["7d", "Неделя"], ["30d", "Месяц"]].map(([k, t]) => `<button data-act="ca-rng" data-v="${k}" class="${k === cxRange ? "on" : ""}">${t}</button>`).join("")}</div>
    <div class="inccard">${caChart(a.chart, a.color)}</div>
    <div class="inccard ca-hold" style="margin-top:10px">${caHold()}</div>
    <div class="inccard ca-trade" style="margin-top:10px">
      <div class="seg"><button data-act="ca-side" data-v="buy" class="${cxSide === "buy" ? "on" : ""}">Купить</button><button data-act="ca-side" data-v="sell" class="${cxSide === "sell" ? "on" : ""}">Продать</button></div>
      <div id="ca-form"></div></div>
    ${a.tx.length ? `<div class="sec-t">${ic("clock")}Твои сделки</div><div class="box">${a.tx.map(t => `<div class="row"><span class="pic ${t.side === "buy" ? "g" : "r"}">${ic(t.side === "buy" ? "plus" : "coins")}</span>
      <div class="grow"><div class="t">${{ buy: "Покупка", sell: "Продажа", swap: "Обмен", swapin: "Получено обменом" }[t.side] || t.side} ${qtyFmt(t.qty)} ${a.id}</div><div class="s">по ⭐ ${pxFmt(t.price)} · ${new Date(t.ts * 1000).toLocaleString("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div></div>
      <b class="${t.side === "buy" ? "tl" : t.side === "sell" ? "tw" : ""}">${t.side === "buy" ? "−" : t.side === "sell" ? "+" : "≈ "}⭐ ${short(t.stars)}</b></div>`).join("")}</div>` : ""}
    <div class="disc">Курс с биржи OKX, 1 ⭐ = $0,015. Комиссия ${String(a.fee * 100).replace(".", ",")}% при покупке и продаже. Монеты игровые, вывести нельзя.</div>`;
  caBindChart(el); caForm(el);
}
// тихое обновление раз в 10 с: цена, позиция, форма — без перерисовки графика
function paintCALive(el) {
  const a = CA, live = el.querySelector(".ca-live");
  if (live) live.innerHTML = `<b>⭐ ${pxFmt(a.price)}</b><em class="${a.change >= 0 ? "up" : "dn"}">${pctFmt(a.change)}</em>`;
  const u = el.querySelector(".ca-usd"); if (u) u.textContent = `${usdFmt(a.usd)} · за 24 ч`;
  const h = el.querySelector(".ca-hold"); if (h) h.innerHTML = caHold();
  caForm(el, true);
}
function caForm(el, soft) {
  const f = el.querySelector("#ca-form"); if (!f || !CA) return;
  const a = CA;
  if (cxSide === "buy") {
    const max = Math.max(0, ME.stars);
    if (!soft) cxAmt = Math.min(cxAmt, max) || Math.min(1000, max);
    const get = cxAmt * (1 - a.fee) / (a.price || 1);
    f.innerHTML = `<div class="ca-in"><span>⭐</span><input id="ca-amt" type="number" inputmode="numeric" min="${a.min}" value="${cxAmt}"><small>≈ ${qtyFmt(get)} ${a.id}</small></div>
      <div class="quick">${[100, 1000, 10000].map(v => `<button data-act="ca-amt" data-v="${v}">${short(v)}</button>`).join("")}<button data-act="ca-amt" data-v="max">MAX</button></div>
      <button class="btn cta green ca-go" data-act="ca-buy" ${cxAmt < a.min ? "disabled" : ""}>Купить ${a.id} за ⭐ ${fmt(cxAmt)}</button>`;
    const inp = f.querySelector("#ca-amt");
    inp.oninput = () => { cxAmt = Math.max(0, Math.floor(+inp.value || 0)); const b = f.querySelector(".ca-go"); b.disabled = cxAmt < a.min; b.innerHTML = `Купить ${a.id} за ⭐ ${fmt(cxAmt)}`; f.querySelector(".ca-in small").textContent = `≈ ${qtyFmt(cxAmt * (1 - a.fee) / (a.price || 1))} ${a.id}`; };
  } else {
    const got = p => Math.floor(a.qty * p / 100 * (a.price || 0) * (1 - a.fee));
    f.innerHTML = a.qty ? `<div class="ca-sell">${[25, 50, 100].map(p => `<button class="btn ${p === 100 ? "red" : "ghost"}" data-act="ca-sell" data-v="${p}"><b>${p === 100 ? "Всё" : p + "%"}</b><span>+⭐ ${short(got(p))}</span></button>`).join("")}</div>`
      : `<div class="hint" style="font-size:13px;text-align:center;padding:8px 0">Продавать пока нечего</div>`;
  }
}
Object.assign(ACT, {
  "cx-open": el => openCA(el.dataset.id),
  "ca-rng": async el => { cxRange = el.dataset.v; H.sel(); const s = topSheet(); await loadCA(s._ca); },
  "ca-side": el => { cxSide = el.dataset.v; H.sel(); const s = topSheet(); s.querySelectorAll(".ca-trade .seg button").forEach(b => b.classList.toggle("on", b === el)); caForm(s); },
  "ca-amt": el => { cxAmt = el.dataset.v === "max" ? Math.max(0, ME.stars) : +el.dataset.v; H.sel(); caForm(topSheet(), true); },
  "ca-buy": async el => {
    if (cxAmt > ME.stars) return toast("Не хватает звёзд ⭐");
    el.disabled = true;
    try {
      const r = await post(`crypto/${CA.id}/buy`, { stars: cxAmt });
      setStars(r.stars); H.ok(); toast(`Куплено ${qtyFmt(r.qty)} ${CA.id}`, "ok"); burstAt(el);
    } finally { el.disabled = false; }
    await loadCA(CA.id); loadCX();
  },
  "ca-sell": async el => {
    el.disabled = true;
    try {
      const r = await post(`crypto/${CA.id}/sell`, { pct: +el.dataset.v });
      setStars(r.stars); H.ok(); toast(`Продано · +⭐ ${fmt(r.got)}`, "ok");
    } finally { el.disabled = false; }
    await loadCA(CA.id); loadCX();
  },
});

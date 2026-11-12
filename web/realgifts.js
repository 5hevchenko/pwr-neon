"use strict";
// ============================================================
//  Кейсы с настоящими подарками Telegram (server/realgifts.py) и пополнение криптой (server/cryptopay.py).
//  Приз из такого кейса лежит в своей сумке: его можно продать игре за полную цену или вывести на аккаунт Telegram.
// ============================================================
let RG = null, RG_BUSY = false, RG_ADM = null, RG_WON = 0;
const rgUsd = v => "$" + (v < 100 ? v.toFixed(2) : Math.round(v));
const rgPct = p => (p >= 10 ? p.toFixed(0) : p >= 1 ? p.toFixed(1) : p >= 0.01 ? p.toFixed(2) : p.toFixed(4)).replace(".", ",") + "%";
const rgArt = (x, cls = "") => `<span class="rg-art${cls ? " " + cls : ""}">${x.kind === "nft" ? `<img src="${A.orig(x.ref, 256)}" alt="" loading="lazy">`
  : x.img ? `<img src="api/realgifts/img/${x.ref}" alt="" loading="lazy">` : `<i>${esc(x.emoji || "🎁")}</i>`}</span>`;
const rgCost = x => x.usd || x.value * RG.usdK;
async function rgLoad() { RG = await api("realgifts"); return RG; }

// ---------------- витрина ----------------
function rgCaseCard(c) {
  return `<button class="rg-case" data-act="rg-case" data-id="${c.id}">
    <span class="rg-fan">${c.items.slice(0, 3).map(x => rgArt(x)).join("")}</span>
    <span class="rg-ct"><b>${esc(c.title)}</b><small>${c.items.length} ${plural(c.items.length, ["приз", "приза", "призов"])} · до ⭐ ${short(c.items[0].value)}</small></span>
    <span class="rg-pr">⭐ ${short(c.price)}</span></button>`;
}
function rgLimitHTML() {
  const d = RG;
  if (!d.limit && !d.held) return `<div class="rg-lim"><b>Вывод откроется после первой покупки звёзд</b><span>Вывести можно подарков на сумму до ${d.limitK}% от твоих покупок. До этого любой приз можно продать игре за полную цену.</span></div>`;
  return `<div class="rg-lim"><b>Можно вывести на ${rgUsd(d.left)}</b><span>Лимит — ${d.limitK}% от покупок: ${rgUsd(d.limit)}, уже выведено ${rgUsd(d.used)}.${d.held ? ` Ещё ${rgUsd(d.held)} добавится через ${d.holdHours} ч после оплаты.` : ""}</span></div>`;
}
function rgBagHTML() {
  if (!RG.bag.length) return `<div class="rg-empty">Здесь будут выигранные подарки. Приз лежит у тебя, пока ты сам не решишь — вывести его в Telegram или продать игре.</div>`;
  return `<div class="rg-bag">${RG.bag.map(x => {
    const busy = x.status !== "bag";
    return `<div class="rg-it${busy ? " busy" : ""}">${rgArt(x)}<div class="rg-in"><b>${esc(x.title)}</b><small>${busy ? esc(x.text) : `⭐ ${fmt(x.value)} · ${rgUsd(rgCost(x))}`}</small></div>
      ${busy ? "" : `<div class="rg-acts"><button class="btn ghost" data-act="rg-sell" data-id="${x.id}">Продать</button><button class="btn cta" data-act="rg-out" data-id="${x.id}">Вывести</button></div>`}</div>`;
  }).join("")}</div>`;
}
function rgHubHTML() {
  const d = RG;
  if (!d.on) return `<div class="rg-empty">Кейсы с настоящими подарками пока выключены.</div>`;
  const hist = d.history.length ? `<div class="sec-t">История</div><div class="rg-hist">${d.history.map(x => `<div class="rg-row">${rgArt(x)}<div class="grow"><b>${esc(x.title)}</b><small>${esc(x.text)}</small></div><em>⭐ ${short(x.value)}</em></div>`).join("")}</div>` : "";
  return `<p class="rg-lead">В этих кейсах лежат настоящие подарки Telegram. Выигранный подарок можно вывести на свой аккаунт или продать игре за полную цену.</p>
    ${d.cases.length ? `<div class="rg-cases">${d.cases.map(rgCaseCard).join("")}</div>` : `<div class="rg-empty">Обновляем цены подарков — кейсы появятся через несколько минут.</div>`}
    ${d.nftSoon ? `<div class="hint" style="margin-top:10px">Кейсы с коллекционными подарками появятся позже.</div>` : ""}
    <div class="sec-t">Мои подарки</div>${rgLimitHTML()}${rgBagHTML()}${hist}
    ${ME && ME.admin ? `<div class="sec-t">Для админа</div><div id="rg-adm" class="rg-adm">${RG_ADM ? rgAdmHTML() : `<button class="btn ghost" data-act="rg-adm">Показать состояние</button>`}</div>` : ""}`;
}
function rgCaseHTML(c) {
  return `<h2 class="gtitle">${esc(c.title)}</h2>
    <div class="rg-hero"><span class="rg-fan big">${c.items.slice(0, 3).map(x => rgArt(x)).join("")}</span></div>
    <div id="rg-roul"></div><div id="rg-won"></div>
    <div class="btns" id="rg-btns"><button class="btn cta" data-act="rg-spin" data-id="${c.id}">Открыть за ⭐ ${fmt(c.price)}</button></div>
    <div class="sec-t">Что внутри</div>
    <div class="rg-list">${c.items.map(x => `<div class="rg-row">${rgArt(x)}<div class="grow"><b>${esc(x.title)}</b><small>⭐ ${fmt(x.value)} · ${rgUsd(x.value * RG.usdK)}</small></div><em>${rgPct(x.p)}</em></div>`).join("")}</div>
    <p class="hint">Цена кейса и шансы считаются от текущих цен подарков и обновляются вместе с ними. В среднем кейс возвращает призами ${RG.rtp}% своей цены.
      ${c.nft ? "Коллекционный подарок покупается на рынке в момент вывода: модель и фон будут как у самого доступного предложения. " : ""}Вывести можно подарков на сумму до ${RG.limitK}% от твоих покупок${RG.left ? ` — сейчас это ${rgUsd(RG.left)}` : ""}; продать приз игре за полную цену можно всегда.</p>`;
}
function rgRepaint() {
  const b = document.getElementById("rg-body"); if (b) b.innerHTML = rgHubHTML();
  rgStrip();
}
// блок в начале вкладки «Кейсы»
function rgStrip() {
  const v = $("#v-cases"); if (!v) return;
  const old = v.querySelector(".rg-strip"), ok = RG && RG.on && RG.cases.length;
  const html = ok ? `<div class="rg-strip"><div class="sec-t">Настоящие подарки<button class="rg-more" data-act="rg-open">Мои подарки${RG.bag.length ? ` · ${RG.bag.length}` : ""}</button></div><div class="rg-cases">${RG.cases.map(rgCaseCard).join("")}</div></div>` : "";
  if (old) { if (old.outerHTML !== html) old.outerHTML = html; return; }
  const at = v.querySelector(".pp-banner") || v.querySelector(".ctabs") || v.querySelector(".cases");
  if (html && at) at.insertAdjacentHTML("beforebegin", html);
}
const _rcRg = renderCases;
renderCases = async function () {
  await _rcRg();
  rgStrip();
  if (!RG) rgLoad().then(rgStrip).catch(() => {});
};

// ---------------- открытие ----------------
async function rgSpin(el) {
  if (RG_BUSY) return;
  const c = RG.cases.find(x => x.id === el.dataset.id), sheet = el.closest(".sheet"); if (!c || !sheet) return;
  if (c.price > ME.stars) { H.err(); return typeof openQuickBuy === "function" ? openQuickBuy(c.price - ME.stars) : toast("Не хватает звёзд ⭐"); }
  const roul = sheet.querySelector("#rg-roul"), won = sheet.querySelector("#rg-won"), btns = sheet.querySelector("#rg-btns");
  RG_BUSY = true; btns.querySelectorAll("button").forEach(b => b.disabled = true); won.innerHTML = "";
  const hero = sheet.querySelector(".rg-hero"); if (hero) hero.remove();
  let r;
  try { r = await post(`realgifts/case/${c.id}/open`, { price: c.price }); }
  catch (e) {   // цена могла обновиться: перечитываем кейс и показываем новую
    RG_BUSY = false;
    try { await rgLoad(); const n = RG.cases.find(x => x.id === c.id); if (n) replaceSheet(sheet, rgCaseHTML(n)); else { closeSheet(); toast("Кейс на паузе: обновляем цены"); } } catch (e2) {}
    return;
  }
  const item = r.item; RG = r; RG_WON = item.id; setStars(r.stars);
  try {
    const W = 104, step = W + 8;
    roul.innerHTML = `<div class="roul"><div class="mark"></div><div class="strip">${r.strip.map(x => `<div class="it rg-tile" style="width:${W}px">${rgArt(x)}<small>⭐ ${short(x.value)}</small></div>`).join("")}</div></div>`;
    roul.scrollIntoView({ behavior: "smooth", block: "center" });
    await Promise.race([Promise.all([...roul.querySelectorAll("img")].map(i => i.decode().catch(() => {}))), sleep(1500)]);
    const strip = roul.querySelector(".strip"), cw = roul.querySelector(".roul").clientWidth;
    const target = r.win * step + W / 2 - cw / 2 + (Math.random() - .5) * W * .6, dur = 5200, t0 = performance.now();
    let last = -1;
    await new Promise(done => (function f(now) {
      const t = Math.min(1, (now - t0) / dur), x = target * (1 - Math.pow(1 - t, 4));
      strip.style.transform = `translateX(${-x}px)`;
      const idx = Math.floor((x + cw / 2) / step);
      if (idx !== last) { const it = strip.children; if (it[last]) it[last].classList.remove("cur"); if (it[idx]) it[idx].classList.add("cur"); last = idx; H.sel(); }
      t < 1 && sheet.isConnected ? requestAnimationFrame(f) : done();
    })(t0));
    if (!sheet.isConnected) return;
    const w = strip.children[r.win]; if (w) { w.classList.remove("cur"); w.classList.add("hitw"); }
    H.imp("heavy"); await sleep(500);
    won.innerHTML = `<div class="rg-won">${rgArt(item, "big")}<b>${esc(item.title)}</b><small>⭐ ${fmt(item.value)} · ${rgUsd(rgCost(item))}</small><p>Подарок в сумке. Забери его в Telegram или продай игре.</p></div>`;
    const n = RG.cases.find(x => x.id === c.id);
    btns.innerHTML = `<button class="btn ghost" data-act="rg-sell" data-id="${item.id}">Продать ⭐ ${short(item.value)}</button><button class="btn ghost" data-act="rg-out" data-id="${item.id}">Вывести</button>`
      + (n ? `<button class="btn cta rg-again" data-act="rg-spin" data-id="${n.id}">Открыть ещё за ⭐ ${short(n.price)}</button>` : "");
    won.scrollIntoView({ behavior: "smooth", block: "center" }); H.ok();
  } finally { RG_BUSY = false; rgStrip(); }
}
// после продажи или вывода приза, показанного в окне кейса, — убрать его кнопки
function rgAfter(id, text) {
  const won = document.getElementById("rg-won"), btns = document.getElementById("rg-btns");
  if (won && btns && RG_WON === id) {
    const p = won.querySelector("p"); if (p) p.textContent = text;
    btns.querySelectorAll('[data-act="rg-sell"],[data-act="rg-out"]').forEach(b => b.remove());
    RG_WON = 0;
  }
  rgRepaint();
}

// ---------------- админ ----------------
const rgAge = s => s == null ? "нет данных" : s < 90 ? "только что" : s < 5400 ? Math.round(s / 60) + " мин назад" : Math.round(s / 3600) + " ч назад";
function rgAdmHTML() {
  const a = RG_ADM, row = (k, v) => `<div class="rg-kv"><span>${k}</span><b>${v}</b></div>`;
  return `<div class="rg-list">
      ${row("Баланс бота", a.botStars == null ? "нет данных" : fmt(a.botStars) + " Telegram Stars")}
      ${row("Обычные подарки в продаже", `${a.catalog} · ${rgAge(a.catalogAge)}`)}
      ${row("Площадка Tonnel", !a.tonnelLib ? "библиотека не установлена" : !a.tonnelSession ? "нет сессии (TONNEL_AUTH)" : a.tonnelErr ? "сессия не принята" : a.tonnelBal == null ? "проверяем" : a.tonnelBal.toFixed(2) + " TON")}
      ${row("Коллекционные в кейсах", a.nftMode === "off" ? "выключены" : a.nftReady ? (a.nftMode === "manual" ? "да, выдача вручную" : "да") : "нет")}
      ${row("Курс TON", a.ton ? `$${a.ton.toFixed(3)} · ${rgAge(a.tonAge)}` : "нет данных")}
      ${row("Цены с площадки", `${a.prices.length} из ${a.prices.length + a.noPrice.length}`)}
      ${row("Открыто кейсов", `${fmt(a.opened.n)} · оплачено ⭐ ${short(a.opened.paid)} · выпало ⭐ ${short(a.opened.value)}`)}
      ${row("Выведено подарков", `${a.sent.n} на ${rgUsd(a.sent.usd)}`)}
    </div>
    ${a.pending.length ? `<div class="sec-t">Заявки на ручной проверке</div>${a.pending.map(p => `<div class="rg-it"><div class="rg-in"><b>№${p.id} · ${esc(p.title)} · ${rgUsd(p.usd)}</b><small>игрок ${p.user} · ${esc(p.note)}</small></div>
        <div class="rg-acts"><button class="btn ghost" data-act="rg-adm-back" data-id="${p.id}">Вернуть в сумку</button><button class="btn cta" data-act="rg-adm-done" data-id="${p.id}">Подарок выдан</button></div></div>`).join("")}` : ""}
    <div class="btns"><button class="btn ghost" data-act="rg-adm-refresh">Обновить цены сейчас</button></div>`;
}
function rgAdmPaint() { const e = document.getElementById("rg-adm"); if (e) e.innerHTML = rgAdmHTML(); }

Object.assign(ACT, {
  "rg-open": async () => {
    H.imp("light");
    openSheet(`<h2 class="gtitle">Настоящие</h2><div id="rg-body"><div class="hint" style="padding:18px;text-align:center">Загрузка…</div></div>`, "rg-s");
    await rgLoad(); rgRepaint();
  },
  "rg-case": async el => {
    H.imp("light");
    if (!RG) await rgLoad();
    const c = RG.cases.find(x => x.id === el.dataset.id); if (!c) return toast("Кейс на паузе: обновляем цены");
    RG_WON = 0; openSheet(rgCaseHTML(c), "rg-s rg-cs");
    rgLoad().then(() => { const n = RG.cases.find(x => x.id === c.id), sh = document.querySelector(".sheet.rg-cs"); if (n && sh && !RG_BUSY && !RG_WON && n.price !== c.price) replaceSheet(sh, rgCaseHTML(n)); }).catch(() => {});
  },
  "rg-spin": el => rgSpin(el),
  "rg-sell": async el => {
    if (RG_BUSY) return; RG_BUSY = true; el.disabled = true;
    try { const id = +el.dataset.id, r = await post(`realgifts/item/${id}/sell`); RG = r; setStars(r.stars); H.ok(); toast(`Продано за ⭐ ${fmt(r.paid)}`, "ok"); rgAfter(id, "Продан игре — звёзды уже на балансе."); }
    catch (e) { el.disabled = false; } finally { RG_BUSY = false; }
  },
  "rg-out": async el => {
    if (RG_BUSY) return;
    if (!el.dataset.sure) { el.dataset.sure = 1; el.textContent = "Точно вывести?"; setTimeout(() => { if (el.isConnected && el.dataset.sure) { delete el.dataset.sure; el.textContent = "Вывести"; } }, 4000); return; }
    RG_BUSY = true; el.disabled = true; el.textContent = "Отправляем…";
    const id = +el.dataset.id;
    try {
      RG = await post(`realgifts/item/${id}/withdraw`, {}, { timeout: 90000 });
      const x = RG.bag.find(i => i.id === id);
      H.ok(); toast(x ? "Заявка принята — проверим и отправим" : "Подарок отправлен — смотри в профиле Telegram", "ok");
      rgAfter(id, x ? "Отправка проверяется вручную — обычно до суток." : "Отправлен на твой аккаунт Telegram.");
    } catch (e) { delete el.dataset.sure; el.disabled = false; el.textContent = "Вывести"; rgLoad().then(rgRepaint).catch(() => {}); }
    finally { RG_BUSY = false; }
  },
  "rg-adm": async () => { RG_ADM = await api("admin/realgifts"); rgAdmPaint(); },
  "rg-adm-refresh": async el => { el.disabled = true; try { RG_ADM = await post("admin/realgifts/refresh", {}, { timeout: 120000 }); await rgLoad(); rgRepaint(); toast("Цены обновлены", "ok"); } catch (e) { el.disabled = false; } },
  "rg-adm-done": async el => { el.disabled = true; try { RG_ADM = await post(`admin/realgifts/${el.dataset.id}/done`); rgAdmPaint(); } catch (e) { el.disabled = false; } },
  "rg-adm-back": async el => { el.disabled = true; try { RG_ADM = await post(`admin/realgifts/${el.dataset.id}/back`); rgAdmPaint(); } catch (e) { el.disabled = false; } },
});

// ---------------- пополнение криптой: блок в магазине звёзд ----------------
let CP = null, CP_WAIT = 0;
const _sfRg = shopFill;
shopFill = async function () {
  await _sfRg.apply(this, arguments);
  const box = $("#shop-box"), note = box && box.querySelector(".shop-note"); if (!note) return;
  note.querySelector("span").textContent = "Оплата проходит в Telegram, цены — в Telegram Stars. Сами ⭐ не выводятся: на них открывают кейсы и играют.";
  CP = await api("cpay").catch(() => null);
  if (!CP || !CP.on || !note.isConnected || box.querySelector(".cp")) return;
  note.insertAdjacentHTML("beforebegin", `<div class="cp"><div class="sec-t">Криптой — больше звёзд</div>
    <div class="cp-list">${CP.packs.map(p => `<button class="cp-pk" data-act="cp-buy" data-usd="${p.usd}"><b>${short(p.stars)} ⭐</b><small>${p.stars > p.base ? "×2 первая покупка" : p.bonus ? "+" + p.bonus + "% бонус" : "игровых"}</small><em>$${p.usd}</em></button>`).join("")}</div>
    <p class="hint">Оплата в USDT или TON через @CryptoBot. За доллар выходит примерно на 40% больше звёзд, чем за Telegram Stars: у крипты ниже комиссии.</p></div>`);
};
ACT["cp-buy"] = async el => {
  el.disabled = true;
  try {
    const r = await post("cpay/invoice", { usd: +el.dataset.usd });
    if (inTg && tg.openTelegramLink && /^https:\/\/t\.me\//.test(r.url)) tg.openTelegramLink(r.url); else if (inTg && tg.openLink) tg.openLink(r.url); else window.open(r.url, "_blank");
    toast("Счёт открыт в @CryptoBot. Звёзды придут сразу после оплаты");
    const my = ++CP_WAIT;
    for (let i = 0; i < 200 && my === CP_WAIT; i++) {   // ждём оплату до 10 минут; дальше начислит сервер и напишет бот
      await sleep(3000);
      const s = await api("cpay/check", { id: r.id }, { quiet: true }).catch(() => null);
      if (s && s.status === "paid") { setStars(s.stars); H.ok(); toast("Оплата прошла — звёзды на балансе", "ok"); coinShower($("#bal"), 60); loadMe().catch(() => {}); shopFill(); break; }
      if (s && s.status !== "active") break;
    }
  } catch (e) {} finally { el.disabled = false; }
};

"use strict";
// ============================================================
//  Кейсы с настоящими подарками Telegram (server/realgifts.py) и пополнение криптой (server/cryptopay.py).
//  Приз из такого кейса лежит в своей сумке: его можно продать игре за полную цену или вывести на аккаунт Telegram.
// ============================================================
let RG = null, RG_BUSY = false, RG_ADM = null, RG_WON = 0, RG_CASE = null;
const rgUsd = v => "$" + (v < 100 ? v.toFixed(2) : Math.round(v));
const rgPct = p => p >= 10 ? p.toFixed(0) + "%" : p >= 1 ? p.toFixed(1).replace(".", ",") + "%" : p >= 0.01 ? p.toFixed(2).replace(".", ",") + "%" : "1 из " + fmt(Math.round(100 / p));
const rgArt = (x, cls = "") => `<span class="rg-art${cls ? " " + cls : ""}${x.kind === "star" ? " star" : ""}">${x.kind === "nft" ? `<img src="${A.orig(x.ref, 256)}" alt="" loading="lazy">`
  : x.kind === "tg" && x.img ? `<img src="api/realgifts/img/${x.ref}" alt="" loading="lazy">` : `<i>${x.kind === "star" ? "⭐" : esc(x.emoji || "🎁")}</i>`}</span>`;
const rgCost = x => x.usd || x.value * RG.usdK;
const rgName = x => x.kind === "star" ? `${fmt(x.value)} звёзд` : x.title;
async function rgLoad() { RG = await api("realgifts"); return RG; }

// ---------------- сумка призов ----------------
function rgLimitHTML() {
  const d = RG;
  if (!d.limit && !d.held) return `<div class="rg-lim"><b>Вывод откроется после первой покупки звёзд</b><span>Вывести можно подарков на сумму до ${d.limitK}% от твоих покупок. До этого любой приз можно продать игре за полную цену.</span></div>`;
  return `<div class="rg-lim"><b>Можно вывести на ${rgUsd(d.left)}</b><span>Лимит — ${d.limitK}% от покупок: ${rgUsd(d.limit)}, уже выведено ${rgUsd(d.used)}.${d.held ? ` Ещё ${rgUsd(d.held)} добавится через ${d.holdHours} ч после оплаты.` : ""}</span></div>`;
}
function rgBagHTML() {
  if (!RG.bag.length) return `<div class="rg-empty">Здесь будут подарки, выигранные в кейсах. Приз лежит у тебя, пока ты сам не решишь — вывести его в Telegram или продать игре.</div>`;
  return `<div class="rg-bag">${RG.bag.map(x => {
    const busy = x.status !== "bag";
    return `<div class="rg-it${busy ? " busy" : ""}">${rgArt(x)}<div class="rg-in"><b>${esc(x.title)}</b><small>${busy ? esc(x.text) : `⭐ ${fmt(x.value)} · ${rgUsd(rgCost(x))}`}</small></div>
      ${busy ? "" : `<div class="rg-acts"><button class="btn ghost" data-act="rg-sell" data-id="${x.id}">Продать</button><button class="btn cta" data-act="rg-out" data-id="${x.id}">Вывести</button></div>`}</div>`;
  }).join("")}</div>`;
}
function rgHubHTML() {
  const d = RG;
  if (!d.on) return `<div class="rg-empty">Кейсы с подарками пока выключены.</div>`;
  const hist = d.history.length ? `<div class="sec-t">История</div><div class="rg-hist">${d.history.map(x => `<div class="rg-row">${rgArt(x)}<div class="grow"><b>${esc(x.title)}</b><small>${esc(x.text)}</small></div><em>⭐ ${short(x.value)}</em></div>`).join("")}</div>` : "";
  return `<p class="rg-lead">В кейсах лежат настоящие подарки Telegram. Выигранный подарок можно вывести на свой аккаунт или продать игре за полную цену.</p>
    ${rgLimitHTML()}${rgBagHTML()}${hist}
    ${ME && ME.admin ? `<div class="sec-t">Для админа</div><div id="rg-adm" class="rg-adm">${RG_ADM ? rgAdmHTML() : `<button class="btn ghost" data-act="rg-adm">Показать состояние</button>`}</div>` : ""}`;
}
function rgRepaint() {
  const b = document.getElementById("rg-body"); if (b) b.innerHTML = rgHubHTML();
  rgStrip();
}
// вкладка «Кейсы»: кнопка сумки и пометка кейсов, которые ждут цен
function rgStrip() {
  const v = $("#v-cases"); if (!v || !RG || !RG.on) return;
  const html = `<div class="rg-strip"><button class="rg-more" data-act="rg-open">${ic("gift")}Мои подарки${RG.bag.length ? ` · ${RG.bag.length}` : ""}</button><span>Подарки из кейсов настоящие: выводи в Telegram или продавай</span></div>`;
  const old = v.querySelector(".rg-strip");
  if (old) { if (old.outerHTML !== html) old.outerHTML = html; }
  else { const at = v.querySelector(".pp-banner") || v.querySelector(".ctabs") || v.querySelector(".cases"); if (at) at.insertAdjacentHTML("beforebegin", html); }
  v.querySelectorAll(".case[data-id]").forEach(e => e.classList.toggle("rg-wait", RG.ids.includes(e.dataset.id) && !RG.cases[e.dataset.id]));
  rgCovers();
}
// обложка кейса: три лучших подарка кейса парят над цветным фоном (движутся только те, что видны на экране)
let RG_IO = null;
function rgCovers() {
  const v = $("#v-cases"); if (!v) return;
  if (!RG_IO && "IntersectionObserver" in window) RG_IO = new IntersectionObserver(es => es.forEach(e => e.target.classList.toggle("in", e.isIntersecting)), { rootMargin: "80px" });
  v.querySelectorAll(".case[data-id]").forEach(el => {
    const c = CASES.find(x => x.id === el.dataset.id); if (!c || !c.real) return;
    const tops = (RG && RG.cases[c.id] ? RG.cases[c.id].tops : c.tops) || [], art = el.querySelector(".gl-art");
    if (!art || !tops.length) return;
    const key = tops.map(x => x.key).join("|"); if (art.dataset.rg === key) return;
    art.dataset.rg = key; art.classList.add("rg");
    art.innerHTML = `<span class="rg-cv">${tops.map((x, i) => rgArt(x, "f" + i)).join("")}</span>`;
    const m = el.querySelector(".minis"); if (m) m.outerHTML = `<span class="rg-upto">до ⭐ ${short(tops[0].value)}</span>`;
    else { const u = el.querySelector(".rg-upto"); if (u) u.innerHTML = `до ⭐ ${short(tops[0].value)}`; }
    if (RG_IO) RG_IO.observe(art); else art.classList.add("in");
  });
}
const _rcRg = renderCases;
renderCases = async function () {
  await _rcRg();
  rgCovers(); rgStrip();
  if (!RG) rgLoad().then(() => { rgCovers(); rgStrip(); }).catch(() => {});
};

// ---------------- кейс ----------------
function rgBtnHTML(c) {
  if (c.keys) return `<button class="btn cta" data-act="rg-spin" data-id="${c.id}">Открыть ключом · осталось ${c.keys}</button>`;
  if (c.locked) return `<button class="btn ghost" disabled>Откроется на ${c.level} уровне</button>`;
  if (!c.price) return c.freeIn ? `<button class="btn ghost" disabled>Бесплатно через ${clock(c.freeIn)}</button>` : `<button class="btn cta" data-act="rg-spin" data-id="${c.id}">Открыть бесплатно</button>`;
  return `<button class="btn cta" data-act="rg-spin" data-id="${c.id}">Открыть за ⭐ ${fmt(c.price)}</button>`;
}
function rgCaseHTML(c) {
  const gifts = c.items.filter(x => x.kind !== "star"), stars = c.items.filter(x => x.kind === "star");
  const row = x => `<div class="rg-row">${rgArt(x)}<div class="grow"><b>${esc(rgName(x))}</b><small>${x.kind === "star" ? "сразу на баланс" : `⭐ ${fmt(x.value)} · ${rgUsd(x.value * RG.usdK)}`}</small></div><em>${rgPct(x.p)}</em></div>`;
  return `<h2 class="gtitle">${esc(c.title)}</h2>
    <div class="rg-hero"><span class="rg-fan big">${gifts.slice(0, 3).map(x => rgArt(x)).join("")}</span></div>
    <div id="rg-roul"></div><div id="rg-won"></div>
    <div class="btns" id="rg-btns">${rgBtnHTML(c)}</div>
    <div class="sec-t">Подарки<span class="rg-sum">шанс на подарок ${rgPct(c.gift)}</span></div>
    <div class="rg-list">${gifts.map(row).join("")}</div>
    ${stars.length ? `<div class="sec-t">Звёзды</div><div class="rg-list">${stars.map(row).join("")}</div>` : ""}
    <p class="hint">Подарки настоящие: выигранный можно вывести на свой аккаунт Telegram или продать игре за полную цену. Шансы считаются от текущих цен подарков; в среднем кейс возвращает призами ${RG.rtp}% своей цены.
      ${c.nft ? "Коллекционный подарок покупается на рынке в момент вывода: модель и фон будут как у самого доступного предложения. " : ""}Вывести можно подарков на сумму до ${RG.limitK}% от твоих покупок${RG.left ? ` — сейчас это ${rgUsd(RG.left)}` : ""}.</p>`;
}
async function rgOpenCase(id) {
  H.imp("light");
  if (!RG) await rgLoad();
  if (!RG.cases[id]) return toast("Кейс на паузе: обновляем цены подарков");
  let c; try { c = await api(`realgifts/case/${id}`); } catch (e) { return; }
  RG_WON = 0; RG_CASE = c; openSheet(rgCaseHTML(c), "rg-s rg-cs");
}
const _ocRg = openCase;
openCase = function (id) {
  const c = CASES.find(x => x.id === id);
  if (c ? c.real : RG && RG.ids.includes(id)) return rgOpenCase(id);
  return _ocRg.apply(this, arguments);
};

async function rgSpin(el) {
  if (RG_BUSY) return;
  const c = RG_CASE, sheet = el.closest(".sheet"); if (!c || c.id !== el.dataset.id || !sheet) return;
  const pay = c.keys ? 0 : c.price;
  if (pay > ME.stars) { H.err(); return typeof openQuickBuy === "function" ? openQuickBuy(pay - ME.stars) : toast("Не хватает звёзд ⭐"); }
  const roul = sheet.querySelector("#rg-roul"), won = sheet.querySelector("#rg-won"), btns = sheet.querySelector("#rg-btns");
  RG_BUSY = true; btns.querySelectorAll("button").forEach(b => b.disabled = true); won.innerHTML = "";
  const hero = sheet.querySelector(".rg-hero"); if (hero) hero.remove();
  let r;
  try { r = await post(`realgifts/case/${c.id}/open`, { price: c.price }); }
  catch (e) {   // цена или шансы могли обновиться: перечитываем кейс
    RG_BUSY = false;
    try { await rgLoad(); RG_CASE = await api(`realgifts/case/${c.id}`); replaceSheet(sheet, rgCaseHTML(RG_CASE)); } catch (e2) { closeSheet(); }
    return;
  }
  const prize = r.prize, item = r.item; RG = r; RG_CASE = r.case; RG_WON = item ? item.id : 0;
  const before = ME.stars - pay;   // звёзды-приз покажем после рулетки
  setStars(prize.kind === "star" ? before : r.stars);
  if (!c.price) loadMe().catch(() => {});
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
    setStars(r.stars);
    if (!sheet.isConnected) return;
    const w = strip.children[r.win]; if (w) { w.classList.remove("cur"); w.classList.add("hitw"); }
    H.imp(item ? "heavy" : "light"); await sleep(400);
    won.innerHTML = item
      ? `<div class="rg-won">${rgArt(item, "big")}<b>${esc(item.title)}</b><small>⭐ ${fmt(item.value)} · ${rgUsd(rgCost(item))}</small><p>Подарок в сумке. Забери его в Telegram или продай игре.</p></div>`
      : `<div class="rg-won">${rgArt(prize, "big")}<b>${fmt(prize.value)} звёзд</b><p>Уже на балансе.</p></div>`;
    btns.innerHTML = (item ? `<button class="btn ghost" data-act="rg-sell" data-id="${item.id}">Продать ⭐ ${short(item.value)}</button><button class="btn ghost" data-act="rg-out" data-id="${item.id}">Вывести</button>` : "")
      + rgBtnHTML(RG_CASE).replace("Открыть за", "Ещё за").replace('class="btn cta"', 'class="btn cta rg-again"').replace('class="btn ghost" disabled', 'class="btn ghost rg-again" disabled');
    if (item) { won.scrollIntoView({ behavior: "smooth", block: "center" }); H.ok(); }
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
      ${row("Цены коллекционных", a.feed.portals ? `Portals: ${a.feed.portals} · ${a.prices.length} в кейсах` : a.prices.length ? `${a.prices.length} (Tonnel)` : "нет: " + esc(a.feed.portals_err || a.feed.tonnel_err || "ждём первое обновление"))}
      ${row("Курс TON", a.ton ? `$${a.ton.toFixed(3)} · ${rgAge(a.tonAge)}` : "нет данных")}
      ${row("Выдача коллекционных", a.nftMode === "off" ? "выключена" : a.nftAuto ? `сервер покупает на Tonnel · баланс ${a.tonnelBal == null ? "?" : a.tonnelBal.toFixed(2)} TON` : "вручную: заявки приходят тебе" + (a.tonnelSession ? " (сессия Tonnel не принята)" : " (нет TONNEL_AUTH)"))}
      ${row("Кейсы", `${a.cases} работают` + (a.paused.length ? ` · на паузе: ${a.paused.map(p => esc(p.title) + " (" + esc(p.why) + ")").join(", ")}` : ""))}
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
    openSheet(`<h2 class="gtitle">Мои подарки</h2><div id="rg-body"><div class="hint" style="padding:18px;text-align:center">Загрузка…</div></div>`, "rg-s");
    await rgLoad(); rgRepaint();
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
if (typeof i18nAdd === "function" && typeof LANG === "string" && LANG === "en") i18nAdd({
  "Подарок можно продать, улучшить или выставить на маркет.": "You can sell this gift, upgrade it or list it on the market.",
  "Залетай открывать кейсы с подарками Telegram": "Come open cases with Telegram gifts",
  "Мои подарки": "My gifts", "вывод и продажа": "withdraw and sell",
});

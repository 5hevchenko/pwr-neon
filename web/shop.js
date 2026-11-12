"use strict";
// ============================================================
//  Покупка игровых звёзд за Telegram Stars (1 ⭐ Telegram = 1000 игровых). Блок в окне баланса.
// ============================================================
let SHOP = null;
const _openDailyS = openDaily;
openDaily = function (tab) { _openDailyS(tab); shopFill(); };
ICONS.tgplane = '<path d="M21.5 4.2 2.9 11.4c-1 .4-1 1.8 0 2.1l4.6 1.5 1.8 5.6c.2.7 1.1.9 1.6.4l2.6-2.4 4.6 3.4c.6.4 1.4.1 1.6-.6L22.9 5.6c.3-1-.6-1.8-1.4-1.4z" fill="currentColor" stroke="none"/><path d="M7.6 15 18 7.6l-8.3 8.6" stroke="#fff" stroke-width="1.4" fill="none"/>';
// цена в Telegram Stars — компактная таблетка: самолётик + число (подпись «Telegram Stars» — рядом, а не внутри)
const tgPrice = n => `<span class="tgp">${ic("tgplane")}<b>${fmt(n)}</b></span>`;
async function shopFill() {
  const box = $("#shop-box"); if (!box) return;
  SHOP = await api("shop").catch(() => SHOP);
  if (!SHOP || !box.isConnected) return;
  if (!SHOP.on) {   // продажа звёзд выключена в админке: окно — только бонус дня
    box.innerHTML = ""; const sh = box.closest(".sheet"); if (sh) { sh.classList.add("no-shop"); stTab(sh, "daily"); }
    return;
  }
  const last = SHOP.packs.length - 1;
  box.innerHTML = `<div class="shop">
      <div class="shop-h"><span class="shop-rate">${ic("tgplane")}1 Telegram Star = ${fmt(SHOP.rate)} ⭐</span></div>
      ${SHOP.first ? `<div class="shop-first"><b>×2</b><span><b>Первая покупка: вдвое больше звёзд</b>бонус до ${short(SHOP.firstCap)} ⭐</span></div>` : ""}
      <div class="sec-t">${ic("sparkles")}Пакеты звёзд</div>
      <div class="shop-list">${SHOP.packs.map((p, i) => `<button class="pk${i === last ? " best" : ""}${p.bonus ? " hot" : ""}" data-act="buy-pack" data-x="${p.xtr}" style="--lv:${i}">
          ${i === last ? `<i class="pk-tag best">Лучший курс</i>` : p.bonus ? `<i class="pk-tag">+${p.bonus}%</i>` : ""}
          <span class="pk-art">${STAR_SVG}${i >= 2 ? STAR_SVG : ""}${i >= 4 ? STAR_SVG : ""}</span>
          <span class="pk-v"><b>${short(p.stars)}</b><small>игровых ⭐</small>${p.stars > p.base ? `<s>${short(p.base)}</s>` : ""}</span>
          ${tgPrice(p.xtr)}</button>`).join("")}</div>
      <div class="shop-cust">
        <div class="shop-cust-h">Своя сумма</div>
        <div class="shop-c"><span class="tgi">${ic("tgplane")}</span><input id="shop-x" inputmode="numeric" placeholder="От 1 до ${fmt(SHOP.max)} Telegram Stars"></div>
        <div class="shop-cv" id="shop-cv">Введи количество — покажем, сколько игровых ⭐ получишь</div>
        <button class="btn shop-buy" data-act="buy-custom" id="shop-cb" disabled>${ic("tgplane")}Оплатить</button>
      </div>
      <div class="shop-note">${ic("lock")}<span>Оплата проходит в Telegram, цены — в Telegram Stars. Игровые ⭐ нельзя вывести или обменять на настоящие подарки.</span></div></div>`;
  starify(box);
  const inp = box.querySelector("#shop-x"), cv = box.querySelector("#shop-cv"), cb = box.querySelector("#shop-cb");
  inp.oninput = () => {
    const x = Math.floor(+inp.value || 0), ok = x >= 1 && x <= SHOP.max, b = shopBonus(x);
    cv.innerHTML = ok ? `Получишь <b>${fmt(shopStars(x))} ⭐</b>${b ? ` (+${b}% бонус)` : ""}${SHOP.first ? " · ×2 первая покупка" : ""}` : x ? `От 1 до ${fmt(SHOP.max)} Telegram Stars` : "Введи количество — покажем, сколько игровых ⭐ получишь";
    cb.disabled = !ok; cb.innerHTML = `${ic("tgplane")}${ok ? `Оплатить ${fmt(x)}` : "Оплатить"}`;
    starify(cv);
  };
}
// бонус своей суммы — как у ближайшего пакета снизу; первая покупка ×2 (бонус не больше firstCap)
const shopBonus = x => Math.max(0, ...Object.entries(SHOP.bonus).filter(([k]) => x >= +k).map(([, v]) => v));
const shopStars = x => Math.floor(x * SHOP.rate * (1 + shopBonus(x) / 100)) + (SHOP.first ? Math.min(SHOP.firstCap, x * SHOP.rate) : 0);
async function shopBuy(xtr, el) {
  if (!inTg || !tg.openInvoice) return toast("Покупка доступна только в Telegram");
  if (el) el.disabled = true;
  try {
    const r = await post("shop/invoice", { xtr });
    tg.openInvoice(r.link, async status => {
      if (status === "paid") {
        H.ok(); toast("Оплата прошла — звёзды зачисляются", "ok");
        const before = ME.stars;
        for (let i = 0; i < 10 && ME.stars <= before; i++) { await sleep(1200); await loadMe(); }   // ждём начисления от бота
        coinShower($("#bal"), 60); shopFill();   // обновить «×2 первая покупка»; SHOP не обнуляем — поле своей суммы ещё на экране
        if (QB_EL && QB_EL.isConnected && topSheet() === QB_EL) closeSheet();
      } else if (status === "failed") toast("Оплата не прошла");
    });
  } catch (e) {} finally { if (el) el.disabled = false; }
}
Object.assign(ACT, {
  "buy-pack": el => shopBuy(+el.dataset.x, el),
  "buy-custom": el => {
    const x = Math.floor(+$("#shop-x").value || 0);
    if (x < 1 || x > SHOP.max) return toast(`От 1 до ${fmt(SHOP.max)} Telegram Stars`);
    shopBuy(x, el);
  },
});

// ---------------- быстрое пополнение: «Не хватает звёзд» → сразу подходящие пакеты ----------------
let QB_EL = null, QB_T = 0;
async function openQuickBuy(need) {
  if (!inTg || Date.now() - QB_T < 4000 || (QB_EL && QB_EL.isConnected)) return false;
  QB_T = Date.now();
  if (!SHOP) SHOP = await api("shop").catch(() => null);
  if (!SHOP || !SHOP.on) return false;
  const lack = Math.max(1, need ? need - Math.max(0, ME.stars) : 0);
  const packs = SHOP.packs, i = Math.max(0, packs.findIndex(p => p.stars >= lack));
  const pick = packs.slice(i, i + 3).length === 3 ? packs.slice(i, i + 3) : packs.slice(-3);
  QB_EL = openSheet(`<div class="qb-h"><span class="shop-ic">${STAR_SVG}</span><h2>Не хватает звёзд</h2>
      <p>${need ? `Нужно ещё <b>${fmt(lack)} ⭐</b> — пополни и продолжай игру` : "Пополни баланс и продолжай игру"}</p><small class="qb-cur">${ic("tgplane")}цены в Telegram Stars</small></div>
    ${SHOP.first ? `<div class="shop-first"><b>×2</b><span><b>Первая покупка — звёзд вдвое больше</b>бонус до ${short(SHOP.firstCap)} ⭐</span></div>` : ""}
    <div class="qb-list">${pick.map((p, j) => `<button class="qb-p${j === 1 ? " best" : ""}" data-act="buy-pack" data-x="${p.xtr}">
        ${j === 1 ? `<i class="qb-tag">выгоднее</i>` : ""}<b>${short(p.stars)} ⭐</b>${p.bonus ? `<em>+${p.bonus}%</em>` : "<em>&nbsp;</em>"}<span>${tgPrice(p.xtr)}</span></button>`).join("")}</div>
    <button class="btn ghost" data-act="qb-all" style="margin-top:10px">Все пакеты и своя сумма</button>`, "qb-s");
  starify(QB_EL); H.imp("medium");
  return true;
}
const _toastQB = toast;
toast = function (text, kind) {
  const m = typeof text === "string" && /не хватает звёзд|нужно ⭐ ?([\d\s]+)/i.exec(text);
  if (m && inTg && !/казн/i.test(text)) {
    const need = m[1] ? +m[1].replace(/\s/g, "") : 0;
    openQuickBuy(need).then(ok => { if (!ok) _toastQB(text, kind); });
    return;
  }
  return _toastQB(text, kind);
};
ACT["qb-all"] = () => { closeSheet(); openDaily("shop"); };

// ---------------- подарить звёзды другу (платит даритель, звёзды — другу, без «×2 первой покупки») ----------------
ICONS.giftbox = '<rect x="3.5" y="9" width="17" height="11.5" rx="2"/><path d="M2.5 9h19v-3.5h-19z"/><path d="M12 5.5v15"/><path d="M12 5.5C10.5 2.5 6.5 2.5 7 4.5c.4 1.4 3 1 5 1zm0 0c1.5-3 5.5-3 5-1-.4 1.4-3 1-5 1z"/>';
let GF_TO = null;
async function openGiftStars(to) {
  if (!SHOP) SHOP = await api("shop").catch(() => null);
  if (!SHOP || !SHOP.on) return toast("Покупка звёзд сейчас недоступна");
  if (!SHOP) SHOP = await api("shop").catch(() => null);
  const fr = await api("friends").catch(() => null);
  if (!SHOP || !fr) return toast("Не удалось загрузить — попробуй ещё раз");
  if (!fr.friends.length) return toast("Сначала добавь друзей — дарить можно только им");
  GF_TO = fr.friends.some(f => f.id === to) ? to : null;
  const el = openSheet(`<div class="qb-h"><span class="shop-ic gf-ic">${ic("giftbox")}</span><h2>Звёзды в подарок</h2>
      <p>Платишь ты в Telegram Stars — игровые ⭐ сразу уходят другу</p><small class="qb-cur">${ic("tgplane")}цены в Telegram Stars</small></div>
    <div class="gf-step">1. Кому</div>
    <div class="gf-fr">${fr.friends.map(f => `<button class="gf-f${f.id === GF_TO ? " on" : ""}" data-act="gf-pick" data-id="${f.id}">${avaHTML(f, 44)}<span>${esc(f.name)}</span></button>`).join("")}</div>
    <div class="gf-step">2. Сколько</div>
    <div class="qb-list gf-packs">${SHOP.packs.filter(p => p.xtr >= 10).map(p => `<button class="qb-p" data-act="gf-buy" data-x="${p.xtr}">
        <b>${short(p.base)} ⭐</b>${p.bonus ? `<em>+${p.bonus}%</em>` : "<em>&nbsp;</em>"}<span>${tgPrice(p.xtr)}</span></button>`).join("")}</div>
    <div class="hint" style="font-size:11.5px;margin-top:10px;text-align:center">Другу придёт сообщение от бота, что звёзды от тебя.</div>`, "qb-s gf-s");
  starify(el);
}
Object.assign(ACT, {
  "gift-stars": el => openGiftStars(+el.dataset.to || null),
  "gf-pick": el => {
    GF_TO = +el.dataset.id; H.sel && H.sel();
    el.parentElement.querySelectorAll(".gf-f").forEach(b => b.classList.toggle("on", b === el));
  },
  "gf-buy": async el => {
    if (!GF_TO) { toast("Выбери друга"); return el.closest(".sheet")?.querySelector(".gf-fr")?.scrollIntoView({ behavior: "smooth", block: "center" }); }
    if (!inTg || !tg.openInvoice) return toast("Покупка доступна только в Telegram");
    el.disabled = true;
    try {
      const r = await post("shop/invoice", { xtr: +el.dataset.x, to: GF_TO });
      tg.openInvoice(r.link, status => {
        if (status === "paid") { H.ok(); toast("Подарок оплачен — звёзды уже летят другу", "ok"); closeSheet(); }
        else if (status === "failed") toast("Оплата не прошла");
      });
    } catch (e) {} finally { el.disabled = false; }
  },
});
const _shopFillG = shopFill;
shopFill = async function () {
  await _shopFillG();
  const s = $("#shop-box .shop-list");
  if (s && !$("#shop-box .gf-open")) s.insertAdjacentHTML("afterend", `<button class="gf-open" data-act="gift-stars"><span>${ic("giftbox")}</span><b>Подарить звёзды другу</b><small>платишь ты — звёзды сразу у друга</small>${ic("chev")}</button>`);
};

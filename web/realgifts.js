"use strict";
// ============================================================
//  Кейсы с настоящими подарками Telegram (server/realgifts.py) и пополнение криптой (server/cryptopay.py).
//  Приз из такого кейса лежит в своей сумке: его можно продать игре за полную цену или вывести на аккаунт Telegram.
// ============================================================
let RG = null, RG_BUSY = false, RG_ADM = null, RG_WON = 0, RG_CASE = null;
const rgUsd = v => "$" + (v < 100 ? v.toFixed(2) : Math.round(v));
const rgArt = (x, cls = "") => `<span class="rg-art${cls ? " " + cls : ""}${x.kind === "star" ? " star" : ""}">${x.kind === "cover" ? `<img src="${x.src}" alt="" loading="lazy" decoding="async">` : x.kind === "nft" ? `<img src="api/realgifts/art/${encodeURIComponent(x.ref)}" alt="" loading="lazy" decoding="async">`
  : x.kind === "tg" && x.img ? `<img src="api/realgifts/img/${x.ref}" alt="" loading="lazy" decoding="async">` : `<i>${x.kind === "star" ? "⭐" : esc(x.emoji || "🎁")}</i>`}</span>`;
const rgCost = x => x.usd || x.value * RG.usdK;
const rgName = x => x.kind === "star" ? `${fmt(x.value)} звёзд` : x.title;
async function rgLoad() { RG = await api("realgifts"); return RG; }

// ---------------- окно состояния (админ) ----------------
function rgHubHTML() {
  const d = RG;
  const hist = d.history.length ? `<div class="sec-t">Мои последние призы</div><div class="rg-hist">${d.history.map(x => `<div class="rg-row">${rgArt(x)}<div class="grow"><b>${esc(x.title)}</b><small>${esc(x.text)}</small></div><em>⭐ ${short(x.value)}</em></div>`).join("")}</div>` : "";
  return `<div id="rg-adm" class="rg-adm">${RG_ADM ? rgAdmHTML() : `<div class="hint" style="padding:18px;text-align:center">Загрузка…</div>`}</div>${hist}`;
}
function rgRepaint() {
  const b = document.getElementById("rg-body"); if (b) b.innerHTML = rgHubHTML();
  rgStrip();
  if (typeof MYP !== "undefined" && MYP && $("#v-inv") && $("#v-inv").innerHTML) drawInventory();
}
// вкладка «Кейсы»: пометка кейсов, которые ждут цен, и обложки
function rgStrip() {
  const v = $("#v-cases"); if (!v || !RG || !RG.on) return;
  const old = v.querySelector(".rg-strip"); if (old) old.remove();
  v.querySelectorAll(".case[data-id]").forEach(e => e.classList.toggle("rg-wait", RG.ids.includes(e.dataset.id) && !RG.cases[e.dataset.id]));
  rgCovers();
}
// обложка кейса: три лучших подарка кейса парят над цветным фоном (движутся только те, что видны на экране)
let RG_IO = null;
function rgCovers() {
  const v = $("#v-cases"); if (!v) return;
  if (!RG_IO && "IntersectionObserver" in window) RG_IO = new IntersectionObserver(es => es.forEach(e => e.target.classList.toggle("in", e.isIntersecting)), { rootMargin: "80px" });
  v.querySelectorAll(".case[data-id]").forEach(el => {
    const c = CASES.find(x => x.id === el.dataset.id); if (!c) return;
    // кейс подарков — три лучших приза; кейс скинов — его родная обложка, парящая так же
    const tops = c.real ? (RG && RG.cases[c.id] ? RG.cases[c.id].tops : c.tops) || []
      : c.src === "cs" && c.items && c.items.length ? [{ kind: "cover", key: "cv:" + c.cover, src: A.orig(c.cover), value: c.items[0].ev }] : [];
    const art = el.querySelector(".gl-art");
    if (!art || !tops.length) return;
    const key = tops.map(x => x.key).join("|"); if (art.dataset.rg === key) return;
    art.dataset.rg = key; art.classList.add("rg");
    art.innerHTML = `<span class="rg-cv">${tops.map((x, i) => rgArt(x, "f" + i)).join("")}</span>`;
    art.querySelectorAll("img").forEach(im => im.addEventListener("error", () => im.parentElement.remove(), { once: true }));   // картинка не пришла — без дыры на обложке
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
  const gifts = c.items.filter(x => x.kind !== "star");
  const tile = x => `<div class="rg-cell k-${x.kind}">${rgArt(x)}<b>${esc(x.kind === "star" ? "Звёзды" : x.title)}</b><small>⭐ ${short(x.value)}</small></div>`;
  return `<h2 class="gtitle">${esc(c.title)}</h2>
    <div class="rg-hero"><span class="rg-fan big">${gifts.slice(0, 3).map(x => rgArt(x)).join("")}</span></div>
    <div id="rg-roul"></div><div id="rg-won"></div>
    <div class="btns" id="rg-btns">${rgBtnHTML(c)}</div>
    ${!c.price && !c.keys && RG && RG.freeFriends ? `<p class="hint rg-freehint">${ic("lock")}Открыть кейс можно сразу. Чтобы забрать подарок — вывести, продать или поставить в игру, — пригласи друга.</p>` : ""}
    <div class="sec-t">Что внутри</div>
    <div class="rg-grid">${c.items.map(tile).join("")}</div>
    <p class="hint">Подарки настоящие: выигранный можно вывести на свой аккаунт Telegram или продать игре за полную цену.${c.items.some(x => x.kind === "star") ? " Звёзды приходят сразу на баланс." : ""}
      ${c.nft ? "Коллекционный подарок покупается на рынке в момент вывода: модель и фон будут как у самого доступного предложения. " : ""}${RG.freeUsd ? `Без пополнений можно вывести подарков на ${rgUsd(RG.freeUsd)}, дальше лимит растёт с покупками: ${RG.limitK}% от них` : `Вывести можно подарков на сумму до ${RG.limitK}% от твоих покупок`}${RG.left ? ` — сейчас доступно ${rgUsd(RG.left)}` : ""}.</p>
    ${c.price && RG && RG.payer === false ? `<button class="rg-tier" data-act="rg-topup">${ic("trend")}<span>Шансы на дорогие призы выше у игроков с пополнением. Пополни баланс — и они вырастут.</span></button>` : ""}`;
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
  if (!c.price && !c.keys && !el._gateOk) {   // бесплатный кейс: сначала подписка на каналы (друг нужен позже — чтобы забрать подарок)
    let g; try { g = await api(`realgifts/free/${c.id}`); } catch (e) { return; }
    if (!g.ok) return rgGate(c, g);
  }
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
  if (typeof SND !== "undefined") SND.whoosh();   // рулетка поехала
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
      ? `<div class="rg-won">${rgArt(item, "big")}<b>${esc(item.title)}</b><small>⭐ ${fmt(item.value)} · ${rgUsd(rgCost(item))}</small><p>${item.lock ? rgLockText(item) : "Подарок в сумке. Забери его в Telegram, продай или поставь в игре."}</p></div>`
      : `<div class="rg-won">${rgArt(prize, "big")}<b>${fmt(prize.value)} звёзд</b><p>Уже на балансе.</p></div>`;
    btns.innerHTML = (!item ? "" : item.lock ? `<button class="btn gold" data-act="rg-gate-inv">${ic("userPlus")}Пригласить друга</button>`
      : `<button class="btn ghost" data-act="rg-sell" data-id="${item.id}">Продать ⭐ ${short(item.value)}</button><button class="btn ghost" data-act="rg-out" data-id="${item.id}">Вывести</button>`)
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

// ---------------- сумка: фильтр Telegram / CS и подарки из кейсов ----------------
let INVK = "all";
const rgIsCs = g => g.src === "cs";
const _diRg = drawInventory;
drawInventory = function () {
  const p = MYP; if (!p) return _diRg();
  // подарки из кейсов лежат и в общем списке (g.real — чтобы работать во всех играх), в сумке показываем их один раз — своим блоком
  const all = p.gifts.filter(g => !g.real), real = RG && RG.on ? RG.bag : [], full = p.gifts;
  p.gifts = INVK === "all" ? all : all.filter(g => rgIsCs(g) === (INVK === "cs"));
  try { _diRg(); } finally { p.gifts = full; }
  const v = $("#v-inv"); if (!v) return;
  if (real.length) { const st = v.querySelector(".invstart"); if (st) st.classList.add("has"); }   // есть подарки из кейсов — без «Сумка пока пустая», но три шага и кнопку оставляем
  const cs = all.filter(rgIsCs).length, n = { all: all.length + real.length, tg: all.length - cs + real.length, cs };
  const tabs = `<div class="ctabs rg-kind">${[["all", "Все"], ["tg", "Telegram"], ["cs", "CS"]].map(([k, t]) => `<button data-act="rg-kind" data-v="${k}" class="${INVK === k ? "on" : ""}">${t}<em>${n[k]}</em></button>`).join("")}</div>`;
  const mine = INVK !== "cs" && real.length ? `<div class="rg-inv"><div class="sec-t">Из кейсов<span class="rg-sum">${RG.limit || RG.held ? "можно вывести на " + rgUsd(RG.left) : "вывод после первой покупки"}</span></div>
    <div class="rg-grid">${real.map(rgCell).join("")}</div></div>` : "";
  const adm = ME && ME.admin && RG && RG.on ? `<button class="rg-more rg-admbtn" data-act="rg-open">Админ: цены, балансы и заявки на вывод</button>` : "";
  const seg = v.querySelector(".seg"), tool = v.querySelector(".itool");
  if (seg) seg.insertAdjacentHTML("afterend", tabs + (tool ? mine + adm : "")); else v.insertAdjacentHTML("afterbegin", tabs + mine + adm);
};
const _riRg = renderInventory;
renderInventory = async function () {
  await rgLoad().catch(() => {});   // каждый раз: подарок мог уйти на маркет, в игру или к другому игроку
  return _riRg.apply(this, arguments);
};
ACT["rg-kind"] = el => { INVK = el.dataset.v; H.sel(); drawInventory(); };
// карточка подарка из кейса: вывести в Telegram или продать — как у скина CS
const rgFriends = n => n === 1 ? "друга" : `${n} ${plural(n, ["друга", "друзей", "друзей"])}`;
const rgLockText = x => `Подарок из бесплатного кейса под замком. Пригласи ${rgFriends(x.lock)} по своей ссылке — и сможешь вывести его в Telegram, продать или поставить в игре.`;
const rgLockShort = x => x.lock > 1 ? `🔒 друзей: ${x.lock}` : "🔒 нужен друг";
const rgBadge = x => x.status !== "bag" ? "отправляется" : x.lock ? rgLockShort(x) : x.busy === "market" ? "на маркете" : x.busy ? "в игре" : "";
const rgCell = x => { const bd = rgBadge(x); return `<button class="rg-cell k-${x.kind}${bd ? " busy" : ""}${x.lock ? " lock" : ""}" data-act="rg-item" data-id="${x.id}">${rgArt(x)}<b>${esc(x.title)}</b><small>${bd || "⭐ " + short(x.value)}</small></button>`; };
ACT["rg-item"] = async el => {
  if (!RG || el.closest(".gsheet")) { try { await rgLoad(); } catch (e) { return; } }   // из профиля сюда можно попасть раньше, чем открыт экран кейсов
  const x = RG && RG.bag.find(i => i.id === +el.dataset.id); if (!x) return;
  H.imp("light");
  if (el.closest(".gsheet")) closeSheet();
  const sending = x.status !== "bag", usd = rgCost(x), can = RG.left + 1e-9 >= usd;
  const head = `<h2 class="gtitle">Подарок</h2><div class="rg-won">${rgArt(x, "big")}<b>${esc(x.title)}</b><small>⭐ ${fmt(x.value)} · ${rgUsd(usd)}</small>`;
  if (sending) return openSheet(`${head}<p>${esc(x.text)}</p></div>`, "rg-s rg-item-s");
  if (x.lock) return openSheet(`${head}<p>${rgLockText(x)}</p></div>
    <div class="btns rg-col"><button class="btn cta" data-act="rg-gate-inv">${ic("userPlus")}Пригласить друга</button></div>
    <p class="hint">Друг должен зайти в игру по твоей ссылке. Как только он зайдёт, замок снимется сам.</p>`, "rg-s rg-item-s");
  if (x.busy === "market") return openSheet(`${head}<p>Подарок выставлен на маркет. Чтобы вывести или продать его игре, сначала сними с продажи.</p></div>
    <div class="btns rg-col"><button class="btn cta" data-act="rg-unlist" data-id="${x.gid}">Снять с продажи</button></div>`, "rg-s rg-item-s");
  if (x.busy) return openSheet(`${head}<p>Подарок сейчас занят: стоит в игре, лежит в сейфе, в залоге или в подарке по ссылке. Вернётся в сумку, когда заберёшь его оттуда.</p></div>`, "rg-s rg-item-s");
  openSheet(`${head}<p>Настоящий подарок Telegram. Выведи его на свой аккаунт, продай игре за полную цену или играй им, как любым подарком.</p></div>
    <div class="btns rg-col"><button class="btn cta" data-act="rg-out" data-id="${x.id}">Вывести в Telegram</button><button class="btn ghost" data-act="rg-sell" data-id="${x.id}">Продать за ⭐ ${fmt(x.value)}</button><button class="btn ghost" data-act="rg-upg" data-id="${x.id}">${ic("trend")}Апгрейд в подарок дороже</button>${x.gid ? `<button class="btn ghost" data-act="rg-more" data-id="${x.id}">${ic("tag")}На маркет, подарить, в сейф</button>` : ""}</div>
    <p class="hint">${!RG.limit && !RG.held ? `Вывод откроется после первой покупки звёзд: вывести можно подарков на сумму до ${RG.limitK}% от покупок.`
      : can ? `Лимит вывода: осталось ${rgUsd(RG.left)}.` : `Лимит вывода: осталось ${rgUsd(RG.left)}, а подарок стоит ${rgUsd(usd)}. Лимит растёт с покупками.`}${x.kind === "nft" ? " Модель и фон будут как у самого доступного предложения на рынке." : ""}</p>`, "rg-s rg-item-s");
};
// обычная карточка подарка (маркет, подарить, сейф, кредит) — для подарка из кейса
ACT["rg-more"] = async el => {
  const id = +el.dataset.id;
  try { MYP = await api("user/" + ME.id); } catch (e) { return; }
  const g = MYP.gifts.find(i => i.real === id); if (!g) return toast("Подарок сейчас занят");
  closeSheet(); openGift({ g, mine: true });
};
ACT["rg-unlist"] = async el => {
  el.disabled = true;
  try { await post(`gift/${el.dataset.id}/unlist`); H.ok(); toast("Снято с продажи", "ok"); closeSheet(); await rgLoad(); rgRepaint(); if (TAB === "inv") renderInventory(); if (TAB === "market") loadMarket(); }
  catch (e) { el.disabled = false; }
};
// в обычной карточке у подарка из кейса: вывод в Telegram и свой апгрейд (цели — настоящие подарки), без дохода в час
const _gshRg = giftSheetHTML;
giftSheetHTML = function (o, mine) {
  let h = _gshRg(o, mine);
  const g = o.g; if (!g.real) return h;
  h = h.replace(/<div class="sub">[^<]*<\/div>/, `<div class="sub">Подарок из кейса · выводится в Telegram</div>`)
    .replace(/<div class="row kv[^>]*><span class="k">Доход<\/span>.*?<\/div>/s, "")
    .replace(/<div class="disc">[^<]*<\/div>/, `<div class="disc">Настоящий подарок Telegram: его можно вывести на свой аккаунт, продать за полную цену, выставить на маркет или поставить в игре.</div>`)
    .replace(/<button data-act="q-upg" data-k="[^"]*">/, `<button data-act="rg-upg" data-id="${g.real}">`);
  // модель, фон и узор не показываем: у обычного подарка Telegram их нет, а коллекционный на выводе покупается на рынке — какой будет доступен
  h = h.replace(/<div class="row kv"><span class="k">(Модель|Фон|Узор)<\/span>.*?<\/div>/gs, "");
  if (!/^Обычный/.test(g.model)) h = h.replace("выставить на маркет или поставить в игре.</div>", "выставить на маркет или поставить в игре. На выводе модель и фон будут как у самого доступного предложения на рынке.</div>");
  if (mine && g.price == null)
    h = h.replace('<div class="btns"><button class="btn gold" data-act="present"', `<div class="btns"><button class="btn cta" data-act="rg-item" data-id="${g.real}">${ic("send")}Вывести в Telegram</button></div><div class="btns"><button class="btn gold" data-act="present"`);
  return h;
};

// ---------------- апгрейд подарка из кейса: ставка — подарок из сумки, цель — подарок дороже ----------------
let RGU = null;
const rguPct = c => (c < 10 ? c.toFixed(1) : Math.round(c)) + "%";
function rgUpgHTML() {
  const u = RGU, t = u.pick;
  if (!t) return `<h2 class="gtitle">Апгрейд</h2>${emptyHTML("search", "Дороже этого подарка сейчас ничего нет")}`;
  return `<h2 class="gtitle">Апгрейд</h2>
    <div class="rgu-pair"><div class="rgu-slot">${rgArt(u.item, "big")}<b>${esc(u.item.title)}</b><small>⭐ ${fmt(u.item.value)}</small></div>
      <div class="rgu-mid"><b>${rguPct(t.chance)}</b><span>шанс</span></div>
      <div class="rgu-slot">${rgArt(t, "big")}<b>${esc(t.title)}</b><small>⭐ ${fmt(t.value)}</small></div></div>
    <div class="rgu-bar" id="rgu-bar"><i style="width:${t.chance}%"></i><u id="rgu-ptr"></u></div>
    <div class="btns"><button class="btn cta gold" data-act="rgu-go">Апгрейд · шанс ${rguPct(t.chance)}</button></div>
    <p class="hint">Повезёт — получишь цель: её можно вывести или продать. Не повезёт — подарок сгорит.</p>
    <div class="sec-t">Выбери цель</div>
    <div class="rg-grid">${u.targets.map(x => `<button class="rg-cell k-${x.kind}${x.key === t.key ? " on" : ""}" data-act="rgu-pick" data-k="${esc(x.key)}">${rgArt(x)}<b>${esc(x.title)}</b><small>⭐ ${short(x.value)} · ${rguPct(x.chance)}</small></button>`).join("")}</div>`;
}
ACT["rg-upg"] = async el => {
  if (RG_BUSY) return;
  const id = +el.dataset.id; let d;
  try { d = await api(`realgifts/item/${id}/upgrade`); } catch (e) { return; }
  H.sel();
  RGU = { id, item: d.item, targets: d.targets, busy: false, pick: d.targets.find(t => t.chance <= 50) || d.targets[0] || null };
  if (el.closest(".rg-item-s, .pgs, .pgs1, .gsheet")) closeSheet();
  openSheet(rgUpgHTML(), "rg-s rg-upg-s");
};
ACT["rgu-pick"] = el => {
  const u = RGU; if (!u || u.busy) return;
  u.pick = u.targets.find(t => t.key === el.dataset.k) || u.pick; H.sel();
  const sh = el.closest(".sheet"), top = sh.scrollTop; replaceSheet(sh, rgUpgHTML()); sh.scrollTop = Math.min(top, 0);
};
ACT["rgu-go"] = async el => {
  const u = RGU; if (!u || u.busy || !u.pick) return;
  if (!el.dataset.sure) { const was = el.textContent; el.dataset.sure = 1; el.textContent = "Точно? Подарок может сгореть"; setTimeout(() => { if (el.isConnected && el.dataset.sure) { delete el.dataset.sure; el.textContent = was; } }, 4000); return; }
  u.busy = true; el.disabled = true; el.textContent = "Крутим…";
  let r;
  try { r = await post(`realgifts/item/${u.id}/upgrade`, { key: u.pick.key }); }
  catch (e) { u.busy = false; el.disabled = false; delete el.dataset.sure; el.textContent = `Апгрейд · шанс ${rguPct(u.pick.chance)}`; return; }
  RG = r;
  const bar = document.getElementById("rgu-bar"), ptr = document.getElementById("rgu-ptr"), ch = r.chance, sh = el.closest(".sheet");
  if (bar && ptr) {   // зелёная зона — ровно шанс с сервера; стрелка встаёт в неё при выигрыше и за неё при проигрыше
    bar.querySelector("i").style.width = ch + "%";
    const stop = r.win ? Math.min(ch - 1, 1.5 + Math.random() * Math.max(0, ch - 3)) : Math.min(98.5, ch + 2.5 + Math.random() * Math.max(0, 96 - ch));
    ptr.style.transition = "left 3.2s cubic-bezier(.12,.8,.2,1)"; void ptr.offsetWidth; ptr.style.left = stop + "%";
    H.imp("light");
    await new Promise(z => setTimeout(z, 3400));
    bar.classList.add(r.win ? "win" : "lose");
  }
  r.win ? H.ok() : H.err();
  u.busy = false;
  if (sh && sh.isConnected) replaceSheet(sh, r.win
    ? `<h2 class="gtitle">Удалось!</h2><div class="rg-won">${rgArt(r.item, "big")}<b>${esc(r.item.title)}</b><small>⭐ ${fmt(r.item.value)}</small><p>Подарок в сумке. Выведи его в Telegram или продай игре.</p></div>
       <div class="btns rg-col"><button class="btn cta" data-act="close">Отлично</button><button class="btn ghost" data-act="rg-upg" data-id="${r.item.id}">${ic("trend")}Апгрейд ещё раз</button></div>`
    : `<h2 class="gtitle">Не повезло</h2><div class="rg-won rgu-lost">${rgArt(u.item, "big")}<b>${esc(u.item.title)}</b><small>сгорел</small><p>Шанс был ${rguPct(ch)}. Подарок ушёл игре.</p></div>
       <div class="btns"><button class="btn cta" data-act="close">Понятно</button></div>`);
  rgRepaint();
  if (typeof drawInventory === "function" && typeof TAB !== "undefined" && TAB === "bag") { try { drawInventory(); } catch (e) {} }
};

// ---------------- админ ----------------
const rgAge = s => s == null ? "нет данных" : s < 90 ? "только что" : s < 5400 ? Math.round(s / 60) + " мин назад" : Math.round(s / 3600) + " ч назад";
function rgAdmHTML() {
  const a = RG_ADM, row = (k, v) => `<div class="rg-kv"><span>${k}</span><b>${v}</b></div>`;
  return `<div class="rg-list">
      ${row("Баланс бота", a.botStars == null ? "нет данных" : num(a.botStars) + " Telegram Stars")}
      ${row("Обычные подарки в продаже", `${a.catalog} · ${rgAge(a.catalogAge)}`)}
      ${row("Цены коллекционных", a.feed.portals ? `Portals: ${a.feed.portals} · ${a.prices.length} в кейсах` : a.prices.length ? `${a.prices.length} (Tonnel)` : "нет: " + esc(a.feed.portals_err || a.feed.tonnel_err || "ждём первое обновление"))}
      ${row("Курс TON", a.ton ? `$${a.ton.toFixed(3)} · ${rgAge(a.tonAge)}` : "нет данных")}
      ${row("Выдача коллекционных", a.nftMode === "off" ? "выключена" : a.nftAuto ? `сервер покупает на Tonnel · баланс ${a.tonnelBal == null ? "?" : a.tonnelBal.toFixed(2)} TON` : "вручную: заявки приходят тебе" + (a.tonnelSession ? " (сессия Tonnel не принята)" : " (нет TONNEL_AUTH)"))}
      ${row("Кейсы", `${a.cases} работают` + (a.paused.length ? ` · на паузе: ${a.paused.map(p => esc(p.title) + " (" + esc(p.why) + ")").join(", ")}` : ""))}
      ${row("Открыто кейсов", `${num(a.opened.n)} · оплачено ⭐ ${short(a.opened.paid)} · выпало ⭐ ${short(a.opened.value)}`)}
      ${row("Выведено подарков", `${a.sent.n} на ${rgUsd(a.sent.usd)}`)}
    </div>
    ${a.pending.length ? `<div class="sec-t">Заявки на ручной проверке</div>${a.pending.map(p => `<div class="rg-it"><div class="rg-in"><b>№${p.id} · ${esc(p.title)} · ${rgUsd(p.usd)}</b><small>игрок ${p.user} · ${esc(p.note)}</small></div>
        <div class="rg-acts"><button class="btn ghost" data-act="rg-adm-back" data-id="${p.id}">Вернуть в сумку</button><button class="btn cta" data-act="rg-adm-done" data-id="${p.id}">Подарок выдан</button></div></div>`).join("")}` : ""}
    <div class="btns"><button class="btn ghost" data-act="rg-adm-refresh">Обновить цены сейчас</button></div>`;
}
function rgAdmPaint() { const e = document.getElementById("rg-adm"); if (e) e.innerHTML = rgAdmHTML(); }

Object.assign(ACT, {
  "rg-bag": () => { INVK = "all"; closeSheet(); setTab("inv"); },
  "rg-open": async () => {   // состояние цен, балансы и заявки — для админа
    if (!ME || !ME.admin) return ACT["rg-bag"]();
    H.imp("light");
    openSheet(`<h2 class="gtitle">Подарки: состояние</h2><div id="rg-body"><div class="hint" style="padding:18px;text-align:center">Загрузка…</div></div>`, "rg-s");
    [RG, RG_ADM] = await Promise.all([api("realgifts"), api("admin/realgifts")]); rgRepaint();
  },
  "rg-spin": el => rgSpin(el),
  "rg-sell": async el => {
    if (RG_BUSY) return; RG_BUSY = true; el.disabled = true;
    try { const id = +el.dataset.id, r = await post(`realgifts/item/${id}/sell`); RG = r; setStars(r.stars); H.ok(); toast(`Продано за ⭐ ${fmt(r.paid)}`, "ok"); if (el.closest(".rg-item-s")) closeSheet(); rgAfter(id, "Продан игре — звёзды уже на балансе."); }
    catch (e) { el.disabled = false; } finally { RG_BUSY = false; }
  },
  "rg-out": async el => {
    if (RG_BUSY) return;
    if (!el.dataset.sure) { const was = el.textContent; el.dataset.sure = 1; el.textContent = "Точно вывести?"; setTimeout(() => { if (el.isConnected && el.dataset.sure) { delete el.dataset.sure; el.textContent = was; } }, 4000); return; }
    RG_BUSY = true; el.disabled = true; el.textContent = "Отправляем…";
    const id = +el.dataset.id;
    try {
      RG = await post(`realgifts/item/${id}/withdraw`, {}, { timeout: 90000 });
      const x = RG.bag.find(i => i.id === id);
      H.ok(); toast(x ? "Заявка принята — проверим и отправим" : "Подарок отправлен — смотри в профиле Telegram", "ok");
      if (el.closest(".rg-item-s")) closeSheet();
      rgAfter(id, x ? "Отправка проверяется вручную — обычно до суток." : "Отправлен на твой аккаунт Telegram.");
    } catch (e) { delete el.dataset.sure; el.disabled = false; el.textContent = el.closest(".rg-item-s") ? "Вывести в Telegram" : "Вывести"; rgLoad().then(rgRepaint).catch(() => {}); }
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
  "Вывод": "Withdraw", "Легенда": "Legend", "Эпик": "Epic", "подарки и скины": "gifts and skins",
});

// переключатель «звёзды / доллары» в окне баланса
ACT["rg-topup"] = () => { H.sel(); openDaily("shop"); };
ACT.cur = el => { if ((el.dataset.v === "usd") === CUR_USD) return; H.sel(); setCur(el.dataset.v === "usd"); };

// ---------------- условия бесплатного кейса: подписки в первый раз, дальше — новый друг ----------------
function rgGateHTML(c, g) {
  const check = `<button class="btn cta rg-gate-go" data-act="rg-gate-check" data-id="${c.id}">Проверить и крутить</button>`;
  if (g.kind === "subs") {
    const n = g.steps.length, w = n === 1 ? "Один шаг" : n === 2 ? "Два шага" : n === 3 ? "Три шага" : `${n} ${plural(n, ["шаг", "шага", "шагов"])}`;
    return `<h2 class="gtitle">${w} до прокрута</h2>
      <div class="rg-gate">${g.steps.map((x, i) => `<div class="rg-gs${x.done ? " done" : ""}"><i>${x.done ? ic("check") : i + 1}</i><b>${esc(x.title)}</b>
        ${x.url ? `<button class="btn sm gold" data-act="rg-gate-link" data-url="${esc(x.url)}">${x.done ? "Открыть" : "Подписаться"}</button>` : ""}</div>`).join("")}</div>${check}`;
  }
  return "";
}
function rgGate(c, g) { H.sel(); const el = openSheet(rgGateHTML(c, g), "rg-s rg-gate-s"); el._case = c; }
Object.assign(ACT, {
  "rg-gate-link": el => { const u = el.dataset.url; if (inTg && /^https:\/\/t\.me\//.test(u)) tg.openTelegramLink(u); else window.open(u, "_blank"); },
  "rg-gate-inv": () => {
    const text = "Залетай в игру — открывай кейсы с настоящими подарками Telegram 🎁";
    const url = `https://t.me/share/url?url=${enc(ME.refLink)}&text=${enc(text)}`;
    if (inTg) tg.openTelegramLink(url); else copyText(ME.refLink);
  },
  "rg-gate-check": async el => {
    const sheet = el.closest(".sheet"), c = sheet && sheet._case; if (!c) return;
    el.disabled = true;
    let g; try { g = await api(`realgifts/free/${c.id}`); } catch (e) { el.disabled = false; return; }
    if (!g.ok) { H.err(); replaceSheet(sheet, rgGateHTML(c, g)); topSheet()._case = c; return toast("Подпишись на все каналы из списка"); }
    closeSheet();
    const btn = document.querySelector(`.sheet [data-act="rg-spin"][data-id="${c.id}"]`);
    if (btn) { btn._gateOk = true; rgSpin(btn); }
  },
});

if (typeof LANG !== "undefined" && LANG === "en" && typeof i18nAdd === "function") i18nAdd({"выбери кейс из списка": "choose a case from the list", "Выбери кейс из списка": "Choose a case from the list", "На 7-й день и дальше каждые 7 дней — ключ от кейса с подарками": "On day 7 and every 7 days after that: a key to a gift case", "на старт": "to start", "Введи количество — покажем, сколько": "Enter an amount and we'll show how many", "⭐ в игре": "⭐ in the game", "В звёздах": "In stars", "В долларах": "In dollars", "Проверить и крутить": "Check and spin", "Подписаться": "Subscribe", "Друг за прокрут": "A friend per spin", "Один шаг до прокрута": "One step to the spin", "Два шага до прокрута": "Two steps to the spin", "Три шага до прокрута": "Three steps to the spin", "до прокрута": "to the spin", "Друзей:": "Friends:", "Пригласить": "Invite", "Первый бесплатный кейс был за подписку. Каждый следующий открывается за нового друга: он заходит в игру по твоей ссылке — и кейс твой.": "The first free case was for subscribing. Each next one opens for a new friend: they join the game via your link and the case is yours.", "Подпишись на все каналы из списка": "Subscribe to all channels in the list", "Друг ещё не зашёл в игру по твоей ссылке": "Your friend hasn't joined via your link yet", "Сначала выполни условия бесплатного кейса": "Complete the free case conditions first", "Кейс на паузе: обновляем цены скинов. Загляни чуть позже": "Case paused: updating skin prices. Check back soon", "Скин подорожал на площадке — вывести его сейчас нельзя. Продай его игре за полную цену или попробуй позже": "This skin got more expensive on the market, so it can't be withdrawn right now. Sell it to the game for full price or try later", "Залетай в игру — открывай кейсы с настоящими подарками Telegram": "Join the game and open cases with real Telegram gifts", "Лимит от": "Limit from", "Взнос от": "Contribution from"});

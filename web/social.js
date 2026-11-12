"use strict";
// ============================================================
//  Инвентарь, маркет, друзья (шторка), профиль
// ============================================================

// ------------------------------------------------------------ шапка
function renderHeader() {
  const prev = +($("#bal-n").textContent.replace(/[^\d-−]/g, "").replace("−", "-") || 0);
  $("#bal-n").textContent = fmt(ME.stars);
  paintBalance(prev && ME.stars > prev ? "up" : prev && ME.stars < prev ? "down" : "");
  const p = Math.round((ME.lv.xp - ME.lv.from) / (ME.lv.to - ME.lv.from) * 100);
  const n = ME.friendReq + ME.trades + (ME.duels || 0) + (ME.rooms || 0);
  $("#me-btn").innerHTML = avaHTML(ME, 38, { ring: true, p, lv: true });
  $("#fr-btn").innerHTML = ic("users") + (n ? `<span class="badge-dot">${n}</span>` : "");
}

// ============================================================ ИНВЕНТАРЬ
const INV = { sort: "value", col: "", mode: "gifts", sel: null };
let COLS = null;
async function renderInventory() {
  const v = $("#v-inv");
  if (!v.innerHTML) v.innerHTML = emptyHTML("hourglass", "Загружаем…");
  const [p, cols] = await Promise.all([api("user/" + ME.id), COLS ? COLS : api("collections")]);
  MYP = p; COLS = cols;
  drawInventory();
}
function drawInventory() {
  const v = $("#v-inv"), p = MYP; if (!p) return;
  const gifts = p.gifts, total = gifts.reduce((s, g) => s + g.value, 0);
  const owned = new Set(gifts.map(g => g.col));
  const top = [...gifts].sort((a, b) => b.value - a.value).slice(0, 3);
  if (!gifts.length && INV.mode === "gifts" && !INV.col) { v.innerHTML = invStartHTML(); drawSelBar(); return; }
  let body = "";
  if (INV.mode === "gifts") {
    let list = INV.col ? gifts.filter(g => g.col === INV.col) : [...gifts];
    list.sort(INV.sort === "new" ? (a, b) => b.id - a.id : INV.sort === "rare" ? (a, b) => a.mp - b.mp || b.value - a.value : (a, b) => b.value - a.value);
    const pinned = new Set(p.pinned.map(g => g.id));
    body = `
      <div class="itool">
        <div class="seg sm">${[["value", "Дорогие"], ["new", "Новые"], ["rare", "Редкие"]].map(([k, t]) => `<button data-act="inv-sort" data-v="${k}" class="${INV.sort === k ? "on" : ""}">${t}</button>`).join("")}</div>
        <button class="ibtn${INV.sel ? " on" : ""}" data-act="inv-sel">${ic(INV.sel ? "x" : "checks")}</button>
      </div>
      ${INV.col ? `<div class="fchip">${esc(INV.col)}<button data-act="inv-col" data-v="">${ic("x")}</button></div>` : ""}
      ${list.length ? `<div class="ggrid">${list.map(g => {
        const picked = INV.sel && INV.sel.has(g.id);
        return `<div class="gcell${picked ? " picked" : ""}" data-act="inv-tap" data-k="${reg({ g, mine: true })}" data-id="${g.id}">
          ${giftHTML(g, { lite: true, tag: "⭐ " + short(g.value) })}${g.price == null ? `<span class="phr">+${perHourTxt(giftPerHour(g))}/ч</span>` : ""}
          ${INV.sel ? `<span class="sel">${picked ? ic("check") : ""}</span>` : ""}
          ${g.price != null ? `<span class="onm">${ic("tag")}${short(g.price)}</span>` : pinned.has(g.id) ? `<span class="onm pin">${ic("pin")}</span>` : ""}
          <div class="cap">${giftName(g)}</div></div>`;
      }).join("")}</div>` : emptyHTML("gift", INV.col ? "В этой коллекции у тебя пока ничего" : "Инвентарь пуст — открой первый кейс")}`;
  } else {
    const rows = Object.entries(COLS).map(([c, [n, base]]) => {
      const mine = gifts.filter(g => g.col === c), models = new Set(mine.map(g => g.model)).size;
      return { c, n, base, models, count: mine.length };
    }).sort((a, b) => b.models / b.n - a.models / a.n || b.base - a.base);
    body = `<div class="hint" style="font-size:13px;margin:0 4px 10px">Собирай разные модели каждой коллекции. Открыто ${owned.size} из ${rows.length} коллекций.</div>
      <div class="box">${rows.map(r => `<div class="row tap colrow${r.count ? "" : " none"}" data-act="inv-col" data-v="${esc(r.c)}">
        <img src="${A.orig(r.c, 64)}" alt="" loading="lazy"><div class="grow"><div class="t">${esc(r.c)}</div>
        <div class="cbar"><div style="width:${Math.max(r.models ? 4 : 0, r.models / r.n * 100)}%"></div></div>
        <div class="s">${r.models}/${r.n} моделей${r.count ? ` · ${r.count} шт.` : ""}</div></div>${ic("chev", "dim")}</div>`).join("")}</div>`;
  }
  v.innerHTML = `
    <div class="invhero">
      <div class="ih-l">
        <div class="ih-two"><div><span>Ценность</span><b>⭐ ${short(total)}</b></div>
          <div class="ih-hr" data-act="inc"><span>Доход в час</span><b>+⭐ ${perHourTxt(gifts.filter(g => g.price == null).reduce((s, g) => s + giftPerHour(g), 0))}</b></div></div>
        <small>${gifts.length} ${plural(gifts.length, ["подарок", "подарка", "подарков"])} · ${owned.size} ${plural(owned.size, ["коллекция", "коллекции", "коллекций"])} · ⭐ ${fmt(Math.round(gifts.filter(g => g.price == null).reduce((s, g) => s + giftPerHour(g), 0) * 24))}&nbsp;в&nbsp;день</small></div>
      <div class="ih-r">${top.map((g, i) => `<div class="ih-g" style="--i:${i}">${giftHTML(g, { lite: true, plain: true })}</div>`).join("")}</div>
    </div>
    <div class="seg">${[["gifts", "grid", "Подарки"], ["cols", "layers", "Коллекции"]].map(([k, i, t]) => `<button data-act="inv-mode" data-v="${k}" class="${INV.mode === k ? "on" : ""}">${ic(i)}${t}</button>`).join("")}</div>
    ${body}`;
  drawSelBar();
}
// пустая сумка у новичка: не нули, а понятный первый шаг
function invStartHTML() {
  const free = ME && !ME.freeIn;
  return `<div class="invstart">
    <div class="is-art">${["Toy Bear", "Plush Pepe", "Ion Gem"].map((g, i) => `<img class="is-g g${i}" src="${A.orig(g, 128)}" alt="">`).join("")}<i class="is-glow"></i></div>
    <h2>Сумка пока пустая</h2>
    <p>Открой кейс — выпавшие подарки лягут сюда и начнут приносить звёзды каждый час.</p>
    ${free ? `<button class="btn cta gold" data-act="case" data-id="free">${ic("gift")}Открыть бесплатный кейс</button>`
      : `<button class="btn cta gold" data-tab="cases">${ic("gift")}К кейсам</button>`}
    <div class="is-steps">
      <div><span>1</span><b>Открой кейс</b><small>${free ? "бесплатный доступен сейчас" : "бесплатный — каждые несколько часов"}</small></div>
      <div><span>2</span><b>Получай доход</b><small>подарки приносят звёзды каждый час</small></div>
      <div><span>3</span><b>Прокачивай</b><small>апгрейд, обмен, коллекции</small></div>
    </div></div>`;
}
function drawSelBar() {
  let bar = $("#selbar");
  if (!INV.sel || TAB !== "inv") { bar && bar.remove(); return; }
  if (!bar) { bar = document.createElement("div"); bar.id = "selbar"; bar.className = "selbar"; document.body.appendChild(bar); }
  if (!MYP) return renderInventory();   // MYP сбрасывают после апгрейда, джекпота и т. п. — подгрузим заново
  const ids = [...INV.sel], sum = MYP.gifts.filter(g => INV.sel.has(g.id)).reduce((s, g) => s + Math.floor(g.value * (1 - FEE("sell", .15))), 0);
  bar.innerHTML = `<div><b>Выбрано: ${ids.length}</b><span>продажа за ⭐ ${fmt(sum)}</span></div>
    <button class="btn sm ghost" data-act="inv-all">Все</button><button class="btn sm red" data-act="inv-sell" ${ids.length ? "" : "disabled"}>${ic("coins")}Продать</button>`;
}

// ============================================================ МАРКЕТ
const MK = { sort: "new", col: "", qs: "", mine: 0, rare: "" };
async function renderMarket() {
  const v = $("#v-market");
  v.innerHTML = `
    <div class="mkstats" id="mk-st"><div><b>—</b><span>лотов</span></div><div><b>—</b><span>флор</span></div><div><b>—</b><span>оборот 24ч</span></div></div>
    <div class="mksearch"><label>${ic("search")}<input id="mk-q" placeholder="Коллекция или модель" value="${esc(MK.qs)}" enterkeyhint="search"></label>
      <button class="btn sm gold" data-act="mk-sell">${ic("plus")}Продать</button></div>
    <div class="seg">${[["new", "Новые"], ["cheap", "Дешёвые"], ["expensive", "Дорогие"], ["deal", "Выгодные"]].map(([k, t]) => `<button data-act="mk" data-k="sort" data-v="${k}" class="${MK.sort === k ? "on" : ""}">${t}</button>`).join("")}</div>
    <div class="chips">${[["", "Все", "grid"], ["legend", "Легенды", "crown"], ["epic", "Эпик", "flame"], ["rare", "Редкие", "sparkles"]].map(([k, t, i]) => `<button data-act="mk" data-k="rare" data-v="${k}" class="${MK.rare === k && !MK.mine ? "on" : ""}">${ic(i)}${t}</button>`).join("")}
      <button data-act="mk" data-k="mine" data-v="${MK.mine ? 0 : 1}" class="${MK.mine ? "on" : ""}">${ic("tag")}Мои лоты<span id="mk-my"></span></button></div>
    <div class="hist" id="mk-cols" style="margin:10px -16px 0"></div>
    <div id="mk-sales"></div>
    <div id="mk-list" style="margin-top:12px">${emptyHTML("hourglass", "Загружаем…")}</div>`;
  const inp = $("#mk-q"); let t;
  inp.oninput = () => { clearTimeout(t); t = setTimeout(() => { MK.qs = inp.value.trim(); loadMarket(); }, 350); };
  loadMarket();
}
async function loadMarket() {
  const d = await api(`market?sort=${MK.sort}&col=${enc(MK.col)}&qs=${enc(MK.qs)}&mine=${MK.mine}&rare=${MK.rare}`);
  if (TAB !== "market") return;
  $("#mk-st").innerHTML = `<div><b>${fmt(d.count)}</b><span>лотов</span></div><div><b>${d.floor ? "⭐ " + short(d.floor) : "—"}</b><span>${MK.col ? "флор коллекции" : "флор"}</span></div><div><b>⭐ ${short(d.vol24)}</b><span>оборот 24ч · ${d.sales24}</span></div>`;
  $("#mk-my").textContent = d.myCount ? ` · ${d.myCount}` : "";
  $("#mk-cols").innerHTML = [["", "Все коллекции"], ...d.cols.map(c => [c, c])].map(([k, t]) => `<span data-act="mk" data-k="col" data-v="${esc(k)}" class="${k === MK.col ? "on" : ""}">${k ? `<img src="${A.orig(k, 64)}" alt="">` : ""}${esc(t)}</span>`).join("");
  $("#mk-sales").innerHTML = d.sales.length && !MK.mine ? `<div class="sec-t">${ic("activity")}Последние продажи</div>
    <div class="feed">${d.sales.map(g => `<div class="fi sale" data-act="gift" data-k="${reg({ g: { ...g, price: null } })}">${giftHTML(g, { lite: true, plain: true })}<span class="sp">⭐ ${short(g.price)}</span></div>`).join("")}</div>` : "";
  $("#mk-list").innerHTML = d.items.length ? `<div class="ggrid two">${d.items.map(g => {
    const k = reg({ g, seller: g.seller, mine: g.owner === ME.id }), diff = Math.round((g.price / g.value - 1) * 100);
    return `<div class="gcell mkc" data-act="gift" data-k="${k}">${giftHTML(g, { lite: true })}
      ${diff <= -3 ? `<span class="deal">−${-diff}%</span>` : ""}${g.owner === ME.id ? `<span class="onm">ТВОЙ</span>` : ""}
      <div class="cap">${giftName(g)}</div>
      <div class="mkrow">${avaHTML(g.seller, 18)}<span>${esc(g.seller.name)}</span></div>
      <div class="pricebtn">⭐ ${fmt(g.price)}</div></div>`;
  }).join("")}</div>` : emptyHTML("store", MK.mine ? "У тебя нет лотов. Нажми «Продать», чтобы выставить подарок" : "Лотов не нашлось");
}
async function listGift(g) {
  const v = await promptM("Цена на маркете", `${esc(g.col)} #${fmt(g.num)} · ценность ⭐ ${fmt(g.value)}. Комиссия маркета ${feeP("market", .05)}.`, Math.round(g.value * 1.1), "Выставить");
  if (v == null) return;
  await post(`gift/${g.id}/list`, { price: Math.floor(+v) }); H.ok(); toast("Выставлено на маркет");
  MYP = null;
  if (TAB === "market") loadMarket();
  if (TAB === "inv") renderInventory();
}

// ============================================================ ДРУЗЬЯ + ОБМЕНЫ (шторка)
function openFriends() {
  H.imp("light");
  const el = openSheet(`<h2 class="gtitle">Друзья</h2><div id="fr-body">${emptyHTML("hourglass", "Загружаем…")}</div>`);
  el._fr = true;
  fillFriends(el);
}
async function refreshFriends() { for (const el of SHEETS) if (el._fr) fillFriends(el); }
async function fillFriends(el) {
  let [fr, trades, duels] = await Promise.all([api("friends"), api("trades"), window.loadDuels ? loadDuels() : []]);
  // во время перезапуска сервера ответ бывает пустым (null) — показываем то, что есть, а не падаем на .filter
  fr = fr || { friends: [], incoming: [], outgoing: [] }; trades = trades || []; duels = duels || [];
  const open = trades.filter(t => t.status === "open"), hist = trades.filter(t => t.status !== "open").slice(0, 8);
  el.querySelector("#fr-body").innerHTML = `
    <div class="ref"><img src="${A.orig("Loot Bag", 128)}" alt=""><b>Пригласи друга</b><p>${ME.ref && ME.ref.on ? `До +${fmt((ME.ref.join || 0) + ME.ref.l1[1] + ME.ref.l2[1])} ⭐ за каждого друга` : "Играйте вместе"} · приглашено: ${ME.refs}</p><button class="btn" data-act="invite">${ic("send")}Пригласить</button></div>
    <label class="srch">${ic("search")}<input id="usearch" placeholder="Найти игрока по имени или @username" enterkeyhint="search"></label><div id="sres"></div>
    ${window.duelsHTML ? duelsHTML(duels) : ""}
    ${fr.incoming.length ? `<div class="sec-t">Заявки в друзья</div><div class="box">${fr.incoming.map(u => userRow(u, `<button class="ibtn green" data-act="fr" data-id="${u.id}" data-v="add">${ic("check")}</button><button class="ibtn red" data-act="fr" data-id="${u.id}" data-v="remove">${ic("x")}</button>`)).join("")}</div>` : ""}
    ${open.length ? `<div class="sec-t">Обмены</div>${open.map(tradeCard).join("")}` : ""}
    <div class="sec-t">Друзья · ${fr.friends.length}</div>
    ${fr.friends.length ? `<div class="box">${fr.friends.map(u => userRow(u, `${window.duelsHTML ? `<button class="ibtn" data-act="duel-new" data-id="${u.id}">${ic("target")}</button>` : ""}<button class="ibtn" data-act="trade-new" data-id="${u.id}">${ic("swap")}</button>`)).join("")}</div>`
      : emptyHTML("users", "Друзей пока нет. Найди игрока или пригласи по ссылке")}
    ${fr.outgoing.length ? `<div class="sec-t">Ждут ответа</div><div class="box">${fr.outgoing.map(u => userRow(u, `<button class="btn sm ghost" data-act="fr" data-id="${u.id}" data-v="remove">Отменить</button>`)).join("")}</div>` : ""}
    ${hist.length ? `<div class="sec-t">История обменов</div>${hist.map(tradeCard).join("")}` : ""}`;
  const inp = el.querySelector("#usearch"); let st;
  inp.oninput = () => { clearTimeout(st); st = setTimeout(async () => {
    const q = inp.value.trim(), box = el.querySelector("#sres");
    if (q.length < 2) return box.innerHTML = "";
    const res = await api("users/search?qs=" + enc(q));
    box.innerHTML = res.length ? `<div class="box" style="margin-top:8px">${res.map(u => userRow(u)).join("")}</div>` : `<div class="hint" style="padding:8px 4px">Никого не нашли</div>`;
  }, 300); };
}
const userRow = (u, right = "") => `<div class="row tap" data-act="profile" data-id="${u.id}">${avaHTML(u, 40, { lv: true })}<div class="grow"><div class="t">${nameHTML(u)}</div><div class="s${u.status ? " ust" : ""}">${u.status ? esc(u.status) : u.username ? "@" + esc(u.username) : u.level + " уровень"}</div></div>${right}</div>`;
function tradeCard(t) {
  const mine = t.src.id === ME.id, other = mine ? t.dst : t.src;
  const side = (gs, s) => (gs.map(g => `<div data-act="gift" data-k="${reg({ g })}">${giftHTML(g, { lite: true, plain: true })}</div>`).join("") + (s ? `<span class="pill" style="color:var(--gold)">⭐ ${fmt(s)}</span>` : "")) || `<span class="hint">ничего</span>`;
  const get = mine ? side(t.want, t.wantStars) : side(t.give, t.giveStars), give = mine ? side(t.give, t.giveStars) : side(t.want, t.wantStars);
  const ST = { open: ["ждёт ответа", "var(--blue)"], done: ["совершён", "var(--green)"], declined: ["отклонён", "var(--red)"], cancelled: ["отменён", "var(--hint)"], void: ["аннулирован", "var(--hint)"] }[t.status];
  let btns = "";
  if (t.status === "open") btns = mine ? `<div class="btns"><button class="btn sm ghost" style="flex:1" data-act="trade" data-id="${t.id}" data-v="cancel">Отменить</button></div>`
    : `<div class="btns"><button class="btn sm red" style="flex:1" data-act="trade" data-id="${t.id}" data-v="decline">Отклонить</button>${ME.stars < t.wantStars ? `<button class="btn sm ghost" style="flex:1" disabled>Нужно ⭐ ${short(t.wantStars)}</button>` : `<button class="btn sm green" style="flex:1" data-act="trade" data-id="${t.id}" data-v="accept">Принять</button>`}</div>`;
  return `<div class="tr"><div class="row" style="padding:0;min-height:0" data-act="profile" data-id="${other.id}">${avaHTML(other, 30)}<div class="grow"><div class="t">${mine ? "Ты → " : ""}${esc(other.name)}${mine ? "" : " → тебе"}</div></div><span class="st" style="color:${ST[1]}">${ST[0]}</span></div>
    <div class="hint" style="font-size:12px;margin-top:8px">Ты отдаёшь</div><div class="side">${give}</div>
    <div class="hint" style="font-size:12px">Ты получаешь</div><div class="side">${get}</div>${btns}</div>`;
}

// ============================================================ ПРОФИЛЬ
async function openProfile(id) {
  H.imp("light");
  const el = openSheet(emptyHTML("hourglass", "Загружаем профиль…"), "psheet");
  await loadBanners();
  const p = await api("user/" + id).catch(() => null);
  if (!p) return closeSheet();
  if (id === ME.id) MYP = p;
  el._pid = id; el._p = p; el._ptab = el._ptab || "show";
  replaceSheet(el, profileHTML(p, el._ptab));
}
async function refreshProfileSheets() {
  for (const el of SHEETS) if (el._pid) {
    const p = await api("user/" + el._pid).catch(() => null);
    if (p) { if (p.id === ME.id) MYP = p; el._p = p; replaceSheet(el, profileHTML(p, el._ptab)); }
  }
}
const GAME_NAMES = { case: ["box", "Кейсы"], crash: ["rocket", "Краш"], upgrade: ["trend", "Апгрейд"], mines: ["bomb", "Мины"], wheel: ["refresh", "Колесо"],
  duel: ["target", "Дуэли"], dice: ["box", "Кубик"], limbo: ["activity", "Лимбо"], plinko: ["grid", "Плинко"], tower: ["layers", "Башня"],
  slots: ["coins", "Слоты"], blackjack: ["award", "Блэкджек"], cards: ["users", "Столы"], dogs: ["paw", "Пёсики"],
  roulette: ["target", "Рулетка"], jroul: ["trophy", "Джекпот"], hilo: ["trend", "Больше/меньше"], craft: ["layers", "Крафт"] };
// последний онлайн: seen — время последнего запроса к API (сервер обновляет раз в минуту); now — серверное время, чтобы не зависеть от часов телефона
function seenHTML(p) {
  if (!p.seen) return "";
  const d = Math.max(0, (p.now || Date.now() / 1000) - p.seen);
  if (d < 180) return `<span class="pf-seen on"><i></i>в сети</span>`;
  const at = new Date(p.seen * 1000), hm = at.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const day = n => { const x = new Date(); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - n); return at >= x; };
  let t;
  if (d < 3600) { const m = Math.floor(d / 60); t = `${m} ${plural(m, ["минуту", "минуты", "минут"])} назад`; }
  else if (d < 6 * 3600) { const h = Math.floor(d / 3600); t = `${h} ${plural(h, ["час", "часа", "часов"])} назад`; }
  else if (day(0)) t = "сегодня в " + hm;
  else if (day(1)) t = "вчера в " + hm;
  else if (d < 300 * 86400) t = at.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  else t = at.toLocaleDateString("ru-RU");
  return `<span class="pf-seen"><i></i>в сети ${t}</span>`;
}
function profileHTML(p, tab = "show") {
  const isMe = p.id === ME.id, lv = p.lv;
  const prog = Math.round((lv.xp - lv.from) / (lv.to - lv.from) * 100);
  const REL = { none: ["userPlus", "В друзья", "add", ""], outgoing: ["userClock", "Заявка отправлена", "remove", "ghost"], incoming: ["userCheck", "Принять заявку", "add", "green"], friend: ["userCheck", "В друзьях", "remove", "ghost"] }[p.rel];
  const got = p.ach.filter(a => a.got).length, st = p.stats || { games: {}, won: 0, lost: 0, best: 0, rounds: 0 };
  const byValue = [...p.gifts].sort((a, b) => b.value - a.value);
  const show = p.pinned.length ? p.pinned : byValue.slice(0, 3);
  const cell = (g, o = {}) => `<div class="gcell" data-act="gift" data-k="${reg({ g, mine: isMe, owner: p })}">${giftHTML(g, o)}${g.price != null ? `<span class="onm">${ic("tag")}${short(g.price)}</span>` : ""}<div class="cap">${giftName(g)}</div></div>`;
  let body;
  if (tab === "legacy") body = lgBody(p);
  else if (tab === "gifts") body = p.gifts.length ? `<div class="ggrid">${byValue.map(g => cell(g, { lite: true })).join("")}</div>` : emptyHTML("gift", isMe ? "Открой первый кейс!" : "Подарков пока нет");
  else if (tab === "ach") body = `<div class="achs">${p.ach.map(a => `<div class="ach${a.got ? " got" : ""}"><span class="ai">${ic(ACH_IC[a.t] || "award")}</span><b>${esc(a.t)}</b><span>${esc(a.d)}</span>${achPct(a)}${a.got ? `<i>${ic("check")}</i>` : ""}</div>`).join("")}</div>`;
  else if (tab === "stats") {
    const list = Object.entries(st.games).sort((a, b) => b[1] - a[1]), max = list.length ? list[0][1] : 1, net = st.won - st.lost;
    body = `<div class="pst">
        <div><span>Раундов</span><b>${fmt(st.rounds)}</b></div>
        <div><span>Выиграно</span><b class="tw">+⭐ ${short(st.won)}</b></div>
        <div><span>Проиграно</span><b class="tl">−⭐ ${short(st.lost)}</b></div>
        <div><span>Итог</span><b class="${net >= 0 ? "tw" : "tl"}">${net >= 0 ? "+" : "−"}⭐ ${short(Math.abs(net))}</b></div>
        <div><span>Лучший занос</span><b class="star">⭐ ${short(st.best)}</b></div>
        <div><span>Рекорд краша</span><b>${p.bestCrash ? "x" + p.bestCrash.toFixed(2) : "—"}</b></div></div>
      ${isMe && ME.cashback ? `<div class="cbk">${ic("refresh")}<div class="grow"><b>Кэшбэк недели: ⭐ ${fmt(ME.cashback)}</b><span>вернём в понедельник — 5% от минуса в играх за неделю</span></div></div>` : ""}
      ${list.length ? `<div class="sec-t">${ic("activity")}Во что играет</div><div class="box">${list.map(([k, n], i) => {
        const [icn, name] = GAME_NAMES[k] || ["box", k];
        return `<div class="row kv pg"><span class="pic ${i ? "b" : "y"}">${ic(icn)}</span><div class="grow"><div class="t">${name}${i ? "" : ` <span class="pill">любимая</span>`}</div>
          <div class="cbar"><div style="width:${Math.max(4, n / max * 100)}%"></div></div></div><b>${fmt(n)}</b></div>`;
      }).join("")}</div>` : emptyHTML("games", "Ещё не играл")}`;
  } else body = show.length ? `<div class="showcase">${show.map((g, i) => `<div class="sc${i === 0 ? " main" : ""}" data-act="gift" data-k="${reg({ g, mine: isMe, owner: p })}">${giftHTML(g)}<div class="cap">${giftName(g)}<span>⭐ ${short(g.value)}</span></div></div>`).join("")}</div>
      ${!p.pinned.length && isMe ? `<button class="btn ghost" style="margin-top:12px" data-act="edit-profile">${ic("pin")}Выбрать подарки для витрины</button>` : ""}`
    : emptyHTML("gift", isMe ? "Открой первый кейс — тут будет витрина" : "Витрина пуста");
  // шапка профиля в духе X / Telegram / Discord: обложка во всю ширину; аватар слева наполовину на обложке (в «вырезе» цвета фона);
  // справа от аватара на обложке — теги; ниже слева имя, @ник, описание и цифры строкой. Свои классы pf-* — старые .phead-правила не влияют.
  return `<div class="pf">
    <div class="pf-cover">${bannerHTML(p)}</div>
    <div class="pf-row">
      <div class="pf-ava">${avaHTML(p, 84, { ring: true, p: prog })}</div>
      <div class="pf-info">
        <div class="pf-tags"><span class="plv">${ic("medal")}${lv.level}</span>${p.clan ? `<span class="ctag" data-act="clan-tag" data-tag="${esc(p.clan)}">${esc(p.clan)}</span>` : ""}</div>
        <div class="pname"><h2>${esc(p.name)}</h2></div>
        <div class="pf-sub">${p.username ? `<span>@${esc(p.username)}</span>` : ""}${p.title ? `<span class="pf-title" ${isMe ? 'data-act="titles"' : ""}>${ic("medal")}${esc(p.title)}</span>` : ""}${isMe ? "" : seenHTML(p)}</div>
      </div>
    </div>
    ${p.badges && p.badges.length ? `<div class="pbadges"></div>` : ""}
    ${p.bio ? `<div class="pf-bio">${esc(p.bio)}</div>` : ""}
    <div class="pf-stats">
      <span><b>⭐ ${short(p.worth)}</b> состояние</span>
      <span><b>${fmt(p.gifts.length)}</b> ${plural(p.gifts.length, ["подарок", "подарка", "подарков"])}</span>
      <span><b>${fmt(p.cols)}</b> ${plural(p.cols, ["коллекция", "коллекции", "коллекций"])}</span>
      <span ${isMe ? 'data-act="friends"' : ""}><b>${fmt(p.friends)}</b> ${plural(p.friends, ["друг", "друга", "друзей"])}</span>
    </div>
  </div>
    <div class="pacts">${isMe
      ? `<button class="btn ghost" data-act="edit-profile">${ic("edit")}Изменить</button><button class="btn ghost" data-act="friends">${ic("users")}Друзья</button><button class="btn" data-act="invite">${ic("send")}Позвать</button><button class="btn ghost pset" data-act="settings" aria-label="Настройки">${ic("gear")}</button>`
      : `<button class="btn ${REL[3]}" data-act="fr" data-id="${p.id}" data-v="${REL[2]}">${ic(REL[0])}${REL[1]}</button><button class="btn ghost" data-act="trade-new" data-id="${p.id}">${ic("swap")}Обмен</button><button class="btn ghost" data-act="duel-new" data-id="${p.id}">${ic("target")}Дуэль</button>${p.rel === "friend" && typeof SHOP !== "undefined" && SHOP && SHOP.on ? `<button class="btn ghost pset" data-act="gift-stars" data-to="${p.id}" aria-label="Подарить звёзды">${ic("giftbox")}</button>` : ""}`}</div>
    <div class="seg ptabs">${[["show", "sparkles", "Витрина"], ["gifts", "grid", "Подарки"], ["stats", "activity", "Стата"], ["legacy", "crown", "Наследие"], ["ach", "award", `${got}/${p.ach.length}`]].map(([k, i, t]) => `<button data-act="ptab" data-v="${k}" class="${tab === k ? "on" : ""}">${ic(i)}${t}</button>`).join("")}</div>
    ${body}
    ${isMe ? `<div class="disc">${esc(ME.disclaimer)}</div>` : ""}`;
}

const ACH_IC = { "Первый кейс": "gift", "Охотник за пасхалками": "award", "Кейсоман": "box", "Легенда": "crown", "Космонавт": "rocket", "На Луну": "moon", "Магнат": "wallet",
  "Коллекционер": "layers", "Душа компании": "heart", "Вербовщик": "megaphone", "Ветеран": "medal" };

// ============================================================ действия
Object.assign(ACT, {
  "my-invites": async () => {
    const d = await api("rooms");
    const inv = d.invites;
    if (inv.length === 1) return openRoom(inv[0].id);
    openSheet(`<h2 class="gtitle">Приглашение</h2>${inv.map(x => `<div class="dcard"><div class="dleft">${avaHTML(x.host, 36)}<div class="grow"><div class="t">${esc(x.host.name)} · ${esc(x.title)}</div>
      <div class="s">${x.count}/${x.maxp} игроков · ${x.kind === "gifts" ? "на подарки" : "⭐ " + fmt(x.stake)}</div></div></div><div class="dright"><button class="btn sm green" data-act="room" data-id="${x.id}">Открыть</button></div></div>`).join("") || emptyHTML("users", "Приглашений нет")}`);
  },
  friends: () => openFriends(),
  ptab: el => { const s = el.closest(".sheet"); s._ptab = el.dataset.v; H.sel(); replaceSheet(s, profileHTML(s._p, s._ptab)); },
  "inv-sort": el => { INV.sort = el.dataset.v; H.sel(); drawInventory(); },
  "inv-mode": el => { INV.mode = el.dataset.v; H.sel(); drawInventory(); },
  "inv-col": el => { INV.col = el.dataset.v; INV.mode = "gifts"; H.sel(); drawInventory(); scrollTo(0, 0); },
  "inv-sel": () => { INV.sel = INV.sel ? null : new Set(); H.sel(); drawInventory(); },
  "inv-tap": el => {
    if (!INV.sel) return openGift(REG.get(el.dataset.k));
    if (!MYP) return renderInventory();
    const id = +el.dataset.id, g = MYP.gifts.find(x => x.id === id);
    if (!g) return renderInventory();   // подарка уже нет (продан, ушёл в игру)
    if (g.price != null) return toast("Сначала сними подарок с маркета");
    INV.sel.has(id) ? INV.sel.delete(id) : INV.sel.add(id); H.sel(); drawInventory();
  },
  "inv-all": () => { if (!MYP) return renderInventory(); MYP.gifts.filter(g => g.price == null && (!INV.col || g.col === INV.col)).forEach(g => INV.sel.add(g.id)); H.sel(); drawInventory(); },
  "inv-sell": async () => {
    const ids = [...INV.sel]; if (!ids.length) return;
    if (!MYP) return renderInventory();
    const sum = MYP.gifts.filter(g => INV.sel.has(g.id)).reduce((s, g) => s + Math.floor(g.value * (1 - FEE("sell", .15))), 0);
    if (!await confirmM(`Продать ${ids.length} ${plural(ids.length, ["подарок", "подарка", "подарков"])}?`, `Получишь ⭐ ${fmt(sum)} (${sellP()} ценности).`, "Продать")) return;
    const r = await post("gifts/sell", { ids }); setStars(r.stars); H.ok(); toast(`Продано на ⭐ ${fmt(r.paid)}`);
    INV.sel = null; renderInventory();
  },
  mk: el => {
    const k = el.dataset.k, v = el.dataset.v;
    if (k === "mine") { MK.mine = +v; MK.rare = ""; } else if (k === "rare") { MK.rare = v; MK.mine = 0; } else MK[k] = v;
    H.sel(); renderMarket();
  },
  "mk-sell": () => pickGift("На маркет", listGift),
  list: () => { const g = topSheet()._o.g; closeSheet(); listGift(g); },
  trade: async el => {
    const v = el.dataset.v;
    if (v === "accept" && !await confirmM("Принять обмен?", "Подарки и звёзды сразу перейдут между вами.", "Принять")) return;
    try { await post(`trades/${el.dataset.id}/${v}`); }
    catch (e) { if (e.status !== "dup") refreshFriends(); return; }   // обмен уже закрыт / не хватает звёзд — убираем устаревшую карточку
    H.ok(); toast({ accept: "Обмен совершён", decline: "Отклонено", cancel: "Отменено" }[v]);
    await loadMe(); refreshFriends();
  },
});
// при смене вкладки убираем панель выбора
const _setTab = setTab;
setTab = function (t) { if (t !== "inv") { INV.sel = null; drawSelBar(); } _setTab(t); };

// ============================================================ ЕЖЕДНЕВНЫЕ ЗАДАНИЯ
async function openQuests() {
  H.imp("light");
  const el = openSheet(`<h2 class="gtitle">Задания</h2><div id="q-body">${emptyHTML("hourglass", "Загружаем…")}</div>`);
  el._q = true;
  fillQuests(el);
}
const QTAG = { 1: ["лёгкое", "#35d07f"], 2: ["среднее", "#4aa8ff"], 3: ["сложное", "#ff7a45"], new: ["новинка", "#c77dff"], event: ["событие", "#ffb21f"], week: ["неделя", "#ffc53d"] };
async function fillQuests(el) {
  const d = await api("quests"); if (!el.isConnected) return;
  const total = d.items.reduce((s, x) => s + x.reward, 0), done = d.items.filter(x => x.claimed).length;
  el.querySelector("#q-body").innerHTML = `<div class="qhead"><div><b>${done}/${d.items.length} выполнено</b><span>Обновятся через ${clock(d.resetIn)}</span></div><div class="qsum">до ⭐ ${fmt(total)}</div></div>
    <div class="box">${d.items.map(x => {
      const ready = x.have >= x.need && !x.claimed;
      const tag = QTAG[x.tier];
      return `<div class="row qrow${x.claimed ? " done" : ""}${x.tier === "chest" || x.tier === "week" ? " qchest" : ""}"><span class="pic ${x.claimed ? "g" : ready ? "y" : "b"}">${ic(x.claimed ? "check" : x.icon)}</span>
        <div class="grow">${tag ? `<span class="qtag" style="--c:${tag[1]}">${tag[0]}</span>` : ""}<div class="t">${esc(x.t)}</div><div class="cbar"><div style="width:${x.have / x.need * 100}%"></div></div><div class="s">${x.have}/${x.need} · награда ⭐ ${fmt(x.reward)}</div></div>
        ${ready ? `<button class="btn sm gold" data-act="q-claim" data-id="${x.id}">Забрать</button>` : x.claimed ? `<span class="tw" style="font-weight:800;font-size:13px">Готово</span>` : ""}</div>`;
    }).join("")}</div>
    <div class="disc">Задания засчитываются автоматически, пока ты играешь. Каждый день — новый набор.</div>`;
}
Object.assign(ACT, {
  quests: () => openQuests(),
  "q-claim": async el => {
    const r = await post(`quests/${el.dataset.id}/claim`); setStars(r.stars); H.ok(); toast(`+⭐ ${fmt(r.reward)}`, "ok"); burstAt(el);
    await loadMe(); for (const s of SHEETS) if (s._q) fillQuests(s);
    if (TAB === "cases") renderCases();
  },
});

Object.assign(ACT, {
  "e-pick": () => {
    const s = topSheet(), ed = s._ed;
    pickGifts("Подарки для витрины", { pre: ed.pinned.map(i => ({ id: i })), max: 6 }, gs => { ed.pinned = gs.map(g => g.id); s._edDraw(); });
  },
});

// редкость достижения (achrare.py): «есть у 12% игроков», меньше 5% подсвечиваем как редкое
function achPct(a) {
  if (a.pct == null) return "";
  if (!a.pct) return `<em class="ach-pct rare">пока ни у кого</em>`;
  const v = a.pct < 1 ? "<1%" : (a.pct >= 10 ? Math.round(a.pct) : String(a.pct).replace(".", LANG === "en" ? "." : ",")) + "%";
  return `<em class="ach-pct${a.pct < 5 ? " rare" : ""}"><span>есть у</span> ${v} <span>игроков</span></em>`;
}

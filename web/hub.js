"use strict";
// ============================================================
//  Разгрузка интерфейса:
//   · вкладка «Банк» (бывшая «Крипта»): Крипта · Доход · Акции · Кредиты
//   · колокольчик в шапке — входящие (копии сообщений бота)
//   · профиль — личный центр: задания, титулы, альбом, история, друзья, клан, идеи, настройки
//   · главная: акции/ивенты/сезон/турниры/доход/розыгрыш — одной листалкой; лента дропов убрана
//   · топ: два раздела — «Соревнования» и «Рейтинги»
// ============================================================
ICONS.bell = '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>';
ICONS.receipt = '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>';

// ---------------- 1. вкладка «Банк» ----------------
let BH = "shares";
const BH_TABS = [["crypto", "coin", "Крипта"], ["inc", "store", "Доход"], ["shares", "pie", "Акции"], ["loans", "coins", "Кредиты"]];
TITLES.crypto = "Банк";
(() => {
  const nb = document.querySelector('nav.tabs [data-tab="crypto"]');
  if (nb) nb.innerHTML = `<i>${ic("bank")}</i>Банк`;
  const nav = document.createElement("div"); nav.id = "bh-nav"; nav.className = "bh-nav";
  $("#v-crypto").before(nav);
})();
function bhNav() {
  const n = $("#bh-nav"); if (!n) return;
  n.innerHTML = BH_TABS.map(([k, i, t]) => `<button data-act="bh" data-v="${k}" class="${BH === k ? "on" : ""}">${ic(i)}<span>${t}</span></button>`).join("");
}
const _bhCx = TAB_RENDER.crypto;
TAB_RENDER.crypto = async function () {
  bhNav();
  const v = $("#v-crypto"), load = t => emptyHTML("hourglass", t);
  if (v._bh !== BH) { v.innerHTML = load("Загружаем…"); v._bh = BH; }
  if (BH === "crypto") return _bhCx();
  clearInterval(cxPoll); clearInterval(fxPoll);
  if (BH === "inc") { v.innerHTML = `<div id="inc-body">${load("Считаем доход…")}</div>`; await loadInc(); }
  else if (BH === "shares") { v.innerHTML = `<div id="bk-body">${load("Считаем банк…")}</div>`; await loadBK(); }
  else {
    v.innerHTML = `<div class="loans-sec">${load("Загружаем…")}</div>`;
    const h = await loansHTML(), s = v.querySelector(".loans-sec");
    if (s && BH === "loans") s.innerHTML = h;
  }
};
// крипто-экраны рисуют только в своём разделе
const _bhFill = fillCX;
fillCX = function () { if (BH === "crypto") _bhFill(); };
const _bhFut = fillFut;
fillFut = function (v) { if (BH === "crypto") _bhFut(v); };
// доход и акции рисуются прямо во вкладке
const _bhInc = loadInc;
loadInc = async function () { await _bhInc(); if (TAB === "crypto" && BH === "inc" && $("#v-crypto #inc-body")) fillInc($("#v-crypto")); };
const _bhBK = loadBK;
loadBK = async function () { await _bhBK(); if (TAB === "crypto" && BH === "shares" && BK && $("#v-crypto #bk-body")) _fillBKL($("#v-crypto")); };
setInterval(() => { if (TAB === "crypto" && BH === "inc" && !bgOff()) loadInc(); }, 30000);
function goBank(sec) {
  while (SHEETS.length) closeSheet();
  BH = sec;
  if (TAB === "crypto") TAB_RENDER.crypto(); else setTab("crypto");
}

// ---------------- 2. колокольчик ----------------
(() => {
  const b = document.createElement("button");
  b.className = "fr-btn bell-btn"; b.id = "bell-btn"; b.dataset.act = "inbox"; b.setAttribute("aria-label", "Уведомления");
  $("#fr-btn").before(b);
})();
function bellPaint() {
  const b = $("#bell-btn"); if (!b || !ME) return;
  const n = ME.inbox || 0;
  b.innerHTML = ic("bell") + (n ? `<span class="badge-dot">${n > 99 ? "99+" : n}</span>` : "");
  b.classList.toggle("ring", n > 0);
}
const _rhHub = renderHeader;
renderHeader = function () { _rhHub.apply(this, arguments); bellPaint(); };
async function bellPoll() {
  if (bgOff() || !ME) return;
  try { const m = await api("me"); if (m.inbox !== ME.inbox) { ME.inbox = m.inbox; bellPaint(); } } catch (e) {}
}
setInterval(bellPoll, 45000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) bellPoll(); });
const inboxIc = t => /битв/i.test(t) ? "target" : /сезон|турнир|приз|место/i.test(t) ? "trophy" : /кредит|долг|залог/i.test(t) ? "coins"
  : /клан|казн/i.test(t) ? "users" : /дуэл|стол|обмен/i.test(t) ? "swap" : /выигрыш|оценил|реакц/i.test(t) ? "flame"
  : /друз|заявк|приглаш|реферал/i.test(t) ? "userPlus" : /подар/i.test(t) ? "gift" : /доход|бизнес|дивиден/i.test(t) ? "wallet" : "bell";
const noEmoji = t => t.replace(/^[\p{Extended_Pictographic}️‍\s]+/u, "");
const dayLbl = ts => { const d = new Date(ts * 1000), n = new Date(); const y = new Date(n); y.setDate(n.getDate() - 1);
  return d.toDateString() === n.toDateString() ? "Сегодня" : d.toDateString() === y.toDateString() ? "Вчера" : d.toLocaleDateString("ru", { day: "numeric", month: "long" }); };
const hhmm = ts => new Date(ts * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
async function openInbox() {
  H.imp("light");
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "ib-s");
  const d = await api("inbox").catch(() => null); if (!d || !el.isConnected) return;
  ME.inbox = 0; bellPaint();
  let last = "";
  replaceSheet(el, `<h2 class="gtitle">${ic("bell")} Уведомления</h2>
    ${d.items.length ? d.items.map(x => { const day = dayLbl(x.ts), head = day !== last ? `<div class="ib-day">${day}</div>` : ""; last = day;
      return `${head}<div class="ib-it${x.new ? " new" : ""}"><span class="ib-i">${ic(inboxIc(x.text))}</span><div class="grow"><p>${esc(noEmoji(x.text))}</p><span>${hhmm(x.ts)}</span></div></div>`; }).join("")
      : emptyHTML("bell", "Пока тихо. Здесь будут итоги битв, реакции на твои выигрыши, кредиты, клан и подарки")}
    <div class="disc">Те же сообщения приходят от бота в Telegram — их можно отключить в настройках.</div>`);
}

// ---------------- 3. профиль — личный центр ----------------
async function openHistory() {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "hs-s");
  const d = await api("history").catch(() => null); if (!d || !el.isConnected) return;
  const rows = [];   // подряд идущие раунды одной игры склеиваем
  for (const x of d.items) {
    const p = rows[rows.length - 1];
    if (p && p.kind === x.kind && p.ts - x.ts < 600) { p.delta += x.delta; p.n++; p.ts0 = x.ts; } else rows.push({ ...x, n: 1, ts0: x.ts });
  }
  let last = "";
  replaceSheet(el, `<h2 class="gtitle">${ic("receipt")} История</h2><p class="hint" style="margin:-6px 0 12px">Последние движения звёзд. Раунды одной игры подряд собраны в одну строку.</p>
    ${rows.length ? `<div class="box">${rows.map(r => { const day = dayLbl(r.ts), head = day !== last ? `<div class="hs-day">${day}</div>` : ""; last = day;
      return `${head}<div class="row hs-row"><div class="grow"><div class="t">${esc(r.name)}${r.n > 1 ? ` <span class="hint">× ${r.n}</span>` : ""}</div><div class="s">${hhmm(r.ts0)}${r.n > 1 ? "–" + hhmm(r.ts) : ""}</div></div>
        <b class="${r.delta >= 0 ? "tw" : "tl"}">${r.delta >= 0 ? "+" : "−"}⭐ ${fmt(Math.abs(r.delta))}</b></div>`; }).join("")}</div>`
      : emptyHTML("receipt", "Операций пока нет")}`);
  starify(el);
}
const P_MENU = () => [
  ["quests", "checks", "Задания", ME.quests ? ME.quests : ""],
  ["titles", "medal", "Титулы", ""],
  ["album", "layers", "Альбом", ""],
  ["history", "receipt", "История", ""],
  ["friends", "users", "Друзья", ""],
  ["go-clan", "crown", ME.clan ? "Мой клан" : "Кланы", ME.clanChat || ""],
  ["support", "support", "Поддержка", (ME.tickets && ME.tickets.unread) || ""],
  ["idea", "megaphone", "Идеи", ""],
  ["settings", "gear", "Настройки", ""],
];
const _phHub = profileHTML;
profileHTML = function (p, tab) {
  const h = _phHub(p, tab);
  if (!ME || p.id !== ME.id) return h;
  const menu = `<div class="pmenu">${P_MENU().map(([a, i, t, b]) => `<button data-act="${a}"><span>${ic(i)}${b ? `<em>${b}</em>` : ""}</span>${t}</button>`).join("")}</div>
    <div class="pacts"><button class="btn ghost" data-act="edit-profile">${ic("edit")}Изменить</button><button class="btn" data-act="invite">${ic("send")}Позвать</button></div>`;
  return h.replace(/<div class="pacts">[\s\S]*?<\/div>/, menu);
};

// ---------------- 4–5. главная: листалка вместо стопки плашек, без ленты дропов ----------------
let SSB = null, SSB_T = 0, TRB_T = 0, SHB_T = 0;
const ST_ORDER = ["st-poll", "st-wipe", "st-spark", "ob", "st-shop", "st-offer", "prib", "evrib", "incbar", "st-season", "tr-bar", "jpbar", "homecard"];
loadFeed = async function () {};
const _rcHub = renderCases;
renderCases = async function () {
  await _rcHub();
  casesTidy();
  setTimeout(casesTidy, 150);
  // карточки листалки (сезон, магазин, предложения, турниры) — после первой отрисовки, не мешая показать главную
  const later = f => (window.requestIdleCallback ? requestIdleCallback(f, { timeout: 1200 }) : setTimeout(f, 300));
  later(() => {
    if (Date.now() - SSB_T > 120000) { SSB_T = Date.now(); api("season/brief").then(d => { SSB = d; casesTidy(); }).catch(() => {}); }
    if (Date.now() - SHB_T > 300000) { SHB_T = Date.now(); api("shop").then(d => { SHOP = d; casesTidy(); }).catch(() => {}); }
    if (!PREM || Date.now() - PREM_T > 120000) loadPrem().then(() => casesTidy());
    if (Date.now() - TRB_T > 300000) { TRB_T = Date.now(); api("tournaments").then(d => { TR = d; casesTidy(); }).catch(() => {}); }
  });
};
function seasonCard() {
  if (!SSB) return "";
  const left = Math.max(0, SSB.ends - Date.now() / 1000), dd = Math.floor(left / 86400);
  return `<button class="stc st-season" data-act="go-season"><span class="stc-i">${ic("flame")}</span><span class="stc-t"><b>Сезон · ${esc(SSB.title)}</b>
    <small>${SSB.place ? `ты ${SSB.place}-й из ${SSB.players} · ${fmt(SSB.pts)} очк.` : `главный приз ⭐ ${short(SSB.prize)} — сыграй и попади в рейтинг`} · ещё ${dd} д</small></span>${ic("chev")}</button>`;
}
function shopCard() {   // только тем, кто ещё ни разу не покупал
  if (!SHOP || !SHOP.on || !SHOP.first || !inTg) return "";
  return `<button class="stc st-shop" data-act="qb-all"><span class="stc-i"><b>×2</b></span><span class="stc-t"><b>Первая покупка — звёзд вдвое больше</b>
    <small>1 Telegram Star = ${fmt(SHOP.rate * 2)} ⭐ на первом пополнении · бонус до ${short(SHOP.firstCap)} ⭐</small></span>${ic("chev")}</button>`;
}
function sparkCard() {   // друзья уже прислали огоньки — ответь
  const n = ME && ME.sparks; if (!n) return "";
  return `<button class="stc st-spark" data-act="friends"><span class="stc-i">${flameHTML({ count: 1, tier: "red", done: true })}</span><span class="stc-t"><b>${n} ${plural(n, ["друг прислал", "друга прислали", "друзей прислали"])} огонёк</b>
    <small>Ответь до полуночи — серия вырастет, иначе сгорит</small></span>${ic("chev")}</button>`;
}
function tournCard() {
  if (!TR || !TR.items || !TR.items.length) return "";
  const left = Math.max(0, TR.weekEnds - Date.now() / 1000), dd = Math.floor(left / 86400), hh = Math.floor(left % 86400 / 3600);
  return `<button class="stc tr-bar" data-act="tourn"><span class="stc-i">${ic("trophy")}</span><span class="stc-t"><b>Турниры</b>
    <small>${TR.items.map(i => esc(i.title)).join(" · ")} · фонд ⭐ ${short(TR.items[0].pool)} · ${dd ? dd + " д " : ""}${hh} ч</small></span>${ic("chev")}</button>`;
}
// перестройку листалки зовут до 7 раз подряд (сразу, по таймеру, после каждого запроса) — склеиваем в одну за кадр
let tidyQ = 0;
function casesTidy() { if (!tidyQ) tidyQ = requestAnimationFrame(() => { tidyQ = 0; casesTidyNow(); }); }
function casesTidyNow() {
  const v = $("#v-cases"); if (!v || !v.innerHTML) return;
  // лента дропов — больше не на главной (полная лента выигрышей — по нажатию на бегущую строку)
  const f = v.querySelector("#feed");
  if (f) { const s = f.previousElementSibling; if (s && s.querySelector(".live-dot")) s.remove(); f.remove(); }
  // заглушка: старый код не будет склеивать доход и розыгрыш в ряд
  if (!v.querySelector(".dash2")) v.insertAdjacentHTML("beforeend", `<div class="dash2" hidden></div>`);
  v.querySelectorAll(".dash2:not([hidden])").forEach(d => { d.replaceWith(...d.children); });
  let st = v.querySelector(".stories");
  if (!st) {
    st = document.createElement("div"); st.className = "stories";
    st.innerHTML = `<div class="st-track"></div><div class="st-dots"></div>`;
    const anchor = v.querySelector(".promo");
    anchor ? anchor.after(st) : v.prepend(st);
    stBind(st);
  }
  const track = st.querySelector(".st-track");
  // свои карточки (сезон, турниры) — перерисовываем
  [["st-poll", pollCard()], ["st-wipe", wipeCard()], ["st-season", seasonCard()], ["tr-bar", tournCard()], ["st-shop", shopCard()], ["st-spark", sparkCard()], ["st-offer", offerCard()]].forEach(([k, html]) => {
    const old = track.querySelector(`.st-sl[data-k="${k}"]`);
    if (old) old.remove();
    if (html) v.insertAdjacentHTML("beforeend", html);
  });
  // всё, что разные модули вставили на главную, переносим в листалку
  ST_ORDER.forEach(k => {
    v.querySelectorAll("." + k).forEach(el => {
      const par = el.parentElement;
      if (par.classList.contains("st-sl") && par.dataset.k === k) return;
      if (k === "ob" && !el.innerHTML.trim()) return;   // «Старт новичка» ещё не загрузился
      const sl = document.createElement("div"); sl.className = "st-sl"; sl.dataset.k = k;
      el.replaceWith(sl); sl.appendChild(el);
      track.appendChild(sl);
    });
  });
  track.querySelectorAll(".st-sl").forEach(x => { if (!x.children.length) x.remove(); });   // «Старт новичка» пройден — карточка ушла
  [...track.children].sort((a, b) => ST_ORDER.indexOf(a.dataset.k) - ST_ORDER.indexOf(b.dataset.k)).forEach(x => track.appendChild(x));
  // пустые и скрытые блоки (ивент без ивента и т. п.) не занимают слайд и не дают лишнюю точку
  // сначала всё читаем, потом всё пишем: чередование «спросить стиль → поменять hidden» заставляло браузер
  // пересчитывать стили страницы на каждом слайде (сотни мс при запуске на слабых телефонах)
  const sls = [...track.querySelectorAll(".st-sl")];
  sls.forEach(x => { x.hidden = false; });
  const show = sls.map(x => [...x.children].some(stShown));
  sls.forEach((x, i) => { x.hidden = !show[i]; });
  const n = stSlides(track).length, cur = n > 1 ? stIdx(track) : 0;
  st.hidden = !n;
  st.querySelector(".st-dots").innerHTML = n > 1 ? Array.from({ length: n }, (_, i) => `<i class="${i === cur ? "on" : ""}"></i>`).join("") : "";
}
const stShown = el => !el.hidden && el.innerHTML.trim() !== "" && getComputedStyle(el).display !== "none";
const stSlides = tr => [...tr.children].filter(x => !x.hidden);
const stIdx = tr => { const f = stSlides(tr)[0], w = f ? f.offsetWidth + 8 : 1; return Math.round(tr.scrollLeft / w); };
function stBind(st) {
  const tr = st.querySelector(".st-track");
  let touched = 0;
  let raf = 0;   // точки — раз в кадр, а не на каждое событие прокрутки
  tr.addEventListener("scroll", () => { if (raf) return; raf = requestAnimationFrame(() => { raf = 0; const i = stIdx(tr); st.querySelectorAll(".st-dots i").forEach((d, j) => d.classList.toggle("on", i === j)); }); }, { passive: true });
  tr.addEventListener("pointerdown", () => { touched = Date.now(); }, { passive: true });
  const t = setInterval(() => {   // сама листается раз в 6 с, пока игрок её не трогает
    if (!st.isConnected) return clearInterval(t);
    if (TAB !== "cases" || SHEETS.length || document.hidden || Date.now() - touched < 12000 || document.documentElement.classList.contains("lite")) return;
    const n = stSlides(tr).length; if (n < 2) return;
    const i = (stIdx(tr) + 1) % n, w = stSlides(tr)[0].offsetWidth + 8;
    tr.scrollTo({ left: i * w, behavior: "smooth" });
  }, 6000);
}

const _obHub = loadOB;
loadOB = async function () { await _obHub(); if (TAB === "cases") casesTidy(); };

// ---------------- 12. топ: «Соревнования» и «Рейтинги» ----------------
const TOP_COMP = ["league", "clans", "season"];
const TOP_LAST = { comp: "league", rate: "rich" };
topKind = "league";   // топ открывается на лиге недели — она про самого игрока
function topNavHTML() {
  const g = TOP_COMP.includes(topKind) ? "comp" : "rate";
  TOP_LAST[g] = topKind;
  const list = TOPK.filter(([k]) => TOP_COMP.includes(k) === (g === "comp"));
  if (g === "comp") list.sort((a, b) => TOP_COMP.indexOf(a[0]) - TOP_COMP.indexOf(b[0]));
  return `<div class="seg top-grp"><button data-act="topg" data-v="comp" class="${g === "comp" ? "on" : ""}">${ic("trophy")}Соревнования</button>
      <button data-act="topg" data-v="rate" class="${g === "rate" ? "on" : ""}">${ic("trend")}Рейтинги</button></div>
    <div class="chips" style="margin-bottom:12px">${list.map(([k, i, t]) => `<button data-act="topk" data-v="${k}" class="${k === topKind ? "on" : ""}">${ic(i)}${t}</button>`).join("")}${g === "comp" ? `<button data-act="tourn">${ic("target")}Турниры</button>` : ""}</div>`;
}

Object.assign(ACT, {
  bh: el => { if (BH === el.dataset.v) return; BH = el.dataset.v; H.sel(); scrollTo(0, 0); TAB_RENDER.crypto(); },
  inc: () => goBank("inc"),
  bank: () => goBank("shares"),
  "loans-open": () => goBank("loans"),
  inbox: () => openInbox(),
  "bk-top": el => {   // переключатель держателей акций — и в шторке, и во вкладке
    bkTop = el.dataset.v; H.sel();
    const s = el.closest(".sheet") || $("#v-crypto");
    s.querySelectorAll(".bk-tabs button").forEach(b => b.classList.toggle("on", b === el)); s.querySelector("#bk-top").innerHTML = bkTopHTML();
  },
  history: () => openHistory(),
  "go-clan": () => {
    if (ME.clan) return ACT["clan-tag"]({ dataset: { tag: ME.clan } });
    while (SHEETS.length) closeSheet(); topKind = "clans"; TAB === "top" ? renderTop() : setTab("top");
  },
  "go-season": () => { while (SHEETS.length) closeSheet(); topKind = "season"; TAB === "top" ? renderTop() : setTab("top"); },
  topg: el => { topKind = TOP_LAST[el.dataset.v]; H.sel(); renderTop(); },
});

// раздел «Банка» показываем только на своей вкладке
document.body.dataset.view = TAB;
const _stHub = setTab;
setTab = function (t) { document.body.dataset.view = t; return _stHub(t); };

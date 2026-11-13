// ============================================================ PWR: слияние с PWR SKINBOX и RubUp Web
// · вкладки витрины кейсов: Все / Подарки / CS / RubUp
// · боевой пропуск: ежедневные кейсы FREE / PWR / VIP с серией (7-й день — улучшенный)
// · задания SKINBOX в шторке «Задания»: подписка, друг, реклама
// Подключается последним: оборачивает renderCases / openCase / fillQuests, как это делают остальные модули.
let PWR = null;
let CTAB = (() => { try { return localStorage.getItem("np_ctab") || "all"; } catch (e) { return "all"; } })();
const CTABS = [["all", "Все"], ["tg", "Подарки"], ["cs", "CS"]];
const pwrLoad = async () => { try { PWR = await api("pwr"); } catch (e) {} return PWR; };
const pwrImg = (name, s = 256) => A.orig(name, s);
// арт и ролики из Higgsfield (tools/fetch_art.py → web/gen/): используем только то, что скачалось при сборке
const GEN = window.GEN_ART || {};
if (GEN.bg) { document.documentElement.style.setProperty("--gen-bg", `url("${GEN.bg}")`); document.documentElement.classList.add("has-genbg"); }
for (const g of GAMES) if (GEN["game_" + g.id]) g.imgUrl = GEN["game_" + g.id];
const pwrLite = () => document.documentElement.classList.contains("lite");
// адреса картинок с меткой версии: первая выкладка отдавала по скинам CS ответ 301, и браузеры его запомнили
for (const k of ["model", "orig"]) { const f = A[k]; A[k] = (...a) => f(...a) + "&r=4"; }

// ---------------- главная: баннер пропуска и вкладки витрины ----------------
function pwrBannerHTML() {
  const p = PWR && PWR.pass; if (!p) return "";
  const mine = p.tiers.filter(t => t.owned), ready = mine.filter(t => !t.done).length;
  const best = mine[mine.length - 1] || p.tiers[0], f = p.tiers[0];
  return `<button class="pp-banner${ready ? " ready" : ""}${GEN.pass_banner ? " art" : ""}" data-act="pwr-pass" style="--pc:${best.color}${GEN.pass_banner ? `;--art:url('${GEN.pass_banner}')` : ""}">
    <span class="pp-b-art"><img src="${pwrImg(best.cover)}" alt=""></span>
    <span class="pp-b-t"><i>Кейс каждый день</i><b>Боевой пропуск</b>
      <small>${ready ? `${ready} ${plural(ready, ["кейс ждёт", "кейса ждут", "кейсов ждут"])} — забери` : `Новые кейсы через ${clock(p.resetIn)}`}</small>
      <span class="pp-days">${Array.from({ length: f.days }, (_, i) => `<i class="${i < (f.done ? f.day : f.day - 1) ? "on" : ""}${i === f.days - 1 ? " last" : ""}"></i>`).join("")}</span></span>
    <span class="pp-b-go">${ready ? "Открыть" : ic("chev")}</span></button>`;
}
function pwrPaint() {
  const v = $("#v-cases"), grid = v && v.querySelector(".cases"); if (!grid) return;
  const group = id => (CASES.find(c => c.id === id) || {}).group || "tg";
  if (!v.querySelector(".ctabs")) {
    const n = g => CASES.filter(c => c.id !== "free" && (g === "all" || c.group === g)).length;
    grid.insertAdjacentHTML("beforebegin", `<div class="ctabs${GEN.cat_tg ? " art" : ""}">${CTABS.map(([k, t]) => `<button data-act="ctab" data-v="${k}" class="${CTAB === k ? "on" : ""}">${GEN["cat_" + k] ? `<img src="${GEN["cat_" + k]}" alt="">` : ""}${t}<em>${n(k)}</em></button>`).join("")}</div>`);
  }
  v.querySelectorAll(".ctabs button").forEach(b => b.classList.toggle("on", b.dataset.v === CTAB));
  let hidden = 0, next = 99;
  v.querySelectorAll(".case").forEach(c => {
    const g = group(c.dataset.id), hide = CTAB !== "all" && g !== CTAB;
    c.classList.toggle("pwr-hide", hide); c.dataset.g = g;
    const cs = CASES.find(x => x.id === c.dataset.id), pr = c.querySelector(".pr");   // цены оригиналов: бесплатный кейс RubUp и суммы до миллиарда
    if (cs && pr && cs.src && !pr.dataset.f) { pr.dataset.f = 1; if (!cs.price) pr.textContent = "Бесплатно"; else if (cs.price >= 1e7) pr.innerHTML = "⭐ " + short(cs.price); }
    if (!hide) c.classList.remove("defer");
    if (!hide && c.closest("#cases-locked")) { hidden++; next = Math.min(next, (CASES.find(x => x.id === c.dataset.id) || {}).level || 99); }
  });
  const det = v.querySelector("details.locked");   // свёрнутый блок закрытых по уровню кейсов — считаем только текущую вкладку
  if (det) {
    det.classList.toggle("pwr-hide", !hidden);
    const sm = det.querySelector("summary");
    if (sm && hidden) sm.innerHTML = `${ic("lock")}Откроются с уровнем · ${hidden} ${plural(hidden, ["кейс", "кейса", "кейсов"])}<span>следующий на ${next} ур.</span>`;
  }
  const old = v.querySelector(".pp-banner"), html = pwrBannerHTML();
  if (old) old.outerHTML = html || "";
  else if (html) { const t = v.querySelector(".ctabs").previousElementSibling; (t && t.classList.contains("sec-t") ? t : v.querySelector(".ctabs")).insertAdjacentHTML("beforebegin", html); }
}
const _rcPwr = renderCases;
renderCases = async function () {
  if (!CASES.length) CASES = await api("cases");
  CASES.forEach(c => { if (c.k) CASE_COL[c.id] = c.k; });
  await _rcPwr();
  pwrPaint();
  if (!PWR) pwrLoad().then(pwrPaint);
};

// вспышка при открытии кейса: ролик на чёрном фоне накладывается на шапку кейса в режиме «экран» (чёрное становится прозрачным)
function pwrBurst(sheet) {
  const hero = sheet && sheet.querySelector(".chero");
  if (!GEN.case_burst || !hero || pwrLite() || OPEN.fast || hero.querySelector(".pp-burst")) return;
  const v = document.createElement("video");
  v.className = "pp-burst"; v.src = GEN.case_burst; v.muted = true; v.playsInline = true; v.setAttribute("playsinline", ""); v.preload = "auto";
  const done = () => { v.classList.add("out"); setTimeout(() => v.remove(), 500); };
  v.addEventListener("loadedmetadata", () => { try { v.currentTime = 0.9; } catch (e) {} }, { once: true });
  v.addEventListener("ended", done, { once: true }); v.addEventListener("error", () => v.remove(), { once: true });
  setTimeout(done, 4600);
  hero.appendChild(v);
  const p = v.play(); if (p && p.catch) p.catch(() => v.remove());
}
const _doPwr = doOpen;
doOpen = async function (sheet, id) {
  const c = CASES.find(x => x.id === id), n = c && (c.keys ? 1 : c.price ? OPEN.n : 1);
  if (c && !opening && (c.keys || (ME.lv.level >= c.level && c.price * n <= ME.stars)) && !(id === "free" && !c.keys && ME.freeIn > 0)) pwrBurst(sheet);
  return _doPwr(sheet, id);
};

// у кейсов SKINBOX нет планки ценности — правим подпись под списком «Что внутри»
const _ocPwr = openCase;
openCase = function (id) {
  _ocPwr(id);
  const c = CASES.find(x => x.id === id), el = SHEETS[SHEETS.length - 1];
  if (!c || !el || !el._case || el._case.id !== id) return;
  el.classList.add("cs-" + (c.group || "tg"));
  if (GEN.case_burst && !pwrLite() && !window._burstWarm) { window._burstWarm = 1; fetch(GEN.case_burst).catch(() => {}); }   // ролик вспышки — в кэш заранее
  const d = el.querySelector(".disc");
  if (c.src === "cs" && d) d.textContent = d.textContent.replace(/Из платного кейса не выпадает[^.]*\.\s*/, "Чем дороже скин, тем он реже. Пропуск «Плюс» и «Премиум» повышают шансы на дорогие скины. Скин продаётся за полную ценность. ");
  if (c.src === "ru") {   // RubUp: шесть категорий с шансом, внутри категории подарки равновероятны; у каждого подарка твёрдая цена
    if (d) d.textContent = d.textContent.replace(/Из платного кейса не выпадает[^.]*\.\s*/, "Шанс указан для категории; внутри категории подарки выпадают равновероятно. Подарок продаётся за полную ценность. ");
    const grid = el.querySelector(".ggrid"), tiers = [];
    c.gifts.forEach(g => { if (!tiers.includes(g.tier)) tiers.push(g.tier); });
    const share = t => c.gifts.filter(g => g.tier === t).reduce((a, g) => a + g.p, 0);
    if (grid) {
      grid.insertAdjacentHTML("beforebegin", `<div class="ru-tiers">${tiers.map((t, i) => `<span class="rt-${i}"><b>${String(Math.round(share(t) * 10) / 10).replace(".", ",")}%</b>${esc(t)}</span>`).join("")}</div>`);
      grid.innerHTML = [...c.gifts].sort((a, b) => b.ev - a.ev).map(g => `<div class="gcell item rt-${tiers.indexOf(g.tier)}">${giftHTML(g, { plain: true, lite: true })}
        <span class="chance">${g.p < 1 ? g.p.toFixed(2) : g.p.toFixed(1)}%</span><div class="rbar"></div>
        <div class="cap">${esc(g.col)}<br><small>${esc(g.model)} · ⭐ ${short(g.ev)}</small></div></div>`).join("");
    }
    if (!c.price) { const cp = el.querySelector(".cprice"); if (cp) cp.textContent = "Бесплатно · раз в " + (c.freeEvery >= 3600 ? Math.round(c.freeEvery / 3600) + " ч" : Math.max(1, Math.round((c.freeEvery || 60) / 60)) + " мин"); }
  }
};

// ---------------- шторка пропуска ----------------
function pwrTierHTML(t, p) {
  const days = Array.from({ length: t.days }, (_, i) => {
    const d = i + 1, got = t.done ? d <= t.day : d < t.day, cur = !t.done && d === t.day;
    return `<i class="${got ? "on" : ""}${cur ? " cur" : ""}${d === t.days ? " last" : ""}">${d === t.days ? ic("sparkles") : d}</i>`;
  }).join("");
  const inside = [...(t.stars ? [`<span class="pp-in st"><b>⭐</b><small>${fmt(t.stars.min)}–${fmt(t.stars.max)}</small></span>`] : []),
    ...t.skins.slice(0, t.stars ? 4 : 5).map(s => `<span class="pp-in"><img src="${A.orig(s.col, 128)}" alt="" loading="lazy"><small>⭐ ${short(s.ev)}</small></span>`)].join("");
  const cta = !t.owned ? `<button class="btn cta gold" data-act="pwr-buy" data-id="${t.id}">Купить за ${fmt(t.xtr)} Telegram Stars · ${t.days} дней</button>`
    : t.done ? `<button class="btn cta ghost" disabled>Открыт · новый через ${clock(p.resetIn)}</button>`
      : `<button class="btn cta gold" data-act="pwr-open" data-id="${t.id}">${t.improved ? "Открыть улучшенный кейс" : "Открыть кейс дня"}</button>`;
  return `<div class="pp-tier${t.owned ? " owned" : ""}${t.improved ? " imp" : ""}" style="--pc:${t.color}">
    <div class="pp-head"><span class="pp-art"><img src="${pwrImg(t.cover, 256)}" alt=""></span>
      <div class="grow"><div class="pp-name"><img src="${pwrImg(t.badge, 64)}" alt=""><b>${esc(t.title)}</b>${t.owned && t.until ? `<em>до ${new Date(t.until * 1000).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</em>` : t.owned ? "" : `<em class="lock">${ic("lock")}</em>`}</div>
        <div class="pp-sub">День ${t.day} из ${t.days}${t.improved ? " · улучшенный кейс" : ""}</div>
        <div class="pp-track">${days}</div></div></div>
    <div class="pp-ins">${inside}</div>
    ${t.benefits.length ? `<ul class="pp-ben">${t.benefits.map(b => `<li>${esc(b)}</li>`).join("")}</ul>` : `<div style="height:12px"></div>`}
    ${cta}</div>`;
}
function pwrPassBody() {
  const p = PWR && PWR.pass;
  if (!p) return emptyHTML("hourglass", "Загружаем…");
  const hero = GEN.pass_banner ? `<div class="pp-hero">${GEN.pass_loop && !pwrLite()
    ? `<video src="${GEN.pass_loop}" poster="${GEN.pass_banner}" autoplay muted loop playsinline preload="metadata"></video>` : `<img src="${GEN.pass_banner}" alt="">`}</div>` : "";
  return `${hero}<div class="pp-lead">Каждый день — кейс. Семь дней подряд — улучшенный кейс с наградами лучше.</div>
    <div id="pp-won"></div>
    ${p.tiers.map(t => pwrTierHTML(t, p)).join("")}
    <div class="disc">С 1-го по 6-й день — кейс дня, на 7-й — улучшенный. Сутки считаются по UTC. Серия Free сгорает после пропущенного дня, серии PWR и VIP — нет. При покупке обоих пропусков их эффекты не суммируются. Скины CS здесь игровые: вывода в Steam нет.</div>`;
}
async function pwrPassOpen() {
  H.imp("light");
  const el = openSheet(`<h2 class="gtitle">Пропуск</h2><div id="pp-body">${pwrPassBody()}</div>`, "pp-sheet");
  el._pp = true;
  await pwrLoad(); pwrPassFill();
}
function pwrPassFill(keepWon) {
  for (const s of SHEETS) if (s._pp) { const b = s.querySelector("#pp-body"), won = keepWon && b.querySelector("#pp-won"), html = won ? won.innerHTML : ""; b.innerHTML = pwrPassBody(); if (html) b.querySelector("#pp-won").innerHTML = html; }
  if (TAB === "cases") pwrPaint();
}
Object.assign(ACT, {
  "pwr-pass": () => pwrPassOpen(),
  ctab: el => { CTAB = el.dataset.v; try { localStorage.setItem("np_ctab", CTAB); } catch (e) {} H.sel(); pwrPaint(); },
  "pwr-open": async el => {
    el.disabled = true;
    let r;
    try { r = await post(`pwr/pass/${el.dataset.id}/open`); } catch (e) { el.disabled = false; return; }
    PWR.pass = r.pass; setStars(r.stars); H.ok();
    const sheet = el.closest(".sheet"), won = sheet && sheet.querySelector("#pp-won");
    const body = r.gift
      ? `<div class="won pp-wonbox"><div class="won-g"><i class="won-rays"></i>${giftHTML(r.gift, { big: true })}</div>
          <h2>${esc(r.gift.col)}</h2><div class="hint">${esc(r.gift.model)} · ≈ ⭐ ${fmt(r.gift.value)}</div><small>Скин уже в «Сумке»</small></div>`
      : `<div class="won pp-wonbox"><div class="pp-stars">⭐</div><h2>+ ${fmt(r.reward)}</h2><div class="hint">Звёзды на балансе</div></div>`;
    if (won) { won.innerHTML = body; startLottie(won); }
    pwrPassFill(true);
    if (sheet) { sheet.scrollTo({ top: 0, behavior: "smooth" }); const w = sheet.querySelector(".pp-wonbox"); if (w) burstAt(w, r.gift); }
    toast(r.gift ? `День ${r.day}: ${r.gift.col}` : `День ${r.day}: +⭐ ${fmt(r.reward)}`, "ok");
    loadMe().catch(() => {});
  },
  "pwr-buy": async el => {
    const t = PWR.pass.tiers.find(x => x.id === el.dataset.id); if (!t) return;
    if (!inTg || !tg.openInvoice) return toast("Покупка доступна только в Telegram");
    el.disabled = true;
    try {
      const r = await post(`pwr/pass/${t.id}/invoice`);
      tg.openInvoice(r.link, async status => {
        el.disabled = false;
        if (status === "failed") return toast("Оплата не прошла");
        if (status !== "paid") return;
        H.ok(); toast(`${t.title} активен на ${t.days} дней`, "ok");
        for (let i = 0; i < 8; i++) { await sleep(1200); await pwrLoad(); if (PWR.pass.tiers.find(x => x.id === t.id).owned) break; }
        CASES = []; pwrPassFill(); if (TAB === "cases") renderCases();   // с пропуском меняются шансы кейсов SKINBOX — перечитываем витрину
      });
    } catch (e) { el.disabled = false; }
  },
  "pwr-sub": async el => {
    const t = PWR.tasks.items.find(x => x.id === "sub");
    if (t && t.url && !el.dataset.went) { el.dataset.went = 1; el.textContent = "Проверить"; return inTg && tg.openTelegramLink ? tg.openTelegramLink(t.url) : window.open(t.url, "_blank"); }
    const r = await post("pwr/task/sub/claim"); PWR.tasks = r.tasks; setStars(r.stars); H.ok(); toast(`+⭐ ${fmt(r.reward)}`, "ok"); burstAt(el);
    for (const s of SHEETS) if (s._q) fillQuests(s);
  },
  "pwr-ad": async el => {
    const block = PWR.tasks.adsBlock; if (!block) return toast("Реклама не подключена");
    el.disabled = true;
    try {
      if (!window.Adsgram) await new Promise((ok, no) => { const s = document.createElement("script"); s.src = "https://sad.adsgram.ai/js/sad.min.js"; s.onload = ok; s.onerror = no; document.head.appendChild(s); });
      await window.Adsgram.init({ blockId: block }).show();
      const before = PWR.tasks.items.find(x => x.id === "ad").have;   // награду начисляет сервер по обратному вызову Adsgram — ждём её
      for (let i = 0; i < 6; i++) { await sleep(1200); await pwrLoad(); if (PWR.tasks.items.find(x => x.id === "ad").have > before) break; }
      await loadMe(); H.ok(); toast("Награда за рекламу начислена", "ok");
    } catch (e) { toast("Сейчас нет доступной рекламы"); }
    el.disabled = false;
    for (const s of SHEETS) if (s._q) fillQuests(s);
  },
});

// ---------------- задания SKINBOX — отдельным блоком в шторке «Задания» ----------------
function pwrTasksHTML() {
  const t = PWR && PWR.tasks; if (!t) return "";
  const btn = x => !x.on ? `<span class="pt-off">скоро</span>` : x.done ? `<span class="tw" style="font-weight:800;font-size:13px">Готово</span>`
    : x.id === "sub" ? `<button class="btn sm gold" data-act="pwr-sub">Подписаться</button>`
      : x.id === "invite" ? `<button class="btn sm gold" data-act="invite">Позвать</button>`
        : `<button class="btn sm gold" data-act="pwr-ad">Смотреть</button>`;
  const sub = x => x.id === "invite" ? `${ME.refBonus ? `награда ⭐ ${fmt(ME.refBonus)} за друга · ` : ""}приглашено: ${x.have}`
    : !x.on ? esc(x.why) : x.id === "ad" ? `${x.have}/${x.need} сегодня · награда ⭐ ${fmt(x.reward)}` : `награда ⭐ ${fmt(x.reward)}`;
  return `<div class="sec-t">Реклама и подписка${t.k > 1 ? `<span class="pt-k">×${String(t.k).replace(".", ",")} с пропуском</span>` : ""}</div>
    <div class="box">${t.items.map(x => `<div class="row qrow${x.done ? " done" : ""}${x.on ? "" : " pt-dim"}"><span class="pic ${x.done ? "g" : "b"}">${ic(x.done ? "check" : x.icon === "play" ? "eye" : x.icon)}</span>
      <div class="grow"><div class="t">${esc(x.t)}</div><div class="s">${sub(x)}</div></div>${btn(x)}</div>`).join("")}</div>`;
}
const _fqPwr = fillQuests;
fillQuests = async function (el) {
  await Promise.all([_fqPwr(el), pwrLoad()]);
  if (!el.isConnected) return;
  const b = el.querySelector("#q-body"), d = b && b.querySelector(".disc");
  if (b && !b.querySelector(".pt-k,.pt-wrap")) { const w = document.createElement("div"); w.className = "pt-wrap"; w.innerHTML = pwrTasksHTML(); d ? d.before(w) : b.appendChild(w); }
};

/* «Задания» в нижней панели: счётчик готовых наград */
function pwrQuestDot() { const e = document.getElementById("tq-n"); if (!e) return; const n = ME && ME.quests ? ME.quests : 0; e.textContent = n ? (n > 9 ? "9+" : n) : ""; e.classList.toggle("on", !!n); }
const _rhPwr = renderHeader;
renderHeader = function () { const r = _rhPwr.apply(this, arguments); pwrQuestDot(); return r; };

/* ---------------- вывод скинов CS в Steam ---------------- */
const _gshPwr = giftSheetHTML;
giftSheetHTML = function (o, mine) {
  let h = _gshPwr(o, mine);
  const g = o.g;
  if (mine && g.src === "cs" && g.price == null)
    h = h.replace('<div class="btns"><button class="btn gold" data-act="present"', `<div class="btns"><button class="btn cta" data-act="wd-open" data-id="${g.id}">${ic("send")}Вывести в Steam</button></div><div class="btns"><button class="btn gold" data-act="present"`);
  return h;
};
let WD = null, WD_G = null;
const usd = v => "$" + (Math.round(v * 100) / 100).toFixed(2);
function wdHTML() {
  const d = WD, g = WD_G, price = g ? g.value / d.rate : 0;
  const hist = d.items.length ? `<div class="sec-t">Заявки</div><div class="box">${d.items.map(x => `<div class="row"><div class="grow"><div class="t">${esc(x.col)}</div><div class="s">${esc(x.text)}</div></div><b class="tw">${usd(x.usd)}</b></div>`).join("")}</div>` : "";
  if (!d.on) return `<h2 class="gtitle">Вывод в Steam</h2><div class="box"><div class="hint" style="padding:14px">Вывод скинов пока не включён. Скин остаётся в сумке — его можно продать за полную ценность.</div></div>${hist}`;
  return `<h2 class="gtitle">Вывод в Steam</h2>
    ${g ? `<div class="box"><div class="row kv"><span class="k">Скин</span><span class="v">${esc(g.col)}</span></div><div class="row kv"><span class="k">Цена</span><span class="v">${usd(price)}</span></div>
      <div class="row kv"><span class="k">Доступно к выводу</span><span class="v">${usd(d.left)} из ${usd(d.limit)}</span></div></div>` : ""}
    <div class="sec-t">Трейд-ссылка Steam</div>
    <div class="box" style="padding:12px"><input id="wd-link" class="wd-inp" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="https://steamcommunity.com/tradeoffer/new/?partner=…&token=…" value="${esc(d.link)}">
      <div class="btns" style="margin-top:10px"><button class="btn ghost" data-act="wd-link">Сохранить ссылку</button></div></div>
    ${g ? `<div class="btns"><button class="btn cta" data-act="wd-go" data-id="${g.id}"${d.link && d.left + 1e-9 >= price ? "" : " disabled"}>Вывести ${usd(price)}</button></div>` : ""}
    <p class="hint">${!d.limit ? "Вывод открывается после первой покупки за Telegram Stars." : "Лимит вывода растёт с покупками за Telegram Stars."} Скин покупается на торговой площадке и приходит обменом в Steam; если обмен сорвётся, скин вернётся в сумку.</p>${hist}`;
}
function wdPaint() { const el = document.querySelector(".sheet.wdsheet"); if (el) { const b = el.querySelector(".wd-body"); if (b) b.innerHTML = wdHTML(); } }
Object.assign(ACT, {
  "wd-open": async el => {
    const sh = el.closest(".sheet"), o = sh && sh._o;
    WD_G = o ? o.g : null;
    WD = await api("withdraw");
    closeSheet();
    openSheet(`<div class="wd-body">${wdHTML()}</div>`, "wdsheet");
  },
  "wd-link": async () => {
    const v = (document.getElementById("wd-link") || {}).value || "";
    WD = await post("withdraw/link", { link: v.trim() }); H.ok(); toast("Ссылка сохранена", "ok"); wdPaint();
  },
  "wd-go": async el => {
    el.disabled = true;
    try { WD = await post("withdraw/" + el.dataset.id); WD_G = null; H.ok(); toast("Заявка принята — скин придёт обменом в Steam", "ok"); wdPaint(); if (TAB === "inv") renderInventory(); }
    catch (e) { el.disabled = false; }
  },
});

/* ---------------- «Угадай дроп» на тир-кейсах ---------------- */
GAMES.push({ id: "guess", t: "Угадай дроп", s: "Три подарка из кейса, один — настоящий дроп. Угадал — забираешь все три", img: "Crystal Ball", k: ["#22e9ff", "#0a1a3a"], chips: ["шанс 1 из 3", "приз ×3"] });
Object.assign(GAME_OPEN, { guess: () => openGuess() });
GAME_SECTIONS.find(s => s[0] === "Подарки")[2].push("guess");
GCAT.guess = "gifts";
let GS = null, GS_C = null, GS_BUSY = false;
async function openGuess() {
  openSheet(`${gameHead("Crystal Ball", "Угадай дроп", "Плати цену кейса и выбирай один из трёх подарков")}<div id="gs-body"><div class="hint" style="padding:18px;text-align:center">Загрузка…</div></div>`, "gs-s");
  GS = await api("guess"); GS_C = GS_C || (GS.cases[0] || {}).id; gsPaint();
}
function gsPaint(res) {
  const b = document.getElementById("gs-body"); if (!b) return;
  const cell = (g, i, cls, act) => `<button class="gs-c ${cls || ""}"${act ? ` data-act="gs-pick" data-i="${i}"` : " disabled"}>${giftHTML(g, { plain: true, lite: true })}<span class="cap">${esc(g.col)}<br><small>⭐ ${short(g.value || g.ev || 0)}</small></span></button>`;
  if (res) {
    b.innerHTML = `<div class="gs-res ${res.win ? "w" : "l"}">${res.win ? `Угадал! Все три подарка твои · ⭐ ${fmt(res.pay)}` : "Не угадал — выпал подарок с меткой"}</div>
      <div class="gs-row">${res.choices.map((g, i) => cell(g, i, (i === res.correct ? "ok " : "") + (i === res.pick ? "me" : ""))).join("")}</div>
      <div class="btns"><button class="btn cta" data-act="gs-again">Ещё раз</button></div>`;
    return;
  }
  const r = GS.round;
  if (r) {
    b.innerHTML = `<div class="gs-res">Какой подарок выпадет? Выбери один</div><div class="gs-row">${r.choices.map((g, i) => cell(g, i, "", true)).join("")}</div>
      <p class="hint">Каждый из трёх выпадает с шансом 1/3. Угадаешь — заберёшь все три подарка.</p>`;
    return;
  }
  const c = GS.cases.find(x => x.id === GS_C) || GS.cases[0];
  b.innerHTML = `<div class="sec-t">Кейс</div><div class="gs-cases">${GS.cases.map(x => `<button class="${x.id === (c && c.id) ? "on" : ""}" data-act="gs-case" data-id="${x.id}"><b>${esc(x.name)}</b><span>⭐ ${short(x.price)}</span></button>`).join("")}</div>
    <div class="btns"><button class="btn cta" data-act="gs-start"${c ? "" : " disabled"}>Играть за ⭐ ${c ? fmt(c.price) : 0}</button></div>
    <p class="hint">Из кейса выбираются три разных подарка с обычными шансами кейса, один из них — настоящий дроп. Угадал — забираешь все три, не угадал — ничего. Возврат такой же, как у обычного открытия этого кейса. Подарки продаются за полную ценность.</p>`;
}
Object.assign(ACT, {
  "gs-case": el => { GS_C = el.dataset.id; gsPaint(); },
  "gs-start": async el => {
    if (GS_BUSY) return; GS_BUSY = true;
    try { const r = await post("guess/start", { cid: GS_C }); setStars(r.stars); GS.round = r; H.imp("light"); gsPaint(); } finally { GS_BUSY = false; }
  },
  "gs-pick": async el => {
    if (GS_BUSY) return; GS_BUSY = true;
    try { const r = await post("guess/pick", { i: +el.dataset.i }); setStars(r.stars); GS.round = null; r.win ? H.ok() : H.imp("heavy"); gsPaint(r); } finally { GS_BUSY = false; }
  },
  "gs-again": () => gsPaint(),
});

/* ---------------- «Задания» — обычная вкладка, а не окно ---------------- */
TITLES.quests = "Задания";
TAB_RENDER.quests = () => { const v = $("#v-quests"); if (!v.querySelector("#q-body")) v.innerHTML = `<div id="q-body">${emptyHTML("hourglass", "Загружаем…")}</div>`; v._q = true; fillQuests(v); };
ACT.quests = () => setTab("quests");
const _qcPwr = ACT["q-claim"];
ACT["q-claim"] = async el => { await _qcPwr(el); if (TAB === "quests") fillQuests($("#v-quests")); };

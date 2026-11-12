// ============================================================ PWR: слияние с PWR SKINBOX и RubUp Web
// · вкладки витрины кейсов: Все / Подарки / CS / RubUp
// · боевой пропуск: ежедневные кейсы FREE / PWR / VIP с серией (7-й день — улучшенный)
// · задания SKINBOX в шторке «Задания»: подписка, друг, реклама
// Подключается последним: оборачивает renderCases / openCase / fillQuests, как это делают остальные модули.
let PWR = null;
let CTAB = (() => { try { return localStorage.getItem("np_ctab") || "all"; } catch (e) { return "all"; } })();
const CTABS = [["all", "Все"], ["tg", "Подарки"], ["cs", "CS"], ["ru", "RubUp"]];
const pwrLoad = async () => { try { PWR = await api("pwr"); } catch (e) {} return PWR; };
const pwrImg = (name, s = 256) => A.orig(name, s);

// ---------------- главная: баннер пропуска и вкладки витрины ----------------
function pwrBannerHTML() {
  const p = PWR && PWR.pass; if (!p) return "";
  const mine = p.tiers.filter(t => t.owned), ready = mine.filter(t => !t.done).length;
  const best = mine[mine.length - 1] || p.tiers[0], f = p.tiers[0];
  return `<button class="pp-banner${ready ? " ready" : ""}" data-act="pwr-pass" style="--pc:${best.color}">
    <span class="pp-b-art"><img src="${pwrImg(best.cover)}" alt=""></span>
    <span class="pp-b-t"><i>Battle Pass</i><b>Боевой пропуск</b>
      <small>${ready ? `${ready} ${plural(ready, ["кейс ждёт", "кейса ждут", "кейсов ждут"])} — забери` : `Новые кейсы через ${clock(p.resetIn)}`}</small>
      <span class="pp-days">${Array.from({ length: f.days }, (_, i) => `<i class="${i < (f.done ? f.day : f.day - 1) ? "on" : ""}${i === f.days - 1 ? " last" : ""}"></i>`).join("")}</span></span>
    <span class="pp-b-go">${ready ? "Открыть" : ic("chev")}</span></button>`;
}
function pwrPaint() {
  const v = $("#v-cases"), grid = v && v.querySelector(".cases"); if (!grid) return;
  const group = id => (CASES.find(c => c.id === id) || {}).group || "tg";
  if (!v.querySelector(".ctabs")) {
    const n = g => CASES.filter(c => c.id !== "free" && (g === "all" || c.group === g)).length;
    grid.insertAdjacentHTML("beforebegin", `<div class="ctabs">${CTABS.map(([k, t]) => `<button data-act="ctab" data-v="${k}" class="${CTAB === k ? "on" : ""}">${t}<em>${n(k)}</em></button>`).join("")}</div>`);
  }
  v.querySelectorAll(".ctabs button").forEach(b => b.classList.toggle("on", b.dataset.v === CTAB));
  let hidden = 0, next = 99;
  v.querySelectorAll(".case").forEach(c => {
    const g = group(c.dataset.id), hide = CTAB !== "all" && g !== CTAB;
    c.classList.toggle("pwr-hide", hide); c.dataset.g = g;
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

// у кейсов SKINBOX нет планки ценности — правим подпись под списком «Что внутри»
const _ocPwr = openCase;
openCase = function (id) {
  _ocPwr(id);
  const c = CASES.find(x => x.id === id), el = SHEETS[SHEETS.length - 1];
  if (!c || !el || !el._case || el._case.id !== id) return;
  el.classList.add("cs-" + (c.group || "tg"));
  if (c.price && c.floor === false) {
    const d = el.querySelector(".disc");
    if (d) d.textContent = d.textContent.replace(/Из платного кейса не выпадает[^.]*\.\s*/, "Чем дороже скин, тем он реже; возврат кейса — 90%. ");
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
  const cta = !t.owned ? `<button class="btn cta gold" data-act="pwr-buy" data-id="${t.id}">Купить · ⭐ ${fmt(t.price)} / ${t.days} дней</button>`
    : t.done ? `<button class="btn cta ghost" disabled>Открыт · новый через ${clock(p.resetIn)}</button>`
      : `<button class="btn cta gold" data-act="pwr-open" data-id="${t.id}">${t.improved ? "Открыть улучшенный кейс" : "Открыть кейс дня"}</button>`;
  return `<div class="pp-tier${t.owned ? " owned" : ""}${t.improved ? " imp" : ""}" style="--pc:${t.color}">
    <div class="pp-head"><span class="pp-art"><img src="${pwrImg(t.cover, 256)}" alt=""></span>
      <div class="grow"><div class="pp-name"><img src="${pwrImg(t.badge, 64)}" alt=""><b>${esc(t.title)}</b>${t.owned && t.until ? `<em>до ${new Date(t.until * 1000).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</em>` : t.owned ? "" : `<em class="lock">${ic("lock")}</em>`}</div>
        <div class="pp-sub">День ${t.day} из ${t.days}${t.improved ? " · улучшенный кейс" : ""}</div>
        <div class="pp-track">${days}</div></div></div>
    <div class="pp-ins">${inside}</div>
    <ul class="pp-ben">${t.benefits.map(b => `<li>${esc(b)}</li>`).join("")}</ul>
    ${cta}</div>`;
}
function pwrPassBody() {
  const p = PWR && PWR.pass;
  if (!p) return emptyHTML("hourglass", "Загружаем…");
  return `<div class="pp-lead">Каждый день — кейс. Семь дней подряд — улучшенный кейс с наградами лучше.</div>
    <div id="pp-won"></div>
    ${p.tiers.map(t => pwrTierHTML(t, p)).join("")}
    <div class="disc">Сутки считаются по UTC. Серия Free сгорает после пропущенного дня, серии PWR и VIP — нет. Скины CS здесь игровые: вывода в Steam нет. Шансы в кейсах пропуска: чем дороже приз, тем он реже.</div>`;
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
    if (ME.stars < t.price) { H.err(); return toast("Не хватает звёзд ⭐"); }
    el.disabled = true;
    try { const r = await post(`pwr/pass/${t.id}/buy`); PWR.pass = r.pass; setStars(r.stars); H.ok(); toast(`${t.title} активен на ${t.days} дней`, "ok"); burstAt(el); }
    catch (e) { el.disabled = false; return; }
    await pwrLoad(); pwrPassFill();
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
  return `<div class="sec-t">Задания PWR${t.k > 1 ? `<span class="pt-k">×${String(t.k).replace(".", ",")} с пропуском</span>` : ""}</div>
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

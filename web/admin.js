"use strict";
// ============================================================ админ-панель (кнопка видна только админу; сервер проверяет сам)
let ADM = { tab: "stats", qs: "", sort: "seen" };
const admDate = ts => ts ? new Date(ts * 1000).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
const admBytes = b => b >= 1e9 ? (b / 1e9).toFixed(1).replace(".", ",") + " ГБ" : Math.round(b / 1e6) + " МБ";
const admSgn = v => `<b class="${v >= 0 ? "tw" : "tl"}">${v >= 0 ? "+" : "−"}⭐ ${fmt(Math.abs(v))}</b>`;
const admKv = (k, v) => `<div class="row kv"><div class="grow"><div class="s">${k}</div></div>${v}</div>`;

// Режим секретности (без пароля): один серверный выключатель. Пока включён — вся админская разметка скрыта
// на устройстве, и бот НЕ шлёт этому админу служебные сообщения (тикеты, идеи, опросы, авто-отключения франшиз).
// Ничего не удаляется: admin_log/actlog пишутся, у других админов уведомления идут. Состояние — на сервере
// (ME.stealth), переживает перезапуск. 20 нажатий на «Кейсы» переключают режим.
const admShown = () => !!(ME && !ME.stealth);   // админка видна, когда режим секретности выключен
function admShow(on) {
  if (!on) { const b = $("#adm-btn"), f = $("#fps"); if (b) b.remove(); if (f) f.remove(); return; }
  if (!$("#adm-btn")) {
    const b = document.createElement("button");
    b.id = "adm-btn"; b.className = "adm-btn"; b.dataset.act = "adm"; b.innerHTML = ic("lock");
    $("#me-btn").before(b);
  }
  fpsMeter();
}
async function admToggleSecret() {
  const on = !ME.stealth;
  let r; try { r = await post("admin/stealth", { on }); } catch (e) { return; }
  if (!r || !r.ok) return;
  ME.stealth = r.on;
  admShow(!ME.stealth);
  H.imp("heavy"); toast(ME.stealth ? "Режим секретности включён — админка скрыта, уведомления отключены" : "Режим секретности выключен", "ok");
}
(function admButton() {
  const t = setInterval(() => { if (ME) { clearInterval(t); if (ME.admin && !ME.stealth) admShow(true); } }, 500);
  let n = 0, last = 0;
  document.addEventListener("click", e => {
    if (!ME || !ME.admin || !e.target.closest || !e.target.closest('[data-tab="cases"]')) return;
    const now = Date.now(); n = now - last < 1200 ? n + 1 : 1; last = now;
    if (n < 20) return;
    n = 0;
    admToggleSecret();
  }, true);
})();

// счётчик FPS — только для админов: средний FPS и самый долгий кадр за 0,5 с (рывки). Тап — спрятать до перезапуска.
function fpsMeter() {
  if ($("#fps")) return;
  const el = document.createElement("div"); el.id = "fps"; document.body.appendChild(el);
  el.onclick = () => el.remove();
  let n = 0, t0 = performance.now(), prev = t0, worst = 0;
  (function f(now) {
    if (!el.isConnected) return;
    n++; worst = Math.max(worst, now - prev); prev = now;
    if (now - t0 >= 500) {
      const fps = Math.round(n * 1000 / (now - t0));
      el.textContent = `${fps} fps · ${Math.round(worst)} мс`;
      el.className = fps >= 100 ? "hi" : fps >= 55 ? "" : "lo";
      n = 0; t0 = now; worst = 0;
    }
    requestAnimationFrame(f);
  })(t0);
}

async function admDbImport(f) {
  const mb = (f.size / 1048576).toFixed(1);
  if (!/\.(db|gz)$/i.test(f.name)) return toast("Нужен файл .db или .db.gz");
  if (!await confirmM("Заменить базу?", `Файл «${esc(f.name)}» (${mb} МБ) заменит ВСЮ текущую базу: игроков, балансы, подарки. Текущая сохранится в backups/ на сервере.`, "Дальше")) return;
  if (!await confirmM("Точно?", "Всё, что игроки сделали после этой копии, пропадёт. Игра перезапустится.", "Да, импортировать")) return;
  toast(`Загружаю ${mb} МБ…`);
  const headers = { "Content-Type": "application/octet-stream" };
  if (inTg) headers["X-Init-Data"] = tg.initData; else if (DEV_USER) headers["X-Dev-User"] = DEV_USER;
  let r, d = null;
  try { r = await fetch("api/admin/db/import", { method: "POST", headers, body: f }); d = await r.json().catch(() => null); }
  catch (e) { return toast("Нет связи с сервером", "err"); }
  if (!r.ok) { H.err(); return toast(d && d.detail || (r.status === 413 ? "Файл слишком большой" : "Ошибка импорта"), "err"); }
  H.ok(); toast(`Импортировано: ${fmt(d.users)} игроков. Перезапуск…`, "ok");
  setTimeout(() => location.reload(), 8000);   // сервис поднимается за ~5–7 с
}
function openAdmin() {
  if (admShown()) fpsMeter();   // открыл админку — счётчик снова виден
  const el = openSheet(`<h2 class="gtitle">Админка</h2>
    <div class="seg adm-tabs" id="adm-seg">${[["stats", "Обзор"], ["sales", "Продажи"], ["users", "Игроки"], ["comp", "Компенсации"], ["games", "Игры"], ["cnames", "Кейсы"], ["odds", "Шансы"], ["claw", "Кран"], ["tickets", `Тикеты${ME.tickets && ME.tickets.open ? ` · ${ME.tickets.open}` : ""}`], ["fees", "Комиссии"], ["wipe", "Вайп"], ["polls", "Опросы"], ["pay", "Переводы"], ["bc", "Рассылка"], ["ev", "Ивенты"], ["ref", "Рефералы"], ["fr", "Боты"], ["db", "База"], ["log", "Журнал"]]
      .map(([k, t]) => `<button data-act="adm-tab" data-v="${k}" class="${ADM.tab === k ? "on" : ""}">${t}</button>`).join("")}</div>
    <div id="adm-body">${emptyHTML("hourglass", "Загружаем…")}</div>`);
  el._adm = true;
  admRender(el);
}

async function admRender(el = topSheet()) {
  const body = el.querySelector("#adm-body"); if (!body) return;
  if (ADM.tab === "stats") {
    const [s, pr, ev, adm, pl] = await Promise.all([api("admin/stats"), api("admin/promo"), api("admin/event"), api("admin/admins"), api("admin/pulse").catch(() => null)]), v = s.server;
    const kinds = Object.entries(s.kinds24).sort((a, b) => b[1].n - a[1].n);
    body.innerHTML = `${pl ? admPulseHTML(pl) : ""}
      <div class="sec-t">Акция «Щедрые выходные» ${pr.active ? `<span class="tw">· идёт</span>` : ""}</div>
      <div class="seg">${[["auto", "Авто (сб–вс)"], ["on", "Включить"], ["off", "Выключить"]].map(([k, t]) => `<button data-act="adm-promo" data-v="${k}" class="${pr.mode === k ? "on" : ""}">${t}</button>`).join("")}</div>
      <div class="sec-t">Сезонный ивент ${ev.active ? `<span class="tw">· ${esc(ev.active.title)} идёт</span>` : ""}</div>
      <div class="seg">${[["auto", "Авто (по датам)"], ...ev.events.map(e => [e.id, "Вкл: " + e.title]), ["off", "Выключить"]].map(([k, t]) => `<button data-act="adm-event" data-v="${k}" class="${ev.mode === k ? "on" : ""}">${esc(t)}</button>`).join("")}</div>
      <div class="box">${admKv("Игроков всего", `<b>${fmt(s.users)}</b>`)}${admKv("Онлайн (5 мин)", `<b>${fmt(s.online)}</b>`)}
        ${admKv("Активных за 24 ч / 7 дн", `<b>${fmt(s.active24)} / ${fmt(s.active7)}</b>`)}${admKv("Новых за 24 ч", `<b>${fmt(s.new24)}</b>`)}
        ${admKv("Заблокировано", `<b>${fmt(s.banned)}</b>`)}</div>
      <div class="sec-t">Экономика</div>
      <div class="box">${admKv("Банк игры", `<b>⭐ ${fmt(s.bank)}</b>`)}${admKv("Прибыль банка 24 ч", admSgn(s.house24))}
        ${admKv("Прибыль банка 7 дн", admSgn(s.house7))}${admKv("Комиссии в банк 24 ч", `<b class="tw">+⭐ ${fmt(s.fees24)}</b>`)}
        ${admKv("Звёзд у игроков", `<b>⭐ ${fmt(s.stars)}</b>`)}${admKv("Подарков у игроков", `<b>${fmt(s.gifts)}</b>`)}</div>
      <div class="sec-t">Сервер</div>
      <div class="box">${admKv("Нагрузка (1/5/15 мин)", `<b>${v.load.map(x => x.toFixed(2)).join(" / ")} · ${v.cpus} CPU</b>`)}
        ${admKv("Память свободно", `<b>${admBytes(v.memAvail)} из ${admBytes(v.memTotal)}</b>`)}
        ${admKv("Swap занято", `<b>${admBytes(v.swapTotal - v.swapFree)} из ${admBytes(v.swapTotal)}</b>`)}
        ${admKv("Диск свободно", `<b>${admBytes(v.diskFree)} из ${admBytes(v.diskTotal)}</b>`)}
        ${admKv("Игра в памяти / база", `<b>${admBytes(v.rss)} / ${admBytes(v.db)}</b>`)}
        ${admKv("Без перезапуска", `<b>${clock(v.uptime)}</b>`)}</div>
      <div class="sec-t">Администраторы</div>
      <div class="box">${adm.list.map(u => `<div class="row tap" data-act="adm-user" data-id="${u.id}">${avaHTML(u, 34)}<div class="grow"><div class="t">${esc(u.name)}</div>
        <div class="s">${u.owner ? "владелец" : "админ"} · id ${u.id}</div></div>${ic("chev")}</div>`).join("")}</div>
      ${adm.canGrant ? `<div class="hint" style="font-size:12px;margin:6px 4px 0">Выдать админку: вкладка «Игроки» → игрок → «Сделать админом»</div>` : ""}
      <div class="sec-t">Операции за 24 ч</div>
      <div class="box">${kinds.map(([k, x]) => admKv(`${esc(k)} · ${fmt(x.n)}`, admSgn(x.sum))).join("") || `<div class="hint" style="padding:14px">Пусто</div>`}</div>`;
  } else if (ADM.tab === "sales") {
    const s = await api("admin/sales");
    const card = (t, x) => `<div><span>${t}</span><b>${fmt(x.xtr)} <i class="adm-tg">${ic("tgplane")}</i></b><small>${x.n} покупок · ${x.buyers} чел.</small></div>`;
    const mx = Math.max(1, ...s.days.map(d => d.xtr));
    const sw = (k, t, d) => `<div class="row kv"><div class="grow"><div class="t">${t}</div><div class="s" style="white-space:normal">${d}</div></div>
        ${s.canEdit ? `<button class="sw${s.sale[k] ? " on" : ""}" data-act="adm-shop" data-k="${k}" data-v="${s.sale[k] ? 0 : 1}"></button>` : `<b>${s.sale[k] ? "вкл" : "выкл"}</b>`}</div>`;
    body.innerHTML = `<div class="sec-t">Что продаётся за Telegram Stars</div><div class="box">
        ${sw("shop", "Игровые звёзды", "Пакеты, своя сумма, «Набор дня», подарок звёзд другу")}
        ${sw("vip", "VIP", "Бонус дня ×2, кейс чаще, комиссия маркета −50%, рамка")}
        ${sw("chest", "Звёздный сундук", "Дорогой подарок за Stars — его можно продать за игровые звёзды")}</div>
      <div class="adm-sales">${card("Сегодня", s.today)}${card("7 дней", s.week)}${card("Всего", s.all)}</div>
      <div class="sec-t">${ic("trend")}По дням (14 дней), Telegram Stars</div>
      <div class="adm-bars">${s.days.length ? s.days.map(d => `<div title="${d.xtr}"><i style="height:${Math.max(4, d.xtr / mx * 100)}%"></i><span>${new Date(d.day * 1000).getDate()}</span></div>`).join("") : `<div class="hint" style="padding:14px">Покупок пока нет</div>`}</div>
      <div class="sec-t">${ic("crown")}Топ покупателей</div>
      <div class="box">${s.top.map(u => `<div class="row tap" data-act="adm-user" data-id="${u.id}">${avaHTML(u, 32)}<div class="grow"><div class="t">${esc(u.name)}</div><div class="s">${u.n} покупок</div></div><b>${fmt(u.xtr)} <i class="adm-tg">${ic("tgplane")}</i></b></div>`).join("") || `<div class="hint" style="padding:14px">Пусто</div>`}</div>
      <div class="sec-t">${ic("clock")}Последние покупки</div>
      <div class="box">${s.last.map(p => `<div class="row kv"><div class="grow"><div class="t">${esc(p.user.name)}</div><div class="s">+⭐ ${fmt(p.stars)} · ${admDate(p.ts)}</div></div><b>${p.xtr} <i class="adm-tg">${ic("tgplane")}</i></b></div>`).join("") || `<div class="hint" style="padding:14px">Пусто</div>`}</div>
      <div class="disc">Telegram Stars копятся на балансе бота — смотреть и выводить в @BotFather → бот → Payments / Stars.</div>`;
    starify(body);
  } else if (ADM.tab === "users") {
    const [r, fz] = await Promise.all([api(`admin/users?sort=${ADM.sort}&qs=${encodeURIComponent(ADM.qs)}`), api("admin/frozen").catch(() => ({ list: [] }))]);
    body.innerHTML = `<input id="adm-q" placeholder="Имя, @ник или id" value="${esc(ADM.qs)}" style="margin-bottom:10px">
      ${fz.list.length && !ADM.qs ? `<div class="sec-t">${ic("lock")}Заморожены · ${fz.list.length}</div><div class="box">${fz.list.map(u => `<div class="row tap" data-act="adm-user" data-id="${u.id}">${avaHTML(u, 32)}
        <div class="grow"><div class="t">${esc(u.name)}</div><div class="s">с ${admDate(u.ts)}${u.reason ? " · " + esc(u.reason) : ""}</div></div>${ic("chev")}</div>`).join("")}</div>` : ""}
      <div class="seg">${[["seen", "Недавние"], ["rich", "Богатые"], ["new", "Новые"]].map(([k, t]) => `<button data-act="adm-sort" data-v="${k}" class="${ADM.sort === k ? "on" : ""}">${t}</button>`).join("")}</div>
      <div class="box">${r.users.map(u => `<div class="row tap" data-act="adm-user" data-id="${u.id}">${avaHTML(u, 36)}
        <div class="grow"><div class="t">${esc(u.name)}${u.banned ? ` <span class="tl">· бан</span>` : ""}</div><div class="s">${u.username ? "@" + esc(u.username) + " · " : ""}${u.id} · ${admDate(u.seen)}</div></div>
        <b>⭐ ${short(u.stars)}</b></div>`).join("") || `<div class="hint" style="padding:14px">Никого не нашли</div>`}</div>`;
    const i = body.querySelector("#adm-q"); let t;
    i.oninput = () => { clearTimeout(t); t = setTimeout(() => { ADM.qs = i.value; admRender(el).then(() => { const n = el.querySelector("#adm-q"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }); }, 400); };
  } else if (ADM.tab === "comp") {   // массовые компенсации (sanctions.py)
    await admComp(body);
  } else if (ADM.tab === "odds") {
    const d = await api("admin/odds"), pc = v => +(v * 100).toFixed(2);
    body.innerHTML = `<p class="hint" style="margin:0 0 10px;font-size:12.5px">Возврат игроку на дистанции: 96% — из каждых ⭐ 100 ставок игрокам возвращается ⭐ 96, банк оставляет 4%. Меньше 100% — банк в плюсе, больше 100% — игроки в плюсе. Действует сразу. Можно ${pc(d.lo)}–${pc(d.hi)}%.</p>
      ${d.promo ? `<div class="adm-warn"><b>Идёт акция «Щедрые выходные».</b> Пока она идёт, часть игр отдаёт не меньше 98% (апгрейд 93%, скретч 96%), значения ниже не действуют. Выключить — вкладка «Обзор».</div>` : ""}
      ${d.canEdit ? (() => { const vs = d.list.map(g => g.value), same = vs.every(v => v === vs[0]), a = pc(same ? vs[0] : vs.reduce((x, y) => x + y, 0) / vs.length); return `<div class="box adm-odd adm-odd-all">
        <div class="adm-oh"><b>Все игры сразу</b><span class="adm-tag">${same ? "у всех одинаково" : "сейчас разные"}</span></div>
        <div class="adm-os">Ставит один возврат для всех игр ниже. ${same ? "" : `Сейчас в среднем ${a}%.`}</div>
        <input type="range" class="drange" id="adm-oall" min="${pc(d.lo)}" max="${pc(d.hi)}" step="0.5" value="${a}">
        <div class="adm-oc"><input class="adm-oi" inputmode="decimal" id="adm-oall-n" value="${a}"><span class="adm-op">%</span>
          <button class="btn sm gold" data-act="adm-odds-all">${ic("check")}Всем играм</button>
          <button class="btn sm ghost" data-act="adm-odds-all-rs">${ic("refresh")}</button></div></div>`; })() : ""}
      <div class="box">${d.list.map(g => `<div class="adm-odd${g.value > 1 ? " plus" : ""}">
        <div class="adm-oh"><b>${esc(g.title)}</b>${g.value > 1 ? `<span class="adm-tag red">игроки в плюсе</span>` : g.changed ? `<span class="adm-tag">изменено</span>` : ""}</div>
        <div class="adm-os">по умолчанию ${pc(g.default)}% · банк за 7 дн: <span class="${g.house7 >= 0 ? "tw" : "tl"}">${g.house7 >= 0 ? "+" : "−"}⭐ ${short(Math.abs(g.house7))}</span> · ${fmt(g.rounds7)} игр${g.max && g.max !== d.hi ? ` · можно до ${pc(g.max)}%` : ""}</div>
        ${g.effective !== g.value ? `<div class="adm-os tl">сейчас действует ${pc(g.effective)}% — из-за акции</div>` : ""}
        ${d.canEdit ? `<div class="adm-oc"><input class="adm-oi" inputmode="decimal" data-k="${g.key}" value="${pc(g.value)}"><span class="adm-op">%</span>
          <button class="btn sm gold" data-act="adm-odds" data-k="${g.key}">${ic("check")}Сохранить</button>
          ${g.changed ? `<button class="btn sm ghost" data-act="adm-odds-rs" data-k="${g.key}" data-n="${esc(g.title)}">${ic("refresh")}</button>` : ""}</div>` : `<div class="adm-oc"><b>${pc(g.value)}%</b></div>`}</div>`).join("")}</div>
      ${d.canEdit ? "" : `<div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Менять шансы может только владелец</div>`}
      <div class="disc">Прибыль банка за 7 дней сильно зависит от удачи: один крупный выигрыш может перекрыть день. Рулетка (97,3%), блэкджек и кейсы здесь не настраиваются: кейсы — в settings.toml.</div>`;
    starify(body);
    const rg = body.querySelector("#adm-oall"), nb = body.querySelector("#adm-oall-n");
    if (rg) { rg.oninput = () => { nb.value = rg.value; }; nb.oninput = () => { const v = parseFloat(nb.value.replace(",", ".")); if (v > 0) rg.value = v; }; }
  } else if (ADM.tab === "cnames") {   // названия и обложки кейсов (admin.py → /admin/cases)
    const d = await api("admin/cases"), whoT = { all: "всем", only: "только этим id", except: "всем, кроме этих id" };
    const whoSel = (cls, cur) => `<select class="adm-sel ${cls}" data-k="who">${Object.entries(whoT).map(([k, t]) => `<option value="${k}"${cur === k ? " selected" : ""}>${t}</option>`).join("")}</select>`;
    body.innerHTML = `<p class="hint" style="margin:0 0 10px;font-size:12.5px">Новое название или обложку видят игроки, которых выберешь; остальные видят оригинал. Пустое название или «Оригинал» — вернуть как было. Действует сразу.</p>
      <div class="box">${d.list.map(c => `<div class="adm-odd" data-cid="${esc(c.id)}">
        <div class="adm-oh"><img src="${A.orig(c.ncover || c.cover, 64)}" alt="" style="width:36px;height:36px;margin-right:8px;flex:none" class="adm-cvp"><b>${esc(c.real)}</b>${c.title ? `<span class="adm-tag">→ ${esc(c.title)} · ${whoT[c.who]}${c.who !== "all" ? ` (${c.ids.length})` : ""}</span>` : ""}</div>
        <div class="adm-os">${esc(c.id)} · ур. ${c.level}${c.price ? ` · ⭐ ${fmt(c.price)}` : " · бесплатный"}${c.ncover ? ` · обложка: ${c.ncover.startsWith("~") ? "своя картинка" : esc(c.ncover)} · ${whoT[c.cwho]}${c.cwho !== "all" ? ` (${c.cids.length})` : ""}` : ""}</div>
        <div class="adm-os"><b>Название</b></div>
        <div class="adm-oc"><input class="adm-oi adm-cn" style="width:46%" maxlength="40" placeholder="Новое название" data-k="title" value="${esc(c.title)}">${whoSel("adm-cn", c.who)}</div>
        <div class="adm-oc"><input class="adm-oi adm-cn" style="width:100%" data-k="ids" placeholder="id игроков через запятую (для «только» и «кроме»)" value="${esc(c.ids.join(", "))}"></div>
        <div class="adm-oc"><button class="btn sm gold" data-act="adm-cname" data-cid="${esc(c.id)}">${ic("check")}Сохранить название</button>
          ${c.title ? `<button class="btn sm ghost" data-act="adm-cname-rs" data-cid="${esc(c.id)}">${ic("refresh")}Настоящее</button>` : ""}</div>
        <div class="adm-os"><b>Обложка</b></div>
        <div class="adm-oc"><select class="adm-sel adm-cc" data-k="cover" style="width:46%"><option value="">Оригинал (${esc(c.cover)})</option>${c.ncover && c.ncover.startsWith("~") ? `<option value="${esc(c.ncover)}" selected>Своя картинка</option>` : ""}${d.cols.map(x => `<option value="${esc(x)}"${c.ncover === x ? " selected" : ""}>${esc(x)}</option>`).join("")}</select>
          <label class="btn sm ghost">${ic("upload")}Файл<input type="file" accept="image/*" class="adm-cc-file" hidden></label>${whoSel("adm-cc", c.cwho)}</div>
        <div class="adm-oc"><input class="adm-oi adm-cc" style="width:100%" data-k="ids" placeholder="id игроков через запятую (для «только» и «кроме»)" value="${esc(c.cids.join(", "))}"></div>
        <div class="adm-oc"><button class="btn sm gold" data-act="adm-ccover" data-cid="${esc(c.id)}">${ic("check")}Сохранить обложку</button>
          ${c.ncover ? `<button class="btn sm ghost" data-act="adm-ccover-rs" data-cid="${esc(c.id)}">${ic("refresh")}Оригинал</button>` : ""}</div></div>`).join("")}</div>`;
    starify(body);
    ADM_CIMG = {};
    body.querySelectorAll(".adm-cc-file").forEach(inp => inp.onchange = async e => {
      const f = e.target.files[0]; e.target.value = ""; if (!f) return;
      const row = inp.closest(".adm-odd"), url = await admCoverData(f).catch(() => null);
      if (!url) return toast("Не удалось прочитать картинку");
      ADM_CIMG[row.dataset.cid] = url; row.querySelector(".adm-cvp").src = url; toast("Картинка выбрана — нажми «Сохранить обложку»", "ok");
    });
  } else if (ADM.tab === "pay") {
    const d = await api("admin/pay"), c = d.cfg, ed = d.canEdit, w = d.week;
    const pair = x => `<div class="row tap" data-act="adm-user" data-id="${x.a.id}">${avaHTML(x.a, 28)}<span class="adm-arr">${ic("chev")}</span>${avaHTML(x.b, 28)}
      <div class="grow" style="min-width:0"><div class="t">${esc(x.a.name)} → ${esc(x.b.name)}</div><div class="s">${x.n != null ? fmt(x.n) + " переводов за 7 дн" : admDate(x.ts) + (x.note ? " · «" + esc(x.note) + "»" : "")}</div></div>
      <b>⭐ ${short(x.sum != null ? x.sum : x.amount)}</b></div>`;
    const field = (k, title, hint, val, unit) => `<div class="adm-odd"><div class="adm-oh"><b>${title}</b>${d.changed.includes(k) ? `<span class="adm-tag">изменено</span>` : ""}</div>
      <div class="adm-os">${hint}</div>
      ${ed ? `<div class="adm-oc"><input class="adm-oi" inputmode="decimal" data-k="${k}" value="${val}"><span class="adm-op">${unit}</span>
        <button class="btn sm gold" data-act="adm-pay" data-k="${k}">${ic("check")}Сохранить</button>
        ${d.changed.includes(k) ? `<button class="btn sm ghost" data-act="adm-pay-rs" data-k="${k}">${ic("refresh")}</button>` : ""}</div>` : `<div class="adm-oc"><b>${val} ${unit}</b></div>`}</div>`;
    body.innerHTML = `<div class="box">
        <div class="row kv"><div class="grow"><div class="t">Переводы включены</div><div class="s" style="white-space:normal">Если выключить, кнопка «Перевести» у игроков перестанет работать</div></div>
          ${ed ? `<button class="sw${c.on ? " on" : ""}" data-act="adm-pay-on" data-v="${c.on ? 0 : 1}"></button>` : `<b>${c.on ? "да" : "нет"}</b>`}</div>
        <div class="row kv"><div class="grow"><div class="t">Инлайн-чеки (@бот в чате)</div><div class="s" style="white-space:normal">Игрок пишет «@бот сумма» в любом чате и отправляет чек — заберёт первый, кто откроет. Комиссия и лимиты — как у переводов</div></div>
          ${ed ? `<button class="sw${c.inline_on ? " on" : ""}" data-act="adm-pay-inline" data-v="${c.inline_on ? 0 : 1}"></button>` : `<b>${c.inline_on ? "да" : "нет"}</b>`}</div>
        ${field("fee", "Комиссия обычного перевода", `по QR, поиску и id · платит отправитель сверху суммы, уходит в банк · по умолчанию ${+(d.defaults.fee * 100).toFixed(2)}%`, +(c.fee * 100).toFixed(2), "%")}
        ${field("fee_addr", "Комиссия перевода по адресу", `когда переводят по адресу кошелька NP… · по умолчанию такая же, как обычная`, +(c.fee_addr * 100).toFixed(2), "%")}
        ${field("min", "Минимальный перевод", `по умолчанию ⭐ ${fmt(d.defaults.min)}`, c.min, "⭐")}
        ${field("max", "Максимум за один перевод", `0 — без ограничения · по умолчанию ${d.defaults.max ? "⭐ " + fmt(d.defaults.max) : "0"}`, c.max, "⭐")}
        ${field("day", "Переводов в сутки с аккаунта", `по умолчанию ${d.defaults.day}`, c.day, "шт")}
        ${field("inline_ttl_h", "Срок жизни инлайн-чека", `через сколько часов невостребованный чек вернётся отправителю · по умолчанию ${d.defaults.inline_ttl_h}`, c.inline_ttl_h, "ч")}</div>
      ${ed ? "" : `<div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Менять настройки может только владелец</div>`}
      <div class="sec-t">За 7 дней</div>
      <div class="box">${admKv("Переводов", `<b>${fmt(w.n)}</b>`)}${admKv("Переведено", `<b>⭐ ${fmt(w.sum)}</b>`)}${admKv("Комиссия в банк", `<b class="tw">⭐ ${fmt(w.fee)}</b>`)}${admKv("Отправителей", `<b>${fmt(w.users)}</b>`)}</div>
      <div class="sec-t">Крупнейшие пары за 7 дней</div>
      <div class="box">${d.top.map(pair).join("") || `<div class="hint" style="padding:14px">Пусто</div>`}</div>
      <div class="sec-t">Последние переводы</div>
      <div class="box">${d.recent.map(pair).join("") || `<div class="hint" style="padding:14px">Переводов пока не было</div>`}</div>
      <div class="disc">Если двое постоянно перекидывают звёзды только друг другу — это может быть один человек с двух аккаунтов. Нажми на пару, чтобы открыть карточку отправителя.</div>`;
    starify(body);
  } else if (ADM.tab === "polls") {   // опросы (polls.js / polls.py)
    await admPolls(body);
  } else if (ADM.tab === "wipe") {   // сезоны-вайпы (wipe.js / wipe.py)
    await admWipe(body);
  } else if (ADM.tab === "tickets") {   // тикеты поддержки (tickets.js / tickets.py)
    await admTickets(body);
  } else if (ADM.tab === "fees") {   // все комиссии и налоги (fees.py)
    const d = await api("admin/fees"), ed = d.canEdit, P = v => String(+(v * 100).toFixed(3)).replace(".", ",");
    const groups = [...new Set(d.items.map(i => i.group))];
    body.innerHTML = `<div class="box">${admKv("Комиссий за 24 ч", `<b>⭐ ${fmt(d.fees24)}</b>`)}</div>
      ${groups.map(g => `<div class="sec-t">${esc(g)}</div><div class="box">${d.items.filter(i => i.group === g).map(i => `<div class="adm-odd">
        <div class="adm-oh"><b>${esc(i.title)}</b>${i.changed ? `<span class="adm-tag">изменено</span>` : ""}</div>
        <div class="adm-os">${i.hint ? esc(i.hint) + " · " : ""}по умолчанию ${P(i.def)}% · ${i.min ? `от ${P(i.min)}% ` : ""}до ${P(i.max)}%</div>
        ${ed ? `<div class="adm-oc"><input class="adm-oi" inputmode="decimal" data-k="${i.k}" value="${P(i.v)}"><span class="adm-op">%</span>
          <button class="btn sm gold" data-act="adm-fee" data-k="${i.k}">${ic("check")}</button>
          ${i.changed ? `<button class="btn sm ghost" data-act="adm-fee-rs" data-k="${i.k}">${ic("refresh")}</button>` : ""}</div>` : `<div class="adm-oc"><b>${P(i.v)}%</b></div>`}</div>`).join("")}</div>`).join("")}
      <div class="disc">Меняется сразу, без перезапуска. Комиссии и налоги — главный доход казино и база для 0,5% владельцам ботов: если сильно снизить, банк перестанет пополняться. Преимущество казино в играх (RTP) — во вкладке «Шансы».</div>`;
    starify(body);
  } else if (ADM.tab === "ev") {   // ивенты раз в ~2 часа (flash.py)
    const d = await api("admin/flash"), c = d.cfg, ed = d.canEdit, now = Math.floor(Date.now() / 1000);
    const sw = (k, title, hint) => `<div class="row kv"><div class="grow"><div class="t">${title}</div><div class="s" style="white-space:normal">${hint}</div></div>
      ${ed ? `<button class="sw${c[k] ? " on" : ""}" data-act="adm-ev-sw" data-k="${k}" data-v="${c[k] ? 0 : 1}"></button>` : `<b>${c[k] ? "да" : "нет"}</b>`}</div>`;
    const field = (k, title, hint, unit) => `<div class="adm-odd"><div class="adm-oh"><b>${title}</b>${d.changed.includes(k) ? `<span class="adm-tag">изменено</span>` : ""}</div>
      <div class="adm-os">${hint}${hint ? " · " : ""}по умолчанию ${fmt(d.defaults[k])}</div>
      ${ed ? `<div class="adm-oc"><input class="adm-oi" inputmode="numeric" data-k="${k}" value="${c[k]}"><span class="adm-op">${unit}</span>
        <button class="btn sm gold" data-act="adm-ev" data-k="${k}">${ic("check")}</button>
        ${d.changed.includes(k) ? `<button class="btn sm ghost" data-act="adm-ev-rs" data-k="${k}">${ic("refresh")}</button>` : ""}</div>` : `<div class="adm-oc"><b>${fmt(c[k])} ${unit}</b></div>`}</div>`;
    const cur = d.current;
    body.innerHTML = `<div class="box">${cur ? admKv("Сейчас идёт", `<b>${esc(d.kinds[cur.kind])}</b> · ещё ${Math.max(0, Math.ceil((cur.end - now) / 60))} мин`)
        : admKv("Следующий ивент", d.next ? `<b>через ${Math.max(0, Math.ceil((d.next - now) / 60))} мин</b>` : "—")}</div>
      ${ed ? `<div class="btns" style="flex-wrap:wrap">${cur ? `<button class="btn ghost" data-act="adm-ev-stop">${ic("x")}Остановить</button>`
        : Object.entries(d.kinds).map(([k, t]) => `<button class="btn sm ghost" data-act="adm-ev-go" data-k="${k}">${esc(t)} сейчас</button>`).join("")}</div>` : ""}
      <div class="sec-t">Настройки</div>
      <div class="box">
        ${sw("on", "Ивенты включены", "Автоматически примерно раз в N минут")}
        ${field("every_min", "Как часто", "", "мин")}
        ${field("jitter_min", "Случайный сдвиг ±", "чтобы не угадывали время", "мин")}
        ${field("dur_min", "Длительность", "", "мин")}
        ${field("w_luck3", "Вес «Удача ×3»", "чаще выпадает тот, у кого вес больше; 0 — не выпадает", "")}
        ${field("w_luck5", "Вес «Удача ×5»", "", "")}
        ${field("w_drop", "Вес «Раздача»", "", "")}
        ${field("drop_amount", "Раздача: сколько звёзд", "каждому, кто успел", "⭐")}
        ${field("drop_max", "Раздача: сколько игроков успеют", "", "чел")}
        ${field("drop_level", "Раздача: с какого уровня", "и сыграл хотя бы раунд за сутки — против твинков", "ур.")}
        ${sw("notify", "Бот пишет о начале", "Игрокам с включёнными уведомлениями, кто заходил за 3 дня")}
        ${field("notify_gap_h", "Писать одному игроку не чаще", "иначе бота начнут блокировать", "ч")}
      </div>
      <div class="sec-t">Последние ивенты</div>
      <div class="box">${d.history.map(h => `<div class="row kv"><div class="grow"><div class="t">${esc(h.title)}${h.manual ? " · вручную" : ""}</div>
        <div class="s">${admDate(h.start)} · ${h.kind === "drop" ? `забрали ${h.claims}` : `удачных моментов ${h.lucky}`}</div></div><b>⭐ ${fmt(h.paid)}</b></div>`).join("") || `<div class="hint" style="padding:14px">Ещё не было</div>`}</div>
      <div class="disc">«Удача ×N» умножает шанс «удачного момента» (сюрприз до 2 500 ⭐ после раунда) и даёт поймать его ещё раз за ивент. Выигрыши в играх не меняются — иначе ивент стал бы «станком».</div>`;
    starify(body);
  } else if (ADM.tab === "ref") {   // реферальная программа (refs.py)
    const [d, gw] = await Promise.all([api("admin/refs"), api("admin/gw").catch(() => null)]), c = d.cfg, ed = d.canEdit, s = d.stats, p = s.paid7;
    const sw = (k, title, hint) => `<div class="row kv"><div class="grow"><div class="t">${title}</div><div class="s" style="white-space:normal">${hint}</div></div>
      ${ed ? `<button class="sw${c[k] ? " on" : ""}" data-act="adm-ref-sw" data-k="${k}" data-v="${c[k] ? 0 : 1}"></button>` : `<b>${c[k] ? "да" : "нет"}</b>`}</div>`;
    const field = (k, title, hint, unit, text) => `<div class="adm-odd"><div class="adm-oh"><b>${title}</b>${d.changed.includes(k) ? `<span class="adm-tag">изменено</span>` : ""}</div>
      <div class="adm-os">${hint} · по умолчанию ${text ? esc(d.defaults[k]) : fmt(d.defaults[k])}</div>
      ${ed ? `<div class="adm-oc"><input class="adm-oi"${text ? ` style="flex:1"` : ` inputmode="numeric"`} data-k="${k}" value="${esc(String(c[k]))}">${unit ? `<span class="adm-op">${unit}</span>` : ""}
        <button class="btn sm gold" data-act="adm-ref" data-k="${k}">${ic("check")}</button>
        ${d.changed.includes(k) ? `<button class="btn sm ghost" data-act="adm-ref-rs" data-k="${k}">${ic("refresh")}</button>` : ""}</div>` : `<div class="adm-oc"><b>${esc(String(c[k]))} ${unit}</b></div>`}</div>`;
    const sum = Object.values(p).reduce((a, b) => a + b, 0);
    body.innerHTML = `<div class="sec-t">За 7 дней</div>
      <div class="box">${admKv("Пришли по ссылкам", `<b>${fmt(s.new7)}</b>`)}${admKv("Всего по ссылкам", `<b>${fmt(s.all)}</b> из ${fmt(s.users)} (${Math.round(s.all / Math.max(1, s.users) * 100)}%)`)}
        ${admKv(`Активных (${c.l1_level}+ ур.)`, `<b>${fmt(s.active)}</b> (${Math.round(s.active / Math.max(1, s.all) * 100)}% приглашённых)`)}
        ${admKv("Выплачено за 7 дн", `<b>⭐ ${fmt(sum)}</b>`)}
        <div class="hint" style="font-size:12px;padding:0 14px 10px">сразу ${fmt(p.ref || 0)} · за уровни ${fmt(p.ref_lvl || 0)} · рубежи ${fmt(p.ref_ms || 0)} · с покупок ${fmt(p.ref_buy || 0)} · топ ${fmt(p.ref_top || 0)}</div></div>
      <div class="sec-t">Лучшие за 7 дней</div>
      <div class="box">${d.top.map(u => `<div class="row tap" data-act="adm-user" data-id="${u.id}">${avaHTML(u, 28)}<div class="grow" style="min-width:0"><div class="t">${esc(u.name)}</div><div class="s">активных ${u.a}</div></div><b>${u.n}</b></div>`).join("") || `<div class="hint" style="padding:14px">Пусто</div>`}</div>
      <div class="sec-t">Настройки</div>
      <div class="box">
        ${sw("on", "Реферальная программа", "Выключить — ссылки работают, но никаких наград")}
        ${field("new_bonus", "Другу при входе по ссылке", "сверх стартовых звёзд", "⭐")}
        ${field("join_bonus", "Пригласившему сразу", "мгновенная награда — её проще всего накрутить твинками", "⭐")}
        ${field("l1_level", "Первый уровень друга", "друг дорос — пригласившему бонус ниже; он же порог «активного» друга", "ур.")}
        ${field("l1_bonus", "Бонус за первый уровень", "", "⭐")}
        ${field("l2_level", "Второй уровень друга", "", "ур.")}
        ${field("l2_bonus", "Бонус за второй уровень", "", "⭐")}
        ${field("buy_pct", "Доля с покупок друга", "% от игровых звёзд, купленных другом за Telegram Stars", "%")}
        ${field("milestones", "Рубежи за активных друзей", "друзей:звёзд через запятую, каждый — один раз", "", true)}
        ${sw("top_on", "Недельный топ приглашений", "Призы в понедельник за прошлую неделю — по числу друзей, ставших активными")}
        ${field("top_prizes", "Призы топа", "за 1, 2, 3… место через запятую", "", true)}
        ${field("top_min", "Минимум для приза", "активных друзей за неделю", "шт")}
        ${sw("gift_on", "Ключ от кейса «от друга»", "Новичок по ссылке получает ключ от «Ширпотреба», пригласившему приходит сообщение, когда тот откроет")}
        ${sw("duo_on", "Цель на двоих", "За 7 дней друг доходит до 5 ур. и набирает оборот, пригласивший тоже, награда обоим")}
        ${field("duo_prize", "Цель на двоих: награда каждому", "с поправкой на курс банка", "⭐")}
        ${field("duo_friend", "Оборот друга за неделю", "сумма выигрышей и проигрышей; потеря на ней не меньше 3,1%, держи награду ниже", "⭐")}
        ${field("duo_ref", "Оборот пригласившего за неделю", "", "⭐")}
      </div>
      ${gw ? `<div class="sec-t">Розыгрыши в канале</div>
      <div class="box">
        <div class="adm-odd"><div class="adm-oh"><b>Канал</b>${gw.channel ? `<span class="adm-tag">${esc(gw.channel)}</span>` : ""}</div>
          <div class="adm-os" style="white-space:normal">Добавь бота в канал администратором с правом публиковать, потом укажи @имя канала</div>
          ${gw.canEdit ? `<div class="adm-oc"><input class="adm-oi" style="flex:1" data-gw="channel" placeholder="@channel" value=""><button class="btn sm gold" data-act="adm-gw-ch">${ic("check")}</button></div>` : ""}</div>
        ${gw.canEdit && gw.channel ? `<div class="adm-odd"><div class="adm-oh"><b>Новый розыгрыш</b></div>
          <div class="adm-os" style="white-space:normal">Приз из банка, сейчас до ⭐ ${fmt(gw.cap)}. Бот опубликует пост с кнопкой «Участвовать»</div>
          <div class="adm-gwf"><input class="adm-oi" data-gw="title" placeholder="Название" maxlength="60">
            <label><span>Приз, ⭐</span><input class="adm-oi" data-gw="prize" inputmode="numeric" value="10000"></label>
            <label><span>Победителей</span><input class="adm-oi" data-gw="winners" inputmode="numeric" value="5"></label>
            <label><span>Часов</span><input class="adm-oi" data-gw="hours" inputmode="numeric" value="24"></label>
            <label><span>С уровня</span><input class="adm-oi" data-gw="minLevel" inputmode="numeric" value="2"></label>
            <button class="btn gold" data-act="adm-gw-new">${ic("send")}Опубликовать</button></div></div>` : ""}
      </div>
      ${gw.list.length ? `<div class="box gw-list">${gw.list.map(g => `<div class="row kv tap" data-act="adm-gw-open" data-id="${g.id}"><div class="grow" style="min-width:0"><div class="t">${esc(g.title)}</div>
        <div class="s">${g.status === "open" ? `идёт · участников ${g.count}` : g.status === "done" ? `итоги · участников ${g.count}` : "отменён"} · ⭐ ${fmt(g.prize)} на ${g.winners}</div></div>
        ${gw.canEdit && g.status === "open" ? `<button class="btn sm ghost" data-act="adm-gw-cancel" data-id="${g.id}">${ic("x")}</button>` : ""}</div>`).join("")}</div>` : ""}` : ""}
      ${ed ? "" : `<div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Менять настройки может только владелец</div>`}
      <div class="disc">Бонусы за уровни друга платятся только за друзей, пришедших после запуска новой программы (14.10). Рубежи считаются по всем друзьям. Награды растут с уровнем друга, а не с его ставками — накрутить оборотом нельзя.</div>`;
    starify(body);
  } else if (ADM.tab === "fr") {   // франшиза: боты игроков (franchise.py)
    const [d, an, mb] = await Promise.all([api("admin/franchise"), api("admin/franchise/announce").catch(() => null), api("admin/franchise/main").catch(() => null)]), c = d.cfg, ed = d.canEdit;
    const mbSel = (k, list) => `<select class="adm-oi" style="flex:1" data-mb="${k}"${ed ? "" : " disabled"}><option value="0">@${esc(mb.base)} — исходный</option>${list.map(b => `<option value="${b.id}"${mb[k] === b.id ? " selected" : ""}>@${esc(b.username)}${b.admin ? " · бот админа" : ""}</option>`).join("")}</select>`;
    const mainHTML = !mb ? "" : `<div class="sec-t">Главный бот</div>
      <div class="box">
        <div class="adm-odd"><div class="adm-oh"><b>Лицо игры</b>${mb.face ? `<span class="adm-tag">изменено</span>` : ""}</div>
          <div class="adm-os" style="white-space:normal">Куда ведут ссылки (рефералки, кланы, подарки), «играй в @…», бот в рассылках. Любой работающий бот. Если это бот игрока — новые игроки по ссылкам засчитываются ему во франшизе.</div>
          <div class="adm-oc">${mbSel("face", mb.bots)}${ed ? `<button class="btn sm gold" data-act="adm-mb" data-k="face">${ic("check")}</button>` : ""}</div></div>
        <div class="adm-odd"><div class="adm-oh"><b>Оплаты Telegram Stars</b>${mb.pay ? `<span class="adm-tag">изменено</span>` : ""}</div>
          <div class="adm-os" style="white-space:normal">Через какого бота выставляются счета. Только боты админов: настоящие звёзды копятся у владельца бота в @BotFather.${mb.bots.some(b => b.admin) ? "" : " У админов пока нет своих ботов — создай со своего аккаунта: /franchise в @" + esc(mb.base) + "."}</div>
          <div class="adm-oc">${mbSel("pay", mb.bots.filter(b => b.admin))}${ed ? `<button class="btn sm gold" data-act="adm-mb" data-k="pay">${ic("check")}</button>` : ""}</div></div>
        <div class="hint" style="font-size:12px;padding:2px 14px 10px;white-space:normal">Создание франшиз и приём старых платежей всегда остаются за @${esc(mb.base)}. Если назначенный бот отключат — игра сама вернётся к @${esc(mb.base)}.</div>
      </div>`;
    const st = { on: "работает", off: "отключён", limit: "лимит владельца" };
    const sw = (k, title, hint) => `<div class="row kv"><div class="grow"><div class="t">${title}</div><div class="s" style="white-space:normal">${hint}</div></div>
      ${ed ? `<button class="sw${c[k] ? " on" : ""}" data-act="adm-frc-sw" data-k="${k}" data-v="${c[k] ? 0 : 1}"></button>` : `<b>${c[k] ? "да" : "нет"}</b>`}</div>`;
    const field = (k, title, hint, unit) => `<div class="adm-odd"><div class="adm-oh"><b>${title}</b>${d.changed.includes(k) ? `<span class="adm-tag">изменено</span>` : ""}</div>
      <div class="adm-os">${hint} · по умолчанию ${String(d.defaults[k]).replace(".", ",")}</div>
      ${ed ? `<div class="adm-oc"><input class="adm-oi" inputmode="${Number.isInteger(d.defaults[k]) ? "numeric" : "decimal"}" data-k="${k}" value="${String(c[k]).replace(".", ",")}"><span class="adm-op">${unit}</span>
        <button class="btn sm gold" data-act="adm-frc" data-k="${k}">${ic("check")}Сохранить</button>
        ${d.changed.includes(k) ? `<button class="btn sm ghost" data-act="adm-frc-rs" data-k="${k}">${ic("refresh")}</button>` : ""}</div>` : `<div class="adm-oc"><b>${fmt(c[k])} ${unit}</b></div>`}</div>`;
    body.innerHTML = `${d.manager ? "" : `<div class="disc" style="margin-top:0">⚠️ Главный бот ещё не может создавать ботов: @BotFather → Mini App → бот → включить управление ботами (Bot Management). Пока не включено, игроки франшизу не видят.</div>`}
      ${mainHTML}
      <div class="sec-t">Франшиза</div>
      <div class="box">
        ${sw("on", "Франшиза включена", "Кнопка в игре, /franchise в боте, подключение новых ботов. Уже созданные боты работают, пока не отключишь их ниже")}
        ${sw("game_promo", "Баннер в игре", "Плашка «Свой бот с этой игрой» на главной (игрок может скрыть на 14 дней)")}
        ${sw("bot_promo", "Бот предлагает игрокам", "Сообщение «создай свой бот» — активным игрокам с включёнными уведомлениями, раз в 30 минут понемногу")}
        ${field("cut_pct", "Пассивный доход: доля каждому", "% от всего дохода игры (игры + налоги и комиссии) — каждому владельцу бота (с уровня ниже) и каждому админу, начисляется каждую минуту из банка. 0 — выключено", "%")}
        ${sw("cap_on", "Общий потолок", "Всем получателям вместе — не больше потолка; если их много, потолок делится поровну")}
        ${c.cap_on ? field("cap_pct", "Потолок на всех", "% дохода игры, который получают все вместе", "%") : ""}
        <div class="hint" style="font-size:12px;padding:2px 14px 10px">Сейчас получателей: <b>${d.cut.n}</b> · каждому ${String(d.cut.share).replace(".", ",")}% · всем вместе ${String(d.cut.total).replace(".", ",")}% дохода игры</div>
        ${field("create_reward", "Сразу за создание бота", "один раз на аккаунт · 0 — без награды", "⭐")}
        ${field("create_level", "…если владелец не ниже уровня", "против твинков: ниже — получит, когда дорастёт; 1 — всем сразу", "ур.")}
        ${field("reward", "За приведённых игроков", "один раз на аккаунт · 0 — без награды", "⭐")}
        ${field("players", "Сколько игроков привести", "новых игроков, пришедших через его бота", "шт")}
        ${field("level", "Уровень этих игроков", "против твинков: уровень даётся за обороты", "ур.")}
        ${field("max_per_owner", "Ботов на одного игрока", "сверх лимита бот создаётся в Telegram, но к игре не подключается", "шт")}
        ${field("promo_days", "Предложение от бота — не чаще", "одному игроку раз в столько дней", "дн")}
        ${field("promo_level", "Предлагать с уровня", "новичкам рано", "ур.")}
      </div>
      <div class="box" style="margin-top:10px">${admKv("Предложений отправлено", `<b>${fmt(d.promo.total)}</b> · за 7 дн ${fmt(d.promo.week)}`)}</div>
      ${an ? `<div class="sec-t">Рассылка о франшизе</div>
      <div class="box" style="padding:12px 14px;font-size:13.5px;line-height:1.45;white-space:normal">${an.text.replace(/\n/g, "<br>")}
        <div class="hint" style="font-size:12px;margin-top:8px">Кнопки под сообщением: «🤖 Создать бота» и «Открыть игру»</div></div>
      <div class="btns"><button class="btn gold" data-act="adm-frc-ann" data-n="${an.total}"${d.promo.running || !ed ? " disabled" : ""}>${ic("send")}Разослать всем · ${fmt(an.total)}</button></div>
      <div class="hint" style="font-size:12px;text-align:center;margin:4px 0 10px">Всем игрокам с включёнными сообщениями от бота, кроме владельцев ботов. Текст меняется вместе с настройками выше</div>` : ""}
      <div class="btns"><button class="btn ghost" data-act="adm-frc-promo"${d.promo.running ? " disabled" : ""}>${ic("send")}${d.promo.running ? "Рассылка идёт…" : "Разослать предложение сейчас"}</button></div>
      <div class="sec-t">Боты игроков · ${d.bots.length}</div>
      <div class="box">${d.bots.map(b => `<div class="row kv">
        <div class="grow" style="min-width:0"><div class="t">@${esc(b.username || "?")}</div>
          <div class="s" style="white-space:normal">${esc(b.oname || "id " + b.owner)} · ${admDate(b.created)} · ${st[b.status] || b.status}<br>пришло ${fmt(b.came)} · играют сейчас ${fmt(b.now)} · ${b.paid ? "награда выплачена" : `к награде ${b.progress}/${d.need}`}<br>пассивный доход владельца: всего ${fmt(b.cut)} ⭐ · за сегодня пока ≈ ${fmt(b.today)} ⭐</div></div>
        ${b.status === "limit" ? "" : `<button class="sw${b.status === "on" ? " on" : ""}" data-act="adm-fr" data-id="${b.id}" data-v="${b.status === "on" ? 0 : 1}"></button>`}</div>`).join("")
        || `<div class="hint" style="padding:14px">Ботов пока нет</div>`}</div>
      <div class="disc">Игрок создаёт бота кнопкой в игре или командой /franchise в главном боте. База общая. Награды — ⭐ ${fmt(c.create_reward)} за создание (с ${c.create_level} ур.) и ⭐ ${fmt(d.reward)}, когда бот приведёт ${d.need} игроков ${d.level}+ уровня; каждая один раз на аккаунт. Если владелец сменит вебхук или кнопку «Играть», бот отключится сам.</div>`;
  } else if (ADM.tab === "bc") {
    const st = await api("admin/broadcast");
    body.innerHTML = `<textarea id="adm-bc" rows="5" placeholder="Текст сообщения всем игрокам"></textarea>
      <button class="btn" data-act="adm-bc" style="margin-top:10px" ${st.running ? "disabled" : ""}>${ic("send")}Отправить всем</button>
      <div class="hint" style="font-size:12.5px;text-align:center;margin-top:10px">${st.total ? `Последняя рассылка: отправлено ${st.sent} из ${st.total}, ошибок ${st.failed}${st.running ? " · идёт…" : ""}` : "Сообщение придёт от бота с кнопкой «Открыть». Заблокированным не отправляется."}</div>`;
    // регулярные рассылки
    const sc = await api("admin/broadcast/sched").catch(() => null);
    if (sc && body.isConnected) {
      const per = n => ({ 1: "каждый день", 2: "раз в 2 дня", 3: "раз в 3 дня", 7: "раз в неделю" })[n] || `раз в ${n} дн.`;
      const left = x => { const s = Math.max(0, x.next - sc.now), h = Math.floor(s / 3600); return h >= 24 ? `${Math.floor(h / 24)} д ${h % 24} ч` : h ? `${h} ч ${Math.floor(s % 3600 / 60)} мин` : `${Math.ceil(s / 60)} мин`; };
      body.insertAdjacentHTML("beforeend", `<div class="sec-t" style="margin-top:16px">${ic("clock")}Регулярные</div>
        ${sc.list.length ? `<div class="box">${sc.list.map(x => `<div class="adm-odd bcs${x.on ? "" : " off"}">
          <div class="adm-oh"><b>${per(x.every)} в ${x.time}</b><span class="adm-tag${x.on ? "" : " red"}">${x.on ? `через ${left(x)}` : "на паузе"}</span></div>
          <div class="adm-os bcs-t">${esc(x.text)}</div>
          ${x.last ? `<div class="adm-os">последняя: ${new Date(x.last * 1000).toLocaleString("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · ${fmt(x.lastSent)} игрокам</div>` : ""}
          <div class="adm-oc"><button class="btn sm ghost" data-act="adm-bcs" data-a="toggle" data-id="${x.id}">${x.on ? "Пауза" : "Включить"}</button>
            <button class="btn sm ghost" data-act="adm-bcs" data-a="now" data-id="${x.id}">${ic("send")}Сейчас</button>
            <button class="btn sm red" data-act="adm-bcs" data-a="del" data-id="${x.id}">${ic("x")}</button></div></div>`).join("")}</div>` : ""}
        <div class="box adm-odd" style="margin-top:8px">
          <textarea id="adm-bcs" rows="4" placeholder="Текст регулярной рассылки"></textarea>
          <div class="adm-oc" style="flex-wrap:wrap"><select id="adm-bcs-e" class="adm-sel">${sc.every.map(n => `<option value="${n}">${per(n)}</option>`).join("")}</select>
            <input id="adm-bcs-t" type="time" value="18:00" class="adm-oi" style="width:96px"><span class="adm-op">МСК</span>
            <button class="btn sm gold" data-act="adm-bcs-add">${ic("plus")}Добавить</button></div>
          <div class="adm-os">Придёт ${fmt(sc.audience)} игрокам — тем, у кого включены напоминания от бота (кто выключил — не получит).</div></div>`);
    }
  } else if (ADM.tab === "db") {
    body.innerHTML = `<div class="box adm-odd"><div class="adm-oh"><b>${ic("download")}Экспорт</b></div>
        <div class="adm-os">Свежая копия базы (игроки, звёзды, подарки, всё) — бот пришлёт файл .db.gz тебе в личку. Игру не останавливает.</div>
        <div class="adm-oc"><button class="btn sm gold" data-act="adm-db-exp">${ic("send")}Прислать базу в Telegram</button></div></div>
      <div class="box adm-odd" style="margin-top:10px"><div class="adm-oh"><b>${ic("upload")}Импорт</b><span class="adm-tag red">заменяет всё</span></div>
        <div class="adm-os">Файл .db или .db.gz (например, из экспорта или ежедневного бэкапа). Текущая база перед заменой сохранится в backups/ на сервере. После импорта игра перезапустится — секунд 10.</div>
        <div class="adm-oc"><label class="btn sm ghost" style="margin-left:auto">${ic("upload")}Выбрать файл<input type="file" id="adm-db-file" accept=".db,.gz,application/gzip,application/octet-stream" hidden></label></div></div>
      <div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Только владелец (ADMIN_IDS в .env)</div>`;
    body.querySelector("#adm-db-file").onchange = e => { const f = e.target.files[0]; e.target.value = ""; if (f) admDbImport(f); };
  } else {
    const [r, al] = await Promise.all([api("admin/log"), api("admin/actlog/cfg")]);
    const kb = b => b < 1024 ? b + " Б" : b < 1048576 ? (b / 1024).toFixed(0) + " КБ" : (b / 1048576).toFixed(1) + " МБ";
    const cfg = `<div class="box">
      <div class="adm-oh"><b>Настройки журналов</b></div>
      <div class="adm-os" style="margin:2px 0 10px">Админский — действия админов (эта вкладка). Подробный — каждый запрос игроков (отдельная база, для разбора жалоб и откатов).</div>
      <div class="row kv"><div class="grow"><div class="t">Админский журнал</div><div class="s">${fmt(r.total || 0)} записей${r.oldest ? ` · с ${admDate(r.oldest)}` : ""}</div></div></div>
      <div class="auto" style="margin:6px 0 2px"><span style="flex:1">Хранить, дней <span class="hint">(0 — всё)</span></span>
        ${r.canEdit ? `<input class="adm-oi" style="width:64px;text-align:center" inputmode="numeric" id="adm-alog-keep" value="${r.keep_days}"><button class="btn sm gold" data-act="adm-alog-keep">${ic("check")}</button>` : `<b>${r.keep_days || "всё"}</b>`}</div>
      ${r.canEdit ? `<button class="btn sm red" data-act="adm-alog-clear" style="margin-top:8px">${ic("x")}Очистить админский журнал</button>` : ""}
      <div style="height:1px;background:rgba(255,255,255,.09);margin:12px 0"></div>
      <div class="row kv"><div class="grow"><div class="t">Подробный журнал действий</div><div class="s">${fmt(al.rows || 0)} записей · ${kb(al.bytes || 0)}${al.oldest ? ` · с ${admDate(al.oldest)}` : ""}</div></div>
        ${al.canEdit ? `<button class="sw${al.on ? " on" : ""}" data-act="adm-actlog-on" data-v="${al.on ? 0 : 1}"></button>` : `<b>${al.on ? "вкл" : "выкл"}</b>`}</div>
      <div class="auto" style="margin:6px 0 2px"><span style="flex:1">Хранить, дней</span>
        ${al.canEdit ? `<input class="adm-oi" style="width:64px;text-align:center" inputmode="numeric" id="adm-actlog-keep" value="${al.keep_days}"><button class="btn sm gold" data-act="adm-actlog-keep">${ic("check")}</button>` : `<b>${al.keep_days}</b>`}</div>
      ${al.canEdit ? `<button class="btn sm red" data-act="adm-actlog-clear" style="margin-top:8px">${ic("x")}Очистить подробный журнал</button>` : ""}
      ${al.canEdit && !al.on ? `<div class="adm-warn" style="margin-top:10px">Подробный журнал выключен — новые действия игроков не записываются.</div>` : ""}
    </div>`;
    body.innerHTML = `<div class="sec-t" style="margin-top:0">Действия админов</div>${admLogHTML(r.log)}` + `<div class="sec-t">Настройки</div>` + cfg;
  }
}

async function openAdmUser(id) {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"));
  const draw = async () => {
    const [u, cs, fr, tr, ins] = await Promise.all([api("admin/user/" + id), api(`admin/user/${id}/cosm`), api(`admin/user/${id}/friends`),
      api(`admin/user/${id}/transfers`).catch(() => ({ sent: 0, got: 0, list: [] })), api(`admin/user/${id}/insight`).catch(() => null)]);
    const [wa, fzz] = await Promise.all([api(`admin/user/${id}/addr`).catch(() => null), api(`admin/user/${id}/freeze`).catch(() => null)]);
    const frRow = (f, s) => `<div class="row tap" data-act="adm-user" data-id="${f.id}">${avaHTML(f, 32)}<div class="grow"><div class="t">${esc(f.name)}</div><div class="s">${s} · был ${admDate(f.seen)}</div></div>${ic("chev")}</div>`;
    replaceSheet(el, `<div style="display:flex;align-items:center;gap:12px;margin:4px 0 12px">${avaHTML(u, 48)}<div class="grow"><b style="font-size:19px">${esc(u.name)}</b>
        <div class="hint" style="font-size:13px">${u.username ? "@" + esc(u.username) + " · " : ""}id ${u.id}${u.banned ? ` · <span class="tl">заблокирован</span>` : ""}</div></div></div>
      ${fzz && fzz.frozen ? `<div class="adm-frz">${ic("lock")}<div><b>Кошелёк заморожен</b><span>с ${admDate(fzz.ts)}${fzz.by ? " · " + esc(fzz.by.name) : ""}${fzz.reason ? " · " + esc(fzz.reason) : ""}</span></div></div>` : ""}
      <div class="box">${admKv("Баланс", `<b>⭐ ${fmt(u.stars)}</b>`)}${admKv("Подарков", `<b>${fmt(u.gifts)} · ⭐ ${fmt(u.giftsValue)}</b>`)}
        ${admKv("Итог в играх 24 ч / всего", `<span>${admSgn(u.pnl24)} / ${admSgn(u.pnlAll)}</span>`)}${admKv("Кейсов открыто", `<b>${fmt(u.opened)}</b>`)}
        ${admKv("Рефералов", `<b>${fmt(u.refs)}</b>`)}${admKv("Регистрация / был", `<b>${admDate(u.created)} / ${admDate(u.seen)}</b>`)}</div>
      ${wa ? `<div class="sec-t">${ic("wallet")}Кошелёк</div><div class="box adm-wal">
        ${[["main", "Адрес", wa.addr, "по нему игроку переводят звёзды"], ["anon", "Анонимный", wa.anon, "секретный: отправитель не видит, кому ушло"]].map(([k, t, a, s]) => `<div class="row"><div class="grow">
          <div class="s">${t} · ${s}</div><div class="t adm-addr">${esc(a)}</div></div></div>
          <div class="btns" style="margin:0 12px 10px"><button class="btn ghost sm" style="flex:1" data-act="adm-addr" data-id="${u.id}" data-k="${k}" data-m="rnd">${ic("refresh")}Новый</button>
            <button class="btn ghost sm" style="flex:1" data-act="adm-addr" data-id="${u.id}" data-k="${k}" data-m="own">${ic("edit")}Свой</button></div>`).join("")}</div>` : ""}
      ${ins ? admInsightHTML(ins) : ""}
      <div class="sec-t">Кто пригласил</div>
      <div class="box">${u.inviter ? `<div class="row tap" data-act="adm-user" data-id="${u.inviter.id}">${avaHTML(u.inviter, 36)}<div class="grow"><div class="t">${esc(u.inviter.name)}</div>
        <div class="s">${u.refSrc === "gift" ? "через подарок по ссылке" : "по реферальной ссылке"} · ${u.inviter.username ? "@" + esc(u.inviter.username) + " · " : ""}id ${u.inviter.id}</div></div>${ic("chev")}</div>`
        : `<div class="hint" style="padding:14px">Без приглашения — вход напрямую</div>`}</div>
      <div class="btns"><button class="btn green sm" style="flex:1" data-act="adm-stars" data-id="${u.id}" data-v="1">+ Звёзды</button>
        <button class="btn ghost sm" style="flex:1" data-act="adm-stars" data-id="${u.id}" data-v="-1" data-b="${u.stars}">− Звёзды</button>
        <button class="btn ${u.banned ? "ghost" : "red"} sm" style="flex:1" data-act="adm-ban" data-id="${u.id}" data-v="${u.banned ? 0 : 1}">${u.banned ? "Разбанить" : "Забанить"}</button></div>
      ${fzz && !u.isAdmin ? `<button class="btn ${fzz.frozen ? "ghost" : "adm-frzb"} sm" style="width:100%;margin-top:8px" data-act="adm-freeze" data-id="${u.id}" data-v="${fzz.frozen ? 0 : 1}">${ic("lock")}${fzz.frozen ? "Разморозить кошелёк" : "Заморозить кошелёк"}</button>` : ""}
      <div class="btns"><button class="btn gold sm" style="flex:1" data-act="adm-gift" data-id="${u.id}">${ic("gift")}Подарок</button>
        <button class="btn gold sm" style="flex:1" data-act="adm-keys" data-id="${u.id}">${ic("lock")}Кейсы</button></div>
      ${u.canGrant && !u.isOwner ? `<button class="btn ${u.isAdmin ? "red" : "ghost"} sm" style="width:100%;margin-top:8px" data-act="adm-grant" data-id="${u.id}" data-v="${u.isAdmin ? 0 : 1}" data-n="${esc(u.name)}">${ic("crown")}${u.isAdmin ? "Снять админку" : "Сделать админом"}</button>`
        : u.isAdmin ? `<div class="hint" style="font-size:12px;text-align:center;margin-top:8px">${u.isOwner ? "Владелец" : "Администратор"}</div>` : ""}
      <button class="btn ghost sm" style="width:100%;margin-top:8px" data-act="profile" data-id="${u.id}">Открыть профиль</button>
      ${u.log.length ? `<div class="sec-t">Действия админа</div><div class="box">${u.log.map(x => admKv(`${esc(x.action)} ${esc(x.detail || "")}`, `<span class="hint" style="font-size:12px">${admDate(x.ts)}</span>`)).join("")}</div>` : ""}
      <div class="sec-t">Приглашённые · ${u.invited.length}</div>
      <div class="box">${u.invited.map(f => `<div class="row tap" data-act="adm-user" data-id="${f.id}">${avaHTML(f, 32)}<div class="grow"><div class="t">${esc(f.name)}</div><div class="s">в игре с ${admDate(f.created)} · активность ${admDate(f.seen)}</div></div>${ic("chev")}</div>`).join("") || `<div class="hint" style="padding:14px">Приглашённых нет</div>`}</div>
      <div class="sec-t">Друзья · ${fr.ok.length}</div>
      <div class="box">${fr.ok.map(f => frRow(f, "друзья с " + admDate(f.since))).join("") || `<div class="hint" style="padding:14px">Друзей нет</div>`}</div>
      ${fr.in.length || fr.out.length ? `<div class="sec-t">Заявки в друзья</div><div class="box">${fr.in.map(f => frRow(f, "входящая заявка")).join("")}${fr.out.map(f => frRow(f, "исходящая заявка")).join("")}</div>` : ""}
      <div class="sec-t">Переводы · отправлено ⭐ ${fmt(tr.sent)} · получено ⭐ ${fmt(tr.got)}</div>
      <div class="box">${tr.list.map(t => `<div class="row tap" data-act="adm-user" data-id="${t.user.id}">${avaHTML(t.user, 32)}<div class="grow"><div class="t">${esc(t.user.name)}</div>
        <div class="s">${t.in ? "получено от" : "отправлено"} · ${admDate(t.ts)}${t.note ? " · «" + esc(t.note) + "»" : ""}</div></div><b class="${t.in ? "tw" : "tl"}">${t.in ? "+" : "−"}${fmt(t.amount)}</b></div>`).join("") || `<div class="hint" style="padding:14px">Переводов не было</div>`}</div>
      <div class="sec-t">Оформление · ${cs.list.length}</div>
      <div class="box">${cs.list.map(c => `<div class="row"><div class="grow"><div class="t">${esc(c.title)}</div><div class="s">${c.kind === "frame" ? "рамка" : "ник"} · до ${admDate(c.until)} · ⭐ ${fmt(c.price)}</div></div>
        <button class="btn sm red" data-act="adm-cosm-rm" data-id="${u.id}" data-i="${c.item}" data-n="${esc(c.title)}" data-p="${c.price}">Забрать</button></div>`).join("") || `<div class="hint" style="padding:14px">Ничего не куплено</div>`}</div>
      <div class="sec-t">Подарки · ${u.giftList.length}</div>
      <div class="box">${u.giftList.map(g => `<div class="row"><img class="spi" style="width:36px;height:36px;margin:0" src="${A.model(g.col, g.model, 64)}" alt="">
        <div class="grow"><div class="t">${esc(g.col)} <small class="hint">#${fmt(g.num)}</small></div><div class="s">${esc(g.model)} · ⭐ ${fmt(g.value)}${g.price != null ? " · на маркете" : ""}</div></div>
        <button class="btn sm red" data-act="adm-gift-rm" data-id="${u.id}" data-g="${g.id}" data-n="${esc(g.col)} #${fmt(g.num)}">${ic("x")}</button></div>`).join("") || `<div class="hint" style="padding:14px">Подарков нет</div>`}</div>
      <div class="sec-t">Последние операции</div>
      <div class="box">${u.events.map(x => admKv(`${esc(x.kind)} · ${admDate(x.ts)}`, admSgn(x.delta))).join("") || `<div class="hint" style="padding:14px">Пусто</div>`}</div>`);
  };
  el._redraw = draw;
  await draw();
}

let ADM_CAT = null;
let ADM_CIMG = {};   // выбранные, но ещё не сохранённые картинки обложек: cid → data URL
function admCoverData(file) {
  return new Promise((res, rej) => {
    const img = new Image(), u = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(u);
      const S = 512, k = Math.min(1, S / Math.max(img.width, img.height)), w = Math.round(img.width * k), h = Math.round(img.height * k);
      const cv = document.createElement("canvas"); cv.width = S; cv.height = S;
      cv.getContext("2d").drawImage(img, (S - w) / 2, (S - h) / 2, w, h);
      res(cv.toDataURL("image/png"));
    };
    img.onerror = rej; img.src = u;
  });
}
const admSel = (id, opts, first) => `<select id="${id}" class="adm-sel">${first ? `<option value="">${first}</option>` : ""}${opts.map(o => `<option value="${esc(o[0])}">${esc(o[1])}</option>`).join("")}</select>`;
async function openAdmGift(uid) {
  if (!ADM_CAT || !ADM_CAT.bases) ADM_CAT = await api("admin/catalog");
  const el = openSheet(`<h2 class="gtitle">Выдать подарок</h2>
    <input id="ag-q" placeholder="Поиск коллекции" style="margin-bottom:10px">
    <div class="adm-cg" id="ag-grid"></div>`, "admg-s");
  el._uid = uid;
  const paint = qs => {
    const list = ADM_CAT.cols.filter(c => !qs || c.toLowerCase().includes(qs.toLowerCase()));
    el.querySelector("#ag-grid").innerHTML = list.map(c => `<button class="adm-ci" data-act="ag-col" data-v="${esc(c)}"><img src="${A.orig(c, 128)}" loading="lazy" alt="">
      <b>${esc(c)}</b><span>⭐ ${short(ADM_CAT.bases[c] || 0)}</span></button>`).join("") || `<div class="hint" style="grid-column:1/-1;padding:20px;text-align:center">Ничего не найдено</div>`;
    starify(el.querySelector("#ag-grid"));
  };
  let t; el.querySelector("#ag-q").oninput = e => { clearTimeout(t); t = setTimeout(() => paint(e.target.value.trim()), 200); };
  paint("");
}
async function admGiftCol(col) {
  const el = topSheet(), uid = el._uid;
  const d = await api("admin/catalog?col=" + encodeURIComponent(col));
  el._g = { col, model: "" };
  replaceSheet(el, `<div class="adm-gh"><button class="btn sm ghost" data-act="ag-back">${ic("chev")}</button><img src="${A.orig(col, 96)}" alt=""><div><b>${esc(col)}</b><span>${d.models.length} моделей · база ⭐ ${fmt(d.base)}</span></div></div>
    <div class="sec-t" style="margin-top:6px">Модель <span class="hint" style="text-transform:none;font-weight:500">редкие — первыми</span></div>
    <div class="adm-cg models" id="ag-models"><button class="adm-ci on" data-act="ag-model" data-v=""><span class="adm-rnd">${ic("refresh")}</span><b>Случайная</b><span>как из кейса</span></button>
      ${d.models.map(m => `<button class="adm-ci" data-act="ag-model" data-v="${esc(m)}"><img src="${A.model(col, m, 128)}" loading="lazy" alt=""><b>${esc(m)}</b></button>`).join("")}</div>
    <details class="rules" style="margin-top:12px"><summary>${ic("layers")}Дополнительно: фон и узор</summary>
      <div class="adm-f"><span>Фон</span>${admSel("ag-bd", d.backdrops.map(x => [x, x]), "случайный")}</div>
      <div class="adm-f"><span>Узор</span>${admSel("ag-sym", d.symbols.map(x => [x, x]), "случайный")}</div></details>
    <div class="adm-gfoot">
      <div class="adm-f" style="margin-top:0"><span>Сколько</span><input id="ag-n" inputmode="numeric" value="1"></div>
      <div class="auto" style="margin-top:8px"><button class="sw on" id="ag-feed" data-act="adm-feed-tog"></button><span style="flex:1">Показать в живой ленте</span></div>
      <button class="btn gold" data-act="adm-gift-go" data-id="${uid}" style="margin-top:10px">${ic("gift")}Выдать</button></div>`);
  starify(el);
}
async function openAdmKeys(uid) {
  if (!ADM_CAT) ADM_CAT = await api("admin/catalog");
  openSheet(`<h2 class="gtitle">Выдать кейсы</h2>
    <div class="adm-f"><span>Кейс</span>${admSel("ak-cid", ADM_CAT.cases.map(c => [c.id, `${c.title}${c.price ? " · ⭐ " + fmt(c.price) : ""}`]))}</div>
    <div class="adm-f"><span>Сколько</span><input id="ak-n" inputmode="numeric" value="1"></div>
    <button class="btn gold" data-act="adm-keys-go" data-id="${uid}" style="margin-top:12px">${ic("lock")}Выдать ключи</button>
    <div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Игрок откроет кейс бесплатно, даже если уровень ещё не дорос. Придёт сообщение от бота.</div>`);
}
Object.assign(ACT, {
  adm: () => openAdmin(),
  "adm-event": async el => { await post("admin/event", { mode: el.dataset.v }); H.ok(); toast("Готово", "ok"); CASES = []; await loadMe(); admRender(); },
  "adm-promo": async el => { await post("admin/promo", { mode: el.dataset.v }); H.ok(); toast("Готово", "ok"); await loadMe(); admRender(); },
  "adm-gift": el => openAdmGift(+el.dataset.id),
  "adm-keys": el => openAdmKeys(+el.dataset.id),
  "adm-feed-tog": el => { el.classList.toggle("on"); H.sel(); },
  "adm-gift-rm": async el => {
    if (!await confirmM("Забрать подарок?", `${esc(el.dataset.n)} будет удалён у игрока насовсем. Действие попадёт в журнал.`, "Забрать")) return;
    await post(`admin/user/${el.dataset.id}/gift/${el.dataset.g}/remove`); H.ok(); toast("Подарок забран", "ok");
    topSheet()._redraw && topSheet()._redraw();
  },
  "adm-cosm-rm": async el => {
    const d = el.dataset, el2 = openSheet(`<h2 class="gtitle">Забрать «${esc(d.n)}»?</h2>
      <p class="hint" style="text-align:center;margin:0 0 14px">Вещь пропадёт у игрока. Действие попадёт в журнал.</p>
      <button class="btn gold" data-act="adm-cosm-go" data-r="1">Забрать и вернуть ⭐ ${fmt(+d.p)}</button>
      <button class="btn ghost" data-act="adm-cosm-go" data-r="0" style="margin-top:8px">Забрать без возврата</button>`);
    el2._c = { id: d.id, item: d.i };
    starify(el2);
  },
  "adm-cosm-go": async el => {
    const c = topSheet()._c;
    const r = await post(`admin/user/${c.id}/cosm/${c.item}/remove`, { refund: el.dataset.r === "1" }); H.ok();
    toast(r.refund ? `Забрано, вернули ⭐ ${fmt(r.refund)}` : "Забрано", "ok"); closeSheet();
    if (+c.id === ME.id) loadMe();
    topSheet() && topSheet()._redraw && topSheet()._redraw();
  },
  "ag-col": el => admGiftCol(el.dataset.v),
  "ag-back": () => { const uid = topSheet()._uid; closeSheet(); openAdmGift(uid); },
  "ag-model": el => { topSheet()._g.model = el.dataset.v; H.sel(); el.parentElement.querySelectorAll(".adm-ci").forEach(b => b.classList.toggle("on", b === el)); },
  "adm-gift-go": async el => {
    const s = topSheet(), v = id => s.querySelector(id).value;
    const r = await post(`admin/user/${el.dataset.id}/gift`, { col: s._g.col, model: s._g.model, backdrop: v("#ag-bd"), symbol: v("#ag-sym"), n: Math.max(1, +v("#ag-n") || 1), feed: s.querySelector("#ag-feed").classList.contains("on") });
    H.ok(); toast(`Выдано: ${r.gifts.length} · ⭐ ${fmt(r.gifts.reduce((a, g) => a + g.value, 0))}`, "ok"); closeSheet();
    topSheet() && topSheet()._redraw && topSheet()._redraw();
  },
  "adm-keys-go": async el => {
    const s = topSheet();
    await post(`admin/user/${el.dataset.id}/keys`, { cid: s.querySelector("#ak-cid").value, n: Math.max(1, +s.querySelector("#ak-n").value || 1) });
    H.ok(); toast("Ключи выданы", "ok"); closeSheet(); CASES = [];
  },
  "adm-odds": async el => {
    const inp = topSheet().querySelector(`.adm-oi[data-k="${el.dataset.k}"]`), v = parseFloat(inp.value.replace(",", "."));
    if (!(v > 0)) return toast("Введи число, например 95");
    if (v > 100 && !await confirmM("Больше 100%?", `При ${v}% игроки на дистанции выигрывают больше, чем ставят: банк будет терять звёзды на каждой ставке, а самые хитрые смогут фармить звёзды без риска. Точно ставим?`, "Да, ставим")) return;
    await post("admin/odds", { key: el.dataset.k, value: v / 100 }); H.ok(); toast("Сохранено", "ok"); await loadMe(); admRender();
  },
  "adm-cname": async el => {
    const row = topSheet().querySelector(`.adm-odd[data-cid="${el.dataset.cid}"]`), v = k => row.querySelector(`.adm-cn[data-k="${k}"]`).value;
    await post("admin/cases/name", { cid: el.dataset.cid, title: v("title"), who: v("who"), ids: v("ids") }); H.ok(); toast("Сохранено", "ok"); CASES = []; admRender();
  },
  "adm-ccover": async el => {
    const cid = el.dataset.cid, row = topSheet().querySelector(`.adm-odd[data-cid="${cid}"]`), v = k => row.querySelector(`.adm-cc[data-k="${k}"]`).value;
    await post("admin/cases/cover", { cid, cover: v("cover"), img: ADM_CIMG[cid] || "", who: v("who"), ids: v("ids") }); H.ok(); toast("Обложка сохранена", "ok"); CASES = []; admRender();
  },
  "adm-ccover-rs": async el => { await post("admin/cases/cover", { cid: el.dataset.cid, cover: "" }); H.ok(); toast("Оригинальная обложка", "ok"); CASES = []; admRender(); },
  "adm-cname-rs": async el => { await post("admin/cases/name", { cid: el.dataset.cid, title: "" }); H.ok(); toast("Настоящее название", "ok"); CASES = []; admRender(); },
  "adm-pay": async el => {
    const k = el.dataset.k, inp = topSheet().querySelector(`.adm-oi[data-k="${k}"]`), v = parseFloat(inp.value.replace(",", ".").replace(/\s/g, ""));
    if (!(v >= 0)) return toast("Введи число");
    await post("admin/pay", { [k]: k === "fee" || k === "fee_addr" ? v / 100 : Math.round(v) }); H.ok(); toast("Сохранено", "ok"); admRender();
  },
  "adm-shop": async el => {
    const on = el.dataset.v === "1";
    await post("admin/shop", { what: el.dataset.k, on }); H.ok(); toast(on ? "Продажа включена" : "Продажа выключена", "ok"); SHOP = null; if (typeof PREM !== "undefined") PREM = null; admRender();
  },
  "adm-pay-rs": async el => { await post("admin/pay", { [el.dataset.k]: null }); H.ok(); toast("Сброшено", "ok"); admRender(); },
  "adm-pay-on": async el => {
    const on = el.dataset.v === "1";
    if (!on && !await confirmM("Выключить переводы?", "Игроки не смогут переводить звёзды друг другу, пока не включишь обратно.", "Выключить")) return;
    await post("admin/pay", { on }); H.ok(); toast(on ? "Переводы включены" : "Переводы выключены", "ok"); admRender();
  },
  "adm-pay-inline": async el => {
    const on = el.dataset.v === "1";
    await post("admin/pay", { inline_on: on }); H.ok(); toast(on ? "Инлайн-чеки включены" : "Инлайн-чеки выключены", "ok"); admRender();
  },
  "adm-mb": async el => {
    const k = el.dataset.k, v = +topSheet().querySelector(`select[data-mb="${k}"]`).value;
    if (!await confirmM(k === "pay" ? "Сменить бота для оплат?" : "Сменить лицо игры?", k === "pay" ? "Новые счета Stars будут выставляться через выбранного бота — выручка пойдёт на его баланс." : "Новые ссылки в игре поведут на выбранного бота.", "Сменить")) return;
    await post("admin/franchise/main", { [k]: v }); H.ok(); toast("Сохранено", "ok"); admRender();
  },
  "adm-frc-sw": async el => {
    const on = el.dataset.v === "1";
    await post("admin/franchise/cfg", { [el.dataset.k]: on }); H.ok(); toast(on ? "Включено" : "Выключено", "ok"); admRender();
  },
  "adm-frc": async el => {
    const k = el.dataset.k, v = topSheet().querySelector(`.adm-oi[data-k="${k}"]`).value;
    await post("admin/franchise/cfg", { [k]: v }); H.ok(); toast("Сохранено", "ok"); admRender();
  },
  "adm-frc-rs": async el => { await post("admin/franchise/cfg", { [el.dataset.k]: null }); H.ok(); toast("Вернули по умолчанию", "ok"); admRender(); },
  "adm-frc-ann": async el => {
    if (!await confirmM("Разослать всем?", `Сообщение о франшизе получат ${fmt(+el.dataset.n)} игроков. Отменить отправку будет нельзя.`, "Разослать")) return;
    el.disabled = true;
    try { const r = await post("admin/franchise/announce"); H.ok(); toast(`Отправляем ${fmt(r.total)} игрокам`, "ok"); admRender(); }
    finally { el.disabled = false; }
  },
  "adm-frc-promo": async el => {
    if (!await confirmM("Разослать предложение?", "Получат активные игроки нужного уровня с включёнными уведомлениями, кому ещё не отправляли (или давно).", "Разослать")) return;
    el.disabled = true;
    try { const r = await post("admin/franchise/promo"); H.ok(); toast(`Отправляем ${fmt(r.total)} игрокам`, "ok"); admRender(); }
    finally { el.disabled = false; }
  },
  "adm-ev-sw": async el => { const on = el.dataset.v === "1"; await post("admin/flash", { [el.dataset.k]: on }); H.ok(); toast(on ? "Включено" : "Выключено", "ok"); admRender(); },
  "adm-ev": async el => { const k = el.dataset.k; await post("admin/flash", { [k]: topSheet().querySelector(`.adm-oi[data-k="${k}"]`).value }); H.ok(); toast("Сохранено", "ok"); admRender(); },
  "adm-ev-rs": async el => { await post("admin/flash", { [el.dataset.k]: null }); H.ok(); toast("Вернули по умолчанию", "ok"); admRender(); },
  "adm-ev-go": async el => {
    if (!await confirmM("Запустить ивент сейчас?", "Бот предупредит игроков (если включено).", "Запустить")) return;
    await post("admin/flash/start", { kind: el.dataset.k }); H.ok(); toast("Ивент запущен", "ok"); admRender(); loadMe();
  },
  "adm-fee": async el => { const k = el.dataset.k; await post("admin/fees", { [k]: topSheet().querySelector(`.adm-oi[data-k="${k}"]`).value }); H.ok(); toast("Сохранено", "ok"); admRender(); loadMe(); },
  "adm-fee-rs": async el => { await post("admin/fees", { [el.dataset.k]: null }); H.ok(); toast("Вернули по умолчанию", "ok"); admRender(); loadMe(); },
  "adm-ev-stop": async () => { if (!await confirmM("Остановить ивент?", "Он закончится сразу.", "Остановить")) return; await post("admin/flash/stop"); H.ok(); toast("Остановлен", "ok"); admRender(); loadMe(); },
  "adm-ref-sw": async el => { const on = el.dataset.v === "1"; await post("admin/refs", { [el.dataset.k]: on }); H.ok(); toast(on ? "Включено" : "Выключено", "ok"); admRender(); },
  "adm-ref": async el => {
    const k = el.dataset.k, v = topSheet().querySelector(`.adm-oi[data-k="${k}"]`).value;
    await post("admin/refs", { [k]: v }); H.ok(); toast("Сохранено", "ok"); admRender();
  },
  "adm-gw-ch": async () => {
    const v = topSheet().querySelector('[data-gw="channel"]').value.trim(); if (!v) return toast("Укажи канал");
    const r = await post("admin/gw/channel", { channel: v }); H.ok(); toast("Канал подключён: " + (r.title || r.channel), "ok"); admRender();
  },
  "adm-gw-new": async el => {
    const f = k => topSheet().querySelector(`[data-gw="${k}"]`).value.trim();
    const b = { title: f("title"), prize: f("prize"), winners: f("winners"), hours: f("hours"), minLevel: f("minLevel") };
    if (!b.title) return toast("Введи название");
    if (!await confirmM("Опубликовать розыгрыш?", `«${b.title}»: ⭐ ${fmt(+b.prize)} на ${b.winners}, итоги через ${b.hours} ч. Пост сразу появится в канале.`, "Опубликовать")) return;
    el.disabled = true;
    try { await post("admin/gw", b); H.ok(); toast("Опубликовано", "ok"); admRender(); } finally { el.disabled = false; }
  },
  "adm-gw-open": el => openGw(+el.dataset.id),
  "adm-gw-cancel": async el => {
    if (!await confirmM("Отменить розыгрыш?", "Призы не выплатятся. Пост в канале останется, удали его вручную.", "Отменить")) return;
    await post(`admin/gw/${el.dataset.id}/cancel`); H.ok(); toast("Отменён", "ok"); admRender();
  },
  "adm-ref-rs": async el => { await post("admin/refs", { [el.dataset.k]: null }); H.ok(); toast("Вернули по умолчанию", "ok"); admRender(); },
  "adm-fr": async el => {
    const on = el.dataset.v === "1";
    if (!on && !await confirmM("Отключить бота?", "Его игроки не смогут войти через него — только через главного бота (аккаунт тот же).", "Отключить")) return;
    await post("admin/franchise/" + el.dataset.id, { on }); H.ok(); toast(on ? "Бот включён" : "Бот отключён", "ok"); admRender();
  },
  "adm-db-exp": async el => {
    el.disabled = true;
    try { const r = await post("admin/db/export"); H.ok(); toast(`Бот прислал базу: ${fmt(r.users)} игроков, ${fmt(r.kb)} КБ`, "ok"); }
    finally { el.disabled = false; }
  },
  "adm-odds-all": async () => {
    const v = parseFloat(topSheet().querySelector("#adm-oall-n").value.replace(",", "."));
    if (!(v >= 50 && v <= 150)) return toast("От 50 до 150%");
    if (!await confirmM("Всем играм?", `Поставить возврат ${v}% сразу во всех играх? Свои значения у отдельных игр перезапишутся.`, "Да, всем")) return;
    if (v > 100 && !await confirmM("Больше 100%?", `При ${v}% игроки на дистанции выигрывают больше, чем ставят — во ВСЕХ играх: банк будет терять звёзды на каждой ставке, а самые хитрые смогут фармить звёзды без риска. Точно ставим?`, "Да, ставим")) return;
    await post("admin/odds/all", { value: v / 100 }); H.ok(); toast("Сохранено для всех игр", "ok"); await loadMe(); admRender();
  },
  "adm-odds-all-rs": async () => {
    if (!await confirmM("Сбросить все?", "Все игры вернутся к значениям по умолчанию из settings.toml.", "Сбросить")) return;
    await post("admin/odds/all", { value: null }); H.ok(); toast("Сброшено", "ok"); await loadMe(); admRender();
  },
  "adm-odds-rs": async el => {
    if (!await confirmM("Сбросить?", `${esc(el.dataset.n)}: вернуть значение по умолчанию из settings.toml.`, "Сбросить")) return;
    await post("admin/odds", { key: el.dataset.k, value: null }); H.ok(); toast("Сброшено", "ok"); await loadMe(); admRender();
  },
  "adm-alog-keep": async () => {
    await post("admin/log/cfg", { keep_days: topSheet().querySelector("#adm-alog-keep").value }); H.ok(); toast("Сохранено", "ok"); admRender();
  },
  "adm-alog-clear": async () => {
    if (!await confirmM("Очистить админский журнал?", "Все записи о действиях админов будут удалены. Отменить нельзя.", "Очистить")) return;
    await post("admin/log/clear", {}); H.ok(); toast("Журнал очищен", "ok"); admRender();
  },
  "adm-actlog-on": async el => {
    const on = el.dataset.v === "1"; await post("admin/actlog/cfg", { on }); H.ok(); toast(on ? "Запись включена" : "Запись выключена", "ok"); admRender();
  },
  "adm-actlog-keep": async () => {
    await post("admin/actlog/cfg", { keep_days: topSheet().querySelector("#adm-actlog-keep").value }); H.ok(); toast("Сохранено", "ok"); admRender();
  },
  "adm-actlog-clear": async () => {
    if (!await confirmM("Очистить подробный журнал?", "Все записи действий игроков будут удалены. Отменить нельзя.", "Очистить")) return;
    await post("admin/actlog/clear", {}); H.ok(); toast("Журнал очищен", "ok"); admRender();
  },
  "adm-tab": el => { ADM.tab = el.dataset.v; H.sel(); const s = topSheet(); s.querySelectorAll("#adm-seg button").forEach(b => b.classList.toggle("on", b === el)); s.querySelector("#adm-body").innerHTML = emptyHTML("hourglass", "Загружаем…"); admRender(s); },
  "adm-sort": el => { ADM.sort = el.dataset.v; H.sel(); admRender(); },
  "adm-user": el => openAdmUser(+el.dataset.id),
  "adm-stars": async el => {
    const sign = +el.dataset.v;
    const v = await promptM(sign > 0 ? "Начислить звёзды" : "Списать звёзды", "Сумма в звёздах. Действие попадёт в журнал.", "1000", sign > 0 ? "Начислить" : "Списать");
    if (v == null || !(Math.floor(+v) > 0)) return;
    const amt = Math.floor(+v), b = +(el.dataset.b || 0), neg = sign < 0 && amt > b;
    if (neg && !await confirmM("Списать в минус?", `У игрока ⭐ ${fmt(b)}, баланс станет <b class="tl">⭐ ${fmt(b - amt)}</b>.
      Пока долг не погашен, он не сможет ставить и переводить звёзды. Доход бизнесов, бонусы и продажа подарков пойдут в погашение.`, "Списать в минус")) return;
    await post(`admin/user/${el.dataset.id}/stars`, { delta: sign * amt, neg }); H.ok(); toast("Готово", "ok");
    if (+el.dataset.id === ME.id) loadMe();
    topSheet()._redraw && topSheet()._redraw();
  },
  "adm-grant": async el => {
    const on = el.dataset.v === "1";
    if (!await confirmM(on ? "Сделать админом?" : "Снять админку?", on ? `${esc(el.dataset.n)} получит админ-панель: начислять и списывать звёзды, банить, выдавать подарки и кейсы, делать рассылки. Все действия пишутся в журнал. Выдавать админку дальше сможешь только ты.` : `${esc(el.dataset.n)} потеряет доступ к админ-панели.`, on ? "Выдать" : "Снять")) return;
    await post(`admin/user/${el.dataset.id}/admin`, { on }); H.ok(); toast(on ? "Админка выдана" : "Админка снята", "ok");
    topSheet()._redraw && topSheet()._redraw();
  },
  "adm-addr": async el => {
    const anon = el.dataset.k === "anon";
    let value = "";
    if (el.dataset.m === "own") {
      value = await promptM(anon ? "Свой анонимный адрес" : "Свой адрес кошелька",
        "Любой адрес из латинских букв и цифр, от 3 до 32 знаков — встанет ровно так, как напишешь (например DUROV777 или NPKING). Регистр не важен, пробелы и дефисы уберутся.", "", "Поставить", "text");
      if (value == null || !value.trim()) return;
    } else if (!await confirmM("Новый адрес?", `Игроку выдадим случайный ${anon ? "анонимный " : ""}адрес. Старый перестанет принимать переводы. Отменить можно в журнале.`, "Сменить")) return;
    const r = await post(`admin/user/${el.dataset.id}/addr`, { kind: anon ? "anon" : "main", value }); H.ok(); toast("Адрес: " + r.addr, "ok");
    topSheet()._redraw && topSheet()._redraw();
  },
  "adm-freeze": async el => {
    const on = el.dataset.v === "1";
    let reason = "";
    if (on) {
      reason = await promptM("Заморозить кошелёк?", "Игрок сможет играть, но не сможет переводить звёзды, отправлять подарки, торговать на маркете, меняться и играть против других игроков. Причина (видна игроку, можно пусто):", "", "Заморозить", "text");
      if (reason == null) return;
    }
    await post(`admin/user/${el.dataset.id}/freeze`, { on, reason }); H.ok(); toast(on ? "Кошелёк заморожен" : "Кошелёк разморожен", "ok");
    topSheet()._redraw && topSheet()._redraw();
  },
  "adm-ban": async el => {
    const on = el.dataset.v === "1";
    if (on && !await confirmM("Заблокировать игрока?", "Он не сможет пользоваться игрой, пока не разбаните.", "Заблокировать")) return;
    await post(`admin/user/${el.dataset.id}/ban`, { ban: on }); H.ok(); toast(on ? "Заблокирован" : "Разблокирован", "ok");
    topSheet()._redraw && topSheet()._redraw();
  },
  "adm-bcs-add": async () => {
    const s = topSheet(), text = s.querySelector("#adm-bcs").value.trim(), every = +s.querySelector("#adm-bcs-e").value, time = s.querySelector("#adm-bcs-t").value;
    if (!text) return toast("Напиши текст");
    if (!/^\d{2}:\d{2}$/.test(time)) return toast("Укажи время");
    await post("admin/broadcast/sched", { action: "add", text, every, time }); H.ok(); toast("Регулярная рассылка добавлена", "ok"); admRender();
  },
  "adm-bcs": async el => {
    const a = el.dataset.a;
    if (a === "del" && !await confirmM("Удалить рассылку?", "Она больше не будет отправляться.", "Удалить")) return;
    if (a === "now" && !await confirmM("Отправить сейчас?", "Текст уйдёт игрокам прямо сейчас (расписание не сдвинется).", "Отправить")) return;
    await post("admin/broadcast/sched", { action: a, id: +el.dataset.id }); H.ok();
    toast({ del: "Удалено", now: "Рассылка запущена", toggle: "Готово" }[a], "ok"); admRender();
  },
  "adm-bc": async () => {
    const text = topSheet().querySelector("#adm-bc").value.trim();
    if (!text) return toast("Напиши текст");
    if (!await confirmM("Разослать всем?", "Сообщение уйдёт всем игрокам от бота.", "Отправить")) return;
    const r = await post("admin/broadcast", { text }); H.ok(); toast(`Рассылка запущена: ${r.total} игроков`, "ok");
    setTimeout(() => admRender(), 1500);
  },
});

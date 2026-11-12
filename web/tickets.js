//  Тикеты поддержки (tickets.py): профиль → «Поддержка» — список, новый тикет, переписка.
//  Админам — вкладка «Тикеты» в админке; из бота открывается по ?ticket=ID (игрок) / ?aticket=ID (админ).
ICONS.support = '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4"/><path d="m4.9 4.9 4.3 4.3M14.8 14.8l4.3 4.3M14.8 9.2l4.3-4.3M4.9 19.1l4.3-4.3"/>';
const TK_ST = { open: ["ждёт ответа", "y"], answered: ["есть ответ", "g"], closed: ["закрыт", ""] };
const tkTime = ts => new Date(ts * 1000).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const tkText = s => esc(s).replace(/\n/g, "<br>");
const tkMsgs = (msgs, staffView) => `<div class="tk-thread">${msgs.map(m => `<div class="tk-msg${m.staff ? " staff" : ""}">
  <div class="tk-who">${m.staff ? (staffView && m.by ? `${ic("crown")}${esc(m.by)}` : `${ic("support")}Поддержка`) : (staffView ? "Игрок" : "Ты")}<span>${tkTime(m.ts)}</span></div>
  <div class="tk-body">${tkText(m.text)}</div></div>`).join("")}</div>`;
const tkPill = st => `<span class="tk-st ${TK_ST[st][1]}">${TK_ST[st][0]}</span>`;

async function openTickets() {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "tk-s");
  el._tk = true;
  await tkList(el);
}
async function tkList(el) {
  const d = await api("tickets").catch(() => null); if (!d || !el.isConnected) return;
  const open = d.items.filter(t => t.status !== "closed").length;
  replaceSheet(el, `<div class="inv-hero"><span class="tk-ic">${ic("support")}</span><h2>Поддержка</h2>
      <p>${ME.shopOn ? "Проблема с оплатой, баг" : "Баг"}, пропали звёзды или подарок — напиши, ответим здесь и в боте.</p></div>
    <button class="btn gold" data-act="tk-new"${open >= d.maxOpen ? " disabled" : ""}>${ic("plus")}Новое обращение</button>
    ${open >= d.maxOpen ? `<div class="hint" style="font-size:12px;text-align:center;margin-top:6px">Открыто ${open} — дождись ответа или закрой старое</div>` : ""}
    ${d.items.length ? `<div class="sec-t">Мои обращения</div><div class="box">${d.items.map(t => `<div class="row tap" data-act="tk-open" data-id="${t.id}">
      <div class="grow" style="min-width:0"><div class="t">#${t.id} · ${esc(t.topicTitle)} ${tkPill(t.status)}${t.unread ? ` <span class="tk-new">новый ответ</span>` : ""}</div>
      <div class="s tk-last">${t.lastStaff ? "Поддержка: " : ""}${esc(t.last)}</div></div><span class="hint" style="font-size:11px">${tkTime(t.updated)}</span></div>`).join("")}</div>`
      : `<div style="margin-top:14px">${emptyHTML("support", "Обращений пока нет")}</div>`}
    <div class="disc">Не пиши в тикет пароли и PIN-код кошелька — поддержка их никогда не спрашивает.</div>`);
  el._topics = d.topics;
}
function tkNew() {
  const topics = (topSheet()._topics) || { other: "Другое" };
  const el = openSheet(`<h2 class="gtitle">Обращение</h2>
    <div class="sec-t">Тема</div><div class="tk-topics">${Object.entries(topics).map(([k, t], i) => `<button data-act="tk-topic" data-v="${k}" class="${i ? "" : "on"}">${esc(t)}</button>`).join("")}</div>
    <div class="sec-t">Что случилось</div>
    <textarea id="tk-t" rows="6" maxlength="2000" placeholder="Опиши подробно: что делал, что ожидал, что получилось."></textarea>
    <button class="btn gold" data-act="tk-send" style="margin-top:10px">${ic("send")}Отправить</button>`);
  el._topic = Object.keys(topics)[0];
  setTimeout(() => { const t = el.querySelector("#tk-t"); if (t) t.focus(); }, 400);
}
async function tkOpen(id, el) {
  el = el || openSheet(emptyHTML("hourglass", "Загружаем…"), "tk-s");
  const t = await api("tickets/" + id).catch(() => null); if (!t || !el.isConnected) return;
  el._tkid = id;
  replaceSheet(el, `<h2 class="gtitle">#${t.id} · ${esc(t.topicTitle)}</h2>
    <div style="text-align:center;margin:-6px 0 10px">${tkPill(t.status)}</div>
    ${tkMsgs(t.msgs, false)}
    ${t.status === "closed" ? `<div class="disc">Обращение закрыто. Если вопрос остался — создай новое.</div>`
      : `<textarea id="tk-r" rows="3" maxlength="2000" placeholder="Сообщение…"></textarea>
         <div class="btns"><button class="btn ghost" data-act="tk-close">Вопрос решён</button><button class="btn gold" data-act="tk-msg">${ic("send")}Отправить</button></div>`}`);
  const th = el.querySelector(".tk-thread"); if (th) th.scrollTop = th.scrollHeight;
  if (t.unread !== undefined) loadMe().catch(() => {});
}
const tkRefreshList = () => { const s = SHEETS.find(x => x._tk); if (s) tkList(s); };

// ---------------- админка: вкладка «Тикеты» ----------------
let TK_ADM = "open";
async function admTickets(body) {
  const d = await api("admin/tickets?status=" + TK_ADM), c = d.counts || {};
  body.innerHTML = `<div class="seg">${[["open", "Ждут ответа"], ["answered", "Ответили"], ["closed", "Закрытые"]].map(([k, t]) =>
      `<button data-act="tk-adm-f" data-v="${k}" class="${TK_ADM === k ? "on" : ""}">${t}${c[k] ? ` · ${c[k]}` : ""}</button>`).join("")}</div>
    <div class="box">${d.items.map(t => `<div class="row tap" data-act="tk-adm-open" data-id="${t.id}">${avaHTML(t.user, 34)}
      <div class="grow" style="min-width:0"><div class="t">${esc(t.user.name)} · #${t.id} · ${esc(t.topicTitle)}</div>
      <div class="s tk-last">${t.lastStaff ? "↩ " : ""}${esc(t.last)}</div></div><span class="hint" style="font-size:11px">${tkTime(t.updated)}</span></div>`).join("")
      || `<div class="hint" style="padding:14px">${TK_ADM === "open" ? "Все обращения отвечены 👍" : "Пусто"}</div>`}</div>
    <div class="disc">Новые тикеты и каждое сообщение игрока приходят всем админам в бота. Игрок видит ответ от «Поддержки», без имени админа. Отвеченные тикеты без ответа игрока закрываются сами через 3 дня.</div>`;
}
async function tkAdmOpen(id, el) {
  el = el || openSheet(emptyHTML("hourglass", "Загружаем…"), "tk-s");
  const t = await api("admin/tickets/" + id).catch(() => null); if (!t || !el.isConnected) return;
  el._tkadm = id;
  replaceSheet(el, `<h2 class="gtitle">#${t.id} · ${esc(t.topicTitle)}</h2>
    <div class="box"><div class="row tap" data-act="adm-user" data-id="${t.user.id}">${avaHTML(t.user, 36)}<div class="grow"><div class="t">${esc(t.user.name)}${t.user.banned ? ` <span class="tk-st">бан</span>` : ""}</div>
      <div class="s">id ${t.user.id} · ⭐ ${fmt(t.user.stars)}${t.others ? ` · ещё обращений: ${t.others}` : ""}</div></div>${tkPill(t.status)}</div></div>
    ${tkMsgs(t.msgs, true)}
    <textarea id="tk-ar" rows="3" maxlength="2000" placeholder="Ответ игроку…"></textarea>
    <div class="btns">${t.status === "closed" ? `<button class="btn ghost" data-act="tk-adm-st" data-v="open">Открыть снова</button>` : `<button class="btn ghost" data-act="tk-adm-st" data-v="closed">Закрыть</button>`}
      <button class="btn gold" data-act="tk-adm-reply">${ic("send")}Ответить</button></div>`);
  const th = el.querySelector(".tk-thread"); if (th) th.scrollTop = th.scrollHeight;
}

Object.assign(ACT, {
  support: () => openTickets(),
  "tk-new": () => tkNew(),
  "tk-topic": el => { topSheet()._topic = el.dataset.v; el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); H.sel(); },
  "tk-send": async el => {
    const s = topSheet(), t = s.querySelector("#tk-t").value.trim();
    if (t.length < 3) return toast("Напиши, что случилось");
    el.disabled = true;
    try { const r = await post("tickets", { topic: s._topic, text: t }); H.ok(); toast("Отправлено — ответим здесь и в боте", "ok"); closeSheet(); tkRefreshList(); tkOpen(r.id); }
    finally { el.disabled = false; }
  },
  "tk-open": el => tkOpen(+el.dataset.id),
  "tk-msg": async el => {
    const s = topSheet(), t = s.querySelector("#tk-r").value.trim();
    if (t.length < 3) return toast("Напиши сообщение");
    el.disabled = true;
    try { await post(`tickets/${s._tkid}/msg`, { text: t }); H.ok(); await tkOpen(s._tkid, s); tkRefreshList(); } finally { el.disabled = false; }
  },
  "tk-close": async () => {
    const s = topSheet(); if (!await confirmM("Закрыть обращение?", "Если вопрос снова появится — создай новое.", "Закрыть")) return;
    await post(`tickets/${s._tkid}/close`); H.ok(); await tkOpen(s._tkid, s); tkRefreshList();
  },
  "tk-adm-f": el => { TK_ADM = el.dataset.v; H.sel(); admRender(); },
  "tk-adm-open": el => tkAdmOpen(+el.dataset.id),
  "tk-adm-reply": async el => {
    const s = topSheet(), t = s.querySelector("#tk-ar").value.trim();
    if (t.length < 3) return toast("Напиши ответ");
    el.disabled = true;
    try { await post(`admin/tickets/${s._tkadm}/reply`, { text: t }); H.ok(); toast("Ответ отправлен игроку", "ok"); await tkAdmOpen(s._tkadm, s); }
    finally { el.disabled = false; }
    const a = SHEETS.find(x => x._adm); if (a) admRender(a);
  },
  "tk-adm-st": async el => {
    const s = topSheet(); await post(`admin/tickets/${s._tkadm}/status`, { status: el.dataset.v }); H.ok(); await tkAdmOpen(s._tkadm, s);
    const a = SHEETS.find(x => x._adm); if (a) admRender(a);
  },
});

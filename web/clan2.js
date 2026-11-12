"use strict";
// ============================================================
//  Кланы: чат клана, уровни 6–10 с перками, клановое оформление
//  (тег рядом с ником во всех списках, цветной с 3 ур., сияющий с 8; рамка аватара с 5 ур., золотая с 10)
// ============================================================
ICONS.chat = '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/><path d="M8.5 12h.01M12 12h.01M15.5 12h.01"/>';
ICONS.trash = '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>';
const clanCol = u => CLAN_COLORS[(u.clanc || 0) % CLAN_COLORS.length];
const tagCls = l => (l >= 3 ? " c" : "") + (l >= 8 ? " glow" : "");

// тег клана рядом с именем
function tagHTML(u) {
  if (!u || !u.clan) return "";
  const [a, b] = clanCol(u);
  return `<span class="ntag${tagCls(u.clanl || 1)}" style="--a:${a};--b:${b}">${esc(u.clan)}</span>`;
}
const _nmCl = nameHTML;
nameHTML = function (u) { return _nmCl(u) + tagHTML(u); };

// тег в шапке профиля — в цветах клана
const _phCl = profileHTML;
profileHTML = function (p, tab) {
  const h = _phCl(p, tab);
  if (!p.clan || (p.clanl || 1) < 3) return h;
  const [a, b] = clanCol(p);
  return h.replace('<span class="ctag"', `<span class="ctag${tagCls(p.clanl)}" style="--a:${a};--b:${b}"`);
};

// клановая рамка — если нет сезонной, купленной и VIP
const _avCl = avaHTML;
avaHTML = function (u, s, o) {
  if (!u || u.frame || u.pframe || u.vip || !(u.clanl >= 5)) return _avCl(u, s, o);
  const [a, b] = clanCol(u);
  return _avCl({ ...u, frame: u.clanl >= 10 ? "clang" : "clan" }, s, o).replace('style="', `style="--ca:${a};--cb:${b};`);
};

// ---------------- чат клана ----------------
async function openClanChat() {
  H.imp("light");
  const el = openSheet(`<h2 class="gtitle">${ic("chat")}Чат клана</h2>
    <div class="cc-list" id="cc-list">${emptyHTML("hourglass", "Загружаем…")}</div>
    <div class="cc-in"><textarea id="cc-in" rows="1" maxlength="300" placeholder="Сообщение клану" enterkeyhint="send"></textarea>
      <button class="cc-send" data-act="cc-send">${ic("send")}</button></div>`, "cc-s");
  el._cc = { last: 0, users: {}, role: null };
  const inp = el.querySelector("#cc-in");
  inp.onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ACT["cc-send"](); } };
  inp.oninput = () => { inp.style.height = "auto"; inp.style.height = Math.min(inp.scrollHeight, 96) + "px"; };
  await ccPull(el, true);
  const t = setInterval(() => {
    if (!el.isConnected || !SHEETS.includes(el) || el._cc.dead) return clearInterval(t);
    if (!document.hidden) ccPull(el);
  }, 3000);
}
async function ccPull(el, first) {
  const st = el._cc;
  if (st.busy) { st.again = true; return; }
  st.busy = true;
  try {
    const r = await api("clanchat?after=" + st.last);
    Object.assign(st.users, r.users); st.role = r.role;
    const box = el.querySelector("#cc-list"); if (!box) return;
    if (first || r.msgs.length) {
      const near = first || box.scrollHeight - box.scrollTop - box.clientHeight < 90;
      if (first) box.innerHTML = r.msgs.length ? "" : `<div class="empty" data-i="users"><span class="eic">${ic("chat")}</span><span class="etx"><b>Тут пока тихо</b>Напиши первым — увидит весь клан</span></div>`;
      else if (r.msgs.length) box.querySelector(".cc-empty")?.remove();
      box.insertAdjacentHTML("beforeend", r.msgs.map(m => ccMsg(m, st)).join(""));
      if (r.msgs.length) st.last = r.msgs[r.msgs.length - 1].id;
      if (near) box.scrollTop = box.scrollHeight;
    }
    if (ME.clanChat) { ME.clanChat = 0; }
  } catch (e) { st.dead = true; if (first) closeSheet(); }
  finally { st.busy = false; if (st.again) { st.again = false; ccPull(el); } }
}
function ccSysTxt(m, u) {
  if (m.kind === "win") {
    const [g, x] = String(m.data).split("|");
    return `${ic("trophy")}<span>${u ? `<b>${esc(u.name)}</b>` : "Участник"} · ${esc(g)} · <b class="tw">+⭐ ${fmt(+x)}</b></span>`;
  }
  return `${ic("activity")}<span>${clanFeedTxt({ kind: m.kind, data: m.data, user: u || null })}</span>`;
}
function ccMsg(m, st) {
  const u = st.users[m.u] || null;
  if (m.kind) { st.prev = 0; return `<div class="cc-sys${m.kind === "win" ? " win" : ""}" data-mid="${m.id}">${ccSysTxt(m, u)}</div>`; }
  const v = u || { id: m.u, name: "Игрок" }, mine = m.u === ME.id, cont = st.prev === m.u && m.ts - st.prevTs < 300;
  st.prev = m.u; st.prevTs = m.ts;
  return `<div class="cc-m${mine ? " me" : ""}${cont ? " cont" : ""}" data-mid="${m.id}">
    ${mine ? "" : `<span class="cc-ava"${cont ? "" : ` data-act="profile" data-id="${v.id}"`}>${cont ? "" : avaHTML(v, 30)}</span>`}
    <div class="cc-b" data-act="cc-msg" data-id="${m.id}" data-u="${m.u}">${!mine && !cont ? `<div class="cc-n">${nameHTML(v)}</div>` : ""}<div class="cc-t">${esc(m.text)}</div><span class="cc-ts">${hhmm(m.ts)}</span></div></div>`;
}
Object.assign(ACT, {
  "clan-chat": () => openClanChat(),
  "cc-send": async () => {
    const el = SHEETS.find(s => s._cc); if (!el) return;
    const inp = el.querySelector("#cc-in"), text = inp.value.trim(); if (!text) return;
    inp.value = ""; inp.style.height = "auto"; inp.focus();
    try { await post("clanchat", { text }); H.sel(); await ccPull(el); } catch (e) { if (!inp.value) inp.value = text; }
  },
  "cc-msg": async el => {
    const s = SHEETS.find(x => x._cc); if (!s) return;
    const own = +el.dataset.u === ME.id, staff = s._cc.role === "owner" || s._cc.role === "officer";
    if (!own && !staff) return;
    if (!await confirmM("Удалить сообщение?", own ? "Его больше никто не увидит." : "Сообщение участника исчезнет из чата у всех.", "Удалить")) return;
    await post("clanchat/del/" + el.dataset.id); H.ok();
    s.querySelector(`[data-mid="${el.dataset.id}"]`)?.remove();
  },
});

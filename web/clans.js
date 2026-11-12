"use strict";
// ============================================================ кланы: вкладка «Кланы» в топе, карточка клана, битва недели
const CLAN_COLORS = [["#4aa8ff", "#163a6b"], ["#ff5f8f", "#5a1030"], ["#35d07f", "#0d4429"], ["#ffc53d", "#5a3a00"],
  ["#a77bff", "#33155e"], ["#ff8a3d", "#5a2408"], ["#3fd6ff", "#0a3c5c"], ["#e0e0ea", "#33333d"]];
let CL = null;
TOPK.unshift(["clans", "users", "Кланы"]);   // кланы — первой кнопкой в топе
const clanBadge = c => { const [a, b] = CLAN_COLORS[c.color % CLAN_COLORS.length]; return `<span class="clbadge${c.level >= 8 ? " glow" : ""}" style="--a:${a};--b:${b}">${esc(c.tag)}</span>`; };
const clanHours = s => { s = Math.max(0, s); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600); return d ? `${d} д ${h} ч` : `${h} ч`; };

const _rtC = renderTop;
renderTop = async function () {
  if (topKind !== "clans") return _rtC();
  const v = $("#v-top");
  v.innerHTML = `${topNavHTML()}
    <div id="cl-body">${emptyHTML("hourglass", "Загружаем…")}</div>`;
  CL = await api("clans");
  if (TAB !== "top" || topKind !== "clans") return;
  const mine = CL.mine && CL.list.find(c => c.id === CL.mine);
  const left = CL.weekEnds - Date.now() / 1000;
  let h = mine ? `<div class="clme" data-act="clan" data-id="${mine.id}">
      <div class="clme-h">${clanBadge(mine)}<div class="grow"><b>${esc(mine.name)}</b><span>${mine.members}/${mine.slots} · ${mine.place} место на неделе</span></div>${ME.clanChat ? `<em class="clunread">${ME.clanChat}</em>` : ""}${ic("chev")}</div>
      <div class="clme-lv"><div><span>Уровень ${mine.level}${mine.bonus ? ` · +${mine.bonus}% к доходу` : ""}</span><span>${mine.next ? `⭐ ${short(mine.treasury)} / ${short(mine.next)}` : "максимум"}</span></div>
        <i style="--p:${mine.next ? Math.min(100, mine.treasury / mine.next * 100) : 100}%"></i></div></div>`
    : `<div class="clnone"><span class="pic b">${ic("users")}</span><div class="grow"><b>Ты пока без клана</b><span>Вступи в клан или создай свой — бонус к доходу и призы битвы</span></div>
      <button class="btn sm gold" data-act="clan-new">Создать</button></div>`;
  h += `<div class="timer">${ic("flame")}Битва кланов: оборот в играх за неделю · итоги через ${clanHours(left)} · призы ⭐ ${CL.prizes.map(short).join(" / ")}</div>`;
  h += `<div id="cl-rec"></div>`;
  h += CL.list.length ? `<div class="box">${CL.list.map(c => `<div class="row tap" data-act="clan" data-id="${c.id}"><span class="place${c.place <= 3 ? " p" + c.place : ""}">${c.place}</span>${clanBadge(c)}
      <div class="grow"><div class="t">${esc(c.name)}${c.open ? "" : ` <span class="cllock">${ic("lock")}</span>`}</div><div class="s">${c.members}/${c.slots} · ур. ${c.level}</div></div>${c.emblem ? `<img class="spi" style="width:30px;height:30px;margin:0" src="${A.orig(c.emblem, 64)}" alt="">` : ""}<b class="num">⭐ ${short(c.score)}</b></div>`).join("")}</div>`
    : emptyHTML("users", "Кланов пока нет — создай первый");
  if (CL.last && CL.last.length) h += `<div class="disc">Прошлая неделя: ${CL.last.map(x => `${x.place}. [${esc(x.tag)}] ${esc(x.name)}`).join(" · ")}</div>`;
  h += `<button class="ideabtn" data-act="idea">${ic("megaphone")}<span><b>Идеи и предложения</b>напиши, что добавить или исправить в игре</span>${ic("chev")}</button>`;
  $("#cl-body").innerHTML = h;
  clRecFill();
};
// набор недели (recruit.py): кланы соревнуются, кто приведёт больше новичков
async function clRecFill() {
  const box = $("#cl-rec"); if (!box) return;
  const d = await api("clans-recruit").catch(() => null);
  if (!d || !box.isConnected) return;
  box.innerHTML = `<div class="clrec"><div class="clrec-h"><span class="pic g">${ic("userPlus")}</span><div class="grow"><b>Набор недели</b>
      <span>Новичок вступил в клан и дорос до ${d.level} ур. Итоги через ${clanHours(d.left)}</span></div></div>
    <div class="clrec-pz">${d.prizes.map((p, i) => `<div><span>${i + 1} место</span><b>⭐ ${short(p)}</b></div>`).join("")}</div>
    ${d.top.length ? `<div class="clrec-top">${d.top.map((c, i) => `<div class="row tap" data-act="clan" data-id="${c.id}"><span class="place${i < 3 ? " p" + (i + 1) : ""}">${i + 1}</span>${clanBadge(c)}<div class="grow"><div class="t">${esc(c.name)}</div></div><b>${c.n}</b></div>`).join("")}</div>`
      : `<div class="hint" style="font-size:12.5px;margin-top:8px">На этой неделе пока никто. Призы в казну клана, от ${d.min} новичков</div>`}
    ${d.inClan ? `<div class="hint" style="font-size:12.5px;margin-top:8px">У твоего клана: <b>${d.mine}</b>. Зови друзей ссылкой из карточки клана</div>` : ""}</div>`;
}

// казна клана: баланс, налог, буст; у главы — управление
function clanBankHTML(c) {
  const owner = c.role === "owner", sp = c.spend, boost = c.boostUntil > Date.now() / 1000;
  const pct = x => String(+(x * 100).toFixed(1)).replace(".", ",") + "%";
  return `<div class="sec-t">${ic("wallet")}Казна клана</div>
    <div class="clbank">
      <div class="clb-top"><div><span>В казне</span><b>⭐ ${fmt(c.bank)}</b></div><div><span>Налог с выигрышей</span><b>${c.tax ? pct(c.tax) : "нет"}</b></div>
        <div><span>Буст дохода</span><b class="${boost ? "tw" : ""}">${boost ? `+${sp.boostPct}% · ${Math.ceil((c.boostUntil - Date.now() / 1000) / 3600)} ч` : "выкл."}</b></div></div>
      ${owner ? `<div class="clb-sec">Налог в казну <span class="hint">— с чистого выигрыша участников в играх на звёзды</span></div>
        <div class="seg">${[...new Set([0, .01, .02, .03, .05].filter(x => x <= (sp && sp.taxMax != null ? sp.taxMax : .05)).concat(sp && sp.taxMax ? [sp.taxMax] : []))].map(x => `<button data-act="clan-taxset" data-v="${x}" class="${Math.abs((c.tax || 0) - x) < 1e-6 ? "on" : ""}">${x ? pct(x) : "0"}</button>`).join("")}</div>
        <div class="clb-sec">Потратить казну</div>
        <div class="clb-acts">
          <button data-act="clan-pay">${ic("users")}<b>Раздать участникам</b><span>поровну всем участникам</span></button>
          <button data-act="clan-boost" data-p="${sp.boost}">${ic("trend")}<b>Буст +${sp.boostPct}% к доходу</b><span>на сутки · ⭐ ${short(sp.boost)}</span></button>
          ${Object.entries(sp.keys).map(([k, p]) => `<button data-act="clan-keys" data-v="${k}" data-p="${p}">${ic("lock")}<b>Ключ «${esc(sp.keyTitles[k])}» всем</b><span>⭐ ${short(p)}</span></button>`).join("")}
          ${sp.slots ? `<button data-act="clan-slots" data-p="${sp.slots}">${ic("plus")}<b>+${sp.slotsStep} мест в клане</b><span>⭐ ${short(sp.slots)}</span></button>` : ""}
        </div>` : ""}
      <div id="cl-shares"></div>
      ${owner ? "" : `<div class="hint" style="font-size:12px;margin-top:8px">Казна пополняется взносами${c.tax ? " и налогом с выигрышей" : ""}. Тратит её глава: раздачи, ключи всем, бусты, расширение клана, акции банка.</div>`}
    </div>`;
}
// акции банка у клана: дивиденды идут в казну; покупает и продаёт глава
async function clSharesFill() {
  const box = $("#cl-shares"); if (!box) return;
  let d; try { d = await api("bank/clan"); } catch (e) { return; }
  if (!d.clan || !box.isConnected) return;
  const pl = d.value - d.cost, sell = Math.floor(d.n * d.price * (1 - d.sellFee));
  box.innerHTML = `<div class="clb-sec">Акции банка <span class="hint">— дивиденды каждый день идут в казну</span></div>
    <div class="clsh">
      <div class="clsh-top"><div><span>У клана</span><b>${fmt(d.n)}</b></div><div><span>Стоимость</span><b>⭐ ${short(d.value)}</b></div>
        <div><span>Прибыль</span><b class="${pl >= 0 ? "tw" : "tl"}">${d.n ? (pl >= 0 ? "+" : "−") + short(Math.abs(pl)) : "—"}</b></div></div>
      ${d.n ? `<div class="bks-row"><span>${d.crisis ? "Дивиденды на паузе — банк в кризисе" : "Дивиденды сегодня (прогноз)"}</span><b class="tw">${d.crisis ? "—" : "+⭐ " + fmt(d.est)}</b></div>
        <div class="bks-row"><span>Получено в казну</span><b>⭐ ${fmt(d.div)}</b></div>` : ""}
      ${d.owner ? `${d.room > 0 ? `<div class="jpbuy bks-buy">${[10, 100, 500, 1000].filter(n => n <= d.room).map(n => `<button data-act="clsh-buy" data-v="${n}" ${n * d.price > d.pool ? "disabled" : ""}><b>+${n}</b><span>⭐ ${short(n * d.price)}</span></button>`).join("")}</div>`
          : `<div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Лимит клана — ${fmt(d.max)} акций</div>`}
        ${d.n ? `<button class="btn ghost bks-sell" data-act="clsh-sell" data-n="${d.n}" data-g="${sell}" ${d.sellIn ? "disabled" : ""}>${d.sellIn ? `${ic("lock")}Продажа через ${Math.floor(d.sellIn / 3600)} ч ${Math.floor(d.sellIn % 3600 / 60)} мин` : `${ic("coins")}Продать все · ⭐ ${short(sell)} в казну`}</button>` : ""}`
        : `<div class="hint" style="font-size:12px;margin-top:6px">Покупает и продаёт акции глава клана — из казны.</div>`}
    </div>`;
  starify(box);
}
const _clBankHTML = clanBankHTML;
clanBankHTML = function (c) { setTimeout(clSharesFill, 0); return _clBankHTML(c); };
// подарки для герба клана (коллекции)
const CLAN_EMBLEMS = ["Plush Pepe", "Durov's Cap", "Heart Locket", "Precious Peach", "Mighty Arm", "Loot Bag", "Ion Gem", "Astral Shard",
  "Signet Ring", "Swiss Watch", "Scared Cat", "Toy Bear", "Kissed Frog", "Magic Potion", "Genie Lamp", "Neko Helmet",
  "Electric Skull", "Mad Pumpkin", "Witch Hat", "Stellar Rocket", "Money Pot", "Jack-in-the-Box", "Heroic Helmet", "Low Rider"];
// уровни клана: что открывает каждый
function clanLevelsHTML(c) {
  if (!CL || !CL.perks) return "";
  const nxt = c.level + 1, perk = CL.perks[nxt];
  return `<details class="cllv"><summary>${ic("layers")}<div class="grow"><b>Уровень ${c.level} из ${CL.levels.length}</b>
      <span>${c.next ? `дальше: ${perk ? esc(perk) : `+2% к доходу`} · ⭐ ${short(c.next - c.treasury)} до ${nxt} ур.` : "максимальный уровень клана"}</span></div>${ic("chev")}</summary>
    <div class="cllv-l">${CL.levels.map((need, i) => { const L = i + 1, done = c.level >= L;
      return `<div class="cllv-r${done ? " done" : ""}${L === c.level ? " cur" : ""}"><span class="cllv-n">${done ? ic("check") : L}</span>
        <div class="grow"><b>${L > 1 ? `+${2 * (L - 1)}% к доходу` : "Основание клана"}${CL.perks[L] ? ` · ${esc(CL.perks[L])}` : ""}</b><span>${need ? `казна ⭐ ${short(need)}` : "сразу"}</span></div></div>`; }).join("")}</div></details>`;
}
const ROLE_T = { owner: "глава", officer: "офицер", treasurer: "казначей", captain: "капитан" };
const clanAgo = ts => { const s = Date.now() / 1000 - ts; return s < 3600 ? Math.max(1, Math.floor(s / 60)) + " мин" : s < 86400 ? Math.floor(s / 3600) + " ч" : Math.floor(s / 86400) + " д"; };
function clanFeedTxt(f) {
  const n = f.user ? `<b>${esc(f.user.name)}</b>` : "";
  return { create: `${n} основал клан`, join: `${n} вступил в клан`, leave: `${n} покинул клан`, kick: `${n} исключён`,
    donate: `${n} внёс в казну ⭐ ${fmt(+f.data)}`, level: `Клан достиг <b>${f.data} уровня</b>`, owner: `${n} — новый глава`,
    officer: `${n} назначен офицером`, demote: `${n} больше не офицер`,
    tag: `Глава сменил тег клана на [${esc(f.data)}]`,
    tax: +f.data ? `Глава установил налог ${String(+(f.data * 100).toFixed(1)).replace(".", ",")}% в казну` : "Глава отменил налог",
    spend_pay: `Казна раздала участникам ⭐ ${fmt(+f.data)}`, spend_keys: `Казна купила всем ключ «${esc(f.data)}»`,
    spend_boost: `Включён буст: +${f.data}% к доходу на сутки`, spend_slots: `Клан расширен до ${f.data} мест`,
    sharebuy: `${n} купил клану ${fmt(+f.data)} ${plural(+f.data, ["акцию", "акции", "акций"])} банка`, sharesell: `Клан продал акции банка: +⭐ ${fmt(+f.data)} в казну`,
    sharediv: `Дивиденды по акциям банка: +⭐ ${fmt(+f.data)} в казну`,
    goal: (() => { const [need, key] = String(f.data).split("|"); return `Цель недели: оборот ⭐ ${short(+need)} — всем ключ «${esc(key)}»`; })() }[f.kind] || n;
}
async function openClan(id) {
  const el = openSheet(emptyHTML("hourglass", "Загружаем клан…"));
  const draw = async () => {
    const c = await api("clans/" + id);
    if (!CL) CL = await api("clans").catch(() => null);
    const free = !CL || !CL.mine, staff = c.role === "owner" || c.role === "officer";
    const [ca, cb] = CLAN_COLORS[c.color % 8];
    const nextGoal = c.goals.find(g => !g.done);
    replaceSheet(el, `<div class="clhero" style="--a:${ca};--b:${cb}">
        ${c.emblem && c.level >= 4 ? `<div class="clpat" style="--img:url('${A.orig(c.emblem, 64)}')"></div>` : ""}
        ${c.emblem ? `<img class="clemb" src="${A.orig(c.emblem, 256)}" alt="">` : ""}${clanBadge(c)}<h2>${esc(c.name)}</h2>
        <span>${c.members}/${c.slots || 20} участников · уровень ${c.level}${c.bonus ? ` · +${c.bonus}% к доходу` : ""} · ${c.open ? "открытый" : "по заявкам"}</span>
        ${c.descr ? `<p class="cldescr">${esc(c.descr)}</p>` : ""}</div>
      ${c.mine ? `<button class="clchat-btn" data-act="clan-chat">${ic("chat")}<div class="grow"><b>Чат клана</b><span>${ME.clanChat ? "есть новые сообщения" : "переписка и крупные выигрыши участников"}</span></div>${ME.clanChat ? `<em>${ME.clanChat}</em>` : ""}${ic("chev")}</button>` : ""}
      <div class="bks-top" style="margin:12px 0"><div><span>Оборот недели</span><b>⭐ ${short(c.score)}</b></div><div><span>Казна</span><b>⭐ ${short(c.treasury)}</b></div><div><span>След. уровень</span><b>${c.next ? "⭐ " + short(c.next) : "—"}</b></div></div>
      ${clanLevelsHTML(c)}
      <div class="sec-t">${ic("target")}Цели недели</div>
      <div class="clgoals">${c.goals.map(g => `<div class="clgoal${g.done ? " done" : ""}"><div class="clg-h"><b>⭐ ${short(g.need)}</b><span>${g.done ? ic("check") : ""}ключ «${esc(g.key)}»</span></div>
        <i style="--p:${Math.min(100, c.score / g.need * 100)}%"></i></div>`).join("")}</div>
      <div class="hint" style="font-size:12px;margin:6px 4px 0">${nextGoal ? `Оборот в играх всех участников (не больше ⭐ 10K с одной ставки). До цели — ⭐ ${short(Math.max(0, nextGoal.need - c.score))}. Ключ получат все, кто сыграл за неделю от 20 раундов.` : "Все цели недели выполнены!"}</div>
      ${clanBankHTML(c)}
      ${c.mine ? `<button class="btn ghost fwide" style="margin-bottom:8px" data-act="clan-biz">${ic("store")}Бизнесы клана</button>` : ""}
      ${c.mine ? `<div class="btns"><button class="btn gold" style="flex:2" data-act="clan-donate">${ic("coins")}В казну</button><button class="btn ghost" style="flex:2" data-act="clan-invite" data-link="${esc(c.invite)}" data-n="${esc(c.name)}">${ic("send")}Позвать</button>
          <button class="btn ghost" style="flex:1" data-act="clan-leave">${ic("x")}</button></div>
        ${staff ? `<button class="btn ghost sm" style="width:100%;margin-top:8px" data-act="clan-set" data-id="${c.id}">${ic("edit")}Настройки клана</button>` : ""}`
        : free ? (c.requested ? `<button class="btn ghost" disabled>${ic("hourglass")}Заявка отправлена</button>`
          : `<button class="btn gold" data-act="clan-join" data-id="${c.id}">${ic("users")}${c.open ? "Вступить" : "Подать заявку"}</button>`) : ""}
      ${c.requests.length ? `<div class="sec-t">${ic("userPlus")}Заявки · ${c.requests.length}</div><div class="box">${c.requests.map(u => `<div class="row">${avaHTML(u, 34)}
        <div class="grow"><div class="t">${nameHTML(u)}</div><div class="s">${u.level} ур. · ${clanAgo(u.ts)} назад</div></div>
        <button class="btn sm green" data-act="clan-req" data-id="${u.id}" data-v="accept">${ic("check")}</button><button class="btn sm ghost" data-act="clan-req" data-id="${u.id}" data-v="decline">${ic("x")}</button></div>`).join("")}</div>` : ""}
      <div class="sec-t">${ic("users")}Участники</div>
      <div class="box">${c.list.map(m => `<div class="row tap" data-act="${c.isOwner && m.id !== ME.id ? "clan-mem" : "profile"}" data-id="${m.id}" data-role="${m.role}" data-n="${esc(m.name)}">${avaHTML(m, 34)}
        <div class="grow"><div class="t">${esc(m.name)}${ROLE_T[m.role] ? ` <span class="pill${m.role === "owner" ? " gold" : ""}">${ROLE_T[m.role]}</span>` : ""}</div>
        <div class="s">оборот ⭐ ${short(m.score)}${m.donated ? ` · взнос ⭐ ${short(m.donated)}` : ""}${m.taxed ? ` · налог ⭐ ${short(m.taxed)}` : ""}</div></div>
        ${staff && m.id !== ME.id && (c.isOwner || m.role === "member") ? `<button class="btn sm ghost" data-act="clan-kick" data-id="${m.id}">${ic("x")}</button>` : ""}</div>`).join("")}</div>
      ${c.feed.length ? `<div class="sec-t">${ic("activity")}Лента клана</div><div class="box clfeed">${c.feed.map(f => `<div class="row kv"><div class="grow"><div class="s">${clanFeedTxt(f)}</div></div><span class="hint" style="font-size:11.5px">${clanAgo(f.ts)}</span></div>`).join("")}</div>` : ""}
      <div class="disc">Взносы и налог копятся в казне клана и качают уровень: каждый уровень даёт всем участникам +2% к доходу с подарков и бизнесов, а с 3 уровня открываются перки: цветной тег, рамка клана, места, скидки на оформление. Каждую неделю 3 клана с самым большим оборотом в играх получают призы — их делят между участниками по вкладу. За цели недели каждый участник получает ключ от кейса.</div>`);
    el._clan = c;
    starify(el);
  };
  el._redraw = draw;
  await draw();
}
const clanRefresh = async () => { CL = await api("clans"); if (TAB === "top" && topKind === "clans") renderTop(); const s = topSheet(); s && s._redraw && s._redraw(); };

Object.assign(ACT, {
  clan: el => openClan(+el.dataset.id),
  "clan-tag": async el => { const c = (CL || await api("clans")).list.find(x => x.tag === el.dataset.tag); if (c) openClan(c.id); },
  "clan-new": () => {
    const el = openSheet(`<h2 class="gtitle">Новый клан</h2>
      <div class="adm-f"><span>Название</span><input id="cn-name" maxlength="20" placeholder="Например, Пёсики"></div>
      <div class="adm-f"><span>Тег</span><input id="cn-tag" maxlength="4" placeholder="PES" style="text-transform:uppercase"></div>
      <div class="adm-f"><span>Цвет</span><div class="cl-colors">${CLAN_COLORS.map((c, i) => `<button data-act="cn-color" data-v="${i}" class="${i ? "" : "on"}" style="background:linear-gradient(135deg,${c[0]},${c[1]})"></button>`).join("")}</div></div>
      <button class="btn gold" data-act="clan-create" style="margin-top:14px">Создать за ⭐ ${fmt(CL ? CL.createCost : 5000)}</button>
      <div class="hint" style="font-size:12px;text-align:center;margin-top:8px">Тег — 2–4 заглавные буквы или цифры, он будет виден в профиле. До ${CL ? CL.maxMembers : 20} участников.</div>`);
    el._color = 0;
  },
  "cn-color": el => { topSheet()._color = +el.dataset.v; el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); H.sel(); },
  "clan-create": async () => {
    const s = topSheet();
    const r = await post("clans", { name: s.querySelector("#cn-name").value, tag: s.querySelector("#cn-tag").value.toUpperCase(), color: s._color || 0 });
    setStars(r.stars); H.ok(); toast("Клан создан!", "ok"); burstAt(s); closeSheet(); topKind = "clans"; await clanRefresh();
  },
  "clan-join": async el => { const r = await post(`clans/${el.dataset.id}/join`); H.ok(); toast(r.requested ? "Заявка отправлена — ждём ответа главы" : "Ты в клане!", "ok"); await clanRefresh(); },
  "clan-invite": el => {
    const text = `Вступай в мой клан «${el.dataset.n}» 🛡`, url = `https://t.me/share/url?url=${enc(el.dataset.link)}&text=${enc(text)}`;
    if (inTg) tg.openTelegramLink(url); else { navigator.clipboard?.writeText(el.dataset.link); toast("Ссылка скопирована"); }
  },
  "clan-req": async el => { await post(`clans/requests/${el.dataset.id}/${el.dataset.v}`); H.ok(); toast(el.dataset.v === "accept" ? "Принят в клан" : "Заявка отклонена", "ok"); await clanRefresh(); },
  "clan-mem": el => {   // меню главы для участника
    const role = el.dataset.role, n = el.dataset.n, id = el.dataset.id;
    openSheet(`<h2 class="gtitle">${esc(n)}</h2><p class="hint" style="margin:-6px 0 14px">${ROLE_T[role] || "участник"}</p>
      <div style="display:grid;gap:8px"><button class="btn ghost" data-act="profile" data-id="${id}">${ic("users")}Профиль</button>
      ${role === "officer" ? `<button class="btn ghost" data-act="clan-role" data-id="${id}" data-v="member">Снять с офицера</button>`
        : `<button class="btn ghost" data-act="clan-role" data-id="${id}" data-v="officer">${ic("medal")}Сделать офицером</button>`}
      <button class="btn ghost" data-act="clan-role" data-id="${id}" data-v="owner" data-n="${esc(n)}">${ic("crown")}Передать главенство</button></div>`);
  },
  "clan-role": async el => {
    const v = el.dataset.v;
    if (v === "owner" && !await confirmM("Передать главенство?", `${esc(el.dataset.n)} станет главой клана, а ты — офицером.`, "Передать")) return;
    await post(`clans/role/${el.dataset.id}`, { role: v }); H.ok(); toast("Готово", "ok"); closeSheet(); await clanRefresh();
  },
  "clan-taxset": async el => {
    const v = +el.dataset.v;
    if (!await confirmM(v ? `Налог ${pctF(v)}?` : "Отменить налог?", v ? "С каждого чистого выигрыша участников в играх на звёзды эта доля уйдёт в казну клана. Участники получат уведомление." : "Выигрыши участников больше не будут облагаться.", "Применить")) return;
    await post("clans/tax", { rate: v }); H.ok(); toast("Налог обновлён", "ok"); await clanRefresh();
  },
  "clan-pay": async () => {
    const c = topSheet()._clan;
    const v = await promptM("Раздать из казны", `В казне ⭐ ${fmt(c.bank)}. Сумма делится между ${c.members} участниками поровну.${c.spend && c.spend.payTax ? ` Налог ${pctF(c.spend.payTax)} с каждой доли уходит в банк игры.` : ""}`, String(Math.floor(c.bank / 2)), "Раздать");
    if (v == null || !(+v > 0)) return;
    await post("clans/spend", { kind: "pay", amount: Math.floor(+v), mode: "equal" }); H.ok(); toast("Раздано!", "ok"); await loadMe(); await clanRefresh();
  },
  "clan-boost": async el => { if (!await confirmM("Включить буст?", `+10% к доходу всем участникам на сутки за ⭐ ${fmt(+el.dataset.p)} из казны.`, "Включить")) return; await post("clans/spend", { kind: "boost" }); H.ok(); toast("Буст включён", "ok"); await clanRefresh(); },
  "clan-keys": async el => { if (!await confirmM("Купить ключи всем?", `Каждый участник получит ключ. Цена ⭐ ${fmt(+el.dataset.p)} из казны.`, "Купить")) return; await post("clans/spend", { kind: "keys", cid: el.dataset.v }); H.ok(); toast("Ключи розданы", "ok"); CASES = []; await clanRefresh(); },
  "clsh-buy": async el => {
    const n = +el.dataset.v;
    if (!await confirmM(`Купить клану ${fmt(n)} ${plural(n, ["акцию", "акции", "акций"])} банка?`, "Звёзды спишутся из казны. Дивиденды будут каждый день приходить в казну.", "Купить")) return;
    await post("bank/clan", { n }); H.ok(); toast("Акции куплены", "ok"); await clanRefresh();
  },
  "clsh-sell": async el => {
    if (!await confirmM("Продать все акции клана?", `В казну придёт ⭐ ${fmt(+el.dataset.g)} (комиссия 3%).`, "Продать")) return;
    await post("bank/clan", { n: -(+el.dataset.n) }); H.ok(); toast("Продано — звёзды в казне", "ok"); await clanRefresh();
  },
  "clan-slots": async el => { if (!await confirmM("Расширить клан?", `+5 мест за ⭐ ${fmt(+el.dataset.p)} из казны.`, "Расширить")) return; await post("clans/spend", { kind: "slots" }); H.ok(); toast("Клан расширен", "ok"); await clanRefresh(); },
  "clan-set": el => {
    const c = topSheet()._clan; if (!c) return;
    const s = openSheet(`<h2 class="gtitle">Настройки</h2>
      ${c.role === "owner" ? `<div class="adm-f"><span>Тег [${esc(c.tag)}]</span><input id="cs-tag" maxlength="4" value="${esc(c.tag)}" placeholder="ТЕГ" style="text-transform:uppercase;max-width:120px"></div>
      <div class="hint" style="margin:-4px 2px 8px;font-size:12px">2–4 заглавные буквы или цифры. Сменится у всех участников.</div>` : ""}
      <div class="adm-f"><span>Описание</span><input id="cs-d" maxlength="140" value="${esc(c.descr)}" placeholder="Кто мы и куда идём"></div>
      <div class="adm-f"><span>Вступление</span><div class="seg" style="flex:1;margin:0" id="cs-o"><button data-act="cs-open" data-v="1" class="${c.open ? "on" : ""}">Свободное</button><button data-act="cs-open" data-v="0" class="${c.open ? "" : "on"}">По заявкам</button></div></div>
      <div class="sec-t">Герб клана</div>
      <div class="clembs">${CLAN_EMBLEMS.map(e => `<button data-act="cs-emb" data-v="${esc(e)}" class="${c.emblem === e ? "on" : ""}"><img src="${A.orig(e, 64)}" alt=""></button>`).join("")}</div>
      <button class="btn gold" data-act="cs-save" style="margin-top:14px">Сохранить</button>`);
    s._set = { open: c.open, emblem: c.emblem };
  },
  "cs-open": el => { topSheet()._set.open = el.dataset.v === "1"; el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); H.sel(); },
  "cs-emb": el => { const st = topSheet()._set; st.emblem = st.emblem === el.dataset.v ? "" : el.dataset.v; el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === st.emblem)); H.sel(); },
  "cs-save": async () => {
    const s = topSheet(), st = s._set, tagEl = s.querySelector("#cs-tag");
    const body = { descr: s.querySelector("#cs-d").value, emblem: st.emblem, open: st.open };
    if (tagEl) body.tag = tagEl.value.trim().toUpperCase();
    await post("clans/settings", body); H.ok(); toast("Сохранено", "ok"); closeSheet(); await clanRefresh();
  },
  "clan-leave": async () => {
    if (!await confirmM("Выйти из клана?", "Вступить в другой клан можно будет через 12 часов. Взносы в казну не возвращаются.", "Выйти")) return;
    await post("clans/leave"); toast("Ты вышел из клана"); closeSheet(); await clanRefresh();
  },
  "clan-kick": async el => { if (!await confirmM("Исключить игрока?", "Он сможет вступить снова через 12 часов.", "Исключить")) return; await post(`clans/kick/${el.dataset.id}`); toast("Исключён"); await clanRefresh(); },
  "clan-donate": async () => {
    const c = topSheet()._clan, dt = c && c.spend ? c.spend.donateTax : 0;
    const v = await promptM("Взнос в казну", `Звёзды уйдут в казну клана и прокачают его уровень.${dt ? ` Налог ${pctF(dt)} — в банк игры.` : ""}`, "1000", "Внести");
    if (v == null || !(Math.floor(+v) >= 100)) return v == null ? null : toast("Взнос от ⭐ 100");
    const r = await post("clans/donate", { amount: Math.floor(+v) }); setStars(r.stars); H.ok(); toast(`Казна: ⭐ ${fmt(r.treasury)} · уровень ${r.level}${r.tax ? ` · налог ⭐ ${fmt(r.tax)}` : ""}`, "ok"); await clanRefresh();
  },
});

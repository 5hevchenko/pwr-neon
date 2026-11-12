"use strict";
// ============================================================
//  Админка: пульт (живые цифры), тревоги, разбор игрока, журнал с отменой действий (сервер — ops.py)
// ============================================================
const ADM_ACT = { stars: "Звёзды", ban: "Бан", unban: "Разбан", gift: "Выдал подарок", keys: "Выдал ключи", game: "Состояние игры", odds: "Шансы",
  undo: "Отмена", admin_on: "Выдал админку", admin_off: "Снял админку", alerts: "Тревоги", claw: "Кран", broadcast: "Рассылка", promo: "Акция",
  event: "Ивент", gift_rm: "Забрал подарок", cosm_rm: "Забрал оформление", wipe: "Вайп", fees: "Комиссии", shop: "Продажи",
  freeze: "Заморозил кошелёк", unfreeze: "Разморозил кошелёк", comp: "Компенсация", addr: "Адрес кошелька" };
const ALERT_IC = { bigwin: "trophy", hour: "flame", bank: "bank", game: "games", adminstars: "users", server: "activity" };

// ---------------- пульт ----------------
function admPulseHTML(p) {
  const mx = Math.max(1, ...p.onlineHours);
  const gmx = Math.max(1, ...p.games.map(g => Math.abs(g.house)));
  return `<div class="ap">
    <div class="ap-top">
      <div class="ap-c on"><span>Онлайн сейчас</span><b>${fmt(p.online)}</b><div class="ap-spark">${p.onlineHours.map(v => `<i style="height:${Math.max(6, v / mx * 100)}%"></i>`).join("")}</div><small>за 24 ч по часам</small></div>
      <div class="ap-c"><span>Банк</span><b>⭐ ${short(p.bank)}</b><small class="${p.bank24 >= 0 ? "tw" : "tl"}">${p.bank24 >= 0 ? "+" : "−"}${short(Math.abs(p.bank24))} за сутки</small>${p.crisis ? `<em class="ap-cr">кризис</em>` : ""}</div>
      <div class="ap-c"><span>Банк за сегодня</span><b class="${p.houseToday >= 0 ? "tw" : "tl"}">${p.houseToday >= 0 ? "+" : "−"}${short(Math.abs(p.houseToday))}</b><small>игры против игроков</small></div>
      <div class="ap-c"><span>Продажи сегодня</span><b>${fmt(p.sales.xtr)} <i class="adm-tg">${ic("tgplane")}</i></b><small>${p.sales.n} покупок</small></div>
      <div class="ap-c"><span>Активных 24 ч</span><b>${fmt(p.active24)}</b><small>новых: ${fmt(p.new24)}</small></div>
      <button class="ap-c tap" data-act="adm-goto" data-v="tickets"><span>Тикеты</span><b class="${p.tickets ? "tl" : ""}">${fmt(p.tickets)}</b><small>${p.tickets ? "ждут ответа" : "всё отвечено"}</small></button>
    </div>
    <button class="ap-al" data-act="adm-alerts"><span class="ap-al-i">${ic("megaphone")}</span><div class="grow"><b>Тревоги</b>
      <small>${p.alerts.length ? esc(p.alerts[0].text).slice(0, 80) : "Тихо — ничего подозрительного"}</small></div>${p.alerts.length ? `<em>${p.alerts.length}</em>` : ""}${ic("chev")}</button>
    <div class="sec-t">${ic("games")}Игры сегодня</div>
    <div class="box">${p.games.length ? p.games.map(g => `<div class="row kv ap-g"><div class="grow"><div class="t">${esc(g.name)}</div>
        <div class="s">${fmt(g.rounds)} раундов · ${fmt(g.players)} игроков</div><div class="ap-bar"><i class="${g.house >= 0 ? "up" : "dn"}" style="width:${Math.max(3, Math.abs(g.house) / gmx * 100)}%"></i></div></div>${admSgn(g.house)}</div>`).join("")
      : `<div class="hint" style="padding:14px">Сегодня ещё никто не играл</div>`}</div>
    ${p.wins.length ? `<div class="sec-t">${ic("trophy")}Крупные выигрыши сегодня</div><div class="box">${p.wins.map(w => `<div class="row tap" data-act="adm-user" data-id="${w.id}">${avaHTML(w, 32)}
      <div class="grow"><div class="t">${esc(w.name)}</div><div class="s">${esc(w.game)} · ${admDate(w.ts)}</div></div><b class="tw">+⭐ ${short(w.amount)}</b></div>`).join("")}</div>` : ""}
    <div class="ap-cb">${ic("refresh")}<span>Возврат ушедших за 7 дней: написали <b>${fmt(p.comeback.sent)}</b>, вернулись <b>${fmt(p.comeback.back)}</b>${p.comeback.sent ? ` (${Math.round(p.comeback.back / p.comeback.sent * 100)}%)` : ""}</span></div>
  </div>`;
}

// ---------------- тревоги ----------------
async function openAdmAlerts() {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "adm-al-s");
  const draw = async () => {
    const d = await api("admin/alerts"); if (!el.isConnected) return;
    replaceSheet(el, `<h2 class="gtitle">Тревоги</h2>
      <p class="hint" style="margin:-4px 0 12px;font-size:13px">Бот пишет владельцам в личку, когда происходит что-то важное. Проверка — раз в минуту, одна и та же тревога не повторяется часами.</p>
      <div class="box">${d.cfg.map(c => `<div class="row kv ap-ac"><span class="pic ${c.on ? "y" : "b"}">${ic(ALERT_IC[c.k] || "activity")}</span><div class="grow"><div class="t">${esc(c.title)}</div>
        <div class="s">${esc(c.hint)}</div>
        ${d.canEdit ? `<div class="ap-ain"><input class="adm-oi" inputmode="numeric" id="al-${c.k}" value="${c.min}"><button class="btn sm ghost" data-act="adm-al-min" data-k="${c.k}">${ic("check")}</button></div>` : `<div class="s"><b>${fmt(c.min)}</b></div>`}</div>
        ${d.canEdit ? `<button class="sw${c.on ? " on" : ""}" data-act="adm-al-on" data-k="${c.k}" data-v="${c.on ? 0 : 1}"></button>` : `<b>${c.on ? "вкл" : "выкл"}</b>`}</div>`).join("")}</div>
      <div class="sec-t">${ic("clock")}Последние тревоги</div>
      <div class="box">${d.last.map(a => `<div class="row"><span class="pic r">${ic(ALERT_IC[a.kind] || "activity")}</span><div class="grow"><div class="t" style="white-space:normal">${esc(a.text)}</div><div class="s">${admDate(a.ts)}</div></div></div>`).join("")
        || `<div class="hint" style="padding:14px">Тревог ещё не было</div>`}</div>`);
  };
  el._redraw = draw;
  await draw();
}

// ---------------- разбор игрока ----------------
function admInsightHTML(d) {
  const mx = Math.max(1, ...d.kinds.map(k => Math.abs(k.sum)));
  return `${d.flags.length ? `<div class="ap-flags">${d.flags.map(f => `<div>${ic("bomb")}<span>${esc(f)}</span></div>`).join("")}</div>` : ""}
    <div class="sec-t">${ic("wallet")}Откуда баланс — за всё время</div>
    <div class="box">${d.kinds.map(k => `<div class="row kv ap-g"><div class="grow"><div class="t">${esc(k.name)}</div><div class="s">${fmt(k.n)} операций</div>
      <div class="ap-bar"><i class="${k.sum >= 0 ? "up" : "dn"}" style="width:${Math.max(3, Math.abs(k.sum) / mx * 100)}%"></i></div></div>${admSgn(k.sum)}</div>`).join("") || `<div class="hint" style="padding:14px">Операций нет</div>`}</div>
    ${d.games.length ? `<div class="sec-t">${ic("games")}Итог по играм</div><div class="box">${d.games.map(g => `<div class="row kv"><div class="grow"><div class="t">${esc(g.name)}</div>
      <div class="s">${fmt(g.n)} раундов · лучший занос ${g.best > 0 ? "+⭐ " + short(g.best) : "—"}</div></div>${admSgn(g.sum)}</div>`).join("")}</div>` : ""}
    ${d.peers.length ? `<div class="sec-t">${ic("swap")}С кем гоняет звёзды</div><div class="box">${d.peers.map(p => `<div class="row tap" data-act="adm-user" data-id="${p.id}">${avaHTML(p, 32)}
      <div class="grow"><div class="t">${esc(p.name)}</div><div class="s">${p.n} переводов · отправил ⭐ ${short(p.sent)} · получил ⭐ ${short(p.got)}</div></div>${ic("chev")}</div>`).join("")}</div>` : ""}`;
}

// ---------------- журнал с отменой ----------------
function admLogHTML(log) {
  if (!log.length) return `<div class="box"><div class="hint" style="padding:14px">Действий пока нет</div></div>`;
  return `<div class="box ap-log">${log.map(x => `<div class="row${x.undone ? " undone" : ""}">
      <div class="grow"><div class="t">${esc(ADM_ACT[x.action] || x.action)}${x.target ? ` · <span class="ap-lnk" data-act="adm-user" data-id="${x.target}">${esc(x.targetName || x.target)}</span>` : ""}</div>
        <div class="s">${esc(x.detail || "")}</div>
        <div class="s">${esc(x.adminName || x.admin)} · ${admDate(x.ts)}${x.undone ? ` · <b class="tl">отменено</b>` : ""}</div></div>
      ${x.canUndo ? `<button class="btn sm ghost" data-act="adm-undo" data-id="${x.id}" data-n="${esc(ADM_ACT[x.action] || x.action)}">${ic("refresh")}Отменить</button>` : ""}</div>`).join("")}</div>`;
}

Object.assign(ACT, {
  "adm-alerts": () => openAdmAlerts(),
  "adm-al-on": async el => { await post("admin/alerts", { k: el.dataset.k, on: el.dataset.v === "1" }); H.sel(); const s = topSheet(); s && s._redraw && s._redraw(); },
  "adm-al-min": async el => {
    const v = $("#al-" + el.dataset.k).value;
    await post("admin/alerts", { k: el.dataset.k, min: v }); H.ok(); toast("Порог сохранён", "ok");
  },
  "adm-undo": async el => {
    if (!await confirmM("Отменить действие?", `«${el.dataset.n}» будет отменено, отмена тоже попадёт в журнал.`, "Отменить")) return;
    const r = await post(`admin/log/${el.dataset.id}/undo`); H.ok(); toast("Отменено: " + r.what, "ok");
    const s = topSheet(); if (s) admRender(s);
  },
  "adm-goto": el => { const s = topSheet(); const b = s && s.querySelector(`#adm-seg [data-v="${el.dataset.v}"]`); if (b) { b.click(); b.scrollIntoView({ inline: "center", block: "nearest" }); } },
});

// ---------------- компенсации: кому (игра, период, раундов) → что (звёзды фикс / % проигрыша, ключи) → предпросмотр → выдать ----------------
let COMP = null;
const compDt = t => { const d = new Date(t * 1000 - new Date().getTimezoneOffset() * 60000); return d.toISOString().slice(0, 16); };
async function admComp(body) {
  COMP = await api("admin/comp/meta");
  const t = COMP.now;
  body.innerHTML = `<div class="box adm-odd cp-f">
      <div class="adm-oh"><b>${ic("users")}Кому</b></div>
      <div class="adm-f"><span>Игра</span>${admSel("cp-game", COMP.games, "Любая игра")}</div>
      <div class="adm-f"><span>С</span><input id="cp-from" type="datetime-local" value="${compDt(t - 86400)}"></div>
      <div class="adm-f"><span>По</span><input id="cp-to" type="datetime-local" value="${compDt(t)}"></div>
      <div class="adm-f"><span>Сыграл раундов, не меньше</span><input id="cp-min" inputmode="numeric" value="1"></div>
      <div class="adm-oh" style="margin-top:6px"><b>${ic("gift")}Что выдать</b></div>
      <div class="seg" id="cp-mode"><button class="on" data-act="cp-mode" data-v="fixed">Всем поровну</button><button data-act="cp-mode" data-v="loss">% от проигрыша</button></div>
      <div class="adm-f cp-fixed"><span>Звёзд каждому</span><input id="cp-amt" inputmode="numeric" placeholder="0"></div>
      <div class="cp-two cp-loss" hidden><div class="adm-f"><span>Вернуть %</span><input id="cp-pct" inputmode="decimal" placeholder="50"></div>
        <div class="adm-f"><span>Не больше ⭐ одному</span><input id="cp-cap" inputmode="numeric" placeholder="без предела"></div></div>
      <div class="cp-two"><div class="adm-f"><span>Ключи</span>${admSel("cp-cid", COMP.cases, "Без ключей")}</div>
        <div class="adm-f"><span>Сколько</span><input id="cp-keys" inputmode="numeric" value="1"></div></div>
      <div class="adm-f"><span>Сообщение игрокам</span><input id="cp-note" placeholder="Компенсация за лаги в краше"></div>
      <button class="btn ghost" data-act="cp-prev" style="margin-top:10px">${ic("search")}Посчитать</button>
    </div>
    <div id="cp-res"></div>
    <div class="hint" style="font-size:12px;text-align:center;margin-top:10px">Звёзды начисляются сверх банка, как выдача админом. Отменить можно в «Журнале» — снимет начисленное (кто уже потратил, у того сколько осталось).${COMP.owner ? "" : ` Больше ⭐ ${fmt(COMP.max)} за раз — только владелец.`}</div>`;
}
function compBody() {
  const v = id => $("#" + id).value.trim(), ts = id => Math.floor(new Date(v(id)).getTime() / 1000);
  return { game: v("cp-game") || "any", from: ts("cp-from"), to: ts("cp-to"), minRounds: +v("cp-min") || 1,
    mode: $("#cp-mode .on").dataset.v, amount: +v("cp-amt") || 0, pct: +v("cp-pct").replace(",", ".") || 0, cap: +v("cp-cap") || 0,
    cid: v("cp-cid"), keys: v("cp-cid") ? +v("cp-keys") || 1 : 0, note: v("cp-note") };
}
Object.assign(ACT, {
  "cp-mode": el => {
    H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el));
    const loss = el.dataset.v === "loss"; $(".cp-fixed").hidden = loss; $(".cp-loss").hidden = !loss;
  },
  "cp-prev": async () => {
    const b = compBody(), r = await post("admin/comp/preview", b), res = $("#cp-res"); if (!res) return;
    H.sel();
    res.innerHTML = `<div class="box adm-odd cp-sum"><div class="cp-big"><div><b>${fmt(r.players)}</b><span>игроков</span></div><div><b>⭐ ${short(r.stars)}</b><span>всего звёзд</span></div>${r.keys ? `<div><b>${fmt(r.keys)}</b><span>ключей</span></div>` : ""}</div>
      ${r.top.length ? `<div class="cp-top">${r.top.map(u => `<div class="row">${avaHTML(u, 28)}<div class="grow"><div class="t">${esc(u.name)}</div><div class="s">${fmt(u.rounds)} раундов · проиграл ⭐ ${fmt(u.loss)}</div></div><b>${u.stars ? "+" + fmt(u.stars) : "—"}</b></div>`).join("")}
        ${r.players > r.top.length ? `<div class="hint" style="font-size:12px;padding:6px 12px">…и ещё ${fmt(r.players - r.top.length)}</div>` : ""}</div>` : ""}
      ${r.players ? `<button class="btn gold" data-act="cp-send" style="margin-top:10px" ${r.stars > r.max && !r.owner ? "disabled" : ""}>${ic("gift")}Выдать ${fmt(r.players)} игрокам</button>` : `<div class="hint" style="padding:12px;text-align:center">Под условия никто не попал</div>`}</div>`;
    starify(res); res.scrollIntoView({ behavior: "smooth", block: "start" });
  },
  "cp-send": async el => {
    const b = compBody(), r = await post("admin/comp/preview", b);
    if (!await confirmM("Выдать компенсацию?", `${fmt(r.players)} игрокам: ⭐ ${fmt(r.stars)}${r.keys ? ` и ${fmt(r.keys)} ключей` : ""}. Каждому придёт сообщение от бота.`, "Выдать")) return;
    el.disabled = true;
    try { const s = await post("admin/comp/send", b); H.ok(); toast(`Выдано ${fmt(s.players)} игрокам · ⭐ ${fmt(s.stars)}`, "ok"); $("#cp-res").innerHTML = ""; }
    catch (e) { el.disabled = false; }
  },
});

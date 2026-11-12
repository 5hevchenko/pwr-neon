"use strict";
// ============================================================
//  Окно «Пригласи друга»: личный QR-код со ссылкой игрока, ссылка с копированием, «Поделиться»
// ============================================================
function qrSVG(text) {
  const q = qrcode(0, "H");   // высокий уровень коррекции — в центре помещается значок
  q.addData(text); q.make();
  const n = q.getModuleCount(), hole = Math.ceil(n * 0.22) | 1, h0 = (n - hole) / 2;
  let d = "";
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) {
    if (!q.isDark(r, c)) continue;
    if (r >= h0 && r < h0 + hole && c >= h0 && c < h0 + hole) continue;   // место под значок
    d += `M${c} ${r}h1v1h-1z`;
  }
  return { svg: `<svg viewBox="-4 -4 ${n + 8} ${n + 8}" shape-rendering="crispEdges"><rect x="-4" y="-4" width="${n + 8}" height="${n + 8}" fill="#fff"/><path d="${d}" fill="#14112a"/></svg>`, n };
}
function copyText(t) {
  const ok = () => { H.ok(); toast("Ссылка скопирована", "ok"); };
  if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(t).then(ok, () => copyFallback(t, ok));
  copyFallback(t, ok);
}
function copyFallback(t, ok) {
  const a = document.createElement("textarea"); a.value = t; a.setAttribute("readonly", ""); a.style.cssText = "position:fixed;opacity:0;top:0";
  document.body.appendChild(a); a.select();
  try { document.execCommand("copy"); ok(); } catch (e) { toast("Не получилось — выдели ссылку и скопируй вручную"); }
  a.remove();
}
invite = async function () {
  H.imp("light");
  let qr = "";
  try { qr = qrSVG(ME.refLink).svg; } catch (e) {}
  const r = ME.ref || {};
  const el = openSheet(`<div class="inv-hero"><h2>Пригласи друга</h2><p>${r.on === false ? "Друг заходит по твоей ссылке и играет с тобой"
      : `Друг заходит по твоей ссылке${r.new ? ` и сразу получает <b class="star">+${fmt(r.new)} ⭐</b>` : ""}. Чем дальше он играет — тем больше получаешь ты`}</p></div>
    <div class="inv-qr"><div class="inv-code">${qr}<span class="inv-logo">${avaHTML(ME, 44)}</span></div>
      <span>Покажи QR-код — друг наведёт камеру и сразу попадёт в игру</span></div>
    <div class="inv-link"><code>${esc(ME.refLink.replace(/^https:\/\//, ""))}</code><button class="btn sm" data-act="inv-copy">${ic("layers")}Копировать</button></div>
    <button class="btn gold inv-share" data-act="inv-share">${ic("send")}Поделиться в Telegram</button>
    <div id="inv-more"><div class="empty" style="padding:24px 0"><b>⏳</b></div></div>`, "inv-s");
  starify(el);
  const d = await api("refs").catch(() => null);
  const box = el.querySelector("#inv-more"); if (!box) return;
  if (!d) { box.innerHTML = ""; return; }
  const step = (icn, cls, t, s) => `<div class="row"><span class="pic ${cls}">${ic(icn)}</span><div class="grow"><div class="t">${t}</div><div class="s">${s}</div></div></div>`;
  const next = d.milestones.find(m => !m.done);
  box.innerHTML = `<div class="inv-stats inv-s3"><div><b>${fmt(d.invited)}</b><span>${plural(d.invited, ["друг пришёл", "друга пришли", "друзей пришли"])}</span></div>
      <div><b>${fmt(d.active)}</b><span>активных (${d.l1[0]}+ ур.)</span></div>
      <div><b class="tw">+${short(d.earned)} ⭐</b><span>заработано</span></div></div>
    <div class="sec-t">Подарок по ссылке</div>
    <div class="box"><div class="row"><span class="pic y">${ic("gift")}</span><div class="grow"><div class="t">Подари подарок тому, кто ещё не играет</div>
      <div class="s" style="white-space:normal">В сумке открой подарок, нажми «Подарить другу» и выбери «Подарок по ссылке». Кто придёт по нему, станет твоим другом</div></div></div>
      <div class="row kv"><div class="grow"><div class="t">Пришли по твоим подаркам</div><div class="s">Отправлено ссылок: ${fmt(d.giftLinks)}</div></div><b>${fmt(d.giftFriends)}</b></div>
      <div class="row"><button class="btn sm ghost" style="width:100%" data-act="inv-bag">${ic("gift")}Выбрать подарок в сумке</button></div></div>
    ${d.duoOn ? `<div class="sec-t">Цель на двоих</div>
      <div class="hint" style="font-size:12px;margin:-4px 0 8px;white-space:normal"><span>Друг за ${d.duoDays} дней доходит до ${d.duoLevel} уровня и набирает оборот ⭐ ${short(d.duoFriend)}, ты ⭐ ${short(d.duoRef)}.</span> <span>Оборот: выигрыши и проигрыши вместе.</span> <span>Награда каждому ⭐ ${short(d.duoPrize)}</span></div>
      ${d.duos.length ? `<div class="box">${d.duos.map(x => { const f = x.me === "friend", my = f ? [x.fTurn, x.fNeed] : [x.rTurn, x.rNeed], ot = f ? [x.rTurn, x.rNeed] : [x.fTurn, x.fNeed];
        const bar = (a, b) => `<div class="inv-bar"><i style="width:${Math.min(100, a / Math.max(1, b) * 100)}%"></i></div>`;
        return `<div class="row duo-row">${x.other ? avaHTML(x.other, 32) : ""}<div class="grow" style="min-width:0"><div class="t">${esc(x.other ? x.other.name : "Друг")}${f ? `<span class="duo-tag">тебя пригласили</span>` : ""}</div>
          <div class="s">ты ${kk(Math.min(my[0], my[1]))} из ${kk(my[1])}</div>${bar(my[0], my[1])}
          <div class="s">друг: ${kk(Math.min(ot[0], ot[1]))} из ${kk(ot[1])}${f ? "" : ` · ${x.level} из ${x.levelNeed} ур.`}</div>${bar(ot[0], ot[1])}</div>
          <em class="duo-left">${gwLeft(x.left)}</em></div>`; }).join("")}</div>`
        : `<div class="hint" style="font-size:13px;padding:0 4px">Позови друга, и цель начнётся сама</div>`}` : ""}
    ${d.on ? `<div class="sec-t">Что ты получаешь</div><div class="box">
      ${d.join ? step("userPlus", "b", `+${fmt(d.join)} ⭐ сразу`, "когда друг зайдёт по ссылке") : ""}
      ${d.giftOn ? step("gift", "y", "Ключ от кейса другу", "скажем, когда друг откроет") : ""}
      ${d.l1[1] ? step("medal", "g", `+${fmt(d.l1[1])} ⭐`, `когда друг дойдёт до ${d.l1[0]} уровня`) : ""}
      ${d.l2[1] ? step("crown", "y", `+${fmt(d.l2[1])} ⭐`, `когда друг дойдёт до ${d.l2[0]} уровня`) : ""}
      ${d.buyPct && ME.shopOn ? step("gift", "b", `${d.buyPct}% с покупок друга`, "от звёзд, которые он купит в магазине") : ""}</div>` : ""}
    ${d.on && d.milestones.length ? `<div class="sec-t">Награды за активных друзей</div><div class="box">${d.milestones.map(m => `<div class="row kv inv-ms${m.done ? " done" : ""}">
        <div class="grow"><div class="t">${m.n} ${plural(m.n, ["друг", "друга", "друзей"])}</div>
        <div class="inv-bar"><i style="width:${Math.min(100, d.active / m.n * 100)}%"></i></div></div>
        <b>${m.done ? "✓ " : ""}+${short(m.amount)} ⭐</b></div>`).join("")}</div>
      ${next ? `<div class="hint" style="font-size:12px;text-align:center;margin-top:6px">До награды +${fmt(next.amount)} ⭐ — ещё ${next.n - d.active} ${plural(next.n - d.active, ["активный друг", "активных друга", "активных друзей"])}</div>` : ""}` : ""}
    ${d.on && d.topOn ? `<div class="sec-t">Топ недели · до ${new Date(d.weekEnds * 1000).toLocaleDateString(LANG === "en" ? "en-US" : "ru-RU", { day: "numeric", month: "long" })}</div>
      <div class="hint" style="font-size:12px;margin:-4px 0 8px">Кто приведёт больше активных друзей за неделю. Призы: ${d.prizes.map((p, i) => `${i + 1} место — ${short(p)} ⭐`).join(", ")} (от ${d.topMin} друзей). У тебя за неделю: <b>${d.myWeek}</b></div>
      <div class="box">${d.top.map((u, i) => `<div class="row tap" data-act="profile" data-id="${u.id}"><span class="inv-pl">${i + 1}</span>${avaHTML(u, 32)}<div class="grow" style="min-width:0"><div class="t">${esc(u.name)}</div></div><b>${u.n}</b></div>`).join("")
        || `<div class="hint" style="padding:14px">На этой неделе пока никого — стань первым</div>`}</div>` : ""}
    ${d.friends.length ? `<div class="sec-t">Мои друзья</div><div class="box">${d.friends.map(f => `<div class="row tap" data-act="profile" data-id="${f.id}">${avaHTML(f, 32)}
        <div class="grow" style="min-width:0"><div class="t">${esc(f.name)}</div><div class="s">${f.lv} ур.${d.on && f.lv < d.l2[0] ? ` · до бонуса ${f.lv < d.l1[0] ? d.l1[0] : d.l2[0]} ур.` : ""}</div></div></div>`).join("")}</div>` : ""}`;
  starify(box);
};
Object.assign(ACT, {
  "inv-copy": () => copyText(ME.refLink),
  "inv-bag": () => { closeSheet(); setTab("inv"); setTimeout(() => toast("Открой подарок: «Подарить другу», затем «Подарок по ссылке»"), 400); },
  "inv-share": () => {
    const text = ME.refBonus ? `Залетай в кейс-симулятор подарков 🎁 По моей ссылке получишь +${ME.refBonus} ⭐ на старт (игровых)` : "Залетай в кейс-симулятор подарков 🎁";
    const url = `https://t.me/share/url?url=${enc(ME.refLink)}&text=${enc(text)}`;
    if (inTg) tg.openTelegramLink(url); else copyText(ME.refLink);
  },
});

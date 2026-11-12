"use strict";
// ============================================================
//  «С возвращением» (away.py) и лимиты игрока (limits.py)
// ============================================================

// ---------- сводка после перерыва: один раз, когда на экране нет других окон ----------
async function awayStart(tries = 0) {
  if (document.querySelector(".sheet") || document.querySelector("#modal.on") || document.querySelector(".bw-ov")) {
    if (tries < 15) setTimeout(() => awayStart(tries + 1), 2000);
    return;
  }
  const d = await api("away").catch(() => null);
  const a = d && d.away;
  if (!a) return;
  const rows = [];
  for (const g of a.got) rows.push(`<div class="row kv"><span class="pic g">${ic("coins")}</span><div class="grow"><div class="t">${esc(g.t)}</div></div><b class="pos">+${fmt(g.v)} ⭐</b></div>`);
  if (a.income > 0) rows.push(`<div class="row tap" data-act="away-go" data-to="inc"><span class="pic y">${ic("wallet")}</span><div class="grow"><div class="t">Доход с подарков и бизнесов</div><div class="s">ждёт, чтобы его забрали</div></div><b>⭐ ${fmt(a.income)}</b>${ic("chev")}</div>`);
  if (a.free) rows.push(`<div class="row tap" data-act="away-go" data-to="free"><span class="pic y">${ic("gift")}</span><div class="grow"><div class="t">Бесплатный кейс</div><div class="s">готов к открытию</div></div>${ic("chev")}</div>`);
  if (a.keys > 0) rows.push(`<div class="row tap" data-act="away-go" data-to="cases"><span class="pic b">${ic("box")}</span><div class="grow"><div class="t">Ключи от кейсов</div><div class="s">открыть можно бесплатно</div></div><b>${a.keys}</b>${ic("chev")}</div>`);
  const fr = a.friends.length ? `<div class="sec-t">${ic("userPlus")}Пришли по твоей ссылке</div><div class="box">${a.friends.map(u => `<div class="row tap" data-act="profile" data-id="${u.id}">${avaHTML(u, 32)}<div class="grow" style="min-width:0"><div class="t">${esc(u.name)}</div></div>${ic("chev")}</div>`).join("")}</div>` : "";
  if (!rows.length && !fr) return;
  const el = openSheet(`<div class="aw-hero"><span class="aw-ic">${ic("sparkles")}</span><h2>С возвращением</h2>
      <p><span>Тебя не было</span> ${a.days} ${plural(a.days, ["день", "дня", "дней"])}. <span>Вот что накопилось</span></p></div>
    ${rows.length ? `<div class="box">${rows.join("")}</div>` : ""}${fr}
    <button class="btn gold aw-ok" data-act="away-ok">Продолжить</button>`, "aw-s");
  starify(el);
}
Object.assign(ACT, {
  "away-ok": () => closeSheet(),
  "away-go": el => {
    const to = el.dataset.to; closeSheet();
    setTimeout(() => {
      if (to === "inc" && ACT.inc) ACT.inc(el);
      else if (to === "free") openCase("free");
      else setTab("cases");
    }, 250);
  },
});

// ---------- лимиты и перерыв ----------
const LIM_PRESETS = [5000, 20000, 100000, 500000];
const limMsk = ts => new Date((ts + 3 * 3600) * 1000).toISOString().slice(5, 16).replace(/(\d+)-(\d+)T/, "$2.$1 ");
function limHTML(d) {
  const used = d.dayLoss ? Math.min(100, Math.round(d.lossToday * 100 / d.dayLoss)) : 0;
  const pause = d.pauseUntil
    ? `<div class="lim-pause">${ic("clock")}<div><b>Перерыв до ${limMsk(d.pauseUntil)}</b><span>по Москве. Ставки закрыты, отменить перерыв нельзя</span></div></div>` : "";
  return `<h2 class="gtitle">${ic("shield")} Лимиты и перерыв</h2>
    <p class="hint lim-intro">Помогают держать игру под контролем. Сделать строже можно сразу, ослабить или снять только через сутки.</p>
    ${pause}
    <div class="sec-t">Дневной лимит проигрыша</div>
    <div class="box lim-box">
      <div class="row kv"><div class="grow"><div class="t">${d.dayLoss ? `⭐ ${fmt(d.dayLoss)} <span>в сутки</span>` : "Не задан"}</div>
        <div class="s">${d.dayLoss ? `<span>сегодня проиграно</span> ⭐ ${fmt(d.lossToday)} · <span>сброс через</span> ${clock(d.resetIn)}` : "Когда проигрыш за сутки дойдёт до лимита, ставки закроются до конца суток"}</div></div></div>
      ${d.dayLoss ? `<div class="lim-bar"><i style="width:${used}%" class="${used >= 100 ? "full" : used >= 75 ? "hot" : ""}"></i></div>` : ""}
      ${d.next ? `<div class="lim-next">${ic("hourglass")}<span>${d.next.loss ? `<span>Новый лимит</span> ⭐ ${fmt(d.next.loss)}` : "Лимит снимется"} <span>с</span> ${limMsk(d.next.at)}</span></div>` : ""}
      <div class="chips lim-chips">${LIM_PRESETS.map(v => `<button data-act="lim-set" data-v="${v}" class="${d.dayLoss === v ? "on" : ""}">${short(v)}</button>`).join("")}
        ${d.dayLoss ? `<button data-act="lim-set" data-v="0">Снять</button>` : ""}</div>
      <div class="lim-own"><input type="number" inputmode="numeric" id="lim-v" min="100" placeholder="Своя сумма"><button class="btn sm" data-act="lim-own">Сохранить</button></div>
    </div>
    <div class="sec-t">Перерыв</div>
    <div class="box"><div class="hint lim-ph">На время перерыва ставки во всех играх закрыты. Отменить его нельзя.</div>
      <div class="chips lim-chips">${d.pauses.map(n => `<button data-act="lim-pause" data-v="${n}">${n} ${plural(n, ["день", "дня", "дней"])}</button>`).join("")}</div></div>`;
}
async function openLimits() {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "lim-s");
  const d = await api("limits").catch(() => null);
  if (!el.isConnected) return;
  if (!d) return replaceSheet(el, emptyHTML("shield", "Не удалось загрузить"));
  replaceSheet(el, limHTML(d)); starify(el);
}
async function limSave(body, el) {
  const s = el.closest(".sheet");
  try {
    const d = await post("limits", body); H.ok();
    if (s) { replaceSheet(s, limHTML(d)); starify(s); }
    return d;
  } catch (e) { return null; }
}
Object.assign(ACT, {
  limits: () => openLimits(),
  "lim-set": el => limSave({ dayLoss: +el.dataset.v }, el).then(d => d && toast(d.next ? "Изменится через сутки" : "Лимит сохранён", "ok")),
  "lim-own": el => {
    const v = Math.floor(+($("#lim-v") || {}).value || 0);
    if (v < 100) return toast("Лимит от 100 ⭐");
    limSave({ dayLoss: v }, el).then(d => d && toast(d.next ? "Изменится через сутки" : "Лимит сохранён", "ok"));
  },
  "lim-pause": async el => {
    const n = +el.dataset.v;
    const ok = await modal(`<h3>Перерыв на ${n} ${plural(n, ["день", "дня", "дней"])}?</h3><p style="margin:0 0 16px">Ставки во всех играх закроются. Отменить перерыв раньше срока нельзя.</p>
      <button class="btn" data-m="ok">Взять перерыв</button><button class="btn ghost" data-m="no" style="margin-top:8px">Отмена</button>`).catch(() => null);
    if (!ok) return;
    limSave({ pause: n }, el).then(d => d && toast("Перерыв начался", "ok"));
  },
});

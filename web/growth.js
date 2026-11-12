"use strict";
// ============================================================
//  Приток игроков: подарок от друга, цель на двоих, неделя приглашений (refs.py) и розыгрыши в канале (giveaway.py)
// ============================================================
const gwLeft = s => { s = Math.max(0, s); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600);
  return d ? `${d} д ${h} ч` : h ? `${h} ч ${Math.floor(s % 3600 / 60)} мин` : clock(s); };
const kk = n => n >= 1e6 ? +(n / 1e6).toFixed(1) + "M" : n >= 1e3 ? +(n / 1e3).toFixed(n < 1e4 ? 1 : 0) + "K" : String(Math.floor(n));
const gwTimer = s => s < 3600 ? `<span data-left="${Date.now() / 1000 + s}">${clock(s)}</span>` : gwLeft(s);

// refs/bar: один запрос на минуту на баннер и окно подарка (вкладку «Игры» перерисовывают часто)
let refsBarC = null;
function refsBar(fresh) {
  if (fresh || !refsBarC || Date.now() - refsBarC.t > 60000) refsBarC = { t: Date.now(), p: api("refs/bar").catch(e => { refsBarC = null; throw e; }) };
  return refsBarC.p;
}

// ---------- баннер во вкладке «Игры» ----------
const _rgGrow = renderGames;
renderGames = function () {
  _rgGrow();
  const v = $("#v-games"); if (!v) return;
  refsBar().then(d => {
    if (!v.isConnected || v.querySelector(".ivb-bar")) return;
    let bar = "";
    if (d.duo) {
      const x = d.duo, f = x.me === "friend";
      const my = f ? [x.fTurn, x.fNeed] : [x.rTurn, x.rNeed], ot = f ? [x.rTurn, x.rNeed] : [x.fTurn, x.fNeed];
      bar = `<button class="gd-bar ivb-bar" data-act="inv-open"><span class="gd-art">${ic("users")}</span>
        <span class="grow"><i class="gd-tag">${ic("userPlus")}Цель с другом</i><b>${esc(x.other ? x.other.name : "Друг")}</b>
        <span class="gd-sub"><span>ты</span> ${kk(Math.min(my[0], my[1]))}/${kk(my[1])} · <span>друг</span> ${kk(Math.min(ot[0], ot[1]))}/${kk(ot[1])}</span></span>
        <em class="gd-left">${gwLeft(x.left)}</em>${ic("chev")}</button>`;
    } else if (d.week && d.week.prizes.length) {
      const w = d.week;
      bar = `<button class="gd-bar ivb-bar" data-act="inv-open"><span class="gd-art">${ic("userPlus")}</span>
        <span class="grow"><i class="gd-tag">${ic("crown")}Неделя приглашений</i><b>Призы ${w.prizes.map(p => short(p)).join(" / ")} ⭐</b>
        <span class="gd-sub">${w.place ? `<span>твоё место: ${w.place}</span> · ` : ""}<span>у тебя ${w.mine} ${plural(w.mine, ["активный друг", "активных друга", "активных друзей"])}</span></span></span>
        <em class="gd-left">${gwLeft(w.left)}</em>${ic("chev")}</button>`;
    }
    if (!bar) return;
    const gd = v.querySelector(".gd-bar:not(.ivb-bar)"), before = v.querySelector(".tr-bar"), anchor = v.querySelector(".prib, .evrib");
    if (gd) gd.insertAdjacentHTML("afterend", bar);
    else if (before) before.insertAdjacentHTML("beforebegin", bar);
    else if (anchor) anchor.insertAdjacentHTML("afterend", bar);
    else v.insertAdjacentHTML("afterbegin", bar);
    starify(v.querySelector(".ivb-bar"));
  }).catch(() => {});
};

// ---------- подарок от друга: показываем один раз за запуск, пока ключ не открыт ----------
async function growGift() {
  const d = await refsBar(true).catch(() => null);
  if (!d || !d.gift || document.querySelector(".sheet")) return;
  const g = d.gift;
  const el = openSheet(`<div class="gw-hero inv-gift"><span class="gw-ic">${ic("gift")}</span>
      <h2>Подарок от друга</h2><p><b>${esc(g.name)}</b> <span>зовёт тебя в игру и дарит ключ от кейса</span> <b>${esc(g.title)}</b>. <span>Открой его бесплатно</span></p></div>
    <button class="btn gold gw-go" data-act="gift-open" data-cid="${esc(g.cid)}">${ic("gift")}Открыть кейс</button>`, "gw-s");
  starify(el);
}

// ---------- розыгрыш ----------
function gwHTML(g) {
  const done = g.status === "done", open = g.status === "open" && g.left > 0;
  const state = done ? "Итоги подведены" : g.status === "void" ? "Розыгрыш отменён" : open ? "До итогов" : "Подводим итоги";
  const wins = done ? `<div class="sec-t">Победители</div><div class="box">${g.winnersList.map((u, i) => `<div class="row tap" data-act="profile" data-id="${u.id}">
      <span class="inv-pl">${i + 1}</span>${avaHTML(u, 32)}<div class="grow" style="min-width:0"><div class="t">${esc(u.name)}</div></div><b>+${short(g.each)} ⭐</b></div>`).join("")
      || `<div class="hint" style="padding:14px">Никто не участвовал</div>`}</div>` : "";
  return `<div class="gw-hero"><span class="gw-ic">${ic("gift")}</span><i class="gd-tag">Розыгрыш</i><h2>${esc(g.title)}</h2>
      <div class="gw-prize">⭐ ${fmt(g.prize)}</div>
      <p><span>${g.winners} ${plural(g.winners, ["победитель", "победителя", "победителей"])}</span><span>, каждому ⭐ ${fmt(g.each)}</span></p></div>
    <div class="box">
      <div class="row kv"><div class="grow"><div class="t">Участников</div></div><b>${fmt(g.count)}</b></div>
      <div class="row kv"><div class="grow"><div class="t">${state}</div></div>${open ? `<b>${gwTimer(g.left)}</b>` : ""}</div>
      <div class="row kv"><div class="grow"><div class="t">Условия</div><div class="s" style="white-space:normal"><span>подписка на канал</span>${g.minLevel > 1 ? `<span> и </span><span>${g.minLevel} ур. в игре</span>` : ""}</div></div></div>
    </div>
    ${done ? wins : !open ? "" : g.joined ? `<div class="gw-ok">${ic("check")}<span>Ты участвуешь. Итоги пришлёт бот</span></div>`
      : `<button class="btn gold gw-go" data-act="gw-join" data-id="${g.id}">Участвовать</button>`}
    <div class="sec-t">Честность</div>
    <div class="box gw-fair"><div class="s">Хэш секретного числа</div><code>${esc(g.hash)}</code>
      ${done ? `<div class="s">Число</div><code>${esc(g.seed)}</code>
        <button class="btn sm ghost" data-act="gw-verify" data-id="${g.id}">${ic("check")}Проверить сам</button><div class="gw-vres"></div>`
      : `<div class="s">После итогов число раскроем, и победителей можно будет пересчитать</div>`}</div>`;
}
let GW = null;
async function openGw(id) {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "gw-s");
  GW = await api("gw/" + id).catch(() => null);
  if (!el.isConnected) return;
  if (!GW) return replaceSheet(el, emptyHTML("gift", "Розыгрыш не найден"));
  replaceSheet(el, gwHTML(GW)); starify(el); gdTick();
}
async function sha256hex(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
}

// ---------- запуск: после приветствия, чтобы окна не накладывались ----------
async function growthStart() {
  const wq = +new URLSearchParams(location.search).get("gw");
  if (wq) return openGw(wq);
  setTimeout(() => growGift().catch(() => {}), 900);
}

Object.assign(ACT, {
  "inv-open": () => invite(),
  "gift-open": el => { refsBarC = null; closeSheet(); setTimeout(() => openCase(el.dataset.cid), 250); },
  "gw-join": async el => {
    el.disabled = true;
    try { GW = await post(`gw/${el.dataset.id}/join`); H.ok(); toast("Ты участвуешь", "ok"); }
    catch (e) { el.disabled = false; return; }
    const s = el.closest(".sheet"); if (s) { replaceSheet(s, gwHTML(GW)); starify(s); gdTick(); }
  },
  "gw-verify": async el => {
    const g = GW, box = el.parentNode.querySelector(".gw-vres"); if (!g || !box) return;
    try {
      const okHash = await sha256hex(g.seed) === g.hash;
      const ranked = [];
      for (const u of g.entries) ranked.push([await sha256hex(`${g.seed}:${u}`), u]);
      ranked.sort((a, b) => a[0] < b[0] ? -1 : 1);
      const skip = new Set(g.skipped || []), exp = ranked.map(x => x[1]).filter(u => !skip.has(u)).slice(0, g.winners);
      const got = g.winnerIds || g.winnersList.map(u => u.id), okWin = exp.length === got.length && exp.every((u, i) => u === got[i]);
      box.innerHTML = `<div class="gw-v ${okHash ? "ok" : "bad"}">${ic(okHash ? "check" : "x")}<span>${okHash ? "Хэш совпадает с опубликованным" : "Хэш не совпадает"}</span></div>
        <div class="gw-v ${okWin ? "ok" : "bad"}">${ic(okWin ? "check" : "x")}<span>${okWin ? "Победители пересчитаны и совпадают" : "Победители не совпадают"}</span></div>`;
      H.ok();
    } catch (e) { toast("Проверка недоступна в этом браузере"); }
  },
});

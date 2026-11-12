"use strict";
// ============================================================
//  Оформление профиля: акцентный цвет, статус, значки, узор обложки (бесплатно)
//  и магазин за игровые ⭐ — рамки аватара и эффекты ника на 30 дней.
// ============================================================
let STY = null;
const nickCls = u => u && u.nick ? ` nk nk-${u.nick}` : "";
// имя игрока с эффектом ника — во всех списках
function nameHTML(u) { return `<span class="unm${nickCls(u)}">${esc((u && u.name) || "")}</span>`; }

// купленная рамка — если нет сезонной
const _avaSty = avaHTML;
avaHTML = function (u, s, o) { return _avaSty(u && u.pframe ? { ...u, frame: u.pframe } : u, s, o); };   // купленная рамка важнее бесплатной сезонной; снятая возвращает сезонную

// профиль: акцент, статус под именем, выбранные значки, ник
const _phSty = profileHTML;
profileHTML = function (p, tab) {
  let h = _phSty(p, tab);
  h = h.replace(`<h2>${esc(p.name)}</h2>`, `<h2 class="${nickCls(p).trim()}">${esc(p.name)}</h2>`);
  if (p.status) h = h.replace(/(<div class="pname">[\s\S]*?<\/div>)/, `$1<div class="pstatus">${esc(p.status)}</div>`);
  if (p.badges && p.badges.length) {
    const chips = p.badges.map(t => `<span class="pbadge">${ic(ACH_IC[t] || "award")}${esc(t)}</span>`).join("");
    h = /<div class="pbadges">[\s\S]*?<\/div>/.test(h) ? h.replace(/<div class="pbadges">[\s\S]*?<\/div>/, `<div class="pbadges chosen">${chips}</div>`) : h;
  }
  if (p.id === ME.id) h = h.replace(/(<div class="pacts"><button class="btn ghost" data-act="edit-profile">[^]*?<\/button>)/,
    `$1<button class="btn gold sty-open" data-act="style">${ic("sparkles")}Оформление</button>`);
  return `<div class="pwrap${p.accent ? " acc" : ""}"${p.accent ? ` style="--pac:${p.accent}"` : ""}>${h}</div>`;
};
// узор обложки — из выбранного подарка
const _bnSty = bannerHTML;
bannerHTML = function (p) {
  const g = p.cover && p.gifts && p.gifts.find(x => x.id === p.cover);
  return _bnSty(g ? { ...p, pinned: [g, ...(p.pinned || []).filter(x => x.id !== g.id)] } : p);
};

// ---------------- окно оформления ----------------
const FRAME_NM = { neon: "Неон", ice: "Лёд", fire: "Пламя", toxic: "Токсик", rainbow: "Радуга", diamond: "Бриллиант" };
async function openStyle() {
  H.imp("light");
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"), "sty-s");
  const [d, p] = await Promise.all([api("style").catch(() => null), api("user/" + ME.id).catch(() => null)]);
  if (!d || !p || !el.isConnected) return d && p ? null : closeSheet();
  STY = d; MYP = p;
  el._sty = { ...d.cur, badges: [...d.cur.badges] };
  styDraw(el);
}
function styDraw(el) {
  const st = el._sty, d = STY, p = MYP, own = d.owned, now = Date.now() / 1000;
  const got = p.ach.filter(a => a.got);
  const prevU = { ...ME, nick: st.nick ? st.nick.slice(2) : (d.vip ? "gold" : ""), frame: ME.frame, pframe: st.frame || "" };
  const cover = st.cover && p.gifts.find(g => g.id === st.cover);
  const left = it => { const u = own[it]; return u ? Math.max(1, Math.ceil((u - now) / 86400)) : 0; };
  const shopItem = it => {
    const on = it.kind === "frame" ? st.frame === it.id : st.nick === it.id, has = left(it.id);
    const prev = it.kind === "frame" ? avaHTML({ ...ME, frame: "", pframe: it.id }, 52)
      : `<b class="unm nk nk-${it.id.slice(2)}">${esc(ME.name)}</b>`;
    return `<div class="sty-it${on ? " on" : ""}${has ? " has" : ""}"><div class="sty-pv ${it.kind}">${prev}</div><b>${esc(it.name)}</b>
      ${has ? `<small>ещё ${has} ${plural(has, ["день", "дня", "дней"])}</small>
        <div class="sty-bt"><button class="btn sm ${on ? "ghost" : ""}" data-act="sty-wear" data-id="${it.id}">${on ? "Снять" : "Надеть"}</button>
        <button class="btn sm ghost" data-act="sty-buy" data-id="${it.id}" title="Продлить">+${d.days} дн.</button></div>`
      : `${it.full > it.price ? `<s class="sty-full">⭐ ${short(it.full)}</s>` : ""}<button class="btn sm gold" data-act="sty-buy" data-id="${it.id}">⭐ ${short(it.price)}</button>`}</div>`;
  };
  replaceSheet(el, `<h2 class="gtitle">Оформление</h2>
    <div class="sty-prev pwrap acc" style="--pac:${st.accent || "var(--accent)"}">${avaHTML(prevU, 64, { ring: true, p: 100 })}
      <div><b class="unm${nickCls(prevU)}">${esc(ME.name)}</b><span>${esc(st.status) || "без статуса"}</span>
      ${st.badges.length ? `<div class="pbadges chosen">${st.badges.map(t => `<span class="pbadge">${ic(ACH_IC[t] || "award")}${esc(t)}</span>`).join("")}</div>` : ""}</div></div>
    <div class="sec-t">Статус <span id="sty-cnt">${st.status.length}/${d.statusMax}</span></div>
    <input id="sty-status" maxlength="${d.statusMax}" placeholder="Короткая фраза — видна в топах и у друзей" value="${esc(st.status)}">
    <div class="sec-t">Цвет профиля</div>
    <div class="sty-acc">${d.accents.map(c => `<button data-act="sty-acc" data-v="${c}" class="${c === st.accent ? "on" : ""}" style="--c:${c || "var(--card)"}">${c ? "" : ic("x")}</button>`).join("")}</div>
    <div class="sec-t">Значки рядом с именем · до 3</div>
    ${got.length ? `<div class="sty-bdg">${got.map(a => `<button data-act="sty-bdg" data-v="${esc(a.t)}" class="${st.badges.includes(a.t) ? "on" : ""}">${ic(ACH_IC[a.t] || "award")}${esc(a.t)}</button>`).join("")}</div>`
      : `<div class="hint" style="font-size:12.5px">Пока нет достижений — открой кейсы и сыграй пару игр</div>`}
    <div class="sec-t">Узор обложки</div>
    <div class="sty-cov"><div class="sty-cv">${cover ? giftHTML(cover, { lite: true, plain: true }) : `<span>${ic("sparkles")}</span>`}</div>
      <div class="grow"><b>${cover ? giftName(cover) : "Авто"}</b><span>${cover ? "фон и узор из этого подарка" : "из первого подарка витрины"}</span></div>
      ${p.gifts.length ? `<button class="btn sm ghost" data-act="sty-cover">Выбрать</button>` : ""}${cover ? `<button class="ibtn" data-act="sty-cover0">${ic("x")}</button>` : ""}</div>
    ${d.discount ? `<div class="sty-disc">${ic("crown")}Скидка клана −${d.discount}% на рамки и ники</div>` : ""}
    <div class="sec-t">Рамки аватара · ${d.days} дней</div>
    <div class="sty-grid">${d.items.filter(i => i.kind === "frame").map(shopItem).join("")}</div>
    <div class="sec-t">Эффект ника · ${d.days} дней</div>
    ${d.vip ? `<div class="hint" style="font-size:12px;margin:-4px 0 8px">У тебя VIP — золотой ник уже включён бесплатно</div>` : ""}
    <div class="sty-grid nick">${d.items.filter(i => i.kind === "nick").map(shopItem).join("")}</div>
    <div class="esave"><button class="btn cta" data-act="sty-save">${ic("check")}Сохранить</button></div>`);
  starify(el);
  const inp = el.querySelector("#sty-status");
  inp.oninput = () => { st.status = inp.value; el.querySelector("#sty-cnt").textContent = `${inp.value.length}/${d.statusMax}`; el.querySelector(".sty-prev span").textContent = inp.value || "без статуса"; };
}
async function stySave(quiet) {
  const el = SHEETS.find(s => s._sty); if (!el) return;
  const st = el._sty;
  await post("style", { accent: st.accent, status: st.status, badges: st.badges, cover: st.cover || 0, frame: st.frame, nick: st.nick });
  await loadMe();
  if (!quiet) { H.ok(); toast("Оформление сохранено", "ok"); closeSheet(); }
  refreshProfileSheets();
}
Object.assign(ACT, {
  style: () => openStyle(),
  "sty-acc": el => { const s = topSheet(); s._sty.accent = el.dataset.v; H.sel(); styDraw(s); },
  "sty-bdg": el => {
    const s = topSheet(), b = s._sty.badges, v = el.dataset.v;
    if (b.includes(v)) b.splice(b.indexOf(v), 1); else if (b.length >= 3) return toast("Максимум 3 значка"); else b.push(v);
    H.sel(); styDraw(s);
  },
  "sty-cover": () => {
    const s = topSheet();
    pickGift("Узор обложки", g => { s._sty.cover = g.id; styDraw(s); });
  },
  "sty-cover0": () => { const s = topSheet(); s._sty.cover = 0; H.sel(); styDraw(s); },
  "sty-wear": el => {
    const s = topSheet(), id = el.dataset.id, k = id.startsWith("n-") ? "nick" : "frame";
    s._sty[k] = s._sty[k] === id ? "" : id; H.sel(); styDraw(s);
  },
  "sty-buy": async el => {
    const it = STY.items.find(x => x.id === el.dataset.id); if (!it) return;
    const has = STY.owned[it.id];
    if (!await confirmM(`${has ? "Продлить" : "Купить"} «${it.name}»?`, `⭐ ${fmt(it.price)} за ${STY.days} дней.${has ? " Срок добавится к оставшемуся." : " Сразу наденется."}`, has ? "Продлить" : "Купить")) return;
    el.disabled = true;
    try {
      const r = await post("style/buy/" + it.id); setStars(r.stars); H.ok(); toast(has ? "Срок продлён" : "Куплено и надето", "ok");
      const s = SHEETS.find(x => x._sty); if (!s) return;
      STY.owned[it.id] = r.until;
      s._sty[it.kind] = it.id;
      styDraw(s);
      await loadMe(); refreshProfileSheets();
    } catch (e) {} finally { el.disabled = false; }
  },
  "sty-save": () => stySave(),
});

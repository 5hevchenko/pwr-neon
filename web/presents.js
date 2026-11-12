"use strict";
// ============================================================
//  Подарить подарок с открыткой: игроку или по ссылке любому. Распаковка подарка по ссылке.
// ============================================================
let PR = null;
async function openPresent(g) {
  PR = { g, mode: "player", to: null, friends: null };
  const el = openSheet(`<h2 class="gtitle">${ic("gift")} Подарить</h2>
    <div class="pr-card"><div class="pr-g">${giftHTML(g, { big: true })}</div>
      <div class="pr-note"><span>Открытка</span><textarea id="pr-t" maxlength="120" rows="3" placeholder="С днём рождения! 🎉"></textarea></div></div>
    <div class="seg" id="pr-m"><button data-act="pr-mode" data-v="player" class="on">${ic("users")}Игроку</button><button data-act="pr-mode" data-v="link">${ic("send")}По ссылке</button></div>
    <div id="pr-body"></div>`, "pr-s");
  startLottie(el);
  prBody();
}
async function prBody() {
  const b = $("#pr-body"); if (!b) return;
  if (PR.mode === "link") {
    b.innerHTML = `<div class="pr-linkinfo">${ic("send")}<div><b>Подарок по ссылке</b><span>Отправь ссылку кому угодно в Telegram — даже тому, кто ещё не играет. Друг откроет и заберёт подарок, а ты получишь бонус за приглашение. Не открыли за 7 дней — подарок вернётся.</span></div></div>
      <button class="btn gold cta" data-act="pr-link">${ic("gift")}Создать ссылку-подарок</button>`;
    return;
  }
  if (!PR.friends) PR.friends = (await api("friends").catch(() => ({ friends: [] }))).friends;
  b.innerHTML = `<label class="pr-search">${ic("search")}<input id="pr-q" placeholder="Найти игрока: имя или @ник"></label>
    <div class="box" id="pr-list"></div>
    <button class="btn gold cta" data-act="pr-send" id="pr-send" disabled style="margin-top:12px">${ic("gift")}Выбери получателя</button>`;
  const paint = list => {
    $("#pr-list").innerHTML = list.length ? list.map(u => `<div class="row tap${PR.to && PR.to.id === u.id ? " sel" : ""}" data-act="pr-to" data-id="${u.id}" data-n="${esc(u.name)}">${avaHTML(u, 34)}
      <div class="grow"><div class="t">${esc(u.name)}</div><div class="s">${u.username ? "@" + esc(u.username) : u.level + " ур."}</div></div><span class="pr-check">${ic("check")}</span></div>`).join("")
      : `<div class="hint" style="padding:14px;text-align:center">${PR.friends.length ? "Никого не нашли" : "Друзей пока нет — найди игрока поиском или подари по ссылке"}</div>`;
  };
  paint(PR.friends);
  let t; $("#pr-q").oninput = e => { clearTimeout(t); const v = e.target.value.trim(); t = setTimeout(async () => paint(v.length >= 2 ? await api("users/search?qs=" + encodeURIComponent(v)).catch(() => []) : PR.friends), 300); };
}
// распаковка подарка по ссылке
async function openPresentClaim(code) {
  let info; try { info = await api("giftlink/" + code); } catch (e) { return; }
  const el = openSheet(`<div class="pcw">
      <div class="pc-from">${info.sender ? avaHTML(info.sender, 44) : ""}<div><span>Подарок от</span><b>${esc(info.sender ? info.sender.name : "друга")}</b></div></div>
      ${info.text ? `<div class="pc-text">«${esc(info.text)}»</div>` : ""}
      <div class="pc-stage" id="pc-st">${info.status === "open" && !info.mine
        ? `<button class="pc-box" data-act="pc-open" data-code="${esc(code)}"><i class="lid"></i><i class="body"></i><i class="ribbon"></i><span>Нажми, чтобы открыть</span></button>`
        : `<div class="hint" style="text-align:center;padding:30px 10px">${info.mine ? "Это твой подарок — отправь ссылку другу" : info.status === "taken" ? "Этот подарок уже открыли" : "Срок подарка истёк"}</div>`}</div></div>`, "pc-s");
  el._code = code;
}
Object.assign(ACT, {
  present: el => openPresent(topSheet()._o.g),
  "pr-mode": el => { PR.mode = el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); prBody(); },
  "pr-to": el => {
    PR.to = { id: +el.dataset.id, name: el.dataset.n }; H.sel();
    document.querySelectorAll("#pr-list .row").forEach(r => r.classList.toggle("sel", r === el));
    const b = $("#pr-send"); b.disabled = false; b.innerHTML = `${ic("gift")}Подарить: ${esc(PR.to.name)}`;
  },
  "pr-send": async () => {
    if (!PR.to) return;
    if (!await confirmM("Подарить?", `${esc(PR.g.col)} «${esc(PR.g.model)}» уйдёт игроку ${esc(PR.to.name)}. Вернуть нельзя.`, "Подарить")) return;
    await post(`gift/${PR.g.id}/send`, { to: PR.to.id, text: $("#pr-t").value }); H.ok(); toast("Подарок отправлен!", "ok");
    burstAt($(".pr-g"), PR.g); closeSheet(); closeSheet(); if (typeof giftChanged === "function") giftChanged();
  },
  "pr-link": async () => {
    const r = await post(`gift/${PR.g.id}/link`, { text: $("#pr-t").value }); H.ok();
    const text = `🎁 Держи подарок — ${PR.g.col}! Жми, чтобы распаковать`;
    $("#pr-body").innerHTML = `<div class="pr-done">${ic("check")}<b>Ссылка готова</b><span>${esc(r.link)}</span></div>
      <button class="btn gold cta" data-act="pr-share" data-l="${esc(r.link)}" data-t="${esc(text)}">${ic("send")}Отправить в Telegram</button>`;
    if (typeof giftChanged === "function") giftChanged();
  },
  "pr-share": el => { const url = `https://t.me/share/url?url=${enc(el.dataset.l)}&text=${enc(el.dataset.t)}`; if (inTg) tg.openTelegramLink(url); else { navigator.clipboard?.writeText(el.dataset.l); toast("Ссылка скопирована"); } },
  "pc-open": async el => {
    el.classList.add("opening"); H.imp("heavy");
    let r; try { r = await post(`giftlink/${el.dataset.code}/claim`); } catch (e) { el.classList.remove("opening"); return; }
    await sleep(700);
    const st = $("#pc-st"); if (!st) return;
    st.innerHTML = `<div class="pc-won">${giftHTML(r.gift, { big: true })}<h2>${esc(r.gift.col)}</h2><div class="hint">${esc(r.gift.model)} · ⭐ ${fmt(r.gift.value)}</div>
      <button class="btn gold" data-act="close" style="margin-top:14px">Забрать в сумку</button></div>`;
    startLottie(st); starify(st); H.ok(); burstAt(st.querySelector(".gift"), r.gift);
    setTimeout(() => { const im = st.querySelector(".gift > img"); if (im && typeof flyToBag === "function") flyToBag(im); }, 1400);
  },
});

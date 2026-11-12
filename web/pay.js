"use strict";
// ============================================================
//  «Кошелёк» в стиле WeChat: баланс крупно, «Сканировать» / «Получить» (свой QR с аватаркой), перевод звёзд игроку.
//  QR ведёт на бота (t.me/<бот>?start=pay_<id>[_<сумма>]) — работает и из сканера в игре, и из обычной камеры.
// ============================================================
Object.assign(ICONS, {
  xfer: '<path d="M7 3l1.1 2.8 3 .2-2.3 1.9.7 2.9L7 9.2l-2.5 1.6.7-2.9L2.9 6l3-.2Z" fill="currentColor" stroke-width="1"/><path d="M17 12.6l1.1 2.8 3 .2-2.3 1.9.7 2.9-2.5-1.6-2.5 1.6.7-2.9-2.3-1.9 3-.2Z" fill="currentColor" stroke-width="1"/><path d="M12.6 3.6a8.6 8.6 0 0 1 7.8 7.2"/><path d="m18.3 9.3 2.1 1.6 1.7-2.1"/><path d="M11.4 20.4a8.6 8.6 0 0 1-7.8-7.2"/><path d="m5.7 14.7-2.1-1.6-1.7 2.1"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M3 12h18"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
  qr: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20v.01M17 20h4v-3"/>',
});

const PAY = { info: null, friends: null, busy: false, seq: 0 };
const payAddrShort = a => a.length <= 14 ? a : a.slice(0, 6) + "…" + a.slice(-4);
// адрес кошелька NP + 20 символов: показываем группами по 4, копируем слитно
// свой адрес от админа (любой, 3–32 знака) показываем как есть
const payAddrFmt = a => !a ? "" : /^NP[0-9A-Z]{20}$/.test(a) ? "NP " + a.slice(2).match(/.{1,4}/g).join(" ") : a;
const payAddrMaybe = v => /^[0-9A-Z]{3,32}$/.test(String(v || "").toUpperCase().replace(/[\s-]/g, ""));
const payAddrLike = v => /^NP[0-9A-Z]{20}$/.test(String(v || "").toUpperCase().replace(/[\s-]/g, ""));
function payCopy(a, msg) {
  const ok = () => { H.ok(); toast(msg, "ok"); };
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(a).then(ok, () => copyFallback(a, ok)); else copyFallback(a, ok);
}
async function payByAddr(a) {
  const n = String(a).replace(/[\s-]/g, "");
  try { const u = await api("pay/addr/" + enc(n)); if (u.bank) openBankGift(); else openPaySend(u.id, 0, n); return true; }
  catch (e) { return false; }
}
const payTime = ts => new Date(ts * 1000).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
function payDay(ts) {
  const d = new Date(ts * 1000), t = new Date(), y = new Date(Date.now() - 864e5);
  if (d.toDateString() === t.toDateString()) return "Сегодня";
  if (d.toDateString() === y.toDateString()) return "Вчера";
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

// крупный баланс: цифры «набегают» от нуля, потом поле живое (класс bal-live — обновляется вместе с балансом в шапке)
function payCount(el, to) {
  if (!el) return;
  if (window.LITE) { el.textContent = fmt(to); el.classList.add("bal-live"); return; }
  const t0 = performance.now(), d = 700;
  const step = t => {
    const k = Math.min(1, (t - t0) / d), e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(to * e);
    if (k < 1) requestAnimationFrame(step); else { el.classList.add("bal-live"); el.textContent = fmt(ME.stars); }
  };
  requestAnimationFrame(step);
}

// анонимный получатель (пасхалка с адресом): серый аватар с «?» вместо фото
const payAva = (u, s) => u.anon ? `<div class="ava pay-anon" style="--s:${s}px"><span>?</span></div>` : avaHTML(u, s);
const payRow = x => `<div class="row pay-row${x.user.anon ? "" : " tap"}"${x.user.anon ? "" : ` data-act="pay-to" data-id="${x.user.id}"`}>${payAva(x.user, 40)}<div class="grow"><div class="t">${esc(x.user.name)}</div>
  <div class="s">${x.in ? "Входящий" : "Исходящий"} · ${payTime(x.ts)}${x.note ? " · «" + esc(x.note) + "»" : ""}</div></div>
  <b class="pay-d ${x.in ? "in" : ""}">${x.in ? "+" : "−"}${fmt(x.amount)} ⭐</b></div>`;
function payHistory(list) {
  if (!list.length) return `<div class="box"><div class="pay-none">${ic("xfer")}<span>Переводов пока не было</span></div></div>`;
  let out = "", day = "";
  for (const x of list) {
    const d = payDay(x.ts);
    if (d !== day) { out += (day ? "</div>" : "") + `<div class="pay-day">${d}</div><div class="box">`; day = d; }
    out += payRow(x);
  }
  return out + "</div>";
}
const payPeer = (u, tag, addr) => `<button class="pay-peer" data-act="pay-to" data-id="${u.id}"${addr ? ` data-addr="${esc(addr)}"` : ""}>${payAva(u, 50)}<span>${esc(u.name)}</span>${tag ? `<i>${tag}</i>` : ""}</button>`;
// недавние получатели/отправители из истории + друзья, без повторов
function payPeers() {
  const seen = new Set(), out = [];
  for (const x of (PAY.info && PAY.info.history) || []) if (!x.user.anon && !seen.has(x.user.id)) { seen.add(x.user.id); out.push(payPeer(x.user, "недавно")); }
  for (const u of PAY.friends || []) if (!seen.has(u.id)) { seen.add(u.id); out.push(payPeer(u)); }
  return out.slice(0, 20).join("") || `<div class="hint pay-empty">Добавь друзей или найди игрока поиском</div>`;
}

async function openPay(el) {
  H.imp("light");
  if (!el) el = openSheet(emptyHTML("hourglass", "Загружаем…"), "pay-s");
  let r, fr;
  try { [r, fr] = await Promise.all([api("pay"), api("friends").catch(() => ({ friends: [] }))]); } catch (e) { if (SHEETS.includes(el)) closeSheet(); return; }
  if (!el.isConnected) return;
  PAY.info = r; PAY.friends = fr.friends || [];
  setStars(r.stars);
  const w = r.week || { in: 0, out: 0 };
  replaceSheet(el, `<div class="pay-hero">
      <div class="pay-card" id="pay-card"><span class="pay-gloss"></span><span class="pay-spark"></span>
        <div class="pay-bal"><span class="pay-st">⭐</span><span class="pay-num">0</span></div>
        <button class="pay-chg" data-act="pay-hist"><span class="in">+${short(w.in)}</span><i></i><span>−${short(w.out)}</span><small>за 7 дней</small>${ic("chev")}</button>
        <button class="pay-who" data-act="pay-recv">${esc(ME.username || ME.name)}${ic("qr")}</button>
      </div>
    </div>
    <div class="pay-acts">
      <button data-act="daily"><span class="pay-ic">${ic("plus")}</span><b>Пополнить</b></button>
      <button data-act="pay-send"><span class="pay-ic">${ic("xfer")}</span><b>Отправить</b></button>
      <button data-act="pay-recv"><span class="pay-ic">${ic("qr")}</span><b>Получить</b></button>
      <button data-act="pay-scan"><span class="pay-ic">${ic("scan")}</span><b>Сканер</b></button>
    </div>
    ${r.addr ? `<button class="pay-addrrow" data-act="pay-addr-copy" data-a="${esc(r.addr)}"><span>Адрес кошелька</span><code>${payAddrShort(r.addr)}</code>${ic("copy")}</button>` : ""}
    <div class="pay-gifts" id="pay-gifts"></div>
    ${r.on === false ? `<div class="adm-warn">Переводы временно отключены администрацией</div>` : ""}
    <div class="pay-find">${ic("search")}<input class="pay-q" placeholder="Имя, @username или адрес NP…" autocomplete="off" autocapitalize="off" spellcheck="false"></div>
    <div class="pay-peers">${payPeers()}</div>
    <div class="sec-t" id="pay-hist-t">История переводов</div>
    ${payHistory(r.history)}
    <p class="hint pay-note">Комиссия ${+(r.fee * 100).toFixed(2)}%</p>
    <div class="pay-rbtns"><button class="pay-link" data-act="pay-pin-change">${ic("lock")}Сменить пароль</button><button class="pay-link" data-act="pay-pin-forgot">Забыл пароль</button></div>`);
  starify(el);
  payCount(el.querySelector(".pay-num"), r.stars);
  api("user/" + ME.id).then(u => {
    const box = $("#pay-gifts"), g = (u.gifts || []).slice().sort((a, b) => b.value - a.value).slice(0, 6);
    if (box && g.length) box.innerHTML = `<div class="sec-t">Подарки</div><div class="pay-ggrid">${g.map(x => `<button data-act="gift" data-k="${reg({ g: x, mine: true })}">${giftHTML(x, { lite: true, plain: true })}</button>`).join("")}</div>`;
  }).catch(() => {});
  if (!r.pin && !(await payPinSetup())) { if (el.isConnected) closeSheet(); return; }   // без пароля кошелёк не открываем
  let t;
  el.querySelector(".pay-q").oninput = e => {
    clearTimeout(t);
    const v = e.target.value.trim(), my = ++PAY.seq;
    t = setTimeout(async () => {
      const box = el.querySelector(".pay-peers");
      if (v.length < 2) { box.innerHTML = payPeers(); return; }
      if (payAddrLike(v)) {   // вставили адрес кошелька — ищем владельца
        const u = await api("pay/addr/" + enc(v.replace(/[\s-]/g, ""))).catch(() => null);
        if (my !== PAY.seq || !el.isConnected) return;
        box.innerHTML = u ? payPeer(u, "по адресу", v.replace(/[\s-]/g, "")) : `<div class="hint pay-empty">Кошелёк с таким адресом не найден</div>`;
        return;
      }
      // заодно ищем по адресу: у кого-то он свой, словом (например DUROV777)
      const [list, fa] = await Promise.all([api("users/search?qs=" + enc(v)).catch(() => []),
        payAddrMaybe(v) ? api("pay/addrfind/" + enc(v.replace(/[\s-]/g, ""))).catch(() => null) : null]);
      if (my !== PAY.seq || !el.isConnected) return;   // пока ждали ответ, запрос уже поменялся
      box.innerHTML = (fa && fa.user ? payPeer(fa.user, "по адресу", fa.addr) : "") + list.filter(u => !(fa && fa.user && fa.user.id === u.id)).map(u => payPeer(u)).join("")
        || `<div class="hint pay-empty">Никого не нашли</div>`;
    }, 300);
  };
}

// «Получить»: свой QR с аватаркой в центре, по желанию — с суммой
function openPayRecv(amt = 0) {
  H.imp("light");
  const link = ME.refLink.replace(/start=.*$/, `start=pay_${ME.id}${amt ? "_" + amt : ""}`);
  let qr = ""; try { qr = qrSVG(link).svg; } catch (e) {}
  const html = `<div class="pay-rc">
      <div class="pay-qrwrap"><div class="inv-code pay-code">${qr}<span class="inv-logo">${avaHTML(ME, 48)}</span></div></div>
      <b class="pay-rname">${esc(ME.name)}</b>
      ${amt ? `<div class="pay-ramt"><span class="pay-st">⭐</span>${fmt(amt)}</div>` : ""}
      ${PAY.info && PAY.info.addr ? `<button class="pay-addr" data-act="pay-addr-copy" data-a="${esc(PAY.info.addr)}"><span>${payAddrShort(PAY.info.addr)}</span>${ic("copy")}</button>` : ""}
    </div>
    <div class="pay-racts">
      <button class="btn cta" data-act="pay-share" data-l="${esc(link)}" data-v="${amt}">${ic("send")}Поделиться</button>
      <button class="btn ghost" data-act="pay-amt" data-v="${amt}">${amt ? "Изменить сумму" : "Указать сумму"}</button>
      ${amt ? `<button class="pay-link" data-act="pay-amt-clear">Без суммы</button>` : ""}
      <button class="pay-link" data-act="pay-print">${ic("download")}QR для печати</button>
    </div>`;
  const top = SHEETS[SHEETS.length - 1];
  if (top && top.classList.contains("pay-r")) replaceSheet(top, html); else openSheet(html, "pay-r");
  starify(SHEETS[SHEETS.length - 1]);
}

function payParse(text) {
  const m = /(?:pay|ref)_(\d+)(?:_(\d+))?/.exec(text || "") || /[?&]pay=(\d+)(?:&amt=(\d+))?/.exec(text || "");
  return m ? { id: +m[1], amt: +(m[2] || 0) } : null;
}

function payScan() {
  H.imp("light");
  if (inTg && tg.showScanQrPopup && (!tg.isVersionAtLeast || tg.isVersionAtLeast("6.4"))) {
    tg.showScanQrPopup({ text: "Наведи камеру на QR-код игрока" }, text => {
      const p = payParse(text);
      if (!p && payAddrLike(text)) { H.ok(); setTimeout(() => payByAddr(text), 60); return true; }
      if (!p) { H.err(); return false; }   // чужой QR — сканер остаётся открытым
      H.ok();
      setTimeout(() => openPaySend(p.id, p.amt), 60);
      return true;
    });
    return;
  }
  promptM("Перевод по адресу", "Сканер QR работает в Telegram на телефоне. Здесь можно ввести адрес кошелька (NP…) или id игрока:", "", "Дальше").then(v => {
    if (payAddrLike(v)) { payByAddr(v); return; }
    const id = /^\d+$/.test(String(v || "").trim()) ? parseInt(v, 10) : 0; if (id > 0) { openPaySend(id, 0); return; }
    if (payAddrMaybe(v)) payByAddr(v);
  });
}

// экран перевода конкретному игроку
async function openPaySend(id, amt = 0, addr = "") {
  if (PAY.busy) return;   // двойной тап не открывает два экрана
  PAY.busy = true;
  let u, info;
  try { [u, info] = await Promise.all([api(addr ? "pay/addr/" + enc(addr) : "pay/peer/" + id), api("pay").catch(() => PAY.info || { fee: 0.05, min: 10 })]); }
  catch (e) { return; } finally { PAY.busy = false; }
  PAY.info = info;
  const fee = addr && info.feeAddr != null ? info.feeAddr : info.fee, min = info.min || 10, max = info.max || 0, fp = +(fee * 100).toFixed(2);
  const el = openSheet(`<div class="pay-to">${payAva(u, 78)}<span class="pay-tl">Перевод игроку</span><b>${esc(u.name)}</b><span>${addr ? "по адресу " + payAddrFmt(addr.toUpperCase()) : u.username ? "@" + esc(u.username) : "id " + u.id}</span></div>
    <div class="pay-amt"><label>Сумма перевода</label>
      <div class="pay-ai"><span class="pay-st">⭐</span><input class="pay-a" inputmode="numeric" placeholder="0" value="${amt || ""}" autocomplete="off" maxlength="15"></div>
      <div class="pay-ab">Баланс: <b class="bal-live">${fmt(ME.stars)}</b> ⭐</div></div>
    <div class="pay-chips">${[100, 1000, 10000, 100000].map(v => `<button data-act="pay-chip" data-v="${v}">+${short(v)}</button>`).join("")}<button data-act="pay-chip" data-v="all">Всё</button></div>
    <div class="pay-sum"></div>
    <input class="pay-memo" maxlength="60" placeholder="Комментарий (необязательно)" autocomplete="off">
    <button class="btn gold pay-go" data-act="pay-go">${ic("send")}Перевести</button>`, "pay-x");
  el._peer = u; el._addr = addr;
  starify(el);
  const inp = el.querySelector(".pay-a"), box = el.querySelector(".pay-sum"), go = el.querySelector(".pay-go");
  const upd = () => {
    const a = payAmt(el), f = Math.ceil(a * fee);
    const txt = a ? fmt(a) : "";
    if (inp.value !== txt) inp.value = txt;
    let warn = "";
    if (info.on === false) warn = "Переводы временно отключены";
    else if (a && a < min) warn = `Минимум ${fmt(min)} ⭐`;
    else if (max && a > max) warn = `За один раз не больше ${fmt(max)} ⭐`;
    else if (a + f > ME.stars) warn = "Не хватает звёзд с учётом комиссии";
    box.innerHTML = `<div><span>Получит</span><b>${fmt(a)} ⭐</b></div><div><span>Комиссия ${fp}%</span><b>${fmt(f)} ⭐</b></div>
      <div class="tot"><span>Спишется</span><b>${fmt(a + f)} ⭐</b></div>${warn ? `<p class="tl">${warn}</p>` : !a ? `<p>Минимум ${fmt(min)} ⭐${max ? ` · максимум ${fmt(max)} ⭐` : ""}</p>` : ""}`;
    go.disabled = !a || !!warn;
    el.querySelector(".pay-amt").classList.toggle("bad", !!warn && !!a);
    starify(box);
  };
  el._upd = upd; el._fee = fee;
  inp.oninput = upd; upd();
  if (!amt) setTimeout(() => inp.focus(), 350);
}

const payAmt = el => Math.min(1e12, parseInt((el.querySelector(".pay-a").value || "").replace(/\D/g, ""), 10) || 0);

Object.assign(ACT, {
  "pay-hist": () => { const t = $("#pay-hist-t"); if (t) t.scrollIntoView({ block: "start", behavior: "smooth" }); },
  "pay-pin-forgot": async () => { const p = await payPinForgot(); if (p) toast("Пароль обновлён", "ok"); },
  "pay-send": () => { const q = document.querySelector(".pay-q"); if (q) { q.scrollIntoView({ block: "center", behavior: "smooth" }); q.focus(); } },
  pay: () => openPay(),
  "pay-scan": () => payScan(),
  "pay-recv": () => openPayRecv(0),
  "pay-addr-copy": el => {
    // пасхалка: 5 нажатий подряд (без пауз дольше 1.5 с) — анонимный адрес.
    // Копируем синхронно, прямо в обработчике тапа: после await Telegram на Android не даёт писать в буфер обмена.
    const t = Date.now(); PAY.taps = t - (PAY.tapT || 0) < 1500 ? (PAY.taps || 0) + 1 : 1; PAY.tapT = t;
    if (PAY.taps === 3 && !PAY.anon) api("pay/anon").then(r => { PAY.anon = r.addr; }).catch(() => {});   // подгружаем заранее
    if (PAY.taps < 5) return payCopy(el.dataset.a, "Адрес кошелька скопирован");
    PAY.taps = 0; H.imp("heavy");
    const show = a => {
      payCopy(a, "🕶 Анонимный адрес скопирован");
      openSheet(`<div class="pay-anon-s">${payAva({ anon: true }, 72)}<h3>Анонимный адрес</h3>
        <p class="hint">Кто переведёт на него звёзды, увидит получателя как «Неизвестный пользователь». Звёзды придут тебе.</p>
        <button class="pay-raddr" data-act="pay-copy" data-a="${esc(a)}"><small>Нажми, чтобы скопировать</small><span>${payAddrFmt(a)}</span>${ic("copy")}</button></div>`, "pay-an");
      if (typeof eggFound === "function") setTimeout(() => eggFound("anon"), 1200);
    };
    if (PAY.anon) show(PAY.anon); else api("pay/anon").then(r => show(PAY.anon = r.addr)).catch(() => {});
  },
  "pay-copy": el => payCopy(el.dataset.a, "Адрес скопирован"),
  "pay-to": el => openPaySend(+el.dataset.id, 0, el.dataset.addr || ""),
  "pay-amt": async el => {
    const v = await promptM("Сумма", "Сколько звёзд попросить? QR обновится с этой суммой", el.dataset.v !== "0" ? el.dataset.v : "", "Готово");
    const a = parseInt(String(v || "").replace(/\D/g, ""), 10) || 0;
    if (v != null) openPayRecv(Math.min(a, 1e9));
  },
  "pay-amt-clear": () => openPayRecv(0),
  "pay-share": el => {
    const a = +el.dataset.v, text = a ? `Переведи мне ${fmt(a)} ⭐ в игре` : "Мой кошелёк в игре — переводи звёзды по ссылке";
    const url = `https://t.me/share/url?url=${enc(el.dataset.l)}&text=${enc(text)}`;
    if (inTg) tg.openTelegramLink(url); else copyText(el.dataset.l);
  },
  "pay-chip": el => {
    const s = el.closest(".sheet"); if (!s || !s._upd) return;
    H.sel();
    let a = el.dataset.v === "all" ? Math.floor(ME.stars / (1 + s._fee)) : payAmt(s) + +el.dataset.v;
    if (el.dataset.v === "all") while (a > 0 && a + Math.ceil(a * s._fee) > ME.stars) a--;
    if (PAY.info && PAY.info.max) a = Math.min(a, PAY.info.max);
    s.querySelector(".pay-a").value = String(Math.max(0, a)); s._upd();
  },
  "pay-go": async el => {
    const s = el.closest(".sheet"), u = s._peer, a = payAmt(s);
    if (s._sending || !a) return;   // двойной тап — одно подтверждение
    s._sending = true;
    if (!(PAY.info && PAY.info.pin)) {   // перевод из сканера, кошелёк ещё не открывали — пароль мог быть не задан
      const st = await api("pay").catch(() => null);
      if (st) PAY.info = { ...(PAY.info || {}), ...st };
      if (st && !st.pin && !(await payPinSetup())) { s._sending = false; return; }
    }
    const pin = await pinPad(`Перевод ${fmt(a)} ⭐`, `${esc(u.name)} получит ${fmt(a)} ⭐ · введи пароль кошелька`, { forgot: true });
    if (!pin) { s._sending = false; return; }
    el.disabled = true;
    const note = s.querySelector(".pay-memo").value.trim();
    let r;
    try { r = await post("pay/send", s._addr ? { addr: s._addr, amount: a, note, pin } : { to: u.id, amount: a, note, pin }); } catch (e) { el.disabled = false; s._sending = false; return; }
    H.ok(); setStars(r.stars);
    if (r.amount === 1337 && typeof eggFound === "function") setTimeout(() => { toast("👾 1337 ⭐ — ты из наших", "ok"); eggFound("leet"); }, 900);
    replaceSheet(s, `<div class="pay-done"><div class="pay-ok">${ic("check")}</div><b>Перевод отправлен</b>
      <div class="pay-dsum"><span class="pay-st">⭐</span>${fmt(r.amount)}</div>
      <div class="pay-rcpt">
        <div><span>Получатель</span><b class="pay-who">${payAva(u, 22)}${esc(u.name)}</b></div>
        <div><span>Комиссия</span><b>${fmt(r.fee)} ⭐</b></div>
        <div><span>Списано</span><b>${fmt(r.amount + r.fee)} ⭐</b></div>
        ${note ? `<div><span>Комментарий</span><b>«${esc(note.slice(0, 60))}»</b></div>` : ""}
        <div><span>Время</span><b>${payTime(Date.now() / 1000)}</b></div>
        <div class="tot"><span>На балансе</span><b>${fmt(r.stars)} ⭐</b></div></div></div>
      <button class="btn gold" data-act="pay-done">Готово</button>`);
    starify(s);
    burstAt(s.querySelector(".pay-ok"));
  },
  "pay-pin-change": async () => {
    const old = await pinPad("Текущий пароль", "Введи пароль кошелька", { forgot: true }); if (!old) return;
    const pin = await payPinTwice("Новый пароль"); if (!pin) return;
    await post("pay/pin", { old, pin }); H.ok(); toast("Пароль изменён", "ok");
  },
  "pay-print": async el => {
    el.disabled = true;
    try {
      const blob = await payQrPng();
      const headers = { "Content-Type": "image/png" };
      if (inTg) headers["X-Init-Data"] = tg.initData; else if (DEV_USER) headers["X-Dev-User"] = DEV_USER;
      const r = await fetch("api/pay/qr/send", { method: "POST", headers, body: blob }), d = await r.json().catch(() => null);
      if (!r.ok) throw new Error(d && d.detail || "не получилось");
      H.ok(); toast("Бот прислал QR в чат — оттуда его можно распечатать", "ok");
    } catch (e) { H.err(); toast(e.message || "Не получилось", "err"); }
    finally { el.disabled = false; }
  },
  "pay-done": () => {
    closeSheet();
    const top = SHEETS[SHEETS.length - 1];
    if (top && top.classList.contains("pay-s")) openPay(top);   // обновить кошелёк на месте
  },
});

// кнопка в шапке и переход из бота (?pay=<id>&amt=<сумма>)
(() => {
  const b = $("#pay-btn"); if (b) { b.innerHTML = `${ic("wallet")}<span>Кошелёк</span>`; b.classList.add("pay-pill"); }
  // надпись «Кошелёк» прячется, если шапка не влезает (узкий экран, кнопка админа)
  const fit = () => { const h = $("header"); if (!b || !h) return; b.classList.remove("tight"); if (h.scrollWidth > h.clientWidth + 1) b.classList.add("tight"); };
  addEventListener("resize", fit); setTimeout(fit, 0); setTimeout(fit, 1500); setTimeout(fit, 4000);
  const _ssPay = setStars; setStars = v => { _ssPay(v); requestAnimationFrame(fit); };   // баланс стал длиннее — перепроверить
  const p = new URLSearchParams(location.search);
  if (p.get("pay")) {
    const go = () => ME ? openPaySend(+p.get("pay"), +(p.get("amt") || 0)) : setTimeout(go, 300);
    setTimeout(go, 600);
  }
})();

// ============================================================ пароль кошелька (6 цифр, как в WeChat)
// pinPad → Promise<строка из 6 цифр | null (закрыли)>. opts.forgot — ссылка «Забыл пароль?» (сброс кодом от бота).
function pinPad(title, sub, opts = {}) {
  return new Promise(done => {
    let v = "", fin = false;
    const finish = x => { if (fin) return; fin = true; done(x); };
    const keys = [1, 2, 3, 4, 5, 6, 7, 8, 9, opts.forgot ? "?" : "", 0, "<"];
    const el = openSheet(`<div class="pin">
        <div class="pin-ic">${ic("lock")}</div><b class="pin-t">${title}</b><span class="pin-sub">${sub || ""}</span>
        <div class="pin-dots">${"<i></i>".repeat(6)}</div>
        <div class="pin-kb">${keys.map(k => k === "" ? "<span></span>" : k === "?" ? `<button class="pin-f" data-k="?">Забыл?</button>`
          : `<button data-k="${k}">${k === "<" ? ic("back") : k}</button>`).join("")}</div></div>`, "pin-s");
    const dots = el.querySelectorAll(".pin-dots i");
    const paint = () => dots.forEach((d, i) => d.classList.toggle("on", i < v.length));
    el._onClose = () => finish(null);
    el.querySelector(".pin-kb").onclick = async e => {
      const b = e.target.closest("button"); if (!b || fin) return;
      const k = b.dataset.k; H.sel();
      if (k === "<") { v = v.slice(0, -1); return paint(); }
      if (k === "?") { fin = true; closeSheet(); return done(await payPinForgot()); }
      if (v.length >= 6) return;
      v += k; paint();
      if (v.length === 6) { const x = v; setTimeout(() => { if (fin) return; fin = true; closeSheet(); done(x); }, 120); }
    };
  });
}
// ввести новый пароль дважды; null — передумали
async function payPinTwice(title = "Придумай пароль кошелька") {
  for (;;) {
    const a = await pinPad(title, "6 цифр — будешь вводить при каждом переводе"); if (!a) return null;
    if (/^(\d)\1{5}$/.test(a) || ["123456", "654321", "012345", "543210", "123123", "112233"].includes(a)) { H.err(); toast("Слишком простой пароль — придумай другой", "err"); continue; }
    const b = await pinPad("Повтори пароль", "Введи те же 6 цифр ещё раз"); if (!b) return null;
    if (a === b) return a;
    H.err(); toast("Пароли не совпали — давай ещё раз", "err");
  }
}
// первый вход в кошелёк: пароль обязателен
async function payPinSetup() {
  const pin = await payPinTwice();
  if (!pin) { toast("Без пароля кошелёк не откроется — он защищает переводы"); return false; }
  try { await post("pay/pin", { pin }); } catch (e) { return false; }
  if (PAY.info) PAY.info.pin = true;
  H.ok(); toast("Пароль установлен — запомни его", "ok");
  return true;
}
// забыл пароль: код от бота → новый пароль. Возвращает новый пароль (им же продолжаем перевод) или null
async function payPinForgot() {
  if (!await confirmM("Сбросить пароль?", "Бот пришлёт тебе в Telegram код из 6 цифр — введи его, потом придумай новый пароль.", "Прислать код")) return null;
  try { await post("pay/pin/forgot"); } catch (e) { return null; }
  toast("Код отправлен — загляни в чат с ботом", "ok");
  const code = await pinPad("Код из сообщения бота", "Действует 10 минут"); if (!code) return null;
  const pin = await payPinTwice("Новый пароль"); if (!pin) return null;
  try { await post("pay/pin/reset", { code, pin }); } catch (e) { return null; }
  H.ok(); toast("Пароль изменён", "ok");
  return pin;
}
// постоянный QR (без суммы) картинкой для печати: белый лист, имя, QR, подпись
function payQrPng() {
  const link = ME.refLink.replace(/start=.*$/, `start=pay_${ME.id}`);
  const q = qrcode(0, "M"); q.addData(link); q.make();
  const n = q.getModuleCount(), cell = 16, qs = n * cell, W = qs + 160, H0 = qs + 360;
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H0;
  const c = cv.getContext("2d");
  c.fillStyle = "#fff"; c.fillRect(0, 0, W, H0);
  c.fillStyle = "#14112a"; c.textAlign = "center";
  c.font = "800 44px -apple-system,Segoe UI,Roboto,sans-serif"; c.fillText("Оплата звёздами ⭐", W / 2, 80);
  c.font = "600 34px -apple-system,Segoe UI,Roboto,sans-serif"; c.fillText((ME.name || "").slice(0, 28), W / 2, 135);
  for (let r = 0; r < n; r++) for (let k = 0; k < n; k++) if (q.isDark(r, k)) c.fillRect(80 + k * cell, 170 + r * cell, cell, cell);
  c.font = "500 28px -apple-system,Segoe UI,Roboto,sans-serif"; c.fillStyle = "#555";
  c.fillText("Наведи камеру телефона или сканер в игре", W / 2, 170 + qs + 70);
  c.fillText("@" + (ME.refLink.match(/t\.me\/([^?]+)/) || [, "бот"])[1], W / 2, 170 + qs + 115);
  return new Promise((ok, no) => cv.toBlob(b => b ? ok(b) : no(new Error("не получилось сделать картинку")), "image/png"));
}

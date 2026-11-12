"use strict";
// ============================================================
//  Банк казино: шторка с историей прибыли, акциями и дивидендами
// ============================================================
ICONS.bank = '<path d="M3 10l9-6 9 6"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/><path d="M3 21h18"/>';
ICONS.info = '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.5"/>';
ICONS.pie = '<path d="M21 12A9 9 0 1 1 12 3v9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>';
let BK = null;
const sgn = n => (n >= 0 ? "+" : "−") + short(Math.abs(n));

// плашка банка (в играх и в топе) открывает шторку
const _lb = loadBank;
loadBank = async function () {
  document.querySelectorAll(".bankbar").forEach(b => {
    if (b.dataset.act) return;
    b.dataset.act = "bank"; b.classList.add("tap");
    b.querySelector(".bk-i").innerHTML = ic("bank");
    b.insertAdjacentHTML("beforeend", ic("chev"));
  });
  return _lb();
};

async function openBank() {
  H.imp("light");
  const el = openSheet(`<div id="bk-body">${emptyHTML("hourglass", "Считаем банк…")}</div>`, "bk-s");
  el._bk = true;
  await loadBK();
}
async function loadBK() {
  try { BK = await api("bank/info"); } catch (e) { return; }
  for (const s of SHEETS) if (s._bk) fillBK(s);
}
let bkTop = "holders";
const bkDate = t => new Date(t * 1000).toLocaleDateString("ru", { day: "numeric", month: "short" });
// столбики прибыли казино по дням; тап по столбику — подпись с суммой
function bkChart(days) {
  const W = 320, Hc = 120, mid = Hc / 2, max = Math.max(1, ...days.map(d => Math.abs(d.profit))), bw = W / days.length;
  const bars = days.map((d, i) => {
    const h = Math.max(d.profit ? 3 : 1.5, Math.abs(d.profit) / max * (mid - 8)), y = d.profit >= 0 ? mid - h : mid;
    return `<rect class="${d.profit > 0 ? "up" : d.profit < 0 ? "dn" : "z"}${i === days.length - 1 ? " now" : ""}" data-i="${i}" x="${i * bw + 2}" y="${y}" width="${bw - 4}" height="${h}" rx="3"/>`;
  }).join("");
  return `<div class="bkc"><svg viewBox="0 0 ${W} ${Hc}" preserveAspectRatio="none"><line x1="0" x2="${W}" y1="${mid}" y2="${mid}"/>${bars}</svg><div class="bkc-tip"></div></div>
    <div class="bk-axis"><span>${bkDate(days[0].day)}</span><span>${bkDate(days[Math.floor(days.length / 2)].day)}</span><span>сегодня</span></div>
    <div class="bk-legend"><span><i class="up"></i>банк в плюсе</span><span><i class="dn"></i>игроки обыграли банк</span></div>`;
}
function bkBindChart(el) {
  const box = el.querySelector(".bkc"); if (!box) return;
  const tip = box.querySelector(".bkc-tip");
  const show = e => {
    const r = box.getBoundingClientRect(), i = Math.max(0, Math.min(BK.days.length - 1, Math.floor((e.clientX - r.left) / r.width * BK.days.length)));
    const d = BK.days[i];
    box.querySelectorAll("rect").forEach(x => x.classList.toggle("sel", +x.dataset.i === i));
    tip.innerHTML = `<b class="${d.profit >= 0 ? "tw" : "tl"}">${sgn(d.profit)}</b><span>${i === BK.days.length - 1 ? "сегодня" : bkDate(d.day)}</span>`;
    tip.style.display = "flex";
    tip.style.left = Math.max(0, Math.min(r.width - tip.offsetWidth, (i + .5) / BK.days.length * r.width - tip.offsetWidth / 2)) + "px";
  };
  box.onpointermove = show; box.onpointerdown = show;
  box.onpointerleave = () => { tip.style.display = "none"; box.querySelectorAll("rect.sel").forEach(x => x.classList.remove("sel")); };
}
// цена акции по дням: банк на конец дня / выпуск (восстанавливаем назад от текущего банка)
function bkPriceSeries() {
  const out = [], n = BK.days.length;
  let b = BK.bank;
  for (let i = n - 1; i >= 0; i--) { out[i] = b / BK.supply; b -= BK.days[i].profit; }
  return out;
}
function bkPeople(list, f, empty) {
  return list.length ? list.map((u, i) => `<div class="row tap" data-act="profile" data-id="${u.id}"><span class="place p${i + 1}">${i + 1}</span>${avaHTML(u, 34)}
    <div class="grow"><div class="t">${esc(u.name)}</div></div>${f(u)}</div>`).join("") : `<div class="hint bk-empty">${empty}</div>`;
}
function bkTopHTML() {
  if (bkTop === "robbers") return bkPeople(BK.robbers, u => `<b class="tw">+⭐ ${short(u.sum)}</b>`, "Банк пока никто не обыграл");
  if (bkTop === "sponsors") return bkPeople(BK.sponsors, u => `<b class="tl">−⭐ ${short(-u.sum)}</b>`, "Пока никто не проиграл");
  if (bkTop === "donors") return bkPeople(BK.donors, u => `<b class="tw">⭐ ${short(u.sum)}</b>`, "Банку пока никто ничего не дарил — стань первым меценатом");
  if (bkTop === "saviors") return bkPeople((BK.crisis || {}).saviors || [], u => `<b class="tw">⭐ ${short(u.sum)}</b>`, "Спасителей пока нет — подари банку в кризис");
  const clans = (BK.clanHolders || []).map(c => `<div class="row tap" data-act="clan" data-id="${c.id}"><span class="place">${ic("users")}</span>
    <div class="grow"><div class="t">[${esc(c.tag)}] ${esc(c.name)}</div><div class="s">клан · дивиденды в казну</div></div><b>${fmt(c.n)} акц.</b></div>`).join("");
  return bkPeople(BK.holders, u => `<b>${fmt(u.n)} акц.</b>`, "Акции пока никто не купил — будь первым") + clans;
}
function fillBK(el) {
  if (!BK || !el.isConnected) return;
  const m = BK.mine, pl = m.value - m.cost, h = Math.floor(BK.endsIn / 3600), mi = Math.floor(BK.endsIn % 3600 / 60);
  const room = Math.min(BK.maxPer - m.n, BK.supply - BK.held);
  const since = BK.bank - BK.start, d14 = BK.days.reduce((s, d) => s + d.profit, 0);
  const ps = bkPriceSeries(), pch = ps[0] ? (ps[ps.length - 1] / ps[0] - 1) * 100 : 0;
  const pct = v => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2).replace(".", ",") + "%";
  const cr = BK.crisis || {};
  el.querySelector("#bk-body").innerHTML = `
    ${cr.on ? `<div class="bkcr"><div class="bkcr-i">${ic("flame")}</div><div class="grow"><b>Банк в кризисе</b>
      <span>Банк ниже ⭐ ${short(cr.at)}. Ставки — не больше ⭐ ${short(cr.maxBet)}, дивиденды на паузе. Не хватает ⭐ ${short(cr.need)}.</span>
      <em>Подари банку ⭐ ${short(cr.saviorMin)}+ — получишь титул «Спаситель банка»${cr.mine ? ` · ты уже спас на ⭐ ${short(cr.mine)}` : ""}</em></div></div>` : ""}
    <div class="bkh${cr.on ? " crisis" : ""}">
      <div class="bkh-top"><span class="bkh-i">${ic("bank")}</span><div><span>Банк игры</span><b>⭐ ${fmt(BK.bank)}</b></div>
        ${BK.lvl ? `<span class="bklvl">${ic("trophy")}Ур. ${BK.lvl.lvl}${BK.lvl.next ? "" : " · макс"}</span>` : ""}</div>
      <div class="bkh-stats">
        <div><span>Сегодня</span><b class="${BK.today >= 0 ? "up" : "dn"}">${sgn(BK.today)}</b></div>
        <div><span>14 дней</span><b class="${d14 >= 0 ? "up" : "dn"}">${sgn(d14)}</b></div>
        <div><span>С открытия</span><b class="${since >= 0 ? "up" : "dn"}">${sgn(since)}</b></div>
      </div>
      <button class="bkh-vrow" data-act="bk-vault"><span class="bkh-vi">${ic("lock")}</span><span class="bkh-vt"><b>Хранилище банка</b><small>${(BK.vault || {}).count ? `${fmt(BK.vault.count)} ${plural(BK.vault.count, ["подарок", "подарка", "подарков"])} на ⭐ ${short(BK.vault.value)}` : "проигранные в апгрейде подарки"}</small></span>${ic("chev")}</button>
      <button class="bkh-addr" data-act="bk-addr"><span>Адрес банка</span><b>${payAddrFmt(BK.addr)}</b>${ic("copy")}</button>
      <button class="bkh-gift" data-act="bk-gift">${ic("heart")}Перевести в банк${BK.gifted ? `<em>ты уже подарил ⭐ ${short(BK.gifted)}</em>` : ""}</button>
    </div>

    ${BK.k ? bkKHTML(BK.k) : ""}

    <div class="bkme2"><span class="pic ${BK.me > 0 ? "g" : BK.me < 0 ? "r" : "b"}">${ic(BK.me > 0 ? "trophy" : "wallet")}</span>
      <div class="grow"><div class="t">${BK.me > 0 ? "Ты обыграл банк" : BK.me < 0 ? "Ты занёс банку" : "Ты с банком в расчёте"}</div><div class="s">итог всех твоих игр</div></div>
      <b class="${BK.me > 0 ? "tw" : BK.me < 0 ? "tl" : ""}">${BK.me > 0 ? "+" : BK.me < 0 ? "−" : ""}⭐ ${fmt(Math.abs(BK.me))}</b></div>

    <div class="sec-t">${ic("trend")}Прибыль банка по дням</div>
    <div class="inccard">${bkChart(BK.days)}</div>

    <div class="sec-t">${ic("pie")}Акции банка</div>
    <div class="bksh">
      <div class="bksh-top"><div><span>Цена акции</span><b>⭐ ${fmt(BK.price)}</b><em class="${pch >= 0 ? "up" : "dn"}">${pct(pch)} за 14 дней</em></div>
        ${spark(ps, pch >= 0, 110, 44)}</div>
      <div class="bksh-div">${ic("coins")}<div class="grow"><b>Дивиденды через ${h} ч ${mi} мин</b><span>${Math.round(BK.divShare * 100)}% вчерашней прибыли банка делится на акции${BK.lastDiv && BK.lastDiv.total ? ` · прошлая выплата ⭐ ${String(BK.lastDiv.perShare).replace(".", ",")} на акцию` : ""}</span></div></div>
      ${m.n ? `<div class="bks-top"><div><span>У тебя</span><b>${fmt(m.n)}</b></div><div><span>Стоимость</span><b>⭐ ${short(m.value)}</b></div><div><span>Прибыль</span><b class="${pl >= 0 ? "tw" : "tl"}">${sgn(pl)}</b></div></div>
        <div class="bks-row"><span>Дивиденды сегодня (прогноз)</span><b class="tw">+⭐ ${fmt(m.est)}</b></div>
        <div class="bks-row"><span>Получено дивидендов всего</span><b>⭐ ${fmt(m.div)}</b></div>` : ""}
      ${room > 0 ? `<div class="bks-buy-t">${ic("trend")}Купить акции</div><div class="jpbuy bks-buy">${[1, 10, 100, 1000].filter(n => n <= room).map(n => `<button data-act="bk-buy" data-v="${n}"><b>+${n}</b><span>⭐ ${short(n * BK.price)}</span></button>`).join("")}</div>`
        : `<div class="hint" style="font-size:12.5px;text-align:center;margin-top:8px">Лимит — ${fmt(BK.maxPer)} акций в одни руки</div>`}
      ${m.n ? `<button class="btn ghost bks-sell" data-act="bk-sell" ${m.sellIn ? "disabled" : ""}>${m.sellIn ? `${ic("lock")}Продажа через ${Math.floor(m.sellIn / 3600)} ч ${Math.floor(m.sellIn % 3600 / 60)} мин` : `${ic("coins")}Продать все · ⭐ ${short(Math.floor(m.n * BK.price * (1 - BK.sellFee)))}`}</button>` : ""}
      <div class="bks-foot"><span>Акций у игроков</span><div class="cbar"><div style="width:${Math.max(.5, BK.held / BK.supply * 100)}%"></div></div><b>${fmt(BK.held)} / ${short(BK.supply)}</b></div>
    </div>
    <details class="bk-how"><summary>${ic("info")}Как работают акции</summary>
      <p>Цена акции = банк / ${short(BK.supply)}. Игроки проигрывают — банк растёт и акции дорожают, выигрывают — дешевеют.</p>
      <p>Каждый день в 00:00 UTC (11:00 по Сахалину) ${Math.round(BK.divShare * 100)}% вчерашней прибыли банка делится на акции у игроков (если акций у игроков меньше ${short(BK.divFloor || 10000)} — делится как на ${short(BK.divFloor || 10000)}, остаток остаётся в банке). В убыточный для банка день дивидендов нет.</p>
      <p>Не больше ${fmt(BK.maxPer)} акций в одни руки. Продать можно через сутки после покупки, комиссия ${pctF(BK.sellFee)}.</p></details>

    <div class="sec-t">${ic("coins")}Вклады в банк</div>
    <div class="bkdep">
      ${BK.lvl && (BK.lvl.lvl || BK.lvl.next) ? `<div class="bkdep-lvl"><span>Уровень банка <b>${BK.lvl.lvl}</b>${BK.lvl.lvl ? ` · вклады доходнее на ${Math.round(BK.lvl.bonus * BK.lvl.lvl * 100)}%` : ""}</span>
        ${BK.lvl.next ? `<div class="cbar"><div style="width:${Math.max(2, BK.lvl.progress)}%"></div></div><small>до уровня ${BK.lvl.lvl + 1} банку не хватает ⭐ ${short(BK.lvl.next - BK.bank)}</small>` : `<small>максимальный уровень — банк монстр</small>`}</div>` : ""}
      <div class="hint" style="font-size:12.5px;line-height:1.5">Вложи звёзды — они станут «телом» банка (акции и уровень считаются от него), а банк заплатит проценты. Капают каждую минуту, выплата в конце срока.</div>
      <button class="btn cta gold" data-act="bk-dep" style="width:100%;margin-top:10px">${ic("coins")}Вложить звёзды</button>
    </div>

    <div class="seg bk-tabs">${[["holders", "Акционеры"], ["robbers", "Обыграли"], ["sponsors", "Спонсоры"], ["donors", "Меценаты"], ...((BK.crisis || {}).on || ((BK.crisis || {}).saviors || []).length ? [["saviors", "Спасители"]] : [])].map(([k, t]) => `<button data-act="bk-top" data-v="${k}" class="${k === bkTop ? "on" : ""}">${t}</button>`).join("")}</div>
    <div class="box" id="bk-top">${bkTopHTML()}</div>
    <div class="disc">Банк = 50 млн стартового резерва + всё, что игроки проиграли, − всё, что выиграли, − розыгрыши и дивиденды. ${esc(ME.disclaimer)}</div>`;
  bkBindChart(el);
}

// плашка банка: тикер крупных выигрышей («банк −52K») и пометка кризиса; опрос раз в 5 с, пока открыты «Игры»
let bkLastWin = null;
function bankTicker(d) {
  document.querySelectorAll(".bankbar").forEach(bar => {
    bar.classList.toggle("crisis", !!d.crisis);
    let tag = bar.querySelector(".bk-crt");
    if (d.crisis && !tag) bar.querySelector("div").insertAdjacentHTML("beforeend", `<span class="bk-crt">${ic("flame")}кризис</span>`);
    if (!d.crisis && tag) tag.remove();
    let lv = bar.querySelector(".bk-lvl");
    if (d.lvl && !lv) bar.querySelector("div").insertAdjacentHTML("beforeend", `<span class="bk-lvl">${ic("trophy")}${d.lvl}</span>`);
    if (!d.lvl && lv) lv.remove();
  });
  const w = d.win;
  if (bkLastWin === null) { bkLastWin = w ? w.id : 0; return; }   // при первом заходе старые выигрыши не показываем
  if (!w || w.id <= bkLastWin) return;
  bkLastWin = w.id;
  document.querySelectorAll(".bankbar").forEach(bar => {
    bar.classList.remove("hit"); void bar.offsetWidth; bar.classList.add("hit");
    bar.querySelectorAll(".bk-tick").forEach(t => t.remove());
    const t = document.createElement("div"); t.className = "bk-tick";
    t.innerHTML = `<b>−⭐ ${short(w.amount)}</b><span>${esc(w.name)} · ${esc(w.game)}</span>`;
    bar.appendChild(t); starify(t); setTimeout(() => t.remove(), 4200);
  });
}
setInterval(() => { if (typeof TAB !== "undefined" && TAB === "games" && !bgOff() && document.querySelector("#v-games .bankbar")) loadBank(); }, 5000);

// хранилище банка: подарки, проигранные в апгрейде; через 48 ч перерабатываются (ценность банк уже получил)
const vlLeft = s => s >= 3600 ? `${Math.floor(s / 3600)} ч ${Math.floor(s % 3600 / 60)} мин` : `${Math.max(1, Math.floor(s / 60))} мин`;
async function openVault() {
  H.imp("light");
  const el = openSheet(`<div id="vl-body">${emptyHTML("hourglass", "Открываем хранилище…")}</div>`, "vl-s");
  let d; try { d = await api("bank/vault"); } catch (e) { return; }
  if (!el.isConnected) return;
  const cells = d.items.map(x => {
    const k = reg({ g: x.gift, mine: false });
    const p = Math.max(0, Math.min(100, x.left / d.ttl * 100));
    return `<div class="vl-it${x.mine ? " mine" : ""}" data-act="gift" data-k="${k}">
      <div class="vl-g">${giftHTML(x.gift, { lite: true })}${x.mine ? `<span class="vl-mine">твой</span>` : ""}</div>
      <b>⭐ ${short(x.value)}</b><span class="vl-from">${esc(x.from.name)}</span>
      <div class="vl-bar"><i style="width:${p}%"></i></div><span class="vl-left">${ic("refresh")}${vlLeft(x.left)}</span></div>`;
  }).join("");
  el.querySelector("#vl-body").innerHTML = `
    <div class="vlh">
      <div class="vlh-door"><i></i><i></i><i></i>${ic("lock")}</div>
      <div class="vlh-t"><span>Хранилище банка</span><b>${fmt(d.count)} ${plural(d.count, ["подарок", "подарка", "подарков"])}</b><em>⭐ ${fmt(d.value)}</em></div>
    </div>
    <p class="vl-how">Сюда попадают подарки, проигранные в апгрейде. Через ${Math.round(d.ttl / 3600)} часов банк перерабатывает их в звёзды.
      ${d.recycled.n ? `За неделю переработано ${fmt(d.recycled.n)} ${plural(d.recycled.n, ["подарок", "подарка", "подарков"])} на ⭐ ${short(d.recycled.value)}.` : ""}</p>
    ${d.items.length ? `<div class="vl-grid">${cells}</div>` : emptyHTML("lock", "Хранилище пустое — апгрейды пока все удачные")}
    <div class="disc">${esc(ME.disclaimer)}</div>`;
  starify(el);
}

// подарок банку: просто так, без комиссии и без награды — банк растёт, акции дорожают
function openBankGift() {
  H.imp("light");
  const el = openSheet(`<div class="bkg">
      <div class="bkg-i">${ic("bank")}</div>
      <h2>Перевод в банк</h2>
      <p>Звёзды уйдут в банк игры. Взамен ничего не будет — это подарок: банк станет больше, а акции банка подорожают.</p>
      ${BK && BK.addr ? `<div class="bkg-addr">${payAddrFmt(BK.addr)}</div>` : ""}
    </div>
    <div class="betp">${betHTML("bkg-amt", 1000)}
      <button class="btn cta gold" data-act="bk-gift-go">${ic("heart")}Перевести в банк</button></div>
    <div class="disc">Перевод не отменить. ${esc(ME.disclaimer)}</div>`, "bkg-s");
  starify(el);
}
Object.assign(ACT, {
  bank: () => openBank(),
  "bk-addr": () => payCopy(BK.addr, "Адрес банка скопирован"),
  "bk-vault": () => openVault(),
  "bk-gift": () => openBankGift(),
  "bk-gift-go": async el => {
    const amount = betVal("bkg-amt");
    if (!amount || amount < 1) return toast("Введи сумму");
    if (amount > ME.stars) return toast("Не хватает звёзд ⭐");
    if (!await confirmM(`Подарить банку ⭐ ${fmt(amount)}?`, "Звёзды уйдут в банк насовсем — взамен ничего не будет.", "Подарить")) return;
    el.disabled = true;
    try {
      const r = await post("bank/donate", { amount }); setStars(r.stars); H.ok();
      closeSheet(); toast(`Банк благодарит! −⭐ ${fmt(amount)}`, "ok");
      await loadBK(); loadBank();
    } catch (e) { el.disabled = false; }
  },
  "bk-top": el => { bkTop = el.dataset.v; H.sel(); const s = topSheet(); s.querySelectorAll(".bk-tabs button").forEach(b => b.classList.toggle("on", b === el)); s.querySelector("#bk-top").innerHTML = bkTopHTML(); },
  "bk-buy": async el => {
    const n = +el.dataset.v;
    if (n * BK.price > ME.stars) return toast("Не хватает звёзд ⭐");
    const r = await post("bank/shares", { n }); setStars(r.stars); H.ok();
    toast(`+${n} ${plural(n, ["акция", "акции", "акций"])} банка`, "ok");
    await loadBK(); loadBank();
  },
  "bk-sell": async () => {
    const n = BK.mine.n, got = Math.floor(n * BK.price * (1 - BK.sellFee));
    if (!await confirmM(`Продать ${fmt(n)} ${plural(n, ["акцию", "акции", "акций"])}?`, `Получишь ⭐ ${fmt(got)} (комиссия ${pctF(BK.sellFee)}). Дивиденды за сегодня не придут.`, "Продать")) return;
    const r = await post("bank/shares", { n: -n }); setStars(r.stars); H.ok(); toast(`Продано · +⭐ ${fmt(got)}`, "ok");
    await loadBK(); loadBank();
  },
});

// курс банка: от него призы, цены кейсов и скупка — банк растёт, всем лучше
function bkKHTML(k) {
  const x = v => "×" + v.toFixed(2).replace(".", ","), pc = v => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(Math.round(v * 100)) + "%";
  const pos = Math.max(0, Math.min(100, (k.r - .5) / 1.5 * 100)), mood = k.r >= 1.3 ? "Банк жирует" : k.r >= 1 ? "Банк в форме" : k.r >= .8 ? "Банк худеет" : "Банк на мели";
  const tile = (ic_, t, v, good, s) => `<div class="bkk-t ${good > 0 ? "up" : good < 0 ? "dn" : ""}">${ic(ic_)}<span>${t}</span><b>${v}</b><small>${s}</small></div>`;
  return `<div class="bkk">
    <div class="bkk-h"><div><span>Курс банка</span><b>${x(k.r)}</b></div><em class="${k.r >= 1 ? "up" : "dn"}">${mood}</em></div>
    <div class="bkk-bar"><i style="left:${pos}%"></i><span style="left:${(1 - .5) / 1.5 * 100}%"></span></div>
    <div class="bkk-g">${tile("trophy", "Призы", x(k.prize), Math.sign(k.prize - 1), "лиги, сезон, кланы, задания")}
      ${tile("box", "Кейсы", k.case === 1 ? "0%" : pc(k.case - 1), Math.sign(1 - k.case), "к цене кейсов")}
      ${tile("coins", "Скупка", String(Math.round(k.sellRate * 1000) / 10).replace(".", ",") + "%", Math.sign(k.sell), "мгновенная продажа")}</div>
    <div class="bkk-n">Курс = банк / ⭐ ${short(k.ref)}. Банк растёт — призы больше, кейсы дешевле, скупка дороже. Худеет — наоборот.</div></div>`;
}


// ============================================================ Вклады в банк
// звёзды лежат до конца срока, проценты платит банк; досрочное закрытие — с комиссией в пользу банка
let DEPD = null;
async function openBankDep() {
  H.imp("light");
  openSheet(`<div id="dep-body">${emptyHTML("hourglass", "Открываем вклады…")}</div>`, "dep-s");
  await bkDepLoad();
}
async function bkDepLoad() {
  try { DEPD = await api("bank/deposits"); } catch (e) { return; }
  DEPD.sel = DEPD.sel || 7;
  bkDepDraw();
}
const depDays = k => LANG === "en" ? `${k} day${k === 1 ? "" : "s"}` : `${k} ${plural(k, ["день", "дня", "дней"])}`;
const depLeft = s => { const h = Math.ceil(s / 3600); return h >= 48 ? depDays(Math.ceil(h / 24)) : h > 1 ? `${h} ч` : `${Math.max(1, Math.ceil(s / 60))} мин`; };
// итог считается по той же ставке, что показана на кнопке срока
function bkDepSum() {
  const d = DEPD, get = $("#dep-get"), lab = $("#dep-lab"), inp = $("#dep-amt"); if (!d || !get || !inp) return;
  const room = Math.max(d.min, d.maxTotal - d.total);   // MAX и ввод не выходят за общий лимит вкладов
  if (+inp.value > room) inp.value = room;
  const amount = Math.max(0, Math.floor(+inp.value || 0));
  lab.textContent = LANG === "en" ? `In ${depDays(d.sel)} you'll get` : `Через ${depDays(d.sel)} получишь`;
  get.textContent = `⭐ ${fmt(Math.floor(amount * (1 + d.rates[String(d.sel)] / 100)))}`;
}
function bkDepDraw() {
  const d = DEPD, el = $("#dep-body"); if (!d || !el) return;
  const rate = k => String(d.rates[String(k)]).replace(".", ",");
  const start = Math.max(d.min, Math.min(10000, Math.floor(ME.stars)));
  const blocked = d.crisis || d.mine.length >= d.maxN || d.total + d.min > d.maxTotal;
  el.innerHTML = `
    <h2 class="gtitle">${ic("bank")} Вклады</h2>
    <div class="sec-t">Срок</div>
    <div class="dep-terms" style="--n:${d.days.length}">${d.days.map(k => `<button data-act="bk-dep-days" data-v="${k}" class="${d.sel === k ? "on" : ""}"><b>${depDays(k)}</b><span>+${rate(k)}%</span></button>`).join("")}</div>
    <div class="betp dep-form">${betHTML("dep-amt", start, [d.min, 10000, 100000, "max"])}
      <div class="dep-sum"><span id="dep-lab"></span><b id="dep-get"></b></div>
      <button class="btn cta gold" data-act="bk-dep-open" ${blocked ? "disabled" : ""}>${ic("coins")}Открыть вклад</button>
      <div class="dep-meta"><span>Минимум<b>⭐ ${fmt(d.min)}</b></span><span>На вкладах<b>⭐ ${short(d.total)} из ${short(d.maxTotal)}</b></span></div>
      ${blocked ? `<div class="dep-warn">${d.crisis ? "В кризис банка вклады закрыты" : d.mine.length >= d.maxN ? `Открыто ${d.maxN} вклада, это максимум` : "Лимит вкладов исчерпан"}</div>` : ""}</div>
    <div class="sec-t">Мои вклады${d.mine.length ? ` · ${d.mine.length} из ${d.maxN}` : ""}</div>
    ${d.mine.length ? `<div class="dep-list">${d.mine.map(x => `
      <div class="dep-it"><div class="dep-it-h"><b>⭐ ${fmt(x.amount)}</b><em>+${String(x.rate).replace(".", ",")}%</em>
        <button class="btn sm ${x.left ? "ghost" : "cta"}" data-act="bk-dep-out" data-id="${x.id}">${x.left ? "Досрочно" : "Получить"}</button></div>
        <div class="cbar"><div style="width:${Math.max(2, 100 - x.left / (x.days * 864))}%"></div></div>
        <div class="dep-it-s"><span>${x.left ? "осталось " + depLeft(x.left) : "готов к выдаче"}</span><span>проценты +${fmt(x.accrued)}</span></div></div>`).join("")}</div>`
      : `<div class="dep-empty">Вкладов пока нет</div>`}
    <p class="dep-note">Проценты платит банк, они начисляются равномерно и приходят вместе с вкладом в конце срока. Закрыть раньше можно с комиссией ${+(d.earlyFee * 100).toFixed(1)}%, проценты при этом сгорают.</p>
    <div class="disc">${esc(ME.disclaimer)}</div>`;
  $("#dep-amt").addEventListener("input", bkDepSum);
  bkDepSum();
}
Object.assign(ACT, {
  "bk-dep": () => openBankDep(),
  "bk-dep-days": el => {   // без перерисовки: введённая сумма остаётся
    DEPD.sel = +el.dataset.v; H.sel();
    el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el));
    bkDepSum();
  },
  "bk-dep-open": async el => {
    const amount = betVal("dep-amt");
    if (amount < DEPD.min) return toast(`Вклад от ⭐ ${fmt(DEPD.min)}`);
    if (amount > ME.stars) return toast("Не хватает звёзд ⭐");
    if (DEPD.total + amount > DEPD.maxTotal) return toast(`Вклады суммарно не больше ⭐ ${fmt(DEPD.maxTotal)}`);
    el.disabled = true;
    try {
      const r = await post("bank/deposit", { amount, days: DEPD.sel });
      setStars(r.stars); H.ok(); toast("Вклад открыт — банк растёт", "ok");
      await bkDepLoad(); loadBank();
    } catch (e) { el.disabled = false; }
  },
  "bk-dep-out": async el => {
    const x = (DEPD.mine || []).find(m => m.id === +el.dataset.id); if (!x) return;
    if (x.left > 0 && !await confirmM("Забрать вклад досрочно?",
      `Вернём ⭐ ${fmt(Math.floor(x.amount * (1 - DEPD.earlyFee)))} (комиссия ${(DEPD.earlyFee * 100).toFixed(0)}%). Накапанные проценты (+${fmt(x.accrued)}) сгорят.`, "Забрать")) return;
    el.disabled = true;
    try {
      const r = await post("bank/deposit/withdraw", { id: x.id });
      setStars(r.stars); r.early ? H.imp("light") : H.ok();
      toast(`+⭐ ${fmt(r.pay)}`, "ok");
      await bkDepLoad(); loadBank();
    } catch (e) { el.disabled = false; }
  },
});

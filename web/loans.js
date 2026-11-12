"use strict";
// ============================================================ кредит под залог подарка (банк казино)
const loanLeft = s => { s = Math.max(0, s); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600); return d ? `${d} д ${h} ч` : `${h} ч ${Math.floor(s % 3600 / 60)} мин`; };
const dayW = n => `${n} ${n === 1 ? "день" : n < 5 ? "дня" : "дней"}`;
let LN_DAYS = 3;
const lnDays = L => L.terms.some(x => x.days === LN_DAYS) ? LN_DAYS : L.terms[L.terms.length - 1].days;
const lnFee = (L, d) => (L.terms.find(x => x.days === d) || L.terms[0]).fee;
const lnChips = max => [...new Set([0.1, 0.25, 0.5, 1].map(k => Math.max(100, Math.floor(max * k / 100) * 100)))];
async function loansHTML() {
  const L = await api("loans").catch(() => null);
  if (L) LN_CFG = L;
  if (!L) return "";
  const t = L.now, c = L.credit, d = lnDays(L), fee = lnFee(L, d), cash = L.loans.find(x => !x.gift && !x.biz), lvlOk = ME.lv.level >= L.cashLevel, busy = c.penalty > 0;
  const lock = busy ? `<div class="hint tl" style="font-size:13px;margin-top:10px">Просрочка: новый кредит через ${loanLeft(c.penalty)}. Ставки пока до ⭐ ${short(c.penaltyBet)}.</div>` : "";
  return `<div class="cashl cr-card">
      <div class="cr-top"><div class="grow"><span>Кредитный рейтинг</span><b>${fmt(c.score)}<em>из 1000</em></b></div><i class="cr-tier">${esc(c.tier)}</i></div>
      <div class="cr-bar"><i style="width:${c.score / 10}%"></i></div>
      <div class="cr-sub">${c.next ? `До уровня «${esc(c.next.tier)}» ещё ${fmt(c.next.at - c.score)}: лимит ⭐ ${short(c.next.limit)}, ставка ${pctF(c.next.fee)}` : "Лучшие условия банка"}</div>
      <div class="hint" style="font-size:12px;margin-top:6px">Вернул в срок: +${c.gain}, если кредит от ⭐ ${short(c.okMin)} и дольше 6 часов. Просрочка: −${c.drop}.</div>
    </div>
    <div class="sec-t" style="margin-top:14px">${ic("hourglass")}Срок кредита</div>
    <div class="seg cr-terms">${L.terms.map(x => `<button data-act="loan-days" data-v="${x.days}" class="${x.days === d ? "on" : ""}"><b>${dayW(x.days)}</b><span>${pctF(x.fee)}</span></button>`).join("")}</div>
    <div class="cashl">
      <div class="cashl-h"><span class="pic y">${ic("coins")}</span><div class="grow"><b>Без залога</b><span>лимит ⭐ ${short(L.cashMax)} · вернуть +${pctF(fee)}</span></div></div>
      ${L.ladder ? `<div class="cr-lad">${L.ladder.map(x => `<button data-act="loan-tier" data-at="${x.at}" data-tier="${esc(x.tier)}" class="${x.cur ? "cur" : x.on ? "on" : "off"}"><b>${x.on ? "" : ic("lock")}⭐ ${x.limit >= 1e6 ? x.limit / 1e6 + "M" : x.limit / 1e3 + "K"}</b><span>${x.on ? esc(x.tier) : "от " + fmt(x.at)}</span></button>`).join("")}</div>` : ""}
      ${lock || (cash ? `<div class="hint" style="font-size:13px;margin-top:10px">Сначала верни текущий кредит без залога.</div>`
        : !lvlOk ? `<div class="hint" style="font-size:13px;margin-top:10px">${ic("lock")} Доступен с ${L.cashLevel} уровня</div>`
        : L.stars < 0 ? `<div class="hint tl" style="font-size:13px;margin-top:10px">Сначала закрой минус на балансе</div>`
        : `<div class="jpbuy cr-chips">${lnChips(L.cashMax).map(n => `<button data-act="loan-cash" data-v="${n}"><b>⭐ ${short(n)}</b><span>вернуть ${short(Math.ceil(n * (1 + fee)))}</span></button>`).join("")}</div>`)}
      <div class="hint" style="font-size:11.5px;margin-top:8px">Не вернёшь в срок: долг и штраф ${pctF(c.lostFee)} спишутся с баланса, даже в минус. Пока кредит открыт, звёзды в обменах отдавать нельзя.</div>
    </div>
    <div class="sec-t" style="margin-top:14px">${ic("store")}Под залог бизнеса</div>
    ${L.bizItems.length ? `<div class="box cr-rows">${L.bizItems.map(x => `<div class="row"><img class="spi" style="width:38px;height:38px;margin:0" src="${A.orig(x.col, 64)}" alt="">
      <div class="grow"><div class="t">${esc(x.name)}</div><div class="s">ур. ${x.level} · получишь ⭐ ${short(x.got)}, вернуть ${short(Math.ceil(x.got * (1 + fee)))}</div></div>
      <button class="btn sm ghost" data-act="loan-biz" data-v="${esc(x.id)}" data-got="${x.got}" data-name="${esc(x.name)}"${busy ? " disabled" : ""}>Взять</button></div>`).join("")}</div>
      <div class="hint" style="font-size:12px;margin:8px 4px 0">${Math.round(L.autoShare * 100)}% собранного дохода само гасит кредит. Бизнес в залоге нельзя продать или улучшить. Не вернёшь в срок: бизнес заберёт банк вместе с управляющим и несобранным доходом.</div>`
      : `<div class="hint" style="font-size:13px;padding:0 4px">Нет бизнесов для залога: купи бизнес на вкладке «Доход» или закрой текущий кредит.</div>`}
    <div class="sec-t" style="margin-top:14px">${ic("wallet")}Мои кредиты</div>
    ${L.loans.length ? `<div class="box cr-rows">${L.loans.map(x => `<div class="row">${x.gift ? `<img class="spi" style="width:38px;height:38px;margin:0" src="${A.model(x.gift.col, x.gift.model, 64)}" alt="">` : x.biz && x.biz.col ? `<img class="spi" style="width:38px;height:38px;margin:0" src="${A.orig(x.biz.col, 64)}" alt="">` : `<span class="pic y">${ic("coins")}</span>`}
      <div class="grow"><div class="t">${x.gift ? esc(x.gift.col) + " #" + fmt(x.gift.num) : x.biz ? esc(x.biz.name) : "Без залога · ⭐ " + fmt(x.principal)}</div><div class="s ${x.until - t < 43200 ? "tl" : ""}">вернуть ⭐ ${fmt(x.debt)}${x.paid ? ` из ${fmt(x.total)}` : ""} · осталось ${loanLeft(x.until - t)}</div>
        ${x.paid ? `<div class="loan-bar"><i style="width:${Math.round(x.paid / x.total * 100)}%"></i></div>` : ""}</div>
      <button class="btn sm green" data-act="loan-repay" data-id="${x.id}" data-debt="${x.debt}" data-min="${x.partMin || 100}" data-g="${x.gift ? 1 : x.biz ? 2 : 0}">Вернуть</button></div>`).join("")}</div>`
      : `<div class="hint" style="font-size:13px;padding:0 4px">Кредитов нет. Под залог подарка: открой его в сумке и нажми «Кредит под залог».</div>`}
    <div class="hint" style="font-size:12px;margin:8px 4px 0">Под подарок банк даёт ${Math.round(L.ltv * 100)}% ценности. Пока подарок в залоге, он не приносит доход. Не вернёшь в срок: подарок уйдёт банку на маркет. Не больше ${L.max} кредитов сразу.</div>`;
}
let BK_TAB = "bank";
const bkTabs = () => `<div class="seg bk-tabs">${[["bank", "Банк"], ["loans", "Кредиты"]].map(([k, t]) => `<button data-act="bk-tab" data-v="${k}" class="${BK_TAB === k ? "on" : ""}">${t}</button>`).join("")}</div>`;
let LN_CFG = null;   // последние условия кредита с сервера (ltv, fee) — для подтверждений
const lnCfg = async () => LN_CFG || (LN_CFG = await api("loans").catch(() => null)) || { ltv: .4, fee: .15, terms: [{ days: 3, fee: .15 }] };
const lnRefresh = async el => { const s = el.closest(".loans-sec"); if (s) s.innerHTML = await loansHTML(); };
const _fillBKL = fillBK;
fillBK = function (el) {
  const body = el && el.querySelector("#bk-body"); if (!body) return;
  if (BK_TAB === "loans") { body.innerHTML = bkTabs() + `<div class="loans-sec">${emptyHTML("hourglass", "Загружаем…")}</div>`; loansHTML().then(h => { const s = body.querySelector(".loans-sec"); if (s) s.innerHTML = h; }); return; }
  _fillBKL(el);
  body.insertAdjacentHTML("afterbegin", bkTabs());
};
const _openBankL = openBank;
openBank = function () { BK_TAB = "bank"; return _openBankL(); };
Object.assign(ACT, {
  "bk-tab": el => { BK_TAB = el.dataset.v; H.sel(); const s = SHEETS.find(x => x._bk); if (s) fillBK(s); },
  "loans-open": () => { BK_TAB = "loans"; _openBankL(); },
  loan: async el => {
    const ln = await lnCfg(), g = topSheet()._o.g, d = lnDays(ln), got = Math.floor(g.value * ln.ltv), debt = Math.ceil(got * (1 + lnFee(ln, d)));
    if (!await confirmM("Кредит под залог?", `Получишь ⭐ ${fmt(got)} сейчас. Вернуть ⭐ ${fmt(debt)}, срок: ${dayW(d)}. Тогда ${esc(g.col)} #${fmt(g.num)} вернётся к тебе. Не вернёшь: подарок заберёт банк, рейтинг упадёт.`, "Взять")) return;
    const r = await post(`gift/${el.dataset.id}/loan`, { days: d }); setStars(r.stars); H.ok(); toast(`+⭐ ${fmt(r.got)} · подарок в залоге`, "ok");
    closeSheet(); if (typeof giftChanged === "function") giftChanged();
  },
  "loan-tier": el => { H.sel(); if (el.classList.contains("off")) toast(`Откроется с рейтинга ${fmt(+el.dataset.at)}: возвращай кредиты в срок`); },
  "loan-cash": async el => {
    const ln = await lnCfg(), d = lnDays(ln), n = +el.dataset.v, debt = Math.ceil(n * (1 + lnFee(ln, d)));
    if (!await confirmM(`Взять ⭐ ${fmt(n)}?`, `Вернуть ⭐ ${fmt(debt)}, срок: ${dayW(d)}. Не вернёшь: спишем долг и штраф с баланса, даже в минус, рейтинг упадёт.`, "Взять")) return;
    const r = await post("loans/cash", { amount: n, days: d }); setStars(r.stars); H.ok(); toast(`+⭐ ${fmt(r.got)}`, "ok"); burstAt(el);
    await lnRefresh(el);
  },
  "loan-days": async el => { LN_DAYS = +el.dataset.v; H.sel(); await lnRefresh(el); },
  "loan-biz": async el => {
    const ln = await lnCfg(), d = lnDays(ln), got = +el.dataset.got, debt = Math.ceil(got * (1 + lnFee(ln, d)));
    if (!await confirmM("Кредит под бизнес?", `Получишь ⭐ ${fmt(got)} сейчас. Вернуть ⭐ ${fmt(debt)}, срок: ${dayW(d)}. ${Math.round(ln.autoShare * 100)}% дохода при сборе пойдёт в погашение. Не вернёшь: банк заберёт бизнес, рейтинг упадёт.`, "Взять")) return;
    const r = await post("loans/biz", { bid: el.dataset.v, days: d }); setStars(r.stars); H.ok(); toast(`+⭐ ${fmt(r.got)}`, "ok"); burstAt(el);
    await lnRefresh(el);
  },
  "loan-repay": async el => {
    // можно частями: по умолчанию предлагаем весь остаток (или сколько есть на балансе)
    const left = +el.dataset.debt, min = Math.min(+el.dataset.min || 100, left);
    if (ME.stars < min) return toast(`Нужно хотя бы ⭐ ${fmt(min)}`);
    const v = await promptM("Вернуть кредит", `Осталось вернуть ⭐ ${fmt(left)}. Можно частями — от ⭐ ${fmt(min)}. Весь остаток закроет кредит${+el.dataset.g === 1 ? " и вернёт подарок" : +el.dataset.g === 2 ? " и снимет бизнес с залога" : ""}.`, String(Math.min(left, Math.max(0, Math.floor(ME.stars)))), "Внести");
    if (v == null) return;
    const a = parseInt(String(v).replace(/\D/g, ""), 10) || 0;
    if (a < min) return toast(`Взнос — от ⭐ ${fmt(min)}`);
    if (a > ME.stars) return toast(`На балансе только ⭐ ${fmt(ME.stars)}`);
    const r = await post(`loans/${el.dataset.id}/repay`, { amount: Math.min(a, left) }); setStars(r.stars); H.ok();
    toast(r.closed ? (r.gift ? "Кредит закрыт, подарок вернулся" : r.biz ? "Кредит закрыт, бизнес свободен" : r.rating ? `Кредит закрыт, рейтинг +${r.rating}` : "Кредит закрыт") : `Внесено ⭐ ${fmt(r.paid)} · осталось ⭐ ${fmt(r.left)}`, "ok");
    const s = el.closest(".loans-sec"); if (s) s.innerHTML = await loansHTML();
  },
});

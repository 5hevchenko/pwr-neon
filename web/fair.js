"use strict";
// ============================================================
//  ЧЕСТНОСТЬ: шансы всех игр, проверка ставок, обозреватель блоков, транзакции, журнал администрации.
//  Проверка считается на устройстве игрока встроенной криптографией браузера (WebCrypto): внешних сервисов нет,
//  сервер в расчёте не участвует. Без WebCrypto (редкие старые WebView) считает POST /fair/verify на нашем сервере.
// ============================================================
const PF = { tab: "over", pub: null, st: null, hist: null, crash: null, days: null, audit: null, tx: null, txEnd: false, txKind: "", blocks: null, journal: null, exp: null, old: null, game: "", ex: "blocks", block: null, tag: "", caseOdds: {} };

const pfTabs = [["over", "Обзор"], ["games", "Игры и правила"], ["bets", "Мои ставки"], ["gifts", "Подарки"], ["crash", "Краш"], ["chain", "Блоки"], ["admin", "Админ"]];
const pfKind = { seed: "Личный сид", chain: "Цепочка хэшей", day: "Сид дня", skill: "Ловкость" };
const pfAct = { stars: "Изменение баланса", gift: "Выдача подарка", "gift-remove": "Изъятие подарка", keys: "Выдача ключей", comp: "Компенсация", cosm: "Косметика", undo: "Отмена действия",
  promo: "Акция", event: "Ивент", odds: "Изменение шансов", feecfg: "Изменение комиссий", claw: "Настройка крана", game: "Открытие или закрытие игры", flash_start: "Запуск ивента", flash_stop: "Остановка ивента",
  flashcfg: "Настройка ивентов", refcfg: "Настройка рефералки", paycfg: "Настройка переводов", frcfg: "Настройка франшизы", wipecfg: "Настройка вайпа", db_import: "Загрузка базы", shop: "Настройка магазина",
  adminlog_clear: "Очистка служебного журнала", actlog_clear: "Очистка журнала действий" };

const pfNum = n => fmt(Math.round(n || 0));
const pfPct = v => v == null ? "—" : (v * 100).toFixed(v * 100 % 1 ? 1 : 0) + "%";
const pfDate = ts => new Date(ts * 1000).toLocaleString(undefined, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const pfShort = (s, n = 10) => !s ? "—" : s.length <= n * 2 + 1 ? s : s.slice(0, n) + "…" + s.slice(-6);
const pfCopy = s => { try { navigator.clipboard.writeText(s); toast("Скопировано"); } catch (e) { toast(s); } };
const pfHashRow = (label, v) => `<div class="frow"><span>${label}</span><code>${pfShort(v, 12)}</code>${v ? `<button class="fcopy" data-act="pf-copy" data-v="${esc(v)}" aria-label="Копировать">${ic("copy")}</button>` : ""}</div>`;

async function openFair(game) {
  PF.game = game || ""; PF.exp = null; PF.old = null;
  PF.tab = game === "crash" ? "crash" : game ? "bets" : "over";
  openSheet(`<h2 class="gtitle">${ic("shield")} Честность</h2>
    <div class="ftabs" id="pf-tabs"></div><div id="pf-tab">${emptyHTML("hourglass", "Считаем…")}</div>`, "fair-s");
  pfDrawTabs(); pfLoad();
}

function pfDrawTabs() {
  const el = $("#pf-tabs"); if (!el) return;
  el.innerHTML = pfTabs.map(([k, t]) => `<button data-act="pf-tab" data-v="${k}" class="${PF.tab === k ? "on" : ""}">${t}</button>`).join("");
}

async function pfLoad() {
  try {
    if (["over", "games", "admin"].includes(PF.tab)) {
      PF.pub = await api("fair/public");
      if (PF.tab === "over") { PF.audit = await api("fair/audit"); PF.report = await api("fair/report").catch(() => null); await pfWitness().catch(() => {}); }
      if (PF.tab === "admin") PF.journal = (await api("fair/journal")).items;
    } else if (PF.tab === "gifts") {
      PF.gifts = await api("fair/gifts");
    } else if (PF.tab === "bets") {
      [PF.st, PF.hist] = await Promise.all([api("fair"), api("fair/history?limit=40" + (PF.game && PF.game !== "crash" ? "&game=" + PF.game : "")).then(r => r.items)]);
    } else if (PF.tab === "crash") {
      [PF.crash, PF.days, PF.car] = await Promise.all([api("fair/crash?limit=30"), api("fair/days").then(r => r.items), api("fair/carousel?limit=15")]);
    } else if (PF.tab === "chain") {
      if (!PF.pub) PF.pub = await api("fair/public");
      if (!PF.tag) PF.tag = (await api("fair/me-tag")).who;
      [PF.blocks, PF.tx] = await Promise.all([api("fair/blocks?limit=20").then(r => r.items), api("fair/tx?limit=40").then(r => r.items)]);
      PF.txEnd = false; PF.block = null;
    }
  } catch (e) { return; }
  pfDraw();
}

function pfDraw() {
  const el = $("#pf-tab"); if (!el) return;
  ({ over: pfOver, games: pfGames, bets: pfBets, gifts: pfGifts, crash: pfCrash, chain: pfChain, admin: pfAdmin })[PF.tab](el);
}

// ---------------- обзор ----------------
function pfOver(el) {
  const p = PF.pub, a = PF.audit; if (!p || !a) return;
  const ok = a.ok && a.trigger && p.ledger.trigger, b = p.ledger.block;
  const seeded = p.games.filter(g => g.kind !== "skill").length;
  el.innerHTML = `
    <div class="fhero ${ok ? "" : "bad"}">
      <div class="fhero-t">${ic(ok ? "check" : "shield")}<b>${ok ? "Журнал сходится" : "Найдено расхождение"}</b></div>
      <p>${ok ? `Проверено блоков: ${a.checked}. Записи не менялись задним числом.` : "Записи журнала не совпадают с блоками. Подробности — ниже."}</p>
      ${a.broken && a.broken.length ? `<ul class="fbad">${a.broken.slice(0, 5).map(x => `<li>Блок #${x.id}: ${esc(x.why)}</li>`).join("")}</ul>` : ""}
    </div>
    <div class="fstats">
      <div><span>Звёзд у игроков</span><b>${short(b ? b.supply : 0)}</b></div>
      <div><span>Блоков в журнале</span><b>${fmt(p.ledger.blocks)}</b></div>
      <div><span>Выдано админом за 7 дн</span><b class="${p.emission.week.s ? "warn" : ""}">${short(p.emission.week.s)}</b></div>
      <div><span>Игр с проверкой</span><b>${seeded} из ${p.games.length}</b></div>
    </div>
    ${pfReport()}
    <div class="sec-t">Как это устроено</div>
    <div class="box fsteps">
      <div><i>1</i><p><b>Результат зафиксирован до ставки.</b> Мы показываем хэш секретного сида. Подменить сид потом нельзя: хэш не сойдётся.</p></div>
      <div><i>2</i><p><b>Ты влияешь на результат.</b> В расчёт входит твой сид, поэтому заранее подобрать проигрыш под тебя нельзя.</p></div>
      <div><i>3</i><p><b>Проверить можно самому.</b> После смены сида он раскрывается, и телефон пересчитывает ставку сам, без участия сервера.</p></div>
      <div><i>4</i><p><b>Все движения звёзд в журнале.</b> Изменения балансов записываются на уровне базы и связываются в цепочку блоков. Майнинга и токенов нет, это только учёт.</p></div>
    </div>
    <div class="sec-t">Во что больше играют за 7 дней</div>
    <div class="box">${pfPopular(p)}</div>
    <div class="sec-t">Откуда и куда шли звёзды за 7 дней</div>
    <div class="box">${pfSources(p)}</div>
    <div class="sec-t">Доказательства</div>
    <div class="box fproof">
      <div><b>Твой телефон — свидетель</b><p>${pfWitnessText(p)}</p></div>
      <div><b>Твой баланс в общем резерве</b><p>Сумма балансов ${short(+p.reserve.total)} собрана в дерево хэшей. Проверь, что твой баланс в неё входит.</p>
        <button class="btn sm ghost" data-act="pf-reserve">Проверить мой баланс</button><div class="fres" id="pf-reserve-res"></div></div>
    </div>
    <div class="fnote"><b>Сборы банка.</b> С выигрышей от 10 000 звёзд банк берёт 1%. С прибыли бизнесов и дохода подарков берётся налог, с переводов и маркета комиссия. Все они видны в отчёте и транзакциях.</div>
    <div class="fnote"><b>Что это не гарантирует.</b> У владельца сервера есть полный доступ к базе, и в теории он может её переписать. Это перестанет быть незаметным: хэши блоков уже лежат на телефонах игроков и не совпадут с новыми.</div>`;
}

// свидетель: телефон хранит хэши блоков и сверяет их с сервером при каждом открытии панели
const PF_WK = "pf_witness3";
function pfWitnessText(p) {
  const w = PF.witness, st = (w && w.stats) || p.witness;
  if (w && w.bad && w.bad.length) return `<span class="bad">Сервер отдал другой хэш для блоков: ${w.bad.slice(0, 5).join(", ")}. История менялась.</span>`;
  return `${w ? `Сверено блоков на твоём телефоне: ${fmt(w.checked)}. Расхождений нет. ` : ""}Игроков, сверявших журнал за сутки: ${fmt(st.day)}. Сигналов о расхождении: ${fmt(st.bad)}.`;
}
async function pfWitness() {
  let saved = [];
  try { saved = JSON.parse(localStorage.getItem(PF_WK) || "[]"); } catch (e) {}
  const blocks = (await api("fair/blocks?limit=50")).items;
  const known = new Map(saved.map(x => [x[0], x[1]]));
  const local = blocks.filter(b => known.has(b.id) && known.get(b.id) !== b.hash).map(b => b.id);
  const r = await post("fair/witness", { v: 3, blocks: saved.slice(-200) });
  r.bad = [...new Set([...(r.bad || []), ...local])];
  blocks.forEach(b => known.set(b.id, b.hash));
  try { localStorage.setItem(PF_WK, JSON.stringify([...known].sort((a, b) => a[0] - b[0]).slice(-200))); } catch (e) {}
  PF.witness = r;
}
async function pfVerifyReserve(d) {
  let h = await pfShaHex(`${d.salt}:${d.balance}`), s = BigInt(d.balance);
  for (const n of d.path) {
    const ns = BigInt(n.s);
    h = await pfShaHex(n.left ? `${n.h}:${n.s}:${h}:${s}` : `${h}:${s}:${n.h}:${n.s}`);
    s += ns;
  }
  return h === d.root && String(s) === d.total;
}

function pfReport() {
  const r = PF.report; if (!r || !r.weeks.length) return "";
  const wk = x => `${new Date(x.from * 1000).toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" })} – ${new Date(x.to * 1000).toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" })}`;
  const sign = n => `<b class="${n >= 0 ? "good" : "bad"}">${n >= 0 ? "+" : "−"}${short(Math.abs(n))}</b>`;
  const w = r.weeks[0];
  return `<div class="sec-t">Отчёт банка за неделю</div><div class="box frep">
    <div class="frep-h"><span>${wk(w)}</span>${sign(w.net)}</div>
    ${w.groups.map(g => `<div class="fsrc"><span>${esc(g.title)}</span><em></em>${sign(g.net)}</div>`).join("")}
    ${r.weeks.length > 1 ? `<details class="fapi"><summary>Прошлые недели</summary>${r.weeks.slice(1).map(x => `<div class="fsrc"><span>${wk(x)}</span><em></em>${sign(x.net)}</div>`).join("")}</details>` : ""}</div>`;
}

// ---------------- подарки: счётчик и поиск по номеру ----------------
function pfGifts(el) {
  const g = PF.gifts; if (!g) return;
  el.innerHTML = `<div class="fstats">
      <div><span>Сейчас у игроков</span><b>${short(g.alive)}</b></div><div><span>В хранилище банка</span><b>${short(g.vault)}</b></div>
      <div><span>Выпущено</span><b>${short(g.minted)}</b></div><div><span>Сгорело</span><b>${short(g.burned)}</b></div></div>
    <div class="sec-t">Найти подарок по номеру</div>
    <div class="fsearch"><input id="pf-gnum" inputmode="numeric" placeholder="Номер подарка"><button class="btn sm cta" data-act="pf-gfind">Найти</button></div>
    <div id="pf-gres"></div>
    <div class="sec-t">По коллекциям</div>
    <p class="hint fintro">Выпуск и сжигание считаются с момента запуска истории подарков.</p>
    <div class="box"><div class="fgc head"><span>Коллекция</span><em>есть</em><em>вып.</em><em>сгор.</em></div>${g.items.map(x => `<div class="fgc"><span>${esc(x.col)}</span><em>${short(x.alive)}</em><em>${short(x.minted)}</em><em>${short(x.burned)}</em></div>`).join("") || emptyHTML("gift", "Подарков пока нет")}</div>`;
}

async function openGiftPage(x) {
  const el = openSheet(`<h2 class="gtitle">${esc(x.col)} #${x.num}</h2>
    <div class="gpage">${giftHTML(x, { big: true })}<b>${esc(x.model)}</b><span>${esc(x.backdrop)} · ${esc(x.symbol)}</span></div>
    <div class="fstats"><div><span>Ценность</span><b>⭐ ${short(x.value)}</b></div><div><span>Владелец</span><b>${x.owner ? esc(x.owner.name) : "Банк"}</b></div></div>
    <div id="gpage-h"></div>`, "gp-s");
  giftHistory($("#gpage-h"), x.id);
  starify(el);
}

function pfPopular(p) {
  const rows = p.games.filter(g => g.n7 > 0).sort((a, b) => b.n7 - a.n7).slice(0, 10), top = rows.length ? rows[0].n7 : 1, all = rows.reduce((t, g) => t + g.n7, 0);
  if (!rows.length) return emptyHTML("games", "За неделю ещё не играли");
  return rows.map(g => `<div class="fpop"><span>${esc(g.title)}</span><em>${fmt(g.n7)} · ${Math.round(g.n7 / all * 100)}%</em><i><b style="width:${Math.max(3, g.n7 / top * 100)}%"></b></i></div>`).join("");
}

function pfSources(p) {
  const rows = (p.sources || []).filter(r => r.plus !== r.minus).slice(0, 14);
  if (!rows.length) return emptyHTML("receipt", "Пока нет движений");
  return rows.map(r => {
    const net = r.plus - r.minus;
    return `<div class="fsrc"><span>${esc(p.names[r.kind] || r.kind)}</span><em>${fmt(r.n)}</em><b class="${net >= 0 ? "good" : "bad"}">${net >= 0 ? "+" : "−"}${short(Math.abs(net))}</b></div>`;
  }).join("");
}

// ---------------- шансы всех игр ----------------
function pfGames(el) {
  const p = PF.pub; if (!p) return;
  el.innerHTML = `<p class="hint fintro">Заявлено — настройка игры. Факт — сколько реально вернулось игрокам. На малом числе ставок факт сильно колеблется, это нормально.</p>
    <div class="box">${p.games.map(pfGameRow).join("")}</div>
    <div class="sec-t">История изменения шансов</div>
    <div class="box">${p.odds.length ? p.odds.map(o => {
      const g = p.games.find(x => x.id === o.game);
      return `<div class="fsrc"><span>${esc(g ? g.title : o.game)}${o.promo ? ` · акция` : ""}</span><em>${pfDate(o.ts)}</em><b>${o.old == null ? "старт" : pfPct(o.old) + " →"} ${pfPct(o.new)}</b></div>`;
    }).join("") : emptyHTML("shield", "Шансы не менялись")}</div>`;
}

const PF_RULES_EXTRA = {
  case: "Покупаешь кейс и получаешь один случайный подарок. Коллекция выпадает по весам кейса, шансы по коллекциям открыты ниже. Подарок можно оставить, продать или выставить на маркет.",
  keno: "Выбери до 10 номеров из поля и сделай ставку. Выпадает тираж случайных номеров. Выигрыш зависит от числа угаданных: чем их больше, тем выше множитель по таблице.",
  chicken: "Веди курицу через полосы дороги. Каждая пройденная полоса поднимает множитель, но на любой её могут сбить, и тогда ставка сгорает. Забрать выигрыш можно после любого шага. Режим сложности задаёт риск.",
  pump: "Качай шар: каждый качок поднимает множитель и риск, что шар лопнет. Лопнул — ставка сгорает. Забрать выигрыш можно в любой момент.",
  fish: "Закинь удочку и жди поклёвку. После неё множитель растёт, а рыба может сорваться в заранее брошенной точке. Вытащи её раньше, чтобы получить ставку × множитель.",
  penalty: "Выбери зону удара. Вратарь закрывает случайные зоны, их число зависит от режима. Гол поднимает множитель, сейв сжигает ставку. Забрать можно после любого гола, максимум 10 ударов.",
  drill: "Бур проходит пласты сверху вниз. На каждом пласте он может остановиться. Выплата зависит от достигнутой глубины и выбранного режима.",
  darts: "Выбери риск и брось дротик. Зона попадания определяет множитель. Чем выше риск, тем больше пустых зон и выше множители в остальных.",
  avia: "Самолёт летит над облаками и собирает множители. Выигрыш засчитывается, только если он успешно приземлится на палубу.",
  dogs: "Автомат 5×3 с 20 линиями. Три одинаковых символа слева направо дают выплату, вайлды заменяют символы и умножают выигрыш. Три и больше лапок запускают фриспины с липкими вайлдами.",
  duel: "Создай вызов со ставкой или прими чужой. Победитель забирает обе ставки за вычетом комиссии.",
  cards: "Ставка вносится при посадке за стол. Победитель забирает банк стола за вычетом комиссии. Правила каждой игры показаны в её окне.",
  starfall: "Вноси звёзды в общую шкалу. Когда она заполнится, подарок получит один из участников. Шанс равен доле вклада.",
  jackpot: "Билеты дают участие в ежедневном розыгрыше банка. Шанс равен доле твоих билетов, призы получают три победителя.",
  carousel: "Раунд общий на всех. Ставишь на секторы, при выпадении получаешь ставку × множитель. Бонусы играют только те, кто на них поставил.",
  ladder: "На каждой из 10 ступеней две двери: за одной шаг вверх, за другой обрыв. Забрать выигрыш можно после любой ступени. Подсказка показывает верную дверь и стоит 105% от суммы на кону.",
  safe: "Код из 3 цифр, 5 попыток. После каждой видно, какие позиции угаданы. Чем быстрее открыл, тем выше множитель. Открывший за 1–2 попытки забирает общий фонд.",
  bankbet: "Ставка на то, вырастет банк за следующий час или упадёт. Победители делят ставки проигравших, банк берёт комиссию. Изменение считается без операций участников раунда.",
  forecast: "Ставка на итоги следующих суток по Москве: самый большой икс краша, число бонусов Карусели и рост банка. Победители делят ставки проигравших, банк берёт комиссию. Линия фиксируется до приёма ставок и равна медиане прошлых суток.",
  stack: "Бесплатная игра на ловкость: нажимай вовремя и складывай блоки. Награда зависит от достигнутой высоты, случайна только раскладка.",
};
const PF_RULE_ID = { duel: "duels", cards: "blackjack", jroul: "jroul", case: "cases" };
function pfRules(id) {
  const r = typeof RULES !== "undefined" && (RULES[id] || RULES[PF_RULE_ID[id]]);
  let html = "";
  try { html = r ? r() : ""; } catch (e) {}
  html = html || PF_RULES_EXTRA[id] || "";
  return html ? `<div class="sec-t">Правила</div><div class="frules">${html}</div>` : "";
}

function pfGameRow(g) {
  const open = PF.exp === "g" + g.id;
  const fact = g.stake ? g.pay / g.stake : null;
  const co = PF.caseOdds;
  return `<div class="fitem${open ? " open" : ""}"><div class="fitem-h" data-act="pf-exp" data-k="g${g.id}">
      <b>${esc(g.title)}</b>
      <span class="frtp"><small>заявлено</small>${pfPct(g.rtp)}</span>
      <span class="frtp"><small>факт</small>${fact == null ? "—" : pfPct(fact)}</span>${ic("chev")}</div>
    ${open ? `<div class="fitem-b">
      ${pfRules(g.id)}<div class="sec-t">Как считается результат</div><span class="fbadge">${pfKind[g.kind]}</span><p class="fhow">${esc(g.how)}</p>
      <div class="frow"><span>Ставок всего</span><b>${fmt(g.n)}</b></div>
      <div class="frow"><span>Поставлено</span><b>${pfNum(g.stake)}</b></div>
      <div class="frow"><span>Выплачено</span><b>${pfNum(g.pay)}</b></div>
      <div class="frow"><span>За 7 дней</span><b>${g.stake7 ? pfPct(g.pay7 / g.stake7) + " · " + fmt(g.n7) + " ставок" : "—"}</b></div>
      ${g.id === "case" ? `<div class="sec-t">Шансы в кейсах</div><div class="fcases">${(CASES || []).map(c => `<button class="btn sm ghost" data-act="pf-case" data-v="${esc(c.id)}">${esc(c.title)}</button>`).join("")}</div><div id="pf-case">${co.html || ""}</div>` : ""}
    </div>` : ""}</div>`;
}

// ---------------- мои ставки и сиды ----------------
function pfBets(el) {
  const s = PF.st; if (!s) return;
  el.innerHTML = `
    <div class="box">
      <div class="frow"><span>Твой сид</span><code>${esc(s.client_seed)}</code><button class="btn sm ghost" data-act="pf-cs">Сменить</button></div>
      ${pfHashRow("Хэш сида сервера", s.hash)}
      <div class="frow"><span>Ставок на сиде</span><b>${fmt(s.bets || 0)}</b></div>
      <button class="btn ghost fwide" data-act="pf-rotate" ${s.busy ? "disabled" : ""}>${ic("refresh")} Раскрыть сид и проверить ставки</button>
      ${s.busy ? `<p class="hint">Сначала доиграй партию: её результат уже зафиксирован этим сидом.</p>` : ""}
    </div>
    ${PF.old ? `<div class="box fok">${ic("check")}<div>Сид раскрыт, ставок на нём: ${fmt(PF.old.bets)}. Теперь их можно проверить ниже.</div></div>` : ""}
    <div class="sec-t">Последние ставки</div>
    <div class="box" id="pf-hist">${PF.hist && PF.hist.length ? PF.hist.map(pfBetRow).join("") : emptyHTML("shield", "Ставок пока не было")}</div>
    <details class="fapi"><summary>Как считается</summary>
      <code>draw(i) = HMAC_SHA256(сид_сервера, "твой_сид:nonce:игра:ref:i")</code>
      <p class="hint">Берутся первые 15 hex-символов и переводятся в число от 0 до 1. Из него игра получает результат по формуле со вкладки «Шансы». Считает твой телефон, внешних сервисов нет.</p>
    </details>`;
}

function pfBetRow(x) {
  const open = PF.exp === "b" + x.id, profit = x.stake != null ? x.pay - x.stake : null;
  return `<div class="fitem${open ? " open" : ""}"><div class="fitem-h" data-act="pf-exp" data-k="b${x.id}">
      <b>${esc(x.title)}</b>
      ${profit == null || !x.stake ? `<span></span>` : `<span class="${profit >= 0 ? "good" : "bad"}">${profit >= 0 ? "+" : "−"}${short(Math.abs(profit))}</span>`}
      <span>${pfDate(x.ts)}</span>${ic("chev")}</div>
    ${open ? `<div class="fitem-b">
      ${pfHashRow("Хэш сида", x.hash)}
      <div class="frow"><span>Твой сид</span><code>${esc(x.cs || "")}</code></div>
      <div class="frow"><span>Nonce</span><b>${x.nonce}</b></div>
      <div class="frow"><span>Бросков</span><b>${x.n}</b></div>
      ${x.seed ? pfHashRow("Сид сервера", x.seed) : ""}
      <button class="btn sm cta fwide" data-act="pf-verify" data-id="${x.id}" ${x.seed ? "" : "disabled"}>${x.seed ? "Проверить на телефоне" : "Раскрой сид, чтобы проверить"}</button>
      <div class="fres" id="pf-res-${x.id}"></div>
    </div>` : ""}</div>`;
}

// ---------------- WebCrypto: те же формулы, что в server/fair.py ----------------
const pfEnc = s => new TextEncoder().encode(s);
const pfHex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
const pfShaHex = async s => pfHex(await crypto.subtle.digest("SHA-256", pfEnc(s)));
async function pfHmacHex(seed, msg) {
  const key = await crypto.subtle.importKey("raw", pfEnc(seed), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return pfHex(await crypto.subtle.sign("HMAC", key, pfEnc(msg)));
}
const pfU = hx => parseInt(hx, 16) / 16 ** 15;
const pfIdx = (r, n) => Math.min(Math.floor(r * n), n - 1);
function pfSample(rs, pop, k) { const p = [...pop], o = []; for (let i = 0; i < k; i++) o.push(p.splice(pfIdx(rs[i], p.length), 1)[0]); return o; }
function pfPick(r, w) { const t = w.reduce((a, b) => a + b, 0); let x = r * t, acc = 0; for (let i = 0; i < w.length; i++) { acc += w[i]; if (x < acc) return i; } return w.length - 1; }
const pfRange = (a, n) => Array.from({ length: n }, (_, i) => a + i);
const pfSame = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// как результат получается из бросков: true — сошлось, false — нет, null — формула сложнее, сверяем только слепок бросков
const PF_DERIVE = {
  dice: (rs, x) => Math.abs(pfIdx(rs[0], 10000) / 100 - x.roll) < 0.011,
  limbo: (rs, x) => Math.abs(Math.max(1, Math.min(10000, Math.floor(x.edge * 100 / (1 - rs[0])) / 100)) - x.result) < 0.011,
  wheel: (rs, x) => pfIdx(rs[0], x.segs) === x.idx,
  rlt: (rs, x) => pfIdx(rs[0], 37) === x.n,
  mines: (rs, x) => pfSame(pfSample(rs, pfRange(0, 25), x.n), x.bombs),
  tower: (rs, x) => pfSame(rs.map(r => pfIdx(r, x.tiles)), x.bombs),
  keno: (rs, x) => pfSame(pfSample(rs, pfRange(1, x.N), rs.length), x.draw),
  plinko: (rs, x) => pfSame(x.slots.map((_, b) => pfRange(0, x.rows).reduce((s, j) => s + pfIdx(rs[b * x.rows + j], 2), 0)), x.slots),
  slots: (rs, x) => pfSame(x.reels.map((_, s) => [0, 1, 2].map(j => pfPick(rs[s * 3 + j], x.w))), x.reels),
  upgrade: (rs, x) => (rs[0] < x.p) === x.win,
  claw: (rs, x) => (rs[0] < x.p) === x.win,
  chicken: (rs, x) => (rs[0] < x.p) === x.hit,
  pump: (rs, x) => (rs[0] < x.p) === x.hit,
  ladder: (rs, x) => pfSame(rs.map(r => pfIdx(r, 2)), x.doors),
  safe: (rs, x) => rs.slice(0, 3).map(r => pfIdx(r, 10)).join("") === x.code,
  hilo: (rs, x) => x.card == null ? null : 1 + pfIdx(rs[0], 13) === x.card && pfIdx(rs[1], 4) === x.suit,
};

async function pfVerifyBet(x) {
  let hash_ok, digest_ok, rs;
  if (window.crypto && crypto.subtle) {
    hash_ok = await pfShaHex(x.seed) === x.hash;
    const hexes = [];
    for (let i = 0; i < x.n; i++) hexes.push((await pfHmacHex(x.seed, `${x.cs}:${x.nonce}:${x.game}:${x.ref}:${i}`)).slice(0, 15));
    digest_ok = (await pfShaHex(hexes.join(","))).slice(0, 32) === x.digest;
    rs = hexes.map(pfU);
  } else {   // браузер без WebCrypto: считает наш сервер, и это честно указано в результате
    const v = await post("fair/verify", { server_seed: x.seed, hash: x.hash, client_seed: x.cs, nonce: x.nonce, game: x.game, ref: x.ref, n: x.n, digest: x.digest });
    hash_ok = v.hash_ok; digest_ok = v.digest_ok; rs = v.uniform;
  }
  const d = PF_DERIVE[x.game];
  let out_ok = null;
  if (d && x.res && Object.keys(x.res).length && rs.length >= (x.n > 200 ? 0 : x.n)) { try { out_ok = d(rs, x.res); } catch (e) { out_ok = null; } }
  return { hash_ok, digest_ok, out_ok, local: !!(window.crypto && crypto.subtle) };
}

const pfCheck = (ok, yes, no) => `<div class="fchk ${ok ? "good" : "bad"}">${ok ? "✓" : "✗"} ${ok ? yes : no}</div>`;

// ---------------- краш и общий сид ----------------
function pfCrash(el) {
  const c = PF.crash; if (!c) return;
  el.innerHTML = `
    <div class="box">
      ${pfHashRow("Вершина цепочки", c.commit)}
      <div class="frow"><span>Раундов сыграно</span><b>${fmt(c.pos)} из ${fmt(c.size)}</b></div>
      <p class="hint">Все сиды посчитаны заранее одной цепочкой, и её вершина опубликована до первого раунда. Каждый новый сид — хэш-прообраз предыдущего, поэтому подобрать «удобный» раунд невозможно.</p>
    </div>
    <div class="sec-t">Последние раунды</div>
    <div class="box">${c.items.length ? c.items.map(pfCrashRow).join("") : emptyHTML("rocket", "Раундов ещё не было")}</div>
    <div class="sec-t">Карусель: последние раунды</div>
    <div class="box">${PF.car && PF.car.items.length ? PF.car.items.map(x => `<div class="fitem"><div class="fitem-h"><b>Раунд ${fmt(x.pos)}</b><span>${esc(x.sector)}</span><button class="btn sm ghost" data-act="pf-car" data-pos="${x.pos}">Проверить</button></div><div class="fres" id="pf-car-${x.pos}"></div></div>`).join("") : emptyHTML("games", "Раундов ещё не было")}</div>
    <div class="sec-t">Общий сид дня: дуэли, столы, розыгрыши</div>
    <div class="box">${(PF.days || []).length ? PF.days.map(d => `<div class="fday"><b>${new Date(d.day * 86400000).toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" })}</b><em>${fmt(d.draws)} розыгр.</em>
      <code>${pfShort(d.seed || d.hash, 10)}</code><span class="${d.seed ? "good" : ""}">${d.seed ? "раскрыт" : "хэш"}</span>
      <button class="fcopy" data-act="pf-copy" data-v="${esc(d.seed || d.hash)}" aria-label="Копировать">${ic("copy")}</button></div>`).join("") : emptyHTML("shield", "Пока пусто")}
      <p class="hint">Хэш публикуется заранее, сам сид — через двое суток, когда партии того дня точно закончены.</p></div>`;
}

function pfCrashRow(x) {
  const open = PF.exp === "c" + x.pos;
  return `<div class="fitem${open ? " open" : ""}"><div class="fitem-h" data-act="pf-exp" data-k="c${x.pos}">
      <b>Раунд ${fmt(x.pos)}</b><span class="${x.crash < 2 ? "bad" : "good"}">x${(+x.crash).toFixed(2)}</span><span>${pfDate(x.ts)}</span>${ic("chev")}</div>
    ${open ? `<div class="fitem-b">
      ${pfHashRow("Сид раунда", x.seed)}
      <div class="frow"><span>Возврат раунда</span><b>${pfPct(x.edge)}</b></div>
      <button class="btn sm cta fwide" data-act="pf-verify-crash" data-pos="${x.pos}">Проверить до вершины цепочки</button>
      <div class="fres" id="pf-cres-${x.pos}"></div></div>` : ""}</div>`;
}

async function pfVerifyCrash(x, res) {
  const r = pfU((await pfHmacHex(x.seed, "crash")).slice(0, 15));
  const crash = Math.max(1, Math.min(10000, Math.floor(x.edge * 100 / (1 - r)) / 100));
  let cur = x.seed;
  for (let i = 1; i <= x.pos; i++) {
    cur = await pfShaHex(cur);
    if (i % 2000 === 0) { res.textContent = `Проверяем цепочку: ${fmt(i)} из ${fmt(x.pos)}…`; await new Promise(f => setTimeout(f)); }
  }
  return { crash, crash_ok: Math.abs(crash - x.crash) < 0.011, chain_ok: cur === PF.crash.commit };
}

// ---------------- блоки и транзакции ----------------
function pfChain(el) {
  const p = PF.pub; if (!p) return;
  el.innerHTML = `
    <div class="ftabs sub">
      <button data-act="pf-ex" data-v="blocks" class="${PF.ex === "blocks" ? "on" : ""}">Блоки</button>
      <button data-act="pf-ex" data-v="tx" class="${PF.ex === "tx" ? "on" : ""}">Транзакции</button></div>
    <div id="pf-ex"></div>`;
  const b = $("#pf-ex");
  if (PF.ex === "blocks") {
    b.innerHTML = `<p class="hint fintro">Раз в 10 минут изменения балансов запечатываются в блок. В каждом блоке хранится хэш предыдущего, поэтому старую запись нельзя тихо поправить.</p>
      <div class="box">${(PF.blocks || []).length ? PF.blocks.map(pfBlockRow).join("") : emptyHTML("receipt", "Первый блок появится через 10 минут")}</div>`;
  } else {
    b.innerHTML = `<p class="hint fintro">Все движения звёзд, без имён. Псевдоним меняется каждые сутки. Твой сегодня: <b class="ftag">${esc(PF.tag)}</b></p>
      <div class="box" id="pf-txs">${(PF.tx || []).map(pfTxRow).join("") || emptyHTML("receipt", "Пока нет транзакций")}</div>
      ${PF.txEnd || !(PF.tx || []).length ? "" : `<button class="btn ghost fwide" data-act="pf-tx-more">Показать ещё</button>`}`;
  }
}

function pfBlockRow(x) {
  const open = PF.exp === "k" + x.id, d = PF.block && PF.block.block.id === x.id ? PF.block : null;
  return `<div class="fitem${open ? " open" : ""}"><div class="fitem-h" data-act="pf-block" data-id="${x.id}">
      <b>#${fmt(x.id)}</b><span>${fmt(x.n)} зап.</span><span class="${x.net > 0 ? "warn" : x.net < 0 ? "good" : ""}">${x.net > 0 ? "+" : x.net < 0 ? "−" : ""}${short(Math.abs(x.net))}</span>${x.ok ? "" : `<span class="bad">расхождение</span>`}${ic("chev")}</div>
    ${open ? `<div class="fitem-b">
      ${pfHashRow("Хэш блока", x.hash)}${pfHashRow("Предыдущий", x.prev)}
      <div class="frow"><span>Время</span><b>${pfDate(x.ts)}</b></div>
      <div class="frow"><span>Звёзд у игроков</span><b>${fmt(x.supply)}</b></div>
      <div class="frow"><span>Подарков</span><b>${fmt(x.gifts)} · ${short(x.gifts_value)}</b></div>
      ${d ? `<div class="sec-t">Записи блока</div>${d.items.map(r => `<div class="ftx"><code>${esc(r.who)}</code><span>${pfDate(r.ts)}</span><b class="${r.delta >= 0 ? "good" : "bad"}">${r.delta >= 0 ? "+" : "−"}${fmt(Math.abs(r.delta))}</b></div>`).join("") || `<p class="hint">Записи старше 90 дней убраны, блок остаётся в цепочке.</p>`}` : `<p class="hint">Загружаем записи…</p>`}
    </div>` : ""}</div>`;
}

function pfTxRow(r) {
  const p = PF.pub, mine = r.who === PF.tag;
  return `<div class="ftx${mine ? " me" : ""}"><code>${esc(r.who)}</code><span>${esc((p && p.names[r.kind]) || r.kind)}<small>${pfDate(r.ts)}</small></span><b class="${r.delta >= 0 ? "good" : "bad"}">${r.delta >= 0 ? "+" : "−"}${fmt(Math.abs(r.delta))}</b></div>`;
}

// ---------------- журнал администрации ----------------
function pfAdmin(el) {
  const p = PF.pub, j = PF.journal; if (!p || !j) return;
  el.innerHTML = `
    <div class="fstats two">
      <div><span>Выдано за 7 дней</span><b class="${p.emission.week.s ? "warn" : ""}">${short(p.emission.week.s)}</b><em>${fmt(p.emission.week.n)} операций</em></div>
      <div><span>Выдано за всё время</span><b>${short(p.emission.total.s)}</b><em>${fmt(p.emission.total.n)} операций</em></div>
    </div>
    <p class="hint fintro">Сюда автоматически попадает каждое действие администрации, влияющее на звёзды, подарки и шансы. Удалить запись из админки нельзя.</p>
    <div class="box">${j.length ? j.map(r => `<div class="fj"><div><b>${esc(pfAct[r.action] || r.action)}</b><span>${pfDate(r.ts)}</span></div>
      ${r.who || r.detail ? `<p>${r.who ? `<code>${esc(r.who)}</code> ` : ""}${esc(r.detail || "")}</p>` : ""}</div>`).join("") : emptyHTML("shield", "Администрация ничего не меняла")}</div>`;
}

// ---------------- действия ----------------
const pfHistRow = id => (PF.hist || []).find(x => x.id === +id);
Object.assign(ACT, {
  "fair": el => openFair(el.dataset.game || ""),
  "pf-tab": el => { PF.tab = el.dataset.v; PF.exp = null; pfDrawTabs(); const t = $("#pf-tab"); if (t) t.innerHTML = emptyHTML("hourglass", "Считаем…"); pfLoad(); },
  "pf-ex": el => { PF.ex = el.dataset.v; PF.exp = null; pfDraw(); },
  "pf-exp": el => { PF.exp = PF.exp === el.dataset.k ? null : el.dataset.k; pfDraw(); },
  "pf-copy": el => pfCopy(el.dataset.v),
  "pf-case": async el => {
    try {
      const d = await api("fair/case/" + encodeURIComponent(el.dataset.v));
      PF.caseOdds.html = `<div class="box fcase">${d.items.map(r => `<div class="fsrc"><span>${esc(r.col)}</span><em>≈ ${short(r.ev)}</em><b>${r.p}%</b></div>`).join("")}</div>`;
      const b = $("#pf-case"); if (b) b.innerHTML = PF.caseOdds.html;
    } catch (e) {}
  },
  "pf-cs": async () => {
    const seed = await promptM("Свой сид", "От 4 до 64 символов: латиница, цифры, - и _. Смена сида раскрывает текущий сид сервера.", PF.st.client_seed, "Сохранить", "text");
    if (seed === null) return;
    try {
      const r = await post("fair/client-seed", { seed });
      PF.st = r; PF.old = { bets: r.old_bets }; PF.hist = (await api("fair/history?limit=40")).items;
      toast("Сид обновлён"); pfDraw();
    } catch (e) {}
  },
  "pf-rotate": async () => {
    if (!await confirmM("Раскрыть сид?", "Текущий сид сервера станет публичным, и ставки на нём можно будет проверить. Для новых ставок появится новый сид.", "Раскрыть")) return;
    try {
      const r = await post("fair/rotate");
      PF.st = r; PF.old = { bets: r.old_bets }; PF.hist = (await api("fair/history?limit=40")).items;
      pfDraw();
    } catch (e) {}
  },
  "pf-verify": async el => {
    const x = pfHistRow(el.dataset.id), res = $("#pf-res-" + el.dataset.id); if (!x || !res) return;
    res.textContent = "Считаем…";
    try {
      const v = await pfVerifyBet(x);
      res.innerHTML = pfCheck(v.hash_ok, "Хэш совпал с показанным до ставки", "Хэш НЕ совпал") +
        pfCheck(v.digest_ok, "Броски совпали с записанными при ставке", "Броски НЕ совпали") +
        (v.out_ok === null ? `<p class="hint">Результат этой игры собирается по более сложной формуле, сверяются сид и броски.</p>` : pfCheck(v.out_ok, "Результат игры пересчитан и совпал", "Результат НЕ совпал")) +
        `<p class="hint">${v.local ? "Посчитано на твоём устройстве." : "Этот браузер не умеет считать сам, поэтому посчитал наш сервер."}</p>`;
    } catch (e) { res.innerHTML = `<span class="bad">Не удалось проверить</span>`; }
  },
  "pf-verify-crash": async el => {
    const x = PF.crash.items.find(r => r.pos === +el.dataset.pos), res = $("#pf-cres-" + el.dataset.pos); if (!x || !res) return;
    res.textContent = "Считаем…";
    try {
      const v = await pfVerifyCrash(x, res);
      res.innerHTML = pfCheck(v.crash_ok, `Взрыв пересчитан: x${v.crash.toFixed(2)}`, `Взрыв не совпал: x${v.crash.toFixed(2)}`) + pfCheck(v.chain_ok, "Сид ведёт к опубликованной вершине цепочки", "Сид НЕ ведёт к вершине цепочки");
    } catch (e) { res.innerHTML = `<span class="bad">Проверка работает только по HTTPS</span>`; }
  },
  "pf-block": async el => {
    const id = +el.dataset.id, k = "k" + id;
    if (PF.exp === k) { PF.exp = null; return pfDraw(); }
    PF.exp = k; PF.block = null; pfDraw();
    try { PF.block = await api("fair/block/" + id); if (PF.exp === k) pfDraw(); } catch (e) {}
  },
  "pf-gfind": async () => {
    const res = $("#pf-gres"), n = +($("#pf-gnum") || {}).value; if (!res) return;
    if (!n) return toast("Введи номер подарка");
    try {
      const r = await api("gift/find?num=" + n); PF.gfound = r.items;
      res.innerHTML = r.items.length ? `<div class="box">${r.items.map((x, i) => `<div class="fsrc tap" data-act="pf-gopen" data-i="${i}"><span>${esc(x.col)} · ${esc(x.model)}</span><em>${x.owner ? esc(x.owner.name) : "Банк"}</em><b>#${x.num}</b></div>`).join("")}</div>` : `<p class="hint">Подарка с таким номером нет.</p>`;
    } catch (e) {}
  },
  "pf-gopen": el => openGiftPage(PF.gfound[+el.dataset.i]),
  "pf-car": async el => {
    const x = PF.car.items.find(r => r.pos === +el.dataset.pos), res = $("#pf-car-" + el.dataset.pos); if (!x || !res) return;
    res.textContent = "Считаем…";
    try {
      const r = pfU((await pfHmacHex(x.seed, "wheel")).slice(0, 15)), sec = x.order[pfPick(r, x.weights)];
      let cur = x.seed; for (let i = 1; i <= x.pos; i++) { cur = await pfShaHex(cur); if (i % 2000 === 0) await new Promise(f => setTimeout(f)); }
      res.innerHTML = pfCheck(sec === x.sector, `Сектор пересчитан: ${sec}`, `Сектор не совпал: ${sec}`) + pfCheck(cur === PF.car.commit, "Сид ведёт к опубликованной вершине цепочки", "Сид НЕ ведёт к вершине цепочки");
    } catch (e) { res.innerHTML = `<span class="bad">Не удалось проверить</span>`; }
  },
  "pf-reserve": async () => {
    const res = $("#pf-reserve-res"); if (!res) return; res.textContent = "Считаем…";
    try {
      const d = await api("fair/reserve/me");
      if (!d.included) { res.innerHTML = `<p class="hint">В последнем снимке твоего баланса ещё нет: снимок делается раз в 10 минут.</p>`; return; }
      const ok = await pfVerifyReserve(d);
      res.innerHTML = pfCheck(ok, `Баланс ${fmt(+d.balance)} входит в общую сумму`, "Баланс НЕ сходится с общей суммой") + `<p class="hint">Снимок от ${pfDate(d.ts)}. Посчитано на твоём устройстве.</p>`;
    } catch (e) { res.innerHTML = `<span class="bad">Не удалось проверить</span>`; }
  },
  "pf-tx-more": async () => {
    const last = PF.tx[PF.tx.length - 1]; if (!last) return;
    try {
      const r = await api("fair/tx?limit=40&before=" + last.id);
      PF.tx.push(...r.items); PF.txEnd = r.items.length < 40; pfDraw();
    } catch (e) {}
  },
});

"use strict";
// ============================================================
//  Gift Cases — игра-симулятор подарков Telegram (всё ненастоящее)
// ============================================================
const tg = window.Telegram && Telegram.WebApp;
const inTg = !!(tg && tg.initData);
// мини-апп свёрнут: фоновые опросы сервера пропускаем (батарея, трафик, нагрузка), при возврате — сразу обновляем
const bgOff = () => document.hidden || !!(tg && tg.isActive === false);
if (!inTg) document.body.classList.add("no-tg");
const DEV_USER = new URLSearchParams(location.search).get("dev");

const H = {
  imp: s => { if (window.NO_VIBRO) return; try { tg.HapticFeedback.impactOccurred(s) } catch (e) {} },
  sel: () => { if (window.NO_VIBRO) return; try { tg.HapticFeedback.selectionChanged() } catch (e) {} },
  ok: () => { if (window.NO_VIBRO) return; try { tg.HapticFeedback.notificationOccurred("success") } catch (e) {} },
  err: () => { if (window.NO_VIBRO) return; try { tg.HapticFeedback.notificationOccurred("error") } catch (e) {} },
};
if (tg) try {
  tg.ready(); tg.expand();
  tg.disableVerticalSwipes && tg.disableVerticalSwipes();
  tg.setHeaderColor && tg.setHeaderColor("secondary_bg_color");
  tg.setBackgroundColor && tg.setBackgroundColor("secondary_bg_color");
  tg.setBottomBarColor && tg.setBottomBarColor("secondary_bg_color");
} catch (e) {}

// ------------------------------------------------------------ звёзды: любой ⭐ в интерфейсе → иконка в стиле Telegram Stars
const STAR_SVG = '<svg viewBox="0 0 24 24"><use href="#xtr"/></svg>';
// В русском интерфейсе дробные множители и проценты пишутся через запятую, в каком бы модуле ни был собран текст
const NUM_RU = (() => { try { return localStorage.getItem("lang") !== "en"; } catch (e) { return true; } })();
const NUM_DOT = /[x×]\d+\.\d|\d\.\d+(?:%|x\b)/, NUM_DOT_G = /([x×]\d+)\.(\d)|(\d)\.(\d+(?:%|x\b))/g;
function starify(root) {
  if (!root || !root.ownerDocument && root !== document) return;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: n => (n.nodeValue.includes("⭐") || (NUM_RU && NUM_DOT.test(n.nodeValue))) && n.parentNode && !n.parentNode.closest("textarea,input,script,style,title") ? 1 : 3,
  });
  const list = []; while (w.nextNode()) list.push(w.currentNode);
  for (const n of list) {
    if (NUM_RU && NUM_DOT.test(n.nodeValue)) n.nodeValue = n.nodeValue.replace(NUM_DOT_G, "$1$3,$2$4");
    if (!n.nodeValue.includes("⭐")) continue;
    const f = document.createDocumentFragment();
    n.nodeValue.replace(/️/g, "").split("⭐").forEach((part, i) => {
      if (i) { const s = document.createElement("span"); s.className = "xtr"; s.innerHTML = STAR_SVG; f.appendChild(s); }
      if (part) f.appendChild(document.createTextNode(part));
    });
    n.replaceWith(f);
  }
}
new MutationObserver(ms => {
  for (const m of ms) {
    if (m.type === "characterData") { if (m.target.parentNode) starify(m.target.parentNode); }
    else m.addedNodes.forEach(n => n.nodeType === 1 ? starify(n) : n.nodeType === 3 && n.parentNode && starify(n.parentNode));
  }
}).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
document.addEventListener("DOMContentLoaded", () => starify(document.body));
starify(document.body);

// ------------------------------------------------------------ утилиты
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const enc = s => encodeURIComponent(s).replace(/'/g, "%27").replace(/\(/g, "%28").replace(/\)/g, "%29");
const fmt = n => Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");   // неразрывный пробел: число не рвётся между строками
// 12 345 → «12,3K», 10 000 → «10K», 2 500 000 → «2,5M»
const short = n => { const f = (v, d) => v.toFixed(d).replace(/\.0$/, "").replace(".", ","); return n >= 1e6 ? f(n / 1e6, n >= 1e7 ? 0 : 1) + "M" : n >= 1e4 ? f(n / 1e3, n >= 1e5 ? 0 : 1) + "K" : fmt(n); };
const pct = p => (p / 10).toString().replace(".", ",") + "%";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const clock = s => { s = Math.max(0, Math.ceil(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0"); };
const plural = (n, f) => { n = Math.abs(n) % 100; if (n > 10 && n < 20) return f[2]; n %= 10; return n === 1 ? f[0] : n > 1 && n < 5 ? f[1] : f[2]; };

// один и тот же POST (адрес + данные), пока он ещё в пути, второй раз не шлём: двойной тап по «Забрать» / «Играть»
// давал красное «нечего забирать» / «игра уже идёт» сразу после выигрыша. Дубль тихо отклоняется (status — errlog его не шлёт).
const API_BUSY = new Set();
async function api(path, body, o) {   // o: timeout (мс) и quiet (без всплывающей ошибки) для запросов, где важна каждая секунда
  const key = body ? path + "|" + JSON.stringify(body) : "";
  if (key && API_BUSY.has(key)) throw Object.assign(new Error("dup"), { status: "dup" });
  if (key) API_BUSY.add(key);
  try { return await apiReq(path, body, o); } finally { if (key) API_BUSY.delete(key); }
}
async function apiReq(path, body, o = {}) {
  const ac = o.timeout ? new AbortController() : null, tm = ac && setTimeout(() => ac.abort(), o.timeout);
  try { return await apiFetch(path, body, o, ac); } finally { clearTimeout(tm); }
}
async function apiFetch(path, body, o, ac) {
  const headers = { "Content-Type": "application/json" };
  if (inTg) headers["X-Init-Data"] = tg.initData; else if (DEV_USER) headers["X-Dev-User"] = DEV_USER;
  let r;
  try { r = await fetch("api/" + path, { method: body ? "POST" : "GET", headers, body: body ? JSON.stringify(body) : undefined, signal: ac ? ac.signal : undefined }); }
  catch (e) { const m = "Нет связи с сервером — проверь интернет"; if (body && !o.quiet) { toast(m, "err"); H.err(); } throw Object.assign(new Error(m), { status: "net" }); }   // фоновые GET — молча
  let d = null; try { d = await r.json() } catch (e) { if (ac && ac.signal.aborted) throw Object.assign(new Error("timeout"), { status: "net" }); }
  if (!r.ok) {
    let m = d && typeof d.detail === "string" ? d.detail : "";
    if (r.status === 401 || m === "unauthorized") m = "Сессия устарела — закрой и открой игру заново";
    else if (m === "Not Found" || (!m && r.status === 404)) m = "Не найдено — обнови экран";
    else if (!m && r.status === 422) m = "Неверные данные — проверь сумму";
    else if (!m) m = r.status >= 500 ? "Сервер занят — попробуй через пару секунд" : "Ошибка сети — проверь интернет";
    if (!o.quiet && (body || (r.status < 500 && r.status !== 401))) { toast(m, "err"); H.err(); }   // сбои фоновых опросов (502 при перезапуске и т. п.) не показываем
    throw Object.assign(new Error(m), { status: r.status });   // status — чтобы errlog.js не слал на сервер обычные отказы API
  }
  if (r.headers.get("X-Rec") && typeof recSoon === "function") recSoon();   // новый личный рекорд (records.js)
  return d;
}
const post = (p, b = {}, o) => api(p, b, o);

// реестр объектов для data-k в разметке
const REG = new Map(); let regN = 0;
const reg = o => { const k = "k" + (++regN); REG.set(k, o); return k; };

// ------------------------------------------------------------ ассеты подарков (кэш nginx → api.changes.tg)
// сервис картинок принимает только 64/128/256/512 — любой другой размер подгоняем вверх до ближайшего
const imgSize = s => [64, 128, 256, 512].find(x => x >= s) || 512;
const A = {
  model: (c, m, s = 256) => `a/model/${enc(c)}/${enc(m)}.png?size=${imgSize(s)}`,
  pat: (c, s) => `a/pattern/${enc(c)}/${enc(s)}.png?size=64`,
  orig: (c, s = 256) => `a/original/${enc(c)}.png?size=${imgSize(s)}`,
  lottie: (c, m) => `a/model/${enc(c)}/${enc(m)}.json`,
};

// узор кольцами вокруг модели — как на улучшенных подарках Telegram
const PAT = (() => {
  const o = [], rings = [[.35, 6, 0, 15, .5], [.46, 10, .5, 12, .34], [.575, 14, 0, 10, .22], [.69, 18, .5, 8.5, .13]];
  for (const [r, n, off, s, a] of rings) for (let i = 0; i < n; i++) {
    const an = (i + off) / n * Math.PI * 2 - Math.PI / 2;
    o.push([50 + Math.cos(an) * r * 92, 46 + Math.sin(an) * r * 92, s, a]);
  }
  return o;
})();

function tier(g) {
  const p = g.mp;
  return p <= 5 ? "gold" : p <= 10 ? "pink" : p <= 15 ? "purple" : p <= 20 ? "blue" : "gray";
}
function valTier(g, ref) {
  const k = g.value / Math.max(ref, 1);
  return k < .6 ? "gray" : k < 1.2 ? "blue" : k < 3 ? "purple" : k < 8 ? "pink" : "gold";
}
function giftHTML(g, o = {}) {
  const [c1, c2, c3, c4] = g.c, pat = A.pat(g.col, g.symbol), t = tier(g);
  let h = `<div class="gift${o.big ? " big" : ""}${t === "gold" && !o.plain ? " shine" : ""}" style="--c1:${c1};--c2:${c2};--c3:${c3};--c4:${c4}">`;
  for (const [x, y, s, a] of (o.lite ? PAT.slice(0, 16) : PAT))
    h += `<i style="left:${x}%;top:${y}%;width:${s}%;height:${s}%;opacity:${a};-webkit-mask-image:url('${pat}');mask-image:url('${pat}')"></i>`;
  h += `<img src="${o.img || A.model(g.col, g.model, o.big ? 512 : 256)}"${o.eager ? "" : ' loading="lazy"'} alt="">`;
  if (o.big && !o.img) h += `<div class="lt" data-lottie="${A.lottie(g.col, g.model)}"></div>`;
  if (o.tag) h += `<div class="tag">${o.tag}</div>`;
  if (!o.plain && (t === "gold" || t === "pink")) h += `<div class="rib t-${t}">${t === "gold" ? "LEGENDARY" : "EPIC"}</div>`;
  return h + "</div>";
}
const CPAT = (() => {   // россыпь узора по карточке кейса
  const o = [];
  for (let r = 0; r < 6; r++) for (let c = 0; c < 4; c++) {
    const x = 12 + c * 25.3 + (r % 2 ? 12.6 : 0), y = 7 + r * 17;
    if (x > 104) continue;
    o.push([x, y, 11 + ((r * 3 + c) % 3) * 2, .5]);
  }
  return o;
})();
const patHTML = (col, sym, pts, k = 1) => pts.map(([x, y, sz, a]) =>
  `<i class="pi" style="left:${x}%;top:${y}%;width:${sz * k}%;aspect-ratio:1;opacity:${a};-webkit-mask-image:url('${A.pat(col, sym)}');mask-image:url('${A.pat(col, sym)}')"></i>`).join("");
// ставки комиссий из админки (fees.py); до первого /me — значения по умолчанию
const FEE = (k, d) => (ME && ME.fees && ME.fees[k] != null ? ME.fees[k] : d);
const feeP = (k, d) => pctF(FEE(k, d));
const pctF = v => String(+(v * 100).toFixed(2)).replace(".", ",") + "%";   // 0.025 → «2,5%»
const sellP = () => pctF(1 - FEE("sell", .15));   // мгновенная продажа банку, «85%»

// доход подарка: 2% ценности в сутки, легендарные ×2, эпики ×1,5
const giftPerHour = g => g.value * .02 / 24 * (g.mp <= 5 ? 2 : g.mp <= 10 ? 1.5 : 1);
const perHourTxt = v => v >= 100 ? fmt(Math.round(v)) : v >= 10 ? v.toFixed(1).replace(".", ",") : v.toFixed(2).replace(".", ",");
const giftName = g => `${esc(g.col)} <small>#${fmt(g.num)}</small>`;

// анимация модели в большой карточке (Lottie)
let LOTTIE_P = null;
const lottieLoad = () => LOTTIE_P || (LOTTIE_P = new Promise((ok, no) => {
  const s = document.createElement("script"); s.src = "lottie-light-5.12.2.min.js?v=1"; s.async = true;
  s.onload = ok; s.onerror = () => { LOTTIE_P = null; no(); }; document.head.appendChild(s);
}).catch(() => {}));
const LOTTIES = new Set();
function startLottie(root) {
  if (window.LITE) return;   // режим оптимизации: подарки статичными картинками
  if (!window.lottie) {   // библиотека анимаций грузится только когда впервые понадобилась (не на старте игры)
    if (!root.querySelector("[data-lottie]")) return;
    lottieLoad().then(() => root.isConnected && startLottie(root));
    return;
  }
  root.querySelectorAll("[data-lottie]").forEach(el => {
    if (el._l) return;
    const a = lottie.loadAnimation({ container: el, renderer: "svg", loop: true, autoplay: true, path: el.dataset.lottie });
    a.addEventListener("DOMLoaded", () => { const img = el.previousElementSibling; if (img) img.style.opacity = 0; });
    el._l = a; LOTTIES.add(a); a._root = root;
  });
}
function stopLottie(root) { for (const a of [...LOTTIES]) if (root.contains(a.wrapper)) { a.destroy(); LOTTIES.delete(a); } }

function avaHTML(u, s = 36, o = {}) {
  const bg = `hsl(${(u.id * 47) % 360} 55% 52%)`;
  const ini = esc(((u.name || "?").trim()[0] || "?").toUpperCase());
  const img = u.photo ? `<img src="${esc(u.photo)}" referrerpolicy="no-referrer" onerror="this.remove()" alt="">` : "";
  return `<div class="ava${o.ring ? " ring" : ""}${u.frame ? " fr-" + u.frame : u.vip ? " fr-vip" : ""}" style="--s:${s}px;--ac:${bg};${o.p != null ? `--p:${o.p}%` : ""}"><span>${ini}</span>${img}${o.lv ? `<b class="lv">${u.level}</b>` : ""}${u.crown && s >= 30 ? `<i class="crown c${Math.min(u.crown, 4)}">${ic("crown")}</i>` : ""}</div>`;
}

// ------------------------------------------------------------ тосты, модалки, конфетти
let toastT;
function toast(text, kind = "") {
  const t = $("#toast");
  const k = kind || (/^(Не хватает|Нужен|Нужна|Эту|Так нельзя|Сначала|Максимум|Мимо|Пусто|Не повезло|Мина|Бомба)/.test(text) ? "err" : "");
  t.className = "toast " + k;
  t.innerHTML = (k ? `<span class="ti">${ic(k === "err" ? "x" : "check")}</span>` : "") + `<span>${esc(text)}</span>`;
  t.classList.add("on");
  clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("on"), 2600);
}
function modal(html) {
  return new Promise(res => {
    const m = $("#modal"), b = $("#modal-body");
    b.innerHTML = html; m.classList.add("on");
    const done = v => { m.classList.remove("on"); m.onclick = null; res(v); };
    m.onclick = e => {
      if (e.target === m) return done(null);
      const el = e.target.closest("[data-m]"); if (!el) return;
      const inp = b.querySelector("input,textarea");
      done(el.dataset.m === "ok" ? (inp ? inp.value : true) : null);
    };
    const inp = b.querySelector("input"); if (inp) setTimeout(() => inp.focus(), 50);
  });
}
const confirmM = (title, text, ok = "Да") => modal(`<h3>${title}</h3><p class="hint" style="margin:0 0 16px">${text}</p>
  <div class="btns"><button class="btn ghost" data-m="no">Отмена</button><button class="btn" data-m="ok">${ok}</button></div>`);
const promptM = (title, text, val = "", ok = "Готово", im = "numeric") => modal(`<h3>${title}</h3><p class="hint" style="margin:0 0 12px">${text}</p>
  <input inputmode="${im}"${im === "text" ? ' autocapitalize="characters" autocomplete="off" spellcheck="false"' : ""} value="${esc(val)}"><div class="btns"><button class="btn ghost" data-m="no">Отмена</button><button class="btn" data-m="ok">${ok}</button></div>`);

const fx = $("#fx"), fc = fx.getContext("2d"); let P = [], fxOn = false;
function fxSize() { const d = Math.min(devicePixelRatio || 1, 2); fx.width = innerWidth * d; fx.height = innerHeight * d; fc.setTransform(d, 0, 0, d, 0, 0); }
addEventListener("resize", fxSize); fxSize();
function burst(x, y, colors, n = 110) {
  if (window.LITE) n = Math.min(n, 30);
  for (let i = 0; i < n; i++) {
    const a = Math.random() * Math.PI * 2, v = 3 + Math.random() * 10;
    P.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 5, l: 1, c: colors[i % colors.length], w: 4 + Math.random() * 6, r: Math.random() * 6, vr: (Math.random() - .5) * .4, s: Math.random() < .3 });
  }
  if (!fxOn) { fxOn = true; requestAnimationFrame(fxLoop); }
}
let fxT = 0;
function fxLoop(now) {
  // шаг физики в «кадрах по 60 Гц» — на 90/120 Гц экранах конфетти летит с той же скоростью, только плавнее
  const k = fxT ? Math.min(3, (now - fxT) / 16.667) : 1; fxT = now;
  fc.clearRect(0, 0, innerWidth, innerHeight);
  for (const p of P) {
    p.vy += .3 * k; p.vx *= Math.pow(.985, k); p.x += p.vx * k; p.y += p.vy * k; p.r += p.vr * k; p.l -= .01 * k;
    fc.save(); fc.globalAlpha = Math.max(0, p.l); fc.translate(p.x, p.y); fc.rotate(p.r); fc.fillStyle = p.c;
    if (p.s) { fc.font = `${p.w * 2.4}px sans-serif`; fc.fillText("✦", -p.w, p.w); } else fc.fillRect(-p.w / 2, -p.w / 4, p.w, p.w / 2);
    fc.restore();
  }
  P = P.filter(p => p.l > 0 && p.y < innerHeight + 40);
  if (P.length) requestAnimationFrame(fxLoop); else { fxOn = false; fxT = 0; fc.clearRect(0, 0, innerWidth, innerHeight); }
}
function burstAt(el, g) {
  if (!el) return;
  const r = el.getBoundingClientRect();
  burst(r.left + r.width / 2, r.top + r.height / 2, g ? [g.c[0], g.c[3], "#fff", g.c[1]] : ["#ffd76a", "#ff6fb5", "#7cc2ff", "#fff"]);
  if (typeof coinShower === "function") coinShower(el, 26);   // монетки и звёзды фонтаном при любом выигрыше
}

// ------------------------------------------------------------ шторки (стек + BackButton телеги)
const SHEETS = [];
function openSheet(html, cls = "") {
  document.documentElement.classList.add("has-sheet");
  if (SHEETS.length) SHEETS[SHEETS.length - 1].classList.add("under");
  const el = document.createElement("div");
  el.className = "sheet " + cls;
  el.innerHTML = `<button class="x" data-act="close">${ic("x")}</button><button class="sbal" data-act="daily"><span>⭐</span><b class="bal-live">${ME ? fmt(ME.stars) : "—"}</b></button>` + html;
  document.body.appendChild(el);
  SHEETS.push(el);
  requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("on")));
  if (inTg) tg.BackButton.show();
  startLottie(el);
  return el;
}
function closeSheet() {
  const el = SHEETS.pop(); if (!el) return;
  if (!SHEETS.length) document.documentElement.classList.remove("has-sheet");
  else SHEETS[SHEETS.length - 1].classList.remove("under");
  el.classList.remove("on"); stopLottie(el);
  setTimeout(() => el.remove(), 350);
  if (!SHEETS.length && inTg) tg.BackButton.hide();
  if (el._onClose) el._onClose();
}
function replaceSheet(el, html) { stopLottie(el); el.innerHTML = `<button class="x" data-act="close">${ic("x")}</button><button class="sbal" data-act="daily"><span>⭐</span><b class="bal-live">${ME ? fmt(ME.stars) : "—"}</b></button>` + html; startLottie(el); }
if (inTg) tg.BackButton.onClick(closeSheet);

// ------------------------------------------------------------ состояние
let ME = null, CASES = [], BANNERS = null, MYP = null, TAB = "cases";
const CASE_COL = {
  first_ed: ["#2fb6a3", "#08352f"], gold_ed: ["#d9a521", "#3f2d05"],
  champ: ["#e0483f", "#3d0d0a"], gadgets: ["#22a7c9", "#07303c"], treasure: ["#c99a2e", "#3a2a07"], knight: ["#6a7fb5", "#161f38"], cozy: ["#b8603a", "#3a1a0d"], nightlife: ["#c23d9e", "#340b2a"], crown: ["#8a4dff", "#1f0d4a"],
  free: ["#3fb27a", "#123a28"], starter: ["#6b7a91", "#1d2532"], sweet: ["#ff8fb8", "#6e1f45"], winter: ["#62bdff", "#16365f"],
  spooky: ["#ff8a3d", "#45170a"], love: ["#ff5f8f", "#55102b"], gangsta: ["#7d6cff", "#1d1450"], jewel: ["#4fd6c6", "#0d4442"],
  magic: ["#b56cff", "#350e5a"], durov: ["#4aa8ff", "#0b2850"], elite: ["#ffcf5a", "#5e3b00"], mega: ["#ff4d6d", "#38000f"],
  party: ["#ff7ad9", "#4a0f5c"], spring: ["#8fe36b", "#1d4a12"], food: ["#ffb35c", "#5a2a05"], summer: ["#3fd6ff", "#0a3c5c"],
  zoo: ["#c9a26b", "#3d2a12"], style: ["#9aa4b8", "#22262f"], space: ["#6a7dff", "#0c0f3a"], luck: ["#3fe08f", "#063d22"], heroes: ["#ff6a4a", "#4a0f05"],
  fresh: ["#ffd23f", "#4a1d00"], flea: ["#c08457", "#33200f"],
  pepehunt: ["#5fd068", "#0f3d14"], hearthunt: ["#ff4f7a", "#4a0a1e"], retro: ["#e0a96d", "#3d2410"], lux: ["#d4b46a", "#2e2410"],
  cups: ["#7cc2ff", "#0d2a52"], peach: ["#ffa07a", "#5a1e0a"],
  coin: ["#ffd76a", "#4a3200"], cute: ["#ffb3d1", "#5c1d3c"], tech: ["#5ad1ff", "#0b2f45"], peachhunt: ["#ff9b6a", "#561c08"],
  night: ["#c86bff", "#22083d"], caphunt: ["#4aa8ff", "#0a2448"], sport: ["#ff7a3d", "#4a1505"], royal: ["#ffe08a", "#3d1d4a"],
};

let BAL_HOLD = 0;   // >0 — идёт анимация игры: фоновое обновление не показывает итоговый баланс раньше времени
// Telegram кэширует страницу игры до 30 дней: если сервер собрал новую версию, уходим на новый адрес (?v=…) — он всегда свежий.
function checkBuild() {
  try {
    const sc = document.querySelector('script[src*="bundle.js?v="]'), mine = sc && (sc.getAttribute("src").match(/v=([0-9a-f]+)/) || [])[1];
    if (!mine || !ME || !ME.build || ME.build === mine) return;
    if (sessionStorage.getItem("np_upd") === ME.build) return;   // уже пробовали — не крутимся в цикле
    sessionStorage.setItem("np_upd", ME.build);
    toast("Есть обновление игры — перезагружаем…", "ok");
    setTimeout(() => location.replace(location.pathname + "?v=" + ME.build + location.hash), 900);
  } catch (e) {}
}
async function loadMe() {
  const prevKeys = ME ? ME.keys : null;
  let fresh = null;
  if (window.ME_P) { const p = window.ME_P; window.ME_P = null; fresh = await p.catch(() => null); }   // ранний запрос из index.html
  if (!fresh) fresh = await api("me");
  if (!fresh || typeof fresh !== "object") throw new Error("me: пустой ответ");   // иначе ME = null и таймеры падают каждую секунду
  if (BAL_HOLD > 0 && ME) fresh.stars = ME.stars;
  ME = fresh;
  renderHeader();
  checkBuild();
  if (prevKeys !== null && prevKeys !== ME.keys) {   // выдали ключи от кейсов — перезагружаем витрину, чтобы кнопка «Открыть ключом» появилась сразу
    CASES = [];
    if (TAB === "cases" && !SHEETS.length) renderCases();
  }
}
function setStars(s) {
  if (s == null) return;
  const old = ME.stars; ME.stars = s;
  $("#bal-n").textContent = fmt(s);
  paintBalance(s > old ? "up" : s < old ? "down" : "");
}
// живой баланс в шапке и во всех открытых шторках
function paintBalance(dir) {
  document.querySelectorAll(".bal-live").forEach(e => e.textContent = fmt(ME.stars));
  document.querySelectorAll(".sbal, #bal").forEach(e => e.classList.toggle("neg", ME.stars < 0));   // долг — админ списал в минус
  if (!dir) return;
  document.querySelectorAll(".sbal, #bal").forEach(e => { e.classList.remove("up", "down"); void e.offsetWidth; e.classList.add(dir); });
}
async function afterLevelUp(lv) {
  if (!lv) return;
  H.ok(); burst(innerWidth / 2, innerHeight / 3, ["#ffd76a", "#ffab2e", "#fff"]);
  await modal(`<div class="lvup"><div class="hint">Новый уровень</div><b>${lv.level}</b><p>Бонус: <span class="star">+${fmt(lv.bonus)} ⭐</span></p>
    <button class="btn gold" data-m="ok">Круто!</button></div>`);
  loadMe();
}

// ------------------------------------------------------------ подтверждение закрытия, пока идёт игра
function guardClose() {
  if (!inTg || !tg.enableClosingConfirmation) return;
  const busy = (typeof ROOM !== "undefined" && ROOM && ROOM.status === "playing" && SHEETS.some(s => s._room))
    || (typeof MS !== "undefined" && MS && MS.active && SHEETS.some(s => s.classList.contains("mines-s")))
    || (typeof TW !== "undefined" && TW && TW.active && SHEETS.some(s => s.classList.contains("tower-s")))
    || (typeof BJ !== "undefined" && BJ && BJ.active && SHEETS.some(s => s._bj))
    || (typeof CS !== "undefined" && CS && CS.my && !CS.my.cashed && CS.phase !== "end" && SHEETS.some(s => s.classList.contains("crash-s")));
  try { busy ? tg.enableClosingConfirmation() : tg.disableClosingConfirmation(); } catch (e) {}
}
setInterval(guardClose, 1500);

// ------------------------------------------------------------ табы
function moveTabInd() {
  const nav = $("#tabs"), on = nav.querySelector("button.on"), ind = $("#tab-ind");
  if (!on || !ind) return;
  ind.style.width = on.offsetWidth + "px";
  ind.style.transform = `translateX(${on.offsetLeft}px)`;
}
addEventListener("resize", moveTabInd);
const TITLES = { cases: "Кейсы", games: "Игры", inv: "Инвентарь", market: "Маркет", top: "Топ", crypto: "Крипта" };
function setTab(t) {
  if (!$("#v-" + t)) return;   // не вкладка (data-tab на постороннем элементе) — ничего не делаем
  if (t === TAB && $("#v-" + t).innerHTML) return;
  TAB = t;
  document.querySelectorAll("nav.tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
  moveTabInd();
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("on", v.id === "v-" + t));
  $("#title").textContent = TITLES[t];
  scrollTo(0, 0);
  const v = $("#v-" + t);
  // хаб игр почти статичный: если строили < 2 мин назад — показываем готовый, только оживляем счётчик краша и банк
  if (t === "games" && v._ts && Date.now() - v._ts < 120000 && v.innerHTML && typeof gamesResume === "function") return gamesResume();
  (TAB_RENDER[t] || { cases: renderCases, games: renderGames, inv: renderInventory, market: renderMarket, top: renderTop }[t])();
  if (t === "games") v._ts = Date.now();
}
// вкладки из отдельных файлов дописывают себя сюда (crypto.js)
const TAB_RENDER = {};

// ============================================================ КЕЙСЫ
// отложенная отрисовка: первые 6 карточек — сразу, остальные (за экраном) — порциями, когда браузер свободен.
// В разметке они есть с самого начала (display:none), так что код, ищущий .case, их видит.
function casesReveal(v) {
  const step = () => {
    const rest = v.querySelectorAll(".case.defer"); if (!rest.length) return;
    [...rest].slice(0, 6).forEach(c => c.classList.remove("defer"));
    if (rest.length > 6) idle(step);
  };
  const idle = f => (window.requestIdleCallback ? requestIdleCallback(f, { timeout: 500 }) : setTimeout(f, 60));
  requestAnimationFrame(() => idle(step));
}
async function renderCases() {
  const v = $("#v-cases");
  if (!CASES.length) CASES = await api("cases");
  const lvl = ME.lv.level;
  v.innerHTML = `
    ${ME.rooms ? `<button class="invbar" data-act="my-invites">${ic("userPlus")}<span><b>Тебя зовут за стол</b>${ME.rooms} ${plural(ME.rooms, ["приглашение", "приглашения", "приглашений"])} — нажми, чтобы сесть</span>${ic("chev")}</button>` : ""}
    ${flashBar()}
    ${frBanner()}
    <div class="promo">
      <button data-act="case" data-id="free" class="${ME.freeIn ? "" : "ready"}"><span class="pic g">${ic("gift")}</span><div><b>Бесплатный</b><span id="free-t">${ME.freeIn ? "через " + clock(ME.freeIn) : "можно открыть!"}</span></div></button>
      <button data-act="daily" class="${ME.dailyIn ? "" : "ready"}"><span class="pic y">${ic("calendar")}</span><div><b>Бонус дня</b><span>${ME.dailyIn ? "через " + clock(ME.dailyIn) : "забери звёзды"}</span></div></button>
      <button data-act="quests" class="${ME.quests ? "ready" : ""}"><span class="pic b">${ic("checks")}</span><div><b>Задания</b><span>${ME.quests ? "награды: " + ME.quests : "на сегодня"}</span></div></button>
    </div>
    <div class="sec-t">Кейсы</div>
    <div class="cases">${CASES.filter(c => c.id !== "free").sort((a, b) => a.price - b.price).map((c, ci) => {
      const [k1, k2] = CASE_COL[c.id] || ["#555", "#222"];
      return `<div class="case${c.id === "mega" ? " mega" : ""}${ci >= 6 ? " defer" : ""}" data-act="case" data-id="${c.id}" style="--k1:${k1};--k2:${k2}">
                ${c.id === "mega" ? `<span class="hot">${ic("flame")}HOT</span>` : c.level > 1 ? `<span class="lvtag">${c.level} ур.</span>` : ""}
        <span class="gl-art"><img class="cv" src="${A.orig(c.cover)}" alt="" loading="lazy"></span>
        <div class="cfoot"><div class="nm">${esc(c.title)}</div>${c.limit ? `<span class="c-limit">${c.left ? `Осталось ${fmt(c.left)} из ${fmt(c.limit)}` : "Тираж закончился"}</span>` : ""}<span class="minis">${c.previews.slice(0, 3).map(x => `<img src="${A.orig(x, 64)}" alt="" loading="lazy">`).join("")}</span></div>
        ${lvl < c.level ? `<div class="lock">${ic("lock")}${c.level} ур.</div>` : `<span class="pr">⭐ ${fmt(c.price)}</span>`}</div>`;
    }).join("")}</div>
    <div class="sec-t"><span class="live-dot"></span>Живая лента</div><div class="feed" id="feed"></div>
    <div class="disc">${esc(ME.disclaimer)}</div>`;
  casesReveal(v);
  loadFeed();
}
async function loadFeed() {
  const f = $("#feed"); if (!f) return;
  const items = await api("feed").catch(() => []);
  f.innerHTML = items.length ? items.map(x => `<div class="fi" data-act="gift" data-k="${reg({ g: x.gift, owner: x.user })}">${giftHTML(x.gift, { lite: true, plain: true })}${avaHTML(x.user, 20)}</div>`).join("")
    : `<span class="hint" style="font-size:13px">Тут будут дропы игроков</span>`;
}

const OPEN = { n: 1, fast: false };
function openCase(id) {
  const c = CASES.find(x => x.id === id);
  if (!c) { if (!CASES.length) api("cases").then(x => { CASES = x; openCase(id); }); return; }
  H.imp("light");
  const [k1, k2] = CASE_COL[c.id] || ["#555", "#222"];
  const ref = c.price || 300;
  if (!c.price) OPEN.n = 1;
  const el = openSheet(`
    <div class="chero" style="--k1:${k1};--k2:${k2}"><div class="cpat">${patHTML(c.cover, c.pat, CPAT, .7)}</div><div class="rays"></div><div class="halo"></div>
      <img src="${A.orig(c.cover, 512)}" alt=""><h2>${esc(c.title)}</h2>
      <div class="cprice">${c.price ? "⭐ " + fmt(c.price) : `Бесплатно раз в ${ME.promo ? "1,5 часа" : "3 часа"}`}${c.level > 1 ? ` · от ${c.level} ур.` : ""}</div></div>
    <div id="rouls"></div>
    <div id="won"></div>
    ${c.price ? `<div class="ocount">${[1, 2, 3, 5, 10].map(n => `<button data-act="open-n" data-v="${n}" class="${OPEN.n === n ? "on" : ""}">x${n}</button>`).join("")}
      <button class="ofast${OPEN.fast ? " on" : ""}" data-act="open-fast">${ic("trend")}Быстро</button></div>` : ""}
    <div class="btns" id="obtns">${openBtn(c)}</div>
    <div class="sec-t">Что внутри</div>
    <div class="ggrid">${c.items.map(it => { const t = valTier({ value: it.ev }, ref);
      return `<div class="gcell item r-${t}">${giftHTML({ col: it.col, symbol: it.symbol, c: it.c, mp: 99 }, { img: A.orig(it.col), plain: true })}
      <span class="chance">${it.p < 1 ? it.p.toFixed(2) : it.p.toFixed(1)}%</span><div class="rbar b-${t}"></div>
      <div class="cap">${esc(it.col)}<br><small>~⭐ ${short(it.ev)}</small></div></div>`; }).join("")}</div>
    <div class="disc">Шансы честные и считаются на сервере. Из платного кейса не выпадает подарок дешевле ~40% его цены. ${esc(ME.disclaimer)}</div>`);
  el._case = c; el._ref = ref;
}
const openBtn = (c, again) => c.keys ? `<button class="btn cta gold" data-act="open-case" data-id="${c.id}">${ic("lock")}Открыть ключом · ${c.keys} шт.</button>` : `<button class="btn cta gold" data-act="open-case" data-id="${c.id}">${!c.price ? "Открыть бесплатно" : again ? `Ещё${OPEN.n > 1 ? " x" + OPEN.n : ""} · ⭐ ${short(c.price * OPEN.n)}` : `Открыть${OPEN.n > 1 ? " x" + OPEN.n : ""} за ⭐ ${fmt(c.price * OPEN.n)}`}</button>`;

let opening = false;
async function doOpen(sheet, id) {
  if (opening) return;
  const c = CASES.find(x => x.id === id), n = c.keys ? 1 : c.price ? OPEN.n : 1;
  if (!c.keys && ME.lv.level < c.level) return toast(`Нужен ${c.level} уровень`);
  if (id === "free" && !c.keys && ME.freeIn > 0) return toast(`Бесплатный кейс будет через ${clock(ME.freeIn)}`);
  if (!c.keys && c.price * n > ME.stars) { H.err(); return toast("Не хватает звёзд ⭐"); }
  opening = true;
  try { await doOpenInner(sheet, id, c, n); } finally { opening = false; }
}
async function doOpenInner(sheet, id, c, n) {
  const btns = sheet.querySelector("#obtns"), rouls = sheet.querySelector("#rouls"), won = sheet.querySelector("#won");
  btns.querySelectorAll("button").forEach(b => b.disabled = true);
  sheet.querySelectorAll(".ocount button").forEach(b => b.disabled = true);
  won.innerHTML = "";
  let r;
  // после бесплатного кейса обновляем ME — иначе на главной таймер ещё «можно открыть!»
  try { r = await post(`case/${id}/open?n=${n}`); c.keys = r.keys || 0; if (id === "free") loadMe().catch(() => {}); } catch (e) { btns.querySelectorAll("button").forEach(b => b.disabled = false); sheet.querySelectorAll(".ocount button").forEach(b => b.disabled = false); return; }
  setStars(r.stars);
  if (!OPEN.fast) {
    const small = n > 1, W = small ? 76 : 104, step = W + 8;
    rouls.innerHTML = r.strips.map(strip => `<div class="roul${small ? " sm" : ""}"><div class="mark"></div><div class="strip">${strip.map(g =>
      `<div class="it" style="width:${W}px">${giftHTML(g, { lite: true, plain: true, eager: true })}<div class="bar b-${valTier(g, sheet._ref)}"></div></div>`).join("")}</div></div>`).join("");
    rouls.scrollIntoView({ behavior: "smooth", block: n > 2 ? "start" : "center" });
    // ждём картинки ленты, чтобы не крутились пустые плитки (но не дольше 1.5 с)
    await Promise.race([Promise.all([...rouls.querySelectorAll("img")].map(i => i.decode().catch(() => {}))), sleep(1500)]);
    await sleep(150);
    const els = [...rouls.querySelectorAll(".roul")], cw = els[0].clientWidth;
    const plan = els.map((el, i) => ({ strip: el.querySelector(".strip"), target: r.win * step + W / 2 - cw / 2 + (Math.random() - .5) * W * .65, dur: (n > 1 ? 4200 : 5600) + i * 180 }));
    const t0 = performance.now();
    let last = -1;
    await new Promise(done => (function f(now) {
      let all = true;
      for (const p of plan) {
        const t = Math.min(1, (now - t0) / p.dur), x = p.target * (1 - Math.pow(1 - t, 4));
        p.strip.style.transform = `translateX(${-x}px)`;
        if (t < 1) all = false;
      }
      const idx = Math.floor((plan[0].target * (1 - Math.pow(1 - Math.min(1, (now - t0) / plan[0].dur), 4)) + cw / 2) / step);
      if (idx !== last) {   // предмет под маркером подрастает — лента «живая»
        for (const p of plan) { const it = p.strip.children; if (it[last]) it[last].classList.remove("cur"); if (it[idx]) it[idx].classList.add("cur"); }
        last = idx; H.sel();
      }
      !all && sheet.isConnected ? requestAnimationFrame(f) : done();
    })(t0));
    if (!sheet.isConnected) { loadMe(); return; }   // закрыли во время прокрутки — подарки уже в инвентаре
    for (const p of plan) { const w = p.strip.children[r.win]; if (w) { w.classList.remove("cur"); w.classList.add("hitw"); } }
    H.imp("heavy"); await sleep(OPEN.fast ? 0 : 650);
  } else rouls.innerHTML = "";
  const gifts = r.gifts, total = gifts.reduce((s, g) => s + g.value, 0), sellAll = gifts.reduce((s, g) => s + Math.floor(g.value * (1 - FEE("sell", .15))), 0);
  if (n === 1) {
    const g = gifts[0];
    const vt = valTier(g, sheet._ref), RAR = { gold: "Легендарный", pink: "Эпический", purple: "Редкий", blue: "Хороший", gray: "Обычный" };
    won.innerHTML = `<div class="won wt-${vt}" style="margin-top:16px"><div class="won-g"><i class="won-rays"></i>${giftHTML(g, { big: true })}</div>
      <span class="won-rar">${RAR[vt]}</span>
      <h2 style="margin:10px 0 0;font-size:22px">${esc(g.col)}</h2><div class="hint">#${fmt(g.num)} · ${esc(g.model)} · ${esc(g.backdrop)}</div>
      <div class="won-v star">≈ ⭐ <b id="won-v">0</b></div></div>`;
    startLottie(won);
    const wv = won.querySelector("#won-v"), t0v = performance.now();
    (function cnt(t) { const k = Math.min(1, (t - t0v) / 900); if (!wv.isConnected) return; wv.textContent = fmt(g.value * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(cnt); })(t0v);
    if (c.price && g.value >= c.price * 5) setTimeout(() => bigWin(g.value, g.value / c.price, g.value / c.price, { gift: g.id }), 700);
  } else {
    const best = gifts.reduce((a, b) => b.value > a.value ? b : a);
    won.innerHTML = `<div class="multi"><div class="mt"><b>Выпало на ⭐ ${fmt(total)}</b><span class="${total >= c.price * n ? "win" : "lose"}">${total >= c.price * n ? "+" : "−"}⭐ ${fmt(Math.abs(total - c.price * n))}</span></div>
      <div class="ggrid">${gifts.map((g, i) => `<div class="gcell mw${g === best ? " best" : ""}" style="animation-delay:${i * 60}ms" data-act="gift" data-k="${reg({ g, mine: true })}">${giftHTML(g, { lite: true, tag: "⭐ " + short(g.value) })}<div class="cap">${giftName(g)}</div></div>`).join("")}</div></div>`;
  }
  btns.innerHTML = `<button class="btn ghost" data-act="sell-won" data-ids="${gifts.map(g => g.id).join(",")}">${ic("coins")}⭐ ${short(sellAll)}</button>${openBtn(c, true)}`;
  if (!c.price) btns.lastElementChild.disabled = true;
  sheet.querySelectorAll(".ocount button").forEach(b => b.disabled = false);
  won.scrollIntoView({ behavior: "smooth", block: "center" });
  H.ok(); burstAt(won.querySelector(".gift"), gifts[0]);
  if (gifts.some(g => ["gold", "pink"].includes(tier(g)))) setTimeout(() => { H.ok(); burstAt(won, gifts[0]); }, 400);
  if (id === "free") loadMe().catch(() => {});   // точное время перезарядки — с сервера (в акцию она короче)
  await afterLevelUp(r.levelup);
}

// ============================================================ ЕЖЕДНЕВКА
const DAILY_KEYS = { 2: "Охота на Пепе", 3: "Удача", 5: "Охота на Сердце", 7: "Роскошь" };
// как на сервере (STREAK_KEYS): ключ на 2, 3, 5, 7 день, дальше «Роскошь» каждые 7 дней (14, 21, 28…)
const dailyKey = d => DAILY_KEYS[d] || (d > 7 && d % 7 === 0 ? DAILY_KEYS[7] : null);
function openDaily(tab) {
  const next = ME.streakNext || ME.streak + 1, cur = ME.dailyIn ? ME.streak : next;
  const w0 = Math.floor((Math.max(1, cur) - 1) / 7) * 7;   // показываем текущую неделю серии: 1–7, 8–14, 15–21…
  const pay = d => (300 + 100 * Math.min(d, 7)) * (ME.promo ? 2 : 1);
  const days = [1, 2, 3, 4, 5, 6, 7].map(i => w0 + i).map(d => {
    const done = d <= ME.streak && ME.dailyIn, now = d === next && !ME.dailyIn;
    return `<div class="dl-d${done ? " done" : ""}${now ? " now" : ""}"><span>день ${d}</span><b>${short(pay(d))}</b>${dailyKey(d) ? `<i>${ic("lock")}</i>` : done ? `<i>${ic("check")}</i>` : ""}</div>`;
  }).join("");
  const t = tab || (ME.dailyIn ? "shop" : "daily");
  const el = openSheet(`<div class="st-hero">
      <div class="st-hero-ic">${STAR_SVG}<i></i></div>
      <h2>Звёзды</h2>
      <div class="seg st-tabs"><button data-act="st-tab" data-v="shop">${ic("tgplane")}Пополнить</button>
        <button data-act="st-tab" data-v="daily">${ic("calendar")}Бонус дня${ME.dailyIn ? "" : `<i class="st-dot"></i>`}</button></div>
    </div>
    <div class="st-pane" data-p="shop"><div id="shop-box">${emptyHTML("hourglass", "Загружаем магазин…")}</div></div>
    <div class="st-pane" data-p="daily">
      <div class="dl-hero">
        <div class="dl-h-t"><span>${ME.dailyIn ? "Сегодня уже забрал" : `День ${next} серии`}</span>
          <b>${ME.dailyIn ? `Следующий через ${clock(ME.dailyIn)}` : `⭐ ${fmt(pay(next))}${dailyKey(next) ? " + ключ" : ""}`}</b>
          <small>Заходи каждый день — награда растёт до 7 дня. На 2, 3, 5 и 7 день — ключ от кейса, дальше ключ «Роскошь» каждые 7 дней${ME.promo ? " · сегодня ×2" : ""}</small></div>
        ${ME.streakBest > 1 ? `<div class="dl-best">${ic("flame")}Рекорд серии: ${ME.streakBest} дн.</div>` : ""}
      </div>
      <div class="dl-days">${days}</div>
      <div class="btns" style="margin-top:12px">${ME.dailyIn ? `<button class="btn ghost" disabled>${ic("hourglass")}Через ${clock(ME.dailyIn)}</button>`
        : `<button class="btn gold" data-act="claim-daily">Забрать ⭐ ${fmt(pay(next))}${dailyKey(next) ? " + ключ" : ""}</button>`}</div>
      ${ME.streakMs ? `<div class="box dl-ms"><span class="pic y">${ic("trophy")}</span>
        <div class="grow"><div class="t">Награда за ${ME.streakMs.day} дней подряд</div>
        <div class="s">+${fmt(ME.streakMs.stars)} ⭐ + ключ «${ME.streakMs.key}» · осталось ${Math.max(0, ME.streakMs.day - ME.streak)} дн.</div></div></div>` : ""}
      <div class="sec-t">Ещё звёзды</div>
      <div class="box">
        <div class="row tap" data-act="invite"><span class="pic b">${ic("userPlus")}</span><div class="grow"><div class="t">Пригласи друга</div><div class="s">${ME.ref && ME.ref.on ? `до +${fmt((ME.ref.join || 0) + ME.ref.l1[1] + ME.ref.l2[1])} ⭐ за друга + топ недели` : "играйте вместе"}</div></div><span class="pill">${ME.refs}</span></div>
        ${ME.franchise ? `<div class="row tap" data-act="franchise-info"><span class="pic b">${ic("rocket")}</span><div class="grow"><div class="t">Свой бот с этой игрой</div><div class="s">${ME.franchise.cutTotal ? `Пассивный доход: получено ${fmt(ME.franchise.cutTotal)} ⭐` : ME.franchise.create || ME.franchise.reward ? `Создай за 1 тап · до +${fmt((ME.franchise.create || 0) + (ME.franchise.reward || 0))} ⭐` : "Создай за 1 тап — без @BotFather"}</div></div></div>` : ""}
        <div class="row tap" data-act="case" data-id="free"><span class="pic g">${ic("gift")}</span><div class="grow"><div class="t">Бесплатный кейс</div><div class="s">${ME.freeIn ? "через " + clock(ME.freeIn) : "готов"}</div></div></div>
        <div class="row"><span class="pic y">${ic("medal")}</span><div class="grow"><div class="t">Уровни</div><div class="s">За каждый новый уровень — бонус звёздами</div></div></div>
      </div>
    </div>
    <div class="disc">${esc(ME.disclaimer)}</div>`, "st-s");
  stTab(el, t);
}
// переключение «Пополнить / Бонус дня»; без магазина (продажа выключена) — только бонус
function stTab(el, t) {
  if (!el) return;
  if (el.classList.contains("no-shop")) t = "daily";
  el.dataset.stab = t;   // не data-tab: на него реагирует переключатель нижних вкладок (клик внутри окна сломал бы вкладку)
  el.querySelectorAll(".st-tabs button").forEach(b => b.classList.toggle("on", b.dataset.v === t));
}

// краш — в games.js

// ============================================================ ТОП
let topKind = "rich", RICH_PERKS = null;
const TOPK = [["rich", "wallet", "Богачи"], ["profit", "trend", "Профит"], ["week", "flame", "Неделя"], ["level", "medal", "Уровень"], ["crash", "rocket", "Краш"]];
const pm = n => n.won || n.lost ? `<span class="tw">+${short(n.won)}</span><span class="tl">−${short(n.lost)}</span>` : `<span class="hint">ещё не играл</span>`;
async function renderTop() {
  const v = $("#v-top");
  v.innerHTML = `<div class="bankbar" id="bank"><span class="bk-i">${ic("wallet")}</span><div><span>Банк игры</span><b id="bank-v">—</b></div><em id="bank-d"></em></div><div id="tme"></div>
    ${topNavHTML()}
    <div id="tlist">${emptyHTML("hourglass", "Загружаем…")}</div>`;
  loadBank();
  const d = await api("leaders?kind=" + topKind);
  if (TAB !== "top") return;
  const money = topKind === "profit" || topKind === "week";
  const sc = r => topKind === "level" ? `${r.score} ур.` : topKind === "crash" ? `x${(+r.score).toFixed(2)}`
    : money ? `${r.score >= 0 ? "+" : "−"}⭐ ${short(Math.abs(r.score))}` : `⭐ ${short(r.score)}`;
  const me = d.me, tme = $("#tme"); if (!tme) return;   // пока грузилось, переключили на «Сезон» — там другая разметка
  tme.innerHTML = `<div class="tme">
    <div class="tme-h">${avaHTML(ME, 40, { lv: true })}<div><b>Твоя статистика</b><span>${topKind === "week" ? "за эту неделю" : "за всё время"}${me.pos ? ` · ${me.pos} место` : ""}</span></div></div>
    <div class="tme-g"><div><span>Выиграно</span><b class="tw">+⭐ ${short(me.won)}</b></div><div><span>Проиграно</span><b class="tl">−⭐ ${short(me.lost)}</b></div>
      <div><span>Итог</span><b class="${me.net >= 0 ? "tw" : "tl"}">${me.net >= 0 ? "+" : "−"}⭐ ${short(Math.abs(me.net))}</b></div></div></div>`;
  const rows = d.rows;
  let h = topKind === "rich" && d.richPerks ? `<button class="richbar" data-act="rich-info">${ic("crown")}<span><b>Топ-10 богачей — награды каждый день</b>${d.myCrown ? `ты ${d.myCrown} место` : "ключи от кейсов и скидка на маркете"}</span>${ic("chev")}</button>` : "";
  RICH_PERKS = d.richPerks || RICH_PERKS;
  h += topKind === "week" ? `<div class="timer">${ic("flame")}Соревнование недели: профит с кейсов и игр · итоги через ${Math.max(0, Math.floor((d.weekEnds - Date.now() / 1000) / 3600))} ч</div>` : "";
  if (rows.length) {
    const top3 = [rows[1], rows[0], rows[2]];
    h += `<div class="podium">${top3.map((r, i) => r ? `<div class="p${[2, 1, 3][i]}" data-act="profile" data-id="${r.id}">${avaHTML(r, 58, { lv: true })}
      <div class="nm">${nameHTML(r)}</div><div class="sc">${sc(r)}</div><div class="pl">${pm(r)}</div><div class="ped">${[2, 1, 3][i]}</div></div>` : "<div></div>").join("")}</div>`;
    h += `<div class="box">${rows.slice(3).map((r, i) => `<div class="row tap" data-act="profile" data-id="${r.id}"><span class="place">${i + 4}</span>${avaHTML(r, 36)}
      <div class="grow"><div class="t">${nameHTML(r)}${r.id === ME.id ? " <span class='pill'>ты</span>" : ""}</div><div class="s pl">${pm(r)}</div></div><b class="num">${sc(r)}</b></div>`).join("")}</div>`;
    if (!me.pos) h += `<div class="disc">Тебя пока нет в топ-50 — открывай кейсы и играй</div>`;
  } else h += emptyHTML("trophy", "Пока пусто — стань первым");
  h += `<button class="ideabtn" data-act="idea">${ic("megaphone")}<span><b>Идеи и предложения</b>напиши, что добавить или исправить в игре</span>${ic("chev")}</button>`;
  $("#tlist").innerHTML = h;
}

// ============================================================ ПРОФИЛЬ
async function loadBanners() { if (!BANNERS) BANNERS = await api("banners"); return BANNERS; }
function bannerHTML(p) {
  if (p.bannerImg) return `<div class="banner photo" style="background-image:url('${esc(p.bannerImg)}')"></div>`;
  const b = p.banner && BANNERS && BANNERS.find(x => x.name === p.banner);
  const g0 = p.pinned[0] || p.gifts[0];
  const c = b ? b.c : g0 ? g0.c : ["#7b5cff", "#140f33", "#3a2a8f", "#fff"];   // без подарков — фирменный фиолетовый, а не серый
  let pat = "";
  if (g0) {
    const u = A.pat(g0.col, g0.symbol);
    const pts = [[12, 30, 9, .35], [28, 16, 7, .25], [72, 16, 7, .25], [88, 30, 9, .35], [8, 62, 7, .2], [92, 62, 7, .2], [22, 50, 11, .4], [78, 50, 11, .4], [38, 24, 6, .2], [62, 24, 6, .2], [50, 12, 6, .18], [32, 74, 6, .15], [68, 74, 6, .15]];
    pat = pts.map(([x, y, s, a]) => `<i style="left:${x}%;top:${y}%;width:${s}vw;height:${s}vw;max-width:${s * 5}px;max-height:${s * 5}px;opacity:${a};-webkit-mask-image:url('${u}');mask-image:url('${u}')"></i>`).join("");
  }
  return `<div class="banner" style="--c1:${c[0]};--c2:${c[1]};--c3:${c[2]}">${pat}</div>`;
}
async function openProfile(id) {
  H.imp("light");
  const el = openSheet(`<div class="empty" style="padding-top:120px"><b>⏳</b></div>`);
  await loadBanners();
  const p = await api("user/" + id).catch(() => null);
  if (!p) return closeSheet();
  if (id === ME.id) MYP = p;
  el._pid = id;
  replaceSheet(el, profileHTML(p));
}
async function refreshProfileSheets() {
  for (const el of SHEETS) if (el._pid) {
    const p = await api("user/" + el._pid).catch(() => null);
    if (p) { if (p.id === ME.id) MYP = p; replaceSheet(el, profileHTML(p)); }
  }
}

async function editProfile() {
  await loadBanners();
  MYP = await api("user/" + ME.id);
  const ed = { bio: MYP.bio || "", banner: MYP.banner || "", pinned: MYP.pinned.map(g => g.id), notif: ME.notif !== false, img: MYP.bannerImg || "", newImg: null,
    nick: MYP.nick || "", ava: MYP.avatarImg || "", newAva: null };
  const el = openSheet(`<h2 class="gtitle">Профиль</h2>
    <div class="eprev" id="e-prev"></div>
    <div class="sec-t">Имя в игре</div>
    <div class="eid-row">
      <label class="eava-edit"><span id="e-ava"></span><i class="eava-cam">${ic("edit")}</i><input type="file" accept="image/*" id="e-afile" hidden></label>
      <div class="grow"><input id="enick" maxlength="24" placeholder="${esc(MYP.tgName || "Ник")}" value="${esc(ed.nick)}">
        <div class="eid-hint" id="e-idhint"></div></div>
    </div>
    <div class="bnr-photo" id="e-defrow" style="${ed.nick || ed.ava || MYP.bannerImg ? "" : "display:none"}"><button class="btn ghost sm" id="e-tgdef">${ic("refresh")}Вернуть из Telegram</button></div>
    <div class="sec-t">О себе <span id="e-cnt"></span></div>
    <textarea id="ebio" rows="2" maxlength="140" placeholder="Пара слов о себе">${esc(ed.bio)}</textarea>
    <div class="sec-t">Баннер</div>
    <div class="bnr-photo"><label class="btn ghost">${ic("plus")}${MYP.bannerImg ? "Сменить фото" : "Своя картинка"}<input type="file" accept="image/*" id="e-file" hidden></label>
      <button class="btn ghost" id="e-nophoto" style="${MYP.bannerImg ? "" : "display:none"}">${ic("x")}Убрать</button></div>
    <div class="bnr-row" id="ebn"><button data-v="" class="${ed.banner ? "" : "on"}" style="--c1:#5a6278;--c2:#262a36"><span>авто</span></button>
      ${BANNERS.map(b => `<button data-v="${esc(b.name)}" class="${b.name === ed.banner ? "on" : ""}" style="--c1:${b.c[0]};--c2:${b.c[1]}" title="${esc(b.name)}"></button>`).join("")}</div>
    <div class="sec-t">Витрина · до 6 подарков <span id="e-pc"></span></div>
    <div class="epins" id="e-pins"></div>
    <div class="sec-t">Уведомления</div>
    <div class="box"><div class="row"><span class="pic b">${ic("send")}</span><div class="grow"><div class="t">Напоминания от бота</div>
      <div class="s">бесплатный кейс, серия бонусов, твой ход</div></div><button class="sw${ed.notif ? " on" : ""}" id="e-notif"></button></div></div>
    <div class="esave"><button class="btn cta" data-act="save-profile">${ic("check")}Сохранить</button></div>`, "edit-s");
  const all = new Map(MYP.gifts.map(g => [g.id, g]));
  const draw = () => {
    const curAva = ed.newAva !== null ? ed.newAva : ed.ava;       // "" — вернуть аватар из Telegram
    const pu = { ...MYP, name: ed.nick.trim() || MYP.tgName || "Игрок", photo: curAva || MYP.tgPhoto || "" };
    const prev = { ...pu, banner: ed.banner, bio: ed.bio, pinned: ed.pinned.map(i => all.get(i)).filter(Boolean), bannerImg: ed.newImg ?? ed.img };
    el.querySelector("#e-prev").innerHTML = bannerHTML(prev) + `<div class="eprev-u">${avaHTML(pu, 56)}<div><b>${esc(pu.name)}</b><span>${esc(ed.bio) || "без описания"}</span></div></div>`;
    el.querySelector("#e-ava").outerHTML = `<span id="e-ava">${avaHTML(pu, 52)}</span>`;
    const custom = ed.nick.trim() || curAva;
    el.querySelector("#e-idhint").textContent = custom ? "своё имя в игре" : "сейчас как в Telegram";
    el.querySelector("#e-defrow").style.display = custom ? "" : "none";
    el.querySelector("#e-cnt").textContent = `${ed.bio.length}/140`;
    el.querySelector("#e-pc").textContent = `${ed.pinned.length}/6`;
    el.querySelector("#e-pins").innerHTML = ed.pinned.map(i => all.get(i)).filter(Boolean).map(g => `<div class="gcell" data-unpin="${g.id}">${giftHTML(g, { lite: true, plain: true })}<span class="sel">${ic("x")}</span></div>`).join("")
      + (ed.pinned.length < 6 ? `<button class="eadd" data-act="e-pick">${ic("plus")}<span>Добавить</span></button>` : "");
  };
  el.querySelector("#ebio").oninput = e => { ed.bio = e.target.value; draw(); };
  el.querySelector("#ebn").onclick = e => {
    const b = e.target.closest("button"); if (!b) return;
    ed.banner = b.dataset.v; H.sel();
    el.querySelectorAll("#ebn button").forEach(x => x.classList.toggle("on", x === b)); draw();
  };
  el.querySelector("#e-pins").addEventListener("click", e => {
    const c = e.target.closest("[data-unpin]"); if (!c) return;
    ed.pinned = ed.pinned.filter(i => i !== +c.dataset.unpin); H.sel(); draw();
  });
  // своя картинка: обрезаем по центру до 1200×640 и жмём в JPEG прямо в браузере
  el.querySelector("#e-file").onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const url = URL.createObjectURL(f), im = new Image();
    im.onload = () => {
      const W = 1200, Hh = 640, k = Math.max(W / im.width, Hh / im.height), cw = W / k, ch = Hh / k;
      const cv = document.createElement("canvas"); cv.width = W; cv.height = Hh;
      cv.getContext("2d").drawImage(im, (im.width - cw) / 2, (im.height - ch) / 2, cw, ch, 0, 0, W, Hh);
      let q = .85, data = cv.toDataURL("image/jpeg", q);
      while (data.length > 900000 && q > .4) { q -= .1; data = cv.toDataURL("image/jpeg", q); }
      ed.newImg = data; URL.revokeObjectURL(url);
      el.querySelector("#e-nophoto").style.display = ""; H.sel(); draw();
    };
    im.onerror = () => toast("Не получилось открыть картинку", "err");
    im.src = url;
  };
  el.querySelector("#e-nophoto").onclick = () => { ed.newImg = ""; el.querySelector("#e-nophoto").style.display = "none"; H.sel(); draw(); };
  el.querySelector("#enick").oninput = e => { ed.nick = e.target.value; draw(); };
  // своя аватарка: обрезаем по центру в квадрат 256×256 и жмём в JPEG прямо в браузере
  el.querySelector("#e-afile").onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const url = URL.createObjectURL(f), im = new Image();
    im.onload = () => {
      const S = 256, side = Math.min(im.width, im.height);
      const cv = document.createElement("canvas"); cv.width = S; cv.height = S;
      cv.getContext("2d").drawImage(im, (im.width - side) / 2, (im.height - side) / 2, side, side, 0, 0, S, S);
      let q = .85, data = cv.toDataURL("image/jpeg", q);
      while (data.length > 380000 && q > .4) { q -= .1; data = cv.toDataURL("image/jpeg", q); }
      ed.newAva = data; URL.revokeObjectURL(url); H.sel(); draw();
    };
    im.onerror = () => toast("Не получилось открыть картинку", "err");
    im.src = url;
    e.target.value = "";
  };
  el.querySelector("#e-tgdef").onclick = () => {
    ed.nick = ""; ed.newAva = "";
    el.querySelector("#enick").value = "";
    H.sel(); draw();
  };
  el.querySelector("#e-notif").onclick = e => { ed.notif = !ed.notif; e.currentTarget.classList.toggle("on", ed.notif); H.sel(); };
  el._ed = ed; el._edDraw = draw;
  el._save = async () => {
    if (ed.newImg !== null && ed.newImg !== ed.img) await post("profile/banner", { img: ed.newImg });
    if (ed.newAva !== null && ed.newAva !== ed.ava) await post("profile/avatar", { img: ed.newAva });
    await post("profile", { bio: ed.bio, banner: ed.banner, pinned: ed.pinned, nick: ed.nick.trim() });
    if (ed.notif !== (ME.notif !== false)) { await post("settings", { notif: ed.notif }); ME.notif = ed.notif; }
    try { Object.assign(ME, await api("me")); } catch {}   // обновим имя/аватар в шапке сразу
    H.ok(); toast("Профиль сохранён", "ok"); closeSheet(); refreshProfileSheets();
  };
  draw();
}

// ============================================================ ПОДАРОК
const GH_EV = { mint: "Создан", move: "Новый владелец", burn: "Ушёл в банк" };
async function giftHistory(el, id) {
  if (!id || !el) return;
  el.insertAdjacentHTML("beforeend", `<details class="ghist" open><summary>${ic("receipt")}История владельцев</summary><div class="ghist-b">Загружаем…</div></details>`);
  const box = el.querySelector(".ghist"), body = box.querySelector(".ghist-b");
  const load = async () => {
    if (!box.open || box.dataset.ok) return; box.dataset.ok = 1;
    try {
      const r = await api("gift/" + id + "/history");
      body.innerHTML = r.items.length ? r.items.map(x => `<div class="ghist-r"><span>${x.user ? esc(x.user.name) : x.event === "burn" ? "Банк" : "По ссылке"}<small>${GH_EV[x.event] || ""}</small></span><em>${new Date(x.ts * 1000).toLocaleDateString()}</em></div>`).join("") : `<p class="hint">Записей пока нет: история ведётся с этого обновления.</p>`;
    } catch (e) { body.textContent = ""; }
  };
  box.addEventListener("toggle", load); load();
}
function openGift(o) {
  const { g } = o, mine = o.mine || g.owner === ME.id;
  H.imp("light");
  const el = openSheet(giftSheetHTML(o, mine), "gsheet");
  el._o = o;
  giftHistory(el, g.id);
}
function giftSheetHTML(o, mine) {
  const g = o.g, sell = Math.floor(g.value * (1 - FEE("sell", .15)));
  const pinned = MYP && MYP.pinned.some(x => x.id === g.id);
  const seller = o.seller || (o.owner && !mine ? o.owner : null);
  let acts = "";
  if (mine) {
    acts = g.price != null
      ? `<div class="btns"><button class="btn ghost" data-act="unlist" data-id="${g.id}">Снять с продажи</button></div>`
      : `<div class="btns"><button class="btn ghost" data-act="pin" data-id="${g.id}">${ic("pin")}${pinned ? "Открепить" : "Закрепить"}</button><button class="btn ghost" data-act="list" data-id="${g.id}">${ic("tag")}На маркет</button></div>
         <div class="btns"><button class="btn red" data-act="sell" data-id="${g.id}">${ic("coins")}Продать банку за ⭐ ${fmt(sell)}</button></div>
         <p class="hint gsell-rate">Курс банка сейчас ${Math.round((1 - FEE("sell", .15)) * 100)}% от ценности. Банк больше — курс выше.</p>
         <div class="btns"><button class="btn gold" data-act="present" data-id="${g.id}">${ic("gift")}Подарить другу</button></div>
         ${g.value >= 100 ? `<div class="btns"><button class="btn ghost" data-act="loan" data-id="${g.id}">${ic("wallet")}Кредит под залог: ⭐ ${fmt(Math.floor(g.value * .5))}</button></div>` : ""}`;
  } else if (g.price != null) {
    acts = `<div class="btns"><button class="btn gold" data-act="buy" data-id="${g.id}">Купить за ⭐ ${fmt(g.price)}</button></div>`;
  }
  return `${giftHTML(g, { big: true })}<h2>${esc(g.col)}</h2><div class="sub">Коллекционный подарок #${fmt(g.num)}</div>
    <div class="box">
      <div class="row kv"><span class="k">Модель</span><span class="v">${esc(g.model)}</span><span class="pill">${pct(g.mp)}</span></div>
      <div class="row kv"><span class="k">Фон</span><span class="v">${esc(g.backdrop)}</span><span class="pill">${pct(g.bp)}</span></div>
      <div class="row kv"><span class="k">Узор</span><span class="v">${esc(g.symbol)}</span><span class="pill">${pct(g.sp)}</span></div>
      <div class="row kv"><span class="k">Ценность</span><span class="v star">⭐ ${fmt(g.value)}</span></div>
      <div class="row kv${mine ? " tap" : ""}" ${mine ? 'data-act="inc"' : ""}><span class="k">Доход</span><span class="v" style="color:var(--green)">+⭐ ${perHourTxt(giftPerHour(g))} в час</span><span class="pill">${g.mp <= 5 ? "×2 легенда" : g.mp <= 10 ? "×1,5 эпик" : "⭐ " + short(Math.round(giftPerHour(g) * 24)) + "/день"}</span></div>
      ${g.price != null ? `<div class="row kv"><span class="k">На маркете</span><span class="v star">⭐ ${fmt(g.price)}</span></div>` : ""}
      ${seller ? `<div class="row kv tap" data-act="profile" data-id="${seller.id}"><span class="k">Владелец</span><span class="v" style="display:flex;align-items:center;gap:8px">${avaHTML(seller, 24)}${esc(seller.name)}</span><span class="hint">›</span></div>` : ""}
    </div>${acts}
    <div class="disc">Игровой предмет. Это не настоящий подарок Telegram.</div>`;
}
async function giftChanged() {
  closeSheet();
  await loadMe();
  await refreshProfileSheets();
  if (TAB === "market") loadMarket();
  if (TAB === "inv") renderInventory();
}

// ============================================================ ОБМЕН — конструктор
async function newTrade(uid) {
  const el = openSheet(emptyHTML("hourglass", "Загружаем…"));
  const [me, them] = await Promise.all([api("user/" + ME.id), api("user/" + uid)]);
  MYP = me;
  const pickG = new Set(), pickW = new Set();
  const grid = (gs, set, side) => gs.filter(g => g.price == null).length ? `<div class="ggrid">${gs.filter(g => g.price == null).map(g =>
    `<div class="gcell" data-pick="${side}" data-id="${g.id}">${giftHTML(g, { lite: true, plain: true })}<span class="sel">${ic("check")}</span><div class="cap"><small>⭐${short(g.value)}</small></div></div>`).join("")}</div>`
    : `<div class="hint" style="padding:4px">Нет свободных подарков</div>`;
  replaceSheet(el, `<div style="display:flex;align-items:center;gap:12px;margin:4px 0 6px">${avaHTML(them, 44, { lv: true })}<div><div class="hint" style="font-size:13px">Обмен с</div><b style="font-size:19px">${esc(them.name)}</b></div></div>
    <div class="sec-t">Ты отдаёшь</div>${grid(me.gifts, pickG, "g")}
    <div class="auto"><span style="flex:1">+ звёзды от тебя</span><input id="tgs" inputmode="numeric" value="0"></div>
    <div class="sec-t">Ты хочешь получить</div>${grid(them.gifts, pickW, "w")}
    <div class="auto"><span style="flex:1">+ звёзды от него</span><input id="tws" inputmode="numeric" value="0"></div>
    <div class="hint" style="font-size:12px;text-align:center;margin:6px 0 0">Со звёзд, которые переходят в обмене, комиссия ${feeP("trade", .05)} — она уходит в банк игры.</div>
    <div class="box" style="margin-top:14px"><div class="row kv"><span class="k">Баланс</span><span class="v" id="tsum">—</span></div></div>
    <div class="btns"><button class="btn" data-act="send-trade">Предложить обмен</button></div>`);
  const all = new Map([...me.gifts, ...them.gifts].map(g => [g.id, g]));
  const sum = () => {
    const gv = [...pickG].reduce((s, i) => s + all.get(i).value, 0) + (+el.querySelector("#tgs").value || 0);
    const wv = [...pickW].reduce((s, i) => s + all.get(i).value, 0) + (+el.querySelector("#tws").value || 0);
    const d = wv - gv;
    el.querySelector("#tsum").innerHTML = `отдаёшь ⭐${short(gv)} · получаешь ⭐${short(wv)} <span class="${d >= 0 ? "win" : "lose"}">(${d >= 0 ? "+" : "−"}${short(Math.abs(d))})</span>`;
  };
  el.addEventListener("click", e => {
    const c = e.target.closest("[data-pick]"); if (!c) return;
    const set = c.dataset.pick === "g" ? pickG : pickW, id = +c.dataset.id;
    set.has(id) ? set.delete(id) : set.add(id); c.classList.toggle("picked", set.has(id)); H.sel(); sum();
  });
  el.querySelectorAll("input").forEach(i => i.oninput = sum); sum();
  el._send = async () => {
    await post("trades", { to: uid, give: [...pickG], want: [...pickW], giveStars: +el.querySelector("#tgs").value || 0, wantStars: +el.querySelector("#tws").value || 0 });
    H.ok(); toast("Предложение отправлено", "ok"); closeSheet(); refreshFriends();
  };
}

// ============================================================ ивенты раз в ~2 часа (flash.py)
const flashLeft = s => { s = Math.max(0, s); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
function flashBar() {
  const f = ME.flash; if (!f) return "";
  const t = Math.floor(Date.now() / 1000);
  if (!f.kind) {   // между ивентами — подсказка, когда следующий
    const m = Math.ceil((f.next - t) / 60);
    return m > 0 && m <= 180 ? `<div class="flash-next">⚡ Следующий ивент примерно через ${m} мин</div>` : "";
  }
  if (f.end <= t) return "";
  const drop = f.kind === "drop";
  const act = drop ? (f.claimed ? `<span class="flash-ok">${ic("check")}Забрал</span>` : f.left ? `<span class="btn sm gold flash-btn">Забрать +${fmt(f.amount)} ⭐</span>` : `<span class="flash-ok">Разобрали</span>`) : "";
  return `<button class="invbar flash ${drop ? "drop" : "luck"}" data-act="${drop && !f.claimed && f.left ? "flash-claim" : "flash-info"}">
    <span><b>${esc(f.title)} <i class="flash-t" data-end="${f.end}">${flashLeft(f.end - t)}</i></b>${esc(f.desc)}${drop && f.left && !f.claimed ? ` · осталось ${f.left}` : ""}</span>${act}</button>`;
}
setInterval(() => {   // обратный отсчёт; ивент закончился — перерисовываем главную
  const els = document.querySelectorAll(".flash-t"); if (!els.length) return;
  const t = Math.floor(Date.now() / 1000);
  els.forEach(e => { const s = +e.dataset.end - t; e.textContent = flashLeft(s); if (s <= 0 && ME.flash) { ME.flash = null; loadMe().then(() => $("#v-cases") && renderCases()); } });
}, 1000);

// ============================================================ франшиза: свой бот с этой игрой (franchise.py)
const FR_HIDE = "frHide";   // крестик на баннере — прячем на 14 дней (только у этого игрока)
function frBanner() {
  const f = ME.franchise;
  if (!f || !f.banner || f.mine.length) return "";
  try { if (Date.now() - (+localStorage.getItem(FR_HIDE) || 0) < 14 * 864e5) return ""; } catch (e) { }
  return `<button class="invbar" data-act="franchise-info">${ic("rocket")}<span><b>Свой бот с этой игрой</b>${f.create || f.reward ? `до +${fmt((f.create || 0) + (f.reward || 0))} ⭐ · создай за 1 тап` : "создай за 1 тап — без @BotFather"}</span><span data-act="franchise-hide" aria-label="Скрыть" style="flex:none;align-self:flex-start;margin:-6px -8px 0 0;padding:6px 8px;font-size:15px;line-height:1;opacity:.6">✕</span></button>`;
}
function franchiseInfo() {
  const f = ME.franchise; if (!f) return;
  const st = { on: "работает", off: "отключён", limit: "не подключён (лимит)" };
  openSheet(`<div style="text-align:center;padding-top:10px"><div style="font-size:64px">🤖</div><h2 style="margin:4px 0">Свой бот с этой игрой</h2>
    <p class="hint" style="margin:0 0 14px">Одна кнопка — Telegram создаст бота за пару секунд. Без @BotFather и без кода.</p></div>
    <div class="box">
      <div class="row"><span class="pic b">${ic("rocket")}</span><div class="grow"><div class="t">Та же игра</div><div class="s">Кейсы, игры, маркет и турниры — всё как здесь</div></div></div>
      <div class="row"><span class="pic g">${ic("userPlus")}</span><div class="grow"><div class="t">Общие аккаунты</div><div class="s">У игроков тот же баланс и подарки в любом боте</div></div></div>
      ${f.create ? `<div class="row"><span class="pic y">${ic("gift")}</span><div class="grow"><div class="t">+${fmt(f.create)} ⭐ сразу</div><div class="s">За создание бота${ME.lv.level < f.createLevel ? ` — придут, когда дойдёшь до ${f.createLevel} уровня` : ""} (один раз)</div></div></div>` : ""}
      ${f.cut ? `<div class="row"><span class="pic g">${ic("trophy")}</span><div class="grow"><div class="t">${String(f.cut).replace(".", ",")}% каждую минуту</div><div class="s">От всего дохода игры (игры + налоги и комиссии) — пассивно, пока у тебя есть бот${ME.lv.level < f.createLevel ? ` (с ${f.createLevel} уровня)` : ""}${f.cutTotal ? ` · уже получено ${fmt(f.cutTotal)} ⭐` : ""}</div></div></div>` : ""}
      ${f.reward ? `<div class="row"><span class="pic y">${ic("crown")}</span><div class="grow"><div class="t">Ещё +${fmt(f.reward)} ⭐</div><div class="s">Когда через твоего бота придут ${f.need} новых игроков и дорастут до ${f.level} уровня (один раз)</div></div></div>` : ""}
    </div>
    ${f.mine.length ? `<div class="sec-t">Мои боты</div><div class="box">${f.mine.map(b => `<div class="row kv"><div class="grow"><div class="t">@${esc(b.username || "?")}</div><div class="s">${st[b.status] || b.status}${f.reward && b.status === "on" ? ` · игроков ${b.progress}/${f.need}` : ""}</div></div></div>`).join("")}</div>` : ""}
    <div class="btns"><button class="btn gold" data-act="franchise">${ic("rocket")}${f.mine.length ? "Создать ещё бота" : "Создать бота"}</button></div>`);
}

// ============================================================ приглашение
function invite() {
  const text = ME.refBonus ? `Залетай в кейс-симулятор подарков 🎁 По моей ссылке получишь +${ME.refBonus} ⭐ на старт (игровых)` : "Залетай в кейс-симулятор подарков 🎁";
  const url = `https://t.me/share/url?url=${enc(ME.refLink)}&text=${enc(text)}`;
  if (inTg) tg.openTelegramLink(url); else { navigator.clipboard?.writeText(ME.refLink); toast("Ссылка скопирована"); }
}

// ============================================================ клики
const topSheet = () => SHEETS[SHEETS.length - 1];
const ACT = {
  close: () => closeSheet(),
  me: () => openProfile(ME.id),
  profile: el => openProfile(+el.dataset.id),
  daily: (el, e) => openDaily(e && e.target && e.target.closest && e.target.closest(".plus") ? "shop" : undefined),   // «+» на балансе — сразу пополнение
  "st-tab": el => { H.sel(); stTab(el.closest(".sheet"), el.dataset.v); },
  "claim-daily": async () => {
    const r = await post("daily"); H.ok();
    if (r.milestone) { toast(`🏆 Веха ${r.milestone.day} дней подряд! +⭐ ${fmt(r.milestone.stars)} + ключ «${r.milestone.key}»`, "ok"); burst(innerWidth / 2, innerHeight / 3, ["#ffd76a", "#ff6fb5", "#7cc2ff", "#fff"], 160); }
    else { toast(`+⭐ ${r.bonus}${r.key ? ` + ключ «${r.key}»` : ""} · серия ${r.streak} дн.`, "ok"); burst(innerWidth / 2, innerHeight / 3, ["#ffd76a", "#fff"]); }
    if (r.key || r.milestone) CASES = [];
    closeSheet(); await loadMe(); if (TAB === "cases") renderCases();
  },
  case: el => openCase(el.dataset.id),
  "open-case": el => doOpen(topSheet(), el.dataset.id),
  "sell-won": async el => {
    const ids = el.dataset.ids.split(",").map(Number);
    const r = await post("gifts/sell", { ids }); setStars(r.stars); H.ok(); toast(`Продано за ⭐ ${fmt(r.paid)}`);
    el.disabled = true; el.textContent = "Продано";
  },
  "open-n": el => { OPEN.n = +el.dataset.v; H.sel(); const s = topSheet(); s.querySelectorAll(".ocount [data-act=open-n]").forEach(b => b.classList.toggle("on", b === el)); s.querySelector("#obtns").lastElementChild.outerHTML = openBtn(s._case, s.querySelector("#obtns").children.length > 1); },
  "open-fast": el => { OPEN.fast = !OPEN.fast; el.classList.toggle("on", OPEN.fast); H.sel(); },
  gift: el => openGift(REG.get(el.dataset.k)),
  sell: async el => {
    const g = topSheet()._o.g;
    if (!await confirmM("Продать подарок?", `${esc(g.col)} #${fmt(g.num)} уйдёт за ⭐ ${fmt(Math.floor(g.value * (1 - FEE("sell", .15))))} (${sellP()} ценности). Хочешь дороже — выстави на маркет.`, "Продать")) return;
    const r = await post(`gift/${el.dataset.id}/sell`); setStars(r.stars); H.ok(); toast(`+⭐ ${fmt(r.paid)}`, "ok"); giftChanged();
  },
  list: async el => {
    const g = topSheet()._o.g;
    const v = await promptM("Цена на маркете", `Ценность ⭐ ${fmt(g.value)}. Комиссия маркета ${feeP("market", .05)}.`, Math.round(g.value * 1.1), "Выставить");
    if (v == null) return;
    await post(`gift/${el.dataset.id}/list`, { price: Math.floor(+v) }); H.ok(); toast("Выставлено на маркет", "ok"); giftChanged();
  },
  unlist: async el => { await post(`gift/${el.dataset.id}/unlist`); toast("Снято с продажи"); giftChanged(); },
  buy: async el => {
    const g = topSheet()._o.g;
    if (!await confirmM("Купить подарок?", `${esc(g.col)} #${fmt(g.num)} за ⭐ ${fmt(g.price)}`, "Купить")) return;
    const r = await post(`market/${el.dataset.id}/buy`); setStars(r.stars); H.ok(); toast("Подарок твой!", "ok"); burst(innerWidth / 2, innerHeight / 3, [g.c[0], g.c[3], "#fff"]); giftChanged();
  },
  pin: async el => {
    if (!MYP) MYP = await api("user/" + ME.id);
    const id = +el.dataset.id; let ids = MYP.pinned.map(g => g.id);
    if (ids.includes(id)) ids = ids.filter(x => x !== id); else { if (ids.length >= 6) return toast("Можно закрепить до 6 подарков"); ids.push(id); }
    await post("profile", { bio: MYP.bio, banner: MYP.banner, pinned: ids }); H.ok(); toast(ids.includes(id) ? "Закреплено" : "Откреплено", "ok");
    giftChanged();
  },
  "edit-profile": () => editProfile(),
  "save-profile": () => topSheet()._save(),
  invite: () => invite(),
  "franchise-info": () => franchiseInfo(),
  "flash-info": () => { const f = ME.flash; if (f && f.kind) toast(f.desc); },
  "flash-claim": async el => {
    el.disabled = true;
    try { const r = await post("flash/claim"); H.ok(); toast(`+${fmt(r.amount)} ⭐ — забрал!`, "ok"); setStars(r.stars); coinShower(el, 30); ME.flash.claimed = true; renderCases(); }
    catch (e) { await loadMe(); renderCases(); }
    finally { el.disabled = false; }
  },
  "franchise-hide": () => { try { localStorage.setItem(FR_HIDE, Date.now()); } catch (e) { } H.sel(); renderCases(); },
  franchise: () => inTg ? tg.openTelegramLink(ME.franchise.link) : window.open(ME.franchise.link),   // t.me/newbot/<главный бот> — окно создания бота
  fr: async el => { const r = await post(`friends/${el.dataset.id}/${el.dataset.v}`); H.sel(); toast({ friend: "Теперь вы друзья", outgoing: "Заявка отправлена", none: "Готово" }[r.rel] || "Готово"); await loadMe(); refreshProfileSheets(); refreshFriends(); },
  "trade-new": el => newTrade(+el.dataset.id),
  "send-trade": () => topSheet()._send(),
  trade: async el => {
    const v = el.dataset.v;
    if (v === "accept" && !await confirmM("Принять обмен?", "Подарки и звёзды сразу перейдут между вами.", "Принять")) return;
    try { await post(`trades/${el.dataset.id}/${v}`); }
    catch (e) { if (e.status !== "dup") refreshFriends(); return; }   // обмен уже закрыт / не хватает звёзд — убираем устаревшую карточку
    H.ok(); toast({ accept: "Обмен совершён", decline: "Отклонено", cancel: "Отменено" }[v]);
    await loadMe(); refreshFriends();
  },
  topk: el => { topKind = el.dataset.v; H.sel(); renderTop(); },
  "rich-info": () => modal(`<h3>${ic("crown")} Привилегии богачей</h3><p class="hint" style="margin:0 0 12px">Рейтинг — звёзды плюс ценность подарков. Каждый день в полночь топ-10 получает ключ от кейса, а пока ты в топе — корона на аватарке и сниженная комиссия маркета.</p>
    <div class="box" style="margin-bottom:14px">${(RICH_PERKS || []).map(p => `<div class="row kv"><span class="pill">${p.place}</span><div class="grow">ключ «${esc(p.key)}» каждый день</div><span class="hint">маркет ${p.fee}%</span></div>`).join("")}</div>
    <button class="btn gold" data-m="ok">Понятно</button>`),
  idea: () => {
    const el = openSheet(`<h2 class="gtitle">Идеи</h2><p class="hint" style="margin:0 0 12px">Что добавить, что поменять, где баг? Сообщение прочитает создатель игры.</p>
      <textarea id="idea-t" rows="6" maxlength="1000" placeholder="Например: добавьте покупку бонуса в Пёсиках…"></textarea>
      <button class="btn gold" data-act="idea-send" style="margin-top:10px">${ic("send")}Отправить</button>`);
    setTimeout(() => el.querySelector("#idea-t").focus(), 400);
  },
  "idea-send": async () => {
    const t = topSheet().querySelector("#idea-t").value.trim();
    if (t.length < 5) return toast("Напиши хотя бы пару слов");
    await post("feedback", { text: t }); H.ok(); toast("Спасибо! Сообщение отправлено", "ok"); closeSheet();
  },
  "crash-btn": () => crashBtn(),
  "crash-allin": () => crashAllin(),
  "auto-tog": el => { autoOn = !autoOn; el.classList.toggle("on", autoOn); H.sel(); },
  amt: el => {
    const i = $("#camt"), v = el.dataset.v, cur = +i.value || 0;
    i.value = v === "half" ? Math.max(10, Math.floor(cur / 2)) : v === "dbl" ? Math.min(ME.stars, cur * 2) : v === "max" ? ME.stars : v;
    H.sel();
  },
};
document.addEventListener("click", e => {
  const t = e.target.closest("[data-tab]");
  if (t) { H.sel(); if (!ME) return; return setTab(t.dataset.tab); }
  const el = e.target.closest("[data-act]");
  if (!el || el.disabled) return;
  const f = ACT[el.dataset.act]; if (!f) return;
  if (!ME) return toast("Подожди секунду, игра загружается");   // данные игрока ещё не пришли (например, сервер перезапускается)
  try { Promise.resolve(f(el, e)).catch(() => {}); }
  catch (err) { console.error(err); }   // синхронная ошибка в действии не должна ронять страницу
});

// ============================================================ старт
(async function boot() {
  paintIcons();
  let bootErr = null;
  for (let i = 0; i < 6; i++) {   // сервер мог перезапускаться (выкладка обновления) — пробуем ещё, прежде чем показать ошибку
    try { await loadMe(); bootErr = null; break; }
    catch (e) { bootErr = e; if (i < 5) await new Promise(r => setTimeout(r, 1000 * (i + 1))); }
  }
  if (bootErr) {
    $("#boot") && $("#boot").remove();
    document.querySelector("main").innerHTML = `<div class="empty" style="padding-top:80px"><span class="eic">${ic("lock")}</span>${inTg ? "Не удалось войти. Перезапусти приложение." : "Открой игру через бота в Telegram."}</div>`;
    return;
  }
  setTab("cases");
  const rq = new URLSearchParams(location.search).get("room");
  if (rq && window.openRoom) setTimeout(() => openRoom(+rq), 400);
  const gq = new URLSearchParams(location.search).get("gift");   // подарок по ссылке
  if (gq && typeof openPresentClaim === "function") setTimeout(() => openPresentClaim(gq), 500);
  const cq = new URLSearchParams(location.search).get("clan");   // приглашение в клан из бота
  if (cq && typeof openClan === "function") setTimeout(() => openClan(+cq), 500);
  const tq = new URLSearchParams(location.search).get("ticket");   // ответ поддержки из бота
  if (tq && typeof tkOpen === "function") setTimeout(() => tkOpen(+tq), 500);
  const aq = new URLSearchParams(location.search).get("aticket");  // админу: новый тикет из бота
  if (aq && typeof tkAdmOpen === "function") setTimeout(() => tkAdmOpen(+aq), 500);
  setTimeout(() => { const b = $("#boot"); if (b) { b.classList.add("out"); setTimeout(() => b.remove(), 400); } }, 250);
  setInterval(() => { if (TAB === "cases" && !bgOff()) loadFeed(); }, 12000);
  setInterval(() => { if (!bgOff()) loadMe().catch(() => {}); }, 20000);
  const back = () => { if (!bgOff() && ME) loadMe().catch(() => {}); };
  document.addEventListener("visibilitychange", back);
  if (tg && tg.onEvent) tg.onEvent("activated", back);
  setInterval(() => {   // тикающие таймеры
    if (ME.freeIn > 0) ME.freeIn--; if (ME.dailyIn > 0) ME.dailyIn--;
    const f = $("#free-t"); if (f) f.textContent = ME.freeIn ? "через " + clock(ME.freeIn) : "можно открыть!";
  }, 1000);
  try {
    if (!localStorage.getItem("disc1")) {
      await modal(`<h3>Добро пожаловать!</h3><p style="margin:0 0 10px">Открывай кейсы, лови редкие подарки, крути краш, торгуй и меняйся с друзьями.</p>
        <p class="hint" style="margin:0 0 16px;font-size:13.5px">${esc(ME.disclaimer)}</p><button class="btn" data-m="ok">Понятно, погнали</button>`);
      localStorage.setItem("disc1", "1");
    }
  } catch (e) {}
  if (typeof growthStart === "function") growthStart();   // розыгрыш из ссылки или подарок от друга (growth.js)
  if (typeof awayStart === "function") setTimeout(awayStart, 2500);   // «С возвращением» после перерыва (care.js), когда других окон нет
})();

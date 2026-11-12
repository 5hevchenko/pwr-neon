"use strict";
// ============================================================
//  Ещё игры: плинко, башня, кубик, лимбо, слоты
// ============================================================
GAMES.splice(2, 0,
  { id: "tower", t: "Башня", s: "Лезь вверх и не наступи на бомбу", img: "Artisan Brick", k: ["#ff9a3d", "#4a1d02"], chips: ["8 этажей"] });
GAMES.splice(6, 0,
  { id: "slots", t: "Слоты", s: "Три барабана с подарками — джекпот на трёх Plush Pepe", img: "Money Pot", k: ["#ffcf3d", "#4a2c00"], chips: ["джекпот x505"] });
GAMES.push(
  { id: "dice", t: "Кубик", s: "Больше или меньше — сам выбираешь шанс", img: "Evil Eye", k: ["#8a5cff", "#1f0b4a"], chips: ["x1.01–x48"] },
  { id: "limbo", t: "Лимбо", s: "Загадай икс — выпадет больше, и ты в плюсе", img: "Astral Shard", k: ["#4ad0ff", "#0b2550"], chips: ["до x1000"] });
const WIDE_GAMES = new Set(["crash", "duels", "slots"]);
const GAME_OPEN = { tower: () => openTower(), slots: () => openSlots(), dice: () => openDice(), limbo: () => openLimbo() };

// ============================================================ БАШНЯ
let TW = { active: false }, twMode = "mid", twBusy = false, TWM = null;
const TW_N = { easy: 4, mid: 3, hard: 2 };
async function openTower() {
  twBusy = false;
  openSheet(`${gameHead("Artisan Brick", "Башня", "Лезь вверх и не наступи на бомбу", "tower")}
    <div class="tower" id="tw"></div>
    <div class="mstat"><div><span>Выигрыш</span><b id="tw-win">—</b></div><div><span>Следующий</span><b id="tw-next">—</b></div></div>
    <div class="betp" id="tw-ctl">
      <div class="seg" id="tw-mode">${[["easy", "Лёгкая"], ["mid", "Средняя"], ["hard", "Сложная"]].map(([k, t]) => `<button data-act="tw-mode" data-v="${k}" class="${twMode === k ? "on" : ""}">${t}</button>`).join("")}</div>
      ${betHTML("tw-amt")}
      <button class="btn cta gold" id="tw-btn" data-act="tw-btn">Играть</button>
    </div>`, "tower-s");
  const d = await api("tower"); TWM = d.modes; TW = d; if (TW.active) twMode = TW.mode;
  twDraw();
}
function twDraw(boom) {
  const box = $("#tw"); if (!box || !TWM) return;
  const mode = TW.active ? TW.mode : twMode, n = TW_N[mode], picks = TW.picks || [], bombs = TW.bombs, floor = picks.length;
  let h = "";
  for (let f = 7; f >= 0; f--) {
    const cur = TW.active && f === floor, passed = f < floor;
    h += `<div class="tfl${cur ? " cur" : ""}${passed ? " done" : ""}"><span class="tm">x${TWM[mode][f]}</span><div class="tts" style="grid-template-columns:repeat(${n},1fr)">`;
    for (let t = 0; t < n; t++) {
      let cls = "tt", inner = "";
      if (passed && picks[f] === t) { cls += " gem"; inner = `<img src="${A.orig("Hanging Star", 64)}" alt="">`; }
      else if (bombs && bombs[f] === t) { cls += boom && boom[0] === f && boom[1] === t ? " boom" : " bomb"; inner = ic("bomb", "bombic"); }
      h += `<button class="${cls}" data-act="tw-step" data-f="${f}" data-t="${t}" ${cur ? "" : "disabled"}>${inner}</button>`;
    }
    h += `</div></div>`;
  }
  box.innerHTML = h;
  $("#tw-next").textContent = TW.active && floor < 8 ? "x" + TW.next.toFixed(2) : "—";
  $("#tw-win").textContent = TW.active && floor ? "⭐ " + fmt(TW.bet * TW.mult) : TW.pay ? "⭐ " + fmt(TW.pay) : "—";
  const btn = $("#tw-btn");
  if (TW.active) setBtn(btn, floor ? "green cta" : "ghost", floor ? `Забрать ⭐ ${fmt(TW.bet * TW.mult)}` : "Выбери плитку на 1 этаже", !floor);
  else setBtn(btn, "cta gold", "Играть", false);
  document.querySelectorAll("#tw-ctl .amt button, #tw-ctl .quick button, #tw-amt, #tw-mode button").forEach(x => x.disabled = !!TW.active);
}
async function twBtn() {
  if (TW.active) {
    const r = await post("tower/cashout"); TW = { ...TW, ...r }; H.ok(); toast(`+⭐ ${fmt(r.pay)}`, "ok"); burstAt($("#tw")); setStars(r.stars); twDraw(); winFx(null, r.pay, r.bet);
  } else {
    const bet = betVal("tw-amt");
    if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
    const r = await post("tower/start", { bet, mode: twMode }); TW = r; setStars(r.stars); H.imp("medium"); twDraw(); afterLevelUp(r.levelup);
  }
}
async function twStep(t) {
  if (!TW.active || twBusy) return;
  twBusy = true;
  try {
    const r = await post("tower/step", { tile: t }); TW = r;
    if (r.boom) { H.err(); const b = $("#tw"); b.classList.remove("shake"); void b.offsetWidth; b.classList.add("shake"); toast("Бомба!"); twDraw(r.boom); loadMe(); }
    else { H.imp("light"); if (r.pay) { H.ok(); toast(`Башня пройдена! +⭐ ${fmt(r.pay)}`, "ok"); setStars(r.stars); burstAt($("#tw")); winFx(null, r.pay, r.bet); } twDraw(); }
  } finally { twBusy = false; }
}

// ============================================================ КУБИК
const DC = { target: 50, over: true, busy: false };
function openDice() {
  DC.busy = false;
  openSheet(`${gameHead("Evil Eye", "Кубик", "Больше или меньше — сам выбираешь шанс", "dice")}
    <div class="dicebig"><b id="dc-roll">50.00</b><span id="dc-res">Выбери порог и бросай</span></div>
    <div class="dbar"><div class="dzone" id="dc-zone"></div><div class="dmark" id="dc-mark" style="left:50%"></div></div>
    <input type="range" class="drange" id="dc-t" min="2" max="98" step="1" value="${DC.target}">
    <div class="seg" style="margin-top:12px">${[[true, "Больше"], [false, "Меньше"]].map(([k, t]) => `<button data-act="dc-dir" data-v="${k ? 1 : 0}" class="${DC.over === k ? "on" : ""}">${t} <span id="dc-tl${k ? 1 : 0}"></span></button>`).join("")}</div>
    <div class="dstats"><div><span>Шанс</span><b id="dc-ch"></b></div><div><span>Множитель</span><b id="dc-mu"></b></div><div><span>Выигрыш</span><b id="dc-pw"></b></div></div>
    <div class="betp">${betHTML("dc-amt")}<button class="btn cta gold" data-act="dc-roll">Бросить кубик</button></div>`, "dice-s");
  const r = $("#dc-t");
  r.oninput = () => { DC.target = +r.value; H.sel(); dcDraw(); };
  $("#dc-amt").addEventListener("input", dcDraw);
  dcDraw();
}
// шанс не больше 95% (и не выше, чем даёт множитель от x1,01 при текущем возврате) — иначе «выигрыш» меньше ставки; ползунок подтягиваем
function dcClamp() {
  const m = Math.min(95, Math.floor(gEdge("x") * 100 / 1.01)), lim = DC.over ? [100 - m, 98] : [2, m], r = $("#dc-t");
  DC.target = Math.min(lim[1], Math.max(lim[0], DC.target));
  if (r && +r.value !== DC.target) r.value = DC.target;
}
function dcDraw() {
  if (!$("#dc-zone")) return;
  dcClamp();
  const t = DC.target, ch = DC.over ? 100 - t : t, mu = gEdge("x") * 100 / ch;
  $("#dc-zone").style.cssText = DC.over ? `left:${t}%;right:0` : `left:0;right:${100 - t}%`;
  $("#dc-tl1").textContent = t; $("#dc-tl0").textContent = t;
  $("#dc-ch").textContent = ch.toFixed(0) + "%";
  $("#dc-mu").textContent = "x" + mu.toFixed(2);
  $("#dc-pw").textContent = "⭐ " + fmt(betVal("dc-amt") * mu);
}
async function dcRoll() {
  if (DC.busy) return;
  const bet = betVal("dc-amt");
  if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
  DC.busy = true;
  try {
    const r = await post("dice", { bet, target: DC.target, over: DC.over });
    const el = $("#dc-roll"), mark = $("#dc-mark"), t0 = performance.now();
    el.className = "";
    await new Promise(done => (function f(now) {
      const k = Math.min(1, (now - t0) / 650), v = k < 1 ? Math.random() * 100 : r.roll;
      el.textContent = v.toFixed(2); mark.style.left = v + "%";
      k < 1 && el.isConnected ? requestAnimationFrame(f) : done();
    })(t0));
    if (!el.isConnected) return;
    el.className = r.win ? "win" : "lose";
    $("#dc-res").textContent = r.win ? `Победа x${r.mult} · +⭐ ${fmt(r.pay)}` : "Мимо";
    r.win ? H.ok() : H.err();
    setStars(r.stars); afterLevelUp(r.levelup);
  } finally { DC.busy = false; }
}

// ============================================================ ЛИМБО
const LB = { busy: false };
function openLimbo() {
  LB.busy = false;
  openSheet(`${gameHead("Astral Shard", "Лимбо", "Загадай икс — выпадет больше, и ты в плюсе", "limbo")}
    <div class="limbo" id="lb-box"><b id="lb-v">1.00x</b><span id="lb-s">Цель x2.00</span></div>
    <div class="betp">
      <div class="lbt"><span>Цель</span><label class="autof"><input id="lb-t" inputmode="decimal" value="2.00"><span>x</span></label>
        <div class="lbc"><span>Шанс</span><b id="lb-ch">48.50%</b></div></div>
      <div class="quick">${[1.5, 2, 5, 10, 100].map(x => `<button data-act="lb-q" data-v="${x}">x${x}</button>`).join("")}</div>
      <div style="height:8px"></div>${betHTML("lb-amt")}
      <button class="btn cta gold" data-act="lb-go">Играть</button>
    </div>`, "limbo-s");
  $("#lb-t").oninput = lbDraw; lbDraw();
}
const lbTarget = () => Math.max(1.01, Math.min(1000, parseFloat(($("#lb-t").value || "2").replace(",", ".")) || 2));
function lbDraw() { if (!$("#lb-ch")) return; const t = lbTarget(); $("#lb-ch").textContent = (gEdge("x") * 100 / t).toFixed(2) + "%"; $("#lb-s").textContent = "Цель x" + t.toFixed(2); }
async function lbGo() {
  if (LB.busy) return;
  const bet = betVal("lb-amt"), target = lbTarget();
  if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
  LB.busy = true;
  try {
    const r = await post("limbo", { bet, target });
    const v = $("#lb-v"), box = $("#lb-box"), t0 = performance.now(), dur = Math.min(1100, 350 + Math.log(r.result) * 260);
    box.className = "limbo";
    await new Promise(done => (function f(now) {
      const k = Math.min(1, (now - t0) / dur), cur = Math.exp(Math.log(r.result) * (1 - Math.pow(1 - k, 3)));
      v.textContent = cur.toFixed(2) + "x";
      k < 1 && v.isConnected ? requestAnimationFrame(f) : done();
    })(t0));
    if (!v.isConnected) return;
    box.className = "limbo " + (r.win ? "win" : "lose");
    $("#lb-s").textContent = r.win ? `Победа · +⭐ ${fmt(r.pay)}` : `Цель x${target.toFixed(2)} — мимо`;
    r.win ? (H.ok(), burstAt(box), winFx(null, r.pay, r.pay / target)) : H.err();
    setStars(r.stars); afterLevelUp(r.levelup);
  } finally { LB.busy = false; }
}

// ============================================================ СЛОТЫ
let SL = null, slBusy = false, slN = 1, slFast = false;
const slMachine = (m, small) => `<div class="slot${small ? " sm" : ""}" id="sl-m${m}"><div class="sreels">${[0, 1, 2].map(i =>
  `<div class="sreel"><div class="sstrip" id="sl-s${m}-${i}"></div></div>`).join("")}</div><div class="sline"></div><div class="swin" id="sl-w${m}"></div></div>`;
async function openSlots() {
  slBusy = false;
  openSheet(`${gameHead("Money Pot", "Слоты", "Три барабана с подарками", "slots")}
    <div class="slots" id="sl-box"></div>
    <div class="wres" id="sl-res">Крути барабаны</div>
    <div class="betp">
      <div class="mn" style="margin:0 0 10px"><span>Автоматы</span><div class="quick" id="sl-n">${[1, 2, 3, 5].map(n => `<button data-act="sl-n" data-v="${n}" class="${slN === n ? "on" : ""}">x${n}</button>`).join("")}</div></div>
      ${betHTML("sl-amt")}<div class="dgbtns"><button class="btn cta gold" id="sl-btn" data-act="sl-spin">Крутить</button><button class="ufast${slFast ? " on" : ""}" data-act="sl-fast">${ic("trend")}Быстро</button></div></div>
    <div class="sec-t">Выплаты на один автомат</div><div class="box" id="sl-pay"></div>`, "slots-s");
  SL = await api("slots");   // таблица выплат зависит от возврата в админке — не кэшируем
  slBuild();
  $("#sl-amt").addEventListener("input", slBtnText);
  $("#sl-pay").innerHTML = SL.syms.map((s, i) => `<div class="row kv"><img class="spi" src="${A.orig(s, 64)}" alt=""><img class="spi" src="${A.orig(s, 64)}" alt=""><img class="spi" src="${A.orig(s, 64)}" alt="">
    <span class="v" style="text-align:right">x${SL.three[i]}</span><span class="hint" style="font-size:12px;width:62px;text-align:right">два: x${SL.two[i]}</span></div>`).reverse().join("");
}
function slBuild() {
  const box = $("#sl-box"); if (!box || !SL) return;
  box.className = "slots n" + slN;
  box.innerHTML = Array.from({ length: slN }, (_, m) => slMachine(m, slN > 1)).join("");
  for (let m = 0; m < slN; m++) for (let i = 0; i < 3; i++) $(`#sl-s${m}-${i}`).innerHTML = slSym((SL.syms.length - 1 - i - m) % SL.syms.length);
  slBtnText();
}
function slBtnText() { const b = $("#sl-btn"); if (b && !slBusy) b.textContent = slN > 1 ? `Крутить x${slN} · ⭐ ${short(betVal("sl-amt") * slN)}` : "Крутить"; }
const slSym = i => `<div class="ssym"><img src="${A.orig(SL.syms[i], 128)}" alt=""></div>`;
async function slSpin() {
  if (slBusy || !SL) return;
  const bet = betVal("sl-amt"), n = slN;
  if (bet * n > ME.stars) return toast("Не хватает звёзд ⭐");
  slBusy = true; $("#sl-btn").disabled = true;
  document.querySelectorAll("#sl-n button").forEach(b => b.disabled = true);
  setStars(ME.stars - bet * n);
  let r;
  try { r = await post("slots", { bet, n }); } catch (e) { slBusy = false; $("#sl-btn").disabled = false; document.querySelectorAll("#sl-n button").forEach(b => b.disabled = false); loadMe(); return; }
  const res = $("#sl-res"); res.className = "wres"; res.textContent = "…";
  const H0 = $("#sl-box .sreel").clientHeight;
  document.querySelectorAll("#sl-box .swin").forEach(w => { w.className = "swin"; w.textContent = ""; });
  document.querySelectorAll("#sl-box .slot").forEach(m => { m.classList.remove("hit", "jp"); m.classList.add("spin"); });
  await Promise.all(r.spins.map((sp, m) => Promise.all(sp.reels.map((sym, i) => new Promise(done => {
    const strip = $(`#sl-s${m}-${i}`), cnt = slFast ? 7 + i * 2 : 16 + i * 6 + m * 2, d = slFast ? .4 + i * .1 + m * .04 : 1.3 + i * .4 + m * .12;
    let html = ""; for (let k = 0; k < cnt; k++) html += slSym(Math.random() * SL.syms.length | 0);
    strip.innerHTML = slSym(sym) + html;
    strip.style.transition = "none"; strip.style.transform = `translateY(${-cnt * H0}px)`;
    void strip.offsetWidth;
    strip.style.transition = `transform ${d}s cubic-bezier(.2,.8,.25,1.02)`;
    strip.style.transform = "translateY(0)";
    setTimeout(() => { if (m === 0) H.imp("medium"); done(); }, d * 1000);
  }))).then(() => {
    const box = $("#sl-m" + m); if (box) box.classList.remove("spin");
    // «почти!»: два дорогих символа из трёх — подсвечиваем пару, третий барабан вздрагивает
    const cnt = {}; sp.reels.forEach(x => cnt[x] = (cnt[x] || 0) + 1);
    const pair = Object.keys(cnt).find(x => cnt[x] === 2 && +x >= 3);
    if (box && pair != null) {
      const odd = sp.reels.findIndex(x => x !== +pair);
      box.querySelectorAll(".sreel").forEach((r, i) => r.classList.toggle(i === odd ? "near-odd" : "near-pair", true));
      box.insertAdjacentHTML("beforeend", `<span class="snear">${+pair === SL.syms.length - 1 ? "Почти джекпот!" : "Почти!"}</span>`);
      if (typeof SND !== "undefined") SND.near();
      setTimeout(() => { box.querySelectorAll(".sreel").forEach(r => r.classList.remove("near-odd", "near-pair")); const n = box.querySelector(".snear"); if (n) n.remove(); }, 1800);
    }
    const w = $("#sl-w" + m); if (!w || !sp.mult) return;
    w.className = "swin on" + (sp.mult >= 10 ? " jp" : sp.mult < 1 ? " meh" : "");
    w.textContent = "x" + sp.mult;
    if (sp.mult > 1) { box.classList.add("hit"); coinShower(box, Math.min(70, 10 + sp.mult * 3)); }
    if (sp.mult >= 10) box.classList.add("jp");
  })));
  slBusy = false;
  if ($("#sl-btn")) { $("#sl-btn").disabled = false; document.querySelectorAll("#sl-n button").forEach(b => b.disabled = false); slBtnText(); }
  setStars(r.stars);
  const total = r.pay, spent = bet * n, best = Math.max(...r.spins.map(x => x.mult));
  if (best >= 10) { H.ok(); res.className = "wres win"; res.textContent = `ДЖЕКПОТ x${best}! Итого +⭐ ${fmt(total)}`; }
  else if (total > spent) { H.ok(); res.className = "wres win"; res.textContent = n > 1 ? `Итого ⭐ ${fmt(total)} (+${fmt(total - spent)})` : `x${best} · +⭐ ${fmt(total)}`; }
  else if (total > 0) { H.imp("medium"); res.className = "wres meh"; res.textContent = n > 1 ? `Итого ⭐ ${fmt(total)} (−${fmt(spent - total)})` : `x${best} · ⭐ ${fmt(total)}`; }
  else { H.err(); res.className = "wres lose"; res.textContent = "Пусто — ещё разок?"; }
  if (total / spent >= 5) await bigWin(total, total / spent);
  afterLevelUp(r.levelup);
}

// ============================================================ действия
const _gameAct = ACT.game;
Object.assign(ACT, {
  game: el => {
    const id = el.dataset.id;
    GREC = [id, ...GREC.filter(x => x !== id)].slice(0, 8); gSave("grecent", GREC);   // недавние — для хаба
    return GAME_OPEN[id] ? (H.imp("light"), GAME_OPEN[id]()) : _gameAct(el);
  },
  "tw-mode": el => { if (TW.active) return; twMode = el.dataset.v; H.sel(); document.querySelectorAll("#tw-mode button").forEach(b => b.classList.toggle("on", b === el)); twDraw(); },
  "tw-btn": () => twBtn(),
  "tw-step": el => twStep(+el.dataset.t),
  "dc-dir": el => { DC.over = el.dataset.v === "1"; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); dcDraw(); },
  "dc-roll": () => dcRoll(),
  "lb-q": el => { $("#lb-t").value = (+el.dataset.v).toFixed(2); H.sel(); lbDraw(); },
  "lb-go": () => lbGo(),
  "sl-spin": () => slSpin(),
  "sl-fast": el => { slFast = !slFast; el.classList.toggle("on", slFast); H.sel(); },
  "sl-n": el => { if (slBusy) return; slN = +el.dataset.v; H.sel(); document.querySelectorAll("#sl-n button").forEach(b => b.classList.toggle("on", b === el)); slBuild(); },
});

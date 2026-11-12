"use strict";
// ============================================================
//  «Бур» — гонка трёх буров вглубь: ставь на один, кто пробурит глубже всех — забирает множитель пласта.
// ============================================================
const DR_C = [["#2fd4ff", "Синий"], ["#ffc53d", "Золотой"], ["#ff4fd8", "Розовый"]];
const DR_X = [43, 64, 85];          // колонки буров, % ширины
const DR_TOP = 118, DR_LH = 62;     // высота поверхности и пласта, px
// бур: цанга цвета команды, вал и шнек
const drBit = c => `<svg viewBox="0 0 40 74" class="dr-bsvg"><defs>
  <linearGradient id="drs${c.slice(1)}" x1="0" x2="1"><stop offset="0" stop-color="#474c5c"/><stop offset=".4" stop-color="#eef1f8"/><stop offset=".65" stop-color="#9aa0b2"/><stop offset="1" stop-color="#3a3e4c"/></linearGradient></defs>
  <rect x="15" y="0" width="10" height="18" fill="url(#drs${c.slice(1)})"/>
  <rect x="8" y="14" width="24" height="12" rx="3" fill="${c}"/><rect x="8" y="14" width="24" height="4" rx="2" fill="rgba(255,255,255,.45)"/>
  <path d="M9 26h22L20 72Z" fill="url(#drs${c.slice(1)})"/>
  <g class="dr-flute" stroke="rgba(20,22,30,.55)" stroke-width="2.4" fill="none" stroke-linecap="round"><path d="M10 30 30 36M11 38 29 44M13 46 27 52M15 54 25 60M17 62 23 66"/></g></svg>`;
// вышка на поверхности
const drRig = c => `<svg viewBox="0 0 60 84" class="dr-rsvg"><g stroke="#cfd4e2" stroke-width="2.2" fill="none" stroke-linejoin="round">
  <path d="M14 82 28 6h4l14 76M18 62h24M21 44h18M24 26h12M18 62 39 44M21 44 37 26M42 62 21 44"/></g>
  <rect x="24" y="0" width="12" height="8" rx="2" fill="${c}"/><path d="M36 2h14l-4 5 4 5H36Z" fill="${c}"/>
  <rect x="8" y="76" width="44" height="8" rx="2" fill="#2a2d38"/><rect x="8" y="76" width="44" height="2.5" rx="1" fill="rgba(255,255,255,.2)"/></svg>`;
GAMES.push({ id: "drill", t: "Бур", s: "Гонка трёх буров: чей пробурит глубже — тот и забирает", imgUrl: "", k: ["#ffb03d", "#2a1405"], chips: ["новинка", "3 бура"] });
GAMES[GAMES.length - 1].imgUrl = "data:image/svg+xml," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
  <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7a4a26"/><stop offset=".35" stop-color="#b0743f"/><stop offset=".6" stop-color="#5d5d68"/><stop offset=".85" stop-color="#7a1e08"/><stop offset="1" stop-color="#ffb03d"/></linearGradient></defs>
  <rect x="10" y="20" width="100" height="96" rx="20" fill="url(#g)"/><circle cx="60" cy="104" r="22" fill="#ffd76a" opacity=".55"/>
  <g transform="translate(40 2) scale(1)">${drBit("#ffc53d").replace(/<svg[^>]*>|<\/svg>/g, "").replace(/id="drs/g, 'id="drsC').replace(/url\(#drs/g, "url(#drsC")}</g></svg>`);
WIDE_GAMES.add("drill");
GAME_OPEN.drill = () => openDrill();
AR_NEW.push("drill");
GAME_NAMES.drill = ["drill", "Бур"];

let DRL = null, drPick = 1, drBusy = false, drRaf = 0, drMode = "race", drTarget = 6;
const drMs = () => drMode === "depth" ? DRL.depthMults : DRL.mults;
async function openDrill() {
  drBusy = false; cancelAnimationFrame(drRaf);
  const el = openSheet(`<div class="ghead">${gpfBtn("drill")}<img src="${GAMES.find(g => g.id === "drill").imgUrl}" alt=""><div><h2>Бур</h2><span>Выбери бур — и пусть победит глубочайший</span></div></div>
    <div class="ar-stage dr-stage" id="dr-stage"><div class="dr-world" id="dr-w">${emptyHTML("hourglass", "Ставим вышки…")}</div>
      <div class="dr-race" id="dr-race"></div></div>
    <div class="ar-ladder dr-tl" id="dr-tl"></div>
    <div class="dr-tinfo" id="dr-tinfo"></div>
    <div class="betp">
      <div class="seg ar-seg dr-modes" id="dr-modes">${[["race", "Гонка", "#2fd4ff"], ["depth", "Глубина", "#ffc53d"]].map(([k, t, c]) => `<button data-act="dr-mode" data-v="${k}" style="--c:${c}" class="${drMode === k ? "on" : ""}"><i></i>${t}<small id="dr-mx-${k}"></small></button>`).join("")}</div>
      <div class="dr-picks" id="dr-picks">${DR_C.map(([c, t], i) => `<button data-act="dr-pick" data-i="${i}" style="--c:${c}" class="${i === drPick ? "on" : ""}"><span class="dr-pb">${drBit(c)}</span><b>${t}</b></button>`).join("")}</div>
      ${betHTML("dr-amt")}
      <button class="btn cta gold" id="dr-btn" data-act="dr-go">Бурить</button>
    </div>
    <details class="rules" style="margin-top:12px"><summary>${ic("award")}Как играть</summary><div id="dr-rules"></div></details>`, "dr-s");
  el._onClose = () => { cancelAnimationFrame(drRaf); drBusy = false; };
  DRL = await api("drill").catch(() => null);
  if (!DRL || !$("#dr-stage")) return;
  $("#dr-mx-race").textContent = "до " + arX(Math.max(...DRL.mults));
  $("#dr-mx-depth").textContent = "до " + arX(Math.max(...DRL.depthMults));
  $("#dr-rules").innerHTML = `<b>Гонка.</b> Три бура одновременно идут вглубь и ломаются на случайной глубине. Ставишь на один — если он пробурил глубже обоих соперников, получаешь множитель пласта, где он остановился (на ничью множитель делится между лидерами).
    Шансы буров одинаковые — выбирай любимый цвет. До каждого пласта доходит: ${DRL.names.slice(1).map((n, i) => `${n.toLowerCase()} — ${String(DRL.reach[i + 1]).replace(".", ",")}%`).join(", ")}. Возврат игроку — ${String(DRL.rtp).replace(".", ",")}%.<br><br>
    <b>Глубина.</b> Тапни пласт на разрезе — это цель. Твой бур дошёл до цели или глубже — получаешь её множитель: чем глубже цель, тем реже доходит и тем больше икс (ядро — ${arX(DRL.depthMults[DRL.layers])}). Соперников нет — только ты и земля.`;
  drBuild();
}
function drBuild() {
  const w = $("#dr-w"); if (!w) return;
  const ms = drMs(), dep = drMode === "depth";
  $("#dr-stage").classList.toggle("depth", dep);
  w.style.height = DR_TOP + DRL.layers * DR_LH + "px";
  w.innerHTML = `<div class="dr-sky"><i class="dr-moon"></i><i class="dr-hills"></i></div>` +
    DRL.names.slice(1).map((n, i) => `<div class="dr-layer L${i + 1}${dep && drTarget === i + 1 ? " tgt" : ""}${dep && i + 1 > drTarget ? " deep" : ""}" style="top:${DR_TOP + i * DR_LH}px;height:${DR_LH}px"${dep ? ` data-act="dr-target" data-k="${i + 1}"` : ""}><span class="dr-ln"><b>${n}</b><em>${arX(ms[i + 1])}</em></span>${dep && drTarget === i + 1 ? `<span class="dr-tgt">${ic("target")}ЦЕЛЬ</span>` : ""}</div>`).join("") +
    DR_X.map((x, i) => `<div class="dr-col${i === drPick ? " mine" : ""}${dep && i !== drPick ? " idle" : ""}" id="dr-c${i}" style="left:${x}%;--c:${DR_C[i][0]}">
      <div class="dr-rig">${drRig(DR_C[i][0])}<span class="dr-you">ТВОЙ</span></div>
      <div class="dr-bore" id="dr-bo${i}"></div><div class="dr-bit" id="dr-b${i}">${drBit(DR_C[i][0])}</div></div>`).join("");
  drPlace([0, 0, 0]);
  drRace([0, 0, 0]);
  // в «Глубине» камера подъезжает к пласту-цели — глубокие цели тоже видно
  const H0 = $("#dr-stage").clientHeight, worldH = DR_TOP + DRL.layers * DR_LH;
  $("#dr-w").style.transform = `translateY(${dep ? -Math.max(0, Math.min(worldH - H0, DR_TOP + (drTarget - .5) * DR_LH - H0 * .55)) : 0}px)`;
  const tl = $("#dr-tl");
  if (tl) {
    tl.style.display = dep ? "" : "none";
    tl.innerHTML = dep ? DRL.names.slice(1).map((n, i) => `<button class="ar-step${drTarget === i + 1 ? " cur" : ""}" data-act="dr-target" data-k="${i + 1}"><b>${arX(DRL.depthMults[i + 1])}</b><span>${n}</span></button>`).join("") : "";
    const c = tl.querySelector(".cur"); if (c) tl.scrollLeft = c.offsetLeft - tl.clientWidth / 2 + c.offsetWidth / 2;
  }
  drInfo();
}
// подсказка над ставкой: в «Глубине» — выбранная цель, её икс и шанс
function drInfo() {
  const el = $("#dr-tinfo"); if (!el || !DRL) return;
  el.innerHTML = drMode === "depth"
    ? `${ic("target")}<span>Цель: <b>${DRL.names[drTarget]}</b> · ${arX(DRL.depthMults[drTarget])} · шанс ${String(DRL.depthReach[drTarget]).replace(".", ",")}%</span><small>выбери цель в ленте выше или тапни пласт</small>`
    : `${ic("trophy")}<span>Побеждает бур, который пройдёт <b>глубже всех</b></span>`;
  starify(el);
}
const drY = d => d <= 0 ? DR_TOP - 6 : DR_TOP + (d - .5) * DR_LH;   // где кончик бура на глубине d (в пластах, дробно)
function drPlace(ds) {
  ds.forEach((d, i) => {
    const y = drY(d), b = $("#dr-b" + i), bo = $("#dr-bo" + i); if (!b) return;
    b.style.transform = `translateY(${y - 70}px)`; bo.style.height = Math.max(0, y - DR_TOP + 8) + "px";
  });
}
function drRace(ds, done = []) {
  const r = $("#dr-race"); if (!r || !DRL) return;
  r.innerHTML = ds.map((d, i) => `<div class="dr-rr${i === drPick ? " mine" : ""}${done[i] ? " dead" : ""}" style="--c:${DR_C[i][0]}"><i style="--w:${Math.min(100, d / DRL.layers * 100)}%"></i><b>${Math.floor(d)}</b></div>`).join("");
}
async function drGo() {
  if (drBusy || !DRL) return;
  const bet = betVal("dr-amt");
  if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
  drBusy = true; $("#dr-btn").disabled = true;
  let r;
  try { r = await post("drill/play", { bet, pick: drPick, mode: drMode, target: drTarget }); } catch (e) { drBusy = false; $("#dr-btn").disabled = false; return; }
  setStars(r.stars - r.pay); H.imp("heavy"); afterLevelUp(r.levelup);
  if (!$("#dr-stage")) { drBusy = false; setStars(r.stars); return; }
  DRL.mults = r.mults; if (r.depthMults) DRL.depthMults = r.depthMults;
  drBuild();
  $("#dr-stage").querySelectorAll(".ar-banner").forEach(b => b.remove());
  await drAnimate(r.depths);
  if (!$("#dr-stage")) { drBusy = false; setStars(r.stars); return; }
  setStars(r.stars);
  const st = $("#dr-stage"), top = Math.max(...r.depths);
  if (r.mode === "depth") {
    const d = r.depths[r.pick];
    if (r.won) {
      $("#dr-c" + r.pick).classList.add("lead"); H.ok();
      arBanner(st, "win", `Дошёл до «${DRL.names[d]}» · цель «${DRL.names[r.target]}»`, `+⭐ ${fmt(r.pay)}`, arX(r.mult));
      coinShower(st, Math.min(70, 12 + r.mult * 3));
      if (r.mult >= 5) await bigWin(r.pay, r.mult);
    } else {
      H.err();
      arBanner(st, "lose", d ? `Сломался: «${DRL.names[d]}»` : "Сломался на старте", `−⭐ ${fmt(r.bet)}`, `цель — «${DRL.names[r.target]}»`);
    }
    drBusy = false; if ($("#dr-btn")) $("#dr-btn").disabled = false;
    return;
  }
  r.depths.forEach((d, i) => { if (d === top && d > 0) $("#dr-c" + i).classList.add("lead"); });
  if (r.won) {
    H.ok();
    arBanner(st, "win", r.tie ? `Ничья · ${DRL.names[r.depths[r.pick]]}` : `Победа · ${DRL.names[r.depths[r.pick]]}`, `+⭐ ${fmt(r.pay)}`, arX(r.mult));
    coinShower(st, Math.min(70, 12 + r.mult * 5));
    if (r.mult >= 5) await bigWin(r.pay, r.mult);
  } else {
    H.err();
    const w = r.depths.indexOf(top);
    arBanner(st, "lose", top ? `Глубже всех — ${DR_C[w][1].toLowerCase()}` : "Все сломались на старте", `−⭐ ${fmt(r.bet)}`, top ? `${DRL.names[top]} · ${top} пл.` : "");
  }
  drBusy = false; if ($("#dr-btn")) $("#dr-btn").disabled = false;
}
// гонка: все буры идут вниз с одной скоростью; каждый ломается на своей глубине, камера следит за лидером
function drAnimate(depths) {
  return new Promise(res => {
    const SPEED = 2.35, t0 = performance.now(), stopped = [false, false, false];
    const st = $("#dr-stage"), w = $("#dr-w"), H0 = st.clientHeight, worldH = DR_TOP + DRL.layers * DR_LH;
    let lastLayer = 0;
    st.classList.add("drilling");
    [0, 1, 2].forEach(i => $("#dr-c" + i).classList.add("run"));
    SND.drill(Math.max(...depths) / SPEED + .3);
    const frame = now => {
      if (!$("#dr-w")) return res();
      const t = (now - t0) / 1000, front = Math.max(0, t * SPEED - .25);   // короткий разгон
      const ds = depths.map((d, i) => {
        const v = Math.min(d, front);
        if (!stopped[i] && front >= d) {   // сломался: искры, трещина, бур кренится
          stopped[i] = true;
          const c = $("#dr-c" + i); c.classList.remove("run");
          if (c.classList.contains("idle")) return v;
          c.classList.add("broke");
          const sr = st.getBoundingClientRect(), br = $("#dr-b" + i).getBoundingClientRect();
          arSparks(st, br.left - sr.left + br.width / 2, br.bottom - sr.top - 6, 16, [DR_C[i][0], "#fff3c4", "#ff9a3d"], 70);
          SND.crack(); if (i === drPick) H.imp("rigid");
        }
        return v;
      });
      const layer = Math.floor(Math.max(...ds));
      if (layer > lastLayer) { lastLayer = layer; H.sel(); }
      drPlace(ds);
      drRace(ds, stopped);
      const lead = drY(Math.max(...ds));
      w.style.transform = `translateY(${-Math.max(0, Math.min(worldH - H0, lead - H0 * .58))}px)`;
      if (stopped.every(Boolean)) { st.classList.remove("drilling"); setTimeout(res, 380); return; }
      drRaf = requestAnimationFrame(frame);
    };
    drRaf = requestAnimationFrame(frame);
  });
}
Object.assign(ACT, {
  "dr-pick": el => {
    if (drBusy) return;
    drPick = +el.dataset.i; H.sel();
    el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el));
    [0, 1, 2].forEach(i => { const c = $("#dr-c" + i); if (c) c.classList.toggle("mine", i === drPick); });
    if (DRL) { drRace([0, 0, 0]); if (drMode === "depth") drBuild(); }
  },
  "dr-go": () => drGo(),
  "dr-mode": el => {
    if (drBusy || !DRL) return;
    drMode = el.dataset.v; H.sel();
    el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el));
    drBuild();
  },
  "dr-target": el => {
    if (drBusy || drMode !== "depth") return;
    drTarget = +el.dataset.k; H.sel(); drBuild();
  },
});

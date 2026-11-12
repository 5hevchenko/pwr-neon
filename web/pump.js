"use strict";
// ============================================================
//  «Насос» — надувай шар: каждый качок растит множитель, но шар может лопнуть. Забрать можно в любой момент.
// ============================================================
const PM_MODES = [["easy", "Лёгкий", "#3ee6a8"], ["mid", "Средний", "#ff5fa8"], ["hard", "Жёсткий", "#ff5a3d"]];
const PM_COL = { easy: ["#b9ffe4", "#3ee6a8", "#0b8a5e", "#04412c"], mid: ["#ffd6ea", "#ff5fa8", "#b0145e", "#4d0628"], hard: ["#ffd9c9", "#ff5a3d", "#a3170a", "#470803"] };
// глянцевый шар со звездой — один SVG и для сцены, и для карточки
const pmBall = (id, c) => `<svg viewBox="0 0 200 244" class="pm-svg"><defs>
  <radialGradient id="pmg${id}" cx=".36" cy=".3" r=".78"><stop offset="0" stop-color="${c[0]}"/><stop offset=".32" stop-color="${c[1]}"/><stop offset=".78" stop-color="${c[2]}"/><stop offset="1" stop-color="${c[3]}"/></radialGradient>
  <radialGradient id="pmh${id}" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#fff" stop-opacity=".95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
  <linearGradient id="pmr${id}" x1="0" y1="0" x2="1" y2="1"><stop offset=".55" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity=".35"/></linearGradient></defs>
  <path d="M100 6C162 6 194 58 194 112c0 62-52 104-90 112h-8C58 216 6 174 6 112 6 58 38 6 100 6Z" fill="url(#pmg${id})"/>
  <path d="M100 6C162 6 194 58 194 112c0 62-52 104-90 112h-8C58 216 6 174 6 112 6 58 38 6 100 6Z" fill="url(#pmr${id})"/>
  <path d="M100 62l13.5 27.4 30.2 4.4-21.9 21.3 5.2 30.1L100 131l-27 14.2 5.2-30.1-21.9-21.3 30.2-4.4Z" fill="rgba(255,255,255,.13)" stroke="rgba(255,255,255,.28)" stroke-width="2" stroke-linejoin="round"/>
  <ellipse cx="62" cy="62" rx="26" ry="38" transform="rotate(32 62 62)" fill="url(#pmh${id})"/>
  <ellipse cx="148" cy="170" rx="9" ry="20" transform="rotate(38 148 170)" fill="#fff" opacity=".18"/>
  <circle cx="44" cy="104" r="5" fill="#fff" opacity=".55"/>
  <path d="M90 236l10-14 10 14c-6 3-14 3-20 0Z" fill="${c[2]}"/><path d="M93 233l7-9" stroke="rgba(255,255,255,.35)" stroke-width="2" stroke-linecap="round"/></svg>`;
GAMES.push({ id: "pump", t: "Насос", s: "Надувай шар — чем больше, тем выше множитель. Лопнет — ставка сгорит", imgUrl: "", k: ["#ff5fa8", "#2b0a3d"], chips: ["новинка", "до x" + "1000"] });
GAMES[GAMES.length - 1].imgUrl = "data:image/svg+xml," + encodeURIComponent(pmBall("c", PM_COL.mid).replace('class="pm-svg"', 'xmlns="http://www.w3.org/2000/svg"'));
WIDE_GAMES.add("pump");
GAME_OPEN.pump = () => openPump();
AR_NEW.push("pump");
GAME_NAMES.pump = ["wind", "Насос"];

// ручной насос с манометром (стрелка — риск лопнуть на следующем качке)
const PM_PUMP = `<svg viewBox="0 0 120 190" class="pm-psvg"><defs>
  <linearGradient id="pmch" x1="0" x2="1"><stop offset="0" stop-color="#5d6275"/><stop offset=".35" stop-color="#f3f5fb"/><stop offset=".6" stop-color="#b3b8c8"/><stop offset="1" stop-color="#4a4f60"/></linearGradient>
  <linearGradient id="pmred" x1="0" x2="1"><stop offset="0" stop-color="#8f0f22"/><stop offset=".4" stop-color="#ff4b5f"/><stop offset="1" stop-color="#7a0b1c"/></linearGradient>
  <radialGradient id="pmdial" cx=".45" cy=".4" r=".65"><stop offset="0" stop-color="#fffdf5"/><stop offset="1" stop-color="#d9d4c4"/></radialGradient></defs>
  <g class="pm-rod"><rect x="56" y="14" width="8" height="70" rx="3" fill="url(#pmch)"/>
    <rect x="22" y="4" width="76" height="16" rx="8" fill="#20212b"/><rect x="24" y="5.5" width="72" height="5" rx="2.5" fill="rgba(255,255,255,.18)"/></g>
  <rect x="40" y="70" width="40" height="96" rx="9" fill="url(#pmred)"/>
  <rect x="40" y="70" width="40" height="12" rx="6" fill="url(#pmch)"/><rect x="40" y="150" width="40" height="14" rx="5" fill="url(#pmch)"/>
  <rect x="45" y="88" width="5" height="56" rx="2.5" fill="rgba(255,255,255,.35)"/>
  <path d="M14 168h92a6 6 0 0 1 6 6v6H8v-6a6 6 0 0 1 6-6Z" fill="#1d1e27"/><rect x="8" y="176" width="104" height="5" rx="2" fill="rgba(255,255,255,.1)"/>
  <circle cx="60" cy="118" r="17" fill="#22232d"/><circle cx="60" cy="118" r="14" fill="url(#pmdial)"/>
  <path d="M49 124a12 12 0 0 1 22 0" fill="none" stroke="#e33" stroke-width="2.5" stroke-dasharray="0 14 9 40" stroke-linecap="round"/>
  <g class="pm-needle" style="transform-origin:60px 118px"><path d="M59 118l1-11 1 11Z" fill="#111"/></g><circle cx="60" cy="118" r="2.2" fill="#111"/>
  <path d="M80 156h10q8 0 8 8" fill="none" stroke="#2a2b36" stroke-width="7" stroke-linecap="round"/></svg>`;

let PMP = null, pmMode = "mid", pmBusy = false;
async function openPump() {
  pmBusy = false;
  const el = openSheet(`<div class="ghead">${gpfBtn("pump")}<img src="${GAMES.find(g => g.id === "pump").imgUrl}" alt=""><div><h2>Насос</h2><span>Качай, пока не страшно — и забирай</span></div></div>
    <div class="ar-stage pm-stage" id="pm-stage">
      <div class="pm-sky"><i></i><i></i><i></i><i></i><i></i><i></i></div>
      <div class="pm-floor"></div>
      <svg class="pm-hose" id="pm-hose"><path class="pm-hb" id="pm-hb"/><path id="pm-hp"/></svg>
      <div class="pm-ball" id="pm-ball"></div>
      <div class="pm-pump" id="pm-pump">${PM_PUMP}</div>
      <div class="ar-hud"><div class="ar-x dim" id="pm-x">x1,00</div><div class="ar-sub" id="pm-sub"></div></div>
    </div>
    <div class="ar-ladder" id="pm-lad"></div>
    <div class="betp">
      <div class="seg ar-seg" id="pm-mode">${PM_MODES.map(([k, t, c]) => `<button data-act="pm-mode" data-v="${k}" style="--c:${c}" class="${pmMode === k ? "on" : ""}"><i></i>${t}</button>`).join("")}</div>
      <div id="pm-bet">${betHTML("pm-amt")}</div>
      <div class="ar-btns" id="pm-btns"></div>
    </div>
    <details class="rules" style="margin-top:12px"><summary>${ic("award")}Как играть</summary><div id="pm-rules"></div></details>`, "pm-s");
  el._onClose = () => { pmBusy = false; };
  PMP = await api("pump").catch(() => null);
  if (!PMP || !$("#pm-stage")) return;
  if (PMP.active) pmMode = PMP.mode;
  $("#pm-mode").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === pmMode));
  $("#pm-rules").innerHTML = `Ставишь и качаешь насос. Каждый качок увеличивает множитель, но шар может лопнуть — и чем он больше, тем легче (${PM_MODES.map(([k, t]) => `${t.toLowerCase()}: ${String(PMP.riskFrom[k]).replace(".", ",")}% → ${PMP.riskTo[k]}%`).join(", ")}).
    Забери выигрыш в любой момент — или рискни ещё. Надул до предела (${PMP.steps} качков) — выплата автоматически. Возврат игроку — ${String(PMP.rtp).replace(".", ",")}%.`;
  pmPaint(true);
}
const pmTable = () => PMP.active ? PMP.table : PMP.modes[pmMode];
const pmScale = k => .5 + .72 * Math.pow(k / PMP.steps, .75);
function pmPaint(first) {
  if (!PMP || !$("#pm-stage")) return;
  const st = $("#pm-stage"), ball = $("#pm-ball"), k = PMP.active ? PMP.step : 0, mode = PMP.active ? PMP.mode : pmMode;
  st.style.setProperty("--mc", PM_COL[mode][1]);
  if (first || ball.dataset.mode !== mode || !ball.firstChild) { ball.innerHTML = pmBall("s", PM_COL[mode]); ball.dataset.mode = mode; }
  ball.className = "pm-ball";
  ball.style.setProperty("--sc", pmScale(k));
  ball.style.setProperty("--t", (k / PMP.steps).toFixed(3));
  const t = pmTable(), risk = PMP.active ? PMP.risk : PMP.riskFrom[mode];
  $("#pm-pump").querySelector(".pm-needle").style.transform = `rotate(${-70 + Math.min(1, risk / 60) * 140}deg)`;
  const x = $("#pm-x");
  x.textContent = arX(PMP.active ? PMP.mult : 1); x.className = "ar-x" + (PMP.active && k ? "" : " dim");
  $("#pm-sub").innerHTML = PMP.active
    ? `<span class="ar-pill">${ic("trend")}Дальше <b>${PMP.next ? arX(PMP.next) : "—"}</b></span><span class="ar-pill${risk >= 20 ? " warn" : ""}">${ic("bomb")}Лопнет: <b>${String(risk).replace(".", ",")}%</b></span>`
    : `<span class="ar-pill">${ic("wind")}Качков до предела: <b>${PMP.steps}</b></span>`;
  $("#pm-lad").innerHTML = t.map((m, i) => `<div class="ar-step${i < k - 1 ? " done" : ""}${PMP.active && i === k - 1 ? " cur" : ""}${PMP.active && i === k ? " nx" : ""}"><b>${arX(m)}</b><span>${i + 1} качок</span></div>`).join("");
  const cur = $("#pm-lad").children[Math.max(0, k - 2)]; if (cur) $("#pm-lad").scrollLeft = cur.offsetLeft - 8;
  pmHose();
  pmUI();
}
// шланг от насоса к узелку шара — по реальным координатам (ширина сцены разная)
function pmHose() {
  const st = $("#pm-stage"), sv = $("#pm-hose"); if (!st || !sv) return;
  const W = st.clientWidth, Hh = st.clientHeight, p = $("#pm-pump").getBoundingClientRect(), s = st.getBoundingClientRect();
  const nx = p.left - s.left + p.width * .82, ny = p.top - s.top + p.height * .865, kx = W / 2, ky = Hh - 84;
  sv.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  const d = `M${nx} ${ny} C ${nx} ${Hh - 6}, ${kx} ${Hh - 4}, ${kx} ${ky}`;
  $("#pm-hp").setAttribute("d", d); $("#pm-hb").setAttribute("d", d);
}
function pmUI() {
  const b = $("#pm-btns"); if (!b || !PMP) return;
  const on = PMP.active;
  $("#pm-bet").style.display = on ? "none" : "";
  $("#pm-mode").querySelectorAll("button").forEach(x => x.disabled = on);
  b.innerHTML = on
    ? `<button class="btn cta gold ar-two" data-act="pm-step" ${pmBusy ? "disabled" : ""}><b>${ic("wind")}Качнуть</b><small>до ${PMP.next ? arX(PMP.next) : "—"}</small></button>
       <button class="btn cta green ar-two" data-act="pm-cash" ${!PMP.step || pmBusy ? "disabled" : ""}><b>Забрать</b><small>⭐ ${short(PMP.bet * PMP.mult)}</small></button>`
    : `<button class="btn cta gold" data-act="pm-start" ${pmBusy ? "disabled" : ""}>Начать</button>`;
  starify(b);
}
async function pmStart() {
  const bet = betVal("pm-amt");
  if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
  pmBusy = true; pmUI();
  try {
    const r = await post("pump/start", { bet, mode: pmMode });
    setStars(r.stars); H.imp("medium");
    PMP = { ...PMP, ...r }; pmBusy = false; pmPaint(); afterLevelUp(r.levelup);
  } catch (e) { pmBusy = false; pmUI(); }
}
async function pmStep() {
  if (pmBusy || !PMP.active) return;
  pmBusy = true; pmUI();
  const pump = $("#pm-pump"), ball = $("#pm-ball"), st = $("#pm-stage");
  pump.classList.remove("push"); void pump.offsetWidth; pump.classList.add("push");
  $("#pm-hp").classList.remove("flow"); void $("#pm-hp").offsetWidth; $("#pm-hp").classList.add("flow");
  SND.pump(PMP.step); H.imp("light");
  let r;
  try { [r] = await Promise.all([post("pump/step"), sleep(260)]); } catch (e) { pmBusy = false; pmUI(); return; }
  if (!$("#pm-stage")) { pmBusy = false; return; }
  if (r.popped) {   // шар лопнул: вспышка, ошмётки, тряска
    ball.style.setProperty("--sc", pmScale(r.popped) * 1.05);
    ball.classList.add("strain");
    await sleep(320);
    if (!$("#pm-stage")) { pmBusy = false; return; }
    pmPop(st, ball, PM_COL[r.mode]);
    H.err(); SND.pop(); arShake(st);
    PMP = { ...PMP, active: false };
    const x = $("#pm-x"); x.textContent = "БАХ!"; x.className = "ar-x bad"; arBump(x);
    setStars(r.stars);
    arBanner(st, "lose", `Лопнул на ${r.popped} качке`, `−⭐ ${fmt(r.bet)}`);
    await sleep(1700);
    pmBusy = false;
    if (!$("#pm-stage")) return;
    PMP = await api("pump"); pmPaint(true);
    return;
  }
  if (r.pay != null) return pmDone(r);
  PMP = { ...PMP, ...r };
  pmBusy = false; pmPaint(); arBump($("#pm-x"));
  ball.classList.add("puff"); setTimeout(() => ball.classList.remove("puff"), 380);
}
function pmPop(st, ball, c) {
  const r = ball.getBoundingClientRect(), s = st.getBoundingClientRect();
  const cx = r.left - s.left + r.width / 2, cy = r.top - s.top + r.height * .45;
  ball.classList.add("gone");
  const f = document.createElement("i"); f.className = "pm-flash"; f.style.cssText = `left:${cx}px;top:${cy}px`; st.appendChild(f); setTimeout(() => f.remove(), 700);
  const burst = document.createElement("div"); burst.className = "pm-burst"; burst.style.cssText = `left:${cx}px;top:${cy}px`;
  burst.innerHTML = Array.from({ length: 12 }, (_, i) => `<i style="--a:${i * 30 + Math.random() * 12}deg;--l:${50 + Math.random() * 40}px"></i>`).join(""); st.appendChild(burst); setTimeout(() => burst.remove(), 600);
  for (let i = 0; i < 16; i++) {   // ошмётки резины
    const p = document.createElement("i"), a = Math.random() * Math.PI * 2, d = 70 + Math.random() * 130;
    p.className = "pm-shard";
    p.style.cssText = `left:${cx}px;top:${cy}px;--c1:${c[1]};--c2:${c[2]};--dx:${Math.cos(a) * d}px;--dy:${Math.sin(a) * d * .8 + 60}px;--r:${(Math.random() - .5) * 900}deg;--w:${8 + Math.random() * 16}px`;
    st.appendChild(p); setTimeout(() => p.remove(), 1300);
  }
}
async function pmCash() {
  if (pmBusy || !PMP.active || !PMP.step) return;
  pmBusy = true; pmUI();
  try { pmDone(await post("pump/cashout")); } catch (e) { pmBusy = false; pmUI(); }
}
async function pmDone(r) {
  setStars(r.stars); H.ok();
  PMP = { ...PMP, ...r, active: false };
  const st = $("#pm-stage"); if (!st) { pmBusy = false; return; }
  const ball = $("#pm-ball"), x = $("#pm-x");
  x.textContent = arX(r.mult); x.className = "ar-x good"; arBump(x);
  ball.classList.add("fly"); SND.float();
  $("#pm-hp").classList.add("off");
  arBanner(st, "win", "Забрал", `+⭐ ${fmt(r.pay)}`, arX(r.mult));
  coinShower(st, Math.min(70, 12 + r.mult * 4));
  if (r.mult >= 5) await bigWin(r.pay, r.mult);
  await sleep(1600);
  pmBusy = false;
  if (!$("#pm-stage")) return;
  $("#pm-hp").classList.remove("off");
  PMP = await api("pump"); pmPaint(true);
}
Object.assign(ACT, {
  "pm-mode": el => { if (PMP && PMP.active) return; pmMode = el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); if (PMP) pmPaint(); },
  "pm-start": () => pmStart(),
  "pm-step": () => pmStep(),
  "pm-cash": () => pmCash(),
});

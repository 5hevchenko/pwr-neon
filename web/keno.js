"use strict";
// ============================================================
//  «Кено» — отметь до 10 чисел из 40, лототрон вытягивает 10 шаров: чем больше совпало, тем больше икс
// ============================================================
const KN_RISK = [["low", "Низкий", "#35d07f"], ["mid", "Средний", "#ffc53d"], ["high", "Высокий", "#ff4d5e"]];
// цвет шара по десятку — как в настоящей лотерее
const knCol = n => n <= 10 ? ["#ff6b6b", "#b3121f"] : n <= 20 ? ["#ffd056", "#c27a00"] : n <= 30 ? ["#4fe39a", "#0a8049"] : ["#6bb4ff", "#1745b8"];
const knBall = (n, cls = "") => { const [a, b] = knCol(n); return `<i class="kn-ball ${cls}" style="--a:${a};--b:${b}"><b>${n}</b></i>`; };
// карточка в «Играх»: три шара лототрона
function knCard() {
  const balls = [[34, 62, 26, 7], [86, 66, 26, 33], [60, 36, 30, 21]];
  const defs = balls.map(([, , , n]) => { const [a, b] = knCol(n); return `<radialGradient id="kc${n}" cx=".34" cy=".3" r=".8"><stop offset="0" stop-color="#fff"/><stop offset=".22" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></radialGradient>`; }).join("");
  const body = balls.map(([x, y, r, n]) => `<circle cx="${x}" cy="${y + 3}" r="${r}" fill="rgba(0,0,0,.35)"/><circle cx="${x}" cy="${y}" r="${r}" fill="url(#kc${n})"/>
    <circle cx="${x}" cy="${y}" r="${r * .5}" fill="#fff"/><text x="${x}" y="${y + r * .2}" font-size="${r * .58}" font-weight="900" text-anchor="middle" fill="#1b1d26" font-family="Arial,sans-serif">${n}</text>`).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 100"><defs>${defs}</defs>${body}</svg>`;
}
GAMES.push({ id: "keno", t: "Кено", s: "Отметь до 10 чисел — лототрон вытянет 10 шаров", imgUrl: "data:image/svg+xml," + encodeURIComponent(knCard()), k: ["#7c4dff", "#12062e"], chips: ["новинка", "до x970"] });
WIDE_GAMES.add("keno");
GAME_OPEN.keno = () => openKeno();
AR_NEW.push("keno");
GAME_NAMES.keno = ["grid", "Кено"];

let KNS = null, knRisk = "mid", knBusy = false;
const knPicks = new Set();
async function openKeno() {
  knBusy = false;
  const el = openSheet(`<div class="ghead">${gpfBtn("keno")}<img src="${GAMES.find(g => g.id === "keno").imgUrl}" alt=""><div><h2>Кено</h2><span>Отметь числа и жди тиража</span></div></div>
    <div class="ar-stage kn-stage" id="kn-stage">
      <div class="kn-top">
        <div class="kn-dome" id="kn-dome"><div class="kn-mix">${[3, 14, 27, 38, 9, 22, 31, 17, 5, 36, 12, 25].map((n, i) => knBall(n, "m m" + i)).join("")}</div>
          <div class="kn-glass"></div><div class="kn-base"></div></div>
        <div class="kn-tray"><div class="kn-tl"><span>Тираж</span><b id="kn-hits"></b></div><div class="kn-slots" id="kn-slots">${"<i></i>".repeat(10)}</div></div>
      </div>
      <div class="kn-grid" id="kn-grid">${Array.from({ length: 40 }, (_, i) => `<button class="kn-c" data-act="kn-pick" data-n="${i + 1}" style="--a:${knCol(i + 1)[0]}"><span>${i + 1}</span></button>`).join("")}</div>
    </div>
    <div class="kn-ph"><span id="kn-cnt"></span><button class="kn-tb" data-act="kn-auto">${ic("sparkles")}Случайно</button><button class="kn-tb" data-act="kn-clear">${ic("x")}Сброс</button></div>
    <div class="ar-ladder kn-pays" id="kn-pays"></div>
    <div class="betp">
      <div class="seg ar-seg" id="kn-risk">${KN_RISK.map(([k, t, c]) => `<button data-act="kn-risk" data-v="${k}" style="--c:${c}" class="${knRisk === k ? "on" : ""}"><i></i>${t}</button>`).join("")}</div>
      ${betHTML("kn-amt")}
      <button class="btn cta gold" id="kn-btn" data-act="kn-go">${ic("grid")} Играть</button>
    </div>
    <details class="rules" style="margin-top:12px"><summary>${ic("award")}Как играть</summary><div id="kn-rules"></div></details>`, "kn-s");
  el._onClose = () => { knBusy = false; };
  knPaint();
  KNS = await api("keno").catch(() => null);
  if (!KNS || !$("#kn-stage")) return;
  $("#kn-rules").innerHTML = `Отметь на поле от 1 до 10 чисел (или жми «Случайно») и сделай ставку. Лототрон вытянет 10 шаров из 40.
    Чем больше твоих чисел выпало, тем больше множитель — таблица выплат для твоего количества чисел видна над ставкой.
    Риск меняет таблицу: низкий платит чаще и понемногу, высокий — редко, но крупно. Шансы честные, возврат игроку — ${String(KNS.rtp).replace(".", ",")}%.`;
  knPaint();
}
function knPaint() {
  const g = $("#kn-grid"); if (!g) return;
  g.querySelectorAll(".kn-c").forEach(b => b.classList.toggle("on", knPicks.has(+b.dataset.n)));
  const k = knPicks.size;
  $("#kn-cnt").innerHTML = `Отмечено <b>${k}</b> из 10`;
  $("#kn-hits").textContent = k ? `0 из ${k}` : "—";
  const p = $("#kn-pays");
  if (!KNS || !k) { p.innerHTML = `<div class="kn-empty">${ic("grid")}Отметь числа — здесь появятся выплаты</div>`; return; }
  const t = KNS.tables[knRisk][k - 1], ch = KNS.chances[k - 1];
  p.innerHTML = t.map((m, h) => `<div class="ar-step${m ? "" : " zero"}" data-h="${h}" title="шанс ${String(ch[h]).replace(".", ",")}%"><b>${m ? arX(m) : "—"}</b><span>${h} из ${k}</span></div>`).join("");
}
// снять подсветку прошлого тиража (отметки остаются)
function knReset() {
  $("#kn-grid").querySelectorAll(".kn-c").forEach(b => b.classList.remove("hit", "drawn", "miss"));
  $("#kn-slots").innerHTML = "<i></i>".repeat(10);
  $("#kn-stage").classList.remove("done");
  $("#kn-pays").querySelectorAll(".ar-step").forEach(s => s.classList.remove("cur", "done"));
}
// шар вылетает из горлышка лототрона в свою лунку лотка
function knDrop(n, i, hit, h) {
  const st = $("#kn-stage"), slot = $("#kn-slots").children[i], dome = $("#kn-dome");
  const s = st.getBoundingClientRect(), d = dome.getBoundingClientRect(), t = slot.getBoundingClientRect();
  const x0 = d.left - s.left + d.width / 2, y0 = d.top - s.top + d.height * .9, x1 = t.left - s.left + t.width / 2, y1 = t.top - s.top + t.height / 2;
  const w = document.createElement("div"); w.className = "kn-fly"; w.innerHTML = knBall(n); w.style.cssText = `left:${x0}px;top:${y0}px`;
  st.appendChild(w);
  SND.ball(i);
  const a = w.animate([{ transform: "translate(-50%,-50%) scale(.4)", opacity: .2 },
    { transform: `translate(calc(-50% + ${(x1 - x0) * .45}px),calc(-50% + ${(y1 - y0) * .45 - 34}px)) scale(1.25)`, opacity: 1, offset: .5 },
    { transform: `translate(calc(-50% + ${x1 - x0}px),calc(-50% + ${y1 - y0}px)) scale(1)`, opacity: 1 }], { duration: 300, easing: "cubic-bezier(.3,.7,.4,1)", fill: "forwards" });
  return a.finished.then(() => {
    w.remove();
    if (!$("#kn-stage")) return;
    slot.innerHTML = knBall(n, hit ? "in hit" : "in");
    const c = $(`#kn-grid .kn-c[data-n="${n}"]`);
    c.classList.add(hit ? "hit" : "drawn");
    if (hit) {
      SND.gem(h); H.imp("light");
      const r = c.getBoundingClientRect();
      arSparks(st, r.left - s.left + r.width / 2, r.top - s.top + r.height / 2, 12, ["#ffd76a", "#fff3c4", knCol(n)[0]], 60);
      $("#kn-hits").textContent = `${h} из ${knPicks.size}`;
      const p = $("#kn-pays");
      p.querySelectorAll(".ar-step").forEach(e => { const k = +e.dataset.h; e.classList.toggle("cur", k === h); e.classList.toggle("done", k < h); });
      const cur = p.querySelector(".cur"); if (cur) p.scrollLeft = cur.offsetLeft - p.clientWidth / 2 + cur.clientWidth / 2;
    }
  });
}
async function knGo() {
  if (knBusy || !KNS) return;
  if (!knPicks.size) { H.err(); return toast("Отметь хотя бы одно число"); }
  const bet = betVal("kn-amt");
  if (bet > ME.stars) return toast("Не хватает звёзд ⭐");
  knBusy = true; $("#kn-btn").disabled = true; $("#kn-stage").classList.add("busy");
  const sr = $("#kn-stage").getBoundingClientRect(); if (sr.top < 0) $("#kn-stage").scrollIntoView({ behavior: "smooth", block: "start" });
  let r;
  try { r = await post("keno", { bet, risk: knRisk, picks: [...knPicks] }); } catch (e) { knBusy = false; $("#kn-btn").disabled = false; $("#kn-stage").classList.remove("busy"); return; }
  setStars(r.stars - r.pay); afterLevelUp(r.levelup);
  const st = $("#kn-stage"); if (!st) { knBusy = false; setStars(r.stars); return; }
  knReset();
  st.querySelectorAll(".ar-banner").forEach(b => b.remove());
  const k = knPicks.size, dome = $("#kn-dome");
  $("#kn-hits").textContent = `0 из ${k}`;
  dome.classList.add("spin"); SND.whoosh();
  $("#kn-pays").querySelectorAll(".ar-step").forEach(e => e.classList.toggle("cur", +e.dataset.h === 0));
  await sleep(380);
  let h = 0; const lands = [];
  for (let i = 0; i < r.draw.length; i++) {
    if (!$("#kn-stage")) break;
    const n = r.draw[i], hit = knPicks.has(n); if (hit) h++;
    lands.push(knDrop(n, i, hit, h));
    await sleep(165);
  }
  await Promise.all(lands);
  setStars(r.stars);
  if (!$("#kn-stage")) { knBusy = false; return; }
  dome.classList.remove("spin");
  st.classList.remove("busy"); st.classList.add("done");
  $("#kn-grid").querySelectorAll(".kn-c.on:not(.hit)").forEach(c => c.classList.add("miss"));
  const label = `${r.hits} из ${k} совпало`;
  if (r.pay > r.bet) { H.ok(); arBanner(st, "win", label, `+⭐ ${fmt(r.pay)}`, arX(r.mult)); coinShower(st, Math.min(70, 10 + r.mult * 4)); if (r.mult >= 10) await bigWin(r.pay, r.mult); }
  else if (r.pay > 0) { H.imp("light"); arBanner(st, "", label, `⭐ ${fmt(r.pay)}`, `${arX(r.mult)} — часть ставки вернулась`); }
  else { H.err(); arBanner(st, "lose", label, `−⭐ ${fmt(r.bet)}`); }
  knBusy = false; if ($("#kn-btn")) $("#kn-btn").disabled = false;
}
Object.assign(ACT, {
  "kn-pick": el => {
    if (knBusy) return;
    const n = +el.dataset.n;
    if ($("#kn-stage").classList.contains("done")) knReset();
    if (knPicks.has(n)) knPicks.delete(n);
    else if (knPicks.size >= 10) { H.err(); return toast("Не больше 10 чисел"); }
    else knPicks.add(n);
    H.sel(); knPaint();
  },
  "kn-auto": () => {
    if (knBusy) return;
    if ($("#kn-stage").classList.contains("done")) knReset();
    const k = knPicks.size || 5, all = Array.from({ length: 40 }, (_, i) => i + 1);
    knPicks.clear();
    for (let i = 0; i < k; i++) knPicks.add(all.splice(Math.floor(Math.random() * all.length), 1)[0]);
    H.imp("light"); knPaint();
  },
  "kn-clear": () => { if (knBusy) return; knPicks.clear(); knReset(); H.sel(); knPaint(); },
  "kn-risk": el => { if (knBusy) return; knRisk = el.dataset.v; H.sel(); el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el)); knPaint(); },
  "kn-go": () => knGo(),
});

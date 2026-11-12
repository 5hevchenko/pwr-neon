"use strict";
// ============================================================
//  Общие помощники новых игр (Насос, Бур, Дартс, Рыбалка): формат множителя, баннер итога, искры, раздел «Новинки»
// ============================================================
const arX = m => "x" + (m >= 1000 ? short(m) : (+m).toFixed(2).replace(".", ","));
GAME_SECTIONS.splice(1, 0, ["Новинки", "sparkles", []]);
const AR_NEW = GAME_SECTIONS[1][2];
function arBanner(stage, kind, small, big, sub = "") {
  if (!stage) return;
  let b = stage.querySelector(".ar-banner");
  if (!b) { b = document.createElement("div"); stage.appendChild(b); }
  b.className = "ar-banner " + kind;
  b.innerHTML = `<small>${small}</small><b>${big}</b>${sub ? `<em>${sub}</em>` : ""}`;
  void b.offsetWidth; b.classList.add("on");
  starify(b);
}
// искры из точки (x, y — в пикселях внутри сцены)
function arSparks(stage, x, y, n = 18, colors = ["#ffd76a", "#fff3c4", "#ff9a3d"], spread = 120) {
  if (!stage || window.LITE) return;
  for (let i = 0; i < n; i++) {
    const s = document.createElement("i"), a = Math.random() * Math.PI * 2, d = spread * (.35 + Math.random() * .65);
    s.className = "ar-spark";
    s.style.cssText = `left:${x}px;top:${y}px;--c:${colors[i % colors.length]};--s:${3 + Math.random() * 5}px;--dx:${Math.cos(a) * d}px;--dy:${Math.sin(a) * d}px;--d:${.5 + Math.random() * .6}s`;
    stage.appendChild(s); setTimeout(() => s.remove(), 1200);
  }
}
function arShake(stage) { if (!stage) return; stage.classList.remove("shake"); void stage.offsetWidth; stage.classList.add("shake"); }
function arBump(el) { if (!el) return; el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); }

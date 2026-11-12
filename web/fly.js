"use strict";
// ============================================================
//  Полёт подарка в сумку: копия картинки летит по дуге к вкладке «Сумка», вкладка подпрыгивает и показывает «+N»
// ============================================================
function flyToBag(img, n = 1) {
  const tab = document.querySelector('nav.tabs button[data-tab="inv"]');
  if (!img || !tab || window.LITE || !img.getBoundingClientRect) return;
  const a = img.getBoundingClientRect(), b = tab.getBoundingClientRect();
  if (!a.width) return;
  const f = img.cloneNode(); f.className = "fly-gift";
  Object.assign(f.style, { left: a.left + "px", top: a.top + "px", width: a.width + "px", height: a.height + "px" });
  document.body.appendChild(f);
  const dx = b.left + b.width / 2 - (a.left + a.width / 2), dy = b.top + b.height / 2 - (a.top + a.height / 2);
  const anim = f.animate([
    { transform: "translate(0,0) scale(1) rotate(0)", opacity: 1 },
    { transform: `translate(${dx * .45}px,${dy * .3 - 90}px) scale(.7) rotate(-12deg)`, opacity: 1, offset: .45 },
    { transform: `translate(${dx}px,${dy}px) scale(.12) rotate(8deg)`, opacity: .6 },
  ], { duration: 850, easing: "cubic-bezier(.45,.05,.4,1)" });
  anim.onfinish = () => {
    f.remove();
    tab.classList.remove("bag-pop"); void tab.offsetWidth; tab.classList.add("bag-pop");
    const p = document.createElement("b"); p.className = "bag-plus"; p.textContent = "+" + n; tab.appendChild(p); setTimeout(() => p.remove(), 1200);
    H.imp("light");
  };
}
// кейс: после показа выигрыша подарки улетают в сумку
const _doiFly = doOpenInner;
doOpenInner = async function (sheet, id, c, n) {
  await _doiFly(sheet, id, c, n);
  setTimeout(() => {
    const imgs = [...sheet.querySelectorAll("#won .gift > img")].slice(0, 5);
    imgs.forEach((im, i) => setTimeout(() => flyToBag(im, i === imgs.length - 1 ? n : 1), i * 120));
  }, 1100);
};

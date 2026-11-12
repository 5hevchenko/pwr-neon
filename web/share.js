"use strict";
// ============================================================
//  Карточка выигрыша (share.py): кнопки на экране большого выигрыша.
//  Сумму считает сервер по своему журналу, клиент только подсказывает, какой выигрыш имеется в виду.
// ============================================================
const shareStoryOk = () => !!(tg && tg.shareToStory && tg.isVersionAtLeast && tg.isVersionAtLeast("7.8") && (tg.platform === "ios" || tg.platform === "android"));

function shareBtns() {
  return `<div class="bw-share"><button class="bw-sh main" data-to="chat">${ic("send")}Похвастаться</button>${shareStoryOk() ? `<button class="bw-sh" data-to="story">${ic("sparkles")}В сторис</button>` : ""}<button class="bw-sh" data-to="link">${ic("layers")}Ссылка</button></div>`;
}

const SHARE_DONE = new Map();   // одна победа — одна карточка, сколько бы раз ни нажали
async function shareWin(to, o, btn) {
  const key = (o.gift ? "g" + o.gift : "p" + o.pay), html = btn && btn.innerHTML;
  if (btn) { btn.disabled = true; btn.textContent = "Готовим карточку"; }
  try {
    let r = SHARE_DONE.get(key);
    if (!r) {
      r = await post("share/win", { pay: o.pay, gift: o.gift || 0, lang: typeof LANG === "string" ? LANG : "ru" }, { quiet: true });
      SHARE_DONE.set(key, r);
      if (SHARE_DONE.size > 20) SHARE_DONE.delete(SHARE_DONE.keys().next().value);
    }
    if (to === "story") { tg.shareToStory(r.story, { text: `${r.text}\n${r.link}` }); return; }
    if (to === "link") { copyText(r.page || r.link); return; }
    await shareChat(r);
  } catch (e) {
    toast(e.status && e.status !== "net" && e.message ? e.message : "Карточка сейчас недоступна, попробуй позже", "err");
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = html; }
  }
}

function shareChat(r) {
  return new Promise(ok => {
    if (r.prepared && tg && tg.shareMessage && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0")) {
      try { tg.shareMessage(r.prepared, sent => { if (sent) { H.ok(); toast("Карточка отправлена"); } ok(); }); return; } catch (e) {}
    }
    const url = "https://t.me/share/url?url=" + encodeURIComponent(r.page || r.link) + "&text=" + encodeURIComponent(r.text);   // страница карточки: в превью сама картинка
    if (tg && tg.openTelegramLink && inTg) tg.openTelegramLink(url); else window.open(url, "_blank");
    ok();
  });
}

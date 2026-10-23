// Shared helpers for the pywebview pages.
const $ = (s, r = document) => r.querySelector(s);
const api = () => (window.pywebview && window.pywebview.api) || null;
const iconCache = {};
function mmss(s) { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }
function esc(t) { return String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
// Official icon with text fallback (never a broken image).
async function setIcon(el, kind, key, label) {
  if (!el) return;
  const tag = kind + '/' + key;
  if (el.dataset.icon === tag) return;
  el.dataset.icon = tag;
  let url = iconCache[tag];
  if (url === undefined && api()) { try { url = await api().icon(kind, key); } catch (e) { url = ''; } iconCache[tag] = url; }
  if (el.dataset.icon !== tag) return;
  if (url) { el.innerHTML = `<img src="${url}" alt="">`; el.classList.remove('txt'); }
  else { el.textContent = (label || key || '?').replace(/_/g, ' ').slice(0, 6); el.classList.add('txt'); }
}
function onReady(fn) {
  if (window.pywebview && window.pywebview.api) fn();
  else window.addEventListener('pywebviewready', fn, { once: true });
}
function poll(fn, ms) {
  let stop = false;
  const tick = async () => { if (stop) return; try { const s = await api().state(); fn(s); } catch (e) { console.error(e); } setTimeout(tick, ms); };
  tick();
  return () => { stop = true; };
}
function applyMotion(s) { document.documentElement.classList.toggle('reduce-motion', !!s.reduce_motion); }
// Settings sections (anchors on settings.html) used by every "缺配置" hint.
const SET = { rem: 'settings.html#rem', coach: 'settings.html#coach', voice: 'settings.html#voice', overlay: 'settings.html#overlay', adv: 'settings.html#adv', about: 'settings.html#about' };
// Glass toast above the ask bar, 2.5 s. o.href adds a "去设置 →" link; hovering keeps it open.
function toast(msg, o) {
  o = o || {}; const t = $('#toast'); if (!t) return;
  t.classList.add('toast');
  t.innerHTML = `<span class="ti"><svg class="ico"><use href="#${o.icon || 'info'}"/></svg></span><span>${esc(msg)}</span>` +
    (o.href ? `<a class="link" href="${o.href}">${esc(o.action || '去设置')} →</a>` : '');
  const hide = () => { clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('on'), o.ms || 2500); };
  t.onmouseenter = () => clearTimeout(t._t); t.onmouseleave = hide;
  t.classList.add('on'); clearTimeout(t._t); if (!o.sticky) hide();
}
// Clipboard with a fallback for contexts where navigator.clipboard is unavailable.
async function copyText(text) {
  try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; } } catch (e) { /* fall through */ }
  const ta = document.createElement('textarea');
  ta.value = text; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
  document.body.appendChild(ta); ta.select();
  let ok = false; try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  ta.remove(); return ok;
}
function chip(el, cls, text) { if (el) el.innerHTML = `<span class="dot ${cls}"></span>${esc(text)}`; }
// Title-bar status chips shared by every main-window page.
function renderTopbar(s) {
  const g = s.gsi;
  chip($('#chip-gsi'), g.online ? 'ok' : 'warn', g.online ? 'Dota 已连接' : '等待 Dota');
  chip($('#chip-coach'), s.coach.key_ok && !s.coach.error ? 'ok' : 'warn', s.coach.key_ok ? `教练 · ${s.coach.provider}` : '教练 · 未配置');
  const cc = $('#chip-coach'); if (cc) cc.title = s.coach.error ? s.coach.error.reason_zh : '';
  const ttsOff = s.voice.tts === 'mock';
  const v = $('#chip-voice');
  if (v) {
    // status dot like the other chips: green = configured, grey = 未配置
    v.innerHTML = `<span class="dot ${ttsOff ? 'mute' : 'ok'}"></span><svg class="ico" style="width:14px;height:14px"><use href="#${ttsOff ? 'vol-off' : 'vol'}"/></svg><span>${ttsOff ? '播报 · 未配置' : '播报'}</span>`;
    v.classList.toggle('off', ttsOff); v.title = ttsOff ? '去设置配置播报' : `播报 · ${s.voice.tts_zh}`;
  }
}
// Window buttons, chips and rail entries. Nothing here is a dead click.
function wireChrome(getState) {
  const on = (sel, fn) => { const el = $(sel); if (el) el.onclick = fn; };
  on('#btn-min', () => api().minimize());
  on('#btn-close', () => api().close());
  on('#btn-ov', () => api().toggle_overlay());
  on('#chip-gsi', () => { location.href = SET.adv; });
  on('#chip-coach', () => {
    const s = getState();
    if (s && !s.coach.key_ok) toast('教练还没配 Key，提醒照常工作', { icon: 'alert', href: SET.coach });
    else if (s && s.coach.error) toast(s.coach.error.reason_zh, { icon: 'alert', href: SET.coach });
    else location.href = SET.coach;
  });
  on('#chip-voice', () => { const s = getState(); if (s && s.voice.tts === 'mock') toast('还没配语音播报，提醒先只在小窗显示', { icon: 'alert', href: SET.voice }); else location.href = SET.voice; });
  document.querySelectorAll('.rail a.soon').forEach(a => a.onclick = () => toast('这个页面还在做，先用首页'));
}

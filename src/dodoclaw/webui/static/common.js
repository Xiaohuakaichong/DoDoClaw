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

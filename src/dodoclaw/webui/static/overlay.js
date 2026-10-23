const GLYPH = { shrine: ['rgba(98,168,255,.14)', 'var(--info)'], cube: ['rgba(243,194,107,.14)', 'var(--gold)'], spark: ['rgba(229,72,47,.14)', 'var(--brand-2)'] };
let lastAlertAt = 0;
function timerRow(x) {
  const isItem = x.icon.startsWith('item:');
  const [bg, fg] = GLYPH[x.icon] || ['rgba(255,255,255,.06)', 'var(--text-2)'];
  const ic = isItem ? `<div class="gl ic" data-item="${x.icon.slice(5)}"></div>`
    : `<div class="gl" style="background:${bg};color:${fg}"><svg class="ico"><use href="#${x.icon}"/></svg></div>`;
  const pct = Math.min(1, Math.max(0, 1 - x.remain / x.total)).toFixed(3);
  return `<div class="tm">${ic}<div class="m"><div class="n">${esc(x.name)}<b ${x.hot ? 'style="color:var(--brand-2)"' : ''}>${mmss(x.remain)}</b></div><div class="bar"><i style="width:100%;background:var(${x.color});transform:scaleX(${pct})"></i></div></div></div>`;
}
function render(s) {
  applyMotion(s);
  if (s.ov_opacity) $('.ov').style.background = `rgba(9,11,16,${(s.ov_opacity / 100).toFixed(2)})`;
  const ov = $('#ov'), pill = $('#pill');
  ov.hidden = s.compact; pill.hidden = !s.compact;
  const dotCls = s.gsi.online ? (s.paused ? 'warn' : 'ok') : 'err';
  $('#dot').className = 'dot ' + dotCls; $('#pdot').className = 'dot ' + dotCls;
  const clk = s.in_game ? s.clock_mmss : '--:--';
  $('#clock').textContent = clk; $('#pclock').textContent = clk;
  const dn = $('#dn');
  if (s.paused) { dn.hidden = false; dn.textContent = 'Ⅱ 暂停'; }
  else if (s.daytime === null || s.daytime === undefined) dn.hidden = true;
  else { dn.hidden = false; dn.textContent = s.daytime ? '☀ 白天' : '☾ 夜晚'; }
  $('#vol').classList.toggle('on', !!s.speaking);
  const al = s.alert || {};
  const urgent = al.text && al.urgent, soft = al.text && !al.urgent;
  $('#alert').hidden = !urgent; $('#soft').hidden = !soft;
  if (urgent) {
    $('#alert-t').textContent = al.text;
    // Ring shows the objective countdown (e.g. Roshan), not the banner's own timeout
    const tgt = (s.timers || []).find(x => x.hot) || null;
    if (tgt) {
      $('#ring-n').textContent = tgt.remain;
      $('#ring').setAttribute('stroke-dashoffset', (125.6 * (1 - Math.min(tgt.remain, 30) / 30)).toFixed(1));
      $('#alert-s').textContent = `${tgt.name.replace(/^肉山/, '')}还有 ${tgt.remain} 秒`;
    } else { $('#ring-n').textContent = '!'; $('#ring').setAttribute('stroke-dashoffset', '0'); $('#alert-s').textContent = ''; }
    if (al.at !== lastAlertAt) { lastAlertAt = al.at; ov.classList.remove('hot'); void ov.offsetWidth; ov.classList.add('hot'); }
  } else ov.classList.remove('hot');
  if (soft) $('#soft-t').textContent = al.text;
  const hotKey = urgent ? ((s.timers || []).find(x => x.hot) || {}).key : null;
  const ts = (s.timers || []).filter(x => x.key !== hotKey).slice(0, urgent ? 1 : 2);
  $('#timers').innerHTML = ts.map(timerRow).join('');
  document.querySelectorAll('[data-item]').forEach(el => setIcon(el, 'items', el.dataset.item, '盾'));
  $('#pnext').innerHTML = ts[0] ? `${esc(ts[0].name.slice(0, 2))} <b class="num" style="color:var(--info);font-size:15px">${mmss(ts[0].remain)}</b>` : '';
  const box = $('#ans');
  if (s.error) { box.hidden = false; box.classList.add('err'); $('#ans-who').textContent = '出错了'; $('#ans-t').textContent = s.error; }
  else if (s.busy) { box.hidden = false; box.classList.remove('err'); $('#ans-who').textContent = '教练'; $('#ans-t').textContent = '思考中…'; }
  else if (s.answer && s.answer.text && !urgent) {
    box.hidden = false; box.classList.remove('err');
    $('#ans-who').innerHTML = s.speaking ? '<span class="wave"><i style="height:6px"></i><i style="height:14px"></i><i style="height:9px"></i><i style="height:12px"></i></span>正在播报'
      : `<svg class="ico" style="width:12px;height:12px;color:var(--brand-2)"><use href="#spark"/></svg>教练 · ${esc(s.answer.clock)} · ${(s.answer.ms / 1000).toFixed(1)}s`;
    $('#ans-t').textContent = s.answer.text;
  } else box.hidden = true;
}
onReady(() => {
  const q = $('#q');
  q.addEventListener('keydown', e => {
    if (e.key === 'Enter' && q.value.trim()) { api().ask(q.value.trim(), true); q.value = ''; }
    if (e.key === 'Escape') { q.value = ''; q.blur(); api().release_focus(); }
  });
  $('#mic').onclick = () => api().listen();
  $('#cmp').onclick = () => api().toggle_compact();
  $('#exp').onclick = () => api().toggle_compact();
  $('#hd').addEventListener('dblclick', () => api().toggle_compact());
  $('#pill').addEventListener('dblclick', () => api().toggle_compact());
  poll(s => { render(s); fit(); }, 500);
});

// Window follows content: 12px transparent margin on every side for the shadow
let lastSize = '';
function fit() {
  const el = $('#ov').hidden ? $('#pill') : $('#ov');
  const r = el.getBoundingClientRect();
  const w = Math.ceil(r.width) + 24, h = Math.ceil(r.height) + 24, k = `${w}x${h}`;
  if (k !== lastSize && r.height > 0) { lastSize = k; api().fit_overlay(w, h); }
}

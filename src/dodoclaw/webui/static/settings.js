// Settings page. A key only goes JS → Python, through save_key(provider_id, key); Python never
// sends a key back — only "configured" booleans, display names and the env var name.
let S = null, lastS = null;
const ROWS = {
  bounty: { n: '赏金符', s: '0:00 起每 3 分钟，报到 15:00 · 4、5 号位默认开', ico: 'coin', cls: 'gold' },
  runes: { n: '水符 · 强化符', s: '水符 2:00 / 4:00，强化符报到 20:00 · 2 号位默认开', ico: 'rune' },
  shrine: { n: '智慧神龛', s: '7:00 起每 7 分钟', ico: 'shrine' },
  cube: { n: '痛苦魔方', s: '15:00 首刷及每次复活 · “魔方 30 秒后刷新”', ico: 'cube', cls: 'warm' },
  roshan: { n: '肉山复活', s: '最早复活时间前提醒 · “肉山快复活了”', ico: 'skull', cls: 'warm' },
  aegis: { n: '不朽盾', s: '捡盾后 4:00 报 · “盾还剩 1 分钟”', item: 'aegis', label: '不朽盾' },
  tp: { n: '没带回城卷轴', s: '10:00、20:00 各检查一次，每局最多 2 次', item: 'tpscroll', label: '回城', fixed: '固定时间检查，没有提前量' },
  buyback: { n: '后期买活', s: '25 分钟后变为可用 / 买大件后钱不够买活', ico: 'heart', cls: 'gold', fixed: '状态变化时报，没有提前量' },
  lowhp: { n: '低血量 · 大招就绪', s: '默认关，开了会多不少播报，不计入上面的条数', ico: 'alert', fixed: '即时触发' },
};
const PANES = ['rem', 'coach', 'overlay', 'adv', 'about'];

function flashSaved() { document.querySelectorAll('.pane.on .saved').forEach(e => { e.classList.add('on'); clearTimeout(e._t); e._t = setTimeout(() => e.classList.remove('on'), 1500); }); }
async function save(patch) {
  const r = await api().save_settings(patch);
  if (r && r.msg) toast(r.msg, { icon: 'alert' }); else flashSaved();
  await refresh();
  return r;
}
function setSlider(el, pct) { el.querySelector('.fl').style.width = pct + '%'; el.querySelector('.th').style.left = pct + '%'; }
function show(sec) {
  const pane = sec === 'voice' ? 'coach' : (PANES.includes(sec) ? sec : 'rem');
  document.querySelectorAll('.pane').forEach(p => p.classList.toggle('on', p.id === 'p-' + pane));
  document.querySelectorAll('.snav a').forEach(a => a.classList.toggle('on', a.dataset.s === pane));
  if (sec === 'voice') { const c = $('#c-voice'); c.scrollIntoView({ block: 'nearest' }); c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash'); }
}

function renderRem(s) {
  const ui = s.ui, pos = new Set(ui.positions);
  document.querySelectorAll('#pos span').forEach(e => {
    const p = e.dataset.p; e.classList.toggle('on', p === 'all' ? pos.size === 5 : pos.has(+p));
  });
  $('#bud-n').textContent = s.budget; $('#bud-cap').textContent = s.budget_cap;
  $('#bud-bar').style.width = Math.min(100, s.budget / s.budget_cap * 100).toFixed(0) + '%';
  $('#budget').classList.toggle('over', s.budget > s.budget_cap);
  $('#bud-hint').textContent = s.budget > s.budget_cap ? s.over_cap_hint : '';
  const pending = new Set(s.pending || []);
  const box = $('#rrows');
  if (!box.children.length) {
    box.innerHTML = Object.entries(ROWS).map(([k, r]) => {
      const ic = r.item ? `<span class="it" data-n="${r.label}" id="it-${k}"></span>` : `<span class="gl ${r.cls || ''}"><svg class="ico"><use href="#${r.ico}"/></svg></span>`;
      // lead times are read-only until the reminder engine supports them (no input, not draggable)
      const lead = r.fixed ? `<span class="fixed">${r.fixed}</span>` :
        `<div class="lead locked" aria-disabled="true" title="提醒引擎接入后可调"><div class="slider dis" data-k="${k}"><i class="tr"></i><i class="fl"></i><i class="th"></i></div><span class="lv num"><b></b><small>秒</small></span></div>`;
      const pend = pending.has(k);
      const tag = pend ? '<span class="soon-tag">即将上线</span>' : '';
      return `<div class="rr${pend ? ' pending' : ''}" data-k="${k}">${ic}<div><div class="n">${r.n}${tag}</div><div class="s">${r.s}</div></div><i class="sw${pend ? ' dis pend' : ''}" role="switch"${pend ? ' aria-disabled="true" title="这条提醒还在做"' : ''}></i>${lead}</div>`;
    }).join('');
    for (const [k, r] of Object.entries(ROWS)) if (r.item) setIcon($('#it-' + k), 'items', r.item, r.label).then(() => { const el = $('#it-' + k); if (el.classList.contains('txt')) { el.textContent = ''; el.classList.remove('txt'); } });
    box.querySelectorAll('.rr').forEach(row => {
      const k = row.dataset.k;
      row.querySelector('.sw').onclick = pending.has(k)
        ? () => toast('这条提醒还在做', { icon: 'info' })
        : () => save({ reminder: k, on: !S.ui.reminders[k].on });
    });
  }
  box.querySelectorAll('.rr').forEach(row => {
    const k = row.dataset.k, v = ui.reminders[k];
    const on = v.on && !pending.has(k);
    row.classList.toggle('off', !on); row.querySelector('.sw').classList.toggle('on', on);
    const sl = row.querySelector('.slider');
    if (sl && v.lead != null) { setSlider(sl, (v.lead - 5) / 55 * 100); row.querySelector('.lv b').textContent = v.lead; }
  });
}

// ── 教练卡（README D10 “设置页直接配置服务商和 Key”） ──
// ks: none | switch | typing | testing | ok | retest | error — set on #c-coach[data-ks]
let busy = null;        // null | 'save' | 'retest'
let changing = false;   // 更换 Key: input reopened over a configured key
let saveErr = '';       // key rejected before saving (format / write error)
let localTest = null;   // 20 s JS timeout result, until the next real test
const TEST_WAIT_MS = 20000;
const EXT = '<svg class="ico" style="width:12px;height:12px;vertical-align:-1px"><use href="#ext"/></svg>';
const CK = '<svg class="ico ck"><use href="#check"/></svg>';
const TIMEOUT = { ok: false, kind: 'network', reason_zh: '等了 20 秒还没有回应', detail_zh: '多半是网络或代理的问题，检查后点“重新测试”，不用重填。提醒不受影响。', link: '', link_zh: '' };

function tagPill(tag, brand) { return tag ? `<span class="pill ${brand ? 'brand' : 'mute'} tiny">${esc(tag)}</span>` : ''; }
function lastTest(k) { return localTest || k.last_test || {}; }
function coachKs(k) {
  if (busy === 'save') return 'testing';
  if (k.configured && !changing) return busy === 'retest' ? 'retest' : (lastTest(k).ok === false ? 'error' : 'ok');
  if ($('#key-in').value.trim()) return 'typing';
  return k.switched_from && !changing ? 'switch' : 'none';
}
function agoZh(at) {
  if (!at) return '';
  const s = Date.now() / 1000 - at;
  if (s < 90) return '刚刚测试';
  if (s < 3600) return `${Math.round(s / 60)} 分钟前测试`;
  return `${Math.round(s / 3600)} 小时前测试`;
}

function renderProvMenu(s) {
  const k = s.key, rows = s.providers || [];
  $('#prov-menu').innerHTML = rows.map(p => {
    const st = p.configured ? '<span class="dot ok"></span>已配置' : '未配置';
    return `<div class="mi${p.current ? ' cur' : ''}" role="option" aria-selected="${p.current}" data-v="${esc(p.id)}">${CK}<div><div class="nm">${esc(p.name)}${tagPill(p.tag, p.id === 'deepseek')}</div><div class="ds">${esc(p.model)} · ${st}${p.hint ? ' · ' + esc(p.hint) : ''}</div></div>${p.apply_url ? `<span class="link ap" data-apply="${esc(p.id)}">去申请 ${EXT}</span>` : ''}</div>`;
  }).join('') + '<div class="ft" title="config\\settings.yaml">每家的 Key 分开保存，切换不会清掉别家的。<br>通义、Kimi、自定义接口暂时只能在程序目录 config 文件夹里的设置文件中修改。</div>';
  if (!k.in_picker) $('#prov-menu .ft').insertAdjacentHTML('afterbegin', `现在用的是 ${esc(k.provider_name)}（在设置文件里改的）。<br>`);
}

function renderCoachKs() {
  const s = S; if (!s) return;
  const k = s.key, ks = coachKs(k), card = $('#c-coach');
  card.dataset.ks = ks;
  card.classList.toggle('changing', changing && k.configured && busy !== 'save');
  // header pill
  const pill = {
    none: '<span class="pill warn"><span class="dot warn"></span>未配置</span>',
    testing: '<span class="pill mute"><span class="spin-s"></span>测试中</span>',
    ok: '<span class="pill ok"><span class="dot ok"></span>已配置</span>',
    error: '<span class="pill err"><span class="dot err"></span>连接失败</span>',
  };
  // while 更换 Key is open the saved key still counts: the pill keeps its configured status
  const pk = ['none', 'switch', 'typing'].includes(ks) && k.configured ? (lastTest(k).ok === false ? 'error' : 'ok') : ({ switch: 'none', typing: 'none', retest: 'testing' }[ks] || ks);
  $('#coach-pill').innerHTML = pill[pk];
  // snav dot: 未配置 = warn, 连接失败 = err
  const dot = $('#snav-coach-dot');
  dot.style.display = pk === 'ok' || pk === 'testing' ? 'none' : '';
  dot.className = 'dot ' + (pk === 'error' ? 'err' : 'warn');
  // key input
  const inp = $('#key-in'), typed = !!inp.value.trim();
  inp.disabled = ks === 'testing';
  $('#key-box').classList.toggle('dis', ks === 'testing');
  const sb = $('#btn-savekey');
  sb.classList.toggle('busy', ks === 'testing');
  sb.classList.toggle('off', !typed && ks !== 'testing');
  sb.setAttribute('aria-disabled', String(!typed));
  sb.title = typed ? '' : '先把 Key 粘贴进来';
  sb.innerHTML = ks === 'testing' ? '<span class="spin-s"></span>测试中…' : '保存并测试';
  $('#kset-pill').innerHTML = ks === 'ok' ? '<span class="pill ok tiny"><span class="dot ok" style="width:6px;height:6px"></span>已配置</span>' : '<span class="pill mute tiny">已配置</span>';
  const tb = $('#btn-test');
  tb.classList.toggle('busy', ks === 'retest');
  tb.innerHTML = ks === 'retest' ? '<span class="spin-s"></span>测试中…' : '<svg class="ico" style="width:14px;height:14px"><use href="#refresh"/></svg>重新测试';
  $('#btn-change').classList.toggle('off', ks === 'retest');
  // 说明 / 测试结果
  $('#res-k').textContent = ['none', 'switch', 'typing'].includes(ks) ? '说明' : '测试结果';
  const res = $('#key-res'), t = lastTest(k);
  let html = '';
  if (ks === 'none') {
    html = saveErr
      ? `<div class="callout err"><svg class="ico"><use href="#alert"/></svg><div><div class="t">${esc(saveErr)}</div><div class="d">Key 没有保存，检查后重新粘贴。提醒不受影响。</div></div></div>`
      : changing ? '<span class="hint">粘贴新的 Key 后点“保存并测试”，会替换掉现在这个。保存后输入框清空，Key 不再显示。</span>'
        : '<span class="hint">粘贴后点“保存并测试”，会发一条很短的请求试试。保存后输入框清空，Key 不再显示。</span>';
  } else if (ks === 'switch') {
    const p = k.switched_from;
    html = `<div class="callout info" style="padding:8px 12px"><svg class="ico" style="width:16px;height:16px"><use href="#info"/></svg><div class="d" style="margin:0">已切到 ${esc(k.provider_name)}，它还没有 Key，教练提问暂时用不了。<b style="color:var(--text)">${esc(p.name)} 的 Key 还在</b>，每家分开保存，切回去不用重填。</div><div class="acts"><span class="link" style="font-size:12px" data-back="${esc(p.id)}">切回 ${esc(p.name)}</span></div></div>`;
  } else if (ks === 'typing') {
    html = '<span class="hint">保存前可以点 <svg class="ico" style="width:13px;height:13px;vertical-align:-2px"><use href="#eye"/></svg> 核对自己粘贴的内容；保存后就不能再看了。</span>';
  } else if (ks === 'testing' || ks === 'retest') {
    html = `<span class="t2">正在用 ${esc(k.model)} 发一条很短的请求，最多等 15 秒…</span>`;
  } else if (ks === 'ok' && t.ok) {
    const sec = t.ms != null ? `首个回复 <b class="num" style="font-size:15px">${(t.ms / 1000).toFixed(1)}</b> 秒` : '';
    html = `<span style="display:flex;align-items:center;gap:10px;min-width:0;flex:1"><span class="pill ok"><span class="dot ok"></span>连接正常</span><span class="t2" style="white-space:nowrap">${esc(t.model || k.model)}${sec ? ' · ' + sec : ''}</span><span class="hint" style="margin-left:auto;white-space:nowrap">${agoZh(t.at)}</span></span>`;
  } else if (ks === 'ok') {
    html = '<span class="pill mute">还没测试</span><span class="hint">点“重新测试”发一条很短的请求试试</span>';
  } else {
    const link = t.link ? `<span class="link" style="font-size:12px" data-link="${esc(t.link)}">${esc(t.link_zh)}${t.link === 'log' ? '' : ' ' + EXT}</span>` : '';
    html = `<div class="callout err"><svg class="ico"><use href="#alert"/></svg><div><div class="t">${esc(t.reason_zh || '没连上')}</div><div class="d">${esc(t.detail_zh || '提醒不受影响。')}</div></div>${link ? `<div class="acts">${link}</div>` : ''}</div>`;
  }
  if (res._h !== html) { res.innerHTML = html; res._h = html; }
}

function renderCoach(s) {
  const k = s.key, v = s.voice;
  // 服务商
  $('#prov-name').textContent = k.provider_name;
  $('#prov-tag').innerHTML = k.in_picker ? tagPill(k.provider_tag, k.provider === 'deepseek') : '';
  $('#prov-model').textContent = `模型 ${k.model}`;
  const ap = $('#btn-apply');
  ap.innerHTML = `去申请 ${esc(k.provider_short)} Key ${EXT}`;
  ap.style.display = k.apply ? '' : 'none';
  renderProvMenu(s);
  // Key
  $("#key-in").placeholder = `粘贴 ${k.provider_short} 的 API Key`;
  $('#key-line').textContent = `${k.key_env}=你的Key`;
  renderCoachKs();
  // 播报 · 缺少声音组件 → 声音行换成提示，试听和开关都灰掉并说明原因
  const miss = v.tts_available === false;
  document.documentElement.classList.toggle('st-tts-missing', miss);
  $('#tts-pill').className = 'pill tts-ok ' + (v.tts_on ? 'ok' : 'mute');
  $('#tts-pill').innerHTML = v.tts_on ? '<span class="dot ok"></span>已开启' : '未开启';
  const sw = $('#sw-tts');
  sw.classList.toggle('on', v.tts_on && !miss);
  sw.classList.toggle('dis', miss);
  sw.setAttribute('aria-disabled', String(miss));
  sw.title = miss ? '缺少声音组件，开不了' : '';
  $('#tts-name').innerHTML = `<span class="tn">${esc(v.preview_voice_zh || 'Edge 免费声音')}</span>`;
  // 语音提问
  $('#sw-ask').classList.toggle('on', v.ask_on);
  // 语音提问关着时，识别方式和快捷键都不能点
  $('#c-voice').classList.toggle('ask-off', !v.ask_on);
  document.querySelectorAll('#c-voice .opt').forEach(o => { o.classList.toggle('dis', !v.ask_on); o.setAttribute('aria-disabled', String(!v.ask_on)); });
  $('#btn-hotkey').setAttribute('aria-disabled', String(!v.ask_on));
  $('#ask-pill').className = 'pill ' + (v.ask_on ? 'ok' : 'mute');
  $('#ask-pill').textContent = v.ask_on ? `已开启 · ${v.stt_zh}` : '未配置语音识别';
  $('#ask-ico').style.color = v.ask_on ? 'var(--info)' : 'var(--text-3)';
  $('#ask-ico use').setAttribute('href', v.ask_on ? '#mic' : '#mic-off');
  $('#opt-local').classList.toggle('sel', v.stt_mode === 'local');
  $('#opt-cloud').classList.toggle('sel', v.stt_mode === 'cloud');
  const tag = (el, html) => { el.innerHTML = html; };
  const def = '<span class="pill brand" style="height:18px;font-size:10px">默认</span>';
  tag($('#tag-local'), v.stt_default === 'local' ? def : '');
  tag($('#tag-cloud'), v.stt_default === 'cloud' ? def : '<span class="pill warn" style="height:18px;font-size:10px">需要单独的 Key</span>');
  $('#d-cloud').textContent = k.has_stt ? '和教练用同一个 Key' : `${k.provider_short} 不带识别，要另配阶跃 Key`;
  $('#d-local').textContent = v.whisper_ready ? '离线可用，不需要 Key' : '离线可用，首次下载约 150 MB';
}

function renderOverlay(s) {
  $('#sw-auto').classList.toggle('on', !!s.ui.auto_overlay);
  $('#sw-rm').classList.toggle('on', !!s.ui.reduce_motion);
  document.documentElement.classList.toggle('reduce-motion', !!s.ui.reduce_motion);
}

function renderAdv(s) {
  const a = s.adv;
  $('#adv-pill').className = 'pill ' + (a.online ? 'ok' : 'warn');
  $('#adv-pill').innerHTML = a.online ? '<span class="dot ok"></span>正常' : '<span class="dot warn"></span>等待 Dota';
  $('#adv-updates').textContent = a.updates.toLocaleString('en-US');
  $('#adv-age').innerHTML = a.age == null ? '—' : `${a.age}<small style="font-size:13px;color:var(--text-3)"> 秒前</small>`;
  $('#adv-port').textContent = a.port; $('#adv-host').textContent = `端口 · ${a.host}`;
  $('#adv-token').textContent = a.token_set ? '已设置' : '未设置';
  $('#adv-cfg').textContent = a.cfg_path ? (a.cfg_ok ? a.cfg_path : '还没写入：' + a.cfg_path) : '没找到 Dota 目录';
  $('#adv-cfg').dataset.path = a.cfg_path || ''; $('#adv-cfg').title = a.cfg_path ? a.cfg_path + '\n点击复制' : '';
  $('#adv-cfg').classList.toggle('copyable', !!a.cfg_path);
  $('#sw-rec').classList.toggle('on', a.recording);
  $('#adv-icondir').textContent = a.icon_dir || '';
  $('#adv-icondir').dataset.path = a.icon_dir || ''; $('#adv-icondir').title = a.icon_dir ? a.icon_dir + '\n点击复制' : '';
  $('#adv-icons').textContent = `${a.icon_count} 个 · ${a.icon_mb} MB`;
  $('#ver-side').textContent = `v${s.version} 预览版`; $('#ver-about').textContent = `v${s.version} 预览版`;
}

function withTimeout(p, ms) {
  let t;
  return Promise.race([p, new Promise((_, rej) => { t = setTimeout(() => rej({ timeout: true }), ms); })]).finally(() => clearTimeout(t));
}

// 重新测试: one minimal request with the saved key; the result shows in the 测试结果 row.
async function runTest() {
  if (busy) return;
  busy = 'retest'; localTest = null; renderCoachKs();
  try { await withTimeout(api().test_key(), TEST_WAIT_MS); }
  catch (e) { localTest = e && e.timeout ? { ...TIMEOUT } : null; }
  finally { busy = null; await refresh(); }
}

// 保存并测试: save first, then test (a failed test keeps the key). The input is cleared
// as soon as save_key returns, whatever the result.
async function saveKey() {
  const inp = $('#key-in');
  if (busy) return;
  if (!inp.value.trim()) { toast('先把 Key 粘贴进来', { icon: 'info' }); inp.focus(); return; }
  const pid = S.key.provider;
  busy = 'save'; saveErr = ''; localTest = null; renderCoachKs();
  let r;
  try { r = await withTimeout(api().save_key(pid, inp.value), TEST_WAIT_MS); }
  catch (e) { r = e && e.timeout ? { timeout: true } : { ok: false, kind: 'store', reason_zh: '没能保存，详情见日志', saved: false }; }
  inp.value = ''; setEye(false);
  busy = null;
  if (r.timeout) localTest = { ...TIMEOUT };
  else if (r.saved === false) saveErr = r.reason_zh || '没能保存，详情见日志';
  else { changing = false; flashSaved(); if (r.msg) toast(r.msg, { icon: 'alert' }); }
  await refresh();
  if (r.timeout && !S.key.configured) { localTest = null; saveErr = '等了 20 秒还没有回应'; renderCoachKs(); }
}

function setEye(show) {
  $('#key-in').type = show ? 'text' : 'password';
  $('#btn-eye use').setAttribute('href', show ? '#eye-off' : '#eye');
  $('#btn-eye').title = show ? '隐藏输入内容' : '显示输入内容（只在保存前可看）';
}
function resetKeyInput() { $('#key-in').value = ''; setEye(false); saveErr = ''; }

// 选中即生效：写 coach.provider + coach.model，热重载，没有确认框
async function pickProvider(id) {
  if (busy) return;
  resetKeyInput(); changing = false; localTest = null;  // a key typed for the old provider is never saved under the new one
  const r = await api().set_provider(id);
  if (!r || !r.ok) toast((r && r.msg) || '没能切换，详情见日志', { icon: 'alert' });
  else { flashSaved(); if (r.msg) toast(r.msg, { icon: 'alert' }); }
  await refresh();
  if (r && r.ok && r.key && r.key.configured) runTest();  // the old result no longer applies
}

function wireProvMenu() {
  const dd = $('#dd-prov'), menu = $('#prov-menu');
  const items = () => [...menu.querySelectorAll('.mi')];
  const hov = el => { items().forEach(e => e.classList.toggle('hov', e === el)); };
  const isOpen = () => !menu.hidden;
  const close = () => { menu.hidden = true; dd.classList.remove('open'); dd.setAttribute('aria-expanded', 'false'); };
  const open = () => { if (busy) return toast('正在测试，等一下再换', { icon: 'info' }); menu.hidden = false; dd.classList.add('open'); dd.setAttribute('aria-expanded', 'true'); hov(menu.querySelector('.cur') || items()[0]); };
  dd.onclick = () => (isOpen() ? close() : open());
  dd.onkeydown = e => {
    const list = items(), i = list.findIndex(x => x.classList.contains('hov'));
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (!isOpen()) open(); else if (i >= 0) list[i].click(); }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); if (!isOpen()) return open();
      hov(list[Math.max(0, Math.min(list.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]);
    } else if (e.key === 'Escape' || e.key === 'Tab') close();
  };
  menu.onmousemove = e => { const it = e.target.closest('.mi'); if (it) hov(it); };
  menu.onclick = async e => {
    const ap = e.target.closest('[data-apply]');
    if (ap) { e.stopPropagation(); if (!(await api().open_key_page(ap.dataset.apply, 'key'))) toast('没能打开浏览器，详情见日志', { icon: 'alert' }); return; }
    const it = e.target.closest('.mi'); if (!it) return;
    close(); dd.focus();
    if (!it.classList.contains('cur')) pickProvider(it.dataset.v);
  };
  document.addEventListener('mousedown', e => { if (!dd.contains(e.target) && !menu.contains(e.target)) close(); });
}

function wireCoach() {
  wireProvMenu();
  const inp = $('#key-in');
  inp.oninput = () => { saveErr = ''; renderCoachKs(); };
  inp.onkeydown = e => {
    if (e.key === 'Enter') saveKey();
    else if (e.key === 'Escape' && changing) { resetKeyInput(); changing = false; renderCoachKs(); }
  };
  $('#btn-eye').onclick = e => { e.preventDefault(); if (inp.disabled) return; setEye(inp.type === 'password'); inp.focus(); };
  $('#btn-savekey').onclick = saveKey;
  $('#btn-test').onclick = runTest;
  $('#btn-change').onclick = () => {
    if (busy) return toast('正在测试，等一下再换', { icon: 'info' });
    changing = true; resetKeyInput(); renderCoachKs(); setTimeout(() => inp.focus(), 0);
  };
  $('#btn-cancel').onclick = () => { changing = false; resetKeyInput(); renderCoachKs(); };
  $('#btn-apply').onclick = async () => { if (!(await api().open_key_page(S.key.provider, 'key'))) toast('没能打开浏览器，详情见日志', { icon: 'alert' }); };
  $('#key-res').onclick = async e => {
    const back = e.target.closest('[data-back]');
    if (back) return pickProvider(back.dataset.back);
    const l = e.target.closest('[data-link]'); if (!l) return;
    const ok = l.dataset.link === 'log' ? await api().open_log_dir() : await api().open_key_page(S.key.provider, l.dataset.link === 'topup' ? 'topup' : 'key');
    if (!ok) toast(l.dataset.link === 'log' ? '没能打开日志文件夹' : '没能打开浏览器，详情见日志', { icon: 'alert' });
  };
  $('#disc-env').onclick = () => {
    const d = $('#disc-env'), on = !d.classList.contains('open');
    d.classList.toggle('open', on); $('#env-body').classList.toggle('open', on); d.setAttribute('aria-expanded', String(on));
  };
}

async function refresh() {
  S = await api().settings_state();
  renderRem(S); renderCoach(S); renderOverlay(S); renderAdv(S);
}

onReady(async () => {
  wireChrome(() => lastS);
  show(location.hash.slice(1));
  window.addEventListener('hashchange', () => show(location.hash.slice(1)));
  document.querySelectorAll('.snav a').forEach(a => a.onclick = () => { location.hash = a.dataset.s; });
  // positions (multi-select; 全部 = all five)
  document.querySelectorAll('#pos span').forEach(e => e.onclick = () => {
    const cur = new Set(S.ui.positions), p = e.dataset.p;
    let next;
    if (p === 'all') next = cur.size === 5 ? [1] : [1, 2, 3, 4, 5];
    else { cur.has(+p) ? cur.delete(+p) : cur.add(+p); next = [...cur]; if (!next.length) return toast('至少选一个位置'); }
    save({ positions: next });
  });
  // 高级：手动编辑 .env — 打开文件夹 / 重新读取
  document.querySelectorAll('[data-act]').forEach(b => b.onclick = async () => {
    const act = b.dataset.act;
    if (act === 'reload_env') {
      localTest = null;
      const r = await api().reload_env(); await refresh();
      if (r.key.configured) runTest();  // found a key: test it once
      else toast(`还是没读到 Key，检查 .env 里有没有 ${r.key.key_env}=…`, { icon: 'alert' });
    } else if (!(await api()[act]())) toast('没能打开文件夹，详情见日志', { icon: 'alert' });
  });
  wireCoach();
  // voice
  const noTts = () => toast('缺少声音组件，提醒照常显示，只是不念出来。换最新安装包即可恢复', { icon: 'alert' });
  $('#sw-tts').onclick = async () => {
    if (S.voice.tts_available === false) return noTts();
    const r = await api().set_tts(!S.voice.tts_on); if (r.msg) toast(r.msg, { icon: 'alert' }); else flashSaved(); refresh();
  };
  $('#btn-preview-off').onclick = noTts;
  $('#btn-preview').onclick = async () => {
    const b = $('#btn-preview'); if (b.classList.contains('busy')) return;
    b.classList.add('busy');
    try { const r = await api().preview_tts(); if (!r || !r.ok) toast((r && r.msg) || '试听失败，详情见日志', { icon: 'alert' }); }
    catch (e) { toast('试听失败，详情见日志', { icon: 'alert' }); }
    finally { b.classList.remove('busy'); }
  };
  $('#sw-ask').onclick = () => save({ voice_ask: !S.voice.ask_on });
  document.querySelectorAll('.opt').forEach(o => o.onclick = () => { if (S.voice.ask_on) save({ stt_mode: o.dataset.m }); });
  $('#btn-hotkey').onclick = () => { if (S.voice.ask_on) toast('全局快捷键还在做，先点麦克风提问'); };
  // overlay & motion
  $('#btn-ovpos').onclick = async () => toast((await api().reset_overlay_pos()) ? '小窗已回到默认位置' : '小窗还没打开，进对局后再试');
  $('#sw-auto').onclick = () => save({ auto_overlay: !S.ui.auto_overlay });
  $('#sw-rm').onclick = async () => { await api().set_reduce_motion(!S.ui.reduce_motion); flashSaved(); refresh(); };
  // advanced
  $('#btn-cfg').onclick = async () => { const r = await api().rewrite_cfg(); toast(r.msg, { icon: r.ok ? 'check' : 'alert' }); refresh(); };
  document.querySelectorAll('#adv-cfg, #adv-icondir').forEach(el => el.onclick = async () => {
    const p = el.dataset.path; if (!p) return;
    const ok = await copyText(p);
    toast(ok ? '已复制路径' : '没能复制，请手动选中路径', { icon: ok ? 'check' : 'alert' });
  });
  $('#btn-port').onclick = () => toast('换端口还在做，这一版先用 3000');
  $('#sw-rec').onclick = async () => { const on = await api().set_gsi_record(!S.adv.recording); toast(on ? '开始录制，样本存在 logs\\gsi 里' : '已停止录制'); refresh(); };
  $('#btn-icons').onclick = async () => { const n = await api().clear_icon_cache(); toast(`已清空 ${n} 个图标，用到时会重新下载`); refresh(); };
  $('#btn-update').onclick = () => toast('检查更新还在做，新版本会发在社区里');
  await refresh();
  poll(s => { lastS = s; renderTopbar(s); applyMotion(s); }, 1500);
  setInterval(() => { if (document.querySelector('#p-adv.on')) refresh(); }, 2000);
});

// Settings page. Key values never reach JS: only "configured" booleans and the env var name to add.
let S = null, lastS = null, testing = false;
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

function renderCoach(s) {
  const k = s.key, v = s.voice;
  document.documentElement.classList.toggle('key-none', !k.configured);
  $('#prov-name').textContent = k.provider_name;
  $('#key-line').textContent = `${k.key_env}=你的Key`;
  $('#btn-apply').style.display = k.docs ? '' : 'none';
  const t = s.last_test || {};
  if (!testing) $('#test-res').innerHTML = t.ok === undefined
    ? '<span class="pill mute">还没测试</span><span class="hint">点“测试”发一条很短的请求试试</span>'
    : t.ok ? `<span class="pill ok">连接正常</span><span class="t2">用时 <b class="num" style="font-size:15px">${(t.ms / 1000).toFixed(1)}</b> 秒</span>`
      : `<span class="pill err">没连上</span><span class="t2">${esc(t.reason_zh)}</span>`;
  // 播报
  $('#tts-pill').className = 'pill ' + (v.tts_on ? 'ok' : 'mute');
  $('#tts-pill').innerHTML = v.tts_on ? '<span class="dot ok"></span>已开启' : '未配置';
  $('#sw-tts').classList.toggle('on', v.tts_on);
  $('#tts-name').textContent = v.tts_on ? v.tts_zh : '没开播报，提醒只在小窗显示';
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
  $('#d-cloud').textContent = k.has_stt ? '和教练用同一个 Key' : `${k.provider_name} 不带识别，要另配阶跃 Key`;
  $('#d-local').textContent = v.whisper_ready ? '离线可用，不需要 Key' : '离线可用，首次下载约 150 MB';
}

function renderOverlay(s) {
  const op = s.ui.overlay_opacity, sl = $('#sl-op'), inp = sl.querySelector('input');
  if (document.activeElement !== inp) inp.value = op;
  setSlider(sl, (op - 40) / 60 * 100); $('#op-v').textContent = op + '%';
  $('#ovmini').style.background = `rgba(14,17,25,${op / 100})`;
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

// One minimal request; the result is shown inline in the 上次测试 row (no toast).
async function runTest() {
  if (testing) return;
  testing = true;
  const b = $('#btn-test'); b.classList.add('busy'); b.textContent = '测试中…';
  $('#test-res').innerHTML = '<span class="pill mute"><span class="dot"></span>测试中…</span><span class="hint">发一条很短的请求</span>';
  try { await api().test_key(); }
  catch (e) { /* result comes back via settings_state().last_test */ }
  finally { testing = false; b.classList.remove('busy'); b.textContent = '测试'; await refresh(); }
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
  // key row — booleans only
  document.querySelectorAll('[data-act]').forEach(b => b.onclick = async () => {
    const act = b.dataset.act;
    if (act === 'reload_env') {
      const r = await api().reload_env(); await refresh();
      if (r.key.configured) runTest();  // found a key: test it once, result shows in the 上次测试 row
      else toast(`还是没读到 Key，检查 .env 里有没有 ${r.key.key_env}=…`, { icon: 'alert' });
    } else if (!(await api()[act]())) toast('没能打开文件夹，详情见日志', { icon: 'alert' });
  });
  $('#btn-test').onclick = runTest;
  $('#btn-apply').onclick = () => api().open_key_page();
  // voice
  $('#sw-tts').onclick = async () => { const r = await api().set_tts(!S.voice.tts_on); if (r.msg) toast(r.msg, { icon: 'alert' }); else flashSaved(); refresh(); };
  $('#btn-preview').onclick = async () => { if (!(await api().preview_tts())) toast('先打开语音播报再试听', { icon: 'alert' }); };
  $('#sw-ask').onclick = () => save({ voice_ask: !S.voice.ask_on });
  document.querySelectorAll('.opt').forEach(o => o.onclick = () => { if (S.voice.ask_on) save({ stt_mode: o.dataset.m }); });
  $('#btn-hotkey').onclick = () => { if (S.voice.ask_on) toast('全局快捷键还在做，先点麦克风提问'); };
  // overlay & motion
  const op = $('#sl-op input');
  op.oninput = () => { setSlider($('#sl-op'), (op.value - 40) / 60 * 100); $('#op-v').textContent = op.value + '%'; $('#ovmini').style.background = `rgba(14,17,25,${op.value / 100})`; };
  op.onchange = () => save({ overlay_opacity: +op.value });
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

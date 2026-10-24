// Settings page. A key only goes JS → Python, through save_key(provider_id, key); Python never
// sends a key back — only "configured" booleans, display names and the env var name.
let S = null, lastS = null;
let customFormId = ""; // editing custom id, or "" for new
let customBusy = false;
let dlTimer = null;
const ROWS = {
  bounty: { n: '赏金符', s: '每 3 分钟（跳过 0:00），提前 20 秒 · 所有位置可开，4、5 号位默认开', ico: 'coin', cls: 'gold' },
  runes: { n: '河道神符', s: '水符 2:00 / 4:00，强化符 6:00 起每 2 分 · 所有位置可开，2 号位默认开', ico: 'rune' },
  lotus: { n: '莲花池', s: '6:00 起每 6 分钟整点提醒 · 所有位置可开，3、4、5 号位默认开', ico: 'spark', fixed: '整点提醒，没有提前量' },
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
  if (sec === 'voice' || sec === 'stt') { const c = $('#c-stt'); c.scrollIntoView({ block: 'nearest' }); c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash'); }
  if (sec === 'tts') { const c = $('#c-tts'); c.scrollIntoView({ block: 'nearest' }); c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash'); }
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
let testSeq = 0;        // request id: only the newest test / switch may update the card
let switchTimer = null; // auto-test after a provider switch, debounced
const SWITCH_TEST_DELAY_MS = 400;
const TEST_WAIT_MS = 20000;
const EXT = '<svg class="ico" style="width:12px;height:12px;vertical-align:-1px"><use href="#ext"/></svg>';
const CK = '<svg class="ico ck"><use href="#check"/></svg>';
const TIMEOUT = { ok: false, kind: 'network', reason_zh: '等了 20 秒还没有回应', detail_zh: '多半是网络或代理的问题，检查后点“重新测试”，不用重填。提醒不受影响。', link: '', link_zh: '' };

function tagPill(tag, brand) { return tag ? `<span class="pill ${brand ? 'brand' : 'mute'} tiny">${esc(tag)}</span>` : ''; }
function lastTest(k) { return localTest || k.last_test || {}; }
function coachKs(k) {
  // 去填 Key：只显示密码框 + 保存并测试，不管教练自己有没有 Key
  if (S && S.voice && S.voice.key_fill) {
    if (busy === 'save') return 'testing';
    return $('#key-in').value.trim() ? 'typing' : 'none';
  }
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
    if (p.kind === 'add_custom') {
      return `<div class="mi add" role="option" data-v="__add_custom__"><div><div class="nm">${esc(p.name)}</div><div class="ds">${esc(p.subtitle || p.hint || '')}</div></div></div>`;
    }
    const ds = p.subtitle || [p.model, p.configured ? '已配置' : '未配置', p.hint].filter(Boolean).join(' · ');
    return `<div class="mi${p.current ? ' cur' : ''}" role="option" aria-selected="${p.current}" data-v="${esc(p.id)}">${CK}<div><div class="nm">${esc(p.name)}${tagPill(p.tag, p.id === 'deepseek')}</div><div class="ds">${esc(ds)}</div></div>${p.apply_url ? `<span class="link ap" data-apply="${esc(p.id)}">去申请 ${EXT}</span>` : ''}</div>`;
  }).join('') + '<div class="ft">每家的 Key 分开保存，切换不会清掉别家的。<br>通义、Kimi 也可通过自定义接入。</div>';
  if (k.is_custom) $('#prov-menu .ft').insertAdjacentHTML('afterbegin', `现在用的是自定义「${esc(k.provider_name)}」。<br>`);
  else if (!k.in_picker) $('#prov-menu .ft').insertAdjacentHTML('afterbegin', `现在用的是 ${esc(k.provider_name)}。<br>`);
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
  $('#coach-pill').innerHTML = (s.voice && s.voice.key_fill) ? `<span class="pill mute">只填 Key · 教练仍用 ${esc(k.provider_name || '')}</span>` : pill[pk];
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

function coachPane(k) {
  if (customFormId !== null && customFormId !== undefined && document.getElementById('c-coach').dataset.pane === 'custom-form') return 'custom-form';
  if (k.is_custom) return 'custom';
  if (k.provider === 'siliconflow') return 'sf';
  return 'preset';
}

function renderCustomList(s) {
  const list = s.customs || [];
  const box = $('#custom-list');
  if (!list.length) {
    box.innerHTML = '<div class="empty">还没有自定义服务商</div><div class="add" id="btn-custom-add">＋ 添加自定义服务商</div>';
  } else {
    box.innerHTML = list.map(c => {
      const st = c.configured
        ? '<span class="pill ok tiny"><span class="dot ok" style="width:6px;height:6px"></span>已配置</span>'
        : '<span class="pill warn tiny"><span class="dot warn" style="width:6px;height:6px"></span>未配置</span>';
      return `<div class="ci${c.current ? ' cur' : ''}" data-id="${esc(c.id)}"><div><div class="nm">${esc(c.name)}</div><div class="ds">${esc(c.base_url)} · ${esc(c.model)}</div></div><div class="acts">${st}<span class="btn ghost xs" data-edit="${esc(c.id)}">编辑</span><span class="btn ghost xs danger" data-del="${esc(c.id)}">删除</span></div></div>`;
    }).join('') + '<div class="add" id="btn-custom-add">＋ 添加自定义服务商</div>';
  }
  box.querySelectorAll('.ci').forEach(row => {
    row.onclick = (e) => {
      if (e.target.closest('[data-edit],[data-del]')) return;
      pickProvider('custom:' + row.dataset.id);
    };
  });
  box.querySelectorAll('[data-edit]').forEach(b => b.onclick = (e) => { e.stopPropagation(); openCustomForm(b.dataset.edit); });
  box.querySelectorAll('[data-del]').forEach(b => b.onclick = async (e) => {
    e.stopPropagation();
    if (!confirm('删除这个自定义服务商？Key 也会一起删掉。')) return;
    const r = await api().delete_custom(b.dataset.del);
    if (!r || !r.ok) toast((r && r.msg) || '删除失败', { icon: 'alert' });
    else flashSaved();
    await refresh();
  });
  const add = $('#btn-custom-add');
  if (add) add.onclick = () => openCustomForm('');
}

function openCustomForm(id) {
  customFormId = id || '';
  const c = (S.customs || []).find(x => x.id === customFormId);
  $('#cf-name').value = c ? (c.name === '自定义接口' ? '' : c.name) : '';
  $('#cf-url').value = c ? c.base_url : '';
  $('#cf-model').value = c ? c.model : '';
  $('#cf-key').value = '';
  ['cf-err-url','cf-err-model','cf-err-key'].forEach(id => { const el = $('#'+id); el.classList.remove('on'); });
  $('#cf-res').innerHTML = '<span class="hint">填接口地址和模型 ID，粘贴 Key 后点“保存并测试”。</span>';
  $('#c-coach').dataset.pane = 'custom-form';
  $('#prov-name').textContent = customFormId ? '编辑自定义' : '＋ 自定义（OpenAI 兼容）';
  // Drop prior built-in chrome (tag / model label / 去申请) — custom model lives in the form only.
  $('#prov-tag').innerHTML = '';
  $('#prov-model').textContent = '';
  const ap0 = $('#btn-apply'); if (ap0) { ap0.innerHTML = ''; ap0.style.display = 'none'; }
}

function renderCoach(s) {
  const k = s.key, v = s.voice;
  const pane = (() => {
    // Keep form open while editing
    if ($('#c-coach').dataset.pane === 'custom-form' && customFormId !== undefined) return 'custom-form';
    if (k.is_custom) return 'custom';
    if (k.provider === 'siliconflow') return 'sf';
    return 'preset';
  })();
  if (pane !== 'custom-form') $('#c-coach').dataset.pane = pane;
  // 服务商
  const ap = $('#btn-apply');
  if (pane === 'custom-form') {
    // Keep form title from openCustomForm; never reuse prior built-in chrome.
    $('#prov-tag').innerHTML = '';
    $('#prov-model').textContent = '';
    ap.innerHTML = '';
    ap.style.display = 'none';
  } else {
    $('#prov-name').textContent = k.provider_name;
    $('#prov-tag').innerHTML = (k.in_picker || k.is_custom) ? tagPill(k.provider_tag || '', k.provider === 'deepseek') : '';
    $('#prov-model').textContent = k.model ? `模型 ${k.model}` : '';
    ap.innerHTML = `去申请 ${esc(k.provider_short)} Key ${EXT}`;
    ap.style.display = k.apply ? '' : 'none';
  }
  renderProvMenu(s);
  renderCustomList(s);
  // 模型 combobox（预设）
  const mdl = $('#mdl-in'), list = $('#mdl-list');
  if (mdl && pane !== 'custom' && pane !== 'custom-form') {
    if (document.activeElement !== mdl) mdl.value = k.model || '';
    list.innerHTML = (k.models || []).map(m => `<option value="${esc(m)}"></option>`).join('');
    const isDefault = !k.model || k.model === k.default_model;
    $('#btn-mdl-reset').style.display = isDefault ? 'none' : '';
    $('#mdl-hint').textContent = k.provider === 'siliconflow' ? '可改成平台上的任意对话模型 ID' : '可改，一般用默认即可';
  }
  // Key
  $("#key-in").placeholder = `粘贴 ${k.provider_short} 的 API Key`;
  $('#key-line').textContent = `${k.key_env}=你的Key`;
  renderCoachKs();
  renderVoice(s);
}

let jumpBack = null, jumpBackT = 0;
function kreuseHtml(info, purpose) {
  if (!info) return '';
  const name = info.provider_name || '';
  if (info.configured) {
    const jb = jumpBack === purpose;
    return `<span class="kreuse ok"><svg class="ico"><use href="#key"/></svg>复用 ${esc(name)} Key<span class="sep">·</span><span class="st"><span class="dot ok"></span>已保存</span></span>`
      + (jb ? `<span class="savedflash"><svg class="ico"><use href="#check"/></svg>Key 已保存，${purpose === 'tts' ? '语音播报' : '语音识别'}可以用了</span>`
            : `<span class="hint nowrap">要换 Key，在「AI 教练」里选${esc(name)}</span>`);
  }
  return `<span class="kreuse warn"><svg class="ico"><use href="#alert"/></svg>复用 ${esc(name)} Key<span class="sep">·</span><span class="st">还没配</span>`
    + `<span class="link go" data-fill="${esc(info.provider)}" data-purpose="${esc(purpose)}">去填 Key →</span></span>`
    + `<span class="hint nowrap">填好后这里自动变成“已保存”</span>`;
}

function renderVoiceMenu(menuEl, opts, footer) {
  menuEl.innerHTML = (opts || []).map(o => {
    const tag = o.default
      ? '<span class="pill brand tiny">默认</span>'
      : (o.tag ? `<span class="pill mute tiny">${esc(o.tag)}</span>` : '');
    const hint = o.hint || '';
    // colour the ·已保存 / ·还没配 bits
    let ds = esc(hint);
    ds = ds.replace('已保存', '<span class="dot ok"></span>已保存').replace('还没配', '<span class="dot warn"></span>还没配');
    const slow = o.slow_note ? `<span class="hint" style="margin-left:auto">${esc(o.slow_note)}</span>` : '';
    return `<div class="mi${o.sel ? ' cur' : ''}" role="option" data-v="${esc(o.id)}">${CK}<div><div class="nm">${esc(o.name)}${tag}</div><div class="ds">${ds}</div></div>${slow}</div>`;
  }).join('') + (footer ? `<div class="ft">${footer}</div>` : '');
}

function renderVoice(s) {
  const v = s.voice || {}, k = s.key || {};
  const fill = v.key_fill;
  const coach = $('#c-coach');
  coach.classList.toggle('fill-key', !!fill);
  const fromv = $('#fromv');
  if (fill) {
    fromv.classList.add('on');
    const zh = fill.provider === 'siliconflow' ? '硅基流动' : (fill.provider === 'stepfun' ? '阶跃' : fill.provider);
    const which = fill.purpose === 'tts' ? '语音播报' : '语音识别';
    const keep = k.provider_name || '原来的教练';
    $('#fromv-txt').innerHTML = `正在给<b style="color:var(--text)">${which}</b>填 ${esc(zh)} Key，教练不变。保存成功后自动回到${which}。`;
    $('#prov-name').textContent = `${zh} · 只填 Key`;
    $('#prov-tag').innerHTML = '';
    $('#coach-pill').innerHTML = `<span class="pill mute">只填 Key · 教练仍用 ${esc(keep)}</span>`;
    $("#key-in").placeholder = `粘贴 ${zh} 的 API Key`;
  } else {
    fromv.classList.remove('on');
  }

  $('#c-stt').classList.toggle('jb', jumpBack === 'stt');
  $('#c-tts').classList.toggle('jb', jumpBack === 'tts');
  // —— 识别 ——
  const whReady = !!v.whisper_ready;
  const dl = v.whisper_download || {};
  const downloading = dl.phase === 'downloading' || dl.phase === 'checking';
  const dlErr = dl.phase === 'error' || dl.phase === 'cancelled';
  const modelReady = !!v.whisper_model_ready;
  const stt = v.stt_backend || 'whisper';
  const sttOpt = (v.stt_opts || []).find(o => o.id === stt) || {};
  $('#stt-name').textContent = v.stt_zh || sttOpt.name || '—';
  $('#stt-tag').textContent = sttOpt.tag || '';
  $('#stt-tag').style.display = sttOpt.tag ? '' : 'none';
  const cloudModel = !!v.stt_model;
  $('#stt-hint').textContent = cloudModel ? '' : (v.stt_hint || (stt === 'whisper' ? '语音不出本机，模型约 150 MB' : ''));
  $('#stt-hint').hidden = cloudModel;
  $('#stt-model').textContent = v.stt_model || '';
  $('#stt-model').hidden = !cloudModel;
  renderVoiceMenu($('#stt-menu'), v.stt_opts, '教练、识别、播报可以各用一家；用到同一家就共用 Key。');

  // pill + switch
  let askPill, askDis = !!v.ask_blocked;
  if (stt === 'whisper' && downloading) {
    askPill = '<span class="spin-s"></span>下载模型中';
    $('#ask-pill').className = 'pill mute';
  } else if (stt === 'whisper' && dlErr && !modelReady) {
    askPill = '<span class="dot err"></span>模型下载失败';
    $('#ask-pill').className = 'pill err';
  } else if (stt === 'whisper' && !whReady) {
    askPill = '<span class="dot warn"></span>缺少本地识别组件';
    $('#ask-pill').className = 'pill warn';
    askDis = true;
  } else if (v.stt_key && !v.stt_key.configured) {
    askPill = '<span class="dot warn"></span>还没配 Key';
    $('#ask-pill').className = 'pill warn';
    askDis = true;
  } else if (v.ask_on) {
    askPill = '<span class="dot ok"></span>已开启';
    $('#ask-pill').className = 'pill ok';
  } else {
    askPill = '未开启';
    $('#ask-pill').className = 'pill mute';
  }
  $('#ask-pill').innerHTML = askPill;
  const swAsk = $('#sw-ask');
  swAsk.classList.toggle('on', !!v.ask_on && !askDis);
  swAsk.classList.toggle('dis', askDis);
  swAsk.setAttribute('aria-disabled', String(askDis));
  swAsk.title = askDis ? '先把下面的问题解决' : '';
  $('#ask-ico').style.color = v.ask_on ? 'var(--info)' : 'var(--text-3)';
  $('#ask-ico use').setAttribute('href', v.ask_on ? '#mic' : '#mic-off');

  // 识别模型 / Key rows
  const mv = $('#stt-model-v');
  const keyRow = $('#stt-key-row');
  if (stt === 'whisper') {
    keyRow.hidden = true;
    $('#stt-model-row').hidden = false;
    if (!whReady) {
      mv.innerHTML = `<div class="field warnf nowrap" style="width:300px"><svg class="ico" style="width:15px;height:15px"><use href="#alert"/></svg><b style="font-size:13px">缺少本地识别组件</b><span style="font-size:12px;color:var(--text-3)">· 安装包没带 Whisper</span></div>`
        + `<span class="hint" style="margin-left:auto;text-align:right;white-space:nowrap">换最新安装包即可恢复<br>或在上面改用硅基流动 / 阶跃</span>`;
    } else if (downloading) {
      const pct = dl.pct || 0;
      const mb = ((dl.bytes_done || 0) / 1048576).toFixed(0) + ' / ' + ((dl.bytes_total || 148 * 1048576) / 1048576).toFixed(0) + ' MB';
      mv.innerHTML = `<div class="dlwrap"><div class="dlbar"><i style="width:${pct}%"></i></div><div class="dlmeta"><span class="num">${pct}%</span><span>·</span><span class="num">${mb}</span><span class="hint" style="margin-left:10px">下载时可以先打字提问</span></div></div>`
        + `<span class="btn ghost sm" id="btn-dl-cancel">取消</span>`;
    } else if (dlErr || (!modelReady && v.ask_on)) {
      if (dlErr) {
        mv.innerHTML = `<div class="callout err" style="padding:8px 12px"><svg class="ico" style="width:16px;height:16px"><use href="#alert"/></svg><div><div class="t" style="font-size:13px">模型下载失败</div><div class="d" style="margin:0">检查网络后重试；这段时间可以先打字提问，或换成硅基流动 / 阶跃。</div></div><div class="acts"><span class="btn primary sm" id="btn-dl-retry"><svg class="ico" style="width:14px;height:14px"><use href="#refresh"/></svg>重试</span></div></div>`;
      } else {
        mv.innerHTML = `<span class="pill mute">未下载</span><span class="t2 nowrap">开启后下载 · 约 150 MB</span><span class="btn ghost sm" id="btn-dl-retry">现在下载</span>`;
      }
    } else if (!modelReady) {
      mv.innerHTML = `<span class="pill mute">未下载</span><span class="t2 nowrap">开启后下载 · 约 150 MB</span>`;
    } else {
      const mb = ((dl.bytes_total || 148 * 1048576) / 1048576).toFixed(0);
      mv.innerHTML = `<span class="pill ok"><span class="dot ok"></span>已下载</span><span class="t2 nowrap">${mb} MB · 离线可用</span>`;
    }
  } else {
    $('#stt-model-row').hidden = true;
    keyRow.hidden = false;
    $('#stt-key-v').innerHTML = kreuseHtml(v.stt_key, 'stt');
  }

  // —— 播报 ——
  const missTts = v.tts_available === false && (v.tts_backend || 'edge') === 'edge';
  document.documentElement.classList.toggle('st-tts-missing', missTts);
  const tts = v.tts_backend || 'edge';
  const ttsOpt = (v.tts_opts || []).find(o => o.id === tts) || {};
  $('#tts-name').textContent = v.tts_zh || ttsOpt.name || '—';
  $('#tts-tag').textContent = ttsOpt.tag || '';
  $('#tts-tag').style.display = ttsOpt.tag ? '' : 'none';
  $('#tts-hint').textContent = v.tts_hint || (tts === 'edge' ? '免费，需要联网' : '');
  $('#tts-hint').hidden = !!v.tts_model;
  $('#tts-model').textContent = v.tts_model || '';
  $('#tts-model').hidden = !v.tts_model;
  renderVoiceMenu($('#tts-menu'), v.tts_opts, '换服务商后，下面的声音列表跟着换。');

  let ttsPill, ttsDis = !!v.tts_blocked;
  if (missTts) {
    ttsPill = '<span class="dot warn"></span>缺少声音组件';
    $('#tts-pill').className = 'pill warn tts-ok';
    ttsDis = true;
  } else if (v.tts_key && !v.tts_key.configured) {
    ttsPill = '<span class="dot warn"></span>还没配 Key';
    $('#tts-pill').className = 'pill warn tts-ok';
    ttsDis = true;
  } else if (v.tts_on) {
    ttsPill = '<span class="dot ok"></span>已开启';
    $('#tts-pill').className = 'pill ok tts-ok';
  } else {
    ttsPill = '未开启';
    $('#tts-pill').className = 'pill mute tts-ok';
  }
  $('#tts-pill').innerHTML = ttsPill;
  const swT = $('#sw-tts');
  swT.classList.toggle('on', !!v.tts_on && !ttsDis);
  swT.classList.toggle('dis', ttsDis);
  swT.setAttribute('aria-disabled', String(ttsDis));
  swT.title = ttsDis ? '先把下面的问题解决' : '';

  const ttsKeyRow = $('#tts-key-row');
  if (v.tts_key) {
    ttsKeyRow.hidden = false;
    $('#tts-key-v').innerHTML = kreuseHtml(v.tts_key, 'tts');
  } else {
    ttsKeyRow.hidden = true;
  }

  // 声音 dropdown
  const voices = v.tts_voices || [];
  const voiceBlocked = !!(v.tts_key && !v.tts_key.configured);
  const ddVoice = $('#dd-voice');
  ddVoice.classList.toggle('dis', voiceBlocked);
  if (voiceBlocked) {
    $('#voice-name').innerHTML = `<span class="ph">${esc(v.tts_voice_zh || '')}</span>`;
    ddVoice.title = `配好 Key 后可选${(v.tts_key && v.tts_key.provider_name) || ''}的声音`;
  } else {
    ddVoice.title = '';
    $('#voice-name').textContent = v.tts_voice_zh || '—';
  }
  $('#voice-menu').innerHTML = voices.map(x =>
    `<div class="mi${x.id === v.tts_voice ? ' cur' : ''}" role="option" data-v="${esc(x.id)}">${CK}<div><div class="nm">${esc(x.name)}</div></div></div>`
  ).join('');
  const prevOk = !!v.preview_ok && !missTts && !voiceBlocked;
  const bp = $('#btn-preview');
  bp.classList.toggle('off', !prevOk);
  bp.setAttribute('aria-disabled', String(!prevOk));
  bp.title = prevOk ? '' : (v.preview_off_zh || '试听不可用');
  const ph = $('#preview-hint');
  if (!prevOk && v.preview_off_zh && !missTts) {
    ph.hidden = false; ph.textContent = v.preview_off_zh;
  } else { ph.hidden = true; }

  // snav warn dot: coach OR voice missing key / component / download fail
  // 识别默认关不算黄点：只在用户开过识别时把识别的问题算进来
  const voiceWarn = (v.stt_enabled && (askDis || (stt === 'whisper' && dlErr))) || ttsDis;
  const dot = $('#snav-coach-dot');
  if (dot && !fill) {
    // renderCoachKs also touches this; OR in voice warn
    if (voiceWarn && dot.style.display === 'none') {
      dot.style.display = '';
      if (!dot.className.includes('err')) dot.className = 'dot warn';
    }
  }

  if (downloading) {
    clearTimeout(dlTimer);
    dlTimer = setTimeout(async () => { try { await refresh(); } catch (_) {} }, 800);
  }
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
// A newer switch/test bumps testSeq; an older request's result is then ignored here
// (and the backend does not record it either).
async function runTest() {
  if (busy === 'save') return;
  clearTimeout(switchTimer);
  const seq = ++testSeq;
  busy = 'retest'; localTest = null; renderCoachKs();
  let timedOut = false;
  try { await withTimeout(api().test_key(), TEST_WAIT_MS); }
  catch (e) { timedOut = !!(e && e.timeout); }
  if (seq !== testSeq) return;
  busy = null; localTest = timedOut ? { ...TIMEOUT } : null;
  await refresh();
}

// 保存并测试: save first, then test (a failed test keeps the key). The input is cleared
// as soon as save_key returns, whatever the result.
async function saveKey() {
  const inp = $('#key-in');
  if (busy) return;
  if (!inp.value.trim()) { toast('先把 Key 粘贴进来', { icon: 'info' }); inp.focus(); return; }
  // 去填 Key：存那一家的 Key，不改教练服务商；成功后自动滚回语音卡
  const fill = S.voice && S.voice.key_fill;
  const pid = fill ? fill.provider : S.key.provider;
  busy = 'save'; saveErr = ''; localTest = null; renderCoachKs();
  let r;
  try { r = await withTimeout(api().save_key(pid, inp.value), TEST_WAIT_MS); }
  catch (e) { r = e && e.timeout ? { timeout: true } : { ok: false, kind: 'store', reason_zh: '没能保存，详情见日志', saved: false }; }
  inp.value = ''; setEye(false);
  busy = null;
  if (r.timeout) localTest = { ...TIMEOUT };
  else if (r.saved === false) saveErr = r.reason_zh || '没能保存，详情见日志';
  else { changing = false; flashSaved(); if (r.msg && !r.fill_only) toast(r.msg, { icon: 'alert' }); }
  await refresh();
  if (r && r.fill_only && r.ok) {
    jumpBack = r.back === 'tts' ? 'tts' : 'stt';
    clearTimeout(jumpBackT);
    jumpBackT = setTimeout(() => { jumpBack = null; refresh(); }, 4000);
    renderVoice(S);
    const c = $(jumpBack === 'tts' ? '#c-tts' : '#c-stt');
    c.scrollIntoView({ block: 'nearest', behavior: S.ui && S.ui.reduce_motion ? 'auto' : 'smooth' });
  }
  if (r.timeout && !S.key.configured) { localTest = null; saveErr = '等了 20 秒还没有回应'; renderCoachKs(); }
}

function setEye(show) {
  $('#key-in').type = show ? 'text' : 'password';
  $('#btn-eye use').setAttribute('href', show ? '#eye-off' : '#eye');
  $('#btn-eye').title = show ? '隐藏输入内容' : '显示输入内容（只在保存前可看）';
}
function resetKeyInput() { $('#key-in').value = ''; setEye(false); saveErr = ''; }

// 选中即生效：写服务商和默认模型，热重载，没有确认框。
// 换到有 Key 的一家马上显示“测试中”，停手 0.4 秒后只测最后选中的那一家。
async function pickProvider(id) {
  if (S.voice && S.voice.key_fill) return toast('正在给语音填 Key，服务商已锁定；保存后会自动回去', { icon: 'info' });
  if (busy === 'save' || customBusy) return toast('正在保存 Key，等一下再换', { icon: 'info' });
  if (id === '__add_custom__') { openCustomForm(''); return; }
  // Leaving the custom form
  if ($('#c-coach').dataset.pane === 'custom-form') { customFormId = undefined; }
  clearTimeout(switchTimer);
  const seq = ++testSeq;  // any test still out belongs to the old provider: ignore it
  busy = null;
  resetKeyInput(); changing = false; localTest = null;  // a key typed for the old provider is never saved under the new one
  const r = await api().set_provider(id);
  if (seq !== testSeq) return;  // picked again meanwhile; the newer pick renders
  if (!r || !r.ok) toast((r && r.msg) || '没能切换，详情见日志', { icon: 'alert' });
  else { flashSaved(); if (r.msg) toast(r.msg, { icon: 'alert' }); }
  const autoTest = !!(r && r.ok && r.key && r.key.configured);
  if (autoTest) busy = 'retest';  // 测试中 right away, also during the debounce
  await refresh();
  if (seq !== testSeq || !autoTest) return;
  switchTimer = setTimeout(() => { if (seq === testSeq) { busy = null; runTest(); } }, SWITCH_TEST_DELAY_MS);
}

// 删除 Key：只在“更换 Key”编辑态出现；页内确认，不用系统弹窗
function delConfirmText(k) {
  const shared = ((S.providers || []).find(p => p.id === k.provider) || {}).shares_key_with || [];
  const names = shared.map(id => ((S.providers || []).find(p => p.id === id) || {}).name).filter(Boolean);
  const both = names.length ? `${k.provider_name} 和 ${names.join('、')} 共用这一个 Key，${names.length > 1 ? '都' : '两个都'}会被删除。` : '';
  return { t: `删除 ${k.provider_name} 的 Key？`, d: `${both}删除后教练将无法回答，提醒照常工作。` };
}
function openDelDialog() {
  if (busy) return toast('正在测试，等一下再删', { icon: 'info' });
  const k = S.key, m = delConfirmText(k), dlg = $('#dlg-del');
  dlg.dataset.pid = k.provider;
  $('#dlg-del-t span').textContent = m.t;
  $('#dlg-del-d').textContent = m.d;
  dlg.hidden = false;
  setTimeout(() => $('#dlg-del-no').focus(), 0);
}
function closeDelDialog() { $('#dlg-del').hidden = true; }
async function confirmDelete() {
  const dlg = $('#dlg-del'), pid = dlg.dataset.pid;
  if (dlg.hidden) return;
  closeDelDialog();
  clearTimeout(switchTimer); testSeq++; busy = null;
  let r;
  try { r = await api().delete_key(pid); } catch (e) { r = { ok: false, msg: '没能删除，详情见日志' }; }
  if (!r || !r.ok) { toast((r && r.msg) || '没能删除，详情见日志', { icon: 'alert' }); await refresh(); return; }
  changing = false; resetKeyInput(); localTest = null;
  flashSaved();
  if (r.msg) toast(r.msg, { icon: 'alert' });
  await refresh();  // 未配置 → the input box is back
  if (!S.key.configured) setTimeout(() => $('#key-in').focus(), 0);
}

function wireProvMenu() {
  const dd = $('#dd-prov'), menu = $('#prov-menu');
  const items = () => [...menu.querySelectorAll('.mi')];
  const hov = el => { items().forEach(e => e.classList.toggle('hov', e === el)); };
  const isOpen = () => !menu.hidden;
  const close = () => { menu.hidden = true; dd.classList.remove('open'); dd.setAttribute('aria-expanded', 'false'); };
  const open = () => { if (busy === 'save') return toast('正在保存 Key，等一下再换', { icon: 'info' }); menu.hidden = false; dd.classList.add('open'); dd.setAttribute('aria-expanded', 'true'); hov(menu.querySelector('.cur') || items()[0]); };
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
  $('#btn-eye').onclick = e => { e.preventDefault(); if (inp.disabled) return toast('正在测试，测完再看', { icon: 'info' }); setEye(inp.type === 'password'); inp.focus(); };
  $('#btn-savekey').onclick = saveKey;
  $('#btn-test').onclick = runTest;
  $('#btn-change').onclick = () => {
    if (busy) return toast('正在测试，等一下再换', { icon: 'info' });
    changing = true; resetKeyInput(); renderCoachKs(); setTimeout(() => inp.focus(), 0);
  };
  $('#btn-cancel').onclick = () => { changing = false; resetKeyInput(); renderCoachKs(); };
  $('#btn-del').onclick = openDelDialog;
  $('#dlg-del-no').onclick = closeDelDialog;
  $('#dlg-del-yes').onclick = confirmDelete;
  $('#dlg-del').onmousedown = e => { if (e.target === e.currentTarget) closeDelDialog(); };
  $('#dlg-del').onkeydown = e => {
    if (e.key === 'Escape') { e.preventDefault(); closeDelDialog(); $('#btn-del').focus(); }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); document.activeElement === $('#dlg-del-yes') ? confirmDelete() : closeDelDialog(); }
    else if (e.key === 'Tab') { e.preventDefault(); (document.activeElement === $('#dlg-del-no') ? $('#dlg-del-yes') : $('#dlg-del-no')).focus(); }
  };
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
  // voice (D13 dropdowns)
  const noTts = () => toast('缺少声音组件，提醒照常显示，只是不念出来。换最新安装包即可恢复', { icon: 'alert' });
  function closeVoiceMenus() {
    ['stt-menu', 'tts-menu', 'voice-menu'].forEach(id => { const m = $('#' + id); if (m) m.hidden = true; });
    ['dd-stt', 'dd-tts', 'dd-voice'].forEach(id => { const d = $('#' + id); if (d) { d.classList.remove('open'); d.setAttribute('aria-expanded', 'false'); } });
  }
  function wireDd(ddId, menuId, onPick) {
    const dd = $('#' + ddId), menu = $('#' + menuId);
    if (!dd || !menu) return;
    dd.onclick = (e) => {
      if (dd.classList.contains('dis')) return;
      e.stopPropagation();
      const open = menu.hidden;
      closeVoiceMenus();
      if (open) { menu.hidden = false; dd.classList.add('open'); dd.setAttribute('aria-expanded', 'true'); }
    };
    menu.onclick = async (e) => {
      const mi = e.target.closest('.mi'); if (!mi || !mi.dataset.v) return;
      closeVoiceMenus();
      await onPick(mi.dataset.v);
    };
  }
  document.addEventListener('click', closeVoiceMenus);
  wireDd('dd-stt', 'stt-menu', async (id) => {
    const r = await save({ stt_backend: id });
    if (r && r.need_key) { /* UI already shows 去填 Key */ }
  });
  wireDd('dd-tts', 'tts-menu', async (id) => { await save({ tts_backend: id }); });
  wireDd('dd-voice', 'voice-menu', async (id) => {
    const r = await api().set_tts_voice(id);
    if (r && r.msg) toast(r.msg, { icon: 'alert' }); else flashSaved();
    await refresh();
  });
  $('#sw-tts').onclick = async () => {
    if ($('#sw-tts').classList.contains('dis')) {
      if (S.voice.tts_available === false && (S.voice.tts_backend || 'edge') === 'edge') return noTts();
      if (S.voice.tts_key && !S.voice.tts_key.configured) return toast('先点「去填 Key」保存 Key', { icon: 'alert' });
      return;
    }
    const r = await api().set_tts(!S.voice.tts_on);
    if (r && r.msg) toast(r.msg, { icon: 'alert' }); else flashSaved();
    await refresh();
  };
  $('#btn-preview-off').onclick = noTts;
  $('#btn-preview').onclick = async () => {
    if ($('#btn-preview').classList.contains('off')) {
      toast((S.voice && S.voice.preview_off_zh) || '试听不可用', { icon: 'info' });
      return;
    }
    const b = $('#btn-preview'); if (b.classList.contains('busy')) return;
    b.classList.add('busy');
    try { const r = await api().preview_tts(); if (!r || !r.ok) toast((r && r.msg) || '试听失败，详情见日志', { icon: 'alert' }); }
    catch (e) { toast('试听失败，详情见日志', { icon: 'alert' }); }
    finally { b.classList.remove('busy'); }
  };
  $('#sw-ask').onclick = async () => {
    if ($('#sw-ask').classList.contains('dis')) {
      if (S.voice.stt_key && !S.voice.stt_key.configured) return toast('先点「去填 Key」保存 Key', { icon: 'alert' });
      if (!S.voice.whisper_ready) return toast('缺少本地识别组件', { icon: 'info' });
      return;
    }
    const turningOn = !S.voice.ask_on;
    if (turningOn && S.voice.stt_backend === 'whisper' && S.voice.whisper_ready && !S.voice.whisper_model_ready) {
      await api().start_whisper_download();
    }
    await save({ voice_ask: turningOn });
  };
  // 去填 Key → (delegated)
  document.getElementById('p-coach').addEventListener('click', async (e) => {
    const go = e.target.closest('[data-fill]');
    if (!go) {
      const cancel = e.target.closest('#btn-dl-cancel');
      const retry = e.target.closest('#btn-dl-retry');
      if (cancel) { await api().cancel_whisper_download(); refresh(); return; }
      if (retry) { await api().start_whisper_download(); refresh(); return; }
      return;
    }
    const pid = go.dataset.fill, purpose = go.dataset.purpose || 'stt';
    const r = await api().begin_key_fill(pid, purpose);
    if (!r || !r.ok) { toast((r && r.msg) || '打不开填 Key', { icon: 'alert' }); return; }
    changing = true; // show password row
    $('#key-in').value = '';
    await refresh();
    const c = $('#c-coach');
    c.scrollIntoView({ block: 'start' });
    c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash');
    setTimeout(() => { try { $('#key-in').focus(); } catch (_) {} }, 50);
  });
  $('#btn-hotkey').onclick = () => toast('全局快捷键还在做，先点麦克风提问');
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
  setInterval(() => { if (document.querySelector('#p-adv.on')) 
// D12: model override, custom form, whisper download
$('#mdl-in').addEventListener('change', async () => {
  const r = await api().save_coach_model($('#mdl-in').value.trim());
  if (!r || !r.ok) toast((r && r.msg) || '没能保存模型', { icon: 'alert' }); else flashSaved();
  await refresh();
});
$('#btn-mdl-reset').onclick = async () => {
  const r = await api().save_coach_model('');
  if (!r || !r.ok) toast((r && r.msg) || '没能恢复默认', { icon: 'alert' }); else flashSaved();
  await refresh();
};
$('#btn-cf-cancel').onclick = () => { customFormId = undefined; $('#c-coach').dataset.pane = ''; refresh(); };
$('#cf-eye').onclick = () => {
  const inp = $('#cf-key'); const show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  $('#cf-eye use').setAttribute('href', show ? '#eye-off' : '#eye');
};
$('#btn-cf-save').onclick = async () => {
  if (customBusy) return;
  customBusy = true;
  ['cf-err-url','cf-err-model','cf-err-key'].forEach(id => $('#'+id).classList.remove('on'));
  $('#cf-res').innerHTML = '<span class="t2">正在请求自定义接口，最多等 15 秒…</span>';
  $('#btn-cf-save').classList.add('busy');
  let r;
  try {
    r = await withTimeout(api().save_custom($('#cf-name').value, $('#cf-url').value, $('#cf-model').value, $('#cf-key').value, customFormId || ''), TEST_WAIT_MS);
  } catch (e) {
    r = e && e.timeout ? { ok: false, reason_zh: '接口地址连不上 · 等了 20 秒还没有回应', field: 'url' } : { ok: false, reason_zh: '没能保存', field: '' };
  }
  customBusy = false; $('#btn-cf-save').classList.remove('busy');
  $('#cf-key').value = '';
  // inline text follows the backend: 格式不对 (validator) vs 连不上 (probe) vs Key/模型
  const errEl = { url: '#cf-err-url', model: '#cf-err-model', key: '#cf-err-key' }[r.field];
  if (errEl && !r.ok) { if (r.reason_zh) $(errEl).textContent = r.reason_zh; $(errEl).classList.add('on'); }
  if (r.ok) {
    customFormId = undefined;
    flashSaved();
    $('#cf-res').innerHTML = `<span style="display:flex;align-items:center;gap:10px"><span class="pill ok"><span class="dot ok"></span>连接正常</span><span class="t2">${esc(r.model || '')}${r.ms != null ? ' · 首个回复 <b class="num">' + (r.ms/1000).toFixed(1) + '</b> 秒' : ''}</span></span>`;
  } else {
    $('#cf-res').innerHTML = `<div class="callout err"><svg class="ico"><use href="#alert"/></svg><div><div class="t">${esc(r.reason_zh || '没连上')}</div><div class="d">提醒不受影响。</div></div></div>`;
  }
  await refresh();
  if (r.ok) $('#c-coach').dataset.pane = 'custom';
};
$('#btn-dl-cancel').onclick = async () => { await api().cancel_whisper_download(); await refresh(); };
$('#btn-dl-retry').onclick = async () => { await api().start_whisper_download(); await refresh(); };

refresh(); }, 2000);
});

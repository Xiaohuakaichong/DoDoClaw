// Saved provider records never contain API Keys. Only the unsaved input is held here.
const ProviderHub = (() => {
  const NEW = '__new__';
  let state = null, selected = null, working = false, wired = false, loadSeq = 0;
  const drafts = new Map();
  const q = id => document.getElementById(id);
  const current = () => selected === NEW
    ? { id: '', name: '自定义服务商', kind: 'custom', base_url: '', model: '', configured: false, note: '支持 OpenAI 兼容接口，可接入自己的网关、代理或本地模型服务。' }
    : (state?.providers || []).find(p => p.id === selected);
  const isDomestic = p => /^(CN|中国|国内|China)$/i.test(p.region || '');
  const initials = p => ({ siliconflow: '硅', deepseek: 'DS', dashscope: '千', kimi: 'K', moonshot: 'K', zhipu: '智', volcengine: '豆', minimax: 'M', stepfun: '阶', openai: 'O', anthropic: 'A' }[p.id] || (p.name || 'P').slice(0, 1));

  function snapshot() {
    return { name: q('hub-name').value, base_url: q('hub-url').value, model: q('hub-model').value, key: q('hub-key').value };
  }
  function isDirty() {
    const p = current(); if (!p) return false;
    const d = snapshot();
    return d.base_url !== (p.base_url || '') || d.model !== (p.model || '') || !!d.key || (p.kind === 'custom' && d.name !== (selected === NEW ? '' : p.name || ''));
  }
  function remember() {
    if (!current()) return;
    if (isDirty()) drafts.set(selected, snapshot()); else drafts.delete(selected);
  }
  function result(text, cls = '') {
    const el = q('hub-result'); el.textContent = text; el.className = 'hub-result' + (cls ? ' ' + cls : ''); el.hidden = !text;
  }
  function clearErrors() {
    ['name', 'url', 'model', 'key'].forEach(field => {
      q('hub-error-' + field).hidden = true;
      q('hub-' + field).removeAttribute('aria-invalid');
    });
    q('hub-key').closest('.hub-password').classList.remove('invalid');
  }
  function showError(field, text) {
    if (!['name', 'url', 'model', 'key'].includes(field)) return;
    const el = q('hub-error-' + field); el.textContent = text; el.hidden = false;
    q('hub-' + field).setAttribute('aria-invalid', 'true');
    if (field === 'key') q('hub-key').closest('.hub-password').classList.add('invalid');
    q('hub-' + field).focus();
  }
  function setEye(show) {
    q('hub-key').type = show ? 'text' : 'password';
    q('hub-eye').setAttribute('aria-pressed', String(show));
    q('hub-eye').setAttribute('aria-label', show ? '隐藏输入的 API Key' : '显示输入的 API Key');
    q('hub-eye').querySelector('use').setAttribute('href', show ? '#eye-off' : '#eye');
  }

  function renderList() {
    if (!state) return;
    const scrollTop = q('hub-list').scrollTop;
    const all = state.providers || [], query = q('hub-search').value.trim().toLowerCase();
    const filtered = all.filter(p => [p.name, p.id, p.base_url, p.model].join(' ').toLowerCase().includes(query));
    const groups = [
      ['国内预设', filtered.filter(p => p.kind !== 'custom' && isDomestic(p))],
      ['其他预设', filtered.filter(p => p.kind !== 'custom' && !isDomestic(p))],
      ['自定义', filtered.filter(p => p.kind === 'custom')],
    ];
    let html = groups.filter(([, providers]) => providers.length).map(([label, providers]) => `<div class="hub-group"><div class="hub-group-label">${label}<small>${providers.length}</small></div><div class="hub-group-items">${providers.map(p => `<button type="button" class="hub-item${selected === p.id ? ' selected' : ''}" data-provider="${esc(p.id)}" aria-pressed="${selected === p.id}" title="${esc(p.name)}"><span class="hub-item-logo">${esc(initials(p))}</span><span class="hub-item-text"><span class="hub-item-name">${esc(p.name)}</span><span class="hub-item-status"><span class="dot ${p.configured ? 'ok' : 'mute'}"></span>${p.configured ? '已配置 Key' : '未配置 Key'}${drafts.has(p.id) ? ' · 待保存' : ''}</span></span>${p.current || state.active_provider === p.id ? '<span class="hub-current">教练使用中</span>' : ''}</button>`).join('')}</div></div>`).join('');
    if (selected === NEW || drafts.has(NEW)) html += `<div class="hub-group"><button type="button" class="hub-item hub-new${selected === NEW ? ' selected' : ''}" data-provider="${NEW}"><span class="hub-item-logo">＋</span><span class="hub-item-text"><span class="hub-item-name">新自定义服务商</span><span class="hub-item-status">尚未保存</span></span></button></div>`;
    if (!html) html = '<div class="hub-empty">没有匹配的服务商</div>';
    q('hub-list').innerHTML = html;
    q('hub-list').scrollTop = scrollTop;
    q('hub-config-count').textContent = all.filter(p => p.configured).length;
    const active = all.find(p => p.id === state.active_provider || p.current);
    q('hub-active-name').textContent = active?.name || '未选择';
  }

  function renderActions() {
    const p = current(); if (!p) return;
    const dirty = isDirty(), fresh = selected === NEW;
    q('hub-dirty').hidden = !dirty;
    q('hub-reset-url').hidden = !p.default_base_url || q('hub-url').value === p.default_base_url;
    q('hub-reset-model').hidden = !p.default_model || q('hub-model').value === p.default_model;
    q('hub-test').disabled = working || !p.configured || fresh || dirty;
    q('hub-test').title = dirty ? '先保存修改，再测试已保存配置' : p.configured ? '会发一条很短的请求，可能产生少量费用' : '先保存 API Key';
    const active = p.current || state?.active_provider === p.id;
    q('hub-activate').disabled = working || fresh || !p.configured || dirty || !!active;
    q('hub-activate').innerHTML = active ? '<svg class="ico"><use href="#check"/></svg>教练使用中' : '用于 AI 教练<svg class="ico"><use href="#send"/></svg>';
    q('hub-activate').title = dirty ? '先保存修改，再用于 AI 教练' : !p.configured ? '先保存 API Key' : '';
    q('hub-use-title').textContent = active ? '当前 AI 教练服务商' : '供 AI 教练使用';
    q('hub-delete-key').hidden = !p.configured || fresh;
    q('hub-delete-custom').hidden = p.kind !== 'custom' || fresh;
    q('hub-save').disabled = working;
    q('hub-save-test').disabled = working;
    q('hub-add').disabled = working;
    q('hub-delete-key').disabled = working || dirty;
    q('hub-delete-key').title = dirty ? '先保存修改，再删除已保存的 Key' : '';
    q('hub-delete-custom').disabled = working;
    q('hub-apply').disabled = working;
    q('hub-eye').disabled = working;
    ['name', 'url', 'model', 'key'].forEach(id => { q('hub-' + id).disabled = working; });
    q('hub-list').querySelectorAll('button').forEach(b => { b.disabled = working; });
  }

  function renderEditor() {
    const p = current();
    q('hub-editor').hidden = !p;
    if (!p) return;
    const d = drafts.get(selected) || {};
    q('hub-provider-name').textContent = p.name || '自定义服务商';
    q('hub-logo').textContent = selected === NEW ? '+' : initials(p);
    q('hub-provider-type').textContent = p.kind === 'custom' ? '自定义 · OpenAI 兼容' : (isDomestic(p) ? '国内预设' : '预设服务商');
    q('hub-key-status').textContent = p.configured ? 'Key 已保存' : '未配置 Key';
    q('hub-key-status').className = 'pill ' + (p.configured ? 'ok' : 'warn') + ' tiny';
    q('hub-note').textContent = p.note || (p.kind === 'custom' ? '支持 OpenAI 兼容接口。请核对服务商提供的接口地址和模型 ID。' : '可直接使用预设，也可以修改接口地址和模型 ID。');
    q('hub-name-row').hidden = p.kind !== 'custom';
    q('hub-name').value = d.name ?? (selected === NEW ? '' : p.name || '');
    q('hub-url').value = d.base_url ?? p.base_url ?? '';
    q('hub-model').value = d.model ?? p.model ?? '';
    q('hub-models').innerHTML = (p.models || []).map(model => `<option value="${esc(model)}"></option>`).join('');
    q('hub-key').value = d.key || '';
    setEye(false);
    q('hub-key').placeholder = p.configured ? '留空保留现有 Key；填入可替换' : '粘贴 ' + (p.name || '服务商') + ' 的 API Key';
    q('hub-key-action').textContent = p.configured ? '已保存 · 可替换' : '待填写';
    q('hub-key-hint').textContent = p.configured ? '留空会保留现有 Key。已保存的 Key 不回显，填入新 Key 后保存可替换。' : 'Key 只保存在这台电脑上；保存后输入框会清空。';
    q('hub-apply').hidden = !p.apply_url;
    clearErrors(); result(''); renderActions();
  }

  async function load({ forceEditor = false, prefer = null } = {}) {
    const seq = ++loadSeq;
    try {
      const next = await api().provider_hub_state();
      if (seq !== loadSeq) return;
      if (!next || !Array.isArray(next.providers)) throw new Error('invalid state');
      state = next;
      const before = selected;
      if (prefer != null) selected = prefer;
      if (selected !== NEW && !state.providers.some(p => p.id === selected)) selected = state.active_provider || state.providers[0]?.id || NEW;
      q('hub-load-error').hidden = true;
      renderList();
      if (forceEditor || selected !== before || q('hub-editor').hidden) renderEditor(); else renderActions();
    } catch (_) {
      if (seq !== loadSeq) return;
      if (!state) { q('hub-editor').hidden = true; q('hub-list').innerHTML = ''; q('hub-load-error').hidden = false; }
      else result('暂时无法读取服务商配置，请稍后重试。', 'err');
    }
  }

  function revealEditor() {
    requestAnimationFrame(() => {
      const pane = q('p-providers'), editor = q('hub-editor');
      if (!pane.classList.contains('on') || editor.hidden) return;
      const bounds = pane.getBoundingClientRect(), top = editor.getBoundingClientRect().top;
      const keyBottom = q('hub-key').getBoundingClientRect().bottom;
      // Only move when needed, keeping both the provider heading and Key reachable.
      if (top < bounds.top + 8 || keyBottom > bounds.bottom - 16) editor.scrollIntoView({ block: 'start', inline: 'nearest' });
    });
  }
  function select(id) {
    if (working) return;
    remember(); selected = id; renderList(); renderEditor(); revealEditor();
  }
  async function open(id) {
    wire();
    if (working) return;
    if (!state) {
      if (id === '__add_custom__') selected = NEW;
      else if (id) selected = id;
      if (location.hash !== '#providers') location.hash = 'providers';
      await load();
    } else {
      if (id === '__add_custom__') select(NEW);
      else if (id && state.providers.some(p => p.id === id)) select(id);
      if (location.hash !== '#providers') location.hash = 'providers';
    }
    revealEditor();
    if (id === '__add_custom__') q('hub-name').focus();
  }
  function setWorking(on, testing = false) {
    working = on;
    q('hub-save-test').textContent = on && testing ? '保存并测试中…' : '保存并测试';
    renderActions();
  }
  async function updateAll(prefer) {
    if (typeof resetCoachConfigView === 'function') resetCoachConfigView();
    if (typeof refresh === 'function') await refresh();
    await load({ forceEditor: true, prefer });
  }
  function testText(t) {
    if (t.ok) return '连接正常' + (t.ms != null ? ' · 响应 ' + (t.ms / 1000).toFixed(1) + ' 秒' : '');
    return '测试未通过：' + (t.reason_zh || t.msg || '暂时没有连上，请检查地址、模型和 Key。');
  }

  async function saveProvider(test) {
    if (working || !current()) return;
    const oldId = selected, p = current(), d = snapshot();
    clearErrors(); result(test ? '正在保存并测试，测试会发送一条简短请求…' : '正在保存配置…');
    setWorking(true, test);
    try {
      const r = await api().save_provider_config(p.id, p.kind === 'custom' ? d.name.trim() : p.name, d.base_url.trim(), d.model.trim(), d.key.trim(), test);
      if (!r || !r.saved) {
        const message = r?.reason_zh || r?.msg || '保存失败，请检查后重试。';
        result(message, 'err'); showError(r?.field, message); return;
      }
      drafts.delete(oldId);
      q('hub-key').value = ''; setEye(false);
      await updateAll(r.provider_id || p.id);
      if (r.ok === false) {
        const message = r.reason_zh || r.msg || '接口配置已保存，但 Key 未能保存，请重新填写。';
        result(message, 'err'); showError(r.field, message); return;
      }
      if (test && r.test) result('配置已保存。' + testText(r.test), r.test.ok ? 'ok' : 'err');
      else result('配置已保存。' + (test ? '测试未完成，可点击“测试已保存配置”重试。' : r.configured ? '可点击“测试已保存配置”验证连接。' : '填写 API Key 后可测试连接。'), test ? 'err' : 'ok');
    } catch (_) {
      result('操作未完成，请稍后重新读取配置确认保存状态。', 'err');
    } finally { setWorking(false); }
  }

  async function testProvider() {
    const p = current(); if (working || !p || !p.configured || isDirty()) return;
    clearErrors(); result('正在测试已保存配置，测试会发送一条简短请求…'); setWorking(true);
    try { const r = await api().test_provider_config(p.id); result(testText(r || {}), r?.ok ? 'ok' : 'err'); }
    catch (_) { result('测试没有完成，请稍后重试。', 'err'); }
    finally { setWorking(false); }
  }

  async function activate() {
    const p = current(); if (working || !p?.configured || isDirty()) return;
    setWorking(true);
    try {
      const r = await api().set_provider(p.id);
      if (!r?.ok) { result(r?.msg || '未能切换 AI 教练服务商。', 'err'); return; }
      await updateAll(p.id); result('AI 教练已切换为 ' + p.name + '。', 'ok');
    } catch (_) { result('未能切换 AI 教练服务商，请稍后重试。', 'err'); }
    finally { setWorking(false); }
  }

  async function deleteKey() {
    const p = current(); if (working || !p?.configured) return;
    const shared = (p.shares_key_with || []).map(id => state.providers.find(x => x.id === id)?.name).filter(Boolean);
    const detail = shared.length ? '它与 ' + shared.join('、') + ' 共用 Key，相关配置都会受影响。' : '使用它的 AI 教练和云端语音将暂时不可用。';
    if (!confirm('删除 ' + p.name + ' 的 Key？\n' + detail + '\n接口地址和模型配置会保留。')) return;
    setWorking(true);
    try {
      const r = await api().delete_provider_key(p.id);
      if (!r?.ok) { result(r?.msg || '删除失败，请稍后重试。', 'err'); return; }
      drafts.delete(selected); await updateAll(p.id); result('Key 已删除，接口地址和模型配置已保留。');
    } catch (_) { result('删除失败，请稍后重试。', 'err'); }
    finally { setWorking(false); }
  }

  async function deleteCustom() {
    const p = current(); if (working || p?.kind !== 'custom' || selected === NEW) return;
    if (!confirm('删除自定义服务商“' + p.name + '”？\n它的接口配置和 Key 都会删除。')) return;
    setWorking(true);
    try {
      const r = await api().delete_custom(p.id.replace(/^custom:/, ''));
      if (!r?.ok) { result(r?.msg || '删除失败，请稍后重试。', 'err'); return; }
      drafts.delete(selected); selected = null; await updateAll(); result('自定义服务商已删除。');
    } catch (_) { result('删除失败，请稍后重试。', 'err'); }
    finally { setWorking(false); }
  }

  function wire() {
    if (wired) return; wired = true;
    q('hub-form').noValidate = true;
    q('hub-form').onsubmit = e => { e.preventDefault(); saveProvider(true); };
    q('hub-save').onclick = () => saveProvider(false);
    q('hub-test').onclick = testProvider;
    q('hub-activate').onclick = activate;
    q('hub-delete-key').onclick = deleteKey;
    q('hub-delete-custom').onclick = deleteCustom;
    q('hub-search').oninput = renderList;
    q('hub-retry').onclick = () => load({ forceEditor: true });
    q('hub-add').onclick = () => { q('hub-search').value = ''; select(NEW); q('hub-name').focus(); };
    q('hub-list').onclick = e => { const item = e.target.closest('[data-provider]'); if (item) select(item.dataset.provider); };
    q('hub-eye').onclick = () => setEye(q('hub-key').type === 'password');
    ['name', 'url', 'model', 'key'].forEach(id => q('hub-' + id).addEventListener('input', () => { clearErrors(); result(''); remember(); renderActions(); }));
    q('hub-reset-url').onclick = () => { q('hub-url').value = current().default_base_url || ''; remember(); renderActions(); };
    q('hub-reset-model').onclick = () => { q('hub-model').value = current().default_model || ''; remember(); renderActions(); };
    q('hub-apply').onclick = async () => {
      try { if (!(await api().open_key_page(current().id, 'key'))) toast('没能打开浏览器，请稍后重试', { icon: 'alert' }); }
      catch (_) { toast('没能打开浏览器，请稍后重试', { icon: 'alert' }); }
    };
  }

  return { wire, load, open };
})();

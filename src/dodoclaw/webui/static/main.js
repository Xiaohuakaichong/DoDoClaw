const HERO_CN = {}; // filled lazily later from hero_aliases.json (not in prototype)
let lastHero = '';
function chip(el, cls, text) { el.innerHTML = `<span class="dot ${cls}"></span>${esc(text)}`; }
function render(s) {
  applyMotion(s);
  $('#rm').classList.toggle('on', !!s.reduce_motion);
  // top chips + status cards
  const g = s.gsi;
  chip($('#chip-gsi'), g.online ? 'ok' : 'warn', g.online ? 'Dota 已连接' : '等待 Dota');
  chip($('#chip-coach'), s.coach.key_ok ? 'ok' : 'err', s.coach.key_ok ? `教练 · ${s.coach.provider}` : '教练未设置 Key');
  $('#chip-voice span').textContent = `播报 · ${s.voice.tts}`;
  $('#gsi-addr').textContent = g.addr;
  $('#st-gsi-d').textContent = g.age == null ? `还没收到数据 · 监听 ${g.addr}` : `上次推送 ${g.age} 秒前`;
  $('#st-gsi-r').textContent = g.online ? '正常' : '等待'; $('#st-gsi-r').style.color = g.online ? 'var(--ok)' : 'var(--warn)';
  $('#st-gsi .ic').style.color = g.online ? 'var(--ok)' : 'var(--warn)';
  $('#st-coach').classList.toggle('err', !s.coach.key_ok);
  $('#st-coach-d').textContent = s.coach.key_ok ? `${s.coach.provider} · ${s.coach.model}` : '没有 Key，提醒照常工作';
  $('#st-coach-r').textContent = s.coach.key_ok ? '就绪' : '去设置'; $('#st-coach-r').className = 'r' + (s.coach.key_ok ? '' : ' fix');
  $('#st-voice-d').textContent = `TTS ${s.voice.tts} · STT ${s.voice.stt}`;
  // hero banner
  const day = $('#hero-day');
  if (s.daytime === null || s.daytime === undefined) day.hidden = true; else { day.hidden = false; day.textContent = s.daytime ? '☀ 白天' : '☾ 夜晚'; }
  if (s.in_game) {
    $('#hero-label').textContent = `IN GAME · ${s.clock_mmss}${s.paused ? ' · 已暂停' : ''}`;
    $('#hero-h1').innerHTML = `${esc(s.hero_zh || s.hero || '对局中')} <em>Lv${s.level}</em>`;
    $('#hero-p').textContent = s.alive ? '小窗已经在游戏上面了。问问题按 Enter，Esc 把键盘还给游戏。' : '阵亡中，趁现在问问下一步怎么打。';
  } else {
    $('#hero-label').textContent = g.online ? `READY · ${s.game_state || '在客户端'}` : 'READY · 等待下一局';
    $('#hero-h1').innerHTML = '下一局，<em>我帮你盯着</em>';
    $('#hero-p').textContent = '进入对局后小窗会自动出现。打字或点麦克风都能提问。';
  }
  if (s.hero && s.hero !== lastHero) {
    lastHero = s.hero;
    api().icon('heroes', s.hero).then(url => {
      for (const id of ['#hero-art', '#hero-blur']) $(id).style.backgroundImage = url ? `url(${url})` : 'none';
    });
  }
  // current match card
  $('#cur-clock').textContent = s.in_game ? s.clock_mmss : '—';
  $('#cur-hero').textContent = s.hero_zh || s.hero || '还没进对局';
  if (s.hero) setIcon($('#cur-por'), 'heroes', s.hero, s.hero);
  const box = $('#cur-items'); const want = s.items.join(',');
  if (box.dataset.k !== want) {
    box.dataset.k = want; box.innerHTML = '';
    s.items.forEach((n, i) => { const d = document.createElement('div'); d.className = 'it'; box.appendChild(d); setIcon(d, 'items', n, (s.items_zh || [])[i] || '物品'); });
  }
  $('#cur-kda').textContent = s.kda.join('/');
  $('#cur-gold').textContent = s.gold;
  $('#cur-lh').textContent = s.lh.join('/');
  // answer
  const a = $('#answer');
  if (s.error) { a.className = 'answer err'; a.textContent = s.error; }
  else if (s.busy) { a.className = 'answer'; a.innerHTML = '<span style="color:var(--text-3)">思考中…</span>'; }
  else if (s.answer && s.answer.text) {
    a.className = 'answer'; a.innerHTML = `<div class="meta">你问：${esc(s.answer.q)}</div>${esc(s.answer.text)}`;
    $('#ans-meta').textContent = `${s.answer.clock} · 用时 ${(s.answer.ms / 1000).toFixed(1)}s` + (s.speaking ? ' · 播报中' : '');
  }
  $('#send').toggleAttribute('disabled', s.busy);
  // timers
  const t = $('#timers');
  if (s.timers.length) {
    t.innerHTML = s.timers.map(x => `<div class="lt"><div class="n">${esc(x.name)}<b ${x.hot ? 'style="color:var(--brand-2)"' : ''}>${mmss(x.remain)}</b></div><div class="bar"><i style="background:var(${x.color});transform:scaleX(${Math.max(0, 1 - x.remain / x.total).toFixed(3)})"></i></div></div>`).join('');
  }
}
onReady(() => {
  const send = () => { const v = $('#q').value.trim(); if (!v) return; api().ask(v, false); $('#q').value = ''; };
  $('#send').onclick = send;
  $('#q').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
  $('#mic').onclick = () => api().listen();
  $('#btn-min').onclick = () => api().minimize();
  $('#btn-close').onclick = () => api().close();
  $('#btn-ov').onclick = () => api().toggle_overlay();
  $('#rm').onclick = () => api().set_reduce_motion(!$('#rm').classList.contains('on'));
  poll(render, 1000);
});

'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const fish = JSON.parse($('fish-data').textContent);
  const memoryMode = document.documentElement.dataset.edition === 'memory';
  const memoryGame = memoryMode ? AbyssMemory.create(fish) : null;
  const byId = Object.fromEntries(fish.map(f => [f.id, f]));
  let state = null, csrf = '', inFlight = false, activeView = 'fishing', filter = 'all', fraction = 100;
  let sound = false;
  let scientific = false;
  let collectionKey = '', revealTimer, audioContext, pollTimer;
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const compact = (value, digits = 2) => {
    const n = Number(value);
    if (!Number.isFinite(n)) return '已封顶';
    if (n === 0) return '0';
    if ((scientific && n >= 10000) || n >= 1e24) return n.toExponential(digits).replace('e+', ' × 10^');
    const units = [[1e20, '垓'], [1e16, '京'], [1e12, '兆'], [1e8, '亿'], [1e4, '万']];
    for (const [size, unit] of units) if (n >= size) return (n / size).toFixed(digits).replace(/\.?0+$/, '') + ' ' + unit;
    return Math.floor(n).toLocaleString('en-US');
  };
  const diamondFormat = value => {
    const n = BigInt(value);
    if (n < 1000000000000n) return n.toLocaleString('en-US');
    return compact(Number(n));
  };
  const numberMarkup = text => text.replace(/ × 10\^(\d+)/, '<span class="power">×10<sup>$1</sup></span>');
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  function toast(message, error = false) {
    const el = document.createElement('div');
    el.className = 'toast' + (error ? ' error' : '');
    el.textContent = message;
    $('toast-stack').append(el);
    setTimeout(() => el.remove(), error ? 5500 : 3800);
  }

  function tone(event = 'catch') {
    if (!sound) return;
    try {
      audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
      audioContext.resume();
      const notes = event === 'upgrade' ? [261.63, 329.63, 392, 523.25] : event === 'exchange' ? [392, 523.25, 659.25, 783.99] : [220, 330, 440];
      notes.forEach((hz, i) => {
        const o = audioContext.createOscillator(), g = audioContext.createGain();
        const t = audioContext.currentTime + i * .085;
        o.type = 'sine'; o.frequency.value = hz; g.gain.setValueAtTime(0, t);
        g.gain.linearRampToValueAtTime(.035, t + .02); g.gain.exponentialRampToValueAtTime(.001, t + .5);
        o.connect(g).connect(audioContext.destination); o.start(t); o.stop(t + .52);
      });
    } catch (_) { /* Audio is optional; gameplay remains available. */ }
  }

  function renderSound() {
    $('sound-button').classList.toggle('muted', !sound);
    $('sound-button').setAttribute('aria-pressed', String(sound));
    $('sound-button').setAttribute('aria-label', sound ? '关闭音效' : '开启音效');
    $('sound-button').title = sound ? '关闭音效' : '开启音效';
    $('settings-sound').textContent = sound ? '已开启' : '已关闭';
  }
  function toggleSound() { sound = !sound; renderSound(); tone(); }

  async function request(path, body) {
    if (memoryMode) return memoryGame.request(path, body);
    const send = async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch('/api/' + path, {
        method: body === undefined ? 'GET' : 'POST',
        headers: body === undefined ? {} : {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
        body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal,
        credentials: 'same-origin', cache: 'no-store'
      });
      const data = await response.json();
      if (response.status === 401) window.location.assign('/login');
      if (!response.ok) throw new Error(data.error || '声呐连接中断，请稍后再试');
      return data;
    } finally { clearTimeout(timeout); }
    };
    // Cookie saves are shared by tabs. Serialize their requests where supported.
    return navigator.locks ? navigator.locks.request('abyssal-cookie-save', send) : send();
  }

  function accept(data) {
    state = data.state; csrf = data.csrf;
    $('connection-label').textContent = memoryMode ? '即玩模式 · 不保存' : '深海连接正常';
    document.querySelector('.connection').classList.remove('error');
    $('save-status').textContent = memoryMode ? '进度仅在本页有效 · 刷新即重置' : '航行数据已保存至 Cookie';
    render();
  }

  async function action(path, body, handler, minDelay = 0) {
    if (inFlight || !state) return;
    inFlight = true; render();
    try {
      const [data] = await Promise.all([request(path, body), sleep(minDelay)]);
      accept(data);
      if (handler) handler(data.result);
      else if (data.result.message) toast(data.result.message);
    } catch (error) {
      toast(error.name === 'AbortError' ? '连接超时，正在重新同步航行数据' : error.message, true);
    } finally { inFlight = false; render(); schedulePoll(); }
  }

  function schedulePoll(delay = 2500) { clearTimeout(pollTimer); pollTimer = setTimeout(sync, delay); }
  async function sync() {
    if (inFlight) { schedulePoll(1000); return; }
    inFlight = true;
    try {
      const first = !state, oldCatches = state?.catches || 0;
      const data = await request('state');
      accept(data);
      if (first && data.auto_catches > 0) toast(`欢迎回来。拖网带回了 ${data.auto_catches.toLocaleString()} 条渔获。`);
      else if (data.state.catches > oldCatches && data.state.auto && data.state.history[0]) showCatch(data.state.history[0], true);
    } catch (_) {
      $('connection-label').textContent = '连接暂时中断';
      document.querySelector('.connection').classList.add('error');
      $('save-status').textContent = '正在重连，已保存的航程不会丢失';
      if (!state) { $('cast-label').textContent = '等待服务端'; $('casting-status').textContent = '正在尝试重新连接海域…'; }
    } finally { inFlight = false; render(); schedulePoll(state?.auto ? 1500 : 5000); }
  }

  function render() {
    if (!state) return;
    const goldCapped = state.gold === state.limits.gold;
    $('gold-value').innerHTML = `${goldCapped ? '数值封顶' : numberMarkup(compact(state.gold))}<span class="unit">金币</span>`;
    $('gold-value').classList.toggle('is-large', state.gold >= 1e12);
    $('gold-value').title = state.gold.toPrecision(17);
    $('diamond-value').innerHTML = `${numberMarkup(diamondFormat(state.diamonds))}<span class="unit">钻石</span>`;
    $('diamond-value').classList.toggle('is-large', BigInt(state.diamonds) >= 1000000000000n);
    $('diamond-value').title = BigInt(state.diamonds).toLocaleString('en-US');
    $('catch-count').innerHTML = `${compact(state.catches, 1)}<span class="unit">条</span>`;
    const count = Object.keys(state.collection).length;
    $('collection-note').textContent = `已发现 ${count} / ${fish.length} 种异变`;
    $('atlas-progress').textContent = `收集进度 ${Math.round(count / fish.length * 100)}%`;
    $('atlas-count').textContent = `${count} / ${fish.length} 已发现`;
    $('gold-note').textContent = goldCapped ? '已抵达浮点数边界' : state.catches ? `累计收益 ${compact(state.total_gold)}` : '第一条鱼，第一桶金。';
    $('diamond-tag').textContent = state.exchange_unlocked ? '深海黑市已开放' : 'Lv.30 解锁兑换';
    $('level-value').textContent = String(state.level).padStart(2, '0');
    $('rank-title').textContent = state.level < 5 ? '初入深海' : state.level < 30 ? '深潜探索者' : state.level < 80 ? '深渊倾听者' : state.level < 400 ? '禁海行者' : '永夜守望者';
    $('next-unlock').textContent = state.level < 5 ? 'Lv.5 解锁自动拖网' : state.level < 30 ? 'Lv.30 解锁深海黑市' : state.level < 80 ? 'Lv.80 发现深渊回声' : `已下潜 ${state.level} 层深渊`;
    const levelCapped = state.level >= state.max_level;
    $('upgrade-cost').textContent = levelCapped ? 'MAX' : compact(state.cost);
    $('upgrade-cost').title = state.cost.toPrecision(17);
    const progress = levelCapped ? 100 : Math.min(100, state.gold / state.cost * 100);
    $('level-progress-caption').textContent = levelCapped ? '已抵达深渊尽头' : '下一级升级资金';
    $('upgrade-action-label').textContent = levelCapped ? '潜航员已满级' : '升级潜航员';
    $('level-progress').style.width = `${progress}%`;
    $('upgrade-progress-text').textContent = `${Math.floor(progress)}%`;
    $('upgrade-button').disabled = inFlight || state.gold < state.cost || state.level >= state.max_level;
    $('max-upgrade-button').disabled = $('upgrade-button').disabled;
    $('cast-button').disabled = inFlight;
    $('cast-label').textContent = inFlight && $('ocean-scene').classList.contains('casting') ? '正在收线' : '抛下鱼钩';
    $('typical-reward').textContent = state.level === 1 ? 'Lv.1 · 每条鱼 10—100 万金币' : state.typical === state.limits.gold ? `Lv.${state.level} · 单鱼收益已达上限` : `Lv.${state.level} · 基础单鱼约 ${compact(state.typical)} 金币`;
    $('auto-label').textContent = state.auto ? '拖网作业中' : '自动拖网';
    $('auto-button').classList.toggle('on', state.auto);
    $('auto-button').disabled = inFlight;
    $('auto-button').title = state.gear.net.rank ? `每 ${state.interval} 秒捕获 1 条鱼` : 'Lv.5 后在右侧购买自动拖网';
    $('auto-button').setAttribute('aria-pressed', String(state.auto));
    $('market-teaser-text').textContent = state.exchange_unlocked ? '深海黑市已开放，金币可兑换钻石。' : `再升 ${30 - state.level} 级，开启深海黑市。`;
    $('sea-name').textContent = state.level < 30 ? '暮色海沟' : state.level < 80 ? '低语裂隙' : '无光之渊';
    $('depth-value').textContent = (128 + (state.level - 1) * 84).toLocaleString('en-US');
    $('exact-gold').textContent = state.gold.toPrecision(17);
    $('exact-diamonds').textContent = BigInt(state.diamonds).toLocaleString('en-US');
    $('notation-button').textContent = scientific ? '科学计数法' : '中文单位';
    renderGear(); renderRecent(); renderMarket();
    const nextKey = JSON.stringify([state.collection, state.level, filter]);
    if (nextKey !== collectionKey) { collectionKey = nextKey; renderCollection(); }
  }

  function renderGear() {
    const descriptions = {net: state.gear.net.rank ? `每 ${state.interval}s 自动捕获${memoryMode ? ' · 本页有效' : ' · 可离线'}` : '让深海替你工作', sonar: '提高稀有异变出现权重', charm: '每级使单鱼收益 ×2'};
    $('equipment-list').innerHTML = ['net', 'sonar', 'charm'].map(key => {
      const gear = state.gear[key];
      const locked = state.level < gear.unlock, maxed = gear.rank >= gear.max;
      const canBuy = !inFlight && !locked && !maxed && (gear.currency === 'diamonds' ? BigInt(state.diamonds) >= BigInt(gear.cost) : state.gold >= gear.cost);
      return `<div class="gear-item"><div class="gear-icon">${icon(key)}</div><div class="gear-copy"><div class="gear-name">${gear.name}<span>Lv.${gear.rank}</span></div><p>${descriptions[key]}</p></div><button class="gear-buy ${locked ? 'locked' : ''}" data-gear="${key}" ${!canBuy ? 'disabled' : ''} title="${gear.name} ${gear.rank}/${gear.max}">${locked ? icon('lock') + `Lv.${gear.unlock}` : maxed ? 'MAX' : icon(gear.currency === 'diamonds' ? 'diamond' : 'coin') + numberMarkup(compact(gear.cost, 1))}</button></div>`;
    }).join('');
  }

  function card(f, full = false) {
    const discovered = !!state.collection[f.id], locked = state.level < f.unlock;
    return `<button class="fish-card ${discovered ? 'discovered' : 'undiscovered'}" data-fish="${f.id}" style="--fish-color:${f.color}" aria-label="${f.name}${discovered ? '，已发现' : '，未发现'}"><div class="card-art"><span class="card-no">NO. ${String(fish.indexOf(f) + 1).padStart(3, '0')}</span>${fishArt(f)}${!discovered ? `<span class="card-lock">${icon('lock')}</span>` : ''}</div><div class="card-info"><strong>${f.name}</strong><small>${f.latin}</small><span class="rarity-label"><i></i>${f.rarity}</span>${full ? `<p class="atlas-note">${discovered ? f.description : locked ? `Lv.${f.unlock} 后，可以在更深的水域找到它。` : '声呐已探测到踪迹。继续捕鱼以解锁档案。'}</p><span class="atlas-count-note">${discovered ? `已捕获 ${state.collection[f.id]} 条` : locked ? `Lv.${f.unlock} 解锁海域` : '尚未捕获'}</span>` : ''}</div></button>`;
  }
  function renderCollection() {
    $('preview-cards').innerHTML = fish.slice(0, 4).map(f => card(f)).join('');
    const visible = fish.filter(f => filter === 'all' || f.rarity === filter);
    $('atlas-grid').innerHTML = visible.map(f => card(f, true)).join('');
  }
  function renderRecent() {
    $('recent-count').textContent = `${state.catches.toLocaleString()} 条`;
    if (!state.history.length) {
      $('recent-list').innerHTML = `<div class="empty-catches">${icon('hook')}<p>鱼篓还空着。</p><span>试着抛下第一枚鱼钩。</span></div>`;
      return;
    }
    $('recent-list').innerHTML = state.history.slice(0, 3).map(item => {
      const f = byId[item.fish];
      return `<div class="recent-item"><div class="recent-fish-art">${fishArt(f)}</div><div class="recent-copy"><strong>${f.name}${item.new ? ' · 首次发现' : ''}</strong><span>${item.source === 'auto' ? '自动拖网' : '手动捕获'} · ${f.rarity}</span></div><span class="recent-gold">+${compact(item.gold, 1)}</span></div>`;
    }).join('');
  }

  function renderMarket() {
    const special = state.gold > state.limits.exchange_threshold;
    const spent = special ? state.gold : Math.floor(state.gold * (fraction / 100) / 1e12) * 1e12;
    $('exchange-lock').hidden = state.exchange_unlocked;
    $('special-warning').hidden = !special;
    $('exchange-spend').textContent = `${compact(spent)} 金币`;
    $('exchange-button').disabled = inFlight || !state.exchange_unlocked || spent < 1e12;
    $('exchange-button').querySelector('span').textContent = special ? '签订契约 · 兑换全部金币' : '开启随机兑换';
    $('rate-list').innerHTML = state.rates.map(r => `<div class="rate-row"><span>${icon('diamond')}${r.rate.toLocaleString('en-US')} <small>钻石</small></span><strong>${r.probability}%</strong></div>`).join('');
  }

  function navigate(view) {
    if (!['fishing', 'atlas', 'market'].includes(view)) return;
    activeView = view;
    document.querySelectorAll('.view').forEach(el => { el.hidden = el.id !== `view-${view}`; el.classList.toggle('active', !el.hidden); });
    document.querySelectorAll('.rail-nav .nav-button').forEach(el => {
      el.classList.toggle('active', el.dataset.nav === view);
      if (el.dataset.nav === view) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
    });
    const headings = {fishing: ['深海之下，万物生长。', '抛下鱼钩。带回一些不该被发现的东西。'], atlas: ['有些秘密，长着鱼的模样。', '记录你的每一次发现。深海，远比想象中陌生。'], market: ['海底的交易，从不问来处。', '带上金币，试试你的运气。']};
    $('page-title').textContent = headings[view][0]; $('page-description').textContent = headings[view][1];
    window.scrollTo({top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
  }

  function showDetails(id) {
    if (!state) return;
    const f = byId[id], discovered = !!state.collection[id];
    if (!f) return;
    $('details-content').innerHTML = `<div class="eyebrow">ABYSSAL FIELD NOTES / NO.${String(fish.indexOf(f) + 1).padStart(3, '0')}</div><div class="details-art">${fishArt(f)}</div><span class="rarity-label" style="--fish-color:${f.color}"><i></i>${f.rarity} · ${discovered ? '已发现' : '未发现'}</span><h2>${f.name}</h2><div class="details-latin">${f.latin}</div><p class="details-description">${discovered ? f.description : `声呐已记录到它的轮廓。Lv.${f.unlock} 起可捕获，完整档案将在首次捕获后解锁。`}</p><div class="details-meta"><span>体长：${discovered ? f.length : '未知'}</span><span>已捕获 ${state.collection[id] || 0} 条</span></div>`;
    $('details-dialog').showModal();
  }

  function showCatch(item, automatic = false) {
    const f = byId[item.fish];
    $('hero-fish').innerHTML = fishArt(f);
    $('reveal-name').textContent = f.name;
    $('reveal-reward').textContent = `+ ${compact(item.gold)} 金币`;
    $('catch-reveal').querySelector('.reveal-label').textContent = item.new ? '首次发现 · NEW SPECIMEN' : automatic ? '拖网带回了' : '成功捕获 · CATCH SECURED';
    $('catch-reveal').classList.add('visible');
    $('casting-status').textContent = automatic ? '拖网正在深处替你工作。' : '深海又交出了一个秘密。';
    clearTimeout(revealTimer); revealTimer = setTimeout(() => $('catch-reveal').classList.remove('visible'), 2600);
    if (item.new) toast(`异变档案已更新：${f.name}`);
    if (!automatic) tone();
  }

  async function cast() {
    if (!state || inFlight || activeView !== 'fishing' || document.querySelector('dialog[open]')) return;
    $('ocean-scene').classList.remove('casting');
    void $('ocean-scene').offsetWidth;
    $('ocean-scene').classList.add('casting');
    $('catch-reveal').classList.remove('visible');
    $('casting-status').textContent = '鱼线绷紧了，正在收线…';
    await action('catch', {}, result => showCatch(result.catch), 800);
    $('ocean-scene').classList.remove('casting');
  }

  document.addEventListener('click', event => {
    const nav = event.target.closest('[data-nav]'); if (nav) navigate(nav.dataset.nav);
    const f = event.target.closest('[data-fish]'); if (f) showDetails(f.dataset.fish);
    const gear = event.target.closest('[data-gear]'); if (gear && !gear.disabled) action('gear', {key: gear.dataset.gear}, result => { toast(result.message); tone('upgrade'); });
    const filterButton = event.target.closest('[data-filter]');
    if (filterButton) { filter = filterButton.dataset.filter; document.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('active', b === filterButton)); collectionKey = ''; render(); }
    const fractionButton = event.target.closest('[data-fraction]');
    if (fractionButton) { fraction = Number(fractionButton.dataset.fraction); document.querySelectorAll('[data-fraction]').forEach(b => b.classList.toggle('active', b === fractionButton)); if (state) renderMarket(); }
    if (event.target.closest('[data-close]')) event.target.closest('dialog').close();
  });
  document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', e => { if (e.target === dialog) { const r = dialog.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close(); } }));
  $('cast-button').addEventListener('click', cast);
  document.addEventListener('keydown', e => { if (e.code === 'Space' && !['INPUT', 'TEXTAREA', 'BUTTON'].includes(document.activeElement.tagName) && activeView === 'fishing' && !document.querySelector('dialog[open]')) { e.preventDefault(); if (!e.repeat) cast(); } });
  $('upgrade-button').addEventListener('click', () => action('upgrade', {mode: 'one'}, result => { tone('upgrade'); toast(result.message); }));
  $('max-upgrade-button').addEventListener('click', () => action('upgrade', {mode: 'max'}, result => { tone('upgrade'); toast(`连升 ${result.levels} 级，抵达 Lv.${state.level}`); }));
  $('auto-button').addEventListener('click', () => { if (!state) return; if (!state.gear.net.rank) { toast('Lv.5 后，在「深潜装备」购买自动拖网'); return; } action('auto', {enabled: !state.auto}); });
  $('exchange-button').addEventListener('click', () => action('exchange', {fraction}, result => {
    tone('exchange');
    $('exchange-result').textContent = result.special ? `契约已完成。获得 ${BigInt(result.awarded).toLocaleString()} 钻石。${result.destroyed !== '0' ? `另有 ${BigInt(result.destroyed).toLocaleString()} 钻石因超出上限被销毁。` : ''}` : `本次抽中 ${result.rate.toLocaleString()} 钻石 / 兆，获得 ${BigInt(result.awarded).toLocaleString()} 钻石。${result.destroyed !== '0' ? '超出钱包容量的部分已销毁。' : ''}`;
    toast('交易完成。海底不会留下收据。');
  }));
  $('sound-button').addEventListener('click', toggleSound); $('settings-sound').addEventListener('click', toggleSound);
  $('help-button').addEventListener('click', () => $('help-dialog').showModal());
  $('settings-button').addEventListener('click', () => $('settings-dialog').showModal());
  $('notation-button').addEventListener('click', () => { scientific = !scientific; render(); });
  $('logout-button')?.addEventListener('click', async () => {
    if (inFlight) return;
    inFlight = true; clearTimeout(pollTimer);
    try {
      const response = await fetch('/auth/logout', {method:'POST', credentials:'same-origin', headers:{'X-CSRF-Token':csrf}});
      if (!response.ok) throw new Error('无法退出，请刷新后重试');
      window.location.assign('/login');
    } catch (error) { inFlight = false; toast(error.message, true); schedulePoll(); }
  });
  $('reset-button').addEventListener('click', () => action('reset', {confirm: $('reset-confirm').value}, result => { $('settings-dialog').close(); $('reset-confirm').value = ''; collectionKey = ''; $('exchange-result').textContent = ''; $('catch-reveal').classList.remove('visible'); $('hero-fish').innerHTML = fishArt(fish[0]); render(); toast(result.message); navigate('fishing'); }));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) schedulePoll(100); });
  $('hero-fish').innerHTML = fishArt(fish[0]); $('distant-jelly').innerHTML = fishArt(fish.find(f => f.kind === 'jelly'));
  $('sea-particles').innerHTML = Array.from({length: 24}, (_, i) => `<i style="left:${(i * 43.7) % 100}%;top:${28 + (i * 23) % 70}%;width:${i % 3 === 0 ? 3 : 2}px;height:${i % 3 === 0 ? 3 : 2}px;--duration:${7 + i % 9}s;--delay:-${i * .83}s"></i>`).join('');
  if (memoryMode) {
    document.querySelector('.help-dialog ol li').textContent = 'Lv.5 · 船坞开放自动拖网，在本页打开期间工作。';
    document.querySelector('.market-fine-print').innerHTML = '1 兆 = 10¹² 金币 · 常规兑换按整兆结算<br>每次独立抽取 · 浏览器内随机计算';
    document.querySelector('.voyage-number small').textContent = '即玩航程 · 刷新即重置';
    document.querySelector('.reset-section summary').textContent = '重新开始本次航程';
  }
  renderSound(); sync();
})();

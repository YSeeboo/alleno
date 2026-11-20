import { initialState, getPart, specName, available, createSpec, sendProcessing, receiveProcessing, requirements, allocate, updateBom } from './domain.js';

let state = initialState();
let page = 'parts';
let filter = 'all';
let search = '';
let expanded = new Set(['flower']);
let toastTimer;
const main = document.querySelector('main');
const modal = document.querySelector('#modal');
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const groupFor = p => state.groups.find(g => g.id === p.group);
const colorFor = p => ({ 红色: '#c97464', 蓝色: '#7f9ba9', 黄色: '#d0b46b', 绿色: '#85a787', 白色: '#eee9db' }[p.oil] || (p.oil === '无' ? (p.plating === '银色' ? '#bfc6c6' : p.plating === '原坯' ? '#b38b69' : '#d8bc75') : '#a599b1'));
const desc = p => `${groupFor(p).name} / ${specName(p)}`;
function art(group, part, large = false) {
  const color = part ? colorFor(part) : '#d6b978';
  const stroke = part?.plating === '银色' ? '#a3afaf' : '#b2914c';
  const drawing = group.shape === 'flower'
    ? `${[0, 72, 144, 216, 288].map(angle => `<ellipse cx="24" cy="15" rx="6.5" ry="10" transform="rotate(${angle} 24 24)" fill="${color}" stroke="${stroke}" stroke-width="1.1"/>`).join('')}<circle cx="24" cy="24" r="4.7" fill="#e7d29b" stroke="${stroke}"/><circle cx="24" cy="4.7" r="2" fill="#faf7ed" stroke="${stroke}"/>`
    : `<path d="M17 35C12 23 13 8 25 7c13-1 13 15 6 18-7 4-14-3-9-10" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round"/><path d="M17 35l-3 7" fill="none" stroke="${stroke}" stroke-width="2"/><circle cx="14" cy="42" r="2.5" fill="none" stroke="${stroke}"/>`;
  return `<span class="part-art ${large ? 'large' : ''}" aria-hidden="true"><svg viewBox="0 0 48 48">${drawing}</svg></span>`;
}
const option = (value, label, selected) => `<option value="${escape(value)}" ${value === selected ? 'selected' : ''}>${escape(label)}</option>`;
const action = (name, label, attrs = '', classes = '') => `<button class="btn ${classes}" data-action="${name}" ${attrs}>${label}</button>`;
function toast(message) {
  const node = document.querySelector('#toast');
  node.textContent = message;
  node.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove('show'), 4500);
}
function pageHead(eyebrow, title, subtitle, button = '') {
  return `<div class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="subtitle">${subtitle}</p></div>${button}</div>`;
}
function noteCard() {
  return `<section class="card note-card"><div class="card-body"><span class="number-label">THE SAME INVENTORY MODEL</span><h2>不改变库存逻辑，<br>减少重复维护。</h2><div class="note-item"><b>01 / 基础款归组</b><span>材质、尺寸、单位等公共资料统一管理，列表不再被颜色铺满。</span></div><div class="note-item"><b>02 / 加工规格独立库存</b><span>每种实际用到的效果仍是独立配件。相同规格只创建一次。</span></div><div class="note-item"><b>03 / BOM 直接引用</b><span>选定具体规格，才能正确判断齐料；不同颜色不能混用。</span></div></div></section>`;
}
function quickCard() {
  return `<section class="card"><div class="card-head"><h2>建议这样体验</h2><span class="tag">3 STEPS</span></div><div class="card-body"><p class="muted" style="font-size:11px;line-height:2">① 展开小花，新建「花瓣黄色」规格。<br>② 发出 100 个金色小花点红油，收回 98 个。<br>③ 到饰品 BOM，给 48 件耳饰分配用料。</p><div class="actions" style="margin-top:17px">${action('go-process', '查看加工流转 →', '', 'small')}</div></div></section>`;
}
function stats() {
  const pending = state.orders.filter(o => o.status === 'processing');
  const missing = requirements(state).reduce((sum, r) => sum + r.shortage, 0);
  return `<div class="stats"><div class="stat"><span>基础款</span><div>${state.groups.length}<small>款</small></div><p>按基础款收起，不按颜色铺开</p></div><div class="stat"><span>独立配件记录</span><div>${state.parts.length}<small>条</small></div><p>含原坯及已创建的加工规格</p></div><div class="stat"><span>加工在途</span><div>${pending.reduce((n, o) => n + o.qty, 0)}<small>个</small></div><p>${pending.length} 张加工单待收回</p></div><div class="stat tint"><span>示例订单 · 加工件缺口</span><div>${missing}<small>个</small></div><p>只认 BOM 指定规格的库存</p></div></div>`;
}
function renderGroup(group) {
  const parts = state.parts.filter(p => p.group === group.id);
  const query = search.toLowerCase().trim();
  const groupMatch = `${group.name} ${group.code}`.toLowerCase().includes(query);
  const matches = parts.filter(p => (filter === 'all' || (filter === 'oil' && p.oil !== '无') || (filter === 'plain' && p.oil === '无')) && (groupMatch || `${p.id} ${specName(p)}`.toLowerCase().includes(query)));
  if (!matches.length) return '';
  const open = expanded.has(group.id) || Boolean(query) || filter !== 'all';
  return `<section class="card"><div class="group-head"><button class="toggle" data-action="toggle" data-group="${group.id}" aria-expanded="${open}" aria-controls="specs-${group.id}"><span class="chevron">${open ? '▾' : '▸'}</span>${art(group)}<div class="group-info"><h3>${escape(group.name)}</h3><p>${escape(group.code)} · ${escape(group.material)} · ${escape(group.size)} · 单位：${group.unit}</p></div></button><div class="group-tags"><span class="tag">${parts.length} 种规格</span></div>${action('new-spec', '＋ 加工规格', `data-group="${group.id}"`, 'small')}</div><div id="specs-${group.id}" ${open ? '' : 'hidden'}><div class="table-wrap"><table><thead><tr><th>加工规格 / 配件编号</th><th>实际在库</th><th>已分配</th><th>可用</th><th></th></tr></thead><tbody>${matches.map(p => `<tr><td><div class="spec-title"><span class="swatch" style="background:${colorFor(p)}"></span>${escape(specName(p))}</div><span class="mono">${escape(p.id)}</span></td><td><span class="stock num">${p.stock}</span> <small class="muted">个</small></td><td class="muted num">${state.allocations[p.id] || '—'}</td><td class="num ${available(state, p.id) ? 'green' : 'muted'}">${available(state, p.id)}</td><td><button class="text-button" data-action="from-part" data-part="${escape(p.id)}">发出加工</button></td></tr>`).join('')}</tbody></table></div><div class="card-foot">公共资料沿用基础款；每个规格保留独立配件 ID，不合并不同效果的库存。</div></div></section>`;
}
function renderGroups() {
  document.querySelector('#groups').innerHTML = state.groups.map(renderGroup).join('') || '<div class="card no-results">没有符合条件的配件规格</div>';
}
function partsPage() {
  main.innerHTML = `${pageHead('MATERIAL LIBRARY / 配件库', '配件与加工规格', '基础款统一管理，加工结果分别记库存。沿用现有配件模型。', action('new-spec', '＋ 新增加工规格', 'data-group="flower"', 'primary'))}<div class="notice"><span>i</span><div><strong>不用为每次加工重新建配件。</strong> 只有新效果才新增规格，已有「金色 · 花瓣红色点油」可以反复加工、反复使用。</div></div>${stats()}<div class="workspace"><section><div class="toolbar"><div class="pills"><button class="pill ${filter === 'all' ? 'active' : ''}" data-action="filter" data-filter="all">全部规格</button><button class="pill ${filter === 'plain' ? 'active' : ''}" data-action="filter" data-filter="plain">未点油</button><button class="pill ${filter === 'oil' ? 'active' : ''}" data-action="filter" data-filter="oil">已点油</button></div><input class="search" id="search" aria-label="搜索配件" placeholder="搜索配件、颜色、编号…" value="${escape(search)}"></div><div id="groups"></div></section><aside class="aside-content">${noteCard()}${quickCard()}</aside></div>`;
  renderGroups();
}
function ledger() {
  return `<section class="card"><div class="card-head"><h2>本次演示 · 库存流水</h2><span class="tag">${state.logs.length} 条</span></div><div class="card-body">${state.logs.length ? state.logs.map(log => `<div class="ledger-line"><span class="num ${log.qty > 0 ? 'green' : 'amber'}">${log.qty > 0 ? '+' : ''}${log.qty}</span><div><p>${escape(specName(getPart(state, log.partId)))}</p><small>${log.reason} · ${log.ref}</small></div></div>`).join('') : '<p class="muted tiny">还没有库存变动。发出扣原规格，收回增加目标规格。</p>'}</div></section>`;
}
function processingCard(order) {
  const source = getPart(state, order.sourceId), target = getPart(state, order.targetId);
  return `<section class="card"><div class="card-head"><div><h2>${order.id}</h2><p>${escape(groupFor(source).name)} · ${target.oil === '无' ? '电镀加工' : '点油加工'}</p></div><span class="tag ${order.status === 'processing' ? 'amber' : 'green'}">${order.status === 'processing' ? '加工中 · 待收回' : '已收回 · 已结清'}</span></div><div class="flow"><div><small>发出规格</small><strong>${escape(specName(source))}</strong><small>${order.qty} 个 · 发出时已扣库存</small></div><span>→</span><div><small>收回规格</small><strong>${escape(specName(target))}</strong><small>${order.status === 'completed' ? `${order.good} 个 · 已计入目标库存` : '收回前不计入可用库存'}</small></div></div>${order.status === 'processing' ? `<div class="card-body actions">${action('receive', '登记收回', `data-order="${order.id}"`, 'primary small')}<span class="muted tiny">先收回，再到 BOM 分配</span></div>` : `<div class="receipt"><span>合格收回 <b>${order.good} 个</b></span><span>损耗 <b>${order.loss} 个</b></span><span>待处理 <b>0 个</b></span></div>`}</section>`;
}
function processPage() {
  main.innerHTML = `${pageHead('PROCESSING / 加工流转', '从一个规格，加工成另一个规格', '发出扣原规格，收回增加目标规格。加工单可以重复，配件规格无需重复创建。', action('new-processing', '＋ 新建加工单', '', 'primary'))}<div class="notice"><span>↳</span><div><strong>示例：金色小花 → 花瓣红色点油。</strong> 发出 100 个，合格收回 98 个，明确登记损耗 2 个。收回后再统一分配。</div></div>${stats()}<div class="workspace"><section>${state.orders.length ? state.orders.map(processingCard).join('') : `<div class="card"><div class="empty">${art(state.groups[0], state.parts[2], true)}<strong style="margin-top:18px">从第一张加工单开始</strong><p>已有金色小花 200 个，订单还缺 72 个红油小花。<br>可先发出 100 个，回来后再按需分配。</p><div style="margin-top:20px">${action('new-processing', '创建示例加工单 →', '', 'primary')}</div></div></div>`}</section><aside class="aside-content">${ledger()}<section class="card note-card"><div class="card-body"><h2>演示范围</h2><p class="muted tiny" style="line-height:2">本 Demo 只展示一次结清：收回时明确确认合格数及损耗数，不把尚未收回的数量自动当损耗。<br><br>正式实现可沿用系统现有分批收回能力；这里只验证规格与库存的关系。</p></div></section></aside></div>`;
}
function bomPage() {
  const needs = requirements(state), allocated = Object.keys(state.allocations).length > 0;
  const missing = needs.reduce((sum, row) => sum + row.shortage, 0);
  main.innerHTML = `${pageHead('BILL OF MATERIALS / 饰品用料', 'BOM 直接选择加工后的配件', '无需引用加工批次，也不用额外改造用料概念。BOM 仍然关联具体配件 ID。')}<div class="notice"><span>◇</span><div><strong>用料要求固定，加工单可以不同。</strong> 只要收回的是同一个目标配件规格，就能用于这份 BOM。</div></div><section class="card"><div class="card-head"><div class="product">${art(state.groups[0], state.parts[2], true)}<div><span class="mono">SP-0018 · 示例饰品</span><h2>红花垂坠耳饰</h2><p>订单 OR-DEMO-001 · 接单后加工，收回后分配</p></div></div><div class="demand"><div><small>计划生产</small><br><strong>${state.quantity}</strong> <small>件</small></div><span class="tag ${allocated ? 'green' : missing ? 'amber' : 'green'}">${allocated ? '已分配用料' : missing ? '待加工补料' : '可分配'}</span></div></div><div class="table-wrap"><table><thead><tr><th>用料配件 / 指定加工规格</th><th>单件用量</th><th>订单需求</th><th>实际在库</th><th>已分配本单</th><th>未分配可用</th><th>缺口</th><th></th></tr></thead><tbody>${needs.map((r, index) => `<tr><td><div class="spec-title"><span class="swatch" style="background:${colorFor(r.part)}"></span>${escape(groupFor(r.part).name)} / ${escape(specName(r.part))}</div><span class="mono">${escape(r.part.id)}</span></td><td class="num">${r.need / state.quantity} 个</td><td class="num">${r.need} 个</td><td class="num">${r.part.stock}</td><td class="num green">${r.reserved || '—'}</td><td class="num">${r.available}</td><td class="num ${r.shortage ? 'red' : 'green'}">${r.shortage || '齐料'}</td><td>${index === 0 ? '<button class="text-button" data-action="edit-bom">更换规格</button>' : ''}</td></tr>`).join('')}</tbody></table></div><div class="allocation"><div><h3>${allocated ? '已为订单预留，尚未实际领料' : missing ? `还缺 ${missing} 个指定加工件` : '指定规格已齐料，可以分配'}</h3><p>${allocated ? '分配不减少实际在库，只减少未分配可用数量；实际领料不是本 Demo 的演示范围。' : '普通金色小花不能替代红油小花。先加工收回，才算组装所需物料齐备。'}</p></div><div class="actions">${allocated ? action('release', '释放本单分配') : `${missing ? action('new-processing', '去加工补料') : ''}${action('allocate', '分配本单用料', missing ? 'disabled' : '', 'primary')}`}</div></div></section><div class="workspace"><section class="card"><div class="card-head"><h2>这里保留了你现有的优势</h2></div><div class="flow"><div><strong>具体规格 = 配件 ID</strong><small>加工后仍有独立物料身份</small></div><span>→</span><div><strong>BOM 引用该 ID</strong><small>直接计算需求与库存缺口</small></div><span>→</span><div><strong>收回后统一分配</strong><small>多次加工汇入同一规格库存</small></div></div><div class="card-body muted tiny">演示编号以 DEMO 开头的记录只是虚拟配件 ID，不代表正式系统未来的编号规则。</div></section><aside>${action('go-parts', '返回配件库，查看库存变化 →', '', 'small')}</aside></div>`;
}
function render() {
  const labels = { parts: '配件管理', process: '加工流转', bom: '饰品 BOM' };
  document.querySelector('#crumb').textContent = labels[page];
  document.querySelectorAll('[data-page]').forEach(button => {
    button.classList.toggle('active', button.dataset.page === page);
    if (button.dataset.page === page) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  ({ parts: partsPage, process: processPage, bom: bomPage })[page]();
}
function go(next) { page = next; render(); window.scrollTo({ top: 0 }); }
function openModal(title, subtitle, kind, body, footer, attrs = '') {
  if (modal.open) modal.close();
  modal.innerHTML = `<form data-kind="${kind}" ${attrs}><div class="modal-head"><div><h2 id="modal-title">${title}</h2><p>${subtitle}</p></div><button type="button" class="close" data-action="close" aria-label="关闭弹窗">×</button></div><div class="modal-body">${body}<p class="error" id="form-error" role="alert"></p></div><div class="modal-footer">${footer}</div></form>`;
  modal.showModal();
}
function specValues() {
  const data = new FormData(modal.querySelector('form'));
  return Object.fromEntries(data);
}
function specPreview() {
  const values = specValues();
  const area = modal.querySelector('[name="area"]');
  area.disabled = values.oil.trim() === '无';
  area.required = !area.disabled;
  const part = { ...values, plating: values.plating.trim(), oil: values.oil.trim(), area: values.oil.trim() === '无' ? '' : (values.area || '').trim() };
  const group = state.groups.find(g => g.id === values.group);
  const exists = state.parts.some(p => p.group === part.group && p.plating === part.plating && p.oil === part.oil && p.area === part.area);
  modal.querySelector('#spec-preview').innerHTML = `<span>${exists ? '已存在相同规格' : '新规格预览'}</span><strong>${escape(group.name)} / ${escape(specName(part))}</strong><p>${exists ? '将直接复用已有配件，不会重复创建，也不会改变库存。' : '创建独立配件记录，初始库存为 0；公共资料沿用基础款。'}</p>`;
  modal.querySelector('[type="submit"]').textContent = exists ? '使用已有规格' : '确认创建规格';
}
function newSpec(groupId) {
  const group = state.groups.find(g => g.id === groupId);
  openModal('新增加工规格', '只填写差异信息，不再复制一整份配件资料。', 'spec', `<input type="hidden" name="group" value="${group.id}"><div class="inherited">${art(group)}<div><strong>${escape(group.name)}</strong><small>继承：${escape(group.material)} / ${escape(group.size)} / 单位 ${group.unit}</small></div></div><div class="form-grid"><label class="field">电镀效果<select name="plating">${['金色', '银色', '原坯'].map(x => option(x, x, '金色')).join('')}</select></label><label class="field">点油颜色<input name="oil" list="oil-colors" value="黄色" required maxlength="30" placeholder="选择或输入颜色"><datalist id="oil-colors">${['无', '红色', '蓝色', '黄色', '绿色', '白色'].map(x => option(x, x)).join('')}</datalist><small>输入「无」代表未点油</small></label><label class="field full">点油部位 / 配色部位<input name="area" value="${group.shape === 'flower' ? '花瓣' : '装饰部位'}" required maxlength="50"><small>相同颜色、不同部位是不同规格；复杂多部位配色可在正式版扩展为配色方案。</small></label></div><div id="spec-preview" class="preview" aria-live="polite"></div><p class="modal-tip">这里的“新规格”底层仍是一条配件记录，能独立记库存、被 BOM 引用。首次需要才建，以后反复使用。</p>`, `<small>不预先生成所有颜色组合</small><div class="actions"><button type="button" class="btn" data-action="close">取消</button><button class="btn primary" type="submit">确认创建规格</button></div>`);
  specPreview();
}
function refreshTargets(preferred) {
  const source = getPart(state, modal.querySelector('[name="source"]').value);
  const targets = state.parts.filter(p => p.group === source.group && p.id !== source.id);
  modal.querySelector('[name="target"]').innerHTML = targets.map(p => option(p.id, specName(p), preferred || state.bom[0].partId)).join('');
  modal.querySelector('#source-stock').textContent = `当前可用 ${available(state, source.id)} 个，已分配数量不可再次发出。`;
  modal.querySelector('[name="qty"]').max = available(state, source.id);
}
function newProcessing(sourceId) {
  const target = getPart(state, state.bom[0].partId);
  const defaultSource = state.parts.find(p => p.group === target.group && p.plating === target.plating && p.oil === '无' && p.id !== target.id);
  const source = getPart(state, sourceId || defaultSource?.id || 'PJ-DZ-00001-G');
  openModal('新建加工单', '选择发出规格和加工后要收回的规格。不会新建重复配件。', 'processing', `<div class="form-grid"><label class="field full">发出配件规格<select name="source">${state.parts.map(p => option(p.id, `${desc(p)} · 可用 ${available(state, p.id)}`, source.id)).join('')}</select><small id="source-stock"></small></label><label class="field full">收回配件规格<select name="target" required></select><small>只显示同一基础款下的其他规格；加工要求以目标规格为准。</small></label><label class="field full">本次发出数量（个）<input name="qty" type="number" min="1" step="1" value="100" required></label></div><div class="preview"><span>库存规则</span><strong>发出扣原规格 → 收回增加目标规格</strong><p>本次发出后标为加工中，尚未收回的物料不计入目标可用库存。</p></div><p class="modal-tip">目标效果不存在？先回配件库新增加工规格，再创建加工单。工厂、费用和订单关联等字段在此原型中省略。</p>`, `<small>模拟动作，不会发出实际业务请求</small><div class="actions"><button class="btn" type="button" data-action="close">取消</button><button class="btn primary" type="submit">确认发出加工</button></div>`);
  refreshTargets();
}
function receive(id) {
  const order = state.orders.find(o => o.id === id);
  openModal('登记加工收回', `${id} · ${desc(getPart(state, order.targetId))}`, 'receive', `<div class="notice"><span>i</span><div>本演示采用<strong>一次结清</strong>。未返回但仍在加工中的数量不能登记为损耗；如未全部结清，请先取消。</div></div><div class="form-grid"><label class="field full">本次合格收回（个）<input name="good" type="number" min="0" max="${order.qty}" step="1" value="${Math.max(0, order.qty - 2)}" required></label></div><div class="preview"><span>结清核对</span><strong>发出 ${order.qty} = 合格收回 <span id="good-preview"></span> + 损耗 <span id="loss-preview"></span></strong><p>合格数量增加目标规格库存，损耗只记录在加工单中。</p></div><label style="display:flex;gap:10px;align-items:flex-start;margin-top:20px;font-size:11px;color:#7d8e70"><input type="checkbox" required style="min-height:0;margin-top:3px">确认本批加工已全部结清，差额确认为实际损耗，没有尚待收回的数量。</label>`, `<small>收回后可以统一分配给订单</small><div class="actions"><button class="btn" type="button" data-action="close">取消</button><button class="btn primary" type="submit">确认收回并结清</button></div>`, `data-order="${id}"`);
  receiptPreview();
}
function receiptPreview() {
  const order = state.orders.find(o => o.id === modal.querySelector('form').dataset.order);
  const good = Number(modal.querySelector('[name="good"]').value);
  modal.querySelector('#good-preview').textContent = Number.isSafeInteger(good) && good >= 0 && good <= order.qty ? good : '—';
  modal.querySelector('#loss-preview').textContent = Number.isSafeInteger(good) && good >= 0 && good <= order.qty ? order.qty - good : '—';
}
function editBom() {
  if (Object.keys(state.allocations).length) return toast('请先释放本单分配，再修改 BOM');
  openModal('选择 BOM 用料规格', '仍然直接选配件，只是按基础款筛选加工效果。', 'bom', `<div class="inherited">${art(state.groups[0])}<div><strong>五瓣小花</strong><small>BOM 要求具体规格，而不是某次加工批次。</small></div></div><div class="form-grid"><label class="field full">加工后的配件规格<select name="partId">${state.parts.filter(p => p.group === 'flower').map(p => option(p.id, `${specName(p)} · 在库 ${p.stock} 个`, state.bom[0].partId)).join('')}</select></label><label class="field full">每件饰品用量（个）<input name="qty" type="number" min="1" step="1" value="${state.bom[0].qty}" required></label></div><p class="modal-tip">更换规格后，将按新配件 ID 重新计算 ${state.quantity} 件饰品的需求及缺口。不会修改或转换已有库存。</p>`, `<small>独立 ID，直接引用</small><div class="actions"><button class="btn" type="button" data-action="close">取消</button><button class="btn primary" type="submit">保存 BOM</button></div>`);
}

document.addEventListener('click', event => {
  const nav = event.target.closest('[data-page]');
  if (nav) return go(nav.dataset.page);
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled) return;
  const { action: name, group, part, order } = button.dataset;
  try {
    if (name === 'close') modal.close();
    if (name === 'toggle') { expanded.has(group) ? expanded.delete(group) : expanded.add(group); renderGroups(); }
    if (name === 'filter') { filter = button.dataset.filter; partsPage(); }
    if (name === 'new-spec') newSpec(group);
    if (name === 'new-processing') newProcessing();
    if (name === 'from-part') newProcessing(part);
    if (name === 'receive') receive(order);
    if (name === 'go-process') go('process');
    if (name === 'go-parts') go('parts');
    if (name === 'edit-bom') editBom();
    if (name === 'allocate') { allocate(state); render(); toast('已预留本单用料，实际在库不变，可用数量已减少'); }
    if (name === 'release') { state.allocations = {}; render(); toast('已释放本单分配，可用数量恢复'); }
  } catch (error) { toast(error.message); }
});
main.addEventListener('input', event => {
  if (event.target.id === 'search') { search = event.target.value; renderGroups(); }
});
modal.addEventListener('input', () => {
  const kind = modal.querySelector('form').dataset.kind;
  if (kind === 'spec') specPreview();
  if (kind === 'receive') receiptPreview();
  modal.querySelector('#form-error').textContent = '';
});
modal.addEventListener('change', event => {
  if (event.target.name === 'source') refreshTargets();
});
modal.addEventListener('submit', event => {
  event.preventDefault();
  const form = event.target, values = Object.fromEntries(new FormData(form));
  try {
    let message = '';
    if (form.dataset.kind === 'spec') {
      const result = createSpec(state, values);
      expanded.add(result.part.group);
      search = ''; filter = 'all'; page = 'parts';
      message = result.created ? `已创建 ${specName(result.part)}，库存为 0。公共资料无需重复填写。` : `已复用 ${result.part.id}，未重复创建配件。`;
    }
    if (form.dataset.kind === 'processing') {
      const order = sendProcessing(state, values.source, values.target, Number(values.qty));
      page = 'process'; message = `${order.id} 已发出，原规格库存已扣减 ${order.qty} 个。`;
    }
    if (form.dataset.kind === 'receive') {
      const order = receiveProcessing(state, form.dataset.order, Number(values.good));
      message = `收回 ${order.good} 个，损耗 ${order.loss} 个。目标库存已更新，可以分配。`;
    }
    if (form.dataset.kind === 'bom') {
      updateBom(state, values.partId, Number(values.qty)); message = 'BOM 已更新，已按指定规格重新计算需求。';
    }
    modal.close(); render(); toast(message);
  } catch (error) { modal.querySelector('#form-error').textContent = error.message; }
});
document.querySelector('#reset').addEventListener('click', () => {
  if (modal.open) modal.close();
  state = initialState(); page = 'parts'; filter = 'all'; search = ''; expanded = new Set(['flower']);
  render(); toast('演示已重置，未改动任何真实数据');
});
render();

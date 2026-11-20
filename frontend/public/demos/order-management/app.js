import * as D from './domain.js'
import * as V from './views.js'

let state = D.createState(), filters = { search: '', status: '', history: false, sort: 'date' }, page = 1, timer, lastFocus
const app = document.querySelector('#app'), modal = document.querySelector('#modal')
const creating = () => location.hash === '#/create'
function render() {
  page = Math.min(page, Math.max(1, Math.ceil(D.filterOrders(state.orders, filters).length / 7)))
  app.innerHTML = V.shell(creating() ? V.createPage(state.draft) : V.listPage(state, filters, page), creating())
  if (creating()) V.updateTotals(app, state.draft)
  document.body.classList.remove('menu-open')
}
function toast(message) {
  const el = document.querySelector('#toast')
  el.textContent = message; el.classList.add('visible'); clearTimeout(timer)
  timer = setTimeout(() => el.classList.remove('visible'), 2800)
}
function openDialog(title, content, footer = V.btn('返回列表', 'close')) {
  lastFocus = document.activeElement
  modal.innerHTML = `<div class="dialog-head"><h2 id="dialog-title">${V.esc(title)}</h2>${V.btn('×', 'close', 'icon-button', 'aria-label="关闭弹窗"')}</div><div class="dialog-body">${content}</div><div class="dialog-footer">${footer}</div>`
  modal.showModal()
}
function clearFilters() { filters = { search: '', status: '', history: false, sort: 'date' }; page = 1 }
document.addEventListener('click', event => {
  if (event.target.closest('.skip-link')) { event.preventDefault(); document.querySelector('#main').focus(); return }
  const button = event.target.closest('[data-action]')
  if (!button || button.disabled) return
  event.preventDefault()
  const action = button.dataset.action
  if (action === 'menu') { const open = document.body.classList.toggle('menu-open'); document.querySelector('.mobile-trigger').setAttribute('aria-expanded', String(open)); return }
  if (action === 'close') return modal.close()
  if (action === 'inspect') {
    const order = state.orders.find(o => o.id === button.dataset.id)
    if (order) openDialog('订单速览', V.inspectOrder(order))
    return
  }
  if (action === 'reset') { state = D.createState(); clearFilters(); render(); return toast('演示数据已重置') }
  if (action === 'refresh') return toast('演示列表已刷新；未请求真实接口')
  if (action === 'status') { filters.status = button.dataset.value; page = 1 }
  if (action === 'clear-filters') clearFilters()
  if (action === 'page') page = Number(button.dataset.value)
  if (action === 'previous') page = Math.max(1, page - 1)
  if (action === 'next') page += 1
  if (action === 'example') { state.draft = D.exampleDraft(); state.nextKey = 4 }
  if (action === 'empty') state.draft = D.emptyDraft()
  if (action === 'add-line') D.addLine(state, button.dataset.kind)
  if (action === 'remove-line') state.draft.lines = state.draft.lines.filter(l => String(l.key) !== button.dataset.key)
  render()
})
modal.addEventListener('close', () => { (lastFocus?.isConnected ? lastFocus : document.querySelector('#main')).focus() })
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.body.classList.contains('menu-open')) { document.body.classList.remove('menu-open'); document.querySelector('.mobile-trigger').setAttribute('aria-expanded', 'false'); document.querySelector('.mobile-trigger').focus() }
})
document.addEventListener('input', event => {
  const el = event.target
  if (el.id === 'order-search') {
    const position = el.selectionStart
    filters.search = el.value; page = 1; render()
    const search = document.querySelector('#order-search'); search.focus(); search.setSelectionRange(position, position)
    return
  }
  if (!creating()) return
  if (el.name === 'customer') state.draft.customer = el.value
  if (el.name === 'date') state.draft.date = el.value
  if (el.name === 'barcode') state.draft.barcode = el.checked
  const key = el.closest('[data-key]')?.dataset.key, line = state.draft.lines.find(l => String(l.key) === key)
  if (line && ['quantity', 'price', 'remarks'].includes(el.dataset.field)) line[el.dataset.field] = el.value
  V.updateTotals(app, state.draft)
  const error = document.querySelector('#form-error'); if (error) error.textContent = ''
})
document.addEventListener('change', event => {
  const el = event.target
  if (el.id === 'history-filter') { filters.history = el.checked; page = 1; render() }
  if (el.id === 'sort') { filters.sort = el.value; page = 1; render() }
  if (el.dataset.field === 'product') {
    const line = state.draft.lines.find(l => String(l.key) === el.closest('[data-key]').dataset.key)
    D.selectProduct(line, el.value); render()
    app.querySelector(`[data-key="${line.key}"] select`)?.focus()
  }
})
document.addEventListener('submit', event => {
  event.preventDefault()
  if (event.target.id !== 'create-form') return
  try {
    const record = D.createDemoOrder(state)
    clearFilters(); history.replaceState(null, '', '#/orders'); render()
    openDialog('演示订单已创建', `<div class="success-mark">✓</div><h3 class="success-title">${V.esc(record.id)}</h3><p class="success-copy">${V.esc(record.customer)} · ${record.items} 项商品<br>已加入当前演示列表，状态为「待生产」。</p><p class="alert">仅保存在当前页面内存中，刷新即重置。没有创建真实订单，也没有调整库存或生产。</p>`, V.btn('查看演示订单', 'inspect', 'primary', `data-id="${record.id}"`) + V.btn('返回列表', 'close'))
  } catch (error) { const el = document.querySelector('#form-error'); el.textContent = error.message; el.focus() }
})
window.addEventListener('hashchange', () => { if (modal.open) modal.close(); render(); document.querySelector('#main').focus() })
render()

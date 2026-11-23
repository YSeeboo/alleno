import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { h, ref } from 'vue'

const source = readFileSync(new URL('../src/views/handcraft/HandcraftDetail.vue', import.meta.url), 'utf8')
const renderer = source.slice(source.indexOf('const renderJewelryOrderLinkCell ='), source.indexOf('const partStatusLabel ='))
const NButton = { name: 'NButton' }
function setup(links = [], archived = false) {
  const navigation = [], unlinked = [], modals = [], jewelryItemOrderLinks = ref({ 7: links })
  const render = new Function('h', 'NButton', 'jewelryItemOrderLinks', 'order', 'router', 'openJewelryLinkModal', 'doUnlinkJewelryItem',
    `${renderer}; return renderJewelryOrderLinkCell`)(h, NButton, jewelryItemOrderLinks, ref({ archived_at: archived ? '2026-01-01' : null }),
    { push: location => navigation.push(location) }, row => modals.push(row), (...args) => unlinked.push(args))
  return { render, navigation, unlinked, modals, jewelryItemOrderLinks }
}
function buttons(node) {
  if (!node) return []
  if (node.type === NButton) return [node]
  return Array.isArray(node.children) ? node.children.flatMap(buttons) : []
}
const text = button => button.children.default()

test('unassociated output offers association; confirmed quantity links show order numbers instead', () => {
  const ctx = setup()
  assert.equal(text(ctx.render({ id: 7 })), '关联订单')
  ctx.jewelryItemOrderLinks.value[7] = [{ order_id: 'OR-0015', quantity_managed: true, link_id: null }]
  const links = buttons(ctx.render({ id: 7 }))
  assert.deepEqual(links.map(text), ['OR-0015'])
  links[0].props.onClick()
  assert.deepEqual(ctx.navigation, [{ path: '/orders/OR-0015/production', hash: '#handcraft-production' }])
  assert.deepEqual(ctx.unlinked, [])
  assert.deepEqual(ctx.modals, [])
})

test('every linked customer order navigates independently with URL-safe IDs', () => {
  const ctx = setup([{ order_id: 'OR/A #1', quantity_managed: true }, { order_id: 'OR-B', quantity_managed: true }])
  const links = buttons(ctx.render({ id: 7 }))
  assert.deepEqual(links.map(text), ['OR/A #1', 'OR-B'])
  links.forEach(link => link.props.onClick())
  assert.deepEqual(ctx.navigation.map(link => link.path), ['/orders/OR%2FA%20%231/production', '/orders/OR-B/production'])
  assert.ok(ctx.navigation.every(link => link.hash === '#handcraft-production'))
})

test('legacy links remain navigable and unlinkable; quantity allocations never call legacy unlink', () => {
  const legacy = { order_id: 'OR-OLD', link_id: 8 }
  const ctx = setup([legacy])
  const links = buttons(ctx.render({ id: 7 }))
  assert.deepEqual(links.map(text), ['OR-OLD', '×', '+'])
  links[1].props.onClick()
  assert.deepEqual(ctx.unlinked, [[7, legacy]])
  const mixed = setup([legacy, { order_id: 'OR-NEW', quantity_managed: true, link_id: null }])
  assert.deepEqual(buttons(mixed.render({ id: 7 })).map(text), ['OR-OLD', '×', 'OR-NEW'])
})

test('archived output order numbers stay clickable without edit or unlink buttons', () => {
  const ctx = setup([{ order_id: 'OR-0015', quantity_managed: true }], true)
  const links = buttons(ctx.render({ id: 7 }))
  assert.deepEqual(links.map(text), ['OR-0015'])
  links[0].props.onClick()
  assert.equal(ctx.navigation[0].hash, '#handcraft-production')
  assert.equal(setup([], true).render({ id: 7 }), '—')
})

test('the real output column loads the augmented API and reloads it after batch confirmation', async () => {
  const loader = source.slice(source.indexOf('const loadJewelryItemOrderLinks ='), source.indexOf('const openLinkModal ='))
  const links = ref({}), replies = [[{ order_id: 'OR-0015', quantity_managed: true }], []], calls = []
  const load = new Function('jewelryItemOrderLinks', 'jewelryItems', 'route', 'getHandcraftJewelryOrders',
    `${loader}; return loadJewelryItemOrderLinks`)(links, ref([{ id: 7 }, { id: 9 }]), { params: { id: 'HC-A' } },
    async (...args) => { calls.push(args); return { data: replies.shift() } })
  await load()
  assert.deepEqual(calls, [['HC-A', 7], ['HC-A', 9]])
  assert.deepEqual(links.value[7], [{ order_id: 'OR-0015', quantity_managed: true }])
  assert.deepEqual(links.value[9], [])
  const saved = source.slice(source.indexOf('const onProductionLinked ='), source.indexOf('const doUnlinkPartItem ='))
  assert.match(saved, /loadJewelryItemOrderLinks\(\)/)
})

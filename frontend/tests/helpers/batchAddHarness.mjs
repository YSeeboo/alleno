import { readFile } from 'node:fs/promises'
import { parse, compileScript } from '@vue/compiler-sfc'
import { reactive } from 'vue'

const url = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
const runtime = url(`
  export { ref, computed } from ${JSON.stringify(import.meta.resolve('vue'))};
  export const onMounted = fn => globalThis.__batchTest.mounted.push(fn);
  export const onBeforeUnmount = fn => globalThis.__batchTest.cleanup.push(fn);
`)
const router = url('export const onBeforeRouteLeave = fn => globalThis.__batchTest.guards.push(fn); export const onBeforeRouteUpdate = onBeforeRouteLeave;')
const source = await readFile(new URL('../../src/components/BatchAddDialog.vue', import.meta.url), 'utf8')
const compiled = compileScript(parse(source).descriptor, { id: 'batch-test' }).content
  .replace(/from ['"]vue['"]/g, `from ${JSON.stringify(runtime)}`)
  .replace(/from ['"]vue-router['"]/g, `from ${JSON.stringify(router)}`)
  .replace(/import \{ ([^}]+) \} from ['"]naive-ui['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = ${['useMessage', 'useDialog'].includes(n.trim()) ? `() => globalThis.__batchTest.${n.trim()}` : '{}'}`).join(', ')}`)
  .replace(/import \{ ([^}]+) \} from ['"]@\/api\/[^'"]+['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = (...args) => globalThis.__batchTest.api.${n.trim()}(...args)`).join(', ')}`)
  .replace(/from ['"]@\/utils\/batchAdd['"]/g, `from ${JSON.stringify(new URL('../../src/utils/batchAdd.js', import.meta.url).href)}`)
  .replace(/import \{ ([^}]+) \} from ['"]@\/utils\/ui['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = value => value`).join(', ')}`)
  .replace(/import (\w+) from ['"][^'"]+\.vue['"]/g, 'const $1 = {}')
const Component = (await import(url(compiled))).default

export const response = data => Promise.resolve({ data })
export const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
export const part = { id: 'P', key: 'part:P', kind: 'part', name: '链条', unit: '米', is_composite: true, wholesale_price: '0.1234567' }
export const jewelry = { id: 'J', key: 'jewelry:J', kind: 'jewelry', name: '耳饰', unit: '对', status: 'active', wholesale_price: '1.1234567' }
export const colors = [{ code: 'G', label: '金色', method: '金', common: true }, { code: 'S', label: '白K', method: '白K', common: true }, { code: 'SV', label: '银色', method: '银', common: false }]

export function setupBatch(props = {}, overrides = {}) {
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} }
  const calls = [], events = [], notices = [], confirmations = []
  const state = {
    mounted: [], cleanup: [], guards: [],
    useMessage: Object.fromEntries(['warning', 'success', 'error'].map(n => [n, text => notices.push([n, text])])),
    useDialog: { warning: options => confirmations.push(options) },
    api: {
      loadBatchCatalog: async () => ({ products: [part, jewelry], colors }),
      getPart: () => response({ unit: '米' }),
      findOrCreateVariant: (id, { color_code }) => response({ part: { id: `${id}-${color_code}`, name: color_code } }),
      createPartVariant: (id, { color_code }) => response({ id: `${id}-${color_code}`, name: color_code }),
      saveBatchRow: async (...args) => { calls.push(args); return { data: {} } }, ...overrides,
    },
  }
  globalThis.__batchTest = state
  const values = reactive({ scene: 'material', entityId: 'HC-1', allowed: true, externalBusy: false, existingPartIds: [], refresh: async () => true, ...props })
  const ctx = Component.setup(values, { expose() {}, emit: (...args) => events.push(args) })
  return { ctx, props: values, calls, events, notices, confirmations, state }
}

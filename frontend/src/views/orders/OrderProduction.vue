<template>
  <div class="fulfillment-page order-workspace">
    <OrderWorkspaceHeader :order-id="String(route.params.id)" :customer-name="data?.customer_name" :status="order?.status" :created-at="order?.created_at" active="production"><n-button :loading="loading" :disabled="saving" @click="load">刷新并核对</n-button></OrderWorkspaceHeader>
    <n-alert type="info" :bordered="false" class="wf-notice">
      确认关联手工或电镀后，订单自动进入「生产中」，无需手动开始。生产安排不是预留库存、实物归属或客户出货；订单须全部明细足量出货后才完成。现有成品库存可以独立出货，无需补建生产关联。
    </n-alert>
    <n-spin :show="loading">
      <n-alert v-if="loadError" type="error">{{ loadError }}，请刷新后重试。</n-alert>
      <template v-if="data && !loadError">
        <OrderSection title="本单生产需求" :count="`${data.lines.length} 项`">
          <p class="wf-section-description">生产计划与已预留、已出货分别核算；同款重复行保留独立身份。</p>
          <div class="wf-table-wrap"><n-table :bordered="false" class="wf-table"><thead><tr><th>产品 / 客户货号</th><th>订购</th><th>生产安排</th><th>旧记录核对</th><th>操作</th></tr></thead><tbody>
            <tr v-for="line in data.lines" :key="line.id">
              <td><ProductCell :line="line" /></td><td>{{ line.quantity }} {{ line.unit }}</td>
              <td class="wf-green"><strong>{{ line.allocated }}</strong><small class="wf-subtext">计划数量，不代表实收</small></td>
              <td><n-tag size="small" :bordered="false" :type="line.legacy_claim ? 'warning' : 'default'">{{ line.legacy_claim ? '旧关联／批次待核对' : '无旧归属冲突' }}</n-tag></td>
              <td><n-button v-if="data.editable && !line.legacy_claim && Number(line.allocated) < line.quantity && auth.hasPermission('handcraft')" text type="primary" :disabled="loading || saving" @click="creatingLine = line">＋ 安排制作</n-button><span v-else class="wf-muted">{{ line.legacy_claim ? '先核对旧归属' : !data.editable ? '只读' : Number(line.allocated) >= line.quantity ? '已足额安排' : '需手工权限' }}</span></td>
            </tr>
          </tbody></n-table></div>
        </OrderSection>
        <OrderSection title="配件备料需求" :count="`${data.materials?.length || 0} 项`">
          <p class="wf-section-description">按具体订单商品行的 BOM 计算，不扣减公共库存；配件制作不代表最终商品完成或客户出货。无需手动生成配件清单。</p>
          <n-empty v-if="!data.materials?.length" description="暂无商品 BOM 配件需求" />
          <div v-else class="wf-table-wrap"><n-table :bordered="false" class="wf-table"><thead><tr><th>用于商品 / 客户货号</th><th>所需配件</th><th>理论需求</th><th>已安排</th><th>核对</th></tr></thead><tbody>
            <tr v-for="line in data.materials" :key="line.id"><td>{{ line.parent_product_name }} · {{ line.customer_code || '未填货号' }}<small class="wf-subtext">订单明细 #{{ line.order_item_id }}</small></td><td><ProductCell :line="line" /></td><td>{{ line.quantity }} {{ line.unit }}</td><td>{{ line.allocated }}</td><td><span v-if="line.demand_changed" class="warning">BOM／订购量已变化，原需求 {{ line.snapshot_quantity }}；请重新核对安排</span><span v-else>{{ line.legacy_claim ? '旧归属待核对' : '无冲突' }}</span></td></tr>
          </tbody></n-table></div>
        </OrderSection>
        <OrderSection v-for="type in ['handcraft', 'plating']" :key="type" :id="`${type}-production`" tabindex="-1" class="production-arrangement" :title="type === 'handcraft' ? '手工生产安排' : '电镀生产安排'">
          <template v-if="type === 'handcraft'" #header-extra>
            <n-button v-if="data.editable" size="small" type="primary" secondary :disabled="loading || saving" @click="openLinker">订单关联</n-button>
          </template>
          <p class="wf-section-description">{{ type === 'handcraft' ? '只展示已确认关联本单的手工产出；通过「订单关联」选择已有手工单，商品制作／配件备料份额同步计入客户分拣' : '匹配订单商品及 BOM 配件备料，按收回目标而不是原色投入匹配' }}</p>
          <n-empty v-if="!visibleSources(type).length" :description="type === 'handcraft' ? '暂无已关联的手工单，可从右上角「订单关联」选择已有手工单' : '暂无匹配商品或 BOM 配件的电镀产出'" class="wf-empty" />
          <div v-else class="wf-table-wrap"><n-table :bordered="false" class="wf-table"><thead><tr><th>加工单 / 商家 / 关联</th><th>目标产出</th><th>阶段</th><th>整条计划 / 实收</th><th>本单安排</th><th>其他客户安排</th><th>公共备库存</th><th>操作</th></tr></thead><tbody>
            <tr v-for="source in visibleSources(type)" :key="source.source_item_id" class="source-card"><td><n-button text type="primary" @click="openSource(source)">{{ source.production_order_id }}</n-button><small class="wf-subtext">{{ source.supplier_name }}</small><n-tag size="small" :bordered="false" :type="source.legacy_claim ? 'warning' : ownQuantity(source, data.order_id) ? 'success' : 'default'">{{ source.legacy_claim ? '旧归属待核对' : ownQuantity(source, data.order_id) ? '已关联本单' : '候选，未关联本单' }}</n-tag></td><td><ProductCell :line="{ ...source, id: source.source_item_id }" /><small v-if="type === 'plating'" class="wf-subtext">投入 {{ source.input_part_id }} → 目标 {{ source.product_id }}</small></td><td><n-tag size="small" :bordered="false">{{ source.archived ? '历史归档' : { pending: '待发出', processing: '加工中', completed: '已结清' }[source.status] || source.status }}</n-tag></td><td>{{ source.planned }} {{ source.unit }}<small class="wf-subtext">实收 {{ source.received }} / 损耗 {{ source.loss }}</small><small v-if="source.risk" class="wf-subtext wf-amber">存在损耗，需核对交付缺口</small></td><td class="wf-green"><strong>{{ ownQuantity(source, data.order_id) }}</strong></td><td>{{ Number(source.allocated) - ownQuantity(source, data.order_id) }}<small class="wf-subtext">只读，不在本单修改</small></td><td>{{ source.public_unallocated ?? '待核对' }}</td><td><span v-if="source.legacy_claim" class="wf-muted">先核对旧归属</span><n-button v-else-if="data.editable && !source.archived && ['pending', 'processing'].includes(source.status)" text type="primary" @click="edit(source)">{{ ownQuantity(source, data.order_id) ? '调整本单分配' : '分配给本单' }}</n-button><span v-else class="wf-muted">只读追溯</span><small v-if="source.unit_mismatch" class="wf-subtext wf-amber">单位不一致，不自动换算</small></td></tr>
          </tbody></n-table></div>
        </OrderSection>
        <OrderMaterials :order-id="data.order_id" :lines="data.lines" :editable="data.editable" accent-actions />
      </template>
    </n-spin>
    <n-modal v-model:show="showEditor" preset="card" :title="linking ? '订单关联' : '调整本单生产数量'" :mask-closable="!saving" :closable="!saving" :close-on-esc="!saving" :style="{ width: `min(${linking ? 940 : 700}px, calc(100vw - 24px))` }">
      <template v-if="linking">
        <n-alert type="info" :bordered="false">点击右侧「分配给本单」，填写数量后确认。确认前不会建立关联；客户分拣同步占用相同份额，不增加整单产出数量。</n-alert>
        <div class="link-toolbar">
          <strong>已有手工单 <small>{{ linkGroups.length }} 单 · 单号倒序</small></strong>
          <div class="link-filters">
            <n-select v-model:value="linkSupplier" :options="linkSupplierOptions" filterable clearable :disabled="saving" placeholder="全部手工商家" :input-props="{ 'aria-label': '筛选手工商家' }" />
            <n-input v-model:value="linkSearch" clearable :disabled="saving" placeholder="搜索单号、商家或商品" :input-props="{ 'aria-label': '搜索已有手工单' }" />
          </div>
        </div>
        <n-empty v-if="!linkSources.length" description="暂无匹配本单商品的可关联手工单，可先安排制作" class="link-empty" />
        <n-empty v-else-if="!linkGroups.length" description="没有找到匹配的手工单，请更换商家或关键词" class="link-empty" />
        <div v-else class="link-list" aria-label="已有手工单列表">
          <section v-for="group in linkGroups" :key="group.id" class="link-order">
            <header class="link-order-heading"><strong>{{ group.id }}</strong><span>{{ group.supplier || '未填写商家' }}</span></header>
            <div v-for="source in group.sources" :key="source.source_item_id" class="link-output" :class="{ 'is-selected': selected?.source_item_id === source.source_item_id }">
              <div class="link-output-info">
                <ProductCell :line="{ ...source, id: source.source_item_id }" />
                <div class="link-output-stats"><n-tag size="small" :bordered="false">{{ source.status === 'pending' ? '待发出' : '加工中' }}</n-tag><span>计划 <b>{{ source.planned }}</b> {{ source.unit }}</span><span>未分配 <b>{{ source.public_unallocated ?? '待核对' }}</b> {{ source.unit }}</span><span>本单已分配 <b>{{ ownQuantity(source, data.order_id) }}</b> {{ source.unit }}</span></div>
                <small v-if="linkBlockedReason(source)" class="warning">{{ linkBlockedReason(source) }}</small>
              </div>
              <n-button size="small" type="primary" secondary :disabled="!!linkBlockedReason(source) || saving || loading || selected?.source_item_id === source.source_item_id" :aria-label="`${source.production_order_id} 明细 ${source.source_item_id} ${ownQuantity(source, data.order_id) ? '调整本单分配' : '分配给本单'}`" @click="selectLinkOutput(source.source_item_id)">{{ selected?.source_item_id === source.source_item_id ? '已选择' : ownQuantity(source, data.order_id) ? '调整本单分配' : '分配给本单' }}</n-button>
            </div>
          </section>
        </div>
      </template>
      <div v-if="selected" ref="allocationEditor" class="allocation-editor" aria-label="本单分配数量">
        <h3 v-if="linking">填写本单分配数量</h3>
        <n-alert type="info" :bordered="false">仅保存 {{ data.order_id }} 的份额，不改其他客户。填 0 取消安排，不退料、不回库、不影响实收。</n-alert>
        <p>{{ selected.production_order_id }} · {{ selected.product_name }} · 产出明细 #{{ selected.source_item_id }} · 整批计划 {{ selected.planned }} {{ selected.unit }}</p>
        <div v-for="line in matchingLines(demandLines, selected)" :key="line.id" class="editor-line">
          <label :for="`allocation-${line.id}`">{{ line.material_part_id ? '配件备料 · ' + line.parent_product_name : '商品制作 · ' + line.product_name }} · {{ line.customer_code || '未填货号' }} · 明细 #{{ line.order_item_id || line.id }}<br><small>需求 {{ line.quantity }} · 旧关联 {{ line.legacy_claim ? '待核对' : '无' }}</small><br v-if="line.demand_changed"><small v-if="line.demand_changed" class="warning">BOM／订购量已变化，确认将采用当前需求；填 0 可取消原份额。</small></label>
          <n-input-number v-model:value="quantities[line.id]" :input-props="{ id: `allocation-${line.id}`, 'aria-label': `明细 ${line.id} 的本单安排数量` }" :min="0" :max="Math.max(Number(line.quantity), quantities[line.id] || 0)" :precision="line.material_part_id && selected.source_type === 'plating' ? 4 : 0" :disabled="saving || line.legacy_claim" style="max-width: 170px;" />
        </div>
      </div>
      <p v-else-if="linking" class="link-hint">请从上方列表选择要分配给本单的产出。</p>
      <p v-if="saveError" role="alert" class="warning">{{ saveError }}</p>
      <n-space justify="end"><n-button :disabled="saving" @click="showEditor = false">返回</n-button><n-button type="primary" :disabled="!selected || loading || !data?.editable || (linking && !!linkBlockedReason(selected))" :loading="saving" @click="save">{{ linking ? '确认关联并分配' : '保存本单安排' }}</n-button></n-space>
    </n-modal>
    <OrderHandcraftDialog v-if="creatingLine" :order-id="data.order_id" :line="creatingLine" @close="creatingLine = null" @saved="created" />
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NEmpty, NInput, NInputNumber, NModal, NSelect, NSpace, NSpin, NTable, NTag, useMessage } from 'naive-ui'
import OrderWorkspaceHeader from '@/components/fulfillment/OrderWorkspaceHeader.vue'
import OrderSection from '@/components/fulfillment/OrderSection.vue'
import { getOrder } from '@/api/orders'
import ProductCell from '@/components/fulfillment/ProductCell.vue'
import OrderHandcraftDialog from '@/components/fulfillment/OrderHandcraftDialog.vue'
import OrderMaterials from '@/components/fulfillment/OrderMaterials.vue'
import { useAuthStore } from '@/stores/auth'
import { getOrderProduction, replaceOrderProduction } from '@/api/productionAllocation'
import { matchingLines, ownQuantity, allocationPayload, associatedSources, handcraftLinkSources, sourceQuantities, productionDemandLines } from '@/utils/productionAllocation'

const route = useRoute(), router = useRouter(), message = useMessage()
const auth = useAuthStore(), creatingLine = ref(null)
const data = ref(null), order = ref(null), loading = ref(false), loadError = ref(''), saving = ref(false)
const selected = ref(null), quantities = ref({}), showEditor = ref(false), saveError = ref('')
const allocationEditor = ref(null)
const linking = ref(false), linkSearch = ref(''), linkSupplier = ref(null)
const visibleSources = type => associatedSources(data.value.sources, type, data.value.order_id)
const demandLines = computed(() => productionDemandLines(data.value))
const linkSources = computed(() => handcraftLinkSources(data.value?.sources || [])
  .filter(source => matchingLines(demandLines.value, source).length > 0))
const linkSupplierOptions = computed(() => [...new Set(linkSources.value.map(source => source.supplier_name || ''))]
  .sort((a, b) => a.localeCompare(b, 'zh-CN'))
  .map(value => ({ value, label: value || '未填写商家' })))
const linkGroups = computed(() => {
  const groups = new Map(), keyword = linkSearch.value.trim().toLowerCase()
  for (const source of linkSources.value) {
    if (linkSupplier.value !== null && (source.supplier_name || '') !== linkSupplier.value) continue
    if (keyword && ![source.production_order_id, source.supplier_name, source.product_id, source.product_name]
      .some(value => String(value || '').toLowerCase().includes(keyword))) continue
    if (!groups.has(source.production_order_id)) groups.set(source.production_order_id, { id: source.production_order_id, supplier: source.supplier_name, sources: [] })
    groups.get(source.production_order_id).sources.push(source)
  }
  return [...groups.values()].sort((a, b) => String(b.id).localeCompare(String(a.id), 'en', { numeric: true }))
})
function linkBlockedReason(source) {
  if (!data.value?.editable) return '订单只读，无法分配'
  if (source.legacy_claim) return '旧归属待核对，暂不可分配'
  if (source.unit_mismatch) return '单位不一致，不自动换算'
  if (!matchingLines(demandLines.value, source).some(line => !line.legacy_claim)) return '无可分配的本单明细，请先核对商品及旧归属'
  return ''
}
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  loadError.value = ''
  try {
    const [response, info] = await Promise.all([getOrderProduction(route.params.id), getOrder(route.params.id)])
    if (id === requestId) { data.value = response.data; order.value = info.data }
  } catch (error) {
    if (id === requestId) loadError.value = error.response?.data?.detail || '加载失败'
  } finally { if (id === requestId) loading.value = false }
}
watch(() => route.params.id, () => { showEditor.value = false; creatingLine.value = null; data.value = null; order.value = null; load() }, { immediate: true })
async function scrollToProductionSection() {
  const hash = route.hash, orderId = route.params.id
  if (!['#handcraft-production', '#plating-production'].includes(hash) || loading.value || loadError.value || !data.value) return
  await nextTick()
  if (route.hash !== hash || route.params.id !== orderId || loading.value || loadError.value || data.value?.order_id !== String(orderId)) return
  const section = document.getElementById(hash.slice(1))
  section?.scrollIntoView({ block: 'start', behavior: 'auto' })
  section?.focus({ preventScroll: true })
}
watch([() => route.hash, () => data.value, () => loading.value], scrollToProductionSection, { flush: 'post' })
async function created(result) {
  creatingLine.value = null
  message.success(`${result.appended ? '已追加' : '已新建'} ${result.production_order_id}，本行安排 ${result.allocated_quantity}；未扣库或出货`)
  await load()
}
function edit(source) {
  linking.value = false
  selectSource(source)
  showEditor.value = true
}
function selectSource(source, suggest = false) {
  selected.value = source
  quantities.value = sourceQuantities(demandLines.value, source, suggest && !ownQuantity(source, data.value.order_id))
  saveError.value = ''
}
function openLinker() {
  if (saving.value || loading.value || loadError.value || !data.value?.editable) return
  linking.value = true
  linkSearch.value = ''
  linkSupplier.value = null
  selected.value = null
  quantities.value = {}
  saveError.value = ''
  showEditor.value = true
}
function selectLinkOutput(id) {
  if (!linking.value || saving.value || loading.value || loadError.value) return
  const source = linkSources.value.find(row => row.source_item_id === id)
  if (source && !linkBlockedReason(source) && selected.value?.source_item_id !== id) {
    selectSource(source, true)
    nextTick(() => allocationEditor.value?.scrollIntoView({ block: 'start', behavior: 'auto' }))
  }
}
function openSource(source) {
  router.push({ path: `/${source.source_type}/${source.production_order_id}`, query: { from_order: data.value.order_id } })
}
async function save() {
  if (saving.value || loading.value || loadError.value || !data.value?.editable || !selected.value) return
  if (linking.value && (!linkSources.value.includes(selected.value) || linkBlockedReason(selected.value))) return
  saving.value = true
  saveError.value = ''
  try {
    const payload = allocationPayload(demandLines.value, selected.value, quantities.value)
    if (linking.value && !payload.allocations.some(row => row.quantity > 0)) throw new Error('请填写大于 0 的本单份额，才会确认关联')
    await replaceOrderProduction(data.value.order_id, payload)
    showEditor.value = false
    message.success(selected.value.source_type === 'handcraft' ? '本单份额已同步至手工单客户分拣，库存及实收未改变' : '本单生产安排已更新，库存及实收未改变')
    await load()
  } catch (error) { saveError.value = error.response?.data?.detail || error.message || '保存失败' }
  finally { saving.value = false }
}
</script>

<style scoped>
small { color: #777; }
.production-arrangement { scroll-margin-top: 16px; }
.warning { color: #a46613; }
.editor-line { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 16px 0; }
.link-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 18px 0 12px; }
.link-toolbar > strong { flex-shrink: 0; }
.link-filters { display: grid; grid-template-columns: minmax(0, 200px) minmax(0, 320px); gap: 10px; flex: 1; max-width: 530px; min-width: 0; }
.link-list { max-height: 340px; overflow-y: auto; border: 1px solid #e7ece9; border-radius: 8px; }
.link-order + .link-order { border-top: 1px solid #e7ece9; }
.link-order-heading { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; padding: 10px 14px; background: #f6f8f7; }
.link-order-heading span { color: #727d77; font-size: 12px; }
.link-output { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px; }
.link-output + .link-output { border-top: 1px solid #edf1ee; }
.link-output.is-selected { background: #eff8f3; box-shadow: inset 3px 0 #367b52; }
.link-output-info { min-width: 0; overflow-wrap: anywhere; }
.link-output > .n-button { flex-shrink: 0; }
.link-output-stats { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; margin-top: 10px; color: #727d77; font-size: 12px; }
.link-output-stats b { color: #34483c; }
.link-empty { padding: 28px 0; }
.link-hint { color: #727d77; margin: 18px 0; }
.allocation-editor { margin: 20px 0; }
.allocation-editor h3 { font-size: 15px; margin: 0 0 12px; }
@media (max-width: 540px) {
  .editor-line { flex-wrap: wrap; }
  .link-toolbar { align-items: stretch; flex-direction: column; gap: 10px; }
  .link-filters { grid-template-columns: minmax(0, 1fr); max-width: none; }
  .link-list { max-height: 300px; }
  .link-output { flex-wrap: wrap; gap: 12px; padding: 12px; }
  .link-output-info { width: 100%; }
  .link-output > .n-button { margin-left: auto; }
}
</style>

<template>
  <div class="fulfillment-page order-workspace">
    <OrderWorkspaceHeader :order-id="String(route.params.id)" :customer-name="data?.customer_name" :status="order?.status" :created-at="order?.created_at" active="production"><n-button :loading="loading" :disabled="saving || !!creatingLine || !!batchCreating.length" @click="load">刷新并核对</n-button></OrderWorkspaceHeader>
    <n-alert type="info" :bordered="false" class="wf-notice">
      确认关联手工或电镀后，订单自动进入「生产中」，无需手动开始。生产安排不是预留库存、实物归属或客户出货；订单须全部明细足量出货后才完成。现有成品库存可以独立出货，无需补建生产关联。
    </n-alert>
    <n-spin :show="loading">
      <n-alert v-if="loadError" type="error">{{ loadError }}，请刷新后重试。</n-alert>
      <template v-if="data && !loadError">
        <div class="section-controls">
          <span class="section-controls-label">模块视图</span>
          <div class="section-control-group" role="group" aria-label="模块展开与收起" title="收起不影响已选内容和草稿">
            <n-button quaternary size="small" class="section-control-button" @click="expandSections(false)"><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 3h12M4 17h12m-9-9 3-3 3 3m-6 4 3 3 3-3M10 5v10" /></svg>全部展开</n-button>
            <span class="section-control-divider" aria-hidden="true"></span>
            <n-button quaternary size="small" class="section-control-button" @click="expandSections(true)"><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 3h12M4 17h12m-9-10 3 3 3-3m-6 6 3-3 3 3M10 5v10" /></svg>全部收起</n-button>
          </div>
        </div>
        <OrderSection title="本单生产需求" :count="`${data.lines.length} 项`">
          <template #summary><n-tag v-if="reviewCount" size="small" type="warning" :bordered="false">{{ reviewCount }} 项旧记录待核对</n-tag></template>
          <template #header-extra><span>已选 {{ creatingIds.length }} 项</span><n-button size="small" :disabled="loading || saving || !creatingIds.length" @click="creatingIds = []">清空</n-button><n-button v-if="data.editable && auth.hasPermission('handcraft')" size="small" type="primary" secondary :disabled="loading || saving || !creatingIds.length" @click="openBatchCreation">批量安排制作</n-button></template>
          <p class="wf-section-description">生产计划与已预留、已出货分别核算；同款重复行保留独立身份。</p>
          <div class="wf-table-wrap"><n-table :bordered="false" class="wf-table"><thead><tr><th><n-checkbox :checked="allCreationSelected" :indeterminate="creatingIds.length > 0 && !allCreationSelected" :disabled="loading || saving || !creatableLines.length" aria-label="全选可制作明细" @update:checked="toggleCreationAll" /></th><th>产品 / 客户货号</th><th>订购</th><th>生产安排</th><th>旧记录核对</th><th>操作</th></tr></thead><tbody>
            <tr v-for="line in data.lines" :key="line.id">
              <td><n-checkbox :checked="creatingIds.includes(line.id)" :disabled="loading || saving || !canCreate(line)" :aria-label="`选择制作明细 ${line.id}`" @update:checked="toggleCreation(line.id, $event)" /></td>
              <td><ProductCell :line="line" /></td><td>{{ line.quantity }} {{ line.unit }}</td>
              <td class="wf-green"><strong>{{ line.allocated }}</strong><small class="wf-subtext">计划数量，不代表实收</small></td>
              <td><n-tag size="small" :bordered="false" :type="line.legacy_claim ? 'warning' : 'default'">{{ line.legacy_claim ? '旧关联／批次待核对' : line.legacy_batches?.length ? '旧批次仅作参考' : '无旧归属冲突' }}</n-tag><n-button v-if="line.legacy_claim || line.legacy_batches?.length" text size="small" type="primary" :disabled="loading || saving" @click="legacyReviewLine = line">查看旧记录</n-button></td>
              <td><n-button v-if="data.editable && !line.legacy_claim && Number(line.allocated) < line.quantity && auth.hasPermission('handcraft')" text type="primary" :disabled="loading || saving" @click="creatingLine = line">＋ 安排制作</n-button><span v-else class="wf-muted">{{ line.legacy_claim ? '先核对旧归属' : !data.editable ? '只读' : Number(line.allocated) >= line.quantity ? '已足额安排' : '需手工权限' }}</span></td>
            </tr>
          </tbody></n-table></div>
        </OrderSection>
        <OrderMaterials ref="orderMaterials" :key="data.order_id" :order-id="data.order_id" :lines="data.lines" :materials="data.materials || []" :editable="data.editable" accent-actions />
        <OrderSection v-for="type in ['handcraft', 'plating']" :key="type" :id="`${type}-production`" tabindex="-1" class="production-arrangement" :title="type === 'handcraft' ? '手工生产安排' : '电镀生产安排'">
          <template #summary><n-tag v-if="visibleSources(type).some(s => s.legacy_claim || s.unit_mismatch || s.risk)" size="small" type="warning" :bordered="false">有待核对项</n-tag></template>
          <template v-if="type === 'handcraft'" #header-extra>
            <n-button v-if="data.editable" size="small" type="primary" secondary :disabled="loading || saving" @click="openLinker">订单关联</n-button>
          </template>
          <p class="wf-section-description">{{ type === 'handcraft' ? '只展示已确认关联本单的手工产出；通过「订单关联」选择已有手工单，商品制作／配件备料份额同步计入客户分拣' : '匹配订单商品及 BOM 配件备料，按收回目标而不是原色投入匹配' }}</p>
          <n-empty v-if="!visibleSources(type).length" :description="type === 'handcraft' ? '暂无已关联的手工单，可从右上角「订单关联」选择已有手工单' : '暂无匹配商品或 BOM 配件的电镀产出'" class="wf-empty" />
          <div v-else class="wf-table-wrap"><n-table :bordered="false" class="wf-table"><thead><tr><th>加工单 / 商家 / 关联</th><th>目标产出</th><th>阶段</th><th>整条计划 / 实收</th><th>本单安排</th><th>其他客户安排</th><th>未分配计划</th><th>操作</th></tr></thead><tbody>
            <tr v-for="source in visibleSources(type)" :key="source.source_item_id" class="source-card">
              <td>
                <n-button text type="primary" @click="openSource(source)">{{ source.production_order_id }}</n-button>
                <small class="wf-subtext">{{ source.supplier_name }}</small>
                <n-tag size="small" :bordered="false" :type="source.legacy_claim ? 'warning' : ownQuantity(source, data.order_id) ? 'success' : 'default'">{{ source.legacy_claim ? '旧归属待核对' : ownQuantity(source, data.order_id) ? '已关联本单' : '候选，未关联本单' }}</n-tag>
              </td>
              <td><ProductCell :line="{ ...source, id: source.source_item_id }" /><small v-if="type === 'plating'" class="wf-subtext">投入 {{ source.input_part_id }} → 目标 {{ source.product_id }}</small></td>
              <td><n-tag size="small" :bordered="false">{{ source.archived ? '历史归档' : { pending: '待发出', processing: '加工中', completed: '已结清' }[source.status] || source.status }}</n-tag></td>
              <td>{{ source.planned }} {{ source.unit }}<small class="wf-subtext">实收 {{ source.received }} / 损耗 {{ source.loss }}</small><small v-if="source.risk" class="wf-subtext wf-amber">存在损耗，需核对交付缺口</small></td>
              <td class="wf-green"><strong>{{ ownQuantity(source, data.order_id) }}</strong></td>
              <td>{{ Number(source.allocated) - ownQuantity(source, data.order_id) }}<small class="wf-subtext">只读，不在本单修改</small></td>
              <td>{{ source.public_unallocated ?? '待核对' }}</td>
              <td><span v-if="source.legacy_claim" class="wf-muted">先核对旧归属</span><n-button v-else-if="data.editable && !source.archived && ['pending', 'processing'].includes(source.status) && matchingLines(demandLines, source).length" text type="primary" @click="edit(source)">{{ ownQuantity(source, data.order_id) ? '调整本单分配' : '分配给本单' }}</n-button><span v-else class="wf-muted">只读追溯</span><small v-if="source.unit_mismatch" class="wf-subtext wf-amber">单位不一致，不自动换算</small></td>
            </tr>
          </tbody></n-table></div>
        </OrderSection>
      </template>
    </n-spin>
    <n-modal v-model:show="showEditor" preset="card" :title="linking ? '订单关联' : '调整本单生产数量'" :mask-closable="!saving" :closable="!saving" :close-on-esc="!saving" :style="{ width: `min(${linking ? 940 : 700}px, calc(100vw - 24px))` }">
      <template v-if="linking">
        <n-alert type="info" :bordered="false">可跨多张手工单勾选多个产出，在下方统一填写「分配后本单份额」。整批一起保存或一起失败，其他客户和未选产出不变；生产计划不增加实物库存。</n-alert>
        <div class="link-toolbar">
          <strong>已有手工单 <small>{{ linkGroups.length }} 单 · 单号倒序</small></strong>
          <div class="link-filters">
            <n-select v-model:value="linkSupplier" :options="linkSupplierOptions" filterable clearable :disabled="saving" placeholder="全部手工商家" :input-props="{ 'aria-label': '筛选手工商家' }" />
            <n-input v-model:value="linkSearch" clearable :disabled="saving" placeholder="搜索单号、商家或商品" :input-props="{ 'aria-label': '搜索已有手工单' }" />
          </div>
        </div>
        <div class="wf-actions batch-selection"><n-checkbox :checked="allLinkSelected" :indeterminate="someLinkSelected && !allLinkSelected" :disabled="saving || !selectableLinkSources.length" @update:checked="toggleAllLinkOutputs">全选当前可分配产出</n-checkbox><strong>已选 {{ linkSelectedSources.length }} 个产出 / {{ selectedOrderCount }} 张手工单</strong><n-button text :disabled="saving" @click="clearLinkOutputs">清空</n-button></div>
        <n-empty v-if="!linkSources.length" description="暂无匹配本单商品的可关联手工单，可先安排制作" class="link-empty" />
        <n-empty v-else-if="!linkGroups.length" description="没有找到匹配的手工单，请更换商家或关键词" class="link-empty" />
        <div v-else class="link-list" aria-label="已有手工单列表">
          <section v-for="group in linkGroups" :key="group.id" class="link-order">
            <header class="link-order-heading"><n-checkbox :checked="groupSelected(group)" :indeterminate="groupPartial(group)" :disabled="saving || !group.sources.some(s => !linkBlockedReason(s))" :aria-label="`选择 ${group.id} 可分配产出`" @update:checked="toggleLinkGroup(group, $event)" /><strong>{{ group.id }}</strong><span>{{ group.supplier || '未填写商家' }}</span></header>
            <div v-for="source in group.sources" :key="source.source_item_id" class="link-output" :class="{ 'is-selected': !!linkDrafts[source.source_item_id] }">
              <div class="link-output-info">
                <ProductCell :line="{ ...source, id: source.source_item_id }" />
                <div class="link-output-stats"><n-tag size="small" :bordered="false">{{ source.status === 'pending' ? '待发出' : '加工中' }}</n-tag><span>计划 <b>{{ source.planned }}</b> {{ source.unit }}</span><span>未分配 <b>{{ source.public_unallocated ?? '待核对' }}</b> {{ source.unit }}</span><span>本单已分配 <b>{{ ownQuantity(source, data.order_id) }}</b> {{ source.unit }}</span></div>
                <small v-if="linkBlockedReason(source)" class="warning">{{ linkBlockedReason(source) }}</small>
              </div>
              <n-checkbox :checked="!!linkDrafts[source.source_item_id]" :disabled="!!linkBlockedReason(source) || saving || loading" :aria-label="`${source.production_order_id} 明细 ${source.source_item_id} 分配给本单`" @update:checked="selectLinkOutput(source.source_item_id)">选择产出 #{{ source.source_item_id }}</n-checkbox>
            </div>
          </section>
        </div>
      </template>
      <div v-for="entry in editorEntries" :key="`${entry.source.source_type}:${entry.source.source_item_id}`" class="allocation-editor" aria-label="本单分配数量">
        <h3 v-if="linking">{{ entry.source.production_order_id }} · 产出 #{{ entry.source.source_item_id }}</h3>
        <n-alert type="info" :bordered="false">仅保存 {{ data.order_id }} 的份额，不改其他客户。填 0 取消安排，不退料、不回库、不影响实收。</n-alert>
        <p>{{ entry.source.production_order_id }} · {{ entry.source.product_name }} · 产出明细 #{{ entry.source.source_item_id }} · 整批计划 {{ entry.source.planned }} {{ entry.source.unit }} · 本单已有 {{ ownQuantity(entry.source, data.order_id) }} · 可供本单总量 {{ Number(entry.source.planned) - Number(entry.source.allocated) + ownQuantity(entry.source, data.order_id) }}</p>
        <div v-for="line in matchingLines(demandLines, entry.source)" :key="line.id" class="editor-line">
          <label :for="`allocation-${entry.source.source_type}-${entry.source.source_item_id}-${line.id}`">{{ line.material_part_id ? '配件备料 · ' + line.parent_product_name : '商品制作 · ' + line.product_name }} · {{ line.customer_code || '未填货号' }} · 明细 #{{ line.order_item_id || line.id }}<br><small>需求 {{ line.quantity }} · 旧关联 {{ line.legacy_claim ? '待核对' : '无' }}</small><br v-if="line.demand_changed"><small v-if="line.demand_changed" class="warning">BOM／订购量已变化，确认将采用当前需求；填 0 可取消原份额。</small></label>
          <n-input-number v-model:value="entry.quantities[line.id]" :input-props="{ id: `allocation-${entry.source.source_type}-${entry.source.source_item_id}-${line.id}`, 'aria-label': `产出 ${entry.source.source_item_id} 明细 ${line.id} 分配后数量` }" :min="0" :max="9999999999" :precision="line.material_part_id && entry.source.source_type === 'plating' ? 4 : 0" :disabled="saving || line.legacy_claim" style="max-width: 170px;" />
        </div>
      </div>
      <p v-if="linking && !linkSelectedSources.length" class="link-hint">请勾选上方多个产出，筛选不会清除其他手工单下已选内容。</p>
      <div v-if="linking && linkSelectedSources.length" class="wf-table-wrap"><h3>统一核对（包含未选产出的已有份额）</h3><n-table :bordered="false"><thead><tr><th>产出 / 订单明细</th><th>分配后合计</th><th>上限</th></tr></thead><tbody><tr v-for="row in batchReview.sources" :key="`s-${row.source.source_item_id}`"><td>{{ row.source.production_order_id }} / #{{ row.source.source_item_id }}</td><td :class="{ warning: row.invalid }">{{ row.total }}</td><td>{{ row.limit }} {{ row.source.unit }}</td></tr><tr v-for="row in batchReview.lines" :key="`l-${row.line.id}`"><td>{{ row.line.customer_code || row.line.product_name }} · 明细 {{ row.line.id }}</td><td :class="{ warning: row.invalid }">{{ row.total }}</td><td>{{ row.limit }} {{ row.line.unit }}</td></tr></tbody></n-table></div>
      <p v-if="saveError" role="alert" class="warning">{{ saveError }}</p>
      <n-space justify="end"><n-button :disabled="saving" @click="showEditor = false">返回</n-button><n-button type="primary" :disabled="(linking ? !linkSelectedSources.length : !selected) || loading || !data?.editable" :loading="saving" @click="save">{{ linking ? '确认统一分配' : '保存本单安排' }}</n-button></n-space>
    </n-modal>
    <OrderLegacyProductionReview v-if="legacyReviewLine" :order-id="data.order_id" :line="legacyReviewLine" @close="legacyReviewLine = null" @history="showLegacyHistory" />
    <OrderHandcraftDialog v-if="creatingLine" :order-id="data.order_id" :line="creatingLine" @close="creatingLine = null" @saved="created" />
    <OrderHandcraftBatchDialog v-if="batchCreating.length" :order-id="data.order_id" :lines="batchCreating" @close="batchCreating = []" @saved="batchCreated" />
  </div>
</template>

<script setup>
import { computed, nextTick, provide, ref, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { NAlert, NButton, NCheckbox, NEmpty, NInput, NInputNumber, NModal, NSelect, NSpace, NSpin, NTable, NTag, useMessage } from 'naive-ui'
import OrderWorkspaceHeader from '@/components/fulfillment/OrderWorkspaceHeader.vue'
import OrderSection from '@/components/fulfillment/OrderSection.vue'
import { getOrder } from '@/api/orders'
import ProductCell from '@/components/fulfillment/ProductCell.vue'
import OrderHandcraftDialog from '@/components/fulfillment/OrderHandcraftDialog.vue'
import OrderHandcraftBatchDialog from '@/components/fulfillment/OrderHandcraftBatchDialog.vue'
import OrderMaterials from '@/components/fulfillment/OrderMaterials.vue'
import OrderLegacyProductionReview from '@/components/fulfillment/OrderLegacyProductionReview.vue'
import { useAuthStore } from '@/stores/auth'
import { getOrderProduction, replaceOrderProduction, replaceOrderProductionBatch } from '@/api/productionAllocation'
import { matchingLines, ownQuantity, allocationPayload, allocationBatchPayload, allocationBatchReview, associatedSources, handcraftLinkSources, sourceQuantities, productionDemandLines } from '@/utils/productionAllocation'

const route = useRoute(), router = useRouter(), message = useMessage()
const auth = useAuthStore(), creatingLine = ref(null)
const legacyReviewLine = ref(null), orderMaterials = ref(null)
const sectionTitles = ['本单生产需求', '配件备料', '手工生产安排', '电镀生产安排', '已有批次与生产关联记录']
const collapsedSections = ref({})
try {
  const stored = JSON.parse(localStorage.getItem('allen:order-production-sections:v1') || '{}')
  for (const title of sectionTitles) collapsedSections.value[title] = stored?.[title] === true
  // Keep the merged module visible if either of its previous sections was open.
  if (typeof stored?.['配件备料'] !== 'boolean') collapsedSections.value['配件备料'] = stored?.['配件备料需求'] === true && stored?.['配件备料与 BOM'] === true
} catch (_) { /* Storage is optional. */ }
function setSectionCollapsed(title, value) {
  collapsedSections.value = { ...collapsedSections.value, [title]: value }
  try { localStorage.setItem('allen:order-production-sections:v1', JSON.stringify(collapsedSections.value)) } catch (_) { /* Still usable without browser storage. */ }
}
function expandSections(collapsed) { for (const title of sectionTitles) setSectionCollapsed(title, collapsed) }
provide('order-production-sections', { collapsed: collapsedSections, setCollapsed: setSectionCollapsed })
async function showLegacyHistory() {
  legacyReviewLine.value = null
  setSectionCollapsed('已有批次与生产关联记录', false)
  await nextTick()
  orderMaterials.value?.openHistory()
}
const data = ref(null), order = ref(null), loading = ref(false), loadError = ref(''), saving = ref(false)
const selected = ref(null), quantities = ref({}), showEditor = ref(false), saveError = ref('')
const linking = ref(false), linkSearch = ref(''), linkSupplier = ref(null)
const creatingIds = ref([]), batchCreating = ref([]), linkDrafts = ref({})
const canCreate = line => data.value?.editable && auth.hasPermission('handcraft') && !line.legacy_claim && Number(line.allocated) < Number(line.quantity)
const creatableLines = computed(() => (data.value?.lines || []).filter(canCreate))
const allCreationSelected = computed(() => !!creatableLines.value.length && creatableLines.value.every(l => creatingIds.value.includes(l.id)))
const reviewCount = computed(() => (data.value?.lines || []).filter(l => l.legacy_claim || l.legacy_batches?.length).length)
function toggleCreation(id, checked) { if (saving.value || loading.value || !creatableLines.value.some(l => l.id === id)) return; creatingIds.value = checked ? [...new Set([...creatingIds.value, id])] : creatingIds.value.filter(i => i !== id) }
function toggleCreationAll(checked) { if (!saving.value && !loading.value) creatingIds.value = checked ? creatableLines.value.map(l => l.id) : [] }
function openBatchCreation() {
  if (saving.value || loading.value || loadError.value) return
  const lines = creatableLines.value.filter(l => creatingIds.value.includes(l.id))
  if (lines.length && lines.length <= 100) batchCreating.value = lines
  else if (lines.length > 100) message.warning('每批最多选择 100 条明细')
}
async function batchCreated(result) {
  batchCreating.value = []; creatingIds.value = []
  message.success(`${result.appended ? '已追加' : '已新建'} ${result.production_order_id}，整批 ${result.rows.length} 个独立产出；未扣库或出货`)
  await load()
}
const linkSelectedSources = computed(() => Object.values(linkDrafts.value).map(draft => draft.source))
const selectedOrderCount = computed(() => new Set(linkSelectedSources.value.map(s => s.production_order_id)).size)
const linkQuantities = computed(() => Object.fromEntries(Object.entries(linkDrafts.value).map(([id, draft]) => [id, draft.quantities])))
const editorEntries = computed(() => linking.value ? Object.values(linkDrafts.value) : selected.value ? [{ source: selected.value, quantities: quantities.value }] : [])
const batchReview = computed(() => allocationBatchReview(demandLines.value, linkSelectedSources.value, linkQuantities.value, data.value?.order_id))
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
const selectableLinkSources = computed(() => linkGroups.value.flatMap(g => g.sources).filter(s => !linkBlockedReason(s)))
const allLinkSelected = computed(() => !!selectableLinkSources.value.length && selectableLinkSources.value.every(s => !!linkDrafts.value[s.source_item_id]))
const someLinkSelected = computed(() => selectableLinkSources.value.some(s => !!linkDrafts.value[s.source_item_id]))
function groupSelected(group) { const rows = group.sources.filter(s => !linkBlockedReason(s)); return !!rows.length && rows.every(s => !!linkDrafts.value[s.source_item_id]) }
function groupPartial(group) { return !groupSelected(group) && group.sources.some(s => !!linkDrafts.value[s.source_item_id]) }
function toggleLinkGroup(group, checked) { for (const s of group.sources) if (!linkBlockedReason(s) && !!linkDrafts.value[s.source_item_id] !== checked) selectLinkOutput(s.source_item_id) }
function toggleAllLinkOutputs(checked) { toggleLinkGroup({ sources: selectableLinkSources.value }, checked) }
function clearLinkOutputs() { if (!saving.value) linkDrafts.value = {} }
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
    if (id === requestId) {
      data.value = response.data; order.value = info.data
      creatingIds.value = creatingIds.value.filter(lineId => creatableLines.value.some(line => line.id === lineId))
    }
  } catch (error) {
    if (id === requestId) loadError.value = error.response?.data?.detail || '加载失败'
  } finally { if (id === requestId) loading.value = false }
}
watch(() => route.params.id, () => { showEditor.value = false; creatingLine.value = null; batchCreating.value = []; creatingIds.value = []; linkDrafts.value = {}; legacyReviewLine.value = null; data.value = null; order.value = null; load() }, { immediate: true })
async function scrollToProductionSection() {
  const hash = route.hash, orderId = route.params.id
  if (!['#handcraft-production', '#plating-production'].includes(hash) || loading.value || loadError.value || !data.value) return
  setSectionCollapsed(hash === '#handcraft-production' ? '手工生产安排' : '电镀生产安排', false)
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
  linkDrafts.value = {}
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
  if (source && !linkBlockedReason(source)) {
    if (linkDrafts.value[id]) delete linkDrafts.value[id]
    else linkDrafts.value[id] = { source, quantities: sourceQuantities(demandLines.value, source) }
    saveError.value = ''
  }
}
function openSource(source) {
  router.push({ path: `/${source.source_type}/${source.production_order_id}`, query: { from_order: data.value.order_id } })
}
async function save() {
  if (saving.value || loading.value || loadError.value || !data.value?.editable || (linking.value ? !linkSelectedSources.value.length : !selected.value)) return
  if (linking.value && linkSelectedSources.value.some(s => !linkSources.value.includes(s) || linkBlockedReason(s))) return
  saving.value = true
  saveError.value = ''
  try {
    if (linking.value) {
      const sources = allocationBatchPayload(demandLines.value, linkSelectedSources.value, linkQuantities.value, data.value.order_id)
      await replaceOrderProductionBatch(data.value.order_id, sources)
    } else {
      const payload = allocationPayload(demandLines.value, selected.value, quantities.value)
      await replaceOrderProduction(data.value.order_id, payload)
    }
    showEditor.value = false
    message.success(linking.value || selected.value.source_type === 'handcraft' ? '本单份额已同步至手工单客户分拣，库存及实收未改变' : '本单生产安排已更新，库存及实收未改变')
    await load()
  } catch (error) { saveError.value = error.response?.data?.detail || error.message || '保存失败' }
  finally { saving.value = false }
}
onBeforeRouteLeave(() => !saving.value)
onBeforeRouteUpdate(() => !saving.value)
</script>

<style scoped>
small { color: #777; }
.production-arrangement { scroll-margin-top: 16px; }
.section-controls { display:flex; align-items:center; justify-content:flex-end; gap:12px; margin:12px 0 16px; }
.section-controls-label { color:#929A96; font-size:12px; }
.section-control-group { display:inline-flex; align-items:center; padding:3px; border:1px solid #E3E8E5; border-radius:9px; background:#FFF; }
.section-control-button { display:inline-flex; align-items:center; justify-content:center; gap:6px; min-height:30px; padding:0 11px; border:0; border-radius:6px; background:transparent; color:#626E67; font:inherit; font-size:12px; line-height:1; cursor:pointer; transition:background .16s ease, color .16s ease; }
.section-control-button svg { flex-shrink:0; width:15px; height:15px; margin-right:6px; stroke:currentColor; stroke-width:1.5; stroke-linecap:round; stroke-linejoin:round; }
.section-control-button:hover { background:#EEF5F0; color:#1E7A5A; }
.section-control-button:active { background:#E2EDE6; }
.section-control-button:focus-visible { outline:2px solid #1E7A5A; outline-offset:2px; }
.section-control-divider { width:1px; height:14px; margin:0 3px; background:#E8ECE9; }
.batch-selection { margin:12px 0 18px; }
@media (prefers-reduced-motion:reduce) { .section-control-button { transition:none; } }
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
.link-output > .n-checkbox { flex-shrink: 0; }
.link-output-stats { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; margin-top: 10px; color: #727d77; font-size: 12px; }
.link-output-stats b { color: #34483c; }
.link-empty { padding: 28px 0; }
.link-hint { color: #727d77; margin: 18px 0; }
.allocation-editor { margin: 20px 0; }
.allocation-editor h3 { font-size: 15px; margin: 0 0 12px; }
@media (max-width: 540px) {
  .section-controls { justify-content:space-between; gap:8px; }
  .editor-line { flex-wrap: wrap; }
  .link-toolbar { align-items: stretch; flex-direction: column; gap: 10px; }
  .link-filters { grid-template-columns: minmax(0, 1fr); max-width: none; }
  .link-list { max-height: 300px; }
  .link-output { flex-wrap: wrap; gap: 12px; padding: 12px; }
  .link-output-info { width: 100%; }
  .link-output > .n-checkbox { margin-left: auto; }
}
</style>

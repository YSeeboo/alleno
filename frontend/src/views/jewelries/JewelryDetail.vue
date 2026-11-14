<template>
  <div class="jewelry-detail">
    <div class="page-breadcrumb">商品 / 饰品管理 / 饰品详情</div>
    <header class="jd-head">
      <div>
        <div class="jd-title">
          <h2 class="page-title">{{ jewelry?.name || '饰品详情' }}</h2>
          <span v-if="jewelry" class="jd-status" :class="{ 'is-active': jewelry.status === 'active' }">{{ jewelry.status === 'active' ? '启用中' : '已停用' }}</span>
        </div>
        <div v-if="jewelry" class="jd-subtitle"><span class="jd-code">{{ jewelry.id }}</span><button class="jd-copy" aria-label="复制饰品编号" title="复制编号" @click="copyId">⧉</button><span>饰品详情</span></div>
      </div>
      <n-button text size="small" @click="router.push('/jewelries')">← 返回饰品列表</n-button>
    </header>

    <n-spin :show="loading">
      <n-alert v-if="pageError" type="error" class="jd-alert" title="详情未能加载完整">
        {{ pageError }} <n-button text type="primary" :disabled="busy" @click="loadPage">重新加载</n-button>
      </n-alert>
      <n-alert v-if="writeError" type="warning" class="jd-alert" title="请先核对保存结果">
        {{ writeError }} <n-button text type="primary" :disabled="busy" @click="loadPage">刷新核对</n-button>
      </n-alert>
      <template v-if="jewelry">
        <section class="jd-stats" aria-label="饰品概览">
          <div class="jd-stat"><div class="jd-stat-label">当前库存</div><div class="jd-stat-value">{{ stock == null ? '—' : stock }}<small v-if="stock != null">{{ unitLabel }}</small></div><div class="jd-stat-note">{{ !canInventory ? '无库存查看权限' : stockError ? '库存加载失败' : '按库存流水汇总' }}</div></div>
          <div class="jd-stat"><div class="jd-stat-label">物料成本</div><div class="jd-stat-value"><small v-if="completeCost" class="jd-currency">¥</small>{{ completeCost ? fmtMoney(jewelry.material_cost) : '—' }}</div><div class="jd-stat-note">{{ completeCost ? '按当前 BOM 计算' : '成本待补全' }}</div></div>
          <div class="jd-stat"><div class="jd-stat-label">手工费</div><div class="jd-stat-value"><small v-if="jewelry.handcraft_cost != null" class="jd-currency">¥</small>{{ jewelry.handcraft_cost == null ? '—' : fmtMoney(jewelry.handcraft_cost) }}</div><div class="jd-stat-note">{{ jewelry.handcraft_cost == null ? '尚未填写' : `每 1 ${unitLabel}饰品` }}</div></div>
          <div class="jd-stat"><div class="jd-stat-label">总成本</div><div class="jd-stat-value" :class="completeCost ? 'is-green' : 'is-amber'"><small v-if="completeCost" class="jd-currency">¥</small>{{ completeCost ? fmtMoney(jewelry.total_cost) : '—' }}</div><div class="jd-stat-note">{{ completeCost ? '物料成本 + 手工费' : '暂不展示完整总额' }}</div></div>
          <div class="jd-stat"><div class="jd-stat-label">零售价</div><div class="jd-stat-value"><small v-if="jewelry.retail_price != null" class="jd-currency">¥</small>{{ jewelry.retail_price == null ? '—' : fmtMoney(jewelry.retail_price) }}</div><div class="jd-stat-note">每 1 {{ unitLabel }}饰品</div></div>
        </section>

        <section class="jd-section" aria-labelledby="jewelry-info-title">
          <div class="jd-section-head"><h3 id="jewelry-info-title">基本信息</h3><n-button text type="primary" size="small" :disabled="locked" @click="openInfo">编辑基本信息 ↗</n-button></div>
          <div class="jd-overview">
            <div class="jd-gallery">
              <div class="jd-image">
                <n-image v-if="currentImage" :key="currentImage" :src="currentImage" :alt="`${jewelry.name}${imageType === 'structure' ? '结构图' : ''}`" object-fit="contain" :img-props="{ style: 'width: 100%; height: 224px; object-fit: contain;' }" />
                <div v-else class="jd-no-image"><span>◇</span>{{ imageType === 'structure' ? '暂无结构图' : '暂无饰品图片' }}<small>点击下方“上传图片”添加</small></div>
              </div>
              <div class="jd-gallery-foot"><div class="jd-image-tabs" role="group" aria-label="切换图片"><button :aria-pressed="imageType === 'product'" @click="imageType = 'product'">饰品图</button><button :aria-pressed="imageType === 'structure'" @click="imageType = 'structure'">结构图</button></div><n-button text type="primary" size="tiny" :disabled="locked" @click="openImageUpload">{{ currentImage ? '更换图片' : '上传图片' }}</n-button></div>
            </div>
            <div class="jd-info">
              <div class="jd-meta">
                <div><div class="jd-meta-label">饰品编号</div><div class="jd-meta-value jd-code">{{ jewelry.id }}</div></div>
                <div><div class="jd-meta-label">饰品类目</div><div class="jd-meta-value">{{ jewelryCategoryLabel(jewelry.category) }}</div></div>
                <div><div class="jd-meta-label">计量单位</div><div class="jd-meta-value"><span class="jd-unit">{{ unitLabel }}</span></div></div>
                <div><div class="jd-meta-label">颜色</div><div class="jd-meta-value">{{ jewelry.color || '未设置' }}</div></div>
                <div><div class="jd-meta-label">批发价</div><div class="jd-meta-value mono">{{ price(jewelry.wholesale_price) }}<small v-if="jewelry.wholesale_price != null"> / {{ unitLabel }}</small></div></div>
                <div><div class="jd-meta-label">BOM 配件</div><div class="jd-meta-value">{{ bomReady ? `${bomRows.length} 种` : '—' }}<small> · 独立用料</small></div></div>
              </div>
              <div class="jd-info-note"><strong>以 1 {{ unitLabel }}饰品为计量基准</strong><br>下方用量、成本与售价均按此单位展示。当前饰品的 BOM 独立维护，不随结构或方案自动变化。</div>
            </div>
          </div>
        </section>

        <section class="jd-section" aria-labelledby="jewelry-bom-title">
          <div class="jd-section-head"><div class="jd-section-title"><h3 id="jewelry-bom-title">BOM 用料明细</h3><span v-if="bomReady" class="jd-count">{{ bomRows.length }} 项</span></div><div class="jd-section-actions"><span class="jd-hint jd-bom-hint">每 1 {{ unitLabel }}饰品的用料</span><n-input v-model:value="bomKeyword" size="small" clearable placeholder="搜索配件名称 / 编号" aria-label="搜索 BOM 配件" class="jd-search" /><n-button type="primary" secondary size="small" :disabled="!canAdd" @click="openAdd">＋ 添加配件</n-button></div></div>
          <n-alert v-if="!canParts" type="info" class="jd-alert">暂无配件管理权限，无法查看或修改 BOM。上方成本仍以服务端结果为准。</n-alert>
          <n-alert v-else-if="bomError" type="error" class="jd-alert">BOM 加载失败，未按空用料处理。<n-button text type="primary" :disabled="busy" @click="loadPage">重新加载</n-button></n-alert>
          <n-alert v-else-if="partsError" type="warning" class="jd-alert">配件资料加载失败，暂以编号展示用料，配件成本不按零处理。<n-button text type="primary" :disabled="busy" @click="loadPage">重新加载</n-button></n-alert>
          <div v-if="!completeCost && !pageError" class="jd-cost-notice" role="status"><span aria-hidden="true">ⓘ</span><span>{{ bomReady && !bomRows.length ? '尚未配置 BOM，缺少用料不按零成本处理。' : '成本不完整：部分配件缺少成本或用料信息。下方仅展示已知物料成本，暂不作为完整总成本。' }}</span></div>
          <template v-if="bomReady">
            <div class="jd-table-wrap" role="region" tabindex="0" aria-label="BOM 用料表，窄屏可左右滚动">
              <table v-if="filteredBom.length" class="jd-table">
                <thead><tr><th class="jd-index">#</th><th>配件</th><th>颜色</th><th>每 {{ unitLabel }}用量</th><th>配件单位</th><th class="jd-right">单位成本</th><th class="jd-right">成本小计</th><th><span class="jd-sr-only">操作</span></th></tr></thead>
                <tbody><tr v-for="(row, index) in filteredBom" :key="row.part_id">
                  <td class="jd-index">{{ index + 1 }}</td>
                  <td><div class="jd-part"><n-image v-if="row.part_image" :src="row.part_image" :alt="row.part_name" :width="38" :height="38" object-fit="cover" /><span v-else class="jd-part-empty">无图</span><div><div class="jd-part-name">{{ row.part_name }}<span v-if="row.part_is_composite" class="jd-composite">组合</span></div><div class="jd-part-code jd-code">{{ row.part_id }}</div></div></div></td>
                  <td><span class="jd-color-tag">{{ row.part_color || '—' }}</span></td>
                  <td><input v-model="row.editQty" class="jd-qty" type="text" inputmode="decimal" :aria-label="`${row.part_name}每${unitLabel}用量`" :disabled="locked" @blur="saveQty(row)" @keydown.enter.prevent="$event.target.blur()" @keydown.esc.prevent="row.editQty = String(row.qty_per_unit); $event.target.blur()" /></td>
                  <td class="jd-muted">{{ row.part_unit || '—' }}</td><td class="jd-right mono">{{ row.part_unit_cost == null ? (partsReady ? '待录入' : '—') : price(row.part_unit_cost) }}</td><td class="jd-right mono">{{ row.subtotal == null ? '—' : price(row.subtotal) }}</td>
                  <td><n-popconfirm :disabled="locked" @positive-click="doDeleteBom(row)"><template #trigger><button class="jd-remove" :disabled="locked" :aria-label="`删除${row.part_name}`" title="移除用料">×</button></template>从当前饰品 BOM 移除“{{ row.part_name }}”？不删除配件或改变库存。</n-popconfirm></td>
                </tr></tbody>
                <tfoot><tr><td colspan="5" class="jd-total-label">{{ bomKeyword ? '全部用料 · ' : '' }}{{ completeCost ? '物料成本合计' : '已知物料成本小计（非完整成本）' }}</td><td colspan="2" class="jd-right mono"><strong>{{ pageError ? '—' : price(jewelry.material_cost) }}</strong></td><td></td></tr></tfoot>
              </table>
              <n-empty v-else :description="bomRows.length ? '没有匹配的配件，试试其他关键词' : '尚未配置用料，点击“添加配件”建立独立 BOM'" class="jd-empty" />
            </div>
            <div class="jd-table-note"><span>点击用量可直接修改，回车或失焦保存；不同配件的用量不相加。</span><span>窄屏可左右滑动查看完整表格</span></div>
          </template>
        </section>

        <div class="jd-cost-strip"><div>物料 <b>{{ completeCost ? price(jewelry.material_cost) : '待补全' }}</b><span>＋</span>手工 <b>{{ price(jewelry.handcraft_cost) }}</b><span>＝</span>总成本 <b>{{ completeCost ? price(jewelry.total_cost) : '待补全' }}</b></div><small>每 1 {{ unitLabel }} · 服务端实时核算</small></div>
        <p class="jd-footer-note">修改 BOM 不增减库存，也不会同步其他饰品。成本与售价独立维护，BOM 变化不会自动改变售价。</p>
      </template>
      <n-empty v-else-if="!loading && !pageError" description="未找到饰品" class="jd-empty" />
    </n-spin>

    <FloatingActionBar v-if="jewelry" aria-label="饰品操作">
      <FloatingActionButton v-if="canInventory" :disabled="locked" @click="openStock">查看库存</FloatingActionButton>
      <FloatingActionButton :disabled="locked" @click="confirmStatus">{{ jewelry.status === 'active' ? '停用饰品' : '启用饰品' }}</FloatingActionButton>
      <FloatingActionButton :disabled="locked" @click="openPrices">编辑价格</FloatingActionButton>
      <FloatingActionButton v-if="canParts" variant="primary" :disabled="!canAdd" @click="openAdd">＋ 添加配件</FloatingActionButton>
    </FloatingActionBar>

    <n-modal v-model:show="infoVisible" preset="card" title="编辑基本信息" class="jd-modal" :style="modalStyle" :mask-closable="!busy" :close-on-esc="!busy" :closable="!busy">
      <form @submit.prevent="saveInfo">
        <n-form label-placement="top" :disabled="busy">
          <n-form-item label="饰品名称" required><n-input v-model:value="infoForm.name" maxlength="120" placeholder="填写能区分款式的名称" /></n-form-item>
          <div class="jd-form-grid"><n-form-item label="饰品类目"><n-select v-model:value="infoForm.category" :options="categoryOptions" placeholder="请选择饰品类型" /></n-form-item><n-form-item label="计量单位"><n-select v-model:value="infoForm.unit" :options="unitOptions" placeholder="请选择计量单位" /></n-form-item></div>
          <n-form-item label="颜色"><n-input v-model:value="infoForm.color" placeholder="如：金色" /></n-form-item>
          <p class="jd-form-note">修改类目不会改变编号或单位；旧类目仅在你明确选择新类型后更新。</p>
          <n-alert v-if="unitChanged" type="warning" class="jd-alert">修改单位不会换算库存、价格、订单或 BOM。若计量基准发生变化，请先确认业务处理方案。<n-checkbox v-model:checked="unitConfirmed" class="jd-unit-confirm">我已确认单位修改，不需要系统自动换算</n-checkbox></n-alert>
        </n-form>
        <n-space justify="end"><n-button :disabled="busy" @click="infoVisible = false">取消</n-button><n-button type="primary" attr-type="submit" :loading="busy" :disabled="unitChanged && !unitConfirmed">保存</n-button></n-space>
      </form>
    </n-modal>
    <n-modal v-model:show="pricesVisible" preset="card" title="编辑价格" :style="modalStyle" :mask-closable="!busy" :close-on-esc="!busy" :closable="!busy">
      <form @submit.prevent="savePrices"><p class="jd-form-note">以下金额均按 1 {{ unitLabel }}饰品填写。留空表示未填写，0 表示明确为零。</p><n-form label-placement="top" :disabled="busy"><div class="jd-form-grid"><n-form-item label="零售价（元）"><n-input-number v-model:value="priceForm.retail_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" placeholder="未填写" /></n-form-item><n-form-item label="批发价（元）"><n-input-number v-model:value="priceForm.wholesale_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" placeholder="未填写" /></n-form-item></div><n-form-item :label="`手工费（元 / ${unitLabel}）`"><n-input-number v-model:value="priceForm.handcraft_cost" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" placeholder="未填写" /></n-form-item></n-form><n-space justify="end"><n-button :disabled="busy" @click="pricesVisible = false">取消</n-button><n-button type="primary" attr-type="submit" :loading="busy">保存</n-button></n-space></form>
    </n-modal>
    <n-modal v-model:show="addVisible" preset="card" title="添加配件" :style="modalStyle" :mask-closable="!busy" :close-on-esc="!busy" :closable="!busy">
      <form @submit.prevent="addBom"><p class="jd-form-note">仅添加到当前饰品的独立 BOM，不改变库存。</p><n-form label-placement="top" :disabled="busy"><n-form-item label="选择配件" required><n-select v-model:value="newPartId" :options="availableParts" :render-label="renderOptionWithImage" filterable clearable placeholder="搜索配件名称或编号" /></n-form-item><n-form-item :label="`每 1 ${unitLabel}饰品的用量${selectedPart?.unit ? `（${selectedPart.unit}）` : ''}`" required><n-input-number v-model:value="newQty" :min="0.0001" :max="999999.9999" :precision="4" placeholder="请输入用量" /></n-form-item></n-form><n-space justify="end"><n-button :disabled="busy" @click="addVisible = false">取消</n-button><n-button type="primary" attr-type="submit" :loading="busy" :disabled="!newPartId">确认添加</n-button></n-space></form>
    </n-modal>
    <n-modal v-model:show="stockVisible" preset="card" title="当前库存与流水" :style="{ width: isMobile ? '95vw' : '760px', maxWidth: '95vw' }">
      <p class="jd-form-note">{{ jewelry?.id }} · 当前库存 {{ stock == null ? '加载失败' : `${stock} ${unitLabel}` }} · 这里只读展示，不调整库存。</p>
      <n-spin :show="stockLoading"><n-alert v-if="stockLogError" type="error">库存流水加载失败，<n-button text type="primary" @click="loadStockLog">重新加载</n-button></n-alert><n-data-table v-else :columns="stockColumns" :data="stockLogs" :bordered="false" :pagination="{ pageSize: 20 }" :scroll-x="580" /></n-spin>
    </n-modal>
    <ImageUploadModal v-model:show="showImageModal" kind="jewelry" :entity-id="jewelry?.id" suppress-success @uploaded="(url) => saveImage('image', url)" />
    <ImageUploadModal v-model:show="showStructureImageModal" kind="jewelry" :entity-id="jewelry?.id ? jewelry.id + '-structure' : null" suppress-success @uploaded="(url) => saveImage('structure_image', url)" />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NCheckbox, NDataTable, NEmpty, NForm, NFormItem, NImage, NInput, NInputNumber, NModal, NPopconfirm, NSelect, NSpace, NSpin, useDialog, useMessage } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import { useAuthStore } from '@/stores/auth'
import { getJewelry, updateJewelry, updateJewelryStatus } from '@/api/jewelries'
import { getBom, setBom, deleteBom } from '@/api/bom'
import { getStock, getStockLog } from '@/api/inventory'
import { listParts } from '@/api/parts'
import { fmtMoney, fmtPrice, parseNum, renderOptionWithImage } from '@/utils/ui'
import { jewelryCategoryLabel, jewelryCategoryEditOptions, jewelryUnitOptions } from '@/utils/jewelryOptions'
import { bomSubtotal, filterJewelryBom, jewelryInfoPatch, jewelryPricePatch, validBomQuantity } from '@/utils/jewelryDetail'
import ImageUploadModal from '@/components/ImageUploadModal.vue'
import FloatingActionBar from '@/components/FloatingActionBar.vue'
import FloatingActionButton from '@/components/FloatingActionButton.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const message = useMessage()
const dialog = useDialog()
const { isMobile } = useIsMobile()
const canParts = computed(() => auth.hasPermission('parts'))
const canInventory = computed(() => auth.hasPermission('inventory'))
const jewelry = ref(null)
const bomRows = ref([])
const partMap = ref({})
const stock = ref(null)
const loading = ref(false)
const busy = ref(false)
const pageError = ref('')
const writeError = ref('')
const bomError = ref(false)
const partsError = ref(false)
const stockError = ref(false)
const bomReady = ref(false)
const partsReady = ref(false)
const bomKeyword = ref('')
const imageType = ref('product')
const showImageModal = ref(false)
const showStructureImageModal = ref(false)
const infoVisible = ref(false)
const pricesVisible = ref(false)
const addVisible = ref(false)
const stockVisible = ref(false)
const stockLoading = ref(false)
const stockLogError = ref(false)
const stockLogs = ref([])
const infoForm = reactive({ name: '', category: null, unit: null, color: '' })
const priceForm = reactive({ retail_price: null, wholesale_price: null, handcraft_cost: null })
const unitConfirmed = ref(false)
const newPartId = ref(null)
const newQty = ref(1)
let epoch = 0
let loadSequence = 0
let uploadTarget = null
const unitLabel = computed(() => jewelry.value?.unit || '计量单位')
const locked = computed(() => busy.value || loading.value || !!pageError.value || !!writeError.value)
const canAdd = computed(() => canParts.value && bomReady.value && partsReady.value && !locked.value)
const completeCost = computed(() => !pageError.value && !writeError.value && jewelry.value?.has_incomplete_cost === false && jewelry.value?.material_cost != null && jewelry.value?.total_cost != null)
const currentImage = computed(() => imageType.value === 'structure' ? jewelry.value?.structure_image : jewelry.value?.image)
const filteredBom = computed(() => filterJewelryBom(bomRows.value, bomKeyword.value))
const categoryOptions = computed(() => jewelryCategoryEditOptions(infoForm.category))
const unitOptions = computed(() => !infoForm.unit || jewelryUnitOptions.some((option) => option.value === infoForm.unit) ? jewelryUnitOptions : [{ label: infoForm.unit, value: infoForm.unit, disabled: true }, ...jewelryUnitOptions])
const unitChanged = computed(() => infoForm.unit !== jewelry.value?.unit)
const modalStyle = computed(() => ({ width: isMobile.value ? '95vw' : '500px', maxWidth: '95vw' }))
const availableParts = computed(() => Object.values(partMap.value).filter((part) => !bomRows.value.some((row) => row.part_id === part.id)).map((part) => ({ label: `${part.id} ${part.name}`, value: part.id, code: part.id, name: part.name, image: part.image })))
const selectedPart = computed(() => partMap.value[newPartId.value])
const price = (value) => value == null ? '—' : `¥ ${fmtMoney(value)}`
watch(() => infoForm.unit, () => { unitConfirmed.value = false })

async function loadPage() {
  const id = route.params.id
  const current = epoch
  const sequence = ++loadSequence
  loading.value = true
  try {
    const [item, bom, parts, inventory] = await Promise.allSettled([
      getJewelry(id),
      canParts.value ? getBom(id) : Promise.resolve(null),
      canParts.value ? listParts() : Promise.resolve(null),
      canInventory.value ? getStock('jewelry', id) : Promise.resolve(null),
    ])
    if (current !== epoch || sequence !== loadSequence) return false
    if (item.status !== 'fulfilled') {
      pageError.value = '无法取得最新饰品信息，请重新加载后再操作。'
      return false
    }
    jewelry.value = item.value.data
    pageError.value = ''
    writeError.value = ''
    partsReady.value = parts.status === 'fulfilled' && !!parts.value
    partsError.value = parts.status === 'rejected'
    partMap.value = Object.fromEntries((partsReady.value ? parts.value.data : []).map((part) => [part.id, part]))
    bomReady.value = bom.status === 'fulfilled' && !!bom.value
    bomError.value = bom.status === 'rejected'
    bomRows.value = (bomReady.value ? bom.value.data : []).map((row) => {
      const part = partMap.value[row.part_id]
      return { ...row, part_name: part?.name || row.part_id, part_image: part?.image, part_color: part?.color, part_unit: part?.unit, part_unit_cost: part?.unit_cost, part_is_composite: part?.is_composite, subtotal: bomSubtotal(part?.unit_cost, row.qty_per_unit), editQty: String(row.qty_per_unit) }
    })
    stock.value = inventory.status === 'fulfilled' && inventory.value ? inventory.value.data.current : null
    stockError.value = inventory.status === 'rejected'
    return !bomError.value && !partsError.value
  } finally {
    if (current === epoch && sequence === loadSequence) loading.value = false
  }
}

// Keep all totals server-authoritative; PATCH responses do not include costs.
async function mutate(action, success, afterSave = () => {}) {
  if (locked.value) return false
  const current = epoch
  busy.value = true
  try {
    await action()
    if (current !== epoch) return false
    afterSave()
    const refreshed = await loadPage()
    if (!refreshed) {
      if (current === epoch) writeError.value = '修改已保存，但最新资料未加载完整。请刷新核对，不要重复提交。'
      return false
    }
    message.success(success)
    return true
  } catch {
    if (current === epoch) {
      infoVisible.value = false; pricesVisible.value = false; addVisible.value = false
      writeError.value = '保存结果未能确认。请先刷新核对，再决定是否重试。'
    }
    return false
  } finally {
    if (current === epoch) busy.value = false
  }
}

function openInfo() {
  if (locked.value) return
  Object.assign(infoForm, { name: jewelry.value.name, category: jewelry.value.category, unit: jewelry.value.unit, color: jewelry.value.color || '' })
  unitConfirmed.value = false
  infoVisible.value = true
}
async function saveInfo() {
  let patch
  try { patch = jewelryInfoPatch(jewelry.value, infoForm) } catch (error) { message.warning(error.message); return }
  if (unitChanged.value && !unitConfirmed.value) { message.warning('请先确认单位修改不会自动换算业务数据'); return }
  if (!Object.keys(patch).length) { infoVisible.value = false; return }
  const id = jewelry.value.id
  await mutate(() => updateJewelry(id, patch), '基本信息已更新', () => { infoVisible.value = false })
}
function openPrices() {
  if (locked.value) return
  for (const key of Object.keys(priceForm)) priceForm[key] = jewelry.value[key]
  pricesVisible.value = true
}
async function savePrices() {
  let patch
  try { patch = jewelryPricePatch(jewelry.value, priceForm) } catch (error) { message.warning(error.message); return }
  if (!Object.keys(patch).length) { pricesVisible.value = false; return }
  const id = jewelry.value.id
  await mutate(() => updateJewelry(id, patch), '价格已更新', () => { pricesVisible.value = false })
}
function openAdd() { if (!canAdd.value) return; newPartId.value = null; newQty.value = 1; addVisible.value = true }
async function addBom() {
  if (!canAdd.value || !newPartId.value || !validBomQuantity(newQty.value)) { message.warning('请选择配件，用量须大于 0 且最多 4 位小数'); return }
  if (bomRows.value.some((row) => row.part_id === newPartId.value)) { message.warning('该配件已在 BOM 中，请直接修改原用量'); return }
  const id = jewelry.value.id
  const partId = newPartId.value
  const qty = newQty.value
  await mutate(() => setBom(id, partId, qty), '配件已加入 BOM', () => { addVisible.value = false; bomKeyword.value = '' })
}
async function saveQty(row) {
  if (Number(row.editQty) === Number(row.qty_per_unit)) { row.editQty = String(row.qty_per_unit); return }
  if (locked.value) { row.editQty = String(row.qty_per_unit); return }
  if (!validBomQuantity(row.editQty)) { message.warning('用量须大于 0，最多 4 位小数且小于 1000000'); row.editQty = String(row.qty_per_unit); return }
  const id = jewelry.value.id
  await mutate(() => setBom(id, row.part_id, Number(row.editQty)), '用量已更新')
}
async function doDeleteBom(row) {
  const id = jewelry.value.id
  await mutate(() => deleteBom(id, row.part_id), '已从当前 BOM 移除')
}
function confirmStatus() {
  if (locked.value) return
  const current = epoch
  const id = jewelry.value.id
  const status = jewelry.value.status === 'active' ? 'inactive' : 'active'
  dialog.warning({ title: status === 'inactive' ? '停用这件饰品？' : '重新启用饰品？', content: '仅修改启用状态，不删除饰品、BOM、库存或历史记录。', positiveText: '确认', negativeText: '取消', onPositiveClick: async () => {
    if (current === epoch) await mutate(() => updateJewelryStatus(id, status), '饰品状态已更新')
  } })
}
function openImageUpload() {
  if (locked.value) return
  uploadTarget = { id: jewelry.value.id, epoch }
  if (imageType.value === 'structure') showStructureImageModal.value = true; else showImageModal.value = true
}
async function saveImage(field, url) {
  if (!uploadTarget || uploadTarget.epoch !== epoch || uploadTarget.id !== jewelry.value?.id) return
  const id = uploadTarget.id
  // Only show a new image after the database has accepted the link.
  await mutate(() => updateJewelry(id, { [field]: url }), field === 'image' ? '饰品图片已更新' : '结构图已更新')
}
async function copyId() {
  try { await navigator.clipboard.writeText(jewelry.value.id); message.success('编号已复制') } catch { message.info(`饰品编号：${jewelry.value.id}`) }
}
async function openStock() { if (locked.value) return; stockVisible.value = true; await loadStockLog() }
async function loadStockLog() {
  const id = jewelry.value.id
  const current = epoch
  stockLoading.value = true
  stockLogError.value = false
  try {
    const [inventory, logs] = await Promise.all([getStock('jewelry', id), getStockLog('jewelry', id)])
    if (current !== epoch) return
    stock.value = inventory.data.current
    stockError.value = false
    stockLogs.value = [...logs.data].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)) || b.id - a.id)
  } catch { if (current === epoch) stockLogError.value = true } finally { if (current === epoch) stockLoading.value = false }
}
const stockColumns = [
  { title: '时间', key: 'created_at', width: 175, render: (row) => row.created_at?.replace('T', ' ').slice(0, 19) || '—' },
  { title: '变动数量', key: 'change_qty', width: 110, render: (row) => `${row.change_qty > 0 ? '+' : ''}${row.change_qty} ${unitLabel.value}` },
  { title: '原因', key: 'reason', minWidth: 100 },
  { title: '备注', key: 'note', minWidth: 160, render: (row) => row.note || '—' },
]
watch(() => route.params.id, () => {
  epoch++
  busy.value = false; bomReady.value = false; partsReady.value = false; uploadTarget = null
  jewelry.value = null
  pageError.value = ''; writeError.value = ''; bomRows.value = []; stock.value = null; bomKeyword.value = ''; imageType.value = 'product'
  infoVisible.value = false; pricesVisible.value = false; addVisible.value = false; stockVisible.value = false; showImageModal.value = false; showStructureImageModal.value = false
  loadPage()
}, { immediate: true })
function allowNavigation() {
  if (busy.value || showImageModal.value || showStructureImageModal.value) { message.warning('请等待保存完成，或先关闭图片上传窗口'); return false }
}
onBeforeRouteLeave(allowNavigation)
onBeforeRouteUpdate(allowNavigation)
onBeforeUnmount(() => { epoch++ })
</script>

<style scoped>
.jewelry-detail { min-width: 0; }
.jd-head { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin: 8px 0 22px; }
.jd-title { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.jd-title .page-title { margin: 0; overflow-wrap: anywhere; }
.jd-status { display: inline-flex; align-items: center; gap: 5px; color: #7C858C; background: #EBEDF0; border-radius: 20px; padding: 3px 10px; font-size: 11px; white-space: nowrap; }
.jd-status::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.jd-status.is-active { background: #E6F2EC; color: #1E7A5A; }
.jd-subtitle { display: flex; align-items: center; gap: 10px; margin-top: 7px; color: #8B9096; font-size: 11px; }
.jd-code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-variant-numeric: tabular-nums; }
.jd-copy { border: 0; background: transparent; color: #94A39A; padding: 0 3px; cursor: pointer; }
.jd-stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); background: #fff; border: 1px solid #ECEDEF; border-radius: 9px; overflow: hidden; margin-bottom: 25px; }
.jd-stat { padding: 15px 18px; border-right: 1px solid #ECEDEF; min-width: 0; }
.jd-stat:last-child { border-right: 0; }
.jd-stat-label, .jd-meta-label { font-size: 10px; color: #8B9096; margin-bottom: 6px; }
.jd-stat-value { font-size: 25px; font-weight: 700; line-height: 1.3; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.jd-stat-value small { font-size: 11px; font-weight: 400; color: #8B9096; margin-left: 4px; }
.jd-stat-value .jd-currency { font-size: 15px; margin: 0 3px 0 0; }
.jd-stat-note { font-size: 10px; color: #A4ABB1; margin-top: 5px; }
.is-green { color: #1E7A5A; }
.is-amber { color: #B7791F; }
.jd-section { margin-bottom: 26px; }
.jd-section-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; border-bottom: 1px solid #ECEDEF; padding-bottom: 10px; margin-bottom: 15px; }
.jd-section-head h3 { margin: 0; font-size: 11px; color: #8B9096; letter-spacing: .8px; font-weight: 700; }
.jd-section-title, .jd-section-actions { display: flex; align-items: center; gap: 8px; }
.jd-count { font-size: 10px; border-radius: 4px; padding: 1px 6px; color: #879199; background: #E9ECEF; }
.jd-hint { font-size: 10px; color: #939DA5; }
.jd-search { width: 190px; }
.jd-overview { display: grid; grid-template-columns: 240px minmax(0, 1fr); gap: 30px; }
.jd-image { border: 1px solid #E7E9E6; border-radius: 9px; background: #F0F2EF; overflow: hidden; min-height: 224px; display: flex; justify-content: center; align-items: center; }
.jd-image :deep(.n-image) { width: 100%; display: flex; justify-content: center; }
.jd-no-image { min-height: 224px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #8E9B92; font-size: 12px; }
.jd-no-image > span { font-size: 32px; color: #AFBDB2; }
.jd-no-image small { color: #A5AEA7; font-size: 10px; }
.jd-gallery-foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 9px; }
.jd-image-tabs { display: flex; gap: 5px; }
.jd-image-tabs button { cursor: pointer; background: #fff; border: 1px solid #E5E7E6; border-radius: 5px; padding: 3px 8px; font: inherit; font-size: 10px; color: #8B9096; }
.jd-image-tabs button[aria-pressed=true] { border-color: #87AD98; color: #1E7A5A; background: #F0F6F2; }
.jd-info { display: flex; flex-direction: column; min-width: 0; }
.jd-meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px 18px; padding: 8px 0 22px; }
.jd-meta-value { font-size: 13px; min-height: 20px; overflow-wrap: anywhere; }
.jd-meta-value small { color: #939DA5; font-size: 10px; }
.jd-unit { font-size: 11px; padding: 2px 8px; background: #EBEEEC; border-radius: 4px; }
.jd-info-note { margin-top: auto; padding-top: 14px; border-top: 1px solid #ECEDEF; font-size: 11px; color: #8B9690; line-height: 1.9; }
.jd-info-note strong { color: #4F6257; font-weight: 500; }
.jd-table-wrap { position: relative; border: 1px solid #ECEDEF; border-radius: 9px; overflow: auto; background: #fff; }
.jd-table { width: 100%; border-collapse: collapse; text-align: left; white-space: nowrap; font-size: 12px; }
.jd-table th { background: #FAFBFB; color: #8B9096; font-size: 10px; font-weight: 600; letter-spacing: .3px; padding: 11px 15px; }
.jd-table td { padding: 12px 15px; border-top: 1px solid #F0F1F2; }
.jd-table tbody tr:hover { background: #FAFCFA; }
.jd-table .jd-index { width: 35px; padding-right: 0; font-size: 10px; color: #AFB6B9; }
.jd-part { display: flex; align-items: center; gap: 10px; }
.jd-part :deep(.n-image) { border-radius: 6px; overflow: hidden; flex-shrink: 0; }
.jd-part-empty { display: grid; place-items: center; width: 38px; height: 38px; flex-shrink: 0; border-radius: 6px; border: 1px solid #E7E9E6; background: #F4F6F3; font-size: 10px; color: #A5AEA7; }
.jd-part-name { font-weight: 600; }
.jd-part-code { margin-top: 2px; color: #A5ADB4; font-size: 10px; }
.jd-composite { margin-left: 6px; color: #1E7A5A; background: #E6F2EC; padding: 1px 5px; font-size: 9px; border-radius: 4px; }
.jd-color-tag { font-size: 10px; border-radius: 4px; padding: 2px 6px; background: #F3F4F5; color: #89918D; }
.jd-qty { width: 80px; padding: 5px 7px; border: 1px solid transparent; border-radius: 5px; background: transparent; color: #1E7A5A; font: inherit; font-weight: 600; font-variant-numeric: tabular-nums; }
.jd-qty:hover:not(:disabled) { background: #F1F6F2; border-color: #D8E6DD; }
.jd-qty:focus { outline: 0; background: #fff; border-color: #1E7A5A; }
.jd-qty:disabled { opacity: .65; }
.jd-muted { color: #8B9096; }
.jd-table .jd-right { text-align: right; }
.jd-remove { display: inline-grid; place-items: center; border: 0; background: transparent; color: #9AA4AA; font: inherit; font-size: 16px; padding: 5px; cursor: pointer; }
.jd-remove:hover:not(:disabled) { color: #C64B4B; }
.jd-remove:disabled { cursor: not-allowed; opacity: .4; }
.jd-table tfoot td { background: #FAFBFB; padding-top: 13px; padding-bottom: 13px; }
.jd-total-label { font-size: 10px; color: #8E9991; }
.jd-table-note { display: flex; justify-content: space-between; gap: 12px; margin-top: 10px; font-size: 10px; color: #939DA5; }
.jd-empty { padding: 36px 18px; }
.jd-alert { margin-bottom: 12px; }
.jd-cost-notice { display: flex; gap: 9px; background: #FFF8EC; color: #A07836; padding: 10px 13px; border: 1px solid #F0E2C4; border-radius: 7px; font-size: 11px; margin-bottom: 12px; }
.jd-cost-strip { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; background: #EFF3F0; border: 1px solid #E3EAE4; border-radius: 8px; padding: 15px 18px; margin: 23px 0 17px; font-size: 11px; color: #708177; }
.jd-cost-strip > div { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; }
.jd-cost-strip b { color: #3F5749; font-weight: 600; }
.jd-cost-strip span { margin: 0 5px; color: #A0B0A5; }
.jd-cost-strip small { font-size: 10px; color: #939DA5; }
.jd-footer-note { font-size: 10px; color: #A0A8AD; margin-bottom: 13px; }
.jd-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px; }
.jd-form-grid :deep(.n-input-number) { width: 100%; }
.jd-form-note { font-size: 11px; color: #8E9992; line-height: 1.8; margin: 0 0 17px; }
.jd-unit-confirm { margin-top: 10px; display: flex; }
.jd-sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.jewelry-detail button:focus-visible { outline: 2px solid #1E7A5A; outline-offset: 3px; }
@media (max-width: 1200px) { .jd-stat { padding: 13px; } .jd-stat-value { font-size: 23px; } .jd-overview { grid-template-columns: 210px minmax(0, 1fr); gap: 23px; } .jd-meta { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 17px; padding-top: 0; } .jd-bom-hint { display: none; } }
@media (max-width: 760px) {
  .jewelry-detail > .page-breadcrumb { padding-left: 32px; }
  .jd-title .page-title { font-size: 22px; }
  .jd-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .jd-stat { border-bottom: 1px solid #ECEDEF; padding: 13px 12px; }
  .jd-stat:nth-child(3) { border-right: 0; }
  .jd-stat:nth-child(4), .jd-stat:nth-child(5) { border-bottom: 0; }
  .jd-stat:nth-child(5) { grid-column: span 2; }
  .jd-stat-value { font-size: 22px; }
  .jd-stat-note { font-size: 9px; }
  .jd-overview { grid-template-columns: minmax(0, 1fr); gap: 21px; }
  .jd-meta { gap: 19px 12px; padding-bottom: 17px; }
  .jd-meta-value { font-size: 12px; }
  .jd-image-tabs button { padding: 6px 12px; }
  .jd-section-actions { width: 100%; }
  .jd-search { flex: 1; width: 0; min-width: 0; }
  .jd-table { min-width: 760px; }
  .jd-table-note { flex-direction: column; gap: 4px; }
  .jd-cost-strip { padding: 13px; font-size: 10px; }
}
</style>

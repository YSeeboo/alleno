<template>
  <div ref="createForm" class="handcraft-create fulfillment-page">
    <div class="hcc-crumbs">生产管理 <span>/</span> 手工管理 <span>/</span> 新建</div>
    <header class="hcc-page-head"><div><div class="hcc-eyebrow">HANDCRAFT / CREATE</div><h1>新建手工单 <n-tag size="small" :bordered="false">草稿</n-tag></h1><p>先选好要做的产出，再核对交给商家的材料。</p></div><n-button :disabled="submitting || applyingOutputs" @click="goBack">← {{ summaryReturn ? '返回汇总' : '返回' }}</n-button></header>
    <n-alert v-if="catalogError" type="error" class="hcc-alert">商品或商家资料加载失败，已填写的内容保留，暂不能提交。<n-button text :disabled="submitting" @click="loadCatalog">重试加载</n-button></n-alert>
    <n-alert v-if="submitUncertain" type="warning" class="hcc-alert">保存结果未能确认，已暂停重复提交。请返回列表核对是否已创建或追加，勿直接再次创建。<n-button text :disabled="submitting" @click="goBack">返回核对</n-button></n-alert>
    <n-alert v-if="createdOrderId" type="success" class="hcc-alert">手工单 {{ createdOrderId }} 已保存，请勿重复提交。<n-button text @click="openCreated(`/handcraft/${createdOrderId}`)">查看手工单</n-button></n-alert>

    <div class="hcc-layout">
      <div class="hcc-main">
        <section class="hcc-panel" aria-labelledby="hcc-info-title">
          <header class="hcc-section-head"><h2 id="hcc-info-title"><span class="hcc-step">01</span>制作信息</h2><small>先确定交给谁做</small></header>
          <n-form label-placement="top" :show-feedback="false" :disabled="fieldsLocked" class="hcc-info-grid">
            <n-form-item label="手工商家" required><n-select v-model:value="supplierName" :options="supplierOptions" :loading="catalogLoading" filterable tag clearable placeholder="选择或输入手工商家名称" aria-label="手工商家" @update:value="onSupplierChange" /></n-form-item>
            <n-form-item label="创建日期（选填）"><n-date-picker v-model:value="createdAtTs" type="date" clearable :disabled="fieldsLocked || targetMode === 'append'" placeholder="留空使用当前时间" aria-label="创建日期" /></n-form-item>
            <n-form-item label="本单备注（选填）" class="hcc-note-field"><n-input v-model:value="note" placeholder="例如：本周优先制作，按款分袋" :input-props="{ 'aria-label': '本单备注', maxlength: 1000 }" /></n-form-item>
          </n-form>
          <div class="hcc-modes" role="group" aria-label="制作单处理方式"><label :class="{ selected: targetMode === 'new' }"><input type="radio" name="handcraft-mode" value="new" :checked="targetMode === 'new'" :disabled="fieldsLocked" @change="changeTargetMode('new')"><span><strong>新建独立手工单 <b>默认</b></strong><small>每次制作单独记录，不自动合单</small></span></label><label :class="{ selected: targetMode === 'append' }"><input type="radio" name="handcraft-mode" value="append" :checked="targetMode === 'append'" :disabled="fieldsLocked" @change="changeTargetMode('append')"><span><strong>追加已有手工单</strong><small>仅可追加同商家、待发出的单据</small></span></label></div>
          <HandcraftTargetPicker v-if="targetMode === 'append'" v-model="appendToOrderId" append-only :supplier-name="supplierName" :disabled="fieldsLocked" class="hcc-target" />
          <p class="hcc-hint hcc-info-foot">{{ targetMode === 'append' ? '追加只增加本次明细，沿用原单日期，不改写原明细。' : '日期留空使用当前时间。创建后为「待发出」，不会立即扣减库存。' }}</p>
        </section>

        <section class="hcc-panel" aria-labelledby="hcc-outputs-title">
          <header class="hcc-section-head"><div><h2 id="hcc-outputs-title"><span class="hcc-step">02</span>预期产出 <span class="hcc-count">{{ groups.length }} 款</span></h2><p>批量选择饰品与组合配件，数量一次填好。</p></div><n-button type="primary" :disabled="fieldsLocked || catalogLoading || catalogError" @click="openOutputPicker">＋ 批量选择产出</n-button></header>
          <div v-if="groups.length" class="hcc-output-table-head"><span>产出商品</span><span>预期数量 / 单位</span><span></span></div>
          <article v-for="group in groups" :key="outputKey(group)" class="hcc-output-row" :data-output="outputKey(group)">
            <div class="hcc-product"><n-image v-if="getOutputImage(group)" :src="getOutputImage(group)" :alt="getOutputLabel(group)" :width="45" :height="45" object-fit="cover" /><span v-else class="hcc-no-image" aria-hidden="true">◇</span><div><strong>{{ getOutputName(group) }}</strong><small>{{ group.jewelry_id || group.part_id }} <span class="hcc-kind" :class="{ part: group.output_type === 'part' }">{{ group.output_type === 'part' ? '组合配件' : '饰品' }}</span></small></div></div>
            <div class="hcc-output-edit"><div class="hcc-input-unit"><input type="number" :value="group.qty" min="1" step="1" :disabled="fieldsLocked" :aria-label="`${getOutputName(group)} 预期数量`" :aria-invalid="!handcraftInteger(group.qty)" placeholder="预期数量" @input="onOutputQtyChange(group, $event.target.value)"><select v-model="group.unit" :disabled="fieldsLocked" :aria-label="`${getOutputName(group)} 单位`"><option v-for="unit in outputUnits(group)" :key="unit" :value="unit">{{ unit }}</option></select></div><input v-model="group.note" class="hcc-row-note" :disabled="fieldsLocked" :aria-label="`${getOutputName(group)} 制作备注`" placeholder="＋ 制作备注" maxlength="500"></div>
            <n-button text class="hcc-remove" :disabled="fieldsLocked" :aria-label="`移除 ${getOutputName(group)}`" @click="removeGroup(group)">×</n-button>
          </article>
          <div v-if="!groups.length" class="hcc-empty"><span>◇</span><p>{{ catalogLoading ? '正在加载商品资料…' : '还没有选择产出' }}</p><small>从商品库一次勾选多款，也可以只补充发出材料。</small><n-button :disabled="fieldsLocked || catalogLoading || catalogError" @click="openOutputPicker">＋ 选择要制作的商品</n-button></div>
          <footer class="hcc-output-foot"><span>支持饰品与组合配件</span><span>改变数量后，自动用料随 BOM 联动</span></footer>
        </section>

        <section class="hcc-panel" aria-labelledby="hcc-materials-title">
          <header class="hcc-section-head"><div><h2 id="hcc-materials-title"><span class="hcc-step">03</span>发出材料 <span class="hcc-count">{{ allMaterialRows.length }} 行</span></h2><p>按产出展开 BOM，最终以「实际发出」为准。</p></div><n-button :disabled="fieldsLocked || catalogLoading || catalogError" @click="addExtra">＋ 补充材料</n-button></header>
          <div class="hcc-material-notice">↳ 自动用料随产出数量变化；<strong>手动调整的数量会保留</strong>，不会被覆盖。建议数量含备料余量，仅作参考。</div>
          <details v-for="group in groups" :key="outputKey(group)" class="hcc-material-group" open :data-material-group="outputKey(group)">
            <summary><strong>{{ getOutputName(group) }}</strong><span>× {{ handcraftInteger(group.qty) ? formatQty(group.qty) : '待填写' }} {{ group.unit }}</span><small>{{ group.parts.length }} 项材料</small></summary>
            <div v-if="group.bomState === 'loading'" class="hcc-bom-feedback">正在加载 BOM…</div>
            <div v-else-if="group.bomState === 'error'" class="hcc-bom-feedback is-error" role="alert">{{ group.bomError || 'BOM 加载失败，不能当作没有材料。' }} <n-button text type="primary" size="small" :disabled="fieldsLocked" @click="retryBom(group)">重试加载 BOM</n-button></div>
            <template v-else-if="group.parts.length">
              <div class="hcc-material-table-head"><span>发出配件</span><span>理论用量</span><span>建议数量</span><span>实际发出</span><span></span></div>
              <div v-for="(item, index) in group.parts" :key="item._key || index" class="hcc-material-row" :data-material="item.part_id">
                <div class="hcc-material-name"><strong>{{ getPartName(item.part_id) }}</strong><small>{{ item.part_id }}</small><input v-model="item.note" class="hcc-row-note" :disabled="fieldsLocked" :aria-label="`${getOutputName(group)} ${getPartName(item.part_id)} 发料备注`" placeholder="发料备注（选填）" maxlength="500"></div>
                <span class="hcc-theory">{{ formatQty(item.bom_qty) }} {{ item.unit }}</span><span class="hcc-suggestion" :title="getSuggestedTooltip(item)">{{ formatQty(getSuggestedQty(item)) }} {{ item.unit }}</span>
                <div class="hcc-actual"><div class="hcc-input-unit"><input type="number" :value="item.qty" min="0.0001" max="999999.9999" step="0.0001" :disabled="fieldsLocked" :aria-label="`${getOutputName(group)} ${getPartName(item.part_id)} 实际发出`" :aria-invalid="!handcraftQuantity(item.qty)" @input="setMaterialQty(item, $event.target.value)"><span>{{ item.unit }}</span></div><small :class="{ manual: item._manualQty || item._qty_per_unit == null }">{{ item._manualQty || item._qty_per_unit == null ? '手动调整' : 'BOM 自动' }} <button v-if="item._manualQty && item._qty_per_unit != null" type="button" :disabled="fieldsLocked" :aria-label="`恢复 ${getOutputName(group)} ${getPartName(item.part_id)} 自动数量`" @click="restoreMaterial(group, item)">恢复</button></small></div>
                <n-button text class="hcc-remove" :disabled="fieldsLocked" :aria-label="`移除 ${getOutputName(group)} 的材料 ${getPartName(item.part_id)}`" @click="group.parts.splice(index, 1)">×</n-button>
              </div>
            </template>
            <div v-else class="hcc-bom-feedback">{{ group.bomState === 'empty' ? '此商品尚未配置 BOM。' : '本组发料已移除。' }}如需发料，请使用「补充材料」填写；不会修改商品 BOM。</div>
          </details>
          <div v-if="!groups.length && !extras.length" class="hcc-empty hcc-material-empty">选择产出后自动生成 BOM 材料，也可以直接补充材料。</div>
          <div v-if="extras.length" class="hcc-extras"><header><h3>补充材料</h3><span>独立发料 · 不改 BOM</span></header><article v-for="(item, index) in extras" :key="item._key" class="hcc-extra-row">
            <div class="hcc-extra-name"><n-select :value="item.part_id" :options="partOptions" :render-label="renderOptionWithImage" :disabled="fieldsLocked" filterable clearable placeholder="选择补充配件" :aria-label="`补充材料 ${index + 1} 配件`" @update:value="value => onPartSelect(item, value)" /><input v-model="item.note" class="hcc-row-note" :disabled="fieldsLocked" :aria-label="`补充材料 ${index + 1} 备注`" placeholder="发料备注（选填）" maxlength="500"></div>
            <div class="hcc-input-unit"><input v-model="item.qty" type="number" min="0.0001" max="999999.9999" step="0.0001" :disabled="fieldsLocked" :aria-label="`补充材料 ${index + 1} 数量`" :aria-invalid="!handcraftQuantity(item.qty)"><select v-model="item.unit" :disabled="fieldsLocked" :aria-label="`补充材料 ${index + 1} 单位`"><option v-for="unit in materialUnits(item)" :key="unit" :value="unit">{{ unit }}</option></select></div><n-button text class="hcc-remove" :disabled="fieldsLocked" :aria-label="`移除补充材料 ${index + 1}`" @click="extras.splice(index, 1)">×</n-button>
          </article></div>
        </section>
        <p class="hcc-safe-note">ⓘ 这里只安排制作与发料，不代表客户预留、实际回收或已出货。</p>
      </div>

      <aside class="hcc-summary" aria-label="本次制作核对"><section class="hcc-panel"><div class="hcc-eyebrow">PRODUCTION SUMMARY</div><h2>本次制作</h2><strong class="hcc-summary-supplier">{{ supplierName || '尚未选择商家' }}</strong><p class="hcc-summary-mode">{{ targetMode === 'append' ? `追加至 ${appendToOrderId || '待选择的手工单'}` : '＋ 新建独立单 · 待发出' }}</p><div class="hcc-summary-label"><span>预期产出</span><span>{{ groups.length }} 款</span></div>
        <div class="hcc-summary-products"><div v-for="group in groups" :key="outputKey(group)" class="hcc-summary-product"><div>{{ getOutputName(group) }}<small>{{ group.jewelry_id || group.part_id }}</small></div><strong>{{ handcraftInteger(group.qty) ? formatQty(group.qty) : '待填写' }} {{ group.unit }}</strong></div><p v-if="!groups.length" class="hcc-hint">尚未选择产出</p></div>
        <div class="hcc-quantity-chips"><span v-for="entry in outputTotals" :key="entry.unit"><strong>{{ formatQty(entry.qty) }}</strong>{{ entry.unit }}</span></div><div class="hcc-summary-label"><span>实际发出材料</span><span>{{ materialKindCount }} 种 / {{ allMaterialRows.length }} 行</span></div><div class="hcc-material-totals"><span v-for="entry in materialTotals" :key="entry.unit"><strong>{{ formatQty(entry.qty) }}</strong> {{ entry.unit }}</span><span v-if="!materialTotals.length">尚无发出材料</span></div><p class="hcc-hint">{{ manualCount ? `${manualCount} 行手动调整 · ` : '' }}同配件分来源列示，不同单位分别汇总</p>
        <n-alert v-if="bomWarning" type="warning" :show-icon="false" class="hcc-summary-warning">{{ bomWarning }}</n-alert><n-button type="primary" block class="hcc-review-button" :disabled="locked || applyingOutputs || catalogLoading || catalogError" :loading="submitting" @click="review">核对制作单 →</n-button><p class="hcc-hint hcc-submit-hint">先保存为待发出，再在详情页确认发出</p>
      </section><p class="hcc-hint hcc-next-step">✓ 创建时不扣库存；追加仅增加本次新增明细，不自动合并或改写原明细。</p></aside>
    </div>
    <div v-if="isMobile" class="hcc-mobile-bar"><div><small>{{ groups.length }} 款产出 · {{ materialKindCount }} 种材料</small><strong>{{ totalsText(outputTotals) || '尚未选择产出' }}</strong></div><n-button type="primary" :disabled="locked || applyingOutputs || catalogLoading || catalogError" :loading="submitting" @click="review">核对制作单 →</n-button></div>

    <HandcraftOutputPicker v-if="outputPickerVisible" :products="outputProducts" :initial="groups" :busy="applyingOutputs" :apply-error="outputApplyError" @close="outputPickerVisible = false" @confirm="confirmOutputs" />
    <n-modal v-model:show="reviewVisible" preset="card" title="核对本次制作" class="hcc-review-modal" :style="reviewStyle" :content-style="reviewContentStyle" :mask-closable="!submitting" :close-on-esc="!submitting" :closable="!submitting">
      <div class="hcc-review-info"><strong>{{ supplierName }}</strong> · {{ targetMode === 'append' ? `追加 ${appendToOrderId}` : '新建独立手工单' }}<small>日期：{{ targetMode === 'append' ? '沿用原单日期' : tsToDateStr(createdAtTs) || '使用当前时间' }} · 不自动合单 · 不扣库存</small></div>
      <h3 class="hcc-review-heading">预期产出 · {{ groups.length }} 款</h3><div v-for="group in groups" :key="outputKey(group)" class="hcc-review-row"><div><strong>{{ getOutputName(group) }}</strong><small>{{ group.jewelry_id || group.part_id }}{{ group.note ? ` · ${group.note}` : '' }}</small></div><strong>{{ formatQty(group.qty) }} {{ group.unit }}</strong></div><p v-if="!groups.length" class="hcc-hint">本单仅发出材料，未选择预期产出。</p>
      <div v-for="group in groups" :key="`review-${outputKey(group)}`"><h3 class="hcc-review-heading">{{ getOutputName(group) }} · 发出材料</h3><div v-for="(item, index) in group.parts" :key="index" class="hcc-review-row"><div>{{ getPartName(item.part_id) }}<small>{{ item.part_id }} · {{ item._manualQty || item._qty_per_unit == null ? '手动数量' : 'BOM 自动' }}{{ item.note ? ` · ${item.note}` : '' }}</small></div><strong>{{ formatQty(item.qty) }} {{ item.unit }}</strong></div><p v-if="!group.parts.length" class="hcc-hint">本款未单独发料，请核对独立补充材料。</p></div>
      <h3 v-if="extras.length" class="hcc-review-heading">独立补充材料</h3><div v-for="item in extras" :key="item._key" class="hcc-review-row"><div>{{ getPartName(item.part_id) }}<small>{{ item.part_id }}{{ item.note ? ` · ${item.note}` : '' }}</small></div><strong>{{ formatQty(item.qty) }} {{ item.unit }}</strong></div>
      <h3 class="hcc-review-heading">实际发出合计</h3><p>{{ totalsText(materialTotals) }}</p><p v-if="note" class="hcc-hint">备注：{{ note }}</p><n-alert type="info" :show-icon="false" class="hcc-review-notice">只保存制作安排，状态为待发出。请在详情页单独确认发出；此处不会预留客户库存、扣减库存或直接出货。</n-alert>
      <n-alert v-if="submitUncertain" type="warning" class="hcc-review-notice">保存结果未能确认，勿重复创建。请返回核对手工单。</n-alert>
      <template #footer><n-space justify="end"><n-button :disabled="submitting" @click="reviewVisible = false">返回修改</n-button><n-button type="primary" :loading="submitting" :disabled="locked || applyingOutputs" @click="submit">{{ targetMode === 'append' ? '确认追加到手工单' : '确认创建手工单' }}</n-button></n-space></template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useHandcraftSummaryReturn } from '@/composables/useHandcraftSummaryReturn'
import { useMessage, useDialog, NAlert, NSpace, NButton, NSelect, NInput, NForm, NFormItem, NDatePicker, NTag, NImage, NModal } from 'naive-ui'
import { listParts, getPartBom } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { getBom } from '@/api/bom'
import { createHandcraft } from '@/api/handcraft'
import { listSuppliers, createSupplier } from '@/api/suppliers'
import HandcraftTargetPicker from '@/components/fulfillment/HandcraftTargetPicker.vue'
import HandcraftOutputPicker from '@/components/handcraft/HandcraftOutputPicker.vue'
import { renderOptionWithImage } from '@/utils/ui'
import { tsToDateStr } from '@/utils/date'
import { useIsMobile } from '@/composables/useIsMobile'
import { handcraftOutputKey as outputKey, handcraftInteger, handcraftQuantity, handcraftUnitTotals, makeHandcraftGroup, handcraftBomRows, updateHandcraftGroupQuantity, restoreHandcraftMaterial, handcraftBufferRule, handcraftSuggestedQty, handcraftCreateError } from '@/utils/handcraftCreate'

const { summaryReturn, goBack, openCreated } = useHandcraftSummaryReturn()
const message = useMessage(), dialog = useDialog()
const { isMobile } = useIsMobile()
const supplierName = ref(null), appendToOrderId = ref(null), targetMode = ref('new'), supplierOptions = ref([])
const note = ref(''), createdAtTs = ref(null), createForm = ref(null)
const groups = reactive([]), extras = reactive([])
const submitting = ref(false), submitUncertain = ref(false), createdOrderId = ref(null), reviewVisible = ref(false)
const partOptions = ref([]), jewelryOptions = ref([]), catalogLoading = ref(false), catalogError = ref(false)
const outputPickerVisible = ref(false), applyingOutputs = ref(false), outputApplyError = ref('')
const locked = computed(() => submitting.value || submitUncertain.value || !!createdOrderId.value)
const fieldsLocked = computed(() => locked.value || applyingOutputs.value || reviewVisible.value || outputPickerVisible.value)
const outputProducts = computed(() => [
  ...jewelryOptions.value.map(row => ({ ...row, id: row.value, kind: 'jewelry', key: `jewelry:${row.value}` })),
  ...partOptions.value.filter(row => row.is_composite).map(row => ({ ...row, id: row.value, kind: 'part', key: `part:${row.value}` })),
])
const allMaterialRows = computed(() => [...groups.flatMap(group => group.parts), ...extras])
const materialKindCount = computed(() => new Set(allMaterialRows.value.filter(row => row.part_id).map(row => row.part_id)).size)
const outputTotals = computed(() => handcraftUnitTotals(groups.filter(group => handcraftInteger(group.qty))))
const materialTotals = computed(() => handcraftUnitTotals(allMaterialRows.value.filter(row => row.part_id && handcraftQuantity(row.qty))))
const manualCount = computed(() => allMaterialRows.value.filter(item => item._manualQty || item._qty_per_unit == null).length)
const bomWarning = computed(() => groups.some(group => group.bomState === 'error') ? '部分 BOM 加载失败，请重试，暂不能提交。' : groups.some(group => group.bomState === 'loading') ? '正在加载 BOM，请稍候。' : groups.some(group => !handcraftInteger(group.qty)) ? '产出数量待填写，请输入正整数。' : allMaterialRows.value.some(item => !handcraftQuantity(item.qty)) ? '请检查实际发出数量，须大于 0 且最多四位小数。' : groups.some(group => group.bomState === 'empty') ? '有商品尚无 BOM，请核对是否需要补充材料。' : '')
const reviewStyle = { width: '660px', maxWidth: 'calc(100vw - 24px)', maxHeight: '90dvh', display: 'flex', flexDirection: 'column' }
const reviewContentStyle = { minHeight: '0', overflow: 'auto', flex: '1' }
let alive = true, extraSerial = 0, loadSequence = 0
const formatQty = value => value == null || value === '' ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
const totalsText = entries => entries.map(entry => `${formatQty(entry.qty)} ${entry.unit}`).join(' / ')
const getOutputOption = group => (group.output_type === 'part' ? partOptions.value : jewelryOptions.value).find(row => row.value === (group.output_type === 'part' ? group.part_id : group.jewelry_id))
const getOutputImage = group => getOutputOption(group)?.image || null
const getOutputName = group => getOutputOption(group)?.name || group.jewelry_id || group.part_id || '未选择'
const getOutputLabel = group => getOutputOption(group)?.label || '未选择'
const getPartName = id => partOptions.value.find(row => row.value === id)?.name || id || '未选择'
const outputUnits = group => [...new Set([group.unit, '个', '条', '套', '对', '件'].filter(Boolean))]
const materialUnits = item => [...new Set([item.unit, '个', '条', '米', 'g', 'kg'].filter(Boolean))]
const getSuggestedQty = item => handcraftSuggestedQty(item, partOptions.value.find(row => row.value === item.part_id))
const getSuggestedTooltip = item => {
  const { tier, ratio, floor, overridden } = handcraftBufferRule(partOptions.value.find(row => row.value === item.part_id))
  return `${tier === 'medium' ? '中件' : '小件'}${overridden ? '（自定义）' : '规则'}：ceil(理论用量) + ceil(max(${floor}, 理论用量 × ${Number((ratio * 100).toFixed(4))}%))。仅作参考，不自动替代实际发料。`
}
function onSupplierChange() { appendToOrderId.value = null }
function changeTargetMode(mode) { if (!fieldsLocked.value) { targetMode.value = mode; appendToOrderId.value = null } }
function onPartSelect(item, value) {
  item.part_id = value
  item.unit = partOptions.value.find(row => row.value === value)?.unit || '个'
  item._qty_per_unit = null
}
function setMaterialQty(item, value) { item.qty = value; item._manualQty = true }
const onOutputQtyChange = (group, value) => updateHandcraftGroupQuantity(group, value)
const restoreMaterial = (group, item) => restoreHandcraftMaterial(group, item)
function addExtra() { if (!fieldsLocked.value) extras.push({ _key: `extra:${++extraSerial}`, part_id: null, qty: 1, unit: '个', bom_qty: null, _qty_per_unit: null, _manualQty: true, note: '' }) }
function removeGroup(group) {
  if (fieldsLocked.value) return
  dialog.warning({ title: '移除这款产出？', content: `「${getOutputName(group)}」关联的 BOM 发料及手动调整会一起移除，其他产出与补充材料不受影响。`, positiveText: '确认移除', negativeText: '保留', onPositiveClick: () => {
    if (fieldsLocked.value) return false
    const index = groups.indexOf(group)
    if (index >= 0) groups.splice(index, 1)
  } })
}
async function loadGroupBom(group) {
  const identity = outputKey(group)
  group.bomState = 'loading'; group.bomError = ''
  try {
    const { data } = group.output_type === 'part' ? await getPartBom(group.part_id) : await getBom(group.jewelry_id)
    if (!alive || outputKey(group) !== identity) return
    if (!Array.isArray(data)) throw Error('无效 BOM 响应')
    group.parts = handcraftBomRows(group, data, partOptions.value)
    group.bomState = data.length ? 'ready' : 'empty'
  } catch (_) {
    if (alive && outputKey(group) === identity) { group.bomState = 'error'; group.bomError = 'BOM 加载失败，请重试；不会按无 BOM 提交。' }
  }
}
async function retryBom(group) { if (!fieldsLocked.value && group.bomState === 'error') await loadGroupBom(group) }
function openOutputPicker() {
  if (fieldsLocked.value || catalogLoading.value || catalogError.value) return
  if (groups.some(group => group.bomState === 'loading')) { message.warning('正在加载 BOM，请稍候再选择产出'); return }
  outputApplyError.value = ''; outputPickerVisible.value = true
}
async function confirmOutputs(rows) {
  if (applyingOutputs.value || locked.value) return
  if (groups.some(group => group.bomState === 'loading')) { outputApplyError.value = '正在加载 BOM，请稍候再更新清单'; return }
  if (!rows.length || rows.some(row => !handcraftInteger(row.qty) || !row.unit?.trim() || !outputProducts.value.some(product => product.key === row.product?.key)) || new Set(rows.map(row => row.product.key)).size !== rows.length) {
    outputApplyError.value = '请检查选择的产出、数量与单位'; return
  }
  applyingOutputs.value = true; outputApplyError.value = ''
  try {
    const next = rows.map(row => {
      const current = groups.find(group => outputKey(group) === row.product.key)
      // Copies contain editable draft data only; never mutate the main draft before all reads finish.
      const group = current ? JSON.parse(JSON.stringify(current)) : makeHandcraftGroup(row.product, row)
      group.unit = row.unit.trim(); group.note = row.note || ''
      onOutputQtyChange(group, Number(row.qty))
      return { group, needsBom: !current }
    })
    // A bounded queue avoids a request per selected product being launched at once.
    const pending = next.filter(row => row.needsBom)
    let cursor = 0
    await Promise.all(Array.from({ length: Math.min(4, pending.length) }, async () => {
      while (cursor < pending.length && alive) { const current = pending[cursor++]; await loadGroupBom(current.group) }
    }))
    if (!alive) return
    groups.splice(0, groups.length, ...next.map(row => row.group))
    outputPickerVisible.value = false
    message.success('已更新制作清单，请核对 BOM 发料')
  } finally { applyingOutputs.value = false }
}
function normalizedParts() {
  return allMaterialRows.value.filter(item => item.part_id).map(item => ({ part_id: item.part_id, qty: Number(item.qty), unit: item.unit.trim(), bom_qty: item.bom_qty, note: item.note }))
}
const normalizedJewelries = () => groups.filter(group => group.jewelry_id || group.part_id).map(group => ({ [group.output_type === 'part' ? 'part_id' : 'jewelry_id']: group.output_type === 'part' ? group.part_id : group.jewelry_id, qty: Number(group.qty), unit: group.unit.trim(), note: group.note }))
async function commitInputs() {
  const activeInput = document.activeElement
  if (createForm.value?.contains(activeInput)) activeInput.blur()
  await nextTick()
}
function validationError() {
  if (catalogLoading.value || catalogError.value) return '商品资料尚未加载完整，请先重试加载'
  return handcraftCreateError({ supplier: supplierName.value, mode: targetMode.value, target: appendToOrderId.value, groups, extras })
}
async function review() {
  if (locked.value || applyingOutputs.value || outputPickerVisible.value) return
  await commitInputs()
  const error = validationError()
  if (error) { message.warning(error); createForm.value?.querySelector?.('[aria-invalid="true"]')?.focus(); return }
  reviewVisible.value = true
}
const submit = async () => {
  if (locked.value || applyingOutputs.value) return
  // Keep the blur + tick boundary for date/select controls and alternative submit methods.
  await commitInputs()
  if (locked.value || applyingOutputs.value) return
  const error = validationError()
  if (error) { message.warning(error); return }
  const validParts = normalizedParts(), validJewelries = normalizedJewelries()
  submitting.value = true
  const supplier = supplierName.value.trim()
  let createStarted = false
  try {
    if (!supplierOptions.value.some(option => option.value === supplier)) {
      try { await createSupplier({ name: supplier, type: 'handcraft' }) } catch (error) { if (error.response?.status !== 400) throw error }
      supplierOptions.value.push({ label: supplier, value: supplier })
    }
    const payload = { supplier_name: supplier, parts: validParts, jewelries: validJewelries, note: note.value, append_to_order_id: appendToOrderId.value }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt && !appendToOrderId.value) payload.created_at = createdAt
    createStarted = true
    const { data } = await createHandcraft(payload)
    if (!data?.id) throw Error('创建结果未包含单号')
    createdOrderId.value = data.id
    reviewVisible.value = false
    message.success(appendToOrderId.value ? `已追加到 ${data.id}` : '已新建独立手工单')
    openCreated(`/handcraft/${data.id}`)
  } catch (error) {
    if (createdOrderId.value) { message.warning('手工单已保存，可点击「查看手工单」，请勿重复创建'); return }
    if (createStarted && ![400, 401, 403, 404, 409, 422].includes(error.response?.status)) {
      submitUncertain.value = true
      message.warning('保存结果未能确认，请返回核对手工单，勿重复提交')
    } else message.error(typeof error.response?.data?.detail === 'string' ? error.response.data.detail : '未能保存，请检查后重试')
  } finally { submitting.value = false }
}
async function loadCatalog() {
  if (catalogLoading.value || submitting.value) return
  const sequence = ++loadSequence
  catalogLoading.value = true; catalogError.value = false
  try {
    const [parts, jewelries, suppliers] = await Promise.all([listParts(), listJewelries({ status: 'active' }), listSuppliers({ type: 'handcraft' })])
    if (!alive || sequence !== loadSequence) return
    const options = data => data.map(row => ({ ...row, label: `${row.id} ${row.name}`, value: row.id, code: row.id }))
    partOptions.value = options(parts.data)
    jewelryOptions.value = options(jewelries.data.filter(row => row.status === 'active' || row.status == null))
    supplierOptions.value = suppliers.data.map(row => ({ label: row.name, value: row.name }))
  } catch (_) { if (alive && sequence === loadSequence) catalogError.value = true }
  finally { if (alive && sequence === loadSequence) catalogLoading.value = false }
}
onMounted(loadCatalog)
onBeforeUnmount(() => { alive = false; ++loadSequence })
onBeforeRouteLeave(() => { if ((submitting.value && !createdOrderId.value) || applyingOutputs.value) { message.warning('正在处理，请稍候'); return false } })
</script>

<style scoped>
.handcraft-create { max-width:1400px; margin:0 auto; color:#303d37; --hcc-line:#e1e7df; --hcc-green:#1e7a5a; }
.hcc-crumbs { font-size:11px; color:#859181; margin:3px 0 24px; }.hcc-crumbs span { padding:0 10px; color:#b5c0ac; }
.hcc-page-head { display:flex; justify-content:space-between; gap:15px; align-items:center; margin-bottom:28px; }.hcc-eyebrow { font-size:9px; letter-spacing:1.6px; color:#8f9f82; }
.hcc-page-head h1 { display:flex; align-items:center; gap:14px; font-size:28px; font-weight:650; margin:5px 0 9px; letter-spacing:-.6px; }.hcc-page-head p { margin:0; color:#819078; font-size:12px; }
.hcc-layout { display:grid; grid-template-columns:minmax(0,1fr) 275px; gap:23px; align-items:start; }.hcc-main { display:flex; flex-direction:column; gap:20px; min-width:0; }
.hcc-panel { background:white; border:1px solid var(--hcc-line); border-radius:9px; overflow:hidden; }
.hcc-section-head { display:flex; justify-content:space-between; gap:12px; align-items:center; padding:20px 22px; }.hcc-section-head h2 { display:flex; align-items:center; gap:9px; font-size:15px; font-weight:600; margin:0; }
.hcc-step { width:23px; height:23px; background:#f0f5eb; border-radius:5px; color:#8aa177; display:grid; place-items:center; font-size:10px; font-weight:500; }.hcc-count { font-size:11px; color:#809571; background:#f1f5ed; border-radius:4px; padding:1px 6px; font-weight:400; }
.hcc-section-head>small { font-size:11px; color:#99a48f; }.hcc-section-head p { font-size:11px; color:#8a997f; margin:6px 0 0 32px; }
.hcc-info-grid { display:grid; grid-template-columns:1fr 1fr; gap:17px; padding:0 22px 20px; }.hcc-info-grid :deep(.n-form-item-label) { font-size:12px; color:#6b7b61; padding-bottom:7px; }.hcc-info-grid :deep(.n-date-picker) { width:100%; }.hcc-note-field { grid-column:1/-1; }
.hcc-modes { display:grid; grid-template-columns:1fr 1fr; gap:12px; padding:0 22px; }.hcc-modes label { display:flex; gap:9px; align-items:flex-start; border:1px solid var(--hcc-line); border-radius:6px; padding:12px; cursor:pointer; }
.hcc-modes label.selected { border-color:#afc6a2; background:#f6faf2; }.hcc-modes input { accent-color:var(--hcc-green); margin:4px 0 0; width:15px; height:15px; flex-shrink:0; }
.hcc-modes strong { font-size:12px; font-weight:500; }.hcc-modes b { font-size:9px; font-weight:400; color:#8fa47a; margin-left:5px; }.hcc-modes small { display:block; color:#8e9d80; font-size:10px; margin-top:4px; }
.hcc-hint { color:#8d9c80; font-size:11px; line-height:1.8; margin:9px 0 0; }.hcc-info-foot { padding:0 22px 18px; }.hcc-target { margin:15px 22px 0; padding:13px; background:#f7faf3; border-radius:6px; }
.hcc-target :deep(label) { font-size:12px; color:#697e5c; }.hcc-target :deep(small) { font-size:11px; }
.hcc-output-row,.hcc-output-table-head { display:grid; grid-template-columns:minmax(0,1fr) 170px 24px; gap:14px; align-items:center; padding:17px 22px; border-top:1px solid #edf0e8; }
.hcc-output-table-head { background:#fafcf7; padding-block:8px; font-size:11px; color:#94a187; }.hcc-product { display:flex; align-items:center; gap:12px; min-width:0; }
.hcc-product>div { min-width:0; overflow-wrap:anywhere; }.hcc-product strong { font-size:13px; font-weight:550; }.hcc-product small { display:block; font-size:11px; color:#91a080; margin-top:4px; }
.hcc-product :deep(img) { border-radius:6px; }.hcc-no-image { display:grid; place-items:center; width:45px; height:45px; border-radius:6px; background:#f0f4eb; color:#9bae89; font-size:24px; flex-shrink:0; }
.hcc-kind { font-size:9px; border:1px solid #e0e7d9; border-radius:3px; padding:1px 4px; margin-left:5px; background:#f8faf5; color:#899e75; white-space:nowrap; }.hcc-kind.part { color:#a08e70; background:#faf7f1; border-color:#ece4d5; }
.hcc-input-unit { display:flex; align-items:center; border:1px solid #dce5d5; border-radius:5px; height:37px; overflow:hidden; background:white; }
.hcc-input-unit input { min-width:0; width:100%; border:0; background:transparent; color:inherit; font:inherit; font-size:13px; font-weight:550; padding:7px 9px; outline-offset:-2px; }
.hcc-input-unit select { min-width:0; width:50px; flex:0 0 50px; border:0; border-left:1px solid #ebf0e3; padding:6px; background:#fafcf7; color:#7b8e6a; font:inherit; font-size:11px; outline-offset:-2px; }
.hcc-input-unit>span { flex-shrink:0; color:#8d9e7d; font-size:10px; padding-right:8px; }.hcc-input-unit:focus-within { border-color:#78a486; }
.hcc-input-unit:has(input[aria-invalid=true]) { border-color:#c28c67; background:#fffcf5; }.hcc-input-unit input:disabled,.hcc-input-unit select:disabled { opacity:.65; cursor:not-allowed; }
.hcc-row-note { width:100%; min-width:0; box-sizing:border-box; font:inherit; font-size:11px; color:#879d74; border:0; border-radius:3px; padding:5px 0; background:transparent; }
.hcc-row-note::placeholder { color:#a0ae92; }.hcc-remove { color:#9ba98f; font-size:20px; }.hcc-output-foot { display:flex; justify-content:space-between; gap:8px; padding:12px 22px; font-size:10px; color:#92a183; background:#fcfef9; border-top:1px solid #edf1e7; }
.hcc-empty { padding:30px 20px; text-align:center; color:#8c9d7c; font-size:12px; }.hcc-empty>span { display:block; font-size:30px; color:#a6b997; }.hcc-empty p { margin:6px 0; }.hcc-empty small { display:block; font-size:11px; color:#a0ad94; }.hcc-empty :deep(.n-button) { margin-top:17px; }
.hcc-material-notice { margin:0 22px 17px; background:#f4f8ee; border:1px solid #e9efdf; padding:10px 12px; font-size:11px; line-height:1.8; color:#8a9b77; border-radius:5px; }.hcc-material-notice strong { font-weight:550; color:#6c8b58; }
.hcc-material-group { border-top:1px solid #e5ecde; }.hcc-material-group summary { display:flex; align-items:center; gap:8px; background:#fafcf7; padding:14px 22px; cursor:pointer; list-style:none; font-size:12px; }.hcc-material-group summary::-webkit-details-marker { display:none; }
.hcc-material-group summary::before { content:'›'; color:#96a987; font-size:17px; }.hcc-material-group[open] summary::before { transform:rotate(90deg); }.hcc-material-group summary strong { font-weight:550; overflow-wrap:anywhere; }.hcc-material-group summary>span { font-size:10px; color:#829874; background:#f0f5e9; padding:1px 5px; border-radius:3px; white-space:nowrap; }
.hcc-material-group summary small { margin-left:auto; font-size:10px; color:#9aa98b; white-space:nowrap; }
.hcc-material-row,.hcc-material-table-head { display:grid; grid-template-columns:minmax(0,1fr) 76px 76px 126px 18px; gap:10px; align-items:center; padding:13px 22px 13px 35px; }.hcc-material-table-head { padding-block:12px 4px; font-size:10px; color:#a0ad92; }.hcc-material-table-head>span:not(:first-child) { text-align:right; }
.hcc-material-row { border-bottom:1px solid #f0f3e9; }.hcc-material-row:last-child { border-bottom:0; }.hcc-material-name { min-width:0; overflow-wrap:anywhere; }.hcc-material-name strong { font-size:12px; font-weight:400; }.hcc-material-name>small { display:block; color:#9aab8b; font-size:10px; }.hcc-material-name .hcc-row-note { font-size:10px; }
.hcc-theory,.hcc-suggestion { color:#8b9d7c; font-size:11px; text-align:right; }.hcc-suggestion { color:#ab9871; cursor:help; }
.hcc-actual .hcc-input-unit { height:34px; }.hcc-actual input { text-align:right; padding-right:4px; }.hcc-actual>small { display:flex; justify-content:flex-end; align-items:center; gap:5px; font-size:9px; color:#97aa85; min-height:20px; }.hcc-actual>small.manual { color:#ab8d5b; }.hcc-actual button { background:transparent; border:0; color:var(--hcc-green); font:inherit; padding:0; cursor:pointer; }
.hcc-bom-feedback { font-size:12px; padding:18px 22px; color:#a28f64; background:#fffcf5; line-height:1.9; }.hcc-bom-feedback.is-error { color:#b2744d; }.hcc-material-empty { font-size:11px; }
.hcc-extras { border-top:1px solid #e7eddf; }.hcc-extras>header { display:flex; justify-content:space-between; align-items:center; padding:17px 22px 0; }.hcc-extras h3 { font-size:12px; font-weight:550; margin:0; }.hcc-extras>header span { font-size:10px; color:#93a282; }
.hcc-extra-row { display:grid; grid-template-columns:minmax(0,1fr) 150px 24px; gap:12px; align-items:center; padding:15px 22px; border-bottom:1px solid #edf2e5; }.hcc-extra-name { min-width:0; }.hcc-safe-note { color:#93a187; font-size:11px; margin:0; }
.hcc-summary { position:sticky; top:18px; min-width:0; }.hcc-summary>.hcc-panel { padding:23px 21px 18px; }.hcc-summary h2 { font-size:19px; font-weight:550; margin:6px 0 23px; }.hcc-summary-supplier { font-size:13px; font-weight:550; }.hcc-summary-mode { font-size:11px; color:#8d9f7b; margin:5px 0 23px; overflow-wrap:anywhere; }
.hcc-summary-label { display:flex; justify-content:space-between; gap:9px; font-size:11px; color:#90a17e; margin:17px 0 13px; }.hcc-summary-products { max-height:280px; overflow:auto; scrollbar-width:thin; }.hcc-summary-product { display:flex; justify-content:space-between; align-items:start; gap:10px; font-size:12px; margin-bottom:13px; }.hcc-summary-product>div { min-width:0; overflow-wrap:anywhere; }.hcc-summary-product small { display:block; font-size:10px; color:#9aab8b; margin-top:3px; }.hcc-summary-product>strong { font-weight:550; white-space:nowrap; }
.hcc-quantity-chips { display:flex; flex-wrap:wrap; gap:7px; padding:6px 0 18px; border-bottom:1px solid #e2e9db; }.hcc-quantity-chips span { font-size:10px; background:#f0f6e9; color:#7d9b66; padding:4px 8px; border-radius:4px; }.hcc-quantity-chips strong { font-size:18px; font-weight:550; color:#547d40; margin-right:3px; }
.hcc-material-totals { display:flex; flex-wrap:wrap; gap:6px 15px; font-size:11px; color:#88a06f; }.hcc-material-totals strong { font-weight:550; color:#5f7d4e; }.hcc-summary-warning { margin-top:15px; font-size:11px; }.hcc-review-button { margin-top:23px; height:40px; }.hcc-submit-hint { text-align:center; font-size:10px; }.hcc-next-step { padding:7px 12px; font-size:10px; }
.hcc-mobile-bar { display:none; }.hcc-alert { margin-bottom:16px; }
.hcc-review-info { padding:14px 16px; background:#f4f8ee; border-radius:6px; font-size:13px; color:#688554; }.hcc-review-info small { display:block; font-size:11px; color:#8b9f78; margin-top:6px; }.hcc-review-heading { font-size:13px; font-weight:550; margin:22px 0 7px; }.hcc-review-row { display:flex; justify-content:space-between; gap:12px; padding:12px 0; border-bottom:1px solid #edf2e6; font-size:12px; }.hcc-review-row>div { min-width:0; overflow-wrap:anywhere; }.hcc-review-row strong { font-weight:550; }.hcc-review-row>strong { white-space:nowrap; }.hcc-review-row small { display:block; font-size:10px; color:#92a37f; margin-top:4px; }.hcc-review-notice { margin-top:18px; font-size:12px; }
input:focus-visible,select:focus-visible,button:focus-visible,summary:focus-visible { outline:2px solid var(--hcc-green); outline-offset:2px; }
@media(max-width:1190px) { .hcc-layout { grid-template-columns:minmax(0,1fr) 235px; gap:16px; }.hcc-summary>.hcc-panel { padding-inline:16px; }.hcc-section-head { padding-inline:17px; }.hcc-output-row,.hcc-output-table-head { padding-inline:17px; grid-template-columns:minmax(0,1fr) 138px 20px; gap:9px; }.hcc-material-row,.hcc-material-table-head { grid-template-columns:minmax(0,1fr) 57px 57px 103px 16px; gap:8px; padding-inline:22px 15px; }.hcc-product { gap:9px; }.hcc-modes { padding-inline:17px; gap:10px; }.hcc-modes label { padding:10px; }.hcc-modes small { font-size:9px; } }
@media(min-width:769px) and (max-width:1100px) {
  .hcc-layout { grid-template-columns:minmax(0,1fr); }.hcc-summary { position:static; }
}
@media(max-width:768px) {
  .handcraft-create { padding-bottom:100px; }.hcc-crumbs { font-size:10px; margin-bottom:21px; }.hcc-page-head { margin-bottom:22px; gap:10px; }.hcc-page-head h1 { font-size:24px; }.hcc-page-head p { font-size:11px; max-width:245px; line-height:1.8; }.hcc-page-head :deep(.n-button) { font-size:11px; }
  .hcc-layout { display:flex; flex-direction:column; gap:17px; }.hcc-main,.hcc-summary { width:100%; }.hcc-main { gap:15px; }.hcc-summary { position:static; }.hcc-summary .hcc-review-button,.hcc-submit-hint,.hcc-next-step { display:none; }
  .hcc-section-head { padding:17px 14px; gap:7px; }.hcc-section-head h2 { font-size:14px; gap:7px; }.hcc-section-head>small { font-size:10px; }.hcc-section-head p { font-size:10px; margin-left:0; max-width:190px; }.hcc-section-head :deep(.n-button) { font-size:11px; height:39px; padding-inline:10px; }.hcc-step { width:21px; height:21px; font-size:9px; }.hcc-count { font-size:10px; }
  .hcc-info-grid { padding:0 14px 18px; gap:15px 10px; }.hcc-info-grid :deep(.n-form-item-label) { font-size:11px; }.hcc-modes { padding-inline:14px; gap:9px; }.hcc-modes label { padding:10px 8px; gap:6px; }.hcc-modes strong { font-size:11px; }.hcc-modes b { display:none; }.hcc-modes small { font-size:9px; line-height:1.8; }.hcc-modes input { width:13px; height:13px; }.hcc-info-foot { padding:0 14px 16px; font-size:10px; }.hcc-target { margin-inline:14px; }
  .hcc-output-table-head { display:none; }.hcc-output-row { grid-template-columns:minmax(0,1fr) 25px; gap:11px; padding:16px 14px; }.hcc-product { grid-column:1; grid-row:1; }.hcc-output-row>.hcc-remove { grid-column:2; grid-row:1; }.hcc-output-edit { grid-column:1/-1; display:grid; grid-template-columns:145px minmax(0,1fr); gap:12px; align-items:center; }.hcc-input-unit { height:41px; }.hcc-input-unit input { font-size:15px; }.hcc-input-unit select { font-size:11px; }.hcc-output-foot { flex-wrap:wrap; padding:11px 14px; font-size:10px; gap:3px; }.hcc-output-foot span:last-child { width:100%; }
  .hcc-material-notice { margin:0 14px 15px; font-size:10px; padding:10px; }.hcc-material-group summary { padding:13px 14px; font-size:11px; gap:6px; }.hcc-material-group summary>span { font-size:9px; }.hcc-material-group summary small { font-size:9px; }
  .hcc-material-table-head { display:none; }.hcc-material-row { grid-template-columns:minmax(0,1fr) 110px 16px; gap:0 9px; padding:12px 14px 12px 23px; }.hcc-material-name { grid-column:1; grid-row:1; }.hcc-material-name strong { font-size:12px; }.hcc-material-name>small { font-size:9px; }.hcc-material-name .hcc-row-note { padding:2px 0; font-size:9px; }.hcc-theory { grid-column:1; grid-row:2; text-align:left; font-size:10px; margin-top:3px; }.hcc-theory::before { content:'理论 '; }.hcc-suggestion { display:none; }.hcc-actual { grid-column:2; grid-row:1/3; }.hcc-material-row>.hcc-remove { grid-column:3; grid-row:1/3; }.hcc-actual .hcc-input-unit { height:40px; }.hcc-actual>small { font-size:9px; min-height:24px; }.hcc-actual button { min-height:24px; }
  .hcc-bom-feedback { padding:16px; font-size:11px; }.hcc-extras>header { padding-inline:14px; }.hcc-extra-row { grid-template-columns:minmax(0,1fr) 120px 18px; gap:8px; padding-inline:14px; }.hcc-extra-row .hcc-input-unit select { width:43px; flex-basis:43px; padding:4px; }.hcc-extra-row .hcc-input-unit input { font-size:13px; padding-inline:6px; }.hcc-extra-name .hcc-row-note { font-size:10px; }
  .hcc-summary>.hcc-panel { padding:21px; }.hcc-summary h2 { font-size:18px; margin-bottom:18px; }.hcc-safe-note { font-size:10px; }
  .hcc-mobile-bar { position:fixed; bottom:0; inset-inline:0; z-index:20; display:flex; justify-content:space-between; align-items:center; gap:12px; padding:12px 18px calc(12px + env(safe-area-inset-bottom)); background:#fffffff5; border-top:1px solid #dce6d3; box-shadow:0 -5px 25px #29421c08; backdrop-filter:blur(8px); }.hcc-mobile-bar>div { display:flex; flex-direction:column; min-width:0; }.hcc-mobile-bar small { font-size:10px; color:#94a580; }.hcc-mobile-bar strong { font-size:14px; font-weight:550; color:#628148; overflow-wrap:anywhere; }.hcc-mobile-bar :deep(.n-button) { min-height:42px; font-size:12px; flex-shrink:0; }
}
</style>

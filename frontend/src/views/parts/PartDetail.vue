<template>
  <div class="part-detail-page">
    <!-- Page Top -->
    <div class="page-top">
      <button class="back-btn" @click="router.back()">← 返回</button>
      <div class="page-crumbs">商品 / 配件管理 / 配件详情</div>
      <div v-if="part" class="title-row">
        <div class="title-l">
          <h1 class="page-title">{{ part.name }}</h1>
          <span class="id-chip">{{ part.id }}</span>
          <span v-if="part.category" class="cat-tag">{{ part.category }}</span>
          <span class="root-tag" :class="{ 'variant-tag': part.parent_part_id }">
            {{ part.parent_part_id ? '变体' : '根件' }}
          </span>
        </div>
      </div>
      <div v-else-if="!loading" class="title-row">
        <div class="title-l"><h1 class="page-title">配件详情</h1></div>
      </div>
    </div>

    <n-spin :show="loading">
      <!-- Stat Strip (4 cards) -->
      <div v-if="part" class="stat-strip">
        <div class="stat-card">
          <div class="stat-label">当前库存</div>
          <div class="stat-value" :class="{ 'stat-danger': stock < 10 }">{{ stock }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">单件成本</div>
          <div class="stat-value">
            <template v-if="part.unit_cost != null">¥{{ fmtMoney(part.unit_cost) }}</template>
            <template v-else>-</template>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">子配件</div>
          <div class="stat-value">{{ partBomList.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">变体</div>
          <div class="stat-value">{{ variantCount }}</div>
        </div>
      </div>

      <template v-if="part">
        <!-- 基本信息 -->
        <div class="sec">
          <div class="sec-h">
            <span class="t">基本信息</span>
            <span class="r-acts">
              <button class="sbtn" @click="openEdit">✎ 编辑</button>
            </span>
          </div>
          <div class="kv">
            <div class="f"><span class="k">编号</span><span class="v mono">{{ part.id }}</span></div>
            <div class="f"><span class="k">配件</span><span class="v">{{ part.name }}</span></div>
            <div class="f">
              <span class="k">图片</span>
              <span class="v">
                <n-image
                  v-if="part.image"
                  :src="part.image"
                  :alt="part.name"
                  :width="44"
                  :height="44"
                  object-fit="cover"
                  style="border-radius: 8px; border: 1px solid #ECEDEF; overflow: hidden; display: block; cursor: zoom-in;"
                />
                <span v-else style="color: #AEB3B8; font-size: 13px;">无图</span>
              </span>
            </div>
            <div class="f"><span class="k">类目</span><span class="v">{{ part.category || '-' }}</span></div>
            <div class="f">
              <span class="k">颜色</span>
              <span class="v">
                <template v-if="part.color">
                  <span class="color-dot" :style="{ background: badgeOfLabel[part.color] || '#c0c6cd' }"></span>{{ part.color }}
                </template>
                <span v-else>-</span>
              </span>
            </div>
            <div class="f"><span class="k">单位</span><span class="v">{{ part.unit || '-' }}</span></div>
            <div class="f"><span class="k">默认电镀工艺</span><span class="v">{{ part.plating_process || '-' }}</span></div>
            <div class="f">
              <span class="k">组合件</span>
              <span class="v">
                <span v-if="part.is_composite" class="badge-combo">是</span>
                <span v-else class="badge-no">否</span>
              </span>
            </div>
            <div class="f">
              <span class="k">关联原色配件</span>
              <span class="v">
                <router-link v-if="part.parent_part_id" :to="`/parts/${part.parent_part_id}`" class="link">
                  {{ parentPartName || part.parent_part_id }}
                </router-link>
                <span v-else style="color: #AEB3B8;">— (本件即根件)</span>
              </span>
            </div>
            <div class="f kv-full">
              <span class="k">单件成本</span>
              <span class="v">
                <template v-if="part.unit_cost != null">
                  <span class="cost">¥ {{ fmtMoney(part.unit_cost) }}</span>
                  <span v-if="costBreakdown" class="cost-bd">({{ costBreakdown }})</span>
                  <n-popover
                    v-if="costLogs.length > 0"
                    trigger="hover"
                    placement="bottom-start"
                    :style="{ maxWidth: '520px' }"
                  >
                    <template #trigger>
                      <span class="price-hist">📋 价格历史 · {{ costLogs.length }} 条</span>
                    </template>
                    <div :style="{ minWidth: isMobile ? 'auto' : '460px' }">
                      <div style="font-weight: 600; font-size: 13px; margin-bottom: 8px; color: #333;">价格变动历史</div>
                      <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <thead>
                          <tr style="border-bottom: 1px solid #f0f0f0;">
                            <th style="padding: 6px 8px; text-align: left; font-weight: 500; color: #666;">时间</th>
                            <th style="padding: 6px 8px; text-align: left; font-weight: 500; color: #666;">当前价格</th>
                            <th style="padding: 6px 8px; text-align: left; font-weight: 500; color: #666;">变动</th>
                            <th style="padding: 6px 8px; text-align: left; font-weight: 500; color: #666;">原因</th>
                            <th style="padding: 6px 8px; text-align: left; font-weight: 500; color: #666;">来源</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="log in costLogs" :key="log.id" style="border-bottom: 1px solid #f5f5f5;">
                            <td style="padding: 6px 8px; color: #999; font-size: 12px;">
                              {{ new Date(log.created_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) }}
                              {{ new Date(log.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}
                            </td>
                            <td style="padding: 6px 8px; font-weight: 500;">¥ {{ fmtMoney(log.unit_cost_after) }}</td>
                            <td style="padding: 6px 8px;">
                              <span :style="{ color: (log.unit_cost_after - log.unit_cost_before) >= 0 ? '#1E7A5A' : '#E5484D', fontWeight: 600 }">
                                {{ (log.unit_cost_after - log.unit_cost_before) >= 0 ? '+' : '' }}{{ fmtMoney(log.unit_cost_after - log.unit_cost_before) }}
                              </span>
                            </td>
                            <td style="padding: 6px 8px;">
                              <span style="background: #f5f5f5; padding: 2px 8px; border-radius: 4px; font-size: 11px; color: #666;">
                                {{ COST_FIELD_LABELS[log.field] || log.field }}
                              </span>
                            </td>
                            <td style="padding: 6px 8px;">
                              <router-link
                                v-if="sourceRoute(log.source_id)"
                                :to="sourceRoute(log.source_id)"
                                style="color: #1E7A5A; font-size: 12px;"
                              >
                                {{ log.source_id }}
                              </router-link>
                              <span v-else style="color: #999; font-size: 12px;">{{ log.source_id || '-' }}</span>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </n-popover>
                </template>
                <span v-else>-</span>
              </span>
            </div>
          </div>
        </div>

        <!-- 变体家族 -->
        <div v-if="variantFamily.length > 1" class="sec">
          <div class="sec-h">
            <span class="t">变体家族</span>
            <span class="cnt">{{ variantFamily.length }} 个成员</span>
          </div>
          <table class="fam-table">
            <thead>
              <tr>
                <th style="width: 30%;">颜色</th>
                <th>编号</th>
                <th class="r" style="width: 120px;">单件成本</th>
                <th class="r" style="width: 90px;">库存</th>
                <th style="width: 60px;"></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in variantFamily"
                :key="row.id"
                class="vrow"
                :class="{ cur: row.id === partId }"
              >
                <td>
                  <span class="color-dot" :style="{ background: badgeOfLabel[row.color] || '#c0c6cd' }"></span>
                  {{ row.color || '-' }}
                  <span v-if="row.parent_part_id == null" class="fam-root-tag">根</span>
                  <span v-if="row.id === partId" class="cur-tag">· 当前</span>
                </td>
                <td class="cell-id mono">{{ row.id }}</td>
                <td class="r mono">{{ row.unit_cost != null ? '¥' + fmtMoney(row.unit_cost) : '-' }}</td>
                <td class="r">
                  <span v-if="(familyStocks[row.id] ?? 0) < 10" class="stock-low mono">{{ familyStocks[row.id] ?? 0 }}</span>
                  <span v-else class="mono">{{ familyStocks[row.id] ?? 0 }}</span>
                </td>
                <td>
                  <button
                    v-if="row.id !== partId"
                    class="go-btn"
                    @click="router.push('/parts/' + row.id)"
                  >→</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 子配件 BOM -->
        <div class="sec">
          <div class="sec-h">
            <span class="t">子配件 BOM</span>
            <span class="cnt">{{ partBomList.length }} 项</span>
            <span class="r-acts">
              <button class="sbtn" @click="showCopyBom = !showCopyBom">📋 复制其他配件 BOM</button>
            </span>
          </div>

          <!-- Copy BOM source selector -->
          <div v-if="showCopyBom" style="margin-bottom: 14px; display: flex; align-items: center; gap: 10px;">
            <n-select
              filterable
              clearable
              placeholder="选择源配件，复制其 BOM 到待添加列表"
              :options="childPartOptions"
              :render-label="renderOptionWithImage"
              :style="{ width: isMobile ? '100%' : '360px' }"
              @update:value="(v) => { if (v) copyBomFrom(v) }"
            />
            <button class="sbtn" @click="showCopyBom = false">取消</button>
          </div>

          <!-- Existing BOM table -->
          <n-data-table v-if="partBomList.length > 0" :columns="bomColumns" :data="partBomList" :bordered="false" />
          <n-empty v-else description="暂无子配件 BOM" style="margin: 16px 0;" />

          <!-- Batch add panel -->
          <div class="addpanel">
            <div class="addpanel-h">批量添加子配件</div>
            <n-select
              v-model:value="batchSelectVal"
              filterable
              clearable
              placeholder="搜索并选择配件（可多次选择）"
              :options="stageableOptions"
              :render-label="renderOptionWithImage"
              style="width: 100%;"
              @update:value="(val, opt) => { if (opt) stagePart(opt) }"
            />

            <!-- Staging table -->
            <table v-if="staged.length > 0" class="staging" style="margin-top: 12px;">
              <thead>
                <tr>
                  <th>子配件</th>
                  <th style="width: 150px;">每单位用量</th>
                  <th style="width: 50px;"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in staged" :key="row.child_part_id">
                  <td>
                    <div style="display: flex; align-items: center; gap: 9px;">
                      <img
                        v-if="row.child_part_image"
                        :src="row.child_part_image"
                        style="width: 32px; height: 32px; border-radius: 6px; object-fit: cover; border: 1px solid #ECEDEF; flex-shrink: 0;"
                      />
                      <div v-else style="width: 32px; height: 32px; border-radius: 6px; background: #F4F5F6; flex-shrink: 0;"></div>
                      <div>
                        <div style="font-size: 13px; color: #1A1D21;">{{ row.child_part_name }}</div>
                        <div style="font-size: 11px; color: #8B9096; font-variant-numeric: tabular-nums;">{{ row.child_part_id }}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <n-input-number
                      v-model:value="row.qty_per_unit"
                      :min="0.01"
                      :precision="4"
                      style="width: 120px;"
                    />
                  </td>
                  <td>
                    <n-button size="small" type="error" @click="unstage(i)">×</n-button>
                  </td>
                </tr>
              </tbody>
            </table>

            <div class="addpanel-f">
              <span class="addpanel-hint">{{ staged.length > 0 ? staged.length + ' 项待添加' : '从上方搜索添加配件' }}</span>
              <n-button :disabled="staged.length === 0" @click="staged = []">清空</n-button>
              <n-button
                type="primary"
                :loading="batchSubmitting"
                :disabled="staged.length === 0"
                @click="submitBatch"
              >批量添加 {{ staged.length }} 项</n-button>
            </div>
          </div>
        </div>

        <!-- 库存流水 (eyebrow style) -->
        <div class="sec sec-last">
          <div class="sec-h">
            <span class="t">库存流水</span>
            <span class="cnt">{{ logs.length }} 条</span>
          </div>
          <n-data-table v-if="logs.length > 0" :columns="logColumns" :data="logs" :bordered="false" />
          <n-empty v-else description="暂无流水" style="margin: 16px 0;" />
        </div>
      </template>

      <template v-else-if="!loading">
        <n-empty description="配件不存在" style="margin: 60px 0;" />
      </template>
    </n-spin>

    <!-- Edit basic-info modal -->
    <n-modal
      v-model:show="showEdit"
      preset="card"
      title="编辑基本信息"
      :style="{ width: isMobile ? '95vw' : '540px' }"
    >
      <n-form ref="editFormRef" :model="editForm" label-placement="top">
        <div class="modal-grid2">
          <div class="modal-full">
            <n-form-item label="名称" path="name" :rule="{ required: true, message: '请输入名称' }">
              <n-input v-model:value="editForm.name" />
            </n-form-item>
          </div>
          <div class="modal-full">
            <n-form-item label="类目">
              <span style="font-size: 14px; color: #1A1D21;">{{ editForm.category || '-' }}</span>
              <span class="modal-note">类目不可修改</span>
            </n-form-item>
          </div>
          <n-form-item label="颜色">
            <n-input v-model:value="editForm.color" :disabled="editingIsVariant" />
            <span v-if="editingIsVariant" class="modal-note">变体不可修改</span>
          </n-form-item>
          <n-form-item label="单位">
            <n-select v-model:value="editForm.unit" :options="unitOptions" placeholder="请选择单位" />
          </n-form-item>
          <n-form-item label="规格">
            <n-input v-model:value="editForm.spec" placeholder="如 45cm" />
          </n-form-item>
          <n-form-item label="默认电镀工艺">
            <n-input v-model:value="editForm.plating_process" />
          </n-form-item>
        </div>

        <div class="modal-sec-h">单件成本明细</div>
        <div class="modal-grid2">
          <n-form-item label="采购费用">
            <n-input-number v-model:value="editForm.purchase_cost" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width: 100%;" />
          </n-form-item>
          <n-form-item label="穿珠费用">
            <n-input-number v-model:value="editForm.bead_cost" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width: 100%;" />
          </n-form-item>
          <n-form-item label="电镀费用">
            <n-input-number v-model:value="editForm.plating_cost" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width: 100%;" />
          </n-form-item>
        </div>

        <div class="modal-sec-h">图片</div>
        <n-form-item label="">
          <div class="modal-img-row">
            <n-image
              v-if="editForm.image"
              :src="editForm.image"
              alt="配件图片"
              :width="48"
              :height="48"
              object-fit="cover"
              class="modal-img-preview"
            />
            <div v-else class="modal-img-placeholder"></div>
            <n-input v-model:value="editForm.image" placeholder="上传后自动填充，也可手动粘贴 URL" style="flex: 1;" />
            <n-button class="modal-upload-btn" @click="showImageModal = true">上传图片</n-button>
          </div>
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showEdit = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="saveBasicInfo">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <ImageUploadModal
      v-model:show="showImageModal"
      kind="part"
      :entity-id="partId"
      @uploaded="onImageUploaded"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, h, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import {
  NSpin, NDataTable, NSpace, NButton, NEmpty, NImage, NPopover,
  NSelect, NInputNumber, NPopconfirm,
  NModal, NForm, NFormItem, NInput,
} from 'naive-ui'
import {
  getPart, updatePart, getPartCostLogs, listParts, getPartBom, setPartBom, deletePartBom,
  getPartVariants, getColorVariants, setPartBomBatch,
} from '@/api/parts'
import { getStock, getStockLog, batchGetStock } from '@/api/inventory'
import { fmtMoney, fmtPrice, parseNum, renderNamedImage, renderOptionWithImage } from '@/utils/ui'
import ImageUploadModal from '@/components/ImageUploadModal.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const { isMobile } = useIsMobile()

const loading = ref(true)
const part = ref(null)
const parentPartName = ref('')
const stock = ref(0)
const logs = ref([])
const costLogs = ref([])
const partId = computed(() => route.params.id)

// Sub-parts BOM
const partBomList = ref([])
const childPartOptions = ref([])
// Batch add state (Task 3)
const staged = ref([])          // [{ child_part_id, child_part_name, child_part_image, qty_per_unit }]
const batchSubmitting = ref(false)
const batchSelectVal = ref(null)
const showCopyBom = ref(false)

// Color variants for dot display
const colorVariants = ref([])
const badgeOfLabel = computed(() => Object.fromEntries(colorVariants.value.map(c => [c.label, c.badge])))

// Batch staging — exclude self + existing BOM + already staged
const stageableOptions = computed(() => {
  const taken = new Set([...partBomList.value.map(b => b.child_part_id), ...staged.value.map(s => s.child_part_id)])
  return childPartOptions.value.filter(o => !taken.has(o.value))
})

// Variant family
const variantFamily = ref([])
const variantCount = computed(() => Math.max(0, variantFamily.value.length - 1))
const familyStocks = ref({})

// Edit state
const showEdit = ref(false)
const saving = ref(false)
const editFormRef = ref(null)
const editForm = reactive({
  category: '',
  name: '',
  color: '',
  unit: '个',
  spec: '',
  purchase_cost: null,
  bead_cost: null,
  plating_cost: null,
  plating_process: '',
  image: '',
})
const editingIsVariant = computed(() => !!(part.value && part.value.parent_part_id))

// Image upload (within edit modal)
const showImageModal = ref(false)
const onImageUploaded = (url) => {
  editForm.image = url
}

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const COST_FIELD_LABELS = {
  purchase_cost: '采购费用更新',
  bead_cost: '穿珠费用更新',
  plating_cost: '电镀费用更新',
}

const costBreakdown = computed(() => {
  if (!part.value) return null
  const { purchase_cost, bead_cost, plating_cost } = part.value
  if (purchase_cost == null && bead_cost == null && plating_cost == null) return null
  const parts = []
  if (purchase_cost != null && purchase_cost !== 0) parts.push(`采购 ${fmtMoney(purchase_cost)}`)
  if (bead_cost != null && bead_cost !== 0) parts.push(`穿珠 ${fmtMoney(bead_cost)}`)
  if (plating_cost != null && plating_cost !== 0) parts.push(`电镀 ${fmtMoney(plating_cost)}`)
  return parts.length > 0 ? parts.join(' + ') : null
})

const sourceRoute = (sourceId) => {
  if (!sourceId) return null
  if (sourceId.startsWith('CG-')) return `/purchase-orders/${sourceId}`
  if (sourceId.startsWith('ER-')) return `/plating-receipts/${sourceId}`
  if (sourceId.startsWith('HR-')) return `/handcraft-receipts/${sourceId}`
  return null
}

const logColumns = [
  { title: '时间', key: 'created_at', render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
  {
    title: '变动数量',
    key: 'change_qty',
    render: (r) =>
      h('span', { style: { color: r.change_qty > 0 ? '#1E7A5A' : '#E5484D', fontWeight: 600 } },
        (r.change_qty > 0 ? '+' : '') + r.change_qty
      ),
  },
  { title: '原因', key: 'reason' },
  { title: '备注', key: 'note', render: (r) => r.note || '-' },
]

const loadPartBom = async () => {
  try {
    const { data } = await getPartBom(partId.value)
    partBomList.value = data.map((b) => ({ ...b, editQty: null }))
  } catch (_) {
    partBomList.value = []
  }
}

function stagePart(opt) {
  if (!opt) return
  staged.value.push({ child_part_id: opt.value, child_part_name: opt.name, child_part_image: opt.image, qty_per_unit: 1 })
  nextTick(() => { batchSelectVal.value = null })
}
function unstage(i) { staged.value.splice(i, 1) }
async function submitBatch() {
  if (staged.value.length === 0) return
  batchSubmitting.value = true
  try {
    await setPartBomBatch(partId.value, staged.value.map(s => ({ child_part_id: s.child_part_id, qty_per_unit: s.qty_per_unit })))
    message.success(`已添加 ${staged.value.length} 项`)
    staged.value = []
    await loadPartBom()
  } catch (e) { message.error(e.response?.data?.detail || '批量添加失败') }
  finally { batchSubmitting.value = false }
}
async function copyBomFrom(sourceId) {
  if (!sourceId) return
  const { data } = await getPartBom(sourceId)
  const taken = new Set([...partBomList.value.map(b => b.child_part_id), ...staged.value.map(s => s.child_part_id)])
  for (const b of data) {
    if (b.child_part_id === partId.value || taken.has(b.child_part_id)) continue
    staged.value.push({ child_part_id: b.child_part_id, child_part_name: b.child_part_name, child_part_image: b.child_part_image, qty_per_unit: b.qty_per_unit })
    taken.add(b.child_part_id)
  }
  message.success('已预填到待添加列表，可微调后提交')
  showCopyBom.value = false
}

const saveBomQty = async (row) => {
  if (!row.editQty || row.editQty === row.qty_per_unit) { row.editQty = null; return }
  await setPartBom(partId.value, {
    child_part_id: row.child_part_id,
    qty_per_unit: row.editQty,
  })
  message.success('已更新')
  row.qty_per_unit = row.editQty
  row.editQty = null
}

const doDeletePartBom = async (row) => {
  await deletePartBom(row.id)
  message.success('已删除')
  await loadPartBom()
}

const bomColumns = [
  { title: '子配件编号', key: 'child_part_id', width: 160 },
  {
    title: '子配件',
    key: 'child_part_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.child_part_name, row.child_part_image, row.child_part_name, 40, row.child_is_composite ? '组合' : null),
  },
  {
    title: '每单位用量',
    key: 'qty_per_unit',
    render: (row) =>
      h('input', {
        value: row.editQty ?? row.qty_per_unit,
        type: 'number',
        min: 0.001,
        step: 0.001,
        style: 'width: 80px; border: 1px solid #ccc; border-radius: 4px; padding: 2px 6px;',
        onInput: (e) => { row.editQty = parseFloat(e.target.value) },
        onBlur: () => saveBomQty(row),
      }),
  },
  {
    title: '操作',
    key: 'actions',
    render: (row) =>
      h(NPopconfirm, { onPositiveClick: () => doDeletePartBom(row) }, {
        trigger: () => h(NButton, { size: 'small', type: 'error' }, () => '删除'),
        default: () => `确认删除子配件 ${row.child_part_name} 的BOM配置？`,
      }),
  },
]

async function loadVariantFamily() {
  try {
    const { data: fam } = await getPartVariants(partId.value)
    if (part.value && part.value.parent_part_id == null) {
      variantFamily.value = [part.value, ...fam]      // 根件: fam 仅变体
    } else {
      variantFamily.value = fam                        // 变体: fam 含根+全部变体
    }
    variantFamily.value.sort((a, b) => a.id.localeCompare(b.id))
    if (variantFamily.value.length > 0) {
      const ids = variantFamily.value.map(p => p.id)
      const { data: smap } = await batchGetStock('part', ids)
      familyStocks.value = smap
    }
  } catch (_) {
    variantFamily.value = []
  }
}

const openEdit = () => {
  if (!part.value) return
  const p = part.value
  Object.assign(editForm, {
    category: p.category || '',
    name: p.name || '',
    color: p.color || '',
    unit: p.unit || '个',
    spec: p.spec || '',
    purchase_cost: p.purchase_cost ?? null,
    bead_cost: p.bead_cost ?? null,
    plating_cost: p.plating_cost ?? null,
    plating_process: p.plating_process || '',
    image: p.image || '',
  })
  showEdit.value = true
}

async function saveBasicInfo() {
  await editFormRef.value?.validate()
  saving.value = true
  try {
    const { category, ...data } = editForm
    if (editingIsVariant.value) {
      delete data.color
    }
    await updatePart(partId.value, data)
    message.success('已保存')
    const { data: fresh } = await getPart(partId.value)
    part.value = fresh
    // 成本可能变 → 刷新价格历史
    getPartCostLogs(partId.value).then(r => { costLogs.value = r.data }).catch(() => {})
    showEdit.value = false
  } catch (error) {
    message.error(error.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  const id = route.params.id
  getColorVariants().then(r => { colorVariants.value = r.data })
  try {
    const [pRes, sRes, lRes, partsRes] = await Promise.all([
      getPart(id),
      getStock('part', id),
      getStockLog('part', id),
      listParts(),
    ])
    part.value = pRes.data
    stock.value = sRes.data.current
    logs.value = lRes.data
    childPartOptions.value = partsRes.data
      .filter((p) => p.id !== id)
      .map((p) => ({
        label: `${p.id} ${p.name}`,
        value: p.id,
        code: p.id,
        name: p.name,
        image: p.image,
      }))
    getPartCostLogs(id).then(r => { costLogs.value = r.data }).catch(() => {})
    loadPartBom()
    loadVariantFamily()
  } finally {
    loading.value = false
  }
  if (part.value?.parent_part_id) {
    try {
      const ppRes = await getPart(part.value.parent_part_id)
      parentPartName.value = `${ppRes.data.id} ${ppRes.data.name}`
    } catch (_) {
      parentPartName.value = part.value.parent_part_id
    }
  }
})
</script>

<style scoped>
/* ── Page shell ── */
.part-detail-page {
  padding: 0 0 40px;
}

/* ── Header ── */
.page-top {
  padding: 22px 28px 0;
}

.back-btn {
  border: none;
  background: none;
  padding: 0;
  margin: 0 0 8px;
  color: #8B9096;
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.back-btn:hover {
  color: #1A1D21;
}

.page-crumbs {
  font-size: 12px;
  color: #8B9096;
  margin-bottom: 6px;
  letter-spacing: 0.1px;
}

.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
  gap: 12px;
}

.title-l {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
  line-height: 1.2;
  color: #1A1D21;
  letter-spacing: -0.3px;
}

.id-chip {
  font-size: 12px;
  color: #6b7280;
  background: #F6F7F8;
  border: 1px solid #ECEDEF;
  border-radius: 6px;
  padding: 2px 8px;
  font-variant-numeric: tabular-nums;
}

.cat-tag {
  font-size: 11px;
  color: #4b5158;
  background: #F4F5F6;
  border-radius: 5px;
  padding: 2px 8px;
}

.root-tag {
  font-size: 10px;
  font-weight: 600;
  color: #475569;
  background: #EEF1F4;
  border-radius: 4px;
  padding: 2px 8px;
}

.variant-tag {
  background: #E6F2EC;
  color: #1E7A5A;
}

/* ── Stat strip (4-col) ── */
.stat-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  border: 1px solid #ECEDEF;
  border-radius: 10px;
  margin: 20px 28px 0;
  background: #fff;
  overflow: hidden;
}

.stat-card {
  padding: 13px 18px;
  border-right: 1px solid #ECEDEF;
}

.stat-card:last-child {
  border-right: 0;
}

.stat-label {
  font-size: 10.5px;
  letter-spacing: 0.7px;
  text-transform: uppercase;
  color: #8B9096;
  font-weight: 600;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.5px;
  margin-top: 5px;
  line-height: 1;
  color: #1A1D21;
  font-variant-numeric: tabular-nums;
}

.stat-danger {
  color: #E5484D;
}

/* ── Sections ── */
.sec {
  padding: 22px 28px 0;
}

.sec-last {
  padding-bottom: 26px;
}

.sec-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 10px;
  border-bottom: 1px solid #ECEDEF;
  margin-bottom: 14px;
}

.sec-h .t {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: #8B9096;
}

.sec-h .cnt {
  font-size: 11px;
  color: #AEB3B8;
}

.sec-h .r-acts {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

.sbtn {
  font-size: 12px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 6px;
  border: 1px solid #ECEDEF;
  background: #fff;
  color: #1A1D21;
  cursor: pointer;
  line-height: 1.4;
}

.sbtn:hover {
  border-color: #AEB3B8;
  background: #F4F5F6;
}

/* ── Key-value grid ── */
.kv {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px 24px;
}

.kv .f {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.kv .k {
  font-size: 11px;
  color: #8B9096;
}

.kv .v {
  font-size: 14px;
  color: #1A1D21;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
}

.kv-full {
  grid-column: 1 / -1;
}

.color-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 5px;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.12);
  vertical-align: middle;
  flex-shrink: 0;
}

.cost {
  font-weight: 600;
}

.cost-bd {
  color: #8B9096;
  font-size: 12px;
  margin-left: 6px;
}

.link {
  color: #1E7A5A;
  text-decoration: none;
}

.link:hover {
  text-decoration: underline;
}

.badge-no {
  font-size: 11px;
  color: #4b5158;
  background: #F4F5F6;
  border-radius: 5px;
  padding: 1px 7px;
}

.badge-combo {
  font-size: 11px;
  font-weight: 600;
  color: #1E7A5A;
  background: #E6F2EC;
  border-radius: 5px;
  padding: 1px 7px;
}

.price-hist {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #1E7A5A;
  border: 1px solid #E6F2EC;
  background: #E6F2EC;
  border-radius: 6px;
  padding: 1px 7px;
  margin-left: 8px;
  cursor: pointer;
  white-space: nowrap;
}

.mono {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}

/* ── Variant family table ── */
.fam-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.fam-table thead th {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: #8B9096;
  text-align: left;
  padding: 9px 10px;
  border-bottom: 1px solid #ECEDEF;
  background: #FAFBFC;
}

.fam-table thead th.r,
.fam-table tbody td.r {
  text-align: right;
}

.fam-table tbody td {
  padding: 10px;
  border-bottom: 1px solid #F4F5F6;
  vertical-align: middle;
}

.fam-table tbody tr:last-child td {
  border-bottom: none;
}

.vrow.cur {
  background: #E6F2EC;
}

.fam-root-tag {
  font-size: 10px;
  font-weight: 600;
  color: #475569;
  background: #EEF1F4;
  border-radius: 4px;
  padding: 1px 6px;
  margin-left: 6px;
}

.cur-tag {
  font-size: 10px;
  font-weight: 600;
  color: #1E7A5A;
  margin-left: 6px;
}

.cell-id {
  color: #6b7280;
  font-size: 12.5px;
}

.stock-low {
  color: #E5484D;
  font-weight: 700;
}

.go-btn {
  width: 24px;
  height: 24px;
  border: 1px solid #ECEDEF;
  border-radius: 7px;
  background: #fff;
  color: #6b7280;
  cursor: pointer;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.go-btn:hover {
  border-color: #AEB3B8;
  background: #F4F5F6;
}

/* ── Batch add panel ── */
.addpanel {
  margin-top: 14px;
  border: 1px solid #ECEDEF;
  border-radius: 10px;
  padding: 14px 16px;
  background: #F6F7F8;
}

.addpanel-h {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: #8B9096;
  margin-bottom: 10px;
}

.staging thead th {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: #8B9096;
  text-align: left;
  padding: 9px 10px;
  border-bottom: 1px solid #ECEDEF;
  background: #FAFBFC;
}

.staging tbody td {
  padding: 10px;
  border-bottom: 1px solid #F4F5F6;
  vertical-align: middle;
  background: #fff;
}

.staging tbody tr:last-child td {
  border-bottom: none;
}

.addpanel-f {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.addpanel-hint {
  margin-right: auto;
  font-size: 12px;
  color: #8B9096;
}

/* ── Edit modal layout ── */
.modal-sec-h {
  font-size: 11px;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: #8B9096;
  font-weight: 600;
  margin: 12px 0 10px;
}

.modal-grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 14px;
}

.modal-full {
  grid-column: 1 / -1;
}

.modal-note {
  color: #8B9096;
  font-size: 12px;
  margin-left: 8px;
  white-space: nowrap;
}

.modal-img-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.modal-img-preview {
  width: 48px;
  height: 48px;
  border-radius: 9px;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid #ECEDEF;
  display: block;
}

.modal-img-placeholder {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  border-radius: 9px;
  background: linear-gradient(135deg, #f2cdbf, #cf8f7d);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.05);
}

.modal-upload-btn {
  white-space: nowrap;
  flex-shrink: 0;
}
</style>

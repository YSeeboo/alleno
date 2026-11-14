<template>
  <div class="structure-workbench" :class="{ blocked: submitting }">
    <div class="crumb">商品 / 结构与搭配</div>
    <header class="page-head">
      <div>
        <h1>饰品结构工作台</h1>
        <p>先搭结构，再选搭配，批量保存每件饰品的独立用料。</p>
      </div>
      <n-space
        ><n-button @click="reload">重新加载</n-button
        ><n-button @click="newStructure">＋ 新结构</n-button></n-space
      >
    </header>
    <n-alert type="info" :show-icon="false" class="intro"
      >这里使用真实配件。用量按生产 <b>1 {{ draft.unit || '计量单位' }}</b
      >饰品填写，计量单位取配件库存单位；链长不能直接当成克数。修改结构和方案不会自动修改已有饰品。</n-alert
    >
    <n-alert v-if="loadFailed" type="error" class="intro"
      >加载失败，请点击“重新加载”重试，避免在不完整数据上操作。</n-alert
    >
    <n-tabs v-model:value="tab" type="line">
      <n-tab-pane name="work" tab="配置与批量创建">
        <n-spin :show="loading || saving">
          <div class="workspace">
            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2><i>01</i>结构模板</h2>
                  <p>自由定义组成位置，不限定配件类别</p>
                </div>
                <n-tag size="small" :bordered="false">{{
                  current ? `v${current.revision}` : '未保存'
                }}</n-tag>
              </div>
              <div class="panel-body">
                <label class="field-label">选择结构</label>
                <n-select
                  :value="activeId"
                  :options="structureOptions"
                  placeholder="暂无结构，请先新建"
                  @update:value="switchStructure"
                />
                <div class="fields two spaced">
                  <label
                    >结构名称<input
                      v-model="draft.name"
                      aria-label="结构名称"
                      maxlength="120"
                      placeholder="例如：耳钉链条吊坠款" /></label
                  ><label
                    >饰品类目<n-select
                      v-model:value="draft.category"
                      :options="categoryOptions"
                      placeholder="请选择饰品类型"
                  /></label>
                </div>
                <div class="fields two spaced">
                  <label
                    >计量单位<n-select
                      v-model:value="draft.unit"
                      :options="unitOptions" /></label
                  ><label
                    >备注<input
                      v-model="draft.note"
                      aria-label="结构备注"
                      maxlength="2000"
                      placeholder="工艺说明（选填）"
                  /></label>
                </div>
                <p class="helper spaced">类目用于分类，单位用于计量；两者独立设置。修改结构不会改变已有饰品的类目、单位或 BOM。</p>
                <n-alert v-if="!isJewelryType(draft.category)" type="warning" class="spaced">
                  原类目“{{ draft.category || '未分类' }}”尚未归类。请选择饰品类型；已有饰品不会自动跟随修改。
                </n-alert>
                <div class="chain spaced">
                  <template v-for="(slot, i) in draft.slots" :key="slot.key"
                    ><span v-if="i" class="muted">＋</span
                    ><span class="chip">{{
                      slot.name || '未命名'
                    }}</span></template
                  >
                </div>
                <div class="slot-head">
                  <span>组成位置</span><span>默认配件 / 库存单位</span
                  ><span>用量</span><span></span>
                </div>
                <div
                  v-for="(slot, i) in draft.slots"
                  :key="slot.key"
                  class="slot-row"
                >
                  <div>
                    <input
                      v-model="slot.name"
                      :aria-label="`位置${i + 1}名称`"
                      maxlength="120"
                    />
                    <div class="order-actions">
                      <button
                        @click="moveSlot(i, -1)"
                        :disabled="i === 0"
                        aria-label="位置上移"
                      >
                        ↑</button
                      ><button
                        @click="moveSlot(i, 1)"
                        :disabled="i === draft.slots.length - 1"
                        aria-label="位置下移"
                      >
                        ↓
                      </button>
                    </div>
                  </div>
                  <div>
                    <n-select
                      v-model:value="slot.part_id"
                      :options="partOptions"
                      :render-label="renderPartLabel"
                      filterable
                      clearable
                      size="small"
                      :placeholder="
                        slot.selectable ? '每件单独选，可设默认' : '选择默认配件'
                      "
                    />
                    <div class="slot-meta">
                      <span
                        >单位：{{ part(slot.part_id)?.unit || '待选择' }}</span
                      ><label
                        ><input
                          v-model="slot.selectable"
                          type="checkbox"
                        />每件单独选</label
                      >
                    </div>
                  </div>
                  <input
                    v-model="slot.qty"
                    :aria-label="`${slot.name}默认用量`"
                    inputmode="decimal"
                  />
                  <button
                    class="delete"
                    @click="removeSlot(slot.key)"
                    :aria-label="`删除${slot.name}位置`"
                  >
                    ×
                  </button>
                </div>
                <button class="link spaced" @click="addSlot">
                  ＋ 添加组成位置
                </button>
                <p class="helper spaced">
                  勾选“每件单独选”后，可在下方表格为每件饰品选择不同配件。重命名不影响方案；删除位置后，相关方案需显式修复。
                </p>
              </div>
              <div class="panel-foot">
                <span class="helper">{{
                  structureDirty ? '● 有未保存的结构草稿' : '已保存，可复用'
                }}</span
                ><n-space size="small"
                  ><n-button
                    v-if="current"
                    size="small"
                    @click="removeStructure"
                    >删除</n-button
                  ><n-button size="small" @click="copyStructure">另存</n-button
                  ><n-button size="small" type="primary" @click="saveStructure"
                    >保存结构</n-button
                  ></n-space
                >
              </div>
            </section>
            <section class="panel">
              <div class="panel-head">
                <div>
                  <h2><i>02</i>联动搭配方案</h2>
                  <p>只保存需要一起变化的配件与用量</p>
                </div>
                <n-button size="small" @click="startNewScheme"
                  >＋ 新方案</n-button
                >
              </div>
              <div class="panel-body">
                <p class="helper">
                  此处选择要编辑的方案。本批实际使用哪个方案，在下方表格指定。
                </p>
                <n-alert v-if="!schemeId" type="info" class="spaced">
                  新方案草稿：填写名称，设置需要联动的配件和用量，再点击“保存方案”。保存前不会新增方案。
                </n-alert>
                <div class="scheme-cards spaced">
                  <button
                    v-for="s in schemes"
                    :key="s.id"
                    :class="['scheme-card', { active: schemeId === s.id }]"
                    @click="editScheme(s.id)"
                  >
                    <b>{{ s.name }}</b
                    ><span>{{
                      s.invalid_keys.length
                        ? '⚠ 引用已删除位置'
                        : `${Object.keys(s.overrides).length} 个联动位置`
                    }}</span>
                  </button>
                </div>
                <label class="field-label spaced">方案名称</label
                ><input
                  ref="schemeNameInput"
                  v-model="schemeName"
                  aria-label="方案名称"
                  maxlength="120"
                  placeholder="例如：小珠版、大珠版"
                />
                <n-alert
                  v-if="schemeInvalidKeys.length"
                  type="warning"
                  class="spaced"
                  >方案引用了
                  {{ schemeInvalidKeys.length }}
                  个已删除位置，不能用于生成。<button
                    class="link"
                    @click="repairScheme"
                  >
                    移除失效引用（保存后生效）
                  </button></n-alert
                >
                <div class="scheme-head">
                  <span>位置</span><span>方案配件</span><span>用量</span>
                </div>
                <div
                  v-for="slot in draft.slots"
                  :key="slot.key"
                  class="scheme-row"
                >
                  <div>
                    {{ slot.name }}
                    <div class="helper">
                      {{ schemeOverrides[slot.key] ? '方案设置' : '沿用结构' }}
                    </div>
                    <button
                      v-if="schemeOverrides[slot.key]"
                      class="link tiny"
                      @click="delete schemeOverrides[slot.key]"
                    >
                      恢复默认
                    </button>
                  </div>
                  <div v-if="slot.selectable" class="helper">
                    创建时每件单独选配件
                  </div>
                  <n-select
                    v-else
                    :value="schemeValue(slot, 'part_id')"
                    @update:value="setSchemeValue(slot.key, 'part_id', $event)"
                    :options="partOptions"
                    :render-label="renderPartLabel"
                    filterable
                    clearable
                    size="small"
                  />
                  <div>
                    <input
                      :value="schemeValue(slot, 'qty')"
                      @input="
                        setSchemeValue(slot.key, 'qty', $event.target.value)
                      "
                      :aria-label="`方案${slot.name}用量`"
                      inputmode="decimal"
                    /><span class="helper">{{
                      part(schemeValue(slot, 'part_id'))?.unit || ''
                    }}</span>
                  </div>
                </div>
                <div class="linked spaced">
                  联动由你明确配置，不根据珠子直径推算数量或链长。方案不会绑定设置为“每件单独选”的吊坠。
                </div>
                <p v-if="structureDirty" class="helper spaced">
                  请先保存结构，再保存搭配方案；结构草稿仍可参与本批预览。
                </p>
              </div>
              <div class="panel-foot">
                <span class="helper">{{
                  schemeDirty ? '● 方案草稿未保存' : '方案修改不追溯已有饰品'
                }}</span
                ><n-space size="small"
                  ><n-button v-if="schemeId" size="small" @click="removeScheme"
                    >删除</n-button
                  ><n-button
                    v-if="schemeId"
                    size="small"
                    @click="saveScheme(true)"
                    >另存</n-button
                  ><n-button
                    size="small"
                    type="primary"
                    :disabled="!current || structureDirty"
                    @click="saveScheme(false)"
                    >保存方案</n-button
                  ></n-space
                >
              </div>
            </section>
          </div>
          <section class="panel batch">
            <div class="panel-head">
              <div>
                <h2><i>03</i>批量创建饰品</h2>
                <p>每行一件独立商品，不自动生成组合或归为同款</p>
              </div>
              <n-button size="small" @click="addRow">＋ 添加一行</n-button>
            </div>
            <div class="batch-bar">
              <span class="field-label">本批默认搭配</span
              ><n-select
                v-model:value="defaultSchemeId"
                :options="defaultSchemeOptions"
                style="width: 180px"
              /><span class="helper"
                >沿用默认的行一起变化；单独指定方案及单件调整保留。</span
              >
            </div>
            <n-alert v-if="hasInvalidRowReferences" type="warning"
              >结构位置已删除或不再设置为“每件单独选”，本批有旧设置需要检查。<button
                class="link"
                @click="repairRowReferences"
              >
                清理待创建行的失效设置
              </button></n-alert
            >
            <p class="helper mobile-hint">
              ← 左右滑动表格，选择配件或进入单件调整 →
            </p>
            <div class="table-wrap">
              <table class="batch-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>饰品名称 / 颜色</th>
                    <th>搭配方案</th>
                    <th v-for="slot in selectableSlots" :key="slot.key">
                      {{ slot.name }}（每件单独选）
                    </th>
                    <th>调整与用料</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in rows" :key="row.key">
                    <td>{{ String(i + 1).padStart(2, '0') }}</td>
                    <td>
                      <input
                        v-model="row.name"
                        :aria-label="`第${i + 1}行饰品名称`"
                        placeholder="饰品名称"
                        maxlength="120"
                      /><input
                        v-model="row.color"
                        class="spaced-small"
                        :aria-label="`第${i + 1}行颜色`"
                        placeholder="颜色（选填）"
                        maxlength="120"
                      />
                    </td>
                    <td>
                      <n-select
                        v-model:value="row.scheme_id"
                        :options="rowSchemeOptions"
                        placeholder="沿用默认搭配"
                        size="small"
                      />
                      <div class="helper">
                        {{ effectiveScheme(row)?.name || '结构默认' }}
                      </div>
                    </td>
                    <td v-for="slot in selectableSlots" :key="slot.key">
                      <n-select
                        v-model:value="row.selections[slot.key]"
                        :options="partOptions"
                        :render-label="renderPartLabel"
                        filterable
                        clearable
                        :placeholder="
                          slot.part_id ? '沿用位置默认配件' : '请选择配件'
                        "
                        size="small"
                      />
                    </td>
                    <td>
                      <n-space size="small"
                        ><n-button
                          size="small"
                          text
                          type="primary"
                          @click="openDetail(row)"
                          >{{
                            adjustmentCount(row)
                              ? `调整 ${adjustmentCount(row)} 处 / 用料`
                              : '调整 / 用料'
                          }}</n-button
                        ><button
                          class="delete"
                          @click="removeRow(row.key)"
                          :aria-label="`删除${row.name || '空白'}行`"
                        >
                          ×
                        </button></n-space
                      >
                      <p class="helper row-summary">{{ rowSummary(row) }}</p>
                    </td>
                  </tr>
                  <tr v-if="!rows.length">
                    <td :colspan="4 + selectableSlots.length" class="empty">
                      点击“添加一行”开始配置；没有演示配件或自动生成的组合。
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="batch-footer">
              <div>
                <b>本批 {{ rows.length }} 件饰品</b>
                <p class="helper">
                  按 1 {{ draft.unit || '计量单位' }}计算用料；确认后只建立商品和
                  BOM，不增加库存。
                </p>
              </div>
              <n-button
                type="primary"
                :loading="previewing"
                :disabled="!canCreate || !current || !rows.length || loadFailed"
                @click="previewBatch"
                >预览最终 BOM →</n-button
              >
            </div>
            <p v-if="!canCreate" class="helper permission-note">
              创建饰品需要同时具备饰品和配件权限；当前可维护结构与方案。
            </p>
          </section>
        </n-spin>
      </n-tab-pane>
      <n-tab-pane v-if="canCreate" name="history" tab="已生成批次">
        <n-alert type="info" :show-icon="false"
          >以下为你最近 20 批的<b>创建时 BOM 快照</b
          >，不会随模板变化。若饰品后来单独改过用料，以饰品详情的当前 BOM
          为准；这不是投产批次用料锁定。</n-alert
        >
        <n-empty
          v-if="!history.length"
          description="尚无通过工作台创建的批次"
          class="spaced"
        />
        <section v-for="(batch, i) in history" :key="i" class="panel batch">
          <div class="panel-head">
            <div>
              <h2>
                {{ batch.structure_name }}
                <span class="helper"
                  >v{{ batch.structure_revision
                  }}{{ batch.from_draft ? ' ＋ 草稿调整' : '' }}</span
                >
              </h2>
              <p>{{ batch.created_at }} · {{ batch.rows.length }} 件饰品</p>
            </div>
          </div>
          <div class="history-grid">
            <article v-for="row in batch.rows" :key="row.key">
              <h3>{{ row.name }}</h3>
              <p class="helper">{{ row.scheme_name }} · {{ row.jewelry_id }}</p>
              <div
                v-for="item in row.bom"
                :key="item.part_id"
                class="history-line"
              >
                <span>{{ item.part_name }}</span
                ><b>{{ item.qty }} {{ item.unit }}</b>
              </div>
              <router-link :to="`/jewelries/${row.jewelry_id}`"
                >查看饰品当前用料 →</router-link
              >
            </article>
          </div>
        </section>
      </n-tab-pane>
    </n-tabs>

    <n-modal
      :show="detailVisible"
      preset="card"
      :title="`${detail?.name || '新饰品'} · 单件调整`"
      :style="modalStyle"
      :content-style="modalContentStyle"
      :mask-closable="false"
      :close-on-esc="false"
      :closable="false"
    >
      <template v-if="detail">
        <p class="helper">
          只影响这一件。单件覆盖优先于方案，切换方案时保留，直到手动清除。
        </p>
        <div class="fields three spaced">
          <label
            >零售价<input
              v-model="detail.retail_price"
              inputmode="decimal"
              placeholder="选填" /></label
          ><label
            >批发价<input
              v-model="detail.wholesale_price"
              inputmode="decimal"
              placeholder="选填" /></label
          ><label
            >手工费<input
              v-model="detail.handcraft_cost"
              inputmode="decimal"
              placeholder="选填"
          /></label>
        </div>
        <label class="field-label spaced"
          >图片地址（选填，也可创建后在饰品详情上传）</label
        ><input
          v-model="detail.image"
          maxlength="2000"
          placeholder="https://…"
        />
        <div v-for="slot in detailPositions" :key="slot.key" class="detail-row">
          <div>
            <input
              v-if="slot.extra"
              :value="slot.name"
              @input="setDetailValue(slot, 'name', $event.target.value)"
              aria-label="单件新增位置名称"
            /><b v-else>{{ slot.name }}</b>
            <div class="helper">{{ slot.source }}</div>
          </div>
          <div>
            <n-select
              :value="slot.part_id"
              @update:value="setDetailValue(slot, 'part_id', $event)"
              :options="partOptions"
              :render-label="renderPartLabel"
              filterable
              clearable
              size="small"
            />
            <p class="helper">
              库存单位：{{ part(slot.part_id)?.unit || '待选择' }}
            </p>
          </div>
          <input
            :value="slot.qty"
            @input="setDetailValue(slot, 'qty', $event.target.value)"
            :aria-label="`单件${slot.name}用量`"
            inputmode="decimal"
          /><button
            class="delete"
            @click="deleteDetailSlot(slot)"
            :aria-label="`单件删除${slot.name}`"
          >
            ×
          </button>
        </div>
        <n-space class="spaced"
          ><n-button size="small" @click="addDetailSlot"
            >＋ 添加单件配件</n-button
          ><n-button size="small" @click="clearDetail">清除单件调整</n-button
          ><n-button size="small" @click="detailAsStructure"
            >另存为常用结构</n-button
          ></n-space
        >
      </template>
      <template #footer
        ><n-space justify="end"
          ><n-button @click="cancelDetail">取消</n-button
          ><n-button type="primary" @click="saveDetail"
            >保存单件调整</n-button
          ></n-space
        ></template
      >
    </n-modal>

    <n-modal
      :show="previewVisible"
      preset="card"
      title="确认最终用料"
      :style="modalStyle"
      :content-style="modalContentStyle"
      :mask-closable="false"
      :close-on-esc="false"
      :closable="false"
    >
      <template v-if="previewData">
        <n-alert v-if="pendingConfirm" type="warning"
          >已提交过此请求，结果尚未确认。请重试同一请求，不要另建批次；即使上次已经成功，也不会重复创建。</n-alert
        >
        <p class="helper">
          以下为服务端校验、合并后的实际 BOM。按生产 1
          {{ previewData.unit }}填写，生成后不再动态读取结构。
        </p>
        <n-alert v-if="previewData.from_draft" type="info" class="spaced"
          >本批使用结构草稿；创建会保存实际 BOM，不会隐式发布模板草稿。</n-alert
        >
        <article
          v-for="row in previewData.rows"
          :key="row.key"
          class="preview-item"
        >
          <h3>
            {{ row.name }} <span class="helper">{{ row.scheme_name }}</span>
          </h3>
          <div v-for="item in row.bom" :key="item.part_id" class="history-line">
            <div>
              {{ item.part_name }}
              <p class="helper">
                {{ item.part_id }} · {{ item.positions.join(' / ') }}
              </p>
            </div>
            <b>{{ item.qty }} {{ item.unit }}</b>
          </div>
        </article>
      </template>
      <template #footer
        ><n-space justify="end"
          ><n-button
            :disabled="submitting || !!pendingConfirm"
            @click="previewVisible = false"
            >返回调整</n-button
          ><n-button
            type="primary"
            :loading="submitting"
            @click="confirmBatch"
            >{{
              pendingConfirm ? '重试确认（不会重复创建）' : '确认创建饰品'
            }}</n-button
          ></n-space
        ></template
      >
    </n-modal>

    <n-modal
      v-model:show="nameVisible"
      preset="card"
      :title="nameTitle"
      :style="{ width: 'min(95vw, 440px)' }"
      :mask-closable="false"
      ><form @submit.prevent="submitName">
        <label class="field-label">名称</label
        ><input
          v-model="newName"
          aria-label="另存名称"
          maxlength="120"
          required
          autofocus
        />
        <p class="helper spaced">
          只另存配置，不切换当前结构，也不改变本批或已有饰品。
        </p>
        <n-space justify="end" class="spaced"
          ><n-button @click="nameVisible = false">取消</n-button
          ><n-button type="primary" attr-type="submit" :loading="saving"
            >保存</n-button
          ></n-space
        >
      </form></n-modal
    >
  </div>
</template>

<script setup>
import { computed, h, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import {
  NAlert,
  NButton,
  NEmpty,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'
import { listParts } from '@/api/parts'
import * as api from '@/api/jewelryStructures'
import { useAuthStore } from '@/stores/auth'
import { useIsMobile } from '@/composables/useIsMobile'
import { renderImageThumb, renderOptionWithImage } from '@/utils/ui'
import { jewelryCategoryEditOptions, jewelryUnitOptions as unitOptions, isJewelryType } from '@/utils/jewelryOptions'

const message = useMessage(),
  dialog = useDialog(),
  auth = useAuthStore()
const { isMobile } = useIsMobile()
const copy = (value) => JSON.parse(JSON.stringify(value))
const key = () => crypto.randomUUID()
const emptySlot = () => ({
  key: key(),
  name: '',
  part_id: null,
  qty: '1',
  selectable: false,
})
const emptyStructure = () => ({
  name: '',
  note: '',
  category: null,
  unit: null,
  slots: [emptySlot()],
})
const structures = ref([]),
  parts = ref([]),
  activeId = ref(null),
  draft = ref(emptyStructure())
const rows = ref([]),
  history = ref([]),
  defaultSchemeId = ref(0),
  tab = ref('work')
const schemeId = ref(null),
  schemeName = ref(''),
  schemeOverrides = ref({})
const schemeNameInput = ref(null)
const loading = ref(true),
  saving = ref(false),
  loadFailed = ref(false),
  previewing = ref(false),
  submitting = ref(false)
const detail = ref(null),
  detailOriginal = ref(''),
  detailVisible = ref(false)
const previewData = ref(null),
  previewPayload = ref(null),
  previewVisible = ref(false),
  pendingConfirm = ref(null)
const nameVisible = ref(false),
  nameTitle = ref(''),
  newName = ref('')
let nameAction = null
const canCreate = computed(() => auth.hasPermission('jewelries'))
const current = computed(() =>
  structures.value.find((s) => s.id === activeId.value),
)
const schemes = computed(() => current.value?.schemes || [])
const selectedScheme = computed(() =>
  schemes.value.find((s) => s.id === schemeId.value),
)
const structureOptions = computed(() =>
  structures.value.map((s) => ({ label: s.name, value: s.id })),
)
const partMap = computed(() =>
  Object.fromEntries(parts.value.map((p) => [p.id, p])),
)
const part = (id) => partMap.value[id]
const partOptions = computed(() =>
  parts.value.map((p) => ({
    label: `${p.id} ${p.name} · ${p.unit || '未设单位'}`,
    value: p.id,
    code: p.id,
    name: `${p.name} · ${p.unit || '未设单位'}`,
    image: p.image,
  })),
)
function renderPartLabel(option, selected) {
  if (!selected) return renderOptionWithImage(option)
  // Two-line dropdown labels are useful while searching, but get clipped in
  // the compact selected field. Keep the part name and unit readable there.
  return h(
    'span',
    {
      title: option.label,
      style: { display: 'flex', alignItems: 'center', gap: '5px', minWidth: 0 },
    },
    [
      renderImageThumb(option.image, option.name, 20),
      h(
        'span',
        {
          style: {
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            fontSize: '12px',
          },
        },
        option.name,
      ),
    ],
  )
}
const selectableSlots = computed(() =>
  draft.value.slots.filter((s) => s.selectable),
)
const defaultSchemeOptions = computed(() => [
  { label: '结构默认（不使用方案）', value: 0 },
  ...schemes.value.map((s) => ({
    label: s.name + (s.invalid_keys.length ? ' ⚠ 不兼容' : ''),
    value: s.id,
  })),
])
const rowSchemeOptions = computed(() => [
  { label: '沿用本批默认搭配', value: 0 },
  ...schemes.value.map((s) => ({
    label: s.name + (s.invalid_keys.length ? ' ⚠ 不兼容' : ''),
    value: s.id,
  })),
])
const categoryOptions = computed(() => jewelryCategoryEditOptions(draft.value.category))
const modalStyle = computed(() => ({
  width: isMobile.value ? '96vw' : '760px',
}))
const modalContentStyle = {
  maxHeight: 'calc(85dvh - 140px)',
  overflowY: 'auto',
}
function reportError(e) {
  if (!e.response) message.error(e.message || '操作失败，请重试')
}
function configOf(s) {
  return copy({
    name: s.name,
    note: s.note,
    category: s.category,
    unit: s.unit,
    slots: s.slots,
  })
}
const structureDirty = computed(() =>
  current.value
    ? JSON.stringify(draft.value) !== JSON.stringify(configOf(current.value))
    : !!draft.value.name || draft.value.slots.some((s) => s.name || s.part_id),
)
const schemeDirty = computed(
  () =>
    schemeName.value !== (selectedScheme.value?.name || '') ||
    JSON.stringify(schemeOverrides.value) !==
      JSON.stringify(selectedScheme.value?.overrides || {}),
)
const schemeInvalidKeys = computed(() =>
  Object.keys(schemeOverrides.value).filter(
    (k) => !draft.value.slots.some((s) => s.key === k),
  ),
)
const hasUnsaved = computed(
  () =>
    structureDirty.value ||
    schemeDirty.value ||
    rows.value.length > 0 ||
    detailVisible.value ||
    !!pendingConfirm.value,
)
const pendingStorageKey = computed(
  () => `jewelry-structure-confirm:${auth.user?.id}`,
)
const ask = (title, content) =>
  new Promise((resolve) =>
    dialog.warning({
      title,
      content,
      positiveText: '确认',
      negativeText: '取消',
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
      onMaskClick: () => resolve(false),
    }),
  )
async function allowDiscard() {
  return (
    !hasUnsaved.value ||
    (await ask(
      '放弃当前未保存内容？',
      '切换或重新加载会重置结构、方案草稿和本批待创建行，已生成饰品不受影响。',
    ))
  )
}
function applySaved(obj) {
  const i = structures.value.findIndex((s) => s.id === obj.id)
  if (i < 0) structures.value.unshift(obj)
  else structures.value[i] = obj
}
function loadSelected(obj) {
  activeId.value = obj?.id || null
  draft.value = obj ? configOf(obj) : emptyStructure()
  schemeId.value = null
  schemeName.value = ''
  schemeOverrides.value = {}
  rows.value = []
  defaultSchemeId.value = 0
}
async function switchStructure(id) {
  if (id === activeId.value || !(await allowDiscard())) return
  loadSelected(structures.value.find((s) => s.id === id))
}
async function newStructure() {
  if (await allowDiscard()) {
    loadSelected(null)
    tab.value = 'work'
  }
}
async function fetchData() {
  loading.value = true
  loadFailed.value = false
  try {
    const [s, p, h] = await Promise.all([
      api.listStructures(),
      listParts(),
      canCreate.value
        ? api.listStructureBatches()
        : Promise.resolve({ data: [] }),
    ])
    structures.value = s.data
    parts.value = p.data
    history.value = h.data
    loadSelected(
      structures.value.find((s) => s.id === activeId.value) ||
        structures.value[0],
    )
  } catch {
    loadFailed.value = true
  } finally {
    loading.value = false
  }
}
async function reload() {
  if (await allowDiscard()) await fetchData()
}
function addSlot() {
  draft.value.slots.push(emptySlot())
}
function removeSlot(k) {
  draft.value.slots = draft.value.slots.filter((s) => s.key !== k)
}
function moveSlot(i, step) {
  const a = draft.value.slots
  ;[a[i], a[i + step]] = [a[i + step], a[i]]
}
function validateStructure(value) {
  if (!value.name.trim()) return '请填写结构名称'
  if (!isJewelryType(value.category)) return '请选择饰品类型，不再使用单件、单对等计量分类'
  if (!unitOptions.some((option) => option.value === value.unit)) return '请单独选择计量单位'
  if (!value.slots.length) return '至少需要一个组成位置'
  if (value.slots.some((s) => !s.name.trim())) return '请填写所有位置名称'
  if (value.slots.some((s) => !validQty(s.qty)))
    return '用量须大于 0，最多 4 位小数且小于 1000000'
  return ''
}
function validQty(value) {
  return (
    /^\d+(\.\d{1,4})?$/.test(String(value)) &&
    Number(value) > 0 &&
    Number(value) < 1000000
  )
}
async function saveStructure() {
  const error = validateStructure(draft.value)
  if (error) return message.warning(error)
  saving.value = true
  try {
    const { data } = current.value
      ? await api.updateStructure(current.value.id, {
          ...copy(draft.value),
          revision: current.value.revision,
        })
      : await api.createStructure(copy(draft.value))
    applySaved(data)
    activeId.value = data.id
    draft.value = configOf(data)
    message.success('结构已保存，已有饰品 BOM 不变')
  } catch (e) {
    if (!e.response) message.error(e.message || '保存失败，请重试')
  } finally {
    saving.value = false
  }
}
function openName(title, value, action) {
  nameTitle.value = title
  newName.value = value
  nameAction = action
  nameVisible.value = true
}
async function submitName() {
  if (!newName.value.trim()) return
  saving.value = true
  try {
    await nameAction(newName.value.trim())
    nameVisible.value = false
  } catch (e) {
    reportError(e)
  } finally {
    saving.value = false
  }
}
function copyStructure() {
  const error = validateStructure(draft.value)
  if (error) return message.warning(error)
  openName('另存为新结构', draft.value.name + ' · 新结构', async (name) => {
    const { data } = await api.createStructure({ ...copy(draft.value), name })
    applySaved(data)
    message.success('已另存，可在结构列表选择')
  })
}
async function removeStructure() {
  if (
    !(await ask(
      '删除结构？',
      '会删除此结构及其搭配方案；已有饰品、实际 BOM 和创建快照保留。当前未保存内容会丢弃。',
    ))
  )
    return
  saving.value = true
  try {
    await api.deleteStructure(current.value.id, current.value.revision)
    structures.value = structures.value.filter((s) => s.id !== activeId.value)
    loadSelected(structures.value[0])
    message.success('结构已删除，已有饰品未改变')
  } catch (e) {
    reportError(e)
  } finally {
    saving.value = false
  }
}
async function editScheme(id) {
  if (id === schemeId.value && id !== null) return
  if (
    schemeDirty.value &&
    !(await ask(
      '放弃未保存的方案修改？',
      '将切换到所选方案，批量表中的方案选择不变。',
    ))
  )
    return false
  const s = schemes.value.find((s) => s.id === id)
  schemeId.value = id
  schemeName.value = s?.name || ''
  schemeOverrides.value = copy(s?.overrides || {})
  return true
}
async function startNewScheme() {
  if (!(await editScheme(null))) return
  await nextTick()
  schemeNameInput.value?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  schemeNameInput.value?.focus({ preventScroll: true })
  message.info('已进入新方案草稿，填写后请点击“保存方案”')
}
function schemeValue(slot, field) {
  const value = schemeOverrides.value[slot.key]
  return value && Object.hasOwn(value, field) ? value[field] : slot[field]
}
function setSchemeValue(k, field, value) {
  schemeOverrides.value[k] = { ...schemeOverrides.value[k], [field]: value }
}
function repairScheme() {
  for (const k of schemeInvalidKeys.value) delete schemeOverrides.value[k]
  message.info('失效引用已从草稿移除，请保存方案')
}
async function persistScheme(name, asNew) {
  if (!current.value || structureDirty.value) {
    message.warning('请先保存结构')
    return
  }
  if (!name.trim()) {
    message.warning('请填写方案名称')
    return
  }
  const body = {
    name,
    structure_revision: current.value.revision,
    overrides: copy(schemeOverrides.value),
  }
  const { data } =
    asNew || !schemeId.value
      ? await api.createScheme(current.value.id, body)
      : await api.updateScheme(current.value.id, schemeId.value, body)
  const id = asNew || !schemeId.value ? data.schemes.at(-1).id : schemeId.value
  applySaved(data)
  schemeId.value = id
  schemeName.value = data.schemes.find((s) => s.id === id).name
  schemeOverrides.value = copy(data.schemes.find((s) => s.id === id).overrides)
  message.success('搭配方案已保存，已有饰品不变')
}
async function saveScheme(asNew) {
  if (asNew)
    return openName('另存搭配方案', schemeName.value + ' · 调整版', (name) =>
      persistScheme(name, true),
    )
  saving.value = true
  try {
    await persistScheme(schemeName.value, false)
  } catch (e) {
    reportError(e)
  } finally {
    saving.value = false
  }
}
async function removeScheme() {
  if (
    !(await ask(
      '删除搭配方案？',
      '已有饰品不受影响；本批如有引用此方案的行，需要重新选择。',
    ))
  )
    return
  saving.value = true
  try {
    const { data } = await api.deleteScheme(
      current.value.id,
      schemeId.value,
      current.value.revision,
    )
    applySaved(data)
    schemeId.value = null
    schemeName.value = ''
    schemeOverrides.value = {}
    message.success('搭配方案已删除')
  } catch (e) {
    reportError(e)
  } finally {
    saving.value = false
  }
}
function addRow() {
  rows.value.push({
    key: key(),
    name: '',
    color: '',
    scheme_id: 0,
    selections: {},
    overrides: {},
    removed_keys: [],
    extras: [],
    image: null,
    retail_price: null,
    wholesale_price: null,
    handcraft_cost: null,
  })
}
function removeRow(k) {
  rows.value = rows.value.filter((r) => r.key !== k)
}
const hasInvalidRowReferences = computed(() => {
  const keys = new Set(draft.value.slots.map((s) => s.key))
  const selectable = new Set(selectableSlots.value.map((s) => s.key))
  return rows.value.some(
    (r) =>
      Object.keys(r.selections).some((k) => !selectable.has(k)) ||
      Object.keys(r.overrides).some((k) => !keys.has(k)) ||
      r.removed_keys.some((k) => !keys.has(k)),
  )
})
async function repairRowReferences() {
  if (
    !(await ask(
      '清理待创建行的失效设置？',
      '仅移除已删除位置的单件设置和不再选配位置的选择，其他调整保留；已有饰品不变。',
    ))
  )
    return
  const keys = new Set(draft.value.slots.map((s) => s.key))
  const selectable = new Set(selectableSlots.value.map((s) => s.key))
  for (const row of rows.value) {
    row.selections = Object.fromEntries(
      Object.entries(row.selections).filter(([k]) => selectable.has(k)),
    )
    row.overrides = Object.fromEntries(
      Object.entries(row.overrides).filter(([k]) => keys.has(k)),
    )
    row.removed_keys = row.removed_keys.filter((k) => keys.has(k))
  }
}
function effectiveScheme(row) {
  return schemes.value.find(
    (s) => s.id === (row.scheme_id || defaultSchemeId.value),
  )
}
function adjustmentCount(row) {
  return (
    Object.keys(row.overrides).length +
    row.removed_keys.length +
    row.extras.length
  )
}
function positions(row) {
  const overrides = effectiveScheme(row)?.overrides || {}
  return draft.value.slots
    .filter((s) => !row.removed_keys.includes(s.key))
    .map((s) => {
      const local = row.overrides[s.key]
      return {
        ...s,
        ...overrides[s.key],
        ...(row.selections[s.key] ? { part_id: row.selections[s.key] } : {}),
        ...local,
        source: local
          ? '单件调整'
          : row.selections[s.key]
            ? '每件单独选'
            : overrides[s.key]
              ? '搭配方案'
              : '结构默认',
      }
    })
    .concat(row.extras.map((s) => ({ ...s, extra: true, source: '单件新增' })))
}
function rowSummary(row) {
  const p = positions(row)
  return (
    p
      .slice(0, 3)
      .map(
        (s) =>
          `${s.name || '未命名'} ${s.qty}${part(s.part_id)?.unit || '（待选）'}`,
      )
      .join(' / ') + (p.length > 3 ? ` / 共 ${p.length} 个位置` : '')
  )
}
const detailPositions = computed(() =>
  detail.value ? positions(detail.value) : [],
)
function openDetail(row) {
  detail.value = copy(row)
  detailOriginal.value = JSON.stringify(detail.value)
  detailVisible.value = true
}
function setDetailValue(slot, field, value) {
  if (slot.extra)
    detail.value.extras.find((s) => s.key === slot.key)[field] = value
  else
    detail.value.overrides[slot.key] = {
      ...detail.value.overrides[slot.key],
      [field]: value,
    }
}
function deleteDetailSlot(slot) {
  if (slot.extra)
    detail.value.extras = detail.value.extras.filter((s) => s.key !== slot.key)
  else {
    detail.value.removed_keys.push(slot.key)
    delete detail.value.overrides[slot.key]
  }
}
function addDetailSlot() {
  detail.value.extras.push(emptySlot())
}
function clearDetail() {
  detail.value.overrides = {}
  detail.value.removed_keys = []
  detail.value.extras = []
}
async function cancelDetail() {
  if (
    JSON.stringify(detail.value) !== detailOriginal.value &&
    !(await ask('放弃单件调整？', '尚未保存到本批的修改会丢失。'))
  )
    return
  detailVisible.value = false
}
function validatePositions(p) {
  if (!p.length) return '至少保留一个配件'
  if (p.some((s) => !s.name.trim() || !s.part_id || !validQty(s.qty)))
    return '请补全位置名称、配件及有效用量'
  return ''
}
function saveDetail() {
  const error = validatePositions(detailPositions.value)
  if (error) return message.warning(error)
  rows.value[rows.value.findIndex((r) => r.key === detail.value.key)] = copy(
    detail.value,
  )
  detailVisible.value = false
}
function detailAsStructure() {
  const p = detailPositions.value
  const error = validatePositions(p)
  if (error) return message.warning(error)
  const config = {
    ...copy(draft.value),
    slots: p.map(({ source, extra, ...s }) => s),
  }
  openName(
    '把单件用料另存为常用结构',
    (detail.value.name || '单件') + ' · 常用结构',
    async (name) => {
      const { data } = await api.createStructure({ ...config, name })
      applySaved(data)
      message.success('新结构已保存，没有更改当前批次')
    },
  )
}
function batchPayload() {
  return {
    structure_id: current.value.id,
    structure_revision: current.value.revision,
    default_scheme_id: defaultSchemeId.value || null,
    draft: structureDirty.value ? copy(draft.value) : null,
    rows: rows.value.map((r) => ({
      ...copy(r),
      scheme_id: r.scheme_id || null,
      selections: Object.fromEntries(
        Object.entries(r.selections).filter(([, v]) => v),
      ),
      retail_price: r.retail_price === '' ? null : r.retail_price,
      wholesale_price: r.wholesale_price === '' ? null : r.wholesale_price,
      handcraft_cost: r.handcraft_cost === '' ? null : r.handcraft_cost,
    })),
  }
}
async function previewBatch() {
  if (
    schemeDirty.value &&
    !(await ask(
      '方案草稿尚未保存',
      '本批只使用已保存的搭配方案，不会使用右侧方案草稿。继续预览？',
    ))
  )
    return
  const error = validateStructure(draft.value)
  if (error) return message.warning(error)
  for (const [i, row] of rows.value.entries()) {
    if (!row.name.trim()) return message.warning(`请填写第 ${i + 1} 行饰品名称`)
    const rowError = validatePositions(positions(row))
    if (rowError) return message.warning(`第 ${i + 1} 行：${rowError}`)
  }
  previewing.value = true
  try {
    const payload = batchPayload()
    const { data } = await api.previewStructureBatch(payload)
    if (JSON.stringify(payload) !== JSON.stringify(batchPayload()))
      return message.warning('预览期间配置发生变化，请重新预览')
    previewPayload.value = payload
    previewData.value = data
    previewVisible.value = true
  } catch (e) {
    reportError(e)
  } finally {
    previewing.value = false
  }
}
function clearPendingStorage() {
  try {
    sessionStorage.removeItem(pendingStorageKey.value)
  } catch {
    message.warning('浏览器未能清除重试记录；再次打开时可安全重试同一请求。')
  }
}
async function confirmBatch() {
  if (submitting.value || !previewData.value) return
  if (!pendingConfirm.value)
    pendingConfirm.value = {
      request_key: key(),
      preview_token: previewData.value.preview_token,
      batch: copy(previewPayload.value),
    }
  // Persist before sending. A refresh after an ambiguous timeout can retry the
  // same idempotency key instead of creating another batch.
  try {
    sessionStorage.setItem(
      pendingStorageKey.value,
      JSON.stringify({
        request: pendingConfirm.value,
        preview: previewData.value,
      }),
    )
  } catch {
    pendingConfirm.value = null
    message.error('浏览器无法保存重试标识，已停止提交。请允许会话存储后重试。')
    return
  }
  submitting.value = true
  try {
    const { data } = await api.confirmStructureBatch(pendingConfirm.value)
    pendingConfirm.value = null
    clearPendingStorage()
    previewVisible.value = false
    rows.value = []
    history.value = [
      data,
      ...history.value.filter((b) => b.created_at !== data.created_at),
    ].slice(0, 20)
    tab.value = 'history'
    message.success(`已创建 ${data.rows.length} 件饰品，初始库存为 0`)
  } catch (e) {
    if (
      e.response &&
      [400, 401, 403, 404, 409, 422].includes(e.response.status)
    ) {
      pendingConfirm.value = null
      clearPendingStorage()
      previewVisible.value = false
      message.warning('未确认创建，请检查配置后重新预览；修订冲突时请重新加载')
    } else message.warning('提交结果尚未确认，请重试同一请求，系统不会重复创建')
  } finally {
    submitting.value = false
  }
}
watch(
  [draft, rows, defaultSchemeId, activeId, structures],
  () => {
    if (!pendingConfirm.value) {
      previewVisible.value = false
      previewData.value = null
      previewPayload.value = null
    }
  },
  { deep: true },
)
function beforeUnload(e) {
  if (hasUnsaved.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onBeforeRouteLeave(async () => {
  if (pendingConfirm.value) {
    message.warning('上次提交结果尚未确认，请先重试确认')
    return false
  }
  return (
    !hasUnsaved.value ||
    (await ask(
      '离开工作台？',
      '未保存的结构、方案和本批行将丢失，已生成饰品保留。',
    ))
  )
})
onMounted(async () => {
  window.addEventListener('beforeunload', beforeUnload)
  await fetchData()
  try {
    const pending = JSON.parse(
      sessionStorage.getItem(pendingStorageKey.value) || 'null',
    )
    if (pending) {
      pendingConfirm.value = pending.request
      previewData.value = pending.preview
      previewPayload.value = pending.request.batch
      previewVisible.value = true
    }
  } catch {
    message.warning('无法读取上次重试记录，请先在已生成批次中核对结果')
  }
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>

<style scoped>
.structure-workbench {
  color: #1a2522;
  --line: #e5eae6;
  --muted: #7b8580;
  --green: #227654;
}
.blocked {
  pointer-events: none;
}
.crumb {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 12px;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
  margin-bottom: 20px;
}
.page-head h1 {
  font-size: 25px;
  margin: 0;
  font-weight: 650;
  letter-spacing: -0.7px;
}
.page-head p,
.panel-head p {
  color: var(--muted);
  font-size: 12px;
  margin: 5px 0 0;
}
.intro {
  margin: 16px 0 20px;
}
.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 20px;
  margin-top: 8px;
}
.panel {
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--line);
}
h2 {
  font-size: 16px;
  margin: 0;
}
h3 {
  font-size: 14px;
  margin: 0;
}
h2 i {
  color: var(--green);
  font:
    italic 17px Georgia,
    serif;
  margin-right: 10px;
}
.panel-body {
  padding: 18px 20px;
}
.panel-foot {
  background: #fafcf8;
  border-top: 1px solid var(--line);
  padding: 14px 20px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.helper {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.8;
  margin: 0;
}
.muted {
  color: var(--muted);
}
.field-label,
.fields label {
  display: block;
  color: var(--muted);
  font-size: 11px;
  margin-bottom: 6px;
}
.fields {
  display: grid;
  gap: 12px;
}
.fields.two {
  grid-template-columns: 1fr 1fr;
}
.fields.three {
  grid-template-columns: 1fr 1fr 1fr;
}
.fields label input,
.fields label :deep(.n-select) {
  margin-top: 5px;
}
input:not([type='checkbox']) {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  border: 1px solid #dfe5df;
  background: #fff;
  color: #1a2522;
  border-radius: 6px;
  padding: 8px;
  font: inherit;
  font-size: 12px;
  outline: 0;
}
input:focus {
  border-color: var(--green);
  box-shadow: 0 0 0 2px #22765412;
}
button {
  font: inherit;
  cursor: pointer;
}
button:focus-visible {
  outline: 2px solid var(--green);
  outline-offset: 2px;
}
.link {
  border: 0;
  background: transparent;
  color: var(--green);
  padding: 3px 0;
  font-size: 12px;
}
.tiny {
  font-size: 10px;
}
.delete {
  border: 0;
  background: transparent;
  color: #9aa59b;
  padding: 4px;
  font-size: 20px;
  line-height: 1.2;
}
.delete:hover {
  color: #b04439;
}
.spaced {
  margin-top: 16px;
}
.spaced-small {
  margin-top: 7px;
}
.chain {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
}
.chip {
  font-size: 11px;
  padding: 4px 9px;
  border: 1px solid #e0e8da;
  background: #f4f7f0;
  border-radius: 5px;
}
.slot-row,
.slot-head {
  display: grid;
  grid-template-columns: minmax(75px, 0.8fr) minmax(150px, 1.6fr) 65px 20px;
  gap: 9px;
  align-items: start;
  padding: 10px 0;
  border-bottom: 1px solid #eef1eb;
}
.slot-head {
  font-size: 10px;
  color: var(--muted);
  margin-top: 18px;
}
.slot-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 10px;
  margin-top: 5px;
  font-size: 10px;
  color: var(--muted);
}
.slot-meta label {
  display: flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}
.slot-meta input {
  margin: 0;
}
.order-actions {
  display: flex;
  gap: 5px;
  margin-top: 4px;
}
.order-actions button {
  border: 0;
  background: none;
  color: var(--muted);
  padding: 0 4px;
  font-size: 10px;
}
.order-actions button:disabled {
  opacity: 0.3;
}
.scheme-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.scheme-card {
  flex: 1;
  min-width: 105px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #fff;
  text-align: left;
}
.scheme-card.active {
  border-color: var(--green);
  background: #f0f6ec;
}
.scheme-card b {
  display: block;
  font-size: 12px;
}
.scheme-card span {
  display: block;
  color: var(--muted);
  font-size: 10px;
  margin-top: 3px;
}
.scheme-head,
.scheme-row {
  display: grid;
  grid-template-columns: 65px minmax(120px, 1fr) 76px;
  gap: 10px;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #eff2ed;
  font-size: 12px;
}
.scheme-head {
  color: var(--muted);
  font-size: 10px;
  margin-top: 15px;
}
.linked {
  background: #f1f6eb;
  color: #657552;
  padding: 11px 13px;
  border-left: 2px solid #9aaf84;
  font-size: 11px;
}
.batch {
  margin-top: 22px;
}
.batch-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px 20px;
  background: #fafcf8;
  border-bottom: 1px solid var(--line);
}
.batch-bar .field-label {
  margin: 0;
}
.table-wrap {
  overflow: auto;
}
.batch-table {
  width: 100%;
  border-collapse: collapse;
}
.batch-table th {
  text-align: left;
  font-size: 10px;
  font-weight: 500;
  color: var(--muted);
  background: #fcfdfb;
  padding: 12px 15px;
  white-space: nowrap;
}
.batch-table td {
  padding: 14px 15px;
  border-top: 1px solid #eef1eb;
  vertical-align: top;
  font-size: 12px;
  min-width: 185px;
}
.batch-table td:first-child {
  min-width: 35px;
  width: 35px;
  color: #9ca79a;
}
.batch-table td:nth-child(2) {
  min-width: 180px;
}
.row-summary {
  max-width: 230px;
  margin-top: 7px;
}
.batch-footer {
  padding: 18px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
  border-top: 1px solid var(--line);
}
.empty {
  text-align: center;
  padding: 30px !important;
  color: var(--muted);
}
.permission-note {
  padding: 0 20px 15px;
}
.mobile-hint {
  display: none;
}
.detail-row {
  display: grid;
  grid-template-columns: minmax(70px, 0.8fr) minmax(160px, 1.5fr) 85px 24px;
  gap: 10px;
  align-items: center;
  padding: 13px 0;
  border-bottom: 1px solid #e9eee5;
}
.preview-item {
  padding: 15px;
  border: 1px solid #e5eae6;
  border-radius: 7px;
  margin-top: 15px;
}
.preview-item h3 {
  margin-bottom: 10px;
}
.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(245px, 1fr));
  gap: 17px;
  padding: 20px;
}
.history-grid article {
  border: 1px solid #e5eae6;
  border-radius: 7px;
  padding: 16px;
}
.history-line {
  display: flex;
  justify-content: space-between;
  gap: 15px;
  padding: 8px 0;
  border-bottom: 1px solid #edf1e8;
  font-size: 12px;
}
.history-line b {
  font-weight: 500;
  white-space: nowrap;
}
.history-grid a {
  display: block;
  font-size: 12px;
  color: #227654;
  margin-top: 13px;
}
.n-modal input:not([type='checkbox']) {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  border: 1px solid #dfe5df;
  border-radius: 5px;
  padding: 8px;
  font: inherit;
  font-size: 12px;
}
@media (max-width: 1200px) {
  .workspace {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 600px) {
  .page-head {
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .page-head h1 {
    font-size: 22px;
  }
  .page-head p {
    font-size: 11px;
  }
  .panel-head,
  .panel-body {
    padding: 15px;
  }
  .panel-foot {
    padding: 12px 15px;
  }
  .slot-row,
  .slot-head {
    grid-template-columns: 65px minmax(110px, 1fr) 51px 18px;
    gap: 6px;
  }
  .slot-row input:not([type='checkbox']) {
    padding: 7px 4px;
    font-size: 11px;
  }
  .scheme-row,
  .scheme-head {
    grid-template-columns: 60px minmax(100px, 1fr) 60px;
    gap: 7px;
  }
  .batch-footer {
    align-items: stretch;
    flex-direction: column;
    padding: 15px;
  }
  .batch-footer .n-button {
    width: 100%;
  }
  .batch-bar {
    padding: 13px 15px;
  }
  .mobile-hint {
    display: block;
    padding: 8px 15px;
  }
  .detail-row {
    grid-template-columns: 65px minmax(100px, 1fr) 60px 20px;
    gap: 6px;
  }
  .detail-row input {
    padding: 6px 4px !important;
    font-size: 11px !important;
  }
  .fields.three {
    grid-template-columns: 1fr;
  }
  .history-grid {
    padding: 15px;
  }
  .fields.two {
    gap: 8px;
  }
}
</style>

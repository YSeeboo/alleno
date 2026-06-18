<template>
  <n-modal
    :show="show"
    preset="card"
    :title="`手工单 ${orderId || ''}`"
    :style="{ width: '580px', maxWidth: '95vw' }"
    :mask-closable="true"
    @update:show="$emit('update:show', $event)"
  >
    <n-spin :show="loading">
      <div v-if="!loading && order">
        <!-- 顶部信息 grid -->
        <div
          style="
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px 18px;
            margin-bottom: 18px;
            background: #f8f8fc;
            border-radius: 8px;
            padding: 14px 16px;
          "
        >
          <div>
            <div style="font-size: 11px; color: #9ca3af; margin-bottom: 3px;">回执码</div>
            <div style="font-weight: 600; font-size: 14px; letter-spacing: 1px; color: #333;">
              {{ order.receipt_code || '—' }}
            </div>
          </div>
          <div>
            <div style="font-size: 11px; color: #9ca3af; margin-bottom: 3px;">手工商家</div>
            <div style="font-weight: 500; font-size: 14px; color: #333;">
              {{ order.supplier_name || '—' }}
            </div>
          </div>
          <div>
            <div style="font-size: 11px; color: #9ca3af; margin-bottom: 3px;">状态</div>
            <span
              :style="{
                display: 'inline-block',
                padding: '2px 10px',
                borderRadius: '12px',
                fontSize: '12px',
                fontWeight: 600,
                background: statusBg(order.status),
                color: statusColor(order.status),
              }"
            >
              {{ statusLabel(order.status) }}
            </span>
          </div>
          <div>
            <div style="font-size: 11px; color: #9ca3af; margin-bottom: 3px;">创建时间</div>
            <div style="font-size: 13px; color: #555;">
              {{ fmtDate(order.created_at) }}
            </div>
          </div>
        </div>

        <!-- 产出项列表 -->
        <div style="margin-bottom: 14px;">
          <div style="font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
            <span style="width: 3px; height: 14px; background: #6366F1; border-radius: 2px; display: inline-block;"></span>
            产出项
            <span style="font-weight: 400; font-size: 12px; color: #9ca3af;">({{ jewelries.length }} 条)</span>
          </div>
          <div v-if="jewelries.length === 0" style="color: #9ca3af; font-size: 13px; padding: 6px 0;">无产出项</div>
          <div
            v-for="item in jewelries"
            :key="item.id || item.jewelry_id || item.part_id"
            style="
              display: flex;
              align-items: center;
              justify-content: space-between;
              padding: 8px 10px;
              border-radius: 6px;
              background: #fafaff;
              margin-bottom: 6px;
              border: 1px solid #ebebf8;
            "
          >
            <div style="display: flex; align-items: center; gap: 8px; min-width: 0;">
              <span style="font-size: 13px; color: #222; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ item.jewelry_name || item.part_name || item.jewelry_id || item.part_id || '—' }}
              </span>
              <span
                :style="{
                  fontSize: '11px',
                  padding: '1px 6px',
                  borderRadius: '8px',
                  background: item.part_id ? '#fef3c7' : '#e0e7ff',
                  color: item.part_id ? '#92400e' : '#3730a3',
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                }"
              >
                {{ item.part_id ? '配件' : (item.is_composite ? '组合' : '饰品') }}
              </span>
            </div>
            <div style="font-size: 12px; color: #6b7280; white-space: nowrap; flex-shrink: 0; margin-left: 8px;">
              已收回 <strong style="color: #374151;">{{ item.received_qty ?? 0 }}</strong> / {{ item.qty ?? '—' }}
            </div>
          </div>
        </div>

        <!-- 发出配件列表 -->
        <div>
          <div style="font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
            <span style="width: 3px; height: 14px; background: #f59e0b; border-radius: 2px; display: inline-block;"></span>
            发出配件
            <span style="font-weight: 400; font-size: 12px; color: #9ca3af;">({{ parts.length }} 条)</span>
          </div>
          <div v-if="parts.length === 0" style="color: #9ca3af; font-size: 13px; padding: 6px 0;">无发出配件</div>
          <div
            v-for="item in parts"
            :key="item.id || item.part_id"
            style="
              display: flex;
              align-items: center;
              justify-content: space-between;
              padding: 8px 10px;
              border-radius: 6px;
              background: #fffdf5;
              margin-bottom: 6px;
              border: 1px solid #fde68a;
            "
          >
            <span style="font-size: 13px; color: #222; font-weight: 500;">
              {{ item.part_name || item.part_id || '—' }}
            </span>
            <span style="font-size: 12px; color: #6b7280; white-space: nowrap; margin-left: 8px;">
              数量 <strong style="color: #374151;">{{ item.qty ?? '—' }}</strong>
            </span>
          </div>
        </div>
      </div>

      <n-empty v-if="!loading && !order && orderId" description="加载失败，请重试" style="margin: 24px 0;" />
    </n-spin>

    <template #footer>
      <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <n-button @click="$emit('update:show', false)">关闭</n-button>
        <n-button
          type="primary"
          ghost
          :disabled="!orderId"
          @click="openFull"
        >
          打开完整手工单 ↗
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NModal, NSpin, NEmpty, NButton } from 'naive-ui'
import { getHandcraft, getHandcraftParts, getHandcraftJewelries } from '@/api/handcraft'

const props = defineProps({
  show: { type: Boolean, default: false },
  orderId: { type: String, default: null },
})

defineEmits(['update:show'])

const router = useRouter()

const loading = ref(false)
const order = ref(null)
const parts = ref([])
const jewelries = ref([])

const fetchData = async (id) => {
  if (!id) return
  loading.value = true
  order.value = null
  parts.value = []
  jewelries.value = []
  try {
    const [orderRes, partsRes, jewelriesRes] = await Promise.all([
      getHandcraft(id),
      getHandcraftParts(id),
      getHandcraftJewelries(id),
    ])
    order.value = orderRes.data
    parts.value = partsRes.data || []
    jewelries.value = jewelriesRes.data || []
  } catch (_) {
    order.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => props.orderId,
  (id) => {
    if (id) fetchData(id)
  },
  { immediate: true },
)

const openFull = () => {
  if (props.orderId) router.push(`/handcraft/${props.orderId}`)
}

const fmtDate = (val) => {
  if (!val) return '—'
  try {
    return new Date(val).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
  } catch (_) {
    return val
  }
}

const STATUS_LABEL = {
  pending: '待发出',
  processing: '制作中',
  completed: '已完成',
}
const STATUS_BG = {
  pending: '#f3f4f6',
  processing: '#dbeafe',
  completed: '#dcfce7',
}
const STATUS_COLOR = {
  pending: '#6b7280',
  processing: '#1d4ed8',
  completed: '#15803d',
}
const statusLabel = (s) => STATUS_LABEL[s] || s || '—'
const statusBg = (s) => STATUS_BG[s] || '#f3f4f6'
const statusColor = (s) => STATUS_COLOR[s] || '#374151'
</script>

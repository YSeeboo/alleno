<template>
  <div v-if="preview" class="bb">
    <div class="bb__icon">📋</div>
    <div class="bb__body">
      <div class="bb__head">
        <span class="bb__title">客户分拣预览</span>
        <span class="bb__hc">
          已并入 <strong>{{ preview.handcraft_order_id }}</strong>
          <span class="mono">· 回执 {{ preview.receipt_code }}</span>
        </span>
      </div>
      <div v-if="preview.jewelry_items.length" class="bb__desc">
        此订单<template v-if="preview.customer_name">（<strong>{{ preview.customer_name }}</strong>）</template>在该 HC 的分拣中将占：
      </div>
      <ul v-if="preview.jewelry_items.length" class="bb__list">
        <li v-for="it in preview.jewelry_items" :key="it.jewelry_id">
          {{ it.jewelry_name }}<span class="qty"> · {{ it.qty }} 套</span>
        </li>
      </ul>
      <div v-else class="bb__desc">此批次仅提供配件，无饰品分拣份额</div>
    </div>
    <div class="bb__action">
      <n-button size="small" @click="jumpToHc">查看 HC →</n-button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton } from 'naive-ui'
import { getBatchBreakdownPreview } from '@/api/orders'

const props = defineProps({
  orderId: { type: String, required: true },
  batchId: { type: [String, Number], required: true },
})
const router = useRouter()
const preview = ref(null)

async function load() {
  if (!props.orderId || !props.batchId) {
    preview.value = null
    return
  }
  try {
    const { data } = await getBatchBreakdownPreview(props.orderId, props.batchId)
    preview.value = data
  } catch (_) {
    preview.value = null
  }
}
watch(() => [props.orderId, props.batchId], load, { immediate: true })

function jumpToHc() {
  if (preview.value) {
    router.push(`/handcraft/${preview.value.handcraft_order_id}`)
  }
}
</script>

<style scoped>
.bb {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  background: #ecf3fd;
  border: 1px solid #c6dcf9;
  padding: 12px 14px;
  border-radius: 4px;
  margin-bottom: 14px;
}
.bb__icon { font-size: 18px; flex-shrink: 0; line-height: 1.2; }
.bb__body { flex: 1; }
.bb__head {
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 6px;
}
.bb__title { font-weight: 600; font-size: 13px; }
.bb__hc { font-size: 12px; color: rgba(0, 0, 0, 0.65); }
.bb__hc strong {
  color: #2080f0;
  font-family: "SF Mono", Menlo, monospace;
}
.bb__hc .mono {
  font-family: "SF Mono", Menlo, monospace;
  color: rgba(0, 0, 0, 0.45);
}
.bb__desc {
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
  margin-bottom: 6px;
}
.bb__desc strong { color: rgba(0, 0, 0, 0.88); font-weight: 500; }
.bb__list {
  list-style: none;
  margin-left: 4px;
  padding: 0;
}
.bb__list li {
  padding: 2px 0;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.88);
}
.bb__list li::before {
  content: "· ";
  color: rgba(0, 0, 0, 0.45);
  font-weight: 700;
}
.bb__list .qty {
  font-family: "SF Mono", Menlo, monospace;
  color: rgba(0, 0, 0, 0.65);
}
.bb__action { margin-left: auto; flex-shrink: 0; }
</style>

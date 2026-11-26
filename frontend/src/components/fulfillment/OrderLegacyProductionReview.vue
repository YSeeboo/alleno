<template>
  <n-modal :show="true" preset="card" title="旧生产记录核对" style="width:min(720px,calc(100vw - 24px))" @update:show="!$event && $emit('close')">
    <p>{{ line.product_name }} · {{ line.product_id }} · 订单明细 #{{ line.id }}</p>
    <n-alert :type="line.legacy_claim ? 'warning' : 'info'" :bordered="false">
      {{ line.legacy_claim ? '存在旧产出关联或已绑定加工单的批次，仍需核对具体归属，不能直接新增份额。' : '以下旧批次未绑定加工单或产出，仅作历史参考，不再阻止安排制作。' }}
      旧批次数量不是当前明细已安排量，也不是实收或出货量；同名客户不能自动认领为本订单。
    </n-alert>
    <div class="legacy-records">
      <section v-for="record in line.legacy_batches || []" :key="record.batch_id">
        <strong>旧批次 #{{ record.batch_id }}</strong>
        <p>原批次数量 {{ record.quantity }} {{ line.unit }} · 当前订购 {{ line.quantity }} {{ line.unit }}</p>
        <p v-if="Number(record.quantity) !== Number(line.quantity)" class="legacy-warning">原批次数量与当前订购量不同，不自动补齐或转换。</p>
        <p>{{ record.blocks_allocation ? '已记录加工单／产出引用，保留归属保护' : '未绑定加工单／产出，不计入生产安排' }}</p>
        <router-link v-if="record.production_order_id" :to="{ path: `/handcraft/${record.production_order_id}`, query: { from_order: orderId } }">{{ record.production_order_id }} → 查看原加工单</router-link>
        <small v-if="record.source_item_id">原产出明细 #{{ record.source_item_id }}</small>
      </section>
      <p v-if="!line.legacy_batches?.length">此明细有旧关联，请结合本页加工单列表与完整历史记录核对具体来源。</p>
    </div>
    <p>旧材料清单的投入、回收记录继续保留。新增安排前，请核对已有库存与历史加工，填写实际仍需制作的数量；当前新份额为 0 不代表从未生产。</p>
    <n-space justify="end">
      <n-button @click="$emit('history')">查看完整历史关联</n-button>
      <n-button type="primary" @click="$emit('close')">返回</n-button>
    </n-space>
  </n-modal>
</template>
<script setup>
import { NAlert, NButton, NModal, NSpace } from 'naive-ui'
defineProps({ orderId: { type: String, required: true }, line: { type: Object, required: true } })
defineEmits(['close', 'history'])
</script>
<style scoped>
.legacy-records { max-height:45vh; overflow:auto; margin:16px 0; }
.legacy-records section { padding:12px 0; border-bottom:1px solid #eceef0; }
.legacy-records p { margin:6px 0; }.legacy-records small { display:block; color:#777; }
.legacy-warning { color:#a46613; }
</style>

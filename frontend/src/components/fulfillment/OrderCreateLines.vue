<template>
  <section class="om-section">
    <header class="om-section-head"><div><span class="om-section-number">{{ kind === 'jewelry' ? '02' : '03' }}</span><h3>{{ label }}明细</h3></div><div class="om-actions"><span class="om-muted">{{ items.length }} 项</span><n-button size="small" :disabled="disabled" @click="$emit('add')">＋ 添加{{ label }}</n-button></div></header>
    <div class="om-panel">
      <div v-if="items.length" class="om-entry-scroll" tabindex="0" role="region" :aria-label="`${label}编辑表格，可横向滚动`">
        <n-table :bordered="false" class="om-entry-table"><thead><tr><th>#</th><th>商品</th><th>订购数量</th><th>单价</th><th class="om-num">小计</th><th>明细备注</th><th>操作</th></tr></thead><tbody>
          <tr v-for="(item, index) in items" :key="item.key" :data-line-key="item.key">
            <td class="om-line-index">{{ String(index + 1).padStart(2, '0') }}</td>
            <td><div class="om-entry-product"><img v-if="catalog[item[idField]]?.image" :src="catalog[item[idField]].image" alt=""><span v-else class="om-product-placeholder">{{ label }}</span><div><n-select v-model:value="item[idField]" :options="options" :render-label="renderOptionWithImage" :render-tag="renderSelectedProduct" filterable clearable :disabled="disabled" :placeholder="`选择${label}`" :aria-label="`第 ${index + 1} 行${label}`" @update:value="value => $emit('select', item, value)" /><small class="om-subtext">{{ item[idField] || '选择商品后带入参考单价' }}</small></div></div></td>
            <td><div class="om-quantity"><n-input-number v-model:value="item.quantity" :min="1" :show-button="false" :disabled="disabled" placeholder="数量" :input-props="{ 'aria-label': `第 ${index + 1} 行${label}数量` }" /><span>{{ catalog[item[idField]]?.unit || '—' }}</span></div></td>
            <td><n-input-number v-model:value="item.unit_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :show-button="false" :disabled="disabled" placeholder="单价" :input-props="{ 'aria-label': `第 ${index + 1} 行${label}单价` }" /></td>
            <td class="om-num om-line-total">{{ lineAmount(item) }}</td>
            <td><n-input v-model:value="item.remarks" :disabled="disabled" placeholder="选填" :input-props="{ 'aria-label': `第 ${index + 1} 行${label}备注` }" /></td>
            <td><n-button text size="small" :disabled="disabled" :aria-label="`删除第 ${index + 1} 行${label}`" @click="$emit('remove', item.key)">删除</n-button></td>
          </tr>
        </tbody></n-table>
      </div>
      <n-empty v-else :description="`还没有${label}明细`" class="om-entry-empty"><template #extra><span class="om-muted">可以只添加饰品，或直接销售配件。</span></template></n-empty>
      <div v-if="items.length" class="om-section-subtotal">{{ label }}小计<strong>¥{{ formatOrderAmount(subtotal) }}</strong></div>
    </div>
  </section>
</template>
<script setup>
import { computed, h } from 'vue'
import { NButton, NEmpty, NInput, NInputNumber, NSelect, NTable } from 'naive-ui'
import { renderOptionWithImage, fmtPrice, parseNum } from '@/utils/ui'
import { orderLineAmount, formatOrderAmount } from '@/utils/orderManagement'
const props = defineProps({ kind: String, items: Array, options: Array, catalog: Object, subtotal: BigInt, disabled: Boolean })
defineEmits(['add', 'select', 'remove'])
const label = computed(() => props.kind === 'jewelry' ? '饰品' : '配件')
const idField = computed(() => props.kind === 'jewelry' ? 'jewelry_id' : 'part_id')
const renderSelectedProduct = ({ option }) => h('span', { class: 'om-selected-product', title: option.name || option.label }, option.name || option.label)
function lineAmount(item) {
  if (!props.catalog[item[idField.value]]) return '—'
  try { return `¥${formatOrderAmount(orderLineAmount(item))}` } catch { return '待完善' }
}
</script>

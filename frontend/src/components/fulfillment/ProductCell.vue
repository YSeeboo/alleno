<template>
  <div class="wf-product">
    <img v-if="line.image" :src="line.image" alt="" loading="lazy"><span v-else class="wf-product-placeholder">{{ line.product_name?.charAt(0) || '◇' }}</span>
    <div><n-button v-if="interactive" text class="ow-product-name" @click="$emit('inspect', line)">{{ line.product_name }}</n-button><strong v-else>{{ line.product_name }}</strong><small class="wf-subtext">{{ line.product_id }} · 明细 #{{ line.id || line.order_item_id }}</small><small v-if="line.customer_code" class="wf-subtext">客户货号 {{ line.customer_code }}</small></div>
  </div>
</template>
<script setup>
import { NButton } from 'naive-ui'
defineProps({ line: { type: Object, required: true }, interactive: Boolean })
defineEmits(['inspect'])
</script>

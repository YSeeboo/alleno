<template>
  <section class="ow-section">
    <header v-if="title || $slots['header-extra']" class="ow-section-head">
      <div class="ow-section-title"><h3>{{ title }}</h3><span v-if="count != null" class="ow-count">{{ count }}</span></div>
      <div v-if="$slots['header-extra']" class="wf-actions"><slot name="header-extra" /></div>
    </header>
    <slot />
    <div v-if="$slots.footer" class="ow-table-note"><slot name="footer" /></div>
  </section>
</template>
<script setup>
defineProps({ title: String, count: [String, Number] })
</script>

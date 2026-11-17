<template>
  <div class="handcraft-management">
    <header class="hm-header">
      <div class="page-breadcrumb">生产管理 / 手工管理</div>
      <div class="hm-heading">
        <div>
          <h1>手工管理</h1>
          <p>汇总、发出与回收，在同一个入口切换。</p>
        </div>
        <span class="hm-memory"><n-icon :component="TimeOutline" />自动记住上次打开的页面</span>
      </div>
    </header>
    <div ref="tabList" class="hm-tabs" role="tablist" aria-label="手工业务页面" @keydown="onTabKeydown">
      <router-link v-for="tab in HANDCRAFT_TABS" :key="tab.key" v-slot="{ href, navigate }" :to="tabLocation(tab)" custom>
        <a
          :id="`handcraft-tab-${tab.key}`"
          :href="href"
          class="hm-tab"
          role="tab"
          :aria-selected="activeTab.key === tab.key"
          :aria-controls="`handcraft-panel-${tab.key}`"
          :tabindex="activeTab.key === tab.key ? 0 : -1"
          @click="navigate"
        ><n-icon :component="tabIcons[tab.key]" />{{ tab.label }}</a>
      </router-link>
    </div>
    <section :id="`handcraft-panel-${activeTab.key}`" class="hm-content" role="tabpanel" :aria-labelledby="`handcraft-tab-${activeTab.key}`">
      <router-view />
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { BarChartOutline, DownloadOutline, PaperPlaneOutline, TimeOutline } from '@vicons/ionicons5'
import { HANDCRAFT_TABS, getHandcraftLocation, getHandcraftTab } from '@/utils/handcraftNavigation'

const route = useRoute()
const router = useRouter()
const tabList = ref(null)
const activeTab = computed(() => getHandcraftTab(route.path) || HANDCRAFT_TABS[0])
const tabIcons = { summary: BarChartOutline, dispatch: PaperPlaneOutline, receipt: DownloadOutline }

async function revealActiveTab() {
  await nextTick()
  const list = tabList.value
  const tab = list?.querySelector(`#handcraft-tab-${activeTab.value.key}`)
  if (!tab) return
  const bounds = list.getBoundingClientRect()
  const selected = tab.getBoundingClientRect()
  if (selected.left < bounds.left) list.scrollLeft += selected.left - bounds.left
  else if (selected.right > bounds.right) list.scrollLeft += selected.right - bounds.right
}
watch(activeTab, revealActiveTab)
let resizeObserver
onMounted(() => {
  resizeObserver = new ResizeObserver(revealActiveTab)
  resizeObserver.observe(tabList.value)
  void revealActiveTab()
})
onBeforeUnmount(() => resizeObserver?.disconnect())

function tabLocation(tab) {
  return activeTab.value.key === tab.key ? { path: tab.path, query: route.query } : getHandcraftLocation(tab.key)
}

async function onTabKeydown(event) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const current = HANDCRAFT_TABS.findIndex((tab) => tab.key === activeTab.value.key)
  const index = event.key === 'Home' ? 0 : event.key === 'End' ? HANDCRAFT_TABS.length - 1
    : (current + (event.key === 'ArrowRight' ? 1 : HANDCRAFT_TABS.length - 1)) % HANDCRAFT_TABS.length
  await router.push(tabLocation(HANDCRAFT_TABS[index]))
  await nextTick()
  tabList.value?.querySelector(`#handcraft-tab-${HANDCRAFT_TABS[index].key}`)?.focus()
}
</script>

<style scoped>
.handcraft-management { min-width: 0; }
.hm-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.hm-heading h1 { margin: 0; font-size: 27px; font-weight: 700; color: #1A1D21; letter-spacing: -.6px; }
.hm-heading p { margin: 5px 0 0; color: #8B9096; font-size: 12px; }
.hm-memory { display: inline-flex; align-items: center; gap: 6px; color: #8E969C; font-size: 11px; white-space: nowrap; }
.hm-memory :deep(.n-icon) { font-size: 14px; }
.hm-tabs { display: flex; gap: 31px; margin-top: 26px; border-bottom: 1px solid #E1E5E7; overflow-x: auto; }
.hm-tab { position: relative; display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 0 3px 15px; color: #818A91; text-decoration: none; white-space: nowrap; font-size: 14px; }
.hm-tab :deep(.n-icon) { font-size: 17px; }
.hm-tab:hover, .hm-tab[aria-selected="true"] { color: #1E7A5A; }
.hm-tab[aria-selected="true"] { font-weight: 650; }
.hm-tab[aria-selected="true"]::after { content: ''; position: absolute; bottom: -1px; left: 0; right: 0; height: 3px; border-radius: 3px 3px 0 0; background: #1E7A5A; }
.hm-tab:focus-visible { outline: 2px solid #1E7A5A; outline-offset: 4px; border-radius: 3px; }
.hm-content { padding-top: 25px; min-width: 0; }
@media (max-width: 768px) {
  .hm-header { padding-top: 2px; }
  .hm-header > .page-breadcrumb { margin-left: 48px; min-height: 24px; }
  .hm-heading h1 { font-size: 25px; }
  .hm-memory { display: none; }
  .hm-tabs { gap: 20px; margin-top: 23px; }
  .hm-tab { flex-shrink: 0; gap: 6px; font-size: 13px; padding-bottom: 13px; }
  .hm-tab :deep(.n-icon) { font-size: 15px; }
  .hm-content { padding-top: 20px; }
}
</style>

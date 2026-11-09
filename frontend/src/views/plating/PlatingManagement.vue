<template>
  <div class="plating-management">
    <header class="pm-header">
      <div class="page-breadcrumb">生产管理 / 电镀管理</div>
      <div class="pm-heading">
        <div>
          <h1>电镀管理</h1>
          <p>汇总、发出、回收与商家对账，在同一个入口切换。</p>
        </div>
        <span class="pm-memory"><n-icon :component="TimeOutline" />自动记住上次打开的页面</span>
      </div>
    </header>
    <div ref="tabList" class="pm-tabs" role="tablist" aria-label="电镀业务页面" @keydown="onTabKeydown">
      <router-link v-for="tab in PLATING_TABS" :key="tab.key" v-slot="{ href, navigate }" :to="tabLocation(tab)" custom>
        <a
          :id="`plating-tab-${tab.key}`"
          :href="href"
          class="pm-tab"
          role="tab"
          :aria-selected="activeTab.key === tab.key"
          :aria-controls="`plating-panel-${tab.key}`"
          :tabindex="activeTab.key === tab.key ? 0 : -1"
          @click="navigate"
        ><n-icon :component="tabIcons[tab.key]" />{{ tab.label }}</a>
      </router-link>
    </div>
    <section :id="`plating-panel-${activeTab.key}`" class="pm-content" role="tabpanel" :aria-labelledby="`plating-tab-${activeTab.key}`">
      <router-view />
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { DocumentTextOutline, DownloadOutline, PaperPlaneOutline, TimeOutline } from '@vicons/ionicons5'
import PlatingSummaryIcon from '@/components/icons/PlatingSummaryIcon.vue'
import { PLATING_TABS, getPlatingLocation, getPlatingTab } from '@/utils/platingNavigation'

const route = useRoute()
const router = useRouter()
const tabList = ref(null)
const activeTab = computed(() => getPlatingTab(route.path) || PLATING_TABS[0])
const tabIcons = { summary: PlatingSummaryIcon, dispatch: PaperPlaneOutline, receipt: DownloadOutline, reconciliation: DocumentTextOutline }

async function revealActiveTab() {
  await nextTick()
  const list = tabList.value
  const tab = list?.querySelector(`#plating-tab-${activeTab.value.key}`)
  if (!tab) return
  const bounds = list.getBoundingClientRect()
  const selected = tab.getBoundingClientRect()
  // Reveal horizontally without changing the page's vertical scroll position.
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
  return activeTab.value.key === tab.key ? { path: tab.path, query: route.query } : getPlatingLocation(tab.key)
}

async function onTabKeydown(event) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const current = PLATING_TABS.findIndex((tab) => tab.key === activeTab.value.key)
  const index = event.key === 'Home' ? 0 : event.key === 'End' ? PLATING_TABS.length - 1
    : (current + (event.key === 'ArrowRight' ? 1 : PLATING_TABS.length - 1)) % PLATING_TABS.length
  await router.push(tabLocation(PLATING_TABS[index]))
  await nextTick()
  tabList.value?.querySelector(`#plating-tab-${PLATING_TABS[index].key}`)?.focus()
}
</script>

<style scoped>
.plating-management { min-width: 0; }
.pm-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.pm-heading h1 { margin: 0; font-size: 27px; font-weight: 700; color: #1A1D21; letter-spacing: -.6px; }
.pm-heading p { margin: 5px 0 0; color: #8B9096; font-size: 12px; }
.pm-memory { display: inline-flex; align-items: center; gap: 6px; color: #8E969C; font-size: 11px; white-space: nowrap; }
.pm-memory :deep(.n-icon) { font-size: 14px; }
.pm-tabs { display: flex; gap: 31px; margin-top: 26px; border-bottom: 1px solid #E1E5E7; overflow-x: auto; }
.pm-tab { position: relative; display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 0 3px 15px; color: #818A91; text-decoration: none; white-space: nowrap; font-size: 14px; }
.pm-tab :deep(.n-icon) { font-size: 17px; }
.pm-tab:hover, .pm-tab[aria-selected="true"] { color: #1E7A5A; }
.pm-tab[aria-selected="true"] { font-weight: 650; }
.pm-tab[aria-selected="true"]::after { content: ''; position: absolute; bottom: -1px; left: 0; right: 0; height: 3px; border-radius: 3px 3px 0 0; background: #1E7A5A; }
.pm-tab:focus-visible { outline: 2px solid #1E7A5A; outline-offset: 4px; border-radius: 3px; }
.pm-content { padding-top: 25px; min-width: 0; }
@media (max-width: 767px) {
  .pm-header { padding-top: 2px; }
  .pm-header > .page-breadcrumb { margin-left: 48px; min-height: 24px; }
  .pm-heading h1 { font-size: 25px; }
  .pm-memory { display: none; }
  .pm-tabs { gap: 20px; margin-top: 23px; }
  .pm-tab { flex-shrink: 0; gap: 6px; font-size: 13px; padding-bottom: 13px; }
  .pm-tab :deep(.n-icon) { font-size: 15px; }
  .pm-content { padding-top: 20px; }
}
</style>

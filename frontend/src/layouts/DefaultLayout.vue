<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered style="height: 60px; padding: 0 24px; display: flex; align-items: center; justify-content: space-between;">
      <div class="brand">
        <span class="brand-gem">◆</span>
        <span class="brand-en">ALLENOP</span>
        <span class="brand-sep">|</span>
        <span class="brand-zh">管理系统</span>
      </div>
    </n-layout-header>
    <n-layout has-sider style="height: calc(100vh - 60px)">
      <n-layout-sider
        bordered
        collapse-mode="width"
        :collapsed-width="64"
        :width="220"
        :collapsed="collapsed"
        show-trigger
        @collapse="collapsed = true"
        @expand="collapsed = false"
      >
        <n-menu
          :collapsed="collapsed"
          :collapsed-width="64"
          :collapsed-icon-size="22"
          :options="menuOptions"
          :value="activeKey"
          @update:value="handleSelect"
        />
      </n-layout-sider>
      <n-layout-content content-style="padding: 28px; overflow-y: auto; background: #F6F5F1;">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup>
import { ref, computed, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutSider, NLayoutContent, NMenu } from 'naive-ui'
import {
  HomeOutline, ExtensionPuzzleOutline, DiamondOutline, ReceiptOutline,
  ColorWandOutline, HammerOutline, ListOutline, GridOutline,
} from '@vicons/ionicons5'

const router = useRouter()
const route = useRoute()
const collapsed = ref(false)

const icon = (Comp) => () => h(Comp)

const menuOptions = [
  { label: '仪表盘', key: 'dashboard', icon: icon(HomeOutline) },
  { label: '配件管理', key: 'parts', icon: icon(ExtensionPuzzleOutline) },
  { label: '饰品管理', key: 'jewelries', icon: icon(DiamondOutline) },
  { label: '订单管理', key: 'orders', icon: icon(ReceiptOutline) },
  { label: '电镀单', key: 'plating', icon: icon(ColorWandOutline) },
  { label: '手工单', key: 'handcraft', icon: icon(HammerOutline) },
  { label: '库存流水', key: 'inventory-log', icon: icon(ListOutline) },
  { label: '进度看板', key: 'kanban', icon: icon(GridOutline) },
]

const activeKey = computed(() => {
  const seg = route.path.split('/')[1]
  return seg || 'dashboard'
})

const handleSelect = (key) => {
  router.push(key === 'dashboard' ? '/' : `/${key}`)
}
</script>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-gem {
  color: #C4952A;
  font-size: 14px;
  line-height: 1;
}

.brand-en {
  color: #E8DCC8;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.brand-sep {
  color: #3A3830;
  font-size: 16px;
}

.brand-zh {
  color: #6B6560;
  font-size: 13px;
  letter-spacing: 0.05em;
}
</style>

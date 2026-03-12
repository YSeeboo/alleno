<template>
  <n-layout style="height: 100vh">
    <n-layout-header
      bordered
      style="height: 64px; padding: 0 24px; display: flex; align-items: center;"
    >
      <n-text :style="{ fontSize: '20px', fontWeight: 600, color: BRAND_COLOR }">
        Allenop 管理系统
      </n-text>
    </n-layout-header>
    <n-layout has-sider style="height: calc(100vh - 64px)">
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
      <n-layout-content content-style="padding: 24px; overflow-y: auto;">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup>
import { ref, computed, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NLayout, NLayoutHeader, NLayoutSider, NLayoutContent, NMenu, NText,
} from 'naive-ui'
import {
  HomeOutline, ExtensionPuzzleOutline, DiamondOutline, ReceiptOutline,
  ColorWandOutline, HammerOutline, ListOutline,
} from '@vicons/ionicons5'
import { BRAND_COLOR } from '@/utils/ui'

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
]

const activeKey = computed(() => {
  const seg = route.path.split('/')[1]
  return seg || 'dashboard'
})

const handleSelect = (key) => {
  router.push(key === 'dashboard' ? '/' : `/${key}`)
}
</script>

<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered style="height: 52px; padding: 0 24px; display: flex; align-items: center; justify-content: space-between;">
      <div class="brand">
        <span class="brand-icon">◈</span>
        <span class="brand-en">ALLENOP</span>
      </div>
      <div class="actions">
        <span class="action-icon">?</span>
        <span class="action-icon">⚙</span>
      </div>
    </n-layout-header>
    <n-layout has-sider style="height: calc(100vh - 52px)">
      <n-layout-sider
        bordered
        collapse-mode="width"
        :collapsed-width="52"
        :width="240"
        :collapsed="collapsed"
        show-trigger
        @collapse="collapsed = true"
        @expand="collapsed = false"
      >
        <n-menu
          :collapsed="collapsed"
          :collapsed-width="52"
          :collapsed-icon-size="22"
          :options="menuOptions"
          :value="activeKey"
          @update:value="handleSelect"
        />
      </n-layout-sider>
      <n-layout-content content-style="padding: 28px; overflow-y: auto;">
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
  ColorWandOutline, HammerOutline, ListOutline, GridOutline, ArchiveOutline,
} from '@vicons/ionicons5'

const router = useRouter()
const route = useRoute()
const collapsed = ref(false)

const icon = (Comp) => () => h(Comp)

const menuOptions = [
  {
    type: 'group',
    label: '工作台',
    key: 'group-workbench',
    children: [
      { label: '进度看板', key: 'kanban', icon: icon(GridOutline) },
      { label: '仪表盘', key: 'dashboard', icon: icon(HomeOutline) },
    ],
  },
  {
    type: 'group',
    label: '商品',
    key: 'group-products',
    children: [
      { label: '配件管理', key: 'parts', icon: icon(ExtensionPuzzleOutline) },
      { label: '饰品管理', key: 'jewelries', icon: icon(DiamondOutline) },
    ],
  },
  {
    type: 'group',
    label: '生产',
    key: 'group-production',
    children: [
      { label: '订单管理', key: 'orders', icon: icon(ReceiptOutline) },
      { label: '电镀单', key: 'plating', icon: icon(ColorWandOutline) },
      { label: '手工单', key: 'handcraft', icon: icon(HammerOutline) },
    ],
  },
  {
    type: 'group',
    label: '库存',
    key: 'group-inventory',
    children: [
      { label: '库存总表', key: 'inventory', icon: icon(ArchiveOutline) },
      { label: '库存流水', key: 'inventory-log', icon: icon(ListOutline) },
    ],
  },
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
  gap: 8px;
}

.brand-icon {
  color: #6366F1;
  font-size: 18px;
  line-height: 1;
}

.brand-en {
  color: #F1F5F9;
  font-size: 15px;
  font-weight: 800;
  letter-spacing: 0.1em;
}

.actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.action-icon {
  color: #475569;
  font-size: 16px;
  cursor: default;
  user-select: none;
}

:deep(.n-menu-item-group-title) {
  font-size: 10px !important;
  text-transform: uppercase;
  font-weight: 600 !important;
  color: #475569 !important;
  padding-top: 16px !important;
}

:deep(.n-menu-item-content) {
  height: 36px !important;
}
</style>

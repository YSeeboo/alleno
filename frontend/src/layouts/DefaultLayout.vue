<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered :style="{ height: '52px', padding: isMobile ? '0 12px' : '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }">
      <div class="brand">
        <span class="brand-icon" @click="collapsed = !collapsed" style="cursor: pointer;">◈</span>
        <span v-if="!isMobile" class="brand-en">ALLENOP</span>
      </div>
      <div class="header-right">
        <span class="username-text">{{ authStore.user?.owner || authStore.user?.username }}</span>
        <n-button text style="color: #94A3B8; font-size: 13px;" @click="authStore.logout()">退出登录</n-button>
      </div>
    </n-layout-header>
    <n-layout has-sider style="height: calc(100vh - 52px)">
      <div v-if="isMobile && !collapsed" class="sidebar-overlay" @click="collapsed = true" />
      <n-layout-sider
        v-if="!isMobile || !collapsed"
        bordered
        collapse-mode="width"
        :collapsed-width="isMobile ? 0 : 52"
        :width="240"
        :collapsed="collapsed"
        :show-trigger="!isMobile"
        :native-scrollbar="false"
        :style="{
          height: 'calc(100vh - 52px)',
          position: isMobile ? 'fixed' : 'static',
          top: isMobile ? '52px' : undefined,
          left: '0',
          zIndex: isMobile ? 1000 : undefined,
        }"
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
      <n-layout-content :content-style="`padding: ${isMobile ? '12px' : '28px'}; overflow-y: auto;`">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup>
import { ref, computed, h, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutSider, NLayoutContent, NMenu, NButton } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import {
  HomeOutline, ExtensionPuzzleOutline, DiamondOutline, ReceiptOutline,
  CartOutline, ColorWandOutline, HammerOutline, ListOutline, GridOutline, ArchiveOutline,
  PeopleOutline, StorefrontOutline, CopyOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const collapsed = ref(false)
const authStore = useAuthStore()
const { isMobile } = useIsMobile()

watch(isMobile, (mobile) => {
  collapsed.value = mobile
}, { immediate: true })

const icon = (Comp) => () => h(Comp)

const hasPerm = (key) => authStore.hasPermission(key)

const allFlatItems = [
  { label: '进度看板', key: 'kanban', icon: icon(GridOutline), perm: 'kanban' },
  { label: '仪表盘', key: 'dashboard', icon: icon(HomeOutline), perm: 'dashboard' },
  { label: '配件管理', key: 'parts', icon: icon(ExtensionPuzzleOutline), perm: 'parts' },
  { label: '饰品管理', key: 'jewelries', icon: icon(DiamondOutline), perm: 'jewelries' },
  { label: '饰品模板', key: 'jewelry-templates', icon: icon(CopyOutline), perm: 'parts' },
  { label: '订单管理', key: 'orders', icon: icon(ReceiptOutline), perm: 'orders' },
  { label: '配件采购', key: 'purchase-orders', icon: icon(CartOutline), perm: 'purchase_orders' },
  { label: '电镀发出', key: 'plating', icon: icon(ColorWandOutline), perm: 'plating' },
  { label: '电镀回收', key: 'plating-receipts', icon: icon(ColorWandOutline), perm: 'plating' },
  { label: '手工发出', key: 'handcraft', icon: icon(HammerOutline), perm: 'handcraft' },
  { label: '手工回收', key: 'handcraft-receipts', icon: icon(HammerOutline), perm: 'handcraft' },
  { label: '库存总表', key: 'inventory', icon: icon(ArchiveOutline), perm: 'inventory' },
  { label: '库存流水', key: 'inventory-log', icon: icon(ListOutline), perm: 'inventory' },
  { label: '商家管理', key: 'suppliers', icon: icon(StorefrontOutline), perm: 'users' },
  { label: '用户管理', key: 'users', icon: icon(PeopleOutline), perm: 'users' },
]

const filterChildren = (children) => children
  .filter((c) => hasPerm(c.perm))
  .map((c) => c.children ? { ...c, children: c.children.filter((sc) => hasPerm(sc.perm)) } : c)
  .filter((c) => !c.children || c.children.length > 0)

const allGroupedItems = [
  {
    type: 'group', label: '工作台', key: 'group-workbench',
    children: [
      { label: '进度看板', key: 'kanban', icon: icon(GridOutline), perm: 'kanban' },
      { label: '仪表盘', key: 'dashboard', icon: icon(HomeOutline), perm: 'dashboard' },
    ],
  },
  {
    type: 'group', label: '商品', key: 'group-products',
    children: [
      { label: '配件管理', key: 'parts', icon: icon(ExtensionPuzzleOutline), perm: 'parts' },
      { label: '饰品管理', key: 'jewelries', icon: icon(DiamondOutline), perm: 'jewelries' },
      { label: '饰品模板', key: 'jewelry-templates', icon: icon(CopyOutline), perm: 'parts' },
    ],
  },
  {
    type: 'group', label: '生产', key: 'group-production',
    children: [
      { label: '订单管理', key: 'orders', icon: icon(ReceiptOutline), perm: 'orders' },
      { label: '配件采购', key: 'purchase-orders', icon: icon(CartOutline), perm: 'purchase_orders' },
      {
        label: '电镀单', key: 'plating-group', icon: icon(ColorWandOutline), perm: 'plating',
        children: [
          { label: '电镀发出', key: 'plating', perm: 'plating' },
          { label: '电镀回收', key: 'plating-receipts', perm: 'plating' },
        ],
      },
      {
        label: '手工单', key: 'handcraft-group', icon: icon(HammerOutline), perm: 'handcraft',
        children: [
          { label: '手工发出', key: 'handcraft', perm: 'handcraft' },
          { label: '手工回收', key: 'handcraft-receipts', perm: 'handcraft' },
        ],
      },
    ],
  },
  {
    type: 'group', label: '库存', key: 'group-inventory',
    children: [
      { label: '库存总表', key: 'inventory', icon: icon(ArchiveOutline), perm: 'inventory' },
      { label: '库存流水', key: 'inventory-log', icon: icon(ListOutline), perm: 'inventory' },
    ],
  },
  {
    type: 'group', label: '管理', key: 'group-admin',
    children: [
      { label: '商家管理', key: 'suppliers', icon: icon(StorefrontOutline), perm: 'users' },
      { label: '用户管理', key: 'users', icon: icon(PeopleOutline), perm: 'users' },
    ],
  },
]

const flatItems = computed(() => allFlatItems.filter((i) => hasPerm(i.perm)))

const groupedItems = computed(() =>
  allGroupedItems
    .map((g) => ({ ...g, children: filterChildren(g.children) }))
    .filter((g) => g.children.length > 0)
)

const menuOptions = computed(() => collapsed.value ? flatItems.value : groupedItems.value)

const activeKey = computed(() => {
  const seg = route.path.split('/')[1]
  return seg || 'dashboard'
})

const handleSelect = (key) => {
  router.push(key === 'dashboard' ? '/' : `/${key}`)
  if (isMobile.value) {
    collapsed.value = true
  }
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

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.username-text {
  color: #CBD5E1;
  font-size: 13px;
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

.sidebar-overlay {
  position: fixed;
  top: 52px;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 999;
}

</style>

<style>
.n-layout-sider .n-menu-item-content__icon {
  color: rgb(242, 245, 249) !important;
}
.n-layout-sider .n-menu-item-content--selected .n-menu-item-content__icon {
  color: #6366F1 !important;
}
.n-layout-sider .n-menu-item-content:hover .n-menu-item-content__icon {
  color: #FFFFFF !important;
}
</style>

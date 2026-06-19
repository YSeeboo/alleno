<template>
  <n-layout has-sider style="height: 100vh">
    <div v-if="isMobile && !collapsed" class="sidebar-overlay" @click="collapsed = true" />

    <!-- No top header: provide a floating trigger so mobile can open the nav -->
    <button
      v-if="isMobile && collapsed"
      class="mobile-menu-btn"
      aria-label="打开菜单"
      @click="collapsed = false"
    >☰</button>

    <n-layout-sider
      v-if="!isMobile || !collapsed"
      bordered
      collapse-mode="width"
      :collapsed-width="60"
      :width="240"
      :collapsed="collapsed"
      :show-trigger="!isMobile"
      content-style="display: flex; flex-direction: column; height: 100%;"
      v-bind="isMobile ? { collapsedWidth: 0, nativeScrollbar: false, style: { height: '100vh', position: 'fixed', top: '0', left: '0', zIndex: 1000 } } : {}"
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <!-- brand (top) -->
      <div class="side-brand" :class="{ collapsed }">
        <span class="brand-icon" @click="collapsed = !collapsed">◈</span>
        <span v-if="!collapsed" class="brand-en">ALLENOP</span>
      </div>

      <!-- nav (scrolls) -->
      <div class="side-menu">
        <n-menu
          :collapsed="collapsed"
          :collapsed-width="60"
          :collapsed-icon-size="22"
          :options="menuOptions"
          :value="activeKey"
          @update:value="handleSelect"
        />
      </div>

      <!-- user (bottom-left) -->
      <div class="side-user" :class="{ collapsed }">
        <div class="side-user-av">{{ userInitial }}</div>
        <div v-if="!collapsed" class="side-user-meta">
          <div class="side-user-name">{{ username }}</div>
          <button class="side-user-logout" @click="authStore.logout()">退出登录</button>
        </div>
      </div>
    </n-layout-sider>

    <n-layout-content :content-style="`padding: ${isMobile ? '16px' : '28px'}; overflow-y: auto;`">
      <router-view />
    </n-layout-content>
  </n-layout>
</template>

<script setup>
import { ref, computed, h, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutSider, NLayoutContent, NMenu } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import {
  HomeOutline, ExtensionPuzzleOutline, DiamondOutline,
  CartOutline, GridOutline, ArchiveOutline,
  PeopleOutline, StorefrontOutline,
  PaperPlaneOutline, DownloadOutline,
} from '@vicons/ionicons5'
import PlatingIcon from '@/components/icons/PlatingIcon.vue'
import HandcraftIcon from '@/components/icons/HandcraftIcon.vue'
import SortingIcon from '@/components/icons/SortingIcon.vue'
import JewelryTemplateIcon from '@/components/icons/JewelryTemplateIcon.vue'
import OrderIcon from '@/components/icons/OrderIcon.vue'
import PlatingSummaryIcon from '@/components/icons/PlatingSummaryIcon.vue'
import InventoryLogIcon from '@/components/icons/InventoryLogIcon.vue'
import RestockIcon from '@/components/icons/RestockIcon.vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const collapsed = ref(false)
const authStore = useAuthStore()
const { isMobile } = useIsMobile()

watch(isMobile, (mobile) => {
  collapsed.value = mobile
}, { immediate: true })

const username = computed(() => authStore.user?.owner || authStore.user?.username || '')
const userInitial = computed(() => (username.value || '?').trim().charAt(0).toUpperCase())

const icon = (Comp) => () => h(Comp)

const hasPerm = (key) => authStore.hasPermission(key)

const allFlatItems = [
  { label: '进度看板', key: 'kanban', icon: icon(GridOutline), perm: 'kanban' },
  { label: '仪表盘', key: 'dashboard', icon: icon(HomeOutline), perm: 'dashboard' },
  { label: '配件管理', key: 'parts', icon: icon(ExtensionPuzzleOutline), perm: 'parts' },
  { label: '饰品管理', key: 'jewelries', icon: icon(DiamondOutline), perm: 'jewelries' },
  { label: '饰品模板', key: 'jewelry-templates', icon: icon(JewelryTemplateIcon), perm: 'parts' },
  { label: '订单管理', key: 'orders', icon: icon(OrderIcon), perm: 'orders' },
  { label: '配件采购', key: 'purchase-orders', icon: icon(CartOutline), perm: 'purchase_orders' },
  { label: '待补货清单', key: 'restock', icon: icon(RestockIcon), perm: ['handcraft', 'restock'] },
  { label: '电镀汇总', key: 'plating-summary', icon: icon(PlatingSummaryIcon), perm: 'plating' },
  { label: '电镀发出', key: 'plating', icon: icon(PaperPlaneOutline), perm: 'plating' },
  { label: '电镀回收', key: 'plating-receipts', icon: icon(DownloadOutline), perm: 'plating' },
  { label: '手工发出', key: 'handcraft', icon: icon(PaperPlaneOutline), perm: 'handcraft' },
  { label: '手工回收', key: 'handcraft-receipts', icon: icon(DownloadOutline), perm: 'handcraft' },
  { label: '货物分拣', key: 'cargo-sorting', icon: icon(SortingIcon), perm: 'sorting' },
  { label: '库存总表', key: 'inventory', icon: icon(ArchiveOutline), perm: 'inventory' },
  { label: '库存流水', key: 'inventory-log', icon: icon(InventoryLogIcon), perm: 'inventory' },
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
      { label: '饰品模板', key: 'jewelry-templates', icon: icon(JewelryTemplateIcon), perm: 'parts' },
    ],
  },
  {
    type: 'group', label: '生产', key: 'group-production',
    children: [
      { label: '订单管理', key: 'orders', icon: icon(OrderIcon), perm: 'orders' },
      { label: '配件采购', key: 'purchase-orders', icon: icon(CartOutline), perm: 'purchase_orders' },
      { label: '待补货清单', key: 'restock', icon: icon(RestockIcon), perm: ['handcraft', 'restock'] },
      {
        label: '电镀', key: 'plating-group', icon: icon(PlatingIcon), perm: 'plating',
        children: [
          { label: '电镀汇总', key: 'plating-summary', icon: icon(PlatingSummaryIcon), perm: 'plating' },
          { label: '电镀发出', key: 'plating', icon: icon(PaperPlaneOutline), perm: 'plating' },
          { label: '电镀回收', key: 'plating-receipts', icon: icon(DownloadOutline), perm: 'plating' },
        ],
      },
      {
        label: '手工单', key: 'handcraft-group', icon: icon(HandcraftIcon), perm: 'handcraft',
        children: [
          { label: '手工发出', key: 'handcraft', icon: icon(PaperPlaneOutline), perm: 'handcraft' },
          { label: '手工回收', key: 'handcraft-receipts', icon: icon(DownloadOutline), perm: 'handcraft' },
        ],
      },
      { label: '货物分拣', key: 'cargo-sorting', icon: icon(SortingIcon), perm: 'sorting' },
    ],
  },
  {
    type: 'group', label: '库存', key: 'group-inventory',
    children: [
      { label: '库存总表', key: 'inventory', icon: icon(ArchiveOutline), perm: 'inventory' },
      { label: '库存流水', key: 'inventory-log', icon: icon(InventoryLogIcon), perm: 'inventory' },
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
.side-brand {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 56px;
  padding: 0 18px;
  flex: none;
}
.side-brand.collapsed {
  justify-content: center;
  padding: 0;
}
.brand-icon {
  color: #3FBF8F;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}
.brand-en {
  color: #FFFFFF;
  font-size: 15px;
  font-weight: 800;
  letter-spacing: 0.12em;
  white-space: nowrap;
}

.side-menu {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.side-user {
  flex: none;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 16px;
  border-top: 1px solid #20262E;
}
.side-user.collapsed {
  justify-content: center;
  padding: 12px 0;
}
.side-user-av {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2AA177, #155C43);
  color: #FFFFFF;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex: none;
}
.side-user-meta {
  min-width: 0;
}
.side-user-name {
  color: #E7EAEE;
  font-size: 13px;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.side-user-logout {
  background: none;
  border: none;
  padding: 0;
  margin-top: 2px;
  color: #7E858E;
  font-size: 11.5px;
  cursor: pointer;
}
.side-user-logout:hover {
  color: #3FBF8F;
}

.mobile-menu-btn {
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 1001;
  width: 38px;
  height: 38px;
  border-radius: 9px;
  background: #10141A;
  color: #FFFFFF;
  border: none;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

:deep(.n-menu-item-group-title) {
  font-size: 10px !important;
  text-transform: uppercase;
  font-weight: 600 !important;
  color: #5B6470 !important;
  padding-top: 16px !important;
}

:deep(.n-menu-item-content) {
  height: 36px !important;
}

.sidebar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 999;
}
</style>

<style>
/* Menu items as inset rounded pills (closer to the mockup's nav) */
.n-layout-sider .n-menu .n-menu-item-content {
  margin: 2px 10px;
  border-radius: 8px;
}
.n-layout-sider .n-menu-item-content__icon {
  color: #AEB4BC !important;
  margin-right: 10px !important;
}
.n-layout-sider .n-menu-item-content--selected .n-menu-item-content__icon {
  color: #3FBF8F !important;
}
.n-layout-sider .n-menu-item-content:hover .n-menu-item-content__icon {
  color: #FFFFFF !important;
}
/* Collapsed: icon-only items stay centered, no inset margin */
.n-layout-sider.n-layout-sider--collapsed .n-menu .n-menu-item-content {
  margin: 2px 6px;
}
</style>

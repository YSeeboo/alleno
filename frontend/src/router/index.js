import { createRouter, createWebHistory } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

const ROUTE_PERMISSION_MAP = {
  kanban: 'kanban',
  dashboard: 'dashboard',
  parts: 'parts',
  jewelries: 'jewelries',
  orders: 'orders',
  'purchase-orders': 'purchase_orders',
  plating: 'plating',
  'plating-receipts': 'plating',
  handcraft: 'handcraft',
  'handcraft-receipts': 'handcraft',
  inventory: 'inventory',
  'inventory-log': 'inventory',
  users: 'users',
}

const PERMISSION_ROUTE_ORDER = [
  'kanban', 'dashboard', 'parts', 'jewelries', 'orders',
  'purchase-orders', 'plating', 'handcraft', 'inventory', 'inventory-log', 'users',
]

export function getFirstPermittedRoute(authStore) {
  for (const routeKey of PERMISSION_ROUTE_ORDER) {
    const perm = ROUTE_PERMISSION_MAP[routeKey]
    if (authStore.hasPermission(perm)) {
      return routeKey === 'dashboard' ? '/' : `/${routeKey}`
    }
  }
  return null
}

// Wrap dynamic import to auto-reload on chunk load failure (stale deployment cache)
function lazyLoad(importFn) {
  return () => importFn().catch((err) => {
    const msg = err.message || ''
    if (msg.includes('dynamically imported module') || msg.includes('Failed to fetch')) {
      const key = 'chunk_reload_' + window.location.pathname
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, '1')
        window.location.reload()
        return
      }
    }
    throw err
  })
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: lazyLoad(() => import('@/views/login/LoginPage.vue')),
    },
    {
      path: '/',
      component: DefaultLayout,
      children: [
        { path: '', name: 'Dashboard', component: lazyLoad(() => import('@/views/Dashboard.vue')), meta: { perm: 'dashboard' } },
        { path: 'parts', component: lazyLoad(() => import('@/views/parts/PartList.vue')), meta: { perm: 'parts' } },
        { path: 'parts/:id', component: lazyLoad(() => import('@/views/parts/PartDetail.vue')), meta: { perm: 'parts' } },
        { path: 'jewelries', component: lazyLoad(() => import('@/views/jewelries/JewelryList.vue')), meta: { perm: 'jewelries' } },
        { path: 'jewelries/:id', component: lazyLoad(() => import('@/views/jewelries/JewelryDetail.vue')), meta: { perm: 'jewelries' } },
        { path: 'jewelry-templates', component: lazyLoad(() => import('@/views/jewelry-templates/JewelryTemplateList.vue')), meta: { perm: 'parts' } },
        { path: 'jewelry-templates/create', component: lazyLoad(() => import('@/views/jewelry-templates/JewelryTemplateCreate.vue')), meta: { perm: 'parts' } },
        { path: 'jewelry-templates/:id', component: lazyLoad(() => import('@/views/jewelry-templates/JewelryTemplateDetail.vue')), meta: { perm: 'parts' } },
        { path: 'orders', component: lazyLoad(() => import('@/views/orders/OrderList.vue')), meta: { perm: 'orders' } },
        { path: 'orders/create', component: lazyLoad(() => import('@/views/orders/OrderCreate.vue')), meta: { perm: 'orders' } },
        { path: 'orders/:id', component: lazyLoad(() => import('@/views/orders/OrderDetail.vue')), meta: { perm: 'orders' } },
        { path: 'purchase-orders', component: lazyLoad(() => import('@/views/purchase-orders/PurchaseOrderList.vue')), meta: { perm: 'purchase_orders' } },
        { path: 'purchase-orders/create', component: lazyLoad(() => import('@/views/purchase-orders/PurchaseOrderCreate.vue')), meta: { perm: 'purchase_orders' } },
        { path: 'purchase-orders/:id', component: lazyLoad(() => import('@/views/purchase-orders/PurchaseOrderDetail.vue')), meta: { perm: 'purchase_orders' } },
        { path: 'plating', component: lazyLoad(() => import('@/views/plating/PlatingList.vue')), meta: { perm: 'plating' } },
        { path: 'plating/create', component: lazyLoad(() => import('@/views/plating/PlatingCreate.vue')), meta: { perm: 'plating' } },
        { path: 'plating/:id', component: lazyLoad(() => import('@/views/plating/PlatingDetail.vue')), meta: { perm: 'plating' } },
        { path: 'plating-receipts', component: lazyLoad(() => import('@/views/plating-receipts/PlatingReceiptList.vue')), meta: { perm: 'plating' } },
        { path: 'plating-receipts/create', component: lazyLoad(() => import('@/views/plating-receipts/PlatingReceiptCreate.vue')), meta: { perm: 'plating' } },
        { path: 'plating-receipts/:id', component: lazyLoad(() => import('@/views/plating-receipts/PlatingReceiptDetail.vue')), meta: { perm: 'plating' } },
        { path: 'handcraft-receipts', component: lazyLoad(() => import('@/views/handcraft-receipts/HandcraftReceiptList.vue')), meta: { perm: 'handcraft' } },
        { path: 'handcraft-receipts/create', component: lazyLoad(() => import('@/views/handcraft-receipts/HandcraftReceiptCreate.vue')), meta: { perm: 'handcraft' } },
        { path: 'handcraft-receipts/:id', component: lazyLoad(() => import('@/views/handcraft-receipts/HandcraftReceiptDetail.vue')), meta: { perm: 'handcraft' } },
        { path: 'handcraft', component: lazyLoad(() => import('@/views/handcraft/HandcraftList.vue')), meta: { perm: 'handcraft' } },
        { path: 'handcraft/create', component: lazyLoad(() => import('@/views/handcraft/HandcraftCreate.vue')), meta: { perm: 'handcraft' } },
        { path: 'handcraft/:id', component: lazyLoad(() => import('@/views/handcraft/HandcraftDetail.vue')), meta: { perm: 'handcraft' } },
        { path: 'inventory', component: lazyLoad(() => import('@/views/InventoryOverview.vue')), meta: { perm: 'inventory' } },
        { path: 'inventory-log', component: lazyLoad(() => import('@/views/InventoryLog.vue')), meta: { perm: 'inventory' } },
        { path: 'kanban', component: lazyLoad(() => import('@/views/kanban/KanbanBoard.vue')), meta: { perm: 'kanban' } },
        { path: 'suppliers', component: lazyLoad(() => import('@/views/suppliers/SupplierList.vue')), meta: { perm: 'users' } },
        { path: 'users', component: lazyLoad(() => import('@/views/users/UserList.vue')), meta: { perm: 'users' } },
      ],
    },
  ],
})

let userFetched = false

router.beforeEach(async (to) => {
  const { useAuthStore } = await import('@/stores/auth')
  const authStore = useAuthStore()

  if (to.path === '/login') {
    if (!authStore.isLoggedIn) return true
    if (!authStore.user) {
      await authStore.fetchUser()
      userFetched = true
      if (!authStore.isLoggedIn) return true
    }
    const target = getFirstPermittedRoute(authStore)
    if (!target) {
      authStore.logout()
      return true // stay on /login
    }
    return target
  }

  if (!authStore.isLoggedIn) {
    return '/login'
  }

  if (!userFetched) {
    await authStore.fetchUser()
    userFetched = true
    if (!authStore.isLoggedIn) return '/login'
  }

  const perm = to.meta.perm
  if (perm && !authStore.hasPermission(perm)) {
    const target = getFirstPermittedRoute(authStore)
    if (!target) {
      authStore.logout()
      return '/login'
    }
    return target
  }

  return true
})

export default router

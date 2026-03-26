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

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/login/LoginPage.vue'),
    },
    {
      path: '/',
      component: DefaultLayout,
      children: [
        { path: '', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'), meta: { perm: 'dashboard' } },
        { path: 'parts', component: () => import('@/views/parts/PartList.vue'), meta: { perm: 'parts' } },
        { path: 'parts/:id', component: () => import('@/views/parts/PartDetail.vue'), meta: { perm: 'parts' } },
        { path: 'jewelries', component: () => import('@/views/jewelries/JewelryList.vue'), meta: { perm: 'jewelries' } },
        { path: 'jewelries/:id', component: () => import('@/views/jewelries/JewelryDetail.vue'), meta: { perm: 'jewelries' } },
        { path: 'orders', component: () => import('@/views/orders/OrderList.vue'), meta: { perm: 'orders' } },
        { path: 'orders/create', component: () => import('@/views/orders/OrderCreate.vue'), meta: { perm: 'orders' } },
        { path: 'orders/:id', component: () => import('@/views/orders/OrderDetail.vue'), meta: { perm: 'orders' } },
        { path: 'purchase-orders', component: () => import('@/views/purchase-orders/PurchaseOrderList.vue'), meta: { perm: 'purchase_orders' } },
        { path: 'purchase-orders/create', component: () => import('@/views/purchase-orders/PurchaseOrderCreate.vue'), meta: { perm: 'purchase_orders' } },
        { path: 'purchase-orders/:id', component: () => import('@/views/purchase-orders/PurchaseOrderDetail.vue'), meta: { perm: 'purchase_orders' } },
        { path: 'plating', component: () => import('@/views/plating/PlatingList.vue'), meta: { perm: 'plating' } },
        { path: 'plating/create', component: () => import('@/views/plating/PlatingCreate.vue'), meta: { perm: 'plating' } },
        { path: 'plating/:id', component: () => import('@/views/plating/PlatingDetail.vue'), meta: { perm: 'plating' } },
        { path: 'plating-receipts', component: () => import('@/views/plating-receipts/PlatingReceiptList.vue'), meta: { perm: 'plating' } },
        { path: 'plating-receipts/create', component: () => import('@/views/plating-receipts/PlatingReceiptCreate.vue'), meta: { perm: 'plating' } },
        { path: 'plating-receipts/:id', component: () => import('@/views/plating-receipts/PlatingReceiptDetail.vue'), meta: { perm: 'plating' } },
        { path: 'handcraft-receipts', component: () => import('@/views/handcraft-receipts/HandcraftReceiptList.vue'), meta: { perm: 'handcraft' } },
        { path: 'handcraft-receipts/create', component: () => import('@/views/handcraft-receipts/HandcraftReceiptCreate.vue'), meta: { perm: 'handcraft' } },
        { path: 'handcraft-receipts/:id', component: () => import('@/views/handcraft-receipts/HandcraftReceiptDetail.vue'), meta: { perm: 'handcraft' } },
        { path: 'handcraft', component: () => import('@/views/handcraft/HandcraftList.vue'), meta: { perm: 'handcraft' } },
        { path: 'handcraft/create', component: () => import('@/views/handcraft/HandcraftCreate.vue'), meta: { perm: 'handcraft' } },
        { path: 'handcraft/:id', component: () => import('@/views/handcraft/HandcraftDetail.vue'), meta: { perm: 'handcraft' } },
        { path: 'inventory', component: () => import('@/views/InventoryOverview.vue'), meta: { perm: 'inventory' } },
        { path: 'inventory-log', component: () => import('@/views/InventoryLog.vue'), meta: { perm: 'inventory' } },
        { path: 'kanban', component: () => import('@/views/kanban/KanbanBoard.vue'), meta: { perm: 'kanban' } },
        { path: 'suppliers', component: () => import('@/views/suppliers/SupplierList.vue'), meta: { perm: 'users' } },
        { path: 'users', component: () => import('@/views/users/UserList.vue'), meta: { perm: 'users' } },
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

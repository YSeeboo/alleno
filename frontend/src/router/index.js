import { createRouter, createWebHistory } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import { rememberPlatingLocation, restorePlatingListQuery } from '@/utils/platingNavigation'
import { createPlatingRoutes } from './plating'
import { rememberHandcraftLocation, restoreHandcraftListQuery } from '@/utils/handcraftNavigation'
import { createHandcraftRoutes } from './handcraft'

const ROUTE_PERMISSION_MAP = {
  kanban: 'kanban',
  dashboard: 'dashboard',
  parts: 'parts',
  jewelries: 'jewelries',
  'jewelry-structures': 'parts',
  orders: 'orders',
  'purchase-orders': 'purchase_orders',
  plating: 'plating',
  'plating-receipts': 'plating',
  'plating-summary': 'plating',
  'plating-management': 'plating',
  handcraft: 'handcraft',
  'handcraft-receipts': 'handcraft',
  'handcraft-management': 'handcraft',
  'cargo-sorting': 'sorting',
  restock: 'handcraft',
  inventory: 'inventory',
  'inventory-log': 'inventory',
  users: 'users',
}

const PERMISSION_ROUTE_ORDER = [
  'kanban', 'dashboard', 'parts', 'jewelries', 'orders',
  'purchase-orders', 'plating-management', 'handcraft-management', 'restock', 'cargo-sorting',
  'inventory', 'inventory-log', 'users',
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
        { path: 'jewelry-structures', component: lazyLoad(() => import('@/views/jewelries/JewelryStructureWorkbench.vue')), meta: { perm: 'parts' } },
        { path: 'orders', component: lazyLoad(() => import('@/views/orders/OrderList.vue')), meta: { perm: 'orders' } },
        { path: 'orders/create', component: lazyLoad(() => import('@/views/orders/OrderCreate.vue')), meta: { perm: 'orders' } },
        { path: 'orders/:id', component: lazyLoad(() => import('@/views/orders/OrderDetail.vue')), meta: { perm: 'orders' } },
        { path: 'orders/:id/production', component: lazyLoad(() => import('@/views/orders/OrderProduction.vue')), meta: { perm: 'orders' } },
        { path: 'orders/:id/information', component: lazyLoad(() => import('@/views/orders/OrderInfo.vue')), meta: { perm: 'orders' } },
        { path: 'orders/:id/records', redirect: to => ({ path: `/orders/${to.params.id}`, query: to.query, hash: to.hash }), meta: { perm: 'orders' } },
        { path: 'stock-readiness', component: lazyLoad(() => import('@/views/fulfillment/StockReadiness.vue')), meta: { perm: 'orders' } },
        { path: 'shipments', component: lazyLoad(() => import('@/views/fulfillment/ShipmentList.vue')), meta: { perm: 'orders' } },
        { path: 'shipments/create', component: lazyLoad(() => import('@/views/fulfillment/ShipmentCreate.vue')), meta: { perm: 'orders' } },
        { path: 'shipments/:id', component: lazyLoad(() => import('@/views/fulfillment/ShipmentDetail.vue')), meta: { perm: 'orders' } },
        { path: 'purchase-orders', component: lazyLoad(() => import('@/views/purchase-orders/PurchaseOrderList.vue')), meta: { perm: 'purchase_orders' } },
        { path: 'purchase-orders/create', component: lazyLoad(() => import('@/views/purchase-orders/PurchaseOrderCreate.vue')), meta: { perm: 'purchase_orders' } },
        { path: 'purchase-orders/:id', component: lazyLoad(() => import('@/views/purchase-orders/PurchaseOrderDetail.vue')), meta: { perm: 'purchase_orders' } },
        ...createPlatingRoutes(lazyLoad),
        ...createHandcraftRoutes(lazyLoad),
        { path: 'cargo-sorting', component: lazyLoad(() => import('@/views/cargo-sorting/CargoSorting.vue')), meta: { perm: 'sorting' } },
        { path: 'restock', component: lazyLoad(() => import('@/views/restock/RestockList.vue')), meta: { perm: ['handcraft', 'restock'] } },
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

router.beforeEach(async (to, from) => {
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

  return restorePlatingListQuery(to, from) || restoreHandcraftListQuery(to, from) || true
})

router.afterEach((to, from, failure) => {
  if (!failure) {
    rememberPlatingLocation(to)
    rememberHandcraftLocation(to)
  }
})

export default router

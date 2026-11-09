import { getPlatingLocation } from '../utils/platingNavigation.js'

// Keep existing list/detail URLs while sharing a shell only between list pages.
export function createPlatingRoutes(loadComponent, homeLocation = getPlatingLocation) {
  return [
    {
      path: 'plating-management',
      component: loadComponent(() => import('@/views/plating/PlatingManagement.vue')),
      meta: { perm: 'plating' },
      children: [
        { path: '', redirect: () => homeLocation() },
        { path: '/plating-summary', component: loadComponent(() => import('@/views/plating/PlatingSummary.vue')), props: { embedded: true } },
        { path: '/plating', component: loadComponent(() => import('@/views/plating/PlatingList.vue')), props: { embedded: true } },
        { path: '/plating-receipts', component: loadComponent(() => import('@/views/plating-receipts/PlatingReceiptList.vue')), props: { embedded: true } },
        { path: '/plating-reconciliation', component: loadComponent(() => import('@/views/plating/PlatingReconciliation.vue')), props: { embedded: true } },
      ],
    },
    { path: 'plating/create', component: loadComponent(() => import('@/views/plating/PlatingCreate.vue')), meta: { perm: 'plating' } },
    { path: 'plating/:id', component: loadComponent(() => import('@/views/plating/PlatingDetail.vue')), meta: { perm: 'plating' } },
    { path: 'plating-receipts/create', component: loadComponent(() => import('@/views/plating-receipts/PlatingReceiptCreate.vue')), meta: { perm: 'plating' } },
    { path: 'plating-receipts/:id', component: loadComponent(() => import('@/views/plating-receipts/PlatingReceiptDetail.vue')), meta: { perm: 'plating' } },
  ]
}

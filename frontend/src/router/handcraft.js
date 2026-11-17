import { getHandcraftLocation } from '../utils/handcraftNavigation.js'

// Existing URLs stay valid. Only the lists share the management shell.
export function createHandcraftRoutes(loadComponent, homeLocation = getHandcraftLocation) {
  return [
    {
      path: 'handcraft-management',
      component: loadComponent(() => import('@/views/handcraft/HandcraftManagement.vue')),
      meta: { perm: 'handcraft' },
      children: [
        { path: '', redirect: () => homeLocation() },
        { path: '/handcraft-summary', component: loadComponent(() => import('@/views/handcraft/HandcraftSummary.vue')), props: { embedded: true } },
        { path: '/handcraft', component: loadComponent(() => import('@/views/handcraft/HandcraftList.vue')), props: { embedded: true } },
        { path: '/handcraft-receipts', component: loadComponent(() => import('@/views/handcraft-receipts/HandcraftReceiptList.vue')), props: { embedded: true } },
      ],
    },
    { path: 'handcraft/create', component: loadComponent(() => import('@/views/handcraft/HandcraftCreate.vue')), meta: { perm: 'handcraft' } },
    { path: 'handcraft/:id', component: loadComponent(() => import('@/views/handcraft/HandcraftDetail.vue')), meta: { perm: 'handcraft' } },
    { path: 'handcraft-receipts/create', component: loadComponent(() => import('@/views/handcraft-receipts/HandcraftReceiptCreate.vue')), meta: { perm: 'handcraft' } },
    { path: 'handcraft-receipts/:id', component: loadComponent(() => import('@/views/handcraft-receipts/HandcraftReceiptDetail.vue')), meta: { perm: 'handcraft' } },
  ]
}

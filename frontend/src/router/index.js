import { createRouter, createWebHistory } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: DefaultLayout,
      children: [
        { path: '', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
        { path: 'parts', component: () => import('@/views/parts/PartList.vue') },
        { path: 'parts/:id', component: () => import('@/views/parts/PartDetail.vue') },
        { path: 'jewelries', component: () => import('@/views/jewelries/JewelryList.vue') },
        { path: 'jewelries/:id', component: () => import('@/views/jewelries/JewelryDetail.vue') },
        { path: 'orders', component: () => import('@/views/orders/OrderList.vue') },
        { path: 'orders/create', component: () => import('@/views/orders/OrderCreate.vue') },
        { path: 'orders/:id', component: () => import('@/views/orders/OrderDetail.vue') },
        { path: 'plating', component: () => import('@/views/plating/PlatingList.vue') },
        { path: 'plating/create', component: () => import('@/views/plating/PlatingCreate.vue') },
        { path: 'plating/:id', component: () => import('@/views/plating/PlatingDetail.vue') },
        { path: 'handcraft', component: () => import('@/views/handcraft/HandcraftList.vue') },
        { path: 'handcraft/create', component: () => import('@/views/handcraft/HandcraftCreate.vue') },
        { path: 'handcraft/:id', component: () => import('@/views/handcraft/HandcraftDetail.vue') },
        { path: 'inventory-log', component: () => import('@/views/InventoryLog.vue') },
      ],
    },
  ],
})

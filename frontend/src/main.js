import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/global.css'
import './styles/responsive.css'

// Favicon per environment: default red (正式服); test server sets
// VITE_FAVICON=white in its .env.production to flag 测试服 at a glance.
if (import.meta.env.VITE_FAVICON === 'white') {
  const link = document.querySelector("link[rel='icon']")
  if (link) link.href = '/favicon-white.png'
}

createApp(App).use(createPinia()).use(router).mount('#app')

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/global.css'
import './styles/responsive.css'

// Favicon per environment (auto, no server config needed): the production
// build points VITE_API_BASE_URL at the prod API host; any other remote host
// is treated as 测试服 and gets the white favicon. localhost = local dev = red.
;(() => {
  const api = import.meta.env.VITE_API_BASE_URL || ''
  const isProd = api.includes('api.ycbhomeland.top')
  const isLocal = api.includes('localhost') || api.includes('127.0.0.1')
  if (!isProd && !isLocal) {
    const link = document.querySelector("link[rel='icon']")
    if (link) link.href = '/favicon-white.png'
  }
})()

createApp(App).use(createPinia()).use(router).mount('#app')

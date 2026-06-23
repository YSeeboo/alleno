import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/global.css'
import './styles/responsive.css'

// Favicon by environment: local development (`npm run dev`) shows the white
// AL so it's obvious you're not on the live site; production build stays red.
if (import.meta.env.DEV) {
  const link = document.querySelector("link[rel='icon']")
  if (link) link.href = '/favicon-white.png'
}

createApp(App).use(createPinia()).use(router).mount('#app')

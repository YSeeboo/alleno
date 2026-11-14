import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  server: {
    // Optional same-origin API for isolated local previews; production is unchanged.
    proxy: process.env.API_PROXY_TARGET ? {
      '/api': { target: process.env.API_PROXY_TARGET, changeOrigin: true },
    } : undefined,
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})

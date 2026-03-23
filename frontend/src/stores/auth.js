import { defineStore } from 'pinia'
import { login as loginApi, getMe } from '@/api/auth'
import router from '@/router'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: null,
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
    hasPermission: (state) => (key) => {
      if (!state.user) return false
      if (state.user.is_admin) return true
      const perms = new Set(state.user.permissions || [])
      // legacy: inventory_log was merged into inventory
      if (perms.has('inventory_log')) perms.add('inventory')
      return perms.has(key)
    },
  },

  actions: {
    async login(username, password) {
      const { data } = await loginApi({ username, password })
      this.token = data.token
      this.user = data.user
      localStorage.setItem('token', data.token)
    },

    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
      router.push('/login')
    },

    async fetchUser() {
      try {
        const { data } = await getMe()
        this.user = data
      } catch {
        this.logout()
      }
    },
  },
})

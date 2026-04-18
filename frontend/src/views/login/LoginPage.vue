<template>
  <div class="login-wrapper">
    <div class="login-card">
      <div class="login-brand">
        <span class="brand-icon">◈</span>
        <span class="brand-en">ALLENOP</span>
      </div>
      <form @submit.prevent="handleLogin">
        <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
          <n-form-item label="账号" path="username">
            <n-input v-model:value="form.username" placeholder="请输入账号" />
          </n-form-item>
          <n-form-item label="密码" path="password">
            <n-input v-model:value="form.password" type="password" show-password-on="click" placeholder="请输入密码" />
          </n-form-item>
          <n-button type="primary" block :loading="loading" @click="handleLogin" style="margin-top: 8px;">
            登录
          </n-button>
        </n-form>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NForm, NFormItem, NInput, NButton, useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { getFirstPermittedRoute } from '@/router'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()
const formRef = ref(null)
const loading = ref(false)

const form = ref({ username: '', password: '' })
const rules = {
  username: { required: true, message: '请输入账号', trigger: 'blur' },
  password: { required: true, message: '请输入密码', trigger: 'blur' },
}

const handleLogin = async () => {
  try {
    await formRef.value?.validate()
  } catch { return }

  loading.value = true
  try {
    await authStore.login(form.value.username, form.value.password)
    const target = getFirstPermittedRoute(authStore)
    if (!target) {
      authStore.logout()
      message.error('该账号没有任何模块权限，请联系管理员')
      return
    }
    router.push(target)
  } catch (err) {
    if (err.response?.status === 401) {
      message.error('账号/密码错误')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrapper {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0F172A;
}

.login-card {
  width: 360px;
  max-width: 90vw;
  padding: 40px 32px;
  background: #1E293B;
  border-radius: 12px;
  border: 1px solid #334155;
}

.login-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 32px;
}

.login-brand .brand-icon {
  color: #6366F1;
  font-size: 24px;
  line-height: 1;
}

.login-brand .brand-en {
  color: #F1F5F9;
  font-size: 20px;
  font-weight: 800;
  letter-spacing: 0.1em;
}
</style>

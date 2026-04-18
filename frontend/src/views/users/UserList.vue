<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">管理 / 用户管理</div>
      <h2 class="page-title">用户管理</h2>
      <div class="page-divider"></div>
    </div>
    <div class="filter-bar">
      <div></div>
      <div class="filter-bar-end">
        <n-button type="primary" @click="openCreate">新建用户</n-button>
      </div>
    </div>
    <n-spin :show="loading">
      <n-data-table v-if="users.length > 0" :columns="columns" :data="users" :bordered="false" />
      <n-empty v-else-if="!loading" description="暂无用户" style="margin-top: 24px;" />
    </n-spin>

    <n-modal v-model:show="showModal" preset="card" :title="editingUser ? '修改用户' : '新建用户'" :style="{ width: isMobile ? '95vw' : '480px' }">
      <form @submit.prevent="handleSave">
      <n-form ref="modalFormRef" :model="modalForm" :rules="modalRules" label-placement="top">
        <n-form-item label="账号" path="username">
          <n-input v-model:value="modalForm.username" :disabled="!!editingUser" placeholder="请输入账号" />
        </n-form-item>
        <n-form-item label="密码" path="password">
          <n-input v-model:value="modalForm.password" type="password" show-password-on="click" :placeholder="editingUser ? '留空则不修改' : '请输入密码'" />
        </n-form-item>
        <n-form-item label="持有者" path="owner">
          <n-input v-model:value="modalForm.owner" placeholder="请输入持有者" />
        </n-form-item>
        <n-form-item v-if="!editingUser?.is_admin" label="权限" path="permissions">
          <n-checkbox-group v-model:value="modalForm.permissions">
            <n-space item-style="display: flex;">
              <n-checkbox v-for="p in permissionOptions" :key="p.value" :value="p.value" :label="p.label" />
            </n-space>
          </n-checkbox-group>
        </n-form-item>
      </n-form>
      </form>
      <template #action>
        <n-space justify="end">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleSave">确定</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import {
  NButton, NDataTable, NSpin, NEmpty, NModal, NForm, NFormItem, NInput,
  NCheckboxGroup, NCheckbox, NSpace, NTag, NPopconfirm, useMessage,
} from 'naive-ui'
import { listUsers, createUser, updateUser, deleteUser } from '@/api/users'
import { useIsMobile } from '@/composables/useIsMobile'

const message = useMessage()
const { isMobile } = useIsMobile()
const loading = ref(true)
const users = ref([])
const showModal = ref(false)
const editingUser = ref(null)
const saving = ref(false)
const modalFormRef = ref(null)

const permissionOptions = [
  { value: 'kanban', label: '进度看板' },
  { value: 'dashboard', label: '仪表盘' },
  { value: 'parts', label: '配件管理' },
  { value: 'jewelries', label: '饰品管理' },
  { value: 'orders', label: '订单管理' },
  { value: 'purchase_orders', label: '配件采购' },
  { value: 'plating', label: '电镀单' },
  { value: 'handcraft', label: '手工单' },
  { value: 'inventory', label: '库存' },
  { value: 'users', label: '用户管理' },
]

const permLabelMap = Object.fromEntries(permissionOptions.map((p) => [p.value, p.label]))

const defaultForm = () => ({ username: '', password: '', owner: '', permissions: [] })
const modalForm = ref(defaultForm())

const modalRules = {
  username: { required: true, message: '请输入账号', trigger: 'blur' },
  password: {
    required: true,
    validator: (rule, value) => {
      if (!editingUser.value && !value) return new Error('请输入密码')
      return true
    },
    trigger: 'blur',
  },
  owner: { required: true, message: '请输入持有者', trigger: 'blur' },
  permissions: {
    validator: (rule, value) => {
      if (editingUser.value?.is_admin) return true
      if (!value || value.length === 0) return new Error('请至少选择一个权限')
      return true
    },
    trigger: 'change',
  },
}

const load = async () => {
  loading.value = true
  try {
    const { data } = await listUsers()
    users.value = data
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingUser.value = null
  modalForm.value = defaultForm()
  showModal.value = true
}

const openEdit = (user) => {
  editingUser.value = user
  modalForm.value = {
    username: user.username,
    password: '',
    owner: user.owner,
    permissions: [...(user.permissions || [])],
  }
  showModal.value = true
}

const handleSave = async () => {
  try {
    await modalFormRef.value?.validate()
  } catch { return }

  saving.value = true
  try {
    if (editingUser.value) {
      const payload = { owner: modalForm.value.owner, permissions: modalForm.value.permissions }
      if (modalForm.value.password) payload.password = modalForm.value.password
      await updateUser(editingUser.value.id, payload)
      message.success('修改成功')
    } else {
      await createUser(modalForm.value)
      message.success('创建成功')
    }
    showModal.value = false
    await load()
  } finally {
    saving.value = false
  }
}

const handleDelete = async (user) => {
  await deleteUser(user.id)
  message.success('删除成功')
  await load()
}

const columns = [
  { title: '账号', key: 'username' },
  { title: '持有者', key: 'owner' },
  {
    title: '权限',
    key: 'permissions',
    render: (row) => {
      if (row.is_admin) return h(NTag, { type: 'warning', size: 'small' }, () => '管理员（全部权限）')
      return h(NSpace, { size: 'small' }, () =>
        (row.permissions || []).map((p) =>
          h(NTag, { size: 'small', bordered: false }, () => permLabelMap[p] || p)
        )
      )
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 160,
    render: (row) => {
      const btns = [
        h(NButton, { size: 'small', quaternary: true, type: 'primary', onClick: () => openEdit(row) }, () => '修改'),
      ]
      if (!row.is_admin) {
        btns.push(
          h(NPopconfirm, { onPositiveClick: () => handleDelete(row) }, {
            trigger: () => h(NButton, { size: 'small', quaternary: true, type: 'error' }, () => '删除'),
            default: () => `确定删除用户 ${row.username}？`,
          })
        )
      }
      return h(NSpace, { size: 'small' }, () => btns)
    },
  },
]

onMounted(load)
</script>

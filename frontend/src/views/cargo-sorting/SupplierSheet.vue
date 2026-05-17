<template>
  <n-drawer
    :show="show"
    placement="bottom"
    :height="380"
    :auto-focus="false"
    style="border-radius: 16px 16px 0 0"
    @update:show="(v) => emit('update:show', v)"
  >
    <n-drawer-content title="选择手工商家" closable>
      <n-spin :show="loading">
        <div v-if="!loading && suppliers.length === 0" class="empty">
          暂无含分拣信息的商家
        </div>
        <div v-else class="list">
          <div
            v-for="name in suppliers"
            :key="name"
            class="item"
            :class="{ active: name === selected }"
            @click="onPick(name)"
          >
            <span>{{ name }}</span>
            <n-icon v-if="name === selected" :size="18" color="#6366f1">
              <CheckmarkOutline />
            </n-icon>
          </div>
        </div>
      </n-spin>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup>
import { ref, watch } from 'vue'
import { NDrawer, NDrawerContent, NSpin, NIcon, useMessage } from 'naive-ui'
import { CheckmarkOutline } from '@vicons/ionicons5'
import { getCargoSortingSuppliers } from '@/api/cargoSorting'

const props = defineProps({
  show: { type: Boolean, required: true },
  selected: { type: String, default: '' },
})
const emit = defineEmits(['update:show', 'pick'])

const message = useMessage()

const loading = ref(false)
const suppliers = ref([])

const load = async () => {
  loading.value = true
  try {
    const { data } = await getCargoSortingSuppliers()
    suppliers.value = data.suppliers || []
  } catch (err) {
    message.error('加载商家失败')
  } finally {
    loading.value = false
  }
}

watch(() => props.show, (v) => {
  if (v) load()
})

const onPick = (name) => {
  emit('pick', name)
  emit('update:show', false)
}
</script>

<style scoped>
.list { display: flex; flex-direction: column; }
.item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 4px;
  border-bottom: 1px solid #f3f4f6;
  font-size: 15px;
  min-height: 44px;
  cursor: pointer;
}
.item:active { background: #f9fafb; }
.item.active { color: #6366f1; font-weight: 600; }
.empty {
  text-align: center;
  color: #9ca3af;
  padding: 40px 0;
}
</style>

import { onMounted, ref } from 'vue'
import { getPartCategories } from '@/api/parts'

export function usePartCategories(onError) {
  const categoryOptions = ref([])
  const unclassifiedCategory = ref(null)

  onMounted(async () => {
    try {
      const { data } = await getPartCategories()
      categoryOptions.value = data.options
      unclassifiedCategory.value = data.unclassified_value
    } catch {
      onError?.('配件类目加载失败，请刷新后重试')
    }
  })

  const categoryOption = (value) => categoryOptions.value.find(option => option.value === value)
  const categoryLabel = (value) => categoryOption(value)?.label ?? (
    value ? (unclassifiedCategory.value ? `待细分（原：${value}）` : value) : '待细分'
  )
  return { categoryOptions, unclassifiedCategory, categoryOption, categoryLabel }
}

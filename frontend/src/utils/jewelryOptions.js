// Product type answers "what is it?"; unit answers "how is it counted?".
// Keep legacy values in storage until the user explicitly classifies a record.
export const jewelryTypes = ['耳饰', '项链', '手链', '戒指', '胸针', '发饰', '组合套装', '其他']
export const jewelryCategoryOptions = jewelryTypes.map((value) => ({ label: value, value }))
export const jewelryUnitOptions = ['个', '对', '条', '枚', '件', '套', '卡'].map((value) => ({ label: value, value }))

export const isJewelryType = (value) => jewelryTypes.includes(value)
export const jewelryCategoryLabel = (value) => isJewelryType(value)
  ? value
  : value ? `待分类（原：${value}）` : '待分类'

export const jewelryCategoryEditOptions = (value) => isJewelryType(value) || !value
  ? jewelryCategoryOptions
  : [{ label: jewelryCategoryLabel(value), value, disabled: true }, ...jewelryCategoryOptions]

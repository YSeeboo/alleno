import assert from 'node:assert/strict'
import test from 'node:test'
import {
  jewelryTypes,
  jewelryCategoryOptions,
  jewelryUnitOptions,
  isJewelryType,
  jewelryCategoryLabel,
  jewelryCategoryEditOptions,
} from '../src/utils/jewelryOptions.js'

test('new types describe products, not counting units', () => {
  for (const value of ['耳饰', '项链', '手链', '戒指', '组合套装']) {
    assert.ok(isJewelryType(value))
    assert.equal(jewelryCategoryLabel(value), value)
  }
  for (const value of ['单件', '单对', '套装', '对', '卡']) {
    assert.equal(isJewelryType(value), false)
  }
  assert.deepEqual(jewelryCategoryOptions.map(option => option.value), jewelryTypes)
})

test('units include cards and remain separate from categories', () => {
  assert.deepEqual(jewelryUnitOptions.map(option => option.value), ['个', '对', '条', '枚', '件', '套', '卡'])
  assert.ok(jewelryUnitOptions.some(option => option.value === '卡' && option.label === '卡'))
})

test('legacy and missing values remain visibly pending instead of being guessed', () => {
  for (const value of ['单件', '单对', '套装', '自定义旧类目']) {
    assert.equal(jewelryCategoryLabel(value), `待分类（原：${value}）`)
    const options = jewelryCategoryEditOptions(value)
    assert.equal(options[0].value, value)
    assert.equal(options[0].disabled, true)
    assert.deepEqual(options.slice(1), jewelryCategoryOptions)
  }
  assert.equal(jewelryCategoryLabel(null), '待分类')
  assert.equal(jewelryCategoryLabel(''), '待分类')
  assert.equal(jewelryCategoryEditOptions(null), jewelryCategoryOptions)
  assert.equal(jewelryCategoryEditOptions('耳饰'), jewelryCategoryOptions)
})

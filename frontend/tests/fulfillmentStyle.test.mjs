import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('fulfillment adds menu entries without replacing the original application shell', () => {
  const layout = source('layouts/DefaultLayout.vue')
  const theme = source('App.vue')
  assert.match(layout, /:width="240"/)
  assert.match(layout, /ALLENOP/)
  assert.match(layout, /:src="logoWhite"/)
  assert.match(layout, /isMobile && collapsed/)
  assert.doesNotMatch(layout, /workspace-topbar|brand-mark|JEWELRY WORKSPACE/)
  for (const module of ['stock-readiness', 'shipments']) assert.match(layout, new RegExp(`key: '${module}'`))
  assert.match(theme, /siderColor: '#10141A'/)
  assert.match(theme, /color: '#F6F7F8'/)
  assert.match(theme, /borderColor: '#E2E8F0'/)
  assert.match(theme, /borderRadius: '12px'/)
})

test('other fulfillment lists retain their existing page headers, filter bars and Naive UI tables', () => {
  for (const path of ['views/fulfillment/ShipmentList.vue', 'views/fulfillment/StockReadiness.vue']) {
    const view = source(path)
    assert.match(view, /class="page-header"/)
    assert.match(view, /class="page-title"/)
    assert.match(view, /class="filter-bar"/)
    assert.match(view, /<n-(?:data-table|spin)/)
    assert.match(view, /<n-input /)
    assert.doesNotMatch(view, /BUSINESS WORKSPACE|wf-stat|wf-button|wf-input|<table/)
  }
  assert.match(source('components/fulfillment/ShipmentTable.vue'), /<n-data-table/)
})

test('new details and dialogs use the existing controls rather than a separate Demo skin', () => {
  const paths = [
    'views/orders/OrderDetail.vue', 'views/orders/OrderProduction.vue',
    'views/fulfillment/ShipmentCreate.vue', 'views/fulfillment/ShipmentDetail.vue',
    'components/fulfillment/ReservationDialog.vue', 'components/fulfillment/OrderHandcraftDialog.vue',
    'components/fulfillment/HandcraftTargetPicker.vue',
  ]
  for (const path of paths) {
    const view = source(path)
    assert.match(view, /<n-button /)
    assert.doesNotMatch(view, /wf-button|wf-input|<button\b|<input\b|<select\b|<textarea\b|<table\b/)
  }
  assert.match(source('components/fulfillment/OrderWorkspaceHeader.vue'), /<n-tabs/)
  const css = source('styles/fulfillment.css')
  assert.doesNotMatch(css, /\.wf-button|\.wf-input|\.wf-card|\.fulfillment-page h[123]|\.n-layout/)
})

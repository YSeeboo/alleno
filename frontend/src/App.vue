<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { NConfigProvider, NMessageProvider, NDialogProvider } from 'naive-ui'

const themeOverrides = {
  // UI refresh: monochrome (near-black) + single emerald accent.
  common: {
    primaryColor: '#1E7A5A',
    primaryColorHover: '#1A6B4F',
    primaryColorPressed: '#155C43',
    primaryColorSuppl: '#1E7A5A',
    borderRadius: '8px',
    borderRadiusMedium: '8px',
    borderRadiusSmall: '6px',
  },
  Layout: {
    color: '#F6F7F8',
    headerColor: '#10141A',
    headerBorderColor: '#10141A',
    siderColor: '#10141A',
    siderBorderColor: '#20262E',
  },
  Menu: {
    color: 'transparent',
    colorInverted: 'transparent',
    itemTextColor: '#C0C6CD',
    itemTextColorActive: '#3FBF8F',
    itemTextColorActiveHover: '#5BD0A4',
    itemTextColorHover: '#E7EAEE',
    itemTextColorChildActive: '#3FBF8F',
    itemIconColor: '#AEB4BC',
    itemIconColorActive: '#3FBF8F',
    itemIconColorHover: '#E7EAEE',
    itemIconColorChildActive: '#3FBF8F',
    itemColorActive: 'rgba(30,122,90,0.18)',
    itemColorActiveHover: 'rgba(30,122,90,0.24)',
    itemColorHover: 'rgba(255,255,255,0.06)',
    dividerColor: '#20262E',
  },
  DataTable: {
    thColor: '#FFFFFF',
    tdColorHover: '#FAFBFB',
    borderColor: '#ECEDEF',
    thTextColor: '#8B9096',
    thFontWeight: '600',
  },
  Card: {
    color: '#FFFFFF',
    borderColor: '#E2E8F0',
    borderRadius: '12px',
  },
  Button: {
    borderRadius: '8px',
  },
  Input: {
    borderRadius: '8px',
  },
  Modal: {
    borderRadius: '16px',
  },
}
</script>

<style>
* { box-sizing: border-box; }
body { margin: 0; background: #F6F7F8; }

/* Design language: eyebrow-style table headers app-wide (small, spaced, muted) */
.n-data-table .n-data-table-th {
  font-size: 12px !important;
  font-weight: 600 !important;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}
.n-data-table .n-data-table-th .n-data-table-th__title {
  font-size: 12px !important;
}

/* Design-language table-cell utilities — global because they are used inside
   n-data-table column render functions (h()), which don't receive a component's
   scoped data-v attribute, so scoped styles never reach them. Shared across all
   list pages. */
.mono { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }
.cell-id { font-size: 12.5px; color: #6B7280; font-variant-numeric: tabular-nums; }
.cell-name-wrap { display: flex; align-items: center; gap: 8px; }
.cell-color { display: inline-flex; align-items: center; gap: 6px; }
.color-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; flex-shrink: 0; box-shadow: inset 0 0 0 1px rgba(0,0,0,.08); }
.tag-combo { font-size: 10.5px; font-weight: 600; padding: 1px 7px; border-radius: 5px; background: #E6F2EC; color: #1E7A5A; letter-spacing: .2px; white-space: nowrap; }
.currency-sym { color: #8B9096; font-size: 11px; }
.stock-ok { font-weight: 600; color: #1A1D21; font-variant-numeric: tabular-nums; }
.stock-low { font-weight: 700; color: #E5484D; display: inline-flex; align-items: center; gap: 5px; font-variant-numeric: tabular-nums; }
.pill-low { font-size: 10px; background: #FDECEC; color: #E5484D; border-radius: 5px; padding: 1px 6px; font-weight: 600; }
</style>

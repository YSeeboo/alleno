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
    thColor: '#F8FAFC',
    tdColorHover: '#F1F5F9',
    borderColor: '#E2E8F0',
    thTextColor: '#64748B',
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
</style>

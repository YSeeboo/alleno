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
  common: {
    primaryColor: '#6366F1',
    primaryColorHover: '#4F46E5',
    primaryColorPressed: '#4338CA',
    primaryColorSuppl: '#6366F1',
    borderRadius: '8px',
    borderRadiusMedium: '8px',
    borderRadiusSmall: '6px',
  },
  Layout: {
    color: '#F8FAFC',
    headerColor: '#0F172A',
    headerBorderColor: '#0F172A',
    siderColor: '#0F172A',
    siderBorderColor: '#1E293B',
  },
  Menu: {
    color: 'transparent',
    colorInverted: 'transparent',
    itemTextColor: '#94A3B8',
    itemTextColorActive: '#6366F1',
    itemTextColorActiveHover: '#4F46E5',
    itemTextColorHover: '#E2E8F0',
    itemTextColorChildActive: '#6366F1',
    itemIconColor: '#64748B',
    itemIconColorActive: '#6366F1',
    itemIconColorHover: '#E2E8F0',
    itemIconColorChildActive: '#6366F1',
    itemColorActive: 'rgba(99,102,241,0.12)',
    itemColorActiveHover: 'rgba(99,102,241,0.16)',
    itemColorHover: 'rgba(255,255,255,0.08)',
    dividerColor: '#1E293B',
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
body { margin: 0; background: #F8FAFC; }
</style>

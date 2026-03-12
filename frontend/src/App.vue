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
import { BRAND_COLOR } from '@/utils/ui'

const themeOverrides = {
  common: {
    primaryColor: BRAND_COLOR,
    primaryColorHover: '#ff3333',
    primaryColorPressed: '#d90000',
    primaryColorSuppl: '#ff6666',
  },
}
</script>

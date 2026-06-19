<template>
  <div class="fab-spacer"></div>
  <div class="fab-bar">
    <div class="fab-pill"><slot /></div>
  </div>
</template>

<script setup></script>

<style scoped>
/* reserve space so page content isn't hidden behind the sticky bar */
.fab-spacer { height: 64px; }
.fab-bar {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: center;
  padding: 14px 0 calc(14px + env(safe-area-inset-bottom));
  pointer-events: none;
  z-index: 20;
}
.fab-pill {
  pointer-events: auto;
  background: #1A1D21;
  border-radius: 14px;
  padding: 8px 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 14px 34px rgba(16, 20, 26, 0.30);
}
</style>

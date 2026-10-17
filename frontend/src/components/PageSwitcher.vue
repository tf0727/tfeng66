<script setup lang="ts">
defineProps<{ destination: 'admin' | 'consultation' }>()
</script>

<template>
  <a class="page-switcher" :href="destination === 'admin' ? '/admin.html' : '/'">
    {{ destination === 'admin' ? '进入管理后台 ↗' : '返回咨询平台 ↗' }}
  </a>
</template>

<style scoped>
.page-switcher {
  position: fixed;
  top: 12px;
  right: 20px;
  z-index: 100;
  padding: 8px 14px;
  border: 1px solid #dcd7ff;
  border-radius: 8px;
  background: #f4f1ff;
  color: #5946d8;
  text-decoration: none;
  font: 13px/1.4 "Microsoft YaHei", sans-serif;
}
.page-switcher:hover { background: #e9e3ff; }
.page-switcher:focus-visible { outline: 2px solid #6d5dfc; outline-offset: 3px; }
</style>

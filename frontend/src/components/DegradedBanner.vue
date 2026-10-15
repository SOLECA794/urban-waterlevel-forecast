<template>
  <el-alert
    class="banner"
    type="warning"
    :closable="false"
    show-icon
    title="后端服务不可用，已自动降级为 mock 数据演示（页面功能不受影响，恢复后自动切回真实接口）"
  />
</template>

<script setup lang="ts">
</script>

<style scoped>
.banner { margin-bottom: 8px; }
</style>

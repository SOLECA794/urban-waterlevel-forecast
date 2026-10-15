<template>
  <div class="nf-page">
    <div class="nf-card">
      <div class="nf-code">404</div>
      <div class="nf-title">页面不存在</div>
      <div class="muted">您访问的地址没有对应页面；系统已停止跳转，避免静默白屏（评审 P0-2 兜底）。</div>
      <div class="nf-ops">
        <el-button type="primary" @click="$router.push('/')">返回系统总览</el-button>
        <el-button plain @click="$router.push('/agent')">进入 Agent 控制台</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.nf-page { min-height: 70vh; display: flex; align-items: center; justify-content: center; }
.nf-card { text-align: center; background: #fff; border: 1px solid var(--line, #e6ebf0); border-radius: 6px; padding: 48px 64px; }
.nf-code { font-size: 44px; font-weight: 700; color: var(--brand); }
.nf-title { font-size: 18px; font-weight: 600; margin: 8px 0 6px; }
.nf-ops { margin-top: 20px; display: flex; gap: 10px; justify-content: center; }
</style>

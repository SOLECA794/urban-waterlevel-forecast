<template>
  <el-container class="layout">
    <el-aside width="210px" class="aside">
      <div class="logo">
        <span class="logo-mark">▲</span>
        <div>
          <div class="logo-title">内涝预测预警</div>
          <div class="muted">脚手架 · 可运行原型</div>
        </div>
      </div>
      <el-menu :default-active="route.path" router class="menu">
        <el-menu-item index="/">系统总览</el-menu-item>
        <el-menu-item index="/alerts">预警中心</el-menu-item>
        <el-menu-item index="/settings">系统设置</el-menu-item>
        <el-menu-item index="/agent">Agent 控制台</el-menu-item>
      </el-menu>
      <div class="aside-foot muted">
        L0 只读 / L1 生成 / L2 需确认<br />L3 自动执行永不做
      </div>
    </el-aside>

    <el-container>
      <el-header class="header" height="56px">
        <DegradedBanner v-if="system.degraded" />
        <div class="status-bar">
          <span class="chip" :class="sourceChipClass">
            数据源：{{ health?.datasource.status ?? '—' }}<template v-if="health?.datasource.data_age_min != null"> · 滞后 {{ health.datasource.data_age_min }}min</template>
          </span>
          <span class="chip" :class="health?.model.loaded ? 'ok' : 'bad'">
            当前模型：{{ health?.model.active ?? '—' }}
          </span>
          <span class="chip" :class="health?.database.status === 'ok' ? 'ok' : 'bad'">
            数据库：{{ health?.database.status ?? '—' }}
          </span>
          <span class="chip neutral">今日预警：有效 {{ stats?.active_total ?? 0 }} / 参考 {{ stats?.reference_total ?? 0 }}</span>
          <span class="muted">{{ route.meta.title }}</span>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getAlertStats, getHealth } from '@/api/endpoints'
import { usePolling } from '@/composables/usePolling'
import DegradedBanner from '@/components/DegradedBanner.vue'
import { useSystemStore } from '@/stores/useSystemStore'

const route = useRoute()
const system = useSystemStore()
const health = ref(system.health)
const stats = ref<{ active_total: number; reference_total: number } | null>(null)

/** 数据源三态：READY/STREAMING=ok；STALE=黄（评审 R2：滞后不再误报正常）；其余=bad */
const sourceChipClass = computed(() => {
  const st = health.value?.datasource.status ?? ''
  if (['READY', 'STREAMING'].includes(st)) return 'ok'
  if (st === 'STALE') return 'warn'
  return 'bad'
})

async function refreshStatus() {
  try {
    health.value = await getHealth()
    system.health = health.value
  } catch { /* 降级横幅已由 client 置位 */ }
  try {
    stats.value = await getAlertStats()
  } catch { /* 忽略 */ }
}

onMounted(() => document.title = '城市内涝水位预测预警系统')
usePolling(refreshStatus, 30_000)
</script>

<style scoped>
.layout { height: 100%; }
.aside { background: #1f2d3d; color: #cfd8e3; display: flex; flex-direction: column; }
.logo { display: flex; gap: 10px; align-items: center; padding: 18px 16px 12px; }
.logo-mark { color: #8fc7ee; font-size: 22px; }
.logo-title { font-weight: 600; color: #fff; }
.menu { border-right: none; background: transparent; flex: 1; }
.aside :deep(.el-menu-item) { color: #cfd8e3; }
.aside :deep(.el-menu-item.is-active) { color: #fff; background: #1e6fa8; }
.aside-foot { padding: 14px 16px; line-height: 1.8; font-size: 11px; }
.header { background: #fff; border-bottom: 1px solid #e6ebf0; padding: 10px 20px 6px; }
.status-bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.chip { font-size: 12px; border-radius: 12px; padding: 2px 10px; background: #f2f6fa; color: #556; }
.chip.ok::before { content: '● '; color: var(--status-ok); }
.chip.warn { background: #fdf6ec; color: #b88230; }
.chip.warn::before { content: '● '; color: var(--alert-yellow); }
.chip.bad::before { content: '● '; color: var(--status-error); }
.chip.neutral::before { content: '● '; color: var(--brand); }
.main { padding: 0; overflow: auto; }
</style>

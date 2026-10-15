<template>
  <el-card shadow="never" class="situation">
    <div class="blocks">
      <!-- ① 需关注点位 -->
      <div class="block click" @click="$router.push('/alerts')">
        <div class="num" :class="watchColor">{{ watchCount }}</div>
        <div class="label">需关注点位<span class="unit">（等级≥黄）</span></div>
      </div>
      <!-- ② 今日有效预警 -->
      <div class="block click" @click="$router.push('/alerts')">
        <div class="num" :class="watchColor">{{ stats?.effective_total ?? '—' }}</div>
        <div class="label">今日有效预警</div>
      </div>
      <!-- ③ 降雨状态 -->
      <div class="block click" @click="$router.push('/station/1')">
        <div class="num rain">{{ rainText }}</div>
        <div class="label">降雨状态</div>
      </div>
      <!-- ④ 系统状态 -->
      <div class="block click" @click="$router.push('/settings')">
        <div class="num" :class="systemOk ? 'ok' : 'bad'">{{ systemOk ? '正常' : '异常' }}</div>
        <div class="label">系统状态（数据源/模型/库）</div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AlertStatsGlobal, HealthData, StationItem } from '@/types'

const props = defineProps<{
  stations: StationItem[]
  stats: AlertStatsGlobal | null
  health: HealthData | null
}>()

/** 需关注点位：等级 ≥ yellow（rank≥2） */
const watchCount = computed(() => props.stations.filter((s) => s.alert.rank >= 2).length)

const hasOrange = computed(() => props.stations.some((s) => s.alert.rank >= 3))
const watchColor = computed(() => (hasOrange.value ? 'lv-orange' : 'lv-yellow'))

/** 降雨状态：从最新观测雨强推断，无源显示 —（精修 §3.1.1） */
const rainText = computed(() => {
  const rains = props.stations.map((s) => s.current.rain_observed ?? 0)
  if (!props.stations.length || rains.every((r) => r == null)) return '—'
  const peak = Math.max(...rains.map((r) => Number(r ?? 0)))
  if (peak >= 5) return '强降雨'
  if (peak > 0.2) return '持续中'
  return '间歇'
})

/** 系统状态三态合并：数据源 STALE/异常、模型未加载、库异常任一 → 异常 */
const systemOk = computed(() => {
  const h = props.health
  if (!h) return false
  const dsOk = ['READY', 'STREAMING'].includes(h.datasource.status)
  return dsOk && h.model.loaded && h.database.status === 'ok'
})
</script>

<style scoped>
.situation { margin-bottom: 16px; }
.blocks { display: flex; gap: 16px; }
.block { flex: 1; padding: 2px 8px; border-right: 1px solid var(--line); }
.block:last-child { border-right: none; }
.block.click { cursor: pointer; border-radius: 4px; transition: background 0.15s; }
.block.click:hover { background: var(--brand-light); }
.num { font-size: 22px; font-weight: 700; color: var(--brand); line-height: 1.3; }
.num.ok { color: var(--status-ok); }
.num.bad, .num.rain { color: var(--alert-orange); }
.num.rain { font-size: 18px; padding-top: 4px; }
.label { font-size: 12px; color: var(--text-muted); }
.unit { font-weight: 400; }
</style>

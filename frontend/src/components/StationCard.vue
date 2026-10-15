<template>
  <el-card class="card side-stripe" shadow="hover" :style="{ '--stripe-color': stripeColor }" @click="goDetail">
    <div class="head">
      <span class="name">{{ station.station_name }}</span>
      <AlertBadge :level="station.alert.level" :is-reference="station.alert.is_reference" />
    </div>
    <div class="code muted">{{ station.station_code }} · {{ station.location }}</div>
    <div class="level-row">
      <span class="level" :style="{ color: stripeColor }">{{ station.current.level?.toFixed(2) ?? '—' }}</span>
      <span class="unit">m</span>
      <span class="muted">更新于 {{ station.current.ts?.slice(11, 16) ?? '—' }}</span>
    </div>

    <!-- 距下一阈值语义行（替代原进度条，数字有参照，精修 §3.1.2） -->
    <div class="next-th" :class="nextTh.over ? 'over' : ''">
      {{ nextTh.over ? '已超' : '距' }}<b :class="nextTh.cls">{{ nextTh.name }} {{ Math.abs(nextTh.gap).toFixed(2) }}m</b>
    </div>

    <!-- 迷你趋势 sparkline（10 个历史点，加载前占位灰条） -->
    <div class="spark">
      <div v-if="!sparkReady" class="spark-placeholder"></div>
      <div v-show="sparkReady" ref="sparkEl" class="spark-chart"></div>
    </div>

    <div class="th-line">蓝 {{ station.thresholds.blue }} · 黄 {{ station.thresholds.yellow }} · 橙 {{ station.thresholds.orange }} · 红 {{ station.thresholds.red }}</div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getSeries } from '@/api/endpoints'
import type { StationItem } from '@/types'
import { useEcharts } from '@/composables/useEcharts'
import AlertBadge from './AlertBadge.vue'

const props = defineProps<{ station: StationItem }>()
const router = useRouter()

const LV_COLOR: Record<string, string> = {
  red: '#f44336', orange: '#ff9800',
  yellow: '#ffc107', blue: '#2196f3',
  normal: '#9e9e9e',
}

const stripeColor = computed(() => LV_COLOR[props.station.alert.level ?? 'normal'] ?? LV_COLOR.normal)

/** 距下一等级阈值（已超当前等级则显示"已超"） */
const nextTh = computed(() => {
  const th = props.station.thresholds
  const lv = props.station.current.level
  const order: Array<{ key: 'blue' | 'yellow' | 'orange' | 'red'; name: string; rank: number }> = [
    { key: 'blue', name: '蓝色', rank: 1 },
    { key: 'yellow', name: '黄色', rank: 2 },
    { key: 'orange', name: '橙色', rank: 3 },
    { key: 'red', name: '红色', rank: 4 },
  ]
  const curRank = props.station.alert.rank
  const curLv = curRank === 0 ? 0 : curRank
  const next = order.find((o) => o.rank > curLv) ?? order[3]
  const gap = lv != null && th[next.key] != null ? +(th[next.key]! - lv).toFixed(2) : 0
  const over = lv != null && curRank >= next.rank
  return { name: next.name, gap, over, cls: over ? `lv-${next.key}` : '' }
})

// --- sparkline（尾部 10 点，色=等级色） ---
const sparkEl = ref<HTMLElement>()
const sparkReady = ref(false)
const { setOption } = useEcharts(sparkEl)

async function loadSpark() {
  try {
    const s = await getSeries(props.station.station_id, 2)
    const pts = s.points.filter((p) => p.level != null).slice(-10)
    if (!pts.length) return
    setOption({
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: { type: 'category', show: false, data: pts.map((p) => p.ts) },
      yAxis: { type: 'value', show: false, scale: true },
      series: [{
        type: 'line', data: pts.map((p) => p.level), showSymbol: false,
        lineStyle: { color: stripeColor.value, width: 1.5 },
        itemStyle: { color: stripeColor.value },
        silent: true,
      }],
    })
    sparkReady.value = true
  } catch { /* 静默：sparkline 失败不影响卡片主信息 */ }
}

onMounted(loadSpark)
watch(() => props.station.current.ts, loadSpark)

function goDetail() {
  router.push(`/station/${props.station.station_id}`)
}
</script>

<style scoped>
.card { cursor: pointer; width: 300px; }
.head { display: flex; justify-content: space-between; align-items: center; }
.name { font-weight: 600; }
.level-row { display: flex; align-items: baseline; gap: 6px; margin: 8px 0 6px; }
.level { font-size: 30px; font-weight: 700; }
.unit { color: var(--text-muted); }
.next-th { font-size: 12px; color: var(--text-sub); margin-bottom: 6px; }
.next-th.over b { font-weight: 600; }
.spark { height: 28px; margin-bottom: 6px; }
.spark-placeholder { height: 28px; border-radius: 2px; background: repeating-linear-gradient(90deg, #eef1f4 0 14px, #f7f9fa 14px 28px); }
.spark-chart { width: 100%; height: 28px; }
.th-line { font-size: 11px; color: var(--text-muted); }
</style>

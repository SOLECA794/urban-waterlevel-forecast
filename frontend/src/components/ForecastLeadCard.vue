<template>
  <!-- 提前量 > 0：绿色强调卡 + 时间轴示意 -->
  <div v-if="lead > 0" class="lead-card ok">
    <div class="main">较阈值报警提前 <b>{{ lead }}</b> 分钟</div>
    <div class="lead-axis">
      <span class="node"><span class="dot" :style="{ background: 'var(--status-ok)' }"></span>当前 {{ startTime }}</span>
      <span class="bar"></span>
      <span class="lead-min">{{ lead }}min</span>
      <span class="bar"></span>
      <span class="node"><span class="dot" :style="{ background: levelColor }"></span>预测触线 {{ crossTime }}</span>
    </div>
  </div>
  <!-- 提前量 = 0：解释文案（评审 P1-6，替代裸「0 分钟」） -->
  <div v-else-if="lead === 0" class="lead-card zero">
    <div class="main">当前水位已超阈值，预警即时触发</div>
    <div class="muted">提前量不适用（阈值越线与预警判定发生在同一时刻）</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/** 预警摘要的最小形状：兼容 AlertBrief 与 StationAlertInfo 两种来源 */
interface LeadAlertLike {
  level?: string | null
  lead_minutes_advantage?: number | null
}

const props = defineProps<{
  alert: LeadAlertLike | null
  predictTime?: string | null
}>()

const lead = computed(() => props.alert?.lead_minutes_advantage ?? -1)

const LEVEL_COLOR: Record<string, string> = {
  blue: '#2196f3', yellow: '#ffc107', orange: '#ff9800', red: '#f44336',
}
const levelColor = computed(() => LEVEL_COLOR[props.alert?.level ?? ''] ?? '#9e9e9e')

const startTime = computed(() => (props.predictTime ?? '').slice(11, 16) || '—')
const crossTime = computed(() => {
  const base = props.predictTime
  if (!base || !lead.value) return '—'
  const t = new Date(base.replace(' ', 'T'))
  if (Number.isNaN(t.getTime())) return '—'
  t.setMinutes(t.getMinutes() + lead.value)
  const hh = String(t.getHours()).padStart(2, '0')
  const mm = String(t.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
})
</script>

<style scoped>
.lead-card {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px 14px;
  background: #fff;
}
.lead-card.ok { border-left: 4px solid var(--status-ok); background: #f4faf5; }
.lead-card.zero { border-left: 4px solid var(--status-gray); background: #fafbfc; }
.main { font-size: 13px; font-weight: 600; color: var(--text-main); }
.lead-card.ok .main b { color: var(--status-ok); font-size: 16px; }
</style>

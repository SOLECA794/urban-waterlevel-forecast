<template>
  <div v-loading="loading" element-loading-text="加载预警记录…" class="timeline-wrap">
    <el-empty v-if="!loading && !alerts.length" description="暂无预警记录" />
    <div
      v-for="a in alerts"
      :key="a.alert_id"
      class="tl-item"
      :class="{ ref: a.is_reference }"
      @click="$router.push(`/station/${a.station_id}`)"
    >
      <div class="tl-side">
        <span class="tl-dot" :style="{ background: levelColor(a.level) }"></span>
        <span v-if="a.status === 'active'" class="tl-line active"></span>
        <span v-else class="tl-line"></span>
      </div>
      <div class="tl-body">
        <div class="tl-head">
          <AlertBadge :level="a.level" :is-reference="a.is_reference" />
          <b class="st-name">{{ a.station_name ?? `站点 ${a.station_id}` }}</b>
          <span class="muted">{{ fmt(a.alert_time) }}</span>
          <el-tag v-if="a.status === 'active'" type="danger" size="small">生效中</el-tag>
          <el-tag v-else type="info" size="small" effect="plain">已解除</el-tag>
        </div>
        <div class="tl-reason" :title="a.reason ?? ''">{{ a.reason ?? '—' }}</div>
        <div class="muted tl-meta">
          预见期 {{ a.lead_hours ? a.lead_hours + 'h' : '—' }}
          · 提前量 {{ leadText(a) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AlertItem } from '@/types'
import AlertBadge from './AlertBadge.vue'

defineProps<{ alerts: AlertItem[]; loading?: boolean }>()

const LEVEL_COLOR: Record<string, string> = {
  blue: '#2196f3', yellow: '#ffc107', orange: '#ff9800', red: '#f44336',
}

function levelColor(level: string) {
  return LEVEL_COLOR[level] ?? '#9e9e9e'
}

/** 提前量文案：0 → 即时触发解释（评审 P1-6）；null → — */
function leadText(a: AlertItem) {
  if (a.lead_minutes_advantage == null) return '—'
  if (a.lead_minutes_advantage === 0) return '即时触发（提前量不适用）'
  return `${a.lead_minutes_advantage} 分钟`
}

function fmt(ts: string | null) {
  return ts ? ts.replace('T', ' ').slice(0, 19) : '—'
}
</script>

<style scoped>
.timeline-wrap { min-height: 120px; }
.tl-item {
  display: flex;
  gap: 12px;
  padding: 10px 8px;
  border-radius: 4px;
  cursor: pointer;
}
.tl-item:hover { background: var(--brand-light); }
/* 参考级：整条浅色（沿用参考级样式语义） */
.tl-item.ref { background: #fafbfc; opacity: 0.82; }
.tl-side { display: flex; flex-direction: column; align-items: center; width: 14px; }
.tl-dot { width: 12px; height: 12px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 0 1px var(--line); flex-shrink: 0; }
.tl-line { flex: 1; width: 2px; background: var(--line); margin-top: 4px; }
.tl-line.active { background: var(--alert-red); opacity: 0.5; }
.tl-body { flex: 1; min-width: 0; }
.tl-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.st-name { font-size: 13px; }
.tl-reason {
  font-size: 12px;
  color: var(--text-sub);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tl-meta { margin-top: 2px; }
</style>

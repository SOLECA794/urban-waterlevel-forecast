<template>
  <el-table :data="alerts" size="small" :row-class-name="rowClass" @row-click="(r: any) => emit('open', r)">
    <el-table-column label="等级" width="110">
      <template #default="{ row }">
        <AlertBadge :level="row.level" :is-reference="row.is_reference" />
      </template>
    </el-table-column>
    <el-table-column prop="station_name" label="监测点" min-width="140" />
    <el-table-column prop="reason" label="触发原因" min-width="280" show-overflow-tooltip />
    <el-table-column label="预见期" width="80">
      <template #default="{ row }">{{ row.lead_hours ? row.lead_hours + 'h' : '—' }}</template>
    </el-table-column>
    <el-table-column label="提前量" width="90">
      <template #default="{ row }">
        <span v-if="row.lead_minutes_advantage != null" class="lv-blue">提前 {{ row.lead_minutes_advantage }} 分钟</span>
        <span v-else class="muted">—</span>
      </template>
    </el-table-column>
    <el-table-column prop="alert_time" label="预警时间" width="170">
      <template #default="{ row }">{{ fmt(row.alert_time) }}</template>
    </el-table-column>
    <el-table-column label="状态" width="90">
      <template #default="{ row }">
        <el-tag v-if="row.status === 'active'" type="danger" size="small">生效中</el-tag>
        <el-tag v-else type="info" size="small">已解除</el-tag>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { AlertItem } from '@/types'
import AlertBadge from './AlertBadge.vue'

defineProps<{ alerts: AlertItem[] }>()
const emit = defineEmits<{ (e: 'open', row: AlertItem): void }>()

function fmt(ts: string | null) {
  return ts ? ts.replace('T', ' ').slice(0, 19) : '—'
}
function rowClass({ row }: { row: AlertItem }) {
  return row.is_reference ? 'ref-row' : ''
}
</script>

<style>
/* 参考级预警整行浅色（V2.1） */
.el-table .ref-row { color: #a3aeb7; background: #fafbfc; }
.el-table .ref-row td { color: inherit; }
</style>

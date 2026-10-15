<template>
  <div class="page">
    <!-- Agent 主动巡检态势横幅（值班 agent 第一屏） -->
    <SituationBanner />
    <!-- 态势总览条（精修 §3.1.1） -->
    <SituationBar :stations="store.stations" :stats="store.stats" :health="system.health" />

    <!-- 站点示意图（评审 P2-8 一张图） -->
    <StationMap :stations="store.stations" />

    <!-- 监测点网格（后端已按预警等级降序返回，红色脉动卡片在前） -->
    <div class="card-row" v-loading="store.loading" element-loading-text="加载监测点态势…">
      <StationCard v-for="s in sortedStations" :key="s.station_id" :station="s" />
      <el-empty v-if="!store.loading && !store.stations.length" description="暂无监测点" class="grid-empty" />
    </div>

    <el-card shadow="never">
      <template #header>
        <span>最近预测记录</span>
        <span class="muted" style="margin-left: 8px">模型占位实现 · Agent-A 编排 + 协同修正</span>
        <el-radio-group v-model="statusFilter" size="small" style="float: right">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="normal">正常</el-radio-button>
          <el-radio-button value="degraded">数据延迟</el-radio-button>
        </el-radio-group>
      </template>
      <el-table
        v-loading="recentLoading"
        element-loading-text="加载预测记录…"
        :data="filteredRecent"
        size="small"
        empty-text="暂无预测记录"
        @row-click="(r: any) => $router.push(`/station/${r.station_id}`)"
      >
        <el-table-column prop="forecast_id" label="#" width="70" />
        <el-table-column prop="station_name" label="监测点" min-width="150" />
        <el-table-column prop="model_type" label="模型" width="150" />
        <el-table-column label="预见期" width="80">
          <template #default="{ row }">{{ row.lead_hours }}h</template>
        </el-table-column>
        <el-table-column label="峰值水位" width="110">
          <template #default="{ row }">{{ row.peak_level?.toFixed(2) ?? '—' }} m</template>
        </el-table-column>
        <el-table-column label="发起时间" width="170">
          <template #default="{ row }">{{ fmt(row.predict_time) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.degraded" type="warning" size="small">数据延迟</el-tag>
            <el-tag v-else type="success" size="small" effect="plain">正常</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { getGlobalForecasts, type ForecastBrief } from '@/api/endpoints'
import SituationBar from '@/components/SituationBar.vue'
import SituationBanner from '@/components/SituationBanner.vue'
import StationCard from '@/components/StationCard.vue'
import StationMap from '@/components/StationMap.vue'
import { usePolling } from '@/composables/usePolling'
import { useStationStore } from '@/stores/useStationStore'
import { useSystemStore } from '@/stores/useSystemStore'

const store = useStationStore()
const system = useSystemStore()
const recent = ref<ForecastBrief[]>([])
const recentLoading = ref(false)
const statusFilter = ref<'' | 'normal' | 'degraded'>('')

/** 卡片按等级降序渲染（red>orange>yellow>blue>正常），双保险（后端已排序） */
const sortedStations = computed(() =>
  [...store.stations].sort((a, b) => b.alert.rank - a.alert.rank || a.station_id - b.station_id),
)

const filteredRecent = computed(() => {
  if (statusFilter.value === 'normal') return recent.value.filter((r) => !r.degraded)
  if (statusFilter.value === 'degraded') return recent.value.filter((r) => r.degraded)
  return recent.value
})

async function refresh() {
  await store.refresh()
  recentLoading.value = true
  try {
    const page = await getGlobalForecasts(1, 10)
    recent.value = page.items
  } catch { /* 降级已提示 */ } finally {
    recentLoading.value = false
  }
}

function fmt(ts: string | null) {
  return ts ? ts.replace('T', ' ').slice(0, 19) : '—'
}

usePolling(refresh, 30_000)
</script>

<style scoped>
.grid-empty { width: 100%; }
</style>

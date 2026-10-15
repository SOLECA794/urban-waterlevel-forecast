<template>
  <div class="page" v-if="detail">
    <!-- 点位信息 + 预警徽标 + 提前量卡片 -->
    <div class="head-row">
      <div>
        <h2 class="title">
          {{ detail.station_name }}
          <span class="muted">{{ detail.station_code }} · {{ detail.location }}</span>
        </h2>
        <div class="head-badges">
          <AlertBadge :level="detail.alert.level" :is-reference="detail.alert.is_reference" />
          <ForecastLeadCard :alert="detail.alert" :predict-time="forecast?.predict_time" />
        </div>
      </div>
      <div class="ops">
        <el-radio-group v-model="lead" @change="onPredict">
          <el-radio-button v-for="h in [1, 3, 6, 12]" :key="h" :value="h">{{ h }}h</el-radio-button>
        </el-radio-group>
        <el-select
          v-model="modelId" placeholder="切换模型（S7）" style="width: 230px"
          :popper-options="{ strategy: 'fixed' }" popper-class="ops-popper"
          @change="onPredict"
        >
          <el-option
            v-for="m in models"
            :key="m.model_id"
            :value="m.model_id"
            :label="`${m.model_name}（${m.active ? '当前' : '可切换'}）`"
            :disabled="!m.activatable"
          />
        </el-select>
        <el-button type="primary" :loading="predicting" @click="onPredict">发起预测</el-button>
      </div>
    </div>

    <el-alert
      v-if="bizError"
      type="error" :closable="false" show-icon class="err"
      :title="`预测失败（code ${bizError.code}）：${bizError.message}`"
    />
    <el-alert
      v-if="forecast?.degraded"
      type="warning" :closable="false" show-icon class="err"
      title="数据源断流或滞后：本次为降级预测（持久性模型），标注「数据延迟」"
    />

    <!-- 水位趋势图 + 决策侧栏（≥1200px 并排，<1200px 回落堆叠，精修 §3.2.2） -->
    <el-row :gutter="14">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="chart-card">
          <template #header>
            <span>水位趋势（实线=历史 · 蓝虚线=原始预测 · 橙实线=修正后预测 · 横线=四级阈值）</span>
            <span class="muted" style="margin-left: 8px">预见期越长，置信区间越宽（不确定性传播）</span>
          </template>
          <div v-loading="loadingSeries || predicting" element-loading-text="Agent-A 正在编排…" class="chart-wrap">
            <TrendChart ref="chartRef" :series="series" :forecast="forecast" />
          </div>
          <ForecastSummary :forecast="forecast" :lead-hours="lead" />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <ForecastDecisionPanel :decision="forecast?.decision ?? null" hint="解释左侧预测曲线如何产生" class="side-panel" />
      </el-col>
    </el-row>

    <!-- 最近预测记录（RMSE 空值显示「待回填」，评审 P1-3） -->
    <el-card shadow="never" class="mt">
      <template #header>
        <span>最近预测记录</span>
        <span class="muted" style="margin-left: 8px">点击行可复现该次预测（actual_level 回填后自动计算误差）</span>
      </template>
      <el-table :data="forecastList" size="small" @row-click="loadForecastRow">
        <el-table-column prop="forecast_id" label="#" width="70" />
        <el-table-column prop="model_type" label="模型" width="150" />
        <el-table-column label="预见期" width="80">
          <template #default="{ row }">{{ row.lead_hours }}h</template>
        </el-table-column>
        <el-table-column label="峰值" width="90">
          <template #default="{ row }">{{ row.peak_level?.toFixed(2) ?? '—' }} m</template>
        </el-table-column>
        <el-table-column label="RMSE" width="110">
          <template #default="{ row }">
            <span v-if="row.rmse != null">{{ row.rmse.toFixed(4) }}</span>
            <span v-else class="muted">待回填</span>
          </template>
        </el-table-column>
        <el-table-column label="发起时间" min-width="160">
          <template #default="{ row }">{{ row.predict_time?.replace('T', ' ').slice(0, 19) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  getForecastDetail, getSeries, getStation, getStationForecasts, listModels, predict,
  type ForecastBrief, type ForecastData, type ModelItem, type SeriesData, type StationDetail,
} from '@/api/endpoints'
import { BizError } from '@/api/client'
import AlertBadge from '@/components/AlertBadge.vue'
import ForecastDecisionPanel from '@/components/ForecastDecisionPanel.vue'
import ForecastLeadCard from '@/components/ForecastLeadCard.vue'
import ForecastSummary from '@/components/ForecastSummary.vue'
import TrendChart from '@/components/TrendChart.vue'

const route = useRoute()
const stationId = Number(route.params.id)

const detail = ref<StationDetail | null>(null)
const series = ref<SeriesData | null>(null)
const forecast = ref<ForecastData | null>(null)
const forecastList = ref<ForecastBrief[]>([])
const models = ref<ModelItem[]>([])
const lead = ref(1)
const modelId = ref<number | undefined>(undefined)
const loadingSeries = ref(false)
const predicting = ref(false)
const bizError = ref<BizError | null>(null)
const chartRef = ref<InstanceType<typeof TrendChart>>()

const advantageText = computed(() => {
  const adv = detail.value?.alert.lead_minutes_advantage
  return adv != null ? `本次预警较阈值报警提前 ${adv} 分钟` : ''
})

async function loadAll() {
  detail.value = await getStation(stationId)
  loadingSeries.value = true
  try {
    series.value = await getSeries(stationId, 6)
  } finally {
    loadingSeries.value = false
  }
  const page = await getStationForecasts(stationId, 1, 8)
  forecastList.value = page.items
  models.value = await listModels()
  modelId.value = models.value.find((m) => m.active)?.model_id

  // 评审 P2-10：进入详情页自动加载最近一次预测，首屏不再空图
  if (page.items.length) {
    try {
      const f = await getForecastDetail(stationId, page.items[0].forecast_id)
      applyForecastDetail(f)
    } catch { /* 静默：用户仍可手动发起预测 */ }
  }
}

/** 把 forecast 详情响应适配为 ForecastData 形状（置信区间由逐点上下界推导） */
function applyForecastDetail(f: Record<string, any>) {
  const lowers: number[] = (f.points ?? []).map((p: any) => p.lower).filter((v: any) => v != null)
  const uppers: number[] = (f.points ?? []).map((p: any) => p.upper).filter((v: any) => v != null)
  forecast.value = {
    ...(f as unknown as ForecastData),
    station_code: f.station_code ?? detail.value?.station_code ?? '',
    confidence_interval: {
      lower: lowers.length ? Math.min(...lowers) : 0,
      upper: uppers.length ? Math.max(...uppers) : 0,
    },
  }
}

async function onPredict() {
  predicting.value = true
  bizError.value = null
  try {
    forecast.value = await predict(stationId, lead.value, modelId.value)
    const page = await getStationForecasts(stationId, 1, 8)
    forecastList.value = page.items
    detail.value = await getStation(stationId) // 刷新预警徽标/提前量
  } catch (e) {
    if (e instanceof BizError) bizError.value = e
    else throw e
  } finally {
    predicting.value = false
  }
}

async function loadForecastRow(row: ForecastBrief) {
  // 点击历史记录：优先复现该次预测明细，无明细再重新发起同参数预测
  bizError.value = null
  try {
    const f = await getForecastDetail(stationId, row.forecast_id)
    applyForecastDetail(f)
    lead.value = row.lead_hours
  } catch {
    lead.value = row.lead_hours
    await onPredict()
  }
}

onMounted(loadAll)
</script>

<style scoped>
.head-row { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
.title { margin: 0 0 6px; font-size: 20px; }
.head-badges { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.ops { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.err { margin-bottom: 12px; }
.chart-card { height: 100%; }
.side-panel { height: 100%; }
.chart-wrap { min-height: 420px; }
.mt { margin-top: 16px; }
</style>

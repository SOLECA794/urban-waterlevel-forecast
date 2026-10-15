<template>
  <div class="chart-wrap-box">
    <!-- 降级态角标（精修 §3.2.1）：forecast.degraded 时图表右上角提示 -->
    <el-tag
      v-if="forecast?.degraded"
      type="warning" size="small" effect="dark"
      class="degraded-tag"
    >降级预测（数据延迟）</el-tag>
    <div ref="el" class="chart-box" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ForecastData, SeriesData, StationThresholds } from '@/types'
import { useEcharts } from '@/composables/useEcharts'

const props = defineProps<{
  series: SeriesData | null
  forecast: ForecastData | null
}>()

const el = ref<HTMLElement>()
const { setOption } = useEcharts(el)

const TH_COLOR: Record<string, string> = {
  blue: '#2196f3', yellow: '#ffc107', orange: '#ff9800', red: '#f44336',
}
const TH_SHORT: Record<string, string> = {
  blue: '蓝', yellow: '黄', orange: '橙', red: '红',
}

watch(
  () => [props.series, props.forecast],
  () => render(),
  { deep: true },
)

/** 预测曲线首次越过阈值的位置（触发点标记，精修 §3.2.1） */
function thresholdCrossings(fc: ForecastData, th: Partial<StationThresholds>) {
  const marks: Array<{ level: string; value: number; index: number }> = []
  const seen = new Set<string>()
  fc.points.forEach((p, i) => {
    for (const k of ['yellow', 'orange', 'red', 'blue'] as const) {
      const v = th[k]
      if (v == null || seen.has(k)) continue
      if (p.level >= v) {
        seen.add(k)
        marks.push({ level: k, value: p.level, index: i + 1 }) // +1：join 头部占位
      }
    }
  })
  return marks
}

function render() {
  if (!props.series) return
  const s = props.series
  const th = s.thresholds ?? {}
  const histX = s.points.map((p) => p.ts.slice(5, 16).replace('T', ' '))
  const histY = s.points.map((p) => p.level)
  const rainY = s.points.map((p) => p.rain_observed)

  const fc = props.forecast
  const fcX = fc ? fc.points.map((p) => p.t.slice(5, 16).replace('T', ' ')) : []
  // 历史尾部一个点接到预测曲线，视觉连续
  const joinX = histX.length ? [histX[histX.length - 1], ...fcX] : fcX
  const joinRaw = fc ? [histY[histY.length - 1] ?? null, ...fc.points.map((p) => p.level_raw)] : []
  const joinCorr = fc ? [histY[histY.length - 1] ?? null, ...fc.points.map((p) => p.level)] : []
  const joinLower = fc ? [null, ...fc.points.map((p) => p.lower)] : []
  const bandDelta = fc
    ? [null, ...fc.points.map((p) => +(p.upper - p.lower).toFixed(4))]
    : []

  const markLines = (['blue', 'yellow', 'orange', 'red'] as const)
    .filter((k) => th[k] != null)
    .map((k) => ({
      yAxis: th[k],
      name: th[k],
      lineStyle: { color: TH_COLOR[k], type: 'solid' as const, width: 1 },
      label: {
        // 精修 §3.2.1：简短格式减少遮挡
        formatter: `${TH_SHORT[k]} ${th[k]}`,
        position: 'insideEndTop' as const,
        color: TH_COLOR[k],
        fontSize: 10,
      },
    }))

  // 超线触发点：修正后预测曲线越过阈值处加等级色圆点
  const markPoints = fc
    ? thresholdCrossings(fc, th).map((m) => ({
        coord: [joinX[m.index], m.value],
        value: `${TH_SHORT[m.level]}触发`,
        itemStyle: { color: TH_COLOR[m.level] },
        label: {
          show: true,
          formatter: '{c}',
          fontSize: 10,
          color: TH_COLOR[m.level],
          position: 'top' as const,
        },
      }))
    : []

  setOption({
    grid: [{ left: 52, right: 24, top: 40, bottom: 62 }],
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: {
      // 精修 §3.2.1：图例按叙事顺序 历史水位 → 降雨量 → 原始预测 → 修正后预测 → 置信区间
      top: 4,
      data: ['历史水位', '降雨量(mm)', '原始预测', '修正后预测', '置信区间'],
    },
    xAxis: {
      type: 'category',
      data: [...joinX],
      boundaryGap: false,
      axisLabel: { fontSize: 10, interval: Math.max(0, Math.floor(joinX.length / 12)) },
    },
    yAxis: [
      { type: 'value', name: '水位 (m)', scale: true },
      { type: 'value', name: '雨量 (mm/5min)', max: (v: number) => Math.max(10, v * 1.4), splitLine: { show: false } },
    ],
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
    series: [
      {
        name: '降雨量(mm)', type: 'bar', yAxisIndex: 1, data: rainY,
        itemStyle: { color: 'rgba(33,150,243,0.35)' }, barWidth: '40%', silent: true,
      },
      {
        name: '历史水位', type: 'line', data: [...histY, ...fcX.map(() => null)],
        showSymbol: false, lineStyle: { color: '#1E6FA8', width: 2 },
        itemStyle: { color: '#1E6FA8' },
        markLine: { silent: true, symbol: 'none', data: markLines },
      },
      {
        // 原始预测 = 品牌蓝 1.5px 虚线（模型初值，精修 §2.1 硬规则）
        name: '原始预测', type: 'line', data: joinRaw.map((v, i) => (i === 0 ? null : v)),
        showSymbol: false, lineStyle: { color: '#1E6FA8', width: 1.5, type: 'dashed' },
        itemStyle: { color: '#1E6FA8' },
      },
      {
        name: '置信区间下界', type: 'line', data: joinLower, stack: 'ci',
        showSymbol: false, lineStyle: { opacity: 0 }, tooltip: { show: false }, silent: true,
      },
      {
        // 置信区间带 = 品牌蓝 8% 渐变带
        name: '置信区间', type: 'line', data: bandDelta, stack: 'ci',
        showSymbol: false, lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(30,111,168,0.08)' }, tooltip: { show: false }, silent: true,
      },
      {
        // 修正后预测 = 橙色 2.5px 实线（最终建议，视觉最重）
        name: '修正后预测', type: 'line', data: joinCorr.map((v, i) => (i === 0 ? null : v)),
        showSymbol: false, lineStyle: { color: '#FF9800', width: 2.5, type: 'solid' },
        itemStyle: { color: '#FF9800' },
        markPoint: markPoints.length
          ? { symbol: 'circle', symbolSize: 9, data: markPoints }
          : undefined,
      },
    ],
  })
}

defineExpose({ render })
</script>

<style scoped>
.chart-wrap-box { position: relative; }
.degraded-tag {
  position: absolute;
  right: 8px;
  top: 8px;
  z-index: 5;
}
</style>

<template>
  <el-descriptions :column="4" border size="small" class="summary">
    <el-descriptions-item label="预测峰值">
      <b>{{ forecast?.peak_level?.toFixed(2) ?? '—' }}</b> m
    </el-descriptions-item>
    <el-descriptions-item label="峰值时间">
      {{ forecast?.peak_time?.slice(5, 16).replace('T', ' ') ?? '—' }}
    </el-descriptions-item>
    <el-descriptions-item label="置信区间">
      {{ forecast?.confidence_interval ? `${forecast.confidence_interval.lower.toFixed(2)} ~ ${forecast.confidence_interval.upper.toFixed(2)} m` : '—' }}
    </el-descriptions-item>
    <el-descriptions-item label="预见期">
      {{ forecast?.lead_hours ?? leadHours }}h
      <el-tag v-if="forecast && forecast.lead_hours >= 6" type="warning" size="small" effect="plain">参考级</el-tag>
    </el-descriptions-item>
  </el-descriptions>
</template>

<script setup lang="ts">
import type { ForecastData } from '@/types'

defineProps<{ forecast: ForecastData | null; leadHours: number }>()
</script>

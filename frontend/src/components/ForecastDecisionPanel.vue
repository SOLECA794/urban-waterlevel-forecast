<template>
  <el-card shadow="never" class="panel">
    <template #header>
      <span>Agent-A 编排决策</span>
      <el-tag size="small" type="success" effect="plain" style="margin-left: 8px">规则驱动 · 无需 LLM · 全程可追溯</el-tag>
      <div v-if="hint" class="muted hint">{{ hint }}</div>
    </template>
    <template v-if="decision">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="D1 模型选择">
          <!-- 评审 P1-5：D1 必须显示实际执行模型；降级时红色标注，不与横幅矛盾 -->
          <el-tag v-if="decision.degraded" size="small" type="danger" effect="dark">
            {{ decision.selected_model }} · 已降级
          </el-tag>
          <el-tag v-else size="small">{{ decision.selected_model }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="D5 降级">
          <el-tag :type="decision.degraded ? 'danger' : 'success'" size="small" effect="plain">
            {{ decision.degraded ? '已降级（数据延迟）' : '正常' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="D2 多源融合权重">
          水位 {{ w.level }} · 降雨 {{ w.rain }} · 预报 {{ w.fcst }}
        </el-descriptions-item>
        <el-descriptions-item label="D3 修正强度 α">
          {{ decision.revision_alpha }}
        </el-descriptions-item>
        <el-descriptions-item label="D4 置信区间系数" :span="2">
          ×{{ decision.ci_scale }}（宽度 ∝ 近期RMSE × √h）
        </el-descriptions-item>
      </el-descriptions>
      <div class="reason muted">决策理由：{{ decision.reason }}</div>
    </template>
    <el-empty v-else description="本次预测无编排决策记录" :image-size="60" />
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DecisionInfo } from '@/types'

const props = defineProps<{ decision: DecisionInfo | null; hint?: string }>()
const w = computed(() => props.decision?.fusion_weights ?? { level: '—', rain: '—', fcst: '—' })
</script>

<style scoped>
.panel { margin-top: 0; }
.reason { margin-top: 10px; line-height: 1.8; }
.hint { margin-top: 2px; font-weight: 400; }
</style>

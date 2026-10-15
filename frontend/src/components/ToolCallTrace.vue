<template>
  <el-card shadow="never" class="trace">
    <template #header>
      <span>工具调用轨迹</span>
      <span class="muted" style="margin-left: 8px">agent_tool_call 审计日志</span>
    </template>
    <el-empty v-if="!traces.length" description="暂无工具调用（发起对话后显示审计轨迹）" :image-size="60" />
    <el-timeline v-else>
      <el-timeline-item
        v-for="t in traces"
        :key="t.call_id"
        :type="t.success ? 'success' : 'danger'"
        :timestamp="`${t.create_time?.slice(11, 19) ?? ''} · ${t.latency_ms}ms`"
      >
        <div class="line">
          <el-tag size="small" :type="riskType(t.risk_level)" effect="plain">{{ t.risk_level }}</el-tag>
          <code class="tool">{{ t.tool_name }}</code>
        </div>
        <div class="muted args">参数：{{ JSON.stringify(t.args) }}</div>
        <div class="muted">结果：{{ t.result_summary?.slice(0, 120) }}</div>
      </el-timeline-item>
    </el-timeline>
  </el-card>
</template>

<script setup lang="ts">
import type { ToolCallTrace } from '@/types'

defineProps<{ traces: ToolCallTrace[] }>()

function riskType(level: string) {
  return level === 'L2' ? 'warning' : level === 'L1' ? 'primary' : 'info'
}
</script>

<style scoped>
.trace { height: 100%; overflow: auto; }
.line { display: flex; gap: 6px; align-items: center; }
.tool { font-weight: 600; }
.args { word-break: break-all; }
</style>

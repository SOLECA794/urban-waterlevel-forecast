<template>
  <div v-if="latest" class="sit-banner" :class="tone">
    <div class="icon">{{ tone === 'danger' ? '🚨' : tone === 'warn' ? '⚠️' : '🛡️' }}</div>
    <div class="body">
      <div class="head">
        <span class="agent-tag">Agent 值班</span>
        <span class="time">{{ fmt(latest.create_time) }}</span>
      </div>
      <div class="text" v-html="rendered"></div>
    </div>
    <div class="actions">
      <el-button size="small" text @click="refresh" :loading="loading">刷新</el-button>
      <el-button size="small" type="primary" plain @click="goAgent">值班台 →</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getRecentPatrols, type PatrolItem } from '@/api/endpoints'

const router = useRouter()
const latest = ref<PatrolItem | null>(null)
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    const items = await getRecentPatrols(1)
    latest.value = items[0] ?? null
  } catch { /* 首屏无巡检属正常 */ } finally {
    loading.value = false
  }
}

const rendered = computed(() => {
  if (!latest.value) return ''
  return latest.value.content
    .replace(/</g, '&lt;')
    .replace(/\n/g, '<br/>')
    .replace(/【自动巡检.*?】/g, '')
    .replace(/⚠/g, '<b style="color:#f44336">⚠</b>')
})

const tone = computed(() => {
  const t = latest.value?.content ?? ''
  if (t.includes('橙色') || t.includes('红色')) return 'danger'
  if (t.includes('黄色') || t.includes('重点关注') || t.includes('接近黄色')) return 'warn'
  return 'ok'
})

function goAgent() { router.push('/agent') }
function fmt(ts: string) { return ts ? ts.replace('T', ' ').slice(11, 16) : '' }

onMounted(refresh)
</script>

<style scoped>
.sit-banner {
  display: flex; gap: 14px; align-items: flex-start;
  padding: 14px 18px; border-radius: 8px; margin-bottom: 14px;
  border: 1px solid var(--line); background: #fff;
}
.sit-banner.ok { border-left: 4px solid var(--status-ok); background: #f4faf5; }
.sit-banner.warn { border-left: 4px solid var(--alert-yellow); background: #fffbe6; }
.sit-banner.danger { border-left: 4px solid var(--status-error); background: #fff1f0; }
.icon { font-size: 22px; line-height: 1; padding-top: 2px; }
.body { flex: 1; }
.head { display: flex; gap: 10px; align-items: center; margin-bottom: 4px; }
.agent-tag {
  font-size: 11px; font-weight: 600; color: #fff;
  background: var(--brand); padding: 1px 8px; border-radius: 10px;
}
.time { font-size: 11px; color: #999; }
.text { font-size: 13px; line-height: 1.7; color: var(--text-main); }
.actions { display: flex; flex-direction: column; gap: 4px; }
</style>

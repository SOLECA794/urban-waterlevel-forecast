<template>
  <div class="agent-page">
    <!-- 左：会话列表 + 工具分组 -->
    <div class="pane sessions">
      <div class="pane-head">
        <span>会话</span>
        <el-button size="small" @click="newSession">新建</el-button>
      </div>
      <div class="muted pad">当前会话：<code>{{ store.sessionId }}</code></div>
      <div class="muted pad">
        本页演示完整链路：提问 → EchoAgent 关键词匹配 → 工具执行 → 回答 + 轨迹。
        <br />后端 EchoAgent 为占位实现（EXT-POINT(AGENT)），接入 LLM 后本页无需改动。
      </div>
      <div class="pad tools">
        <div v-for="g in groupedTools" :key="g.level" class="tool-group">
          <div class="group-head">
            <el-tag size="small" :type="riskType(g.level)" effect="plain">{{ g.level }}</el-tag>
            {{ g.label }}
          </div>
          <div class="tags">
            <el-tag v-for="t in g.items" :key="t.name" size="small" effect="plain">
              <code>{{ t.name }}</code>
            </el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- 中：值班播报 + 消息流 -->
    <div class="pane chat">
      <div class="pane-head">
        <span>值班台</span>
        <el-button size="small" text @click="loadPatrols" :loading="patrolLoading">刷新巡检</el-button>
      </div>

      <!-- Agent 主动巡检播报（最上面，进入页面第一眼看到） -->
      <div class="patrol-strip">
        <div v-if="!patrols.length" class="muted pad small">暂无巡检记录（等待下一轮滚动预测自动生成）</div>
        <div v-for="p in patrols.slice(0, 3)" :key="p.message_id" class="patrol-item">
          <div class="ptime">🤖 {{ fmt(p.create_time) }}</div>
          <div class="ptext" v-html="p.content.replace(/</g,'&lt;').replace(/\n/g,'<br/>')"></div>
        </div>
      </div>

      <div class="msgs" ref="msgBox">
        <div v-if="!store.messages.length" class="chips pad">
          <div class="muted" style="margin-bottom: 8px">试试点击示例问题（填入输入框，可编辑后发送）：</div>
          <el-tag
            v-for="q in sampleQuestions"
            :key="q" class="chip" effect="plain"
            @click="draft = q"
          >{{ q }}</el-tag>
        </div>
        <div v-for="(m, i) in store.messages" :key="i" class="msg" :class="m.role">
          <div class="bubble">{{ m.content }}</div>
        </div>
      </div>
      <div class="input-row">
        <el-input
          v-model="draft"
          placeholder="输入问题（关键词匹配工具）"
          @keyup.enter="send"
          :disabled="store.sending"
        />
        <el-input v-model="confirmToken" placeholder="可选" style="width: 140px">
          <template #prepend>L2 令牌</template>
        </el-input>
        <el-button type="primary" :loading="store.sending" @click="send">发送</el-button>
      </div>
      <div class="muted pad small">
        SSE 流式接收已就绪（useSSE）；后端流式接口为预留（EXT-POINT(INTEGRATION)），当前一次性返回。
      </div>
    </div>

    <!-- 右：工具调用轨迹 -->
    <div class="pane trace-pane">
      <ToolCallTrace :traces="store.traces" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listTools, sendAgentMessage, getRecentPatrols, type PatrolItem } from '@/api/endpoints'
import { BizError } from '@/api/client'
import ToolCallTrace from '@/components/ToolCallTrace.vue'
import { useAgentStore } from '@/stores/useAgentStore'

const store = useAgentStore()
const draft = ref('')
const confirmToken = ref('')
const tools = ref<{ name: string; risk_level: string }[]>([])
const msgBox = ref<HTMLElement>()
const patrols = ref<PatrolItem[]>([])
const patrolLoading = ref(false)

const sampleQuestions = ['查看当前预警', 'S001 预测 3h', '为什么选这个模型', '校准参数', '生成报告']

const groupedTools = computed(() => {
  const defs = [
    { level: 'L0', label: '只读工具（无副作用）' },
    { level: 'L1', label: '生成工具（产出内容草稿）' },
    { level: 'L2', label: '需确认工具（变更须人工令牌）' },
  ]
  return defs
    .map((d) => ({ ...d, items: tools.value.filter((t) => t.risk_level === d.level) }))
    .filter((g) => g.items.length)
})

function riskType(level: string) {
  return level === 'L2' ? 'warning' : level === 'L1' ? 'primary' : 'info'
}

function newSession() {
  store.sessionId = `web-${Math.random().toString(36).slice(2, 8)}`
  store.messages.length = 0
  store.traces.length = 0
  ElMessage.success(`已新建会话 ${store.sessionId}`)
}

async function loadPatrols() {
  patrolLoading.value = true
  try { patrols.value = await getRecentPatrols(5) } catch { /* 忽略 */ }
  finally { patrolLoading.value = false }
}

async function send() {
  const text = draft.value.trim()
  if (!text) return
  store.push('user', text)
  draft.value = ''
  store.sending = true
  try {
    const reply = await sendAgentMessage(store.sessionId, text, confirmToken.value || undefined)
    store.applyReply(reply)
  } catch (e) {
    if (e instanceof BizError) {
      store.push('assistant', `执行失败（code ${e.code}）：${e.message}`)
    } else throw e
  } finally {
    store.sending = false
    await nextTick()
    msgBox.value?.scrollTo({ top: msgBox.value.scrollHeight })
  }
}

function fmt(ts: string) { return ts ? ts.replace('T', ' ').slice(5, 16) : '' }

onMounted(async () => {
  tools.value = await listTools()
  await loadPatrols()
})
</script>

<style scoped>
.agent-page { display: flex; gap: 16px; padding: 16px 20px; height: calc(100vh - 56px); }
.pane { background: #fff; border-radius: 6px; border: 1px solid var(--line); display: flex; flex-direction: column; overflow: hidden; }
.sessions { width: 250px; flex-shrink: 0; }
.chat { flex: 1.4; }
.trace-pane { flex: 1; overflow: auto; }
.pane-head { padding: 12px 14px; font-weight: 600; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center; }
.pad { padding: 8px 14px; }
.small { font-size: 11px; }
.tools { overflow: auto; }
.patrol-strip { border-bottom: 2px solid var(--brand-light); background: #f4f9ff; max-height: 220px; overflow: auto; }
.patrol-item { padding: 10px 14px; border-bottom: 1px dashed #d0e3f5; }
.ptime { font-size: 11px; color: var(--brand); margin-bottom: 4px; font-weight: 600; }
.ptext { font-size: 13px; line-height: 1.6; color: var(--text-main); white-space: pre-wrap; }
.msgs { flex: 1; overflow: auto; padding: 10px 14px; }
.msg { display: flex; margin-bottom: 10px; }
.msg.user { justify-content: flex-end; }
.bubble { max-width: 78%; padding: 8px 12px; border-radius: 8px; background: #fff; border: 1px solid var(--brand); white-space: pre-wrap; font-size: 13px; line-height: 1.6; }
.msg.user .bubble { background: var(--brand-light); border-color: var(--brand-light); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { cursor: pointer; }
.chip:hover { color: var(--brand-dark); border-color: var(--brand); }
.input-row { display: flex; gap: 8px; padding: 10px 14px; border-top: 1px solid var(--line); }
</style>

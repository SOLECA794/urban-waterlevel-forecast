import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AgentReply, ToolCallTrace } from '@/types'

/** Agent 会话状态（跨页面共享；SSE 流式累积预留，V1.2 §3.1） */
export const useAgentStore = defineStore('agent', () => {
  const sessionId = ref<string>(`web-${Math.random().toString(36).slice(2, 8)}`)
  const messages = ref<{ role: 'user' | 'assistant'; content: string }[]>([])
  const traces = ref<ToolCallTrace[]>([])
  const sending = ref(false)

  function push(role: 'user' | 'assistant', content: string) {
    messages.value.push({ role, content })
  }

  function applyReply(reply: AgentReply) {
    push('assistant', reply.answer)
    if (reply.tool_calls?.length) {
      traces.value = [...reply.tool_calls, ...traces.value]
    }
  }

  return { sessionId, messages, traces, sending, push, applyReply }
})

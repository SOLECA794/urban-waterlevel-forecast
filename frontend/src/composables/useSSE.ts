/** SSE 流式接收（预留，06 §2）：Agent token 流 / 预警事件推送。
 *
 * 本期后端 /stream/alerts 为预留（EXT-POINT(INTEGRATION)），收到 reserved 事件
 * 自动关闭并降级为轮询——调用方无需感知。
 */
import { onBeforeUnmount } from 'vue'

export function useSSE(path: string, onEvent: (data: any) => void) {
  let es: EventSource | undefined

  function connect() {
    if (typeof window === 'undefined' || !('EventSource' in window)) return
    es = new EventSource(`/api/v1${path}`)
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data?.type === 'reserved') {
          // 预留通道：静默降级为轮询
          es?.close()
          return
        }
        onEvent(data)
      } catch {
        /* 忽略非 JSON 帧 */
      }
    }
    es.onerror = () => es?.close()
  }

  onBeforeUnmount(() => es?.close())
  return { connect, close: () => es?.close() }
}

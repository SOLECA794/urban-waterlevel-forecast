/** 轮询 composable：页面隐藏时暂停（usePolling，06 §5.2）。 */
import { onBeforeUnmount, onMounted } from 'vue'

export function usePolling(fn: () => void | Promise<void>, intervalMs = 30_000) {
  let timer: number | undefined

  const tick = () => {
    if (document.hidden) return
    void fn()
  }

  onMounted(() => {
    void fn()
    timer = window.setInterval(tick, intervalMs)
    document.addEventListener('visibilitychange', tick)
  })

  onBeforeUnmount(() => {
    if (timer) window.clearInterval(timer)
    document.removeEventListener('visibilitychange', tick)
  })
}

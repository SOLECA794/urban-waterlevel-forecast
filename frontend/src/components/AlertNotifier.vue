<template><div></div></template>

<script setup lang="ts">
/**
 * 全局预警联动通知器（分析模式3：达到预警条件时联动消息渠道）。
 * 轮询 active alerts，发现新 alert_id 即右上角弹窗，点击跳转告警中心。
 */
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { ElNotification } from 'element-plus'
import { listAlerts, type AlertItem } from '@/api/endpoints'
import { useRouter } from 'vue-router'

const router = useRouter()
const seenIds = ref<Set<number>>(new Set())
let timer: any = null

const LEVEL_TYPE: Record<string, string> = {
  red: 'error', orange: 'warning', yellow: 'warning', blue: 'info',
}
const LEVEL_NAME: Record<string, string> = {
  red: '红色', orange: '橙色', yellow: '黄色', blue: '蓝色',
}

async function poll() {
  try {
    const page = await listAlerts({ status: 'active' })
    const items: AlertItem[] = page.items || []
    for (const a of items) {
      if (seenIds.value.has(a.alert_id)) continue
      seenIds.value.add(a.alert_id)
      // 首次加载不弹窗（只记录），后续新增才弹
      if (seenIds.value.size <= items.length && !seenIdsHasAll(items)) continue
      ElNotification({
        title: `【${LEVEL_NAME[a.level] || a.level}】内涝预警`,
        message: `${a.station_name || ('站点#' + a.station_id)}：${a.reason || '水位超阈值'}`,
        type: (LEVEL_TYPE[a.level] as any) || 'info',
        duration: 8000,
        position: 'top-right',
        onClick: () => router.push('/alerts'),
      })
    }
  } catch { /* 静默 */ }
}

function seenIdsHasAll(items: AlertItem[]) {
  return items.every((i) => seenIds.value.has(i.alert_id))
}

onMounted(async () => {
  await poll()
  timer = setInterval(poll, 15000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

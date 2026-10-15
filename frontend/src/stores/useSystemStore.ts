import { defineStore } from 'pinia'
import type { HealthData } from '@/types'

/** 全局系统状态：降级横幅 / mock 通道标记 / 健康三态缓存（含数据新鲜度，评审 R2） */
export const useSystemStore = defineStore('system', {
  state: () => ({
    degraded: false,      // 后端不可用（FR-5.5）
    mockMode: false,      // 当前数据来自 mock
    health: null as null | HealthData,
  }),
})

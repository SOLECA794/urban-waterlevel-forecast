import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listAlerts, type AlertItem } from '@/api/endpoints'

export const useAlertStore = defineStore('alert', () => {
  const alerts = ref<AlertItem[]>([])
  const loading = ref(false)

  async function refresh(filters: Record<string, any> = {}) {
    loading.value = true
    try {
      const page = await listAlerts(filters)
      alerts.value = page.items
    } finally {
      loading.value = false
    }
  }

  return { alerts, loading, refresh }
})

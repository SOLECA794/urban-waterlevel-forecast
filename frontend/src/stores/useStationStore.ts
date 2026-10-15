import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAlertStats, getStations, type AlertStatsGlobal, type StationItem } from '@/api/endpoints'

export const useStationStore = defineStore('station', () => {
  const stations = ref<StationItem[]>([])
  const stats = ref<AlertStatsGlobal | null>(null)
  const loading = ref(false)

  async function refresh() {
    loading.value = true
    try {
      stations.value = await getStations()
      stats.value = await getAlertStats()
    } finally {
      loading.value = false
    }
  }

  return { stations, stats, loading, refresh }
})

/** ECharts 组合式封装：初始化 / setOption / 自适应 / 销毁。 */
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, type Ref } from 'vue'

export function useEcharts(el: Ref<HTMLElement | undefined>) {
  let chart: echarts.ECharts | undefined

  onMounted(() => {
    if (el.value) {
      chart = echarts.init(el.value)
      window.addEventListener('resize', resize)
    }
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', resize)
    chart?.dispose()
  })

  function resize() {
    chart?.resize()
  }

  function setOption(option: echarts.EChartsCoreOption, notMerge = true) {
    if (!chart && el.value) chart = echarts.init(el.value)
    chart?.setOption(option, notMerge)
  }

  return { setOption, resize, chart: () => chart }
}

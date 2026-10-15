/** Mock 通道开关与请求路由：路径与真实 API 一一对应（VITE_USE_MOCK，FR-5.7）。 */
import type {
  AgentReply, AlertItem, CalibrateResult, ForecastBrief, ForecastData,
  HealthData, ModelItem, PageData, SeriesData, StationDetail, StationItem,
  ToolItem, AlertStatsGlobal, AgentSessionItem, ToolCallTrace,
} from '@/types'
import {
  calibrateResultOf, genAlerts, genForecast, genSeries, mockAgentReply,
  mockForecastBriefs, mockHealth, mockModels, mockStats, mockTools,
  pageOf, stationDetailOf, stationItems,
} from './fixtures'

export const USE_MOCK = String(import.meta.env.VITE_USE_MOCK ?? 'false') === 'true'

export interface MockRequest {
  path: string
  method?: string
  query?: Record<string, any>
  body?: any
}

/** 与后端 /api/v1 同构的 mock 路由；未匹配返回 undefined → 上层报错。 */
export function handleMock<T>(req: MockRequest): T {
  const { path, method = 'GET', query = {}, body = {} } = req
  const seg = path.replace(/^\/+/, '').split('/')
  const num = (v: any, d: number) => (v === undefined || v === '' ? d : Number(v))

  // health
  if (path === '/health') return mockHealth as T

  // stations
  if (path === '/stations' && method === 'GET') return stationItems() as T
  if (path === '/stations' && method === 'POST') return stationDetailOf(1) as T
  if (seg[0] === 'stations' && seg[1] && !seg[2]) return stationDetailOf(Number(seg[1])) as T
  if (seg[0] === 'stations' && seg[2] === 'series') {
    return genSeries(Number(seg[1]), num(query.hours, 6)) as T
  }
  if (seg[0] === 'stations' && seg[2] === 'alert') {
    const it = stationItems().find((s) => s.station_id === Number(seg[1]))!
    return { station_id: Number(seg[1]), current_level: it.current.level, alert: it.alert, thresholds: it.thresholds } as T
  }
  if (seg[0] === 'stations' && seg[2] === 'alerts') {
    const sid = Number(seg[1])
    const rows = genAlerts().filter((a) => a.station_id === sid)
    return pageOf(rows, num(query.page, 1), num(query.page_size, 20)) as unknown as T
  }
  if (seg[0] === 'stations' && seg[2] === 'forecasts') {
    const rows = mockForecastBriefs().filter((f) => f.station_id === Number(seg[1]))
    return pageOf(rows, num(query.page, 1), num(query.page_size, 10)) as unknown as T
  }
  if (seg[0] === 'stations' && seg[2] === 'predict') {
    return genForecast(Number(seg[1]), num(body.lead_hours, 1), 'linear_response') as T
  }

  // alerts
  if (path === '/alerts') {
    let rows: AlertItem[] = genAlerts()
    if (query.status) rows = rows.filter((a) => a.status === query.status)
    if (query.level) rows = rows.filter((a) => a.level === query.level)
    if (query.is_reference !== undefined && query.is_reference !== '') {
      const want = String(query.is_reference) === 'true'
      rows = rows.filter((a) => a.is_reference === want)
    }
    return pageOf(rows, num(query.page, 1), num(query.page_size, 20)) as unknown as T
  }
  if (path === '/alerts/stats') return mockStats as T
  // 评审 P2-9：发布记录（mock 通道与真实接口同构）
  if (path === '/alerts/publish-records') {
    const rows = genAlerts().slice(0, num(query.limit, 50))
    const items = rows.flatMap((a, idx) => {
      const base = (a.alert_id ?? idx + 1) * 10
      return [
        { record_id: `PB${base + 1}`, alert_id: a.alert_id, station_name: a.station_name, level: a.level, channel: '站内消息', channel_code: 'IN_APP', status: 'sent', detail: `已向防汛值班群推送预警：${a.station_name}`, publish_time: a.alert_time },
        { record_id: `PB${base + 2}`, alert_id: a.alert_id, station_name: a.station_name, level: a.level, channel: '信息屏', channel_code: 'INFO_SCREEN', status: 'simulated', detail: `路段信息屏文案已模拟下发（mock）：${a.station_name}`, publish_time: a.alert_time },
        { record_id: `PB${base + 3}`, alert_id: a.alert_id, station_name: a.station_name, level: a.level, channel: '短信', channel_code: 'SMS', status: 'placeholder', detail: 'EXT-POINT(INTEGRATION)：短信网关未接入，发布留白占位', publish_time: a.alert_time },
      ]
    })
    return { items, total: items.length, note: '（mock）站内消息/信息屏为演示通道；短信为真实渠道占位（EXT-POINT(INTEGRATION)）' } as T
  }

  // 评审 P1-7：模拟事件注入（mock 通道）
  if (path === '/sim/events' && method === 'POST') {
    if (body?.demo_key !== 'FANGXUN-DEMO') throw new Error('演示钥匙不正确')
    return {
      event_id: `RAIN-${Date.now() % 10000}`, station_id: body?.station_id ?? 1,
      intensity: body?.intensity ?? 'extreme', intensity_label: '极端暴雨',
      peak_mm_per_step: 12, duration_minutes: 120,
      start_ts: new Date().toISOString(), end_ts: new Date(Date.now() + 120 * 60000).toISOString(),
      injected_at: new Date().toISOString(), note: '（mock）事件已注入', prediction_triggered: true,
    } as T
  }
  if (path === '/sim/events') return [] as T

  // forecasts
  if (path === '/forecasts') return pageOf(mockForecastBriefs(), num(query.page, 1), num(query.page_size, 10)) as unknown as T
  if (seg[0] === 'forecasts' && seg[2] === 'decision') {
    const f = genForecast(1, 3)
    return { forecast_id: Number(seg[1]), decision_id: 1, ...f.decision, create_time: f.predict_time } as T
  }

  // models
  if (path === '/models') return mockModels as T
  if (seg[0] === 'models' && seg[2] === 'activate') {
    const m = mockModels.find((x) => x.model_id === Number(seg[1]))!
    mockModels.forEach((x) => (x.active = false))
    m.active = true
    return { model_id: m.model_id, model_type: m.model_type, version: m.version, active: true, note: '（mock）模型已切换' } as T
  }
  if (seg[0] === 'models' && seg[2] === 'calibrate-params') {
    return calibrateResultOf(Number(seg[1]), num(query.station_id, 1)) as T
  }

  // calibrations（重训占位）
  if (path === '/calibrations' && method === 'POST') {
    return { calibration_id: 1, task_type: 'model_retrain', status: 'pending', created_at: new Date().toISOString(), note: '（mock）占位' } as T
  }
  if (seg[0] === 'calibrations' && seg[1]) {
    return { calibration_id: Number(seg[1]), task_type: 'model_retrain', status: 'pending', created_at: new Date().toISOString() } as T
  }

  // tools / agent
  if (path === '/tools') return mockTools as T
  if (path === '/agent/sessions') return [] as T
  if (seg[0] === 'agent' && seg[1] === 'sessions' && seg[3] === 'messages' && method === 'POST') {
    return mockAgentReply(seg[2], body.message ?? '') as T
  }
  if (seg[0] === 'agent' && seg[1] === 'sessions' && seg[3] === 'tool-calls') {
    return [] as unknown as T
  }
  if (seg[0] === 'agent' && seg[1] === 'sessions' && seg[3] === 'messages') {
    return [] as unknown as T
  }

  throw new Error(`mock 未覆盖的请求：${method} /api/v1${path}`)
}

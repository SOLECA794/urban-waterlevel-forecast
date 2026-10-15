/** Mock 数据形状与后端契约完全一致（06 §7）。
 *
 * 场景覆盖：正常 / 多等级预警（含橙色）/ 参考级预警（6h/12h）/ 数据源断流 /
 * 协同修正双曲线 / Agent-A 决策（权重随数据质量变化）。
 */
import type {
  AgentReply, AlertItem, AlertStatsGlobal, CalibrateResult, ForecastBrief,
  ForecastData, HealthData, ModelItem, PageData, SeriesData, StationDetail,
  StationItem, ToolCallTrace, ToolItem,
} from '@/types'

const now = () => new Date()
const iso = (d: Date) => d.toISOString().slice(0, 19)
const minsAgo = (m: number) => iso(new Date(now().getTime() - m * 60000))
const minsLater = (m: number) => iso(new Date(now().getTime() + m * 60000))

interface MockStation {
  id: number; code: string; name: string; loc: string; kind: string
  th: [number, number, number, number]; base: number; cur: number; alert: string | null
}

const ST: MockStation[] = [
  { id: 1, code: 'S001', name: '站前路低洼段', loc: '站前路与建设大街交叉口', kind: 'low-lying', th: [1.6, 1.9, 2.2, 2.5], base: 1.2, cur: 2.08, alert: 'orange' },
  { id: 2, code: 'S002', name: '建设路下穿隧道', loc: '建设路铁路下穿', kind: 'low-lying', th: [1.5, 1.8, 2.1, 2.4], base: 1.0, cur: 1.9, alert: 'yellow' },
  { id: 3, code: 'S003', name: '城东河河道断面', loc: '城东河桥上游200m', kind: 'river', th: [2.0, 2.4, 2.8, 3.2], base: 1.6, cur: 1.96, alert: 'blue' },
  { id: 4, code: 'S004', name: '老城十字街', loc: '老城区中山路十字街口', kind: 'low-lying', th: [1.7, 2.0, 2.3, 2.6], base: 1.3, cur: 1.42, alert: null },
  { id: 5, code: 'S005', name: '新区主干道', loc: '高新区创新大道', kind: 'road', th: [1.8, 2.2, 2.6, 3.0], base: 1.4, cur: 1.51, alert: null },
  { id: 6, code: 'S006', name: '工业园区雨水泵站', loc: '工业园区纬三路泵站', kind: 'pump', th: [1.9, 2.3, 2.7, 3.1], base: 1.5, cur: 1.86, alert: 'blue' },
]

const rankOf = (lv: string | null) =>
  lv === 'red' ? 4 : lv === 'orange' ? 3 : lv === 'yellow' ? 2 : lv === 'blue' ? 1 : 0

export function stationItems(): StationItem[] {
  return ST.map((s) => ({
    station_id: s.id, station_code: s.code, station_name: s.name, location: s.loc,
    kind: s.kind, enabled: true,
    thresholds: { blue: s.th[0], yellow: s.th[1], orange: s.th[2], red: s.th[3] },
    current: { level: s.cur, ts: minsAgo(1), rain_observed: 0.8, data_age_min: 1 },
    alert: {
      rank: rankOf(s.alert), level: s.alert,
      alert_id: s.alert ? s.id : null,
      reason: s.alert
        ? `预测峰值 ${(s.cur + 0.12).toFixed(2)} m 超过${({ blue: '蓝', yellow: '黄', orange: '橙', red: '红' } as any)[s.alert]}色阈值（mock）`
        : null,
      is_reference: false,
      lead_minutes_advantage: s.alert ? 42 : null,
    },
  })).sort((a, b) => b.alert.rank - a.alert.rank || a.station_id - b.station_id)
}

export function genSeries(id: number, hours = 6): SeriesData {
  const st = ST.find((x) => x.id === id) ?? ST[0]
  const step = 5
  const n = (hours * 60) / step
  const pts = []
  let lvl = st.base + (st.cur - st.base) * 0.55
  for (let i = n; i >= 0; i--) {
    const t = new Date(now().getTime() - i * step * 60000)
    const storm = Math.max(0, 1 - Math.abs((n - i - n * 0.72) / (n * 0.18))) // 峰值在 ~72% 处
    const rain = +(storm > 0.6 ? storm * 9 : 0.2).toFixed(2)
    lvl = lvl + 0.006 * rain - 0.006 * (lvl - st.base)
    pts.push({
      ts: iso(t),
      level: +lvl.toFixed(3),
      rain_observed: rain,
    })
  }
  return {
    station_id: id, station_code: st.code, step_minutes: step,
    thresholds: { blue: st.th[0], yellow: st.th[1], orange: st.th[2], red: st.th[3] },
    points: pts,
  }
}

export function genForecast(id: number, lead: number, model = 'linear_response'): ForecastData {
  const st = ST.find((x) => x.id === id) ?? ST[0]
  const n = lead * 12
  const points = []
  let lvl = st.cur
  let peak = lvl; let peakAt = minsLater(5)
  for (let k = 1; k <= n; k++) {
    const rainFc = k > 18 && k < 42 ? 6.5 : 0.3 // mock「未来暴雨」：90min 后
    lvl = Math.max(0, lvl + 0.006 * rainFc - 0.008 * (lvl - st.base))
    if (lvl > peak) { peak = lvl; peakAt = minsLater(k * 5) }
    const half = 0.02 * (1 + 0.9 * Math.sqrt((k * 5) / 60))
    const h = (k * 5 * 60000)
    points.push({
      t: iso(new Date(now().getTime() + h)),
      level_raw: +lvl.toFixed(4),
      level: +(lvl + 0.01 * Math.exp(-k / 20)).toFixed(4), // 修正量随时间衰减
      revision: +(0.01 * Math.exp(-k / 20)).toFixed(4),
      lower: +(lvl - half).toFixed(4),
      upper: +(lvl + half).toFixed(4),
    })
  }
  return {
    forecast_id: 9000 + id * 10 + lead,
    station_id: id, station_code: st.code,
    model_id: model === 'naive' ? 1 : 2, model_type: model,
    lead_hours: lead, predict_time: iso(now()), horizon_end_time: minsLater(lead * 60),
    points, peak_level: +peak.toFixed(4), peak_time: peakAt,
    confidence_interval: { lower: points[0].lower, upper: points[points.length - 1].upper },
    degraded: false,
    decision: {
      selected_model: model,
      fusion_weights: { level: 0.45, rain: 0.33, fcst: 0.22 },
      revision_alpha: 0.6, ci_scale: 1.0, degraded: false,
      reason: '（mock）历史数据充足，选用 ' + model + ' 模型；'
        + (lead >= 6 ? `${lead}h 预见期强制启用降雨预报序列输入（D1）；` : '')
        + '新息平稳，温和修正 α=0.30',
    },
    alert: peak >= st.th[2]
      ? { alert_id: 1, level: 'orange', reason: `（mock）预测峰值 ${peak.toFixed(2)} m 超过橙色阈值 ${st.th[2]} m（预见期 ${lead}h）`, is_reference: lead >= 6, lead_minutes_advantage: 42, status: 'active' }
      : peak >= st.th[1]
        ? { alert_id: 1, level: 'yellow', reason: `（mock）预测峰值 ${peak.toFixed(2)} m 超过黄色阈值 ${st.th[1]} m（预见期 ${lead}h）`, is_reference: lead >= 6, lead_minutes_advantage: 42, status: 'active' }
        : null,
  }
}

let alertSeq = 100
export function genAlerts(): AlertItem[] {
  const rows: AlertItem[] = []
  for (const s of ST) {
    if (!s.alert) continue
    rows.push({
      alert_id: alertSeq++, station_id: s.id, station_code: s.code, station_name: s.name,
      forecast_id: 9000 + s.id * 10, level: s.alert,
      reason: `（mock）预测峰值 ${(s.cur + 0.12).toFixed(2)} m 超过阈值（预见期 3h）`,
      peak_level: +(s.cur + 0.12).toFixed(2), peak_time: minsLater(50),
      lead_minutes_advantage: 42, is_reference: false, lead_hours: 3,
      alert_time: minsAgo(10), resolve_time: null, status: 'active',
    })
    rows.push({
      alert_id: alertSeq++, station_id: s.id, station_code: s.code, station_name: s.name,
      forecast_id: 9000 + s.id * 10 + 12, level: s.alert,
      reason: `（mock）预测峰值 ${(s.cur + 0.2).toFixed(2)} m 超过阈值（预见期 12h，参考级）`,
      peak_level: +(s.cur + 0.2).toFixed(2), peak_time: minsLater(180),
      lead_minutes_advantage: 174, is_reference: true, lead_hours: 12,
      alert_time: minsAgo(8), resolve_time: null, status: 'active',
    })
  }
  return rows.sort((a, b) => (a.alert_time < b.alert_time ? 1 : -1))
}

export const mockModels: ModelItem[] = [
  { model_id: 1, model_name: '持久性模型（Naive）', version: 'v1.0', model_type: 'naive', active: false, rmse: null, mae: null, model_file: 'checkpoints/naive_v1.json', algorithm_config: {}, activatable: true },
  { model_id: 2, model_name: '降雨线性响应模型（LinearResponse）', version: 'v1.0', model_type: 'linear_response', active: true, rmse: 0.0164, mae: 0.0121, model_file: 'checkpoints/linear_v1.json', algorithm_config: { calibration: { '1': { rmse_before: 0.0166, rmse_after: 0.0164 } } }, activatable: true },
  { model_id: 3, model_name: 'LightGBM 模型（占位，未实现）', version: 'v0.0-placeholder', model_type: 'lgbm', active: false, rmse: null, mae: null, model_file: '', algorithm_config: { status: 'placeholder' }, activatable: false },
]

export const mockTools: ToolItem[] = [
  { name: 'list_stations', description: '列出全部监测点及当前水位、预警等级', parameters: {}, risk_level: 'L0' },
  { name: 'get_station_status', description: '查询单个监测点详情', parameters: { station_id: 'integer' }, risk_level: 'L0' },
  { name: 'get_level_series', description: '查询历史水位/降雨序列', parameters: { station_id: 'integer' }, risk_level: 'L0' },
  { name: 'run_forecast', description: '对某监测点发起水位预测', parameters: { station_id: 'integer', lead_hours: '1/3/6/12' }, risk_level: 'L0' },
  { name: 'get_active_alerts', description: '查询当前全部生效预警', parameters: {}, risk_level: 'L0' },
  { name: 'explain_alert', description: '解释某条预警的成因', parameters: { alert_id: 'integer' }, risk_level: 'L1' },
  { name: 'explain_forecast', description: '解释 Agent-A 的编排决策', parameters: { forecast_id: 'integer?' }, risk_level: 'L1' },
  { name: 'calibrate_params', description: '参数标定（gain/response_k），返回前后误差对比', parameters: { station_id: 'integer' }, risk_level: 'L1' },
  { name: 'query_forecast_accuracy', description: '查询近期预测误差', parameters: { station_id: 'integer' }, risk_level: 'L1' },
  { name: 'draft_alert_report', description: '生成结构化预警报告草稿', parameters: {}, risk_level: 'L1' },
  { name: 'search_similar_events', description: '检索历史相似内涝事件', parameters: { station_id: 'integer?' }, risk_level: 'L1' },
  { name: 'propose_threshold_change', description: '建议调整阈值（不直接修改）', parameters: { station_id: 'integer' }, risk_level: 'L2' },
  { name: 'update_station_threshold', description: '实际修改阈值（必须人工确认）', parameters: { station_id: 'integer', thresholds: 'object' }, risk_level: 'L2' },
]

export const mockHealth: HealthData = {
  status: 'ok', time: iso(now()),
  datasource: { type: 'simulated', status: 'STREAMING', detail: '模拟数据源运行正常（mock）' },
  model: { active: 'linear_response:v1.0', loaded: true, available: ['naive', 'linear_response'] },
  database: { status: 'ok', engine: 'sqlite', stations: 6, forecasts: 24 },
}

export const mockStats: AlertStatsGlobal = {
  today_total: 6, effective_total: 3, reference_total: 3, active_total: 3,
  by_level: { blue: 2, yellow: 2, orange: 2, red: 0 }, max_effective_level: 'orange',
}

const traces: ToolCallTrace[] = []

export function mockAgentReply(sessionId: string, message: string): AgentReply {
  const tool = message.includes('预警') ? 'get_active_alerts'
    : message.includes('预测') ? 'run_forecast'
    : message.includes('决策') || message.includes('为什么') ? 'explain_forecast'
    : message.includes('校准') ? 'calibrate_params'
    : message.includes('报告') ? 'draft_alert_report'
    : 'list_stations'
  const trace: ToolCallTrace = {
    call_id: traces.length + 1, tool_name: tool, risk_level: 'L0',
    args: { mock: true }, result_summary: `（mock EchoAgent）命中工具 ${tool}`,
    success: true, latency_ms: 12, create_time: iso(now()),
  }
  traces.unshift(trace)
  return {
    session_id: sessionId,
    answer: `【${tool}】（mock）已执行工具调用。后端 EchoAgent 为占位实现：关键词匹配选工具 → 执行 → 包装回答；接入 LLM 后此处为真实对话（EXT-POINT(AGENT)）。`,
    tool_calls: [trace],
    mode: 'echo_agent(占位)：关键词匹配选工具，无 LLM（mock 通道）',
  }
}

export function mockForecastBriefs(): ForecastBrief[] {
  const rows: ForecastBrief[] = []
  for (const s of ST) {
    rows.push({
      forecast_id: 9000 + s.id * 10 + 3, station_id: s.id, station_code: s.code,
      station_name: s.name, model_type: 'linear_response', lead_hours: 3,
      predict_time: minsAgo(2), peak_level: +(s.cur + 0.12).toFixed(2),
      peak_time: minsLater(50), rmse: null, degraded: false, remark: null,
    })
  }
  return rows.sort((a, b) => b.forecast_id - a.forecast_id)
}

export function stationDetailOf(id: number): StationDetail {
  const items = stationItems()
  const it = items.find((x) => x.station_id === id) ?? items[0]
  const alerts = genAlerts().filter((a) => a.station_id === it.station_id)
  const by: Record<string, number> = { blue: 0, yellow: 0, orange: 0, red: 0 }
  alerts.forEach((a) => { by[a.level] = (by[a.level] ?? 0) + 1 })
  return {
    ...it,
    base_level: ST.find((s) => s.id === it.station_id)!.base,
    response_k: 0.01,
    alert_stats: { total: alerts.length, by_level: by, reference: alerts.filter((a) => a.is_reference).length, active: alerts.filter((a) => a.status === 'active').length },
  }
}

export function calibrateResultOf(mid: number, sid: number): CalibrateResult {
  return {
    model_id: mid, station_id: sid, method: 'grid_search(gain × response_k)',
    params_before: { gain: 0.006, response_k: 0.01 },
    params_after: { gain: 0.006, response_k: 0.012 },
    rmse_before: 0.0166, rmse_after: 0.0164, mae_before: 0.0123, mae_after: 0.0121,
    improved_pct: 1.2,
  }
}

export function pageOf<T>(items: T[], page: number, size: number): PageData<T> {
  return { items: items.slice((page - 1) * size, page * size), total: items.length, page, page_size: size }
}

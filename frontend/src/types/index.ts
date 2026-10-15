/** 与后端契约一致的 TS 类型（形状来源：/api/v1 OpenAPI；schema.d.ts 为生成物）。 */

export interface StationThresholds {
  blue: number | null
  yellow: number | null
  orange: number | null
  red: number | null
}

export interface StationCurrent {
  level: number | null
  ts: string | null
  rain_observed: number | null
  data_age_min: number | null
}

export interface StationAlertInfo {
  rank: number
  level: string | null
  alert_id: number | null
  reason: string | null
  is_reference: boolean
  lead_minutes_advantage: number | null
}

export interface StationItem {
  station_id: number
  station_code: string
  station_name: string
  location: string | null
  kind: string | null
  enabled: boolean
  thresholds: StationThresholds
  current: StationCurrent
  alert: StationAlertInfo
}

export interface AlertStats {
  total: number
  by_level: Record<string, number>
  reference: number
  active: number
}

export interface StationDetail extends StationItem {
  base_level: number | null
  response_k: number | null
  alert_stats: AlertStats
}

export interface SeriesPoint {
  ts: string
  level: number | null
  rain_observed: number
}

export interface SeriesData {
  station_id: number
  station_code: string | null
  step_minutes: number
  thresholds: StationThresholds
  points: SeriesPoint[]
}

export interface ForecastPoint {
  t: string
  level_raw: number
  level: number
  revision: number
  lower: number
  upper: number
}

export interface DecisionInfo {
  selected_model: string
  fusion_weights: { level: number; rain: number; fcst: number }
  revision_alpha: number
  ci_scale: number
  degraded: boolean
  reason: string
}

export interface AlertBrief {
  alert_id: number
  level: string
  reason: string
  is_reference: boolean
  lead_minutes_advantage: number | null
  status: string
}

export interface ForecastData {
  forecast_id: number
  station_id: number
  station_code: string
  model_id: number | null
  model_type: string
  lead_hours: number
  predict_time: string
  horizon_end_time: string
  points: ForecastPoint[]
  peak_level: number
  peak_time: string
  confidence_interval: { lower: number; upper: number }
  degraded: boolean
  decision: DecisionInfo
  alert: AlertBrief | null
}

export interface ForecastBrief {
  forecast_id: number
  station_id: number
  station_code?: string | null
  station_name?: string | null
  model_type: string
  lead_hours: number
  predict_time: string
  peak_level: number | null
  peak_time: string | null
  rmse: number | null
  degraded: boolean
  remark: string | null
}

export interface AlertItem {
  alert_id: number
  station_id: number
  station_code: string | null
  station_name: string | null
  forecast_id: number | null
  level: string
  reason: string | null
  peak_level: number | null
  peak_time: string | null
  lead_minutes_advantage: number | null
  is_reference: boolean
  lead_hours: number | null
  alert_time: string
  resolve_time: string | null
  status: string
}

export interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface ModelItem {
  model_id: number
  model_name: string
  version: string
  model_type: string
  active: boolean
  rmse: number | null
  mae: number | null
  model_file: string
  algorithm_config: Record<string, any>
  activatable: boolean
}

export interface ToolItem {
  name: string
  description: string
  parameters: Record<string, any>
  risk_level: 'L0' | 'L1' | 'L2'
}

export interface HealthData {
  status: string
  time: string
  datasource: {
    type: string
    status: string
    detail: string
    /** 评审 R2：最新样本滞后分钟数（六站最旧口径） */
    data_age_min?: number | null
  }
  model: { active: string | null; loaded: boolean; available: string[] }
  database: { status: string; engine: string; stations: number; forecasts: number }
}

/** 评审 P2-9：预警联动发布记录（站内消息/信息屏 mock + 短信占位） */
export interface PublishRecord {
  record_id: string
  alert_id: number
  station_name: string
  level: string
  channel: string
  channel_code: 'IN_APP' | 'INFO_SCREEN' | 'SMS' | string
  status: 'sent' | 'simulated' | 'placeholder' | string
  detail: string
  publish_time: string
}

/** 评审 P1-7：模拟降雨事件 */
export interface SimEvent {
  event_id: string
  station_id: number
  intensity: string
  intensity_label?: string
  peak_mm_per_step: number
  duration_minutes: number
  start_ts: string
  end_ts: string
  injected_at: string
}

export interface CalibrateResult {
  model_id: number
  station_id: number
  method: string
  params_before: Record<string, number>
  params_after: Record<string, number>
  rmse_before: number
  rmse_after: number
  mae_before: number
  mae_after: number
  improved_pct: number
}

export interface CalibrationTask {
  calibration_id: number
  task_type: string
  status: string
  created_at: string
  note?: string
}

export interface ToolCallTrace {
  call_id: number
  tool_name: string
  risk_level: string
  args: Record<string, any>
  result_summary: string
  success: boolean
  latency_ms: number
  create_time: string
}

export interface AgentReply {
  session_id: string
  answer: string
  tool_calls: ToolCallTrace[]
  mode: string
}

export interface AgentSessionItem {
  session_id: string
  title: string | null
  create_time: string
  status: string
}

export interface AlertStatsGlobal {
  today_total: number
  effective_total: number
  reference_total: number
  active_total: number
  by_level: Record<string, number>
  max_effective_level: string | null
}

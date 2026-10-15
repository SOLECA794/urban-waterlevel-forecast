/** 业务接口封装（含 decision / calibrate-params / agent，06 §4 api/endpoints.ts）。 */
import { request } from './client'
import type {
  AgentReply, AgentSessionItem, AlertItem, AlertStatsGlobal, CalibrateResult,
  CalibrationTask, ForecastBrief, ForecastData, HealthData, ModelItem, PublishRecord,
  PageData, SeriesData, SimEvent, StationDetail, StationItem, ToolCallTrace, ToolItem,
} from '@/types'

// 类型转出口（页面/组件统一从本模块按需引入，历史用法保持兼容）
export type {
  AgentReply, AgentSessionItem, AlertItem, AlertStatsGlobal, CalibrateResult,
  CalibrationTask, ForecastBrief, ForecastData, HealthData, ModelItem, PublishRecord,
  PageData, SeriesData, SimEvent, StationDetail, StationItem, ToolCallTrace, ToolItem,
}

// --- health ---
export const getHealth = () => request<HealthData>('/health')

// --- stations ---
export const getStations = () => request<StationItem[]>('/stations')
export const getStation = (id: number) => request<StationDetail>(`/stations/${id}`)
export const createStation = (body: Partial<StationItem> & { station_name: string }) =>
  request<StationDetail>('/stations', { method: 'POST', body })
export const updateStation = (id: number, body: Record<string, any>) =>
  request<StationDetail>(`/stations/${id}`, { method: 'PUT', body })
export const deleteStation = (id: number) =>
  request<{ station_id: number; deleted: boolean; note: string | null }>(`/stations/${id}`, { method: 'DELETE' })
export const getSeries = (id: number, hours = 6, aggMinutes = 5) =>
  request<SeriesData>(`/stations/${id}/series`, { query: { hours, agg_minutes: aggMinutes } })
export const getStationCurrentAlert = (id: number) =>
  request<{ station_id: number; current_level: number | null; alert: any; thresholds: any }>(`/stations/${id}/alert`)
export const getStationAlerts = (id: number, page = 1, pageSize = 20) =>
  request<PageData<AlertItem>>(`/stations/${id}/alerts`, { query: { page, page_size: pageSize } })
export const getStationForecasts = (id: number, page = 1, pageSize = 10) =>
  request<PageData<ForecastBrief>>(`/stations/${id}/forecasts`, { query: { page, page_size: pageSize } })

// --- forecast ---
export const predict = (id: number, leadHours: number, modelId?: number) =>
  request<ForecastData>(`/stations/${id}/predict`, {
    method: 'POST',
    body: modelId ? { lead_hours: leadHours, model_id: modelId } : { lead_hours: leadHours },
  })
export const getGlobalForecasts = (page = 1, pageSize = 10) =>
  request<PageData<ForecastBrief>>('/forecasts', { query: { page, page_size: pageSize } })
export const getForecastDetail = (stationId: number, forecastId: number) =>
  request<Record<string, any>>(`/stations/${stationId}/forecasts/${forecastId}`)
export const getForecastDecision = (forecastId: number) =>
  request<Record<string, any>>(`/forecasts/${forecastId}/decision`)

// --- alerts ---
export const listAlerts = (filters: Record<string, any> = {}) =>
  request<PageData<AlertItem>>('/alerts', { query: { page: 1, page_size: 100, ...filters } })
export const getAlertStats = () => request<AlertStatsGlobal>('/alerts/stats')
export const getPublishRecords = (limit = 50) =>
  request<{ items: PublishRecord[]; total: number; note: string }>('/alerts/publish-records', { query: { limit } })

// --- simulation（P1-7 演示钥匙） ---
export const injectRainEvent = (stationId: number, intensity: string, demoKey: string) =>
  request<Record<string, any>>('/sim/events', {
    method: 'POST',
    body: { station_id: stationId, intensity, demo_key: demoKey },
  })
export const listSimEvents = () => request<SimEvent[]>('/sim/events')

// --- models ---
export const listModels = () => request<ModelItem[]>('/models')
export const activateModel = (id: number) =>
  request<Record<string, any>>(`/models/${id}/activate`, { method: 'POST' })
export const calibrateParams = (modelId: number, stationId: number) =>
  request<CalibrateResult>(`/models/${modelId}/calibrate-params`, { query: { station_id: stationId } })

// --- calibrations（重训占位） ---
export const createCalibration = (body: { station_id?: number; base_model_id?: number }) =>
  request<CalibrationTask>('/calibrations', { method: 'POST', body })
export const getCalibration = (id: number) => request<CalibrationTask>(`/calibrations/${id}`)

// --- tools / agent ---
export const listTools = () => request<ToolItem[]>('/tools')
export const invokeTool = (name: string, args: Record<string, any>, confirmToken?: string) =>
  request<Record<string, any>>(`/tools/${name}/invoke`, {
    method: 'POST',
    body: { args, confirm_token: confirmToken },
  })
export const sendAgentMessage = (sessionId: string, message: string, confirmToken?: string) =>
  request<AgentReply>(`/agent/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: { message, confirm_token: confirmToken },
  })
export const listAgentSessions = () => request<AgentSessionItem[]>('/agent/sessions')
export const listAgentToolCalls = (sessionId: string) =>
  request<ToolCallTrace[]>(`/agent/sessions/${sessionId}/tool-calls`)

// --- agent patrol（主动巡检摘要） ---
export interface PatrolItem { message_id: number; content: string; create_time: string }
export const getRecentPatrols = (limit = 10) =>
  request<PatrolItem[]>('/agent/patrol/recent', { query: { limit } })
export const runPatrol = () =>
  request<Record<string, any>>('/agent/patrol/run', { method: 'POST' })
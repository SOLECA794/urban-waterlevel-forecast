<template>
  <div class="page">
    <el-card shadow="never" class="mt0">
      <template #header><span class="h2-title">系统信息（健康检查三态，NFR-11）</span></template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="数据源">
          {{ health?.datasource.type }} · {{ health?.datasource.status }}
          <el-tag v-if="health?.datasource.status === 'STALE'" type="warning" size="small" style="margin-left: 4px">数据滞后</el-tag>
          <div class="muted">
            {{ health?.datasource.detail }}
            <template v-if="health?.datasource.data_age_min != null"> · 最新样本滞后 {{ health.datasource.data_age_min }} 分钟</template>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="模型">
          {{ health?.model.active ?? '—' }}
          <div class="muted">可用：{{ health?.model.available?.join(' / ') ?? '—' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="数据库">
          {{ health?.database.engine }} · {{ health?.database.status }}
          <div class="muted">{{ health?.database.stations }} 个点位 / {{ health?.database.forecasts }} 条预测</div>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 模拟事件注入（评审 P1-7 演示钥匙） -->
    <el-card shadow="never" class="mt">
      <template #header><span class="h2-title">模拟演练（注入极端降雨事件 · 演示钥匙）</span></template>
      <div class="inject-row">
        <el-select v-model="injectStationId" placeholder="选择监测点" style="width: 260px">
          <el-option
            v-for="s in stations" :key="s.station_id"
            :value="s.station_id"
            :label="`${s.station_code} ${s.station_name}`"
          />
        </el-select>
        <el-radio-group v-model="injectIntensity">
          <el-radio-button v-for="(v, k) in intensityPresets" :key="k" :value="k">{{ v }}</el-radio-button>
        </el-radio-group>
        <el-input v-model="demoKey" style="width: 200px" placeholder="演示钥匙">
          <template #prepend>钥匙</template>
        </el-input>
        <el-button type="danger" plain :loading="injecting" @click="doInject">注入事件</el-button>
        <el-button type="danger" :loading="demoRunning" @click="oneClickDemo">一键演示剧本</el-button>
      </div>
      <div class="muted" style="margin-top: 8px">
        注入后：观测雨强自下一采样周期计入（水位开始抬头），同一份雨真值进入降雨预报——滚动预测将提前看到上涨并产生带提前量的预警。
        默认钥匙 FANGXUN-DEMO（生产环境用环境变量覆盖；真实数据源下本功能随 EXT-POINT(DATASOURCE) 一并下线）。
      </div>
      <div v-if="injectResult" class="inject-result">
        <el-alert type="success" :closable="true" show-icon
          :title="`已注入 ${injectResult.event_id}：${injectResult.station_name} · ${injectResult.intensity_label}（峰值 ${injectResult.peak_mm_per_step}mm/5min · 持续 ${injectResult.duration_minutes} 分钟）`"
          :description="'系统已自动为该站发起预测，稍后可在详情页/预警中心查看水位抬升与预警。'" />
      </div>
      <div v-if="recentEvents.length" class="muted" style="margin-top: 8px">
        近期事件：
        <el-tag v-for="e in recentEvents" :key="e.event_id" size="small" effect="plain" style="margin-right: 6px">
          {{ e.event_id }} · 站 {{ e.station_id }} · {{ e.intensity_label ?? e.intensity }}
        </el-tag>
      </div>
    </el-card>

    <el-card shadow="never" class="mt">
      <template #header>
        <span class="h2-title">监测点管理</span>
        <el-button size="small" type="primary" style="float: right" @click="openCreate">新增监测点</el-button>
      </template>
      <el-table :data="stations" size="small">
        <el-table-column prop="station_code" label="编码" width="80" />
        <el-table-column prop="station_name" label="名称" min-width="140" />
        <el-table-column label="蓝/黄/橙/红 阈值 (m)" min-width="330">
          <template #default="{ row }">
            <div class="th-inputs">
              <el-input-number v-for="lv in ['blue', 'yellow', 'orange', 'red'] as const" :key="lv"
                v-model="row.thresholds[lv]" :step="0.1" :min="0" size="small" controls-position="right" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="saveStation(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="saveStation(row)">保存阈值</el-button>
            <el-button size="small" type="danger" plain @click="removeStation(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="muted" style="margin-top: 8px">阈值修改后下一次研判立即生效（FR-4.5，配置真实生效的可验证点）</div>
    </el-card>

    <el-card shadow="never" class="mt">
      <template #header><span class="h2-title">模型管理（S7 模型可插拔 + 参数校准）</span></template>
      <el-table :data="models" size="small">
        <el-table-column prop="model_name" label="模型" min-width="220" />
        <el-table-column prop="model_type" label="类型" width="140" />
        <el-table-column prop="version" label="版本" width="150" />
        <el-table-column label="RMSE" width="90">
          <template #default="{ row }">{{ row.rmse?.toFixed(4) ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="在用" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.active" type="success" size="small">在用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="270">
          <template #default="{ row }">
            <el-button size="small" :disabled="!row.activatable || row.active" @click="activate(row)">激活</el-button>
            <el-button size="small" :disabled="row.model_type !== 'linear_response'" @click="calibrate(row)">参数校准</el-button>
            <el-button size="small" disabled>重训（建设中）</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="muted" style="margin-top: 8px">
        重训为占位功能（/api/v1/calibrations 返回 pending）；模型级在线学习明确不做——预测级协同修正已承担在线适应（05 §7.5 取舍）。
      </div>
    </el-card>

    <el-card shadow="never" class="mt">
      <template #header><span class="h2-title">数据源配置</span></template>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="类型">simulated（真实数据源为 EXT-POINT(DATASOURCE) 占位）</el-descriptions-item>
        <el-descriptions-item label="采集间隔">5 分钟（config/default.yaml）</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 校准结果对话框 -->
    <el-dialog v-model="calibVisible" title="参数校准结果（前后误差对比）" width="560">
      <el-descriptions v-if="calibResult" :column="2" border size="small">
        <el-descriptions-item label="方法">{{ calibResult.method }}</el-descriptions-item>
        <el-descriptions-item label="提升幅度">{{ calibResult.improved_pct }}%</el-descriptions-item>
        <el-descriptions-item label="RMSE（前 → 后）">
          {{ calibResult.rmse_before }} → <b>{{ calibResult.rmse_after }}</b>
        </el-descriptions-item>
        <el-descriptions-item label="MAE（前 → 后）">
          {{ calibResult.mae_before }} → <b>{{ calibResult.mae_after }}</b>
        </el-descriptions-item>
        <el-descriptions-item label="标定参数" :span="2">
          gain: {{ calibResult.params_after.gain }} · response_k: {{ calibResult.params_after.response_k }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 新增点位对话框 -->
    <el-dialog v-model="createVisible" title="新增监测点" width="480">
      <el-form label-width="90px">
        <el-form-item label="名称"><el-input v-model="createForm.station_name" /></el-form-item>
        <el-form-item label="位置"><el-input v-model="createForm.location" /></el-form-item>
        <el-form-item label="黄色阈值"><el-input-number v-model="createForm.yellow" :step="0.1" /></el-form-item>
        <el-form-item label="橙色阈值"><el-input-number v-model="createForm.orange" :step="0.1" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import {
  activateModel, calibrateParams, createStation, deleteStation, getHealth,
  injectRainEvent, listModels, listSimEvents, updateStation,
  type CalibrateResult, type ModelItem, type SimEvent, type StationItem,
} from '@/api/endpoints'
import type { HealthData } from '@/types'
import { usePolling } from '@/composables/usePolling'
import { useRouter } from 'vue-router'

const health = ref<HealthData | null>(null)
const stations = ref<StationItem[]>([])
const models = ref<ModelItem[]>([])
const calibVisible = ref(false)
const calibResult = ref<CalibrateResult | null>(null)
const createVisible = ref(false)
const createForm = ref({ station_name: '', location: '', yellow: 2.0, orange: 2.4 })

// --- 模拟事件注入（P1-7 演示钥匙） ---
const intensityPresets: Record<string, string> = {
  light: '小雨', moderate: '中雨', heavy: '大雨', extreme: '极端暴雨',
}
const injectStationId = ref<number>(1)
const injectIntensity = ref('extreme')
const demoKey = ref('FANGXUN-DEMO')
const injecting = ref(false)
const injectResult = ref<Record<string, any> | null>(null)
const recentEvents = ref<SimEvent[]>([])

async function oneClickDemo() {
  demoRunning.value = true
  try {
    await injectRainEvent(injectStationId.value || 1, 'extreme', demoKey.value || 'FANGXUN-DEMO')
    ElMessage.success('已注入极端暴雨，跳转首页等待预警弹出…')
    setTimeout(() => router.push('/'), 800)
  } catch (e: any) {
    ElMessage.error('注入失败：' + (e?.message || e))
  } finally {
    demoRunning.value = false
  }
}

async function doInject() {
  if (!injectStationId.value) {
    ElMessage.warning('请先选择监测点')
    return
  }
  injecting.value = true
  try {
    injectResult.value = await injectRainEvent(injectStationId.value, injectIntensity.value, demoKey.value)
    ElMessage.success(`事件已注入：${injectResult.value.event_id}，系统正在为该站发起预测`)
    recentEvents.value = await listSimEvents()
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message || '注入失败')
  } finally {
    injecting.value = false
  }
}

async function refresh() {
  const { getStations } = await import('@/api/endpoints')
  stations.value = await getStations()
  health.value = await getHealth()
  if (!injectStationId.value && stations.value.length) {
    injectStationId.value = stations.value[0].station_id
  }
}

async function loadModels() {
  models.value = await listModels()
}

async function saveStation(row: StationItem) {
  await updateStation(row.station_id, { ...row.thresholds, enabled: row.enabled })
  ElMessage.success(`已保存：${row.station_name}（下一次研判按新阈值执行）`)
}

async function removeStation(row: StationItem) {
  const out = await deleteStation(row.station_id)
  ElMessage.success(out.note ?? `已删除：${row.station_name}`)
  await refresh()
}

async function activate(row: ModelItem) {
  await activateModel(row.model_id)
  ElMessage.success(`已切换到 ${row.model_name}：下一次预测生效（业务代码未改动，S7）`)
  await loadModels()
}

async function calibrate(row: ModelItem) {
  const stationId = stations.value[0]?.station_id ?? 1
  const res = await calibrateParams(row.model_id, stationId)
  calibResult.value = res
  calibVisible.value = true
  await loadModels()
}

function openCreate() {
  createVisible.value = true
}

async function doCreate() {
  await createStation({
    station_name: createForm.value.station_name || '未命名点位',
    location: createForm.value.location,
    threshold_yellow: createForm.value.yellow,
    threshold_orange: createForm.value.orange,
  } as any)
  createVisible.value = false
  ElMessage.success('监测点已创建（生成模拟序列后即可预测）')
  await refresh()
}

usePolling(refresh, 60_000)
onMounted(() => {
  loadModels()
  listSimEvents().then((evs) => (recentEvents.value = evs)).catch(() => {})
})
</script>

<style scoped>
.mt { margin-top: 16px; }
.mt0 { margin-top: 0; }
.th-inputs { display: flex; gap: 4px; }
.th-inputs .el-input-number { width: 74px; }
.inject-row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.inject-result { margin-top: 10px; }
</style>

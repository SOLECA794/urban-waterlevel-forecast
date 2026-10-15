<template>
  <div class="page">
    <el-tabs v-model="tab" class="alert-tabs">
      <!-- 标签页一：预警记录（表格 / 时间线双视图） -->
      <el-tab-pane label="预警记录" name="records">
        <div class="filters">
          <el-select v-model="level" placeholder="全部等级" clearable style="width: 140px">
            <el-option value="blue" label="蓝色" />
            <el-option value="yellow" label="黄色" />
            <el-option value="orange" label="橙色" />
            <el-option value="red" label="红色" />
          </el-select>
          <el-select v-model="status" placeholder="全部状态" clearable style="width: 140px">
            <el-option value="active" label="生效中" />
            <el-option value="resolved" label="已解除" />
          </el-select>
          <el-select v-model="isReference" placeholder="有效 + 参考级" clearable style="width: 160px">
            <el-option value="false" label="仅有效预警" />
            <el-option value="true" label="仅参考级（6h/12h）" />
          </el-select>
          <el-button type="primary" @click="load">查询</el-button>
          <!-- 视图切换（精修 §3.3.2：置于筛选器右侧） -->
          <el-radio-group v-model="view" size="small">
            <el-radio-button value="table">表格</el-radio-button>
            <el-radio-button value="timeline">时间线</el-radio-button>
          </el-radio-group>
          <span class="muted">参考级预警以浅色显示、不计入有效预警统计（长预见期降权）</span>
        </div>

        <el-card shadow="never">
          <!-- 表格视图：v-loading 修复首屏「暂无数据」闪空（评审 P2-10 / 精修 §3.3.2） -->
          <div v-if="view === 'table'" v-loading="store.loading" element-loading-text="加载预警记录…" class="table-wrap">
            <AlertList :alerts="store.alerts" @open="(r) => $router.push(`/station/${r.station_id}`)" />
          </div>
          <!-- 时间线视图（精修 §3.3.1） -->
          <AlertTimeline v-else :alerts="store.alerts" :loading="store.loading" />
          <div class="muted" style="margin-top: 10px">共 {{ store.alerts.length }} 条记录（近 100 条）</div>
        </el-card>
      </el-tab-pane>

      <!-- 标签页二：发布记录（评审 P2-9 联动发布踪迹） -->
      <el-tab-pane label="发布记录" name="publish">
        <el-card shadow="never">
          <template #header>
            <span>预警联动发布记录</span>
            <span class="muted" style="margin-left: 8px">{{ publishNote }}</span>
          </template>
          <el-table
            v-loading="publishLoading"
            element-loading-text="加载发布记录…"
            :data="publishRecords"
            size="small"
            empty-text="暂无发布记录（预警触发后自动生成）"
            :row-class-name="publishRowClass"
          >
            <el-table-column prop="record_id" label="#" width="90" />
            <el-table-column prop="alert_id" label="预警 #" width="80" />
            <el-table-column prop="station_name" label="监测点" min-width="140" />
            <el-table-column label="等级" width="90">
              <template #default="{ row }">
                <AlertBadge :level="row.level" />
              </template>
            </el-table-column>
            <el-table-column prop="channel" label="发布渠道" width="100">
              <template #default="{ row }">
                {{ row.channel }}
                <el-tooltip v-if="row.channel_code === 'SMS'" content="真实渠道占位：短信网关未接入（EXT-POINT(INTEGRATION)）">
                  <el-tag size="small" type="info" effect="plain" style="margin-left: 4px">占位</el-tag>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag v-if="row.status === 'sent'" type="success" size="small" effect="plain">已发送</el-tag>
                <el-tag v-else-if="row.status === 'simulated'" type="primary" size="small" effect="plain">模拟下发</el-tag>
                <el-tag v-else type="info" size="small" effect="plain">留白占位</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="详情" min-width="260" show-overflow-tooltip />
            <el-table-column label="发布时间" width="170">
              <template #default="{ row }">{{ fmt(row.publish_time) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getPublishRecords, type PublishRecord } from '@/api/endpoints'
import AlertBadge from '@/components/AlertBadge.vue'
import AlertList from '@/components/AlertList.vue'
import AlertTimeline from '@/components/AlertTimeline.vue'
import { usePolling } from '@/composables/usePolling'
import { useAlertStore } from '@/stores/useAlertStore'

const store = useAlertStore()
const router = useRouter()
const level = ref('')
const status = ref('')
const isReference = ref('')
const view = ref<'table' | 'timeline'>('table')
const tab = ref('records')

const publishRecords = ref<PublishRecord[]>([])
const publishLoading = ref(false)
const publishNote = ref('')

async function load() {
  await store.refresh({
    level: level.value || undefined,
    status: status.value || undefined,
    is_reference: isReference.value || undefined,
  })
}

async function loadPublish() {
  publishLoading.value = true
  try {
    const res = await getPublishRecords(50)
    publishRecords.value = res.items
    publishNote.value = res.note
  } catch { /* 降级已提示 */ } finally {
    publishLoading.value = false
  }
}

/** 短信占位行灰显（EXT-POINT(INTEGRATION) 视觉区分） */
function publishRowClass({ row }: { row: PublishRecord }) {
  return row.status === 'placeholder' ? 'publish-placeholder-row' : ''
}

function fmt(ts: string | null) {
  return ts ? ts.replace('T', ' ').slice(0, 19) : '—'
}

usePolling(load, 30_000)
onMounted(() => {
  load()
  loadPublish()
})
</script>

<style scoped>
.filters { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.table-wrap { min-height: 120px; }
</style>

<style>
/* 短信占位行灰显（非 scoped，作用于 el-table 内部行） */
.el-table .publish-placeholder-row { color: #a3aeb7; background: #fafbfc; }
.el-table .publish-placeholder-row td { color: inherit; }
</style>

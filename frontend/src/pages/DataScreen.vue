<template>
  <div class="screen">
    <header class="hdr">
      <div class="title">城市内涝水位预测预警 · 指挥大屏</div>
      <div class="clock">{{ now }}</div>
    </header>

    <section class="kpis">
      <div class="kpi">
        <div class="num">{{ stats.stations_online ?? 6 }}</div>
        <div class="lbl">监测点在线</div>
      </div>
      <div class="kpi" :class="{ alert: stats.active_alerts > 0 }">
        <div class="num">{{ stats.active_alerts ?? 0 }}</div>
        <div class="lbl">生效预警</div>
      </div>
      <div class="kpi">
        <div class="num">{{ stats.reference_alerts ?? 0 }}</div>
        <div class="lbl">参考级预警</div>
      </div>
      <div class="kpi">
        <div class="num">{{ critical }}</div>
        <div class="lbl">重点关注</div>
      </div>
    </section>

    <section class="body">
      <div class="col stations">
        <h3>监测点实时水位</h3>
        <div v-for="s in stations" :key="s.station_id" class="row">
          <div class="sname">{{ s.station_name }}</div>
          <div class="bar-wrap">
            <div class="bar" :style="barStyle(s)"></div>
          </div>
          <div class="sval">{{ s.current?.level?.toFixed(2) ?? '--' }} m</div>
          <div class="lv" :class="levelClass(s.alert?.level)">{{ levelText(s.alert?.level) }}</div>
        </div>
      </div>

      <div class="col patrol">
        <h3>Agent 值班播报</h3>
        <div v-if="!patrols.length" class="empty">等待 Agent 首次巡检…</div>
        <div v-for="p in patrols" :key="p.message_id" class="patrol-item">
          <div class="ptime">{{ fmt(p.create_time) }}</div>
          <div class="ptext" v-html="p.content.replace(/</g,'&lt;').replace(/\n/g,'<br/>')"></div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getRecentPatrols, getStations, type PatrolItem, type StationItem } from '@/api/endpoints'

const stations = ref<StationItem[]>([])
const patrols = ref<PatrolItem[]>([])
const stats = ref<any>({ stations_online: 6, active_alerts: 0, reference_alerts: 0 })
const now = ref('')

function tick() {
  now.value = new Date().toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  tick()
  stations.value = await getStations()
  stats.value.stations_online = stations.value.filter(s => s.enabled !== false).length
  stats.value.active_alerts = stations.value.filter(s => s.alert?.rank > 0 && !s.alert?.is_reference).length
  stats.value.reference_alerts = stations.value.filter(s => s.alert?.is_reference).length
  patrols.value = await getRecentPatrols(5)
}

const critical = computed(() => {
  const c = [...stations.value].sort((a, b) => (b.alert?.rank ?? 0) - (a.alert?.rank ?? 0))[0]
  if (!c || !c.alert?.level) return '平稳'
  return c.station_name.slice(0, 6)
})

function barStyle(s: StationItem) {
  const v = s.current?.level ?? 0
  const pct = Math.min(100, Math.max(5, v / 3 * 100))
  const color = s.alert?.rank > 0 ? '#f44336' : s.alert?.rank > 0 ? '#ff9800' : '#2196f3'
  return { width: pct + '%', background: color }
}
function levelClass(lv?: string) { return lv ? 'lv-' + lv : '' }
function levelText(lv?: string) {
  return { blue: '蓝', yellow: '黄', orange: '橙', red: '红' }[lv ?? ''] ?? '正常'
}
function fmt(ts: string) { return ts ? ts.replace('T', ' ').slice(5, 16) : '' }

onMounted(async () => { await load(); setInterval(load, 30000) })
</script>

<style scoped>
.screen {
  min-height: 100vh; background: #0a1929; color: #e6f1ff; padding: 20px 28px;
  font-family: 'Microsoft YaHei', sans-serif;
}
.hdr { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.title { font-size: 26px; font-weight: 600; letter-spacing: 2px; color: #fff; }
.clock { font-size: 16px; color: #8fb8e0; }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.kpi {
  background: rgba(30, 111, 168, 0.15); border: 1px solid rgba(30, 111, 168, 0.4);
  border-radius: 8px; padding: 18px; text-align: center;
}
.kpi.alert { background: rgba(244, 67, 54, 0.2); border-color: rgba(244, 67, 54, 0.6); }
.kpi .num { font-size: 42px; font-weight: 700; color: #4fc3f7; line-height: 1.1; }
.kpi.alert .num { color: #ff5252; }
.kpi .lbl { font-size: 13px; color: #8fb8e0; margin-top: 6px; }
.body { display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; }
.col { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 16px; }
.col h3 { margin: 0 0 14px; font-size: 15px; color: #4fc3f7; font-weight: 600; }
.row { display: grid; grid-template-columns: 130px 1fr 80px 40px; gap: 10px; align-items: center; padding: 8px 0; border-bottom: 1px dashed rgba(255,255,255,0.06); }
.sname { font-size: 13px; color: #cfd8e3; }
.bar-wrap { height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; }
.bar { height: 100%; border-radius: 4px; transition: width 0.6s; }
.sval { font-size: 13px; font-family: monospace; color: #fff; text-align: right; }
.lv { font-size: 11px; text-align: center; }
.lv-blue { color: #2196f3; } .lv-yellow { color: #ffc107; } .lv-orange { color: #ff9800; } .lv-red { color: #f44336; }
.patrol-item { padding: 10px 0; border-bottom: 1px dashed rgba(255,255,255,0.08); }
.ptime { font-size: 11px; color: #8fb8e0; margin-bottom: 4px; }
.ptext { font-size: 13px; line-height: 1.7; color: #e6f1ff; }
.empty { color: #666; font-size: 13px; padding: 20px 0; }
</style>

<template>
  <el-card shadow="never" class="map-card">
    <template #header>
      <span class="h2-title">站点示意图（一张图）</span>
      <span class="muted" style="margin-left: 8px">抽象平面 · 按预警等级着色 · 点击圆标进入详情</span>
      <span class="legend">
        <i class="dot" style="background: var(--status-ok)"></i>正常
        <i class="dot" style="background: var(--alert-blue)"></i>蓝
        <i class="dot" style="background: var(--alert-yellow)"></i>黄
        <i class="dot" style="background: var(--alert-orange)"></i>橙
        <i class="dot" style="background: var(--alert-red)"></i>红
      </span>
    </template>

    <svg :viewBox="`0 0 ${W} ${H}`" class="plan">
      <!-- 城市底图：街区 -->
      <g opacity="0.5">
        <rect v-for="b in blocks" :key="b.x + '-' + b.y" :x="b.x" :y="b.y" :width="b.w" :height="b.h"
          rx="3" fill="#f0f3f6" stroke="var(--line)" />
      </g>

      <!-- 城东河（河道带） -->
      <path :d="riverPath" fill="none" stroke="#bcdcf0" stroke-width="26" stroke-linecap="round" />
      <path :d="riverPath" fill="none" stroke="#9cccec" stroke-width="18" stroke-linecap="round" opacity="0.7" />
      <text :x="880" :y="58" class="geo-label">城东河</text>

      <!-- 主干路网 -->
      <path d="M 20 130 H 980" stroke="#dfe6ec" stroke-width="14" />
      <path d="M 300 20 V 300" stroke="#dfe6ec" stroke-width="14" />
      <path d="M 620 20 V 300" stroke="#dfe6ec" stroke-width="14" />
      <text x="34" y="122" class="geo-label">站前路</text>
      <text x="308" y="34" class="geo-label">建设路</text>

      <!-- 铁路（下穿隧道位置） -->
      <path d="M 380 250 L 700 190" stroke="#c9b99a" stroke-width="6" stroke-dasharray="14 6" />
      <text x="560" y="252" class="geo-label">铁路线</text>

      <!-- 泵站水体 -->
      <rect x="656" y="150" width="26" height="26" rx="4" fill="#cfe7f5" stroke="#9cccec" />

      <!-- 监测点（按预警等级着色；红色脉动） -->
      <g v-for="st in placed" :key="st.station_id" class="st" @click="$router.push(`/station/${st.station_id}`)">
        <title>{{ st.station_name }} · {{ levelText(st.alert.level) }}</title>
        <circle v-if="st.alert.level === 'red'" class="ring" :cx="st._x" :cy="st._y" r="10" />
        <circle :cx="st._x" :cy="st._y" r="12" :fill="levelColor(st.alert.level)" stroke="#fff" stroke-width="2" />
        <text :x="st._x" :y="st._y + 4" class="st-kind">{{ kindChar(st.kind) }}</text>
        <text :x="st._x" :y="st._y + 30" class="st-name">{{ st.station_code }} {{ st.station_name }}</text>
      </g>
    </svg>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StationItem } from '@/types'

const props = defineProps<{ stations: StationItem[] }>()

const W = 1000
const H = 320

/** 已知 6 站的示意坐标（与 stations.yaml 场景对应）；未收录站点自动排布在底部一行 */
const KNOWN_POS: Record<string, { x: number; y: number }> = {
  S001: { x: 220, y: 130 },  // 站前路低洼段（主路南侧低洼）
  S002: { x: 520, y: 214 },  // 建设路下穿隧道（铁路线下方）
  S003: { x: 800, y: 84 },   // 城东河河道断面（河道上）
  S004: { x: 120, y: 214 },  // 老城十字街
  S005: { x: 900, y: 214 },  // 新区主干道
  S006: { x: 669, y: 130 },  // 工业园区雨水泵站（河道旁）
}

const blocks = [
  { x: 40, y: 30, w: 110, h: 70 }, { x: 170, y: 30, w: 100, h: 70 },
  { x: 330, y: 30, w: 110, h: 70 }, { x: 470, y: 30, w: 120, h: 70 },
  { x: 640, y: 30, w: 90, h: 40 },
  { x: 40, y: 160, w: 130, h: 110 }, { x: 190, y: 160, w: 100, h: 110 },
  { x: 330, y: 160, w: 90, h: 60 }, { x: 330, y: 240, w: 90, h: 40 },
  { x: 660, y: 190, w: 100, h: 90 }, { x: 790, y: 130, w: 90, h: 60 },
  { x: 790, y: 220, w: 170, h: 70 },
]

const riverPath = 'M 690 30 C 760 60, 820 70, 890 60 S 980 80, 985 96'

const placed = computed(() => {
  let autoX = 60
  return props.stations.map((st) => {
    const known = KNOWN_POS[st.station_code]
    if (known) return { ...st, _x: known.x, _y: known.y }
    const p = { x: autoX, y: 296 }
    autoX += 110
    return { ...st, _x: p.x, _y: p.y }
  })
})

function levelColor(level: string | null) {
  switch (level) {
    case 'red': return 'var(--alert-red)'
    case 'orange': return 'var(--alert-orange)'
    case 'yellow': return 'var(--alert-yellow)'
    case 'blue': return 'var(--alert-blue)'
    default: return 'var(--status-ok)'
  }
}

function levelText(level: string | null) {
  return level ? { blue: '蓝色', yellow: '黄色', orange: '橙色', red: '红色' }[level] ?? level : '正常'
}

function kindChar(kind: string | null) {
  switch (kind) {
    case 'low-lying': return '洼'
    case 'river': return '河'
    case 'road': return '路'
    case 'pump': return '泵'
    default: return '站'
  }
}
</script>

<style scoped>
.map-card { margin-bottom: 16px; }
.legend { float: right; font-size: 12px; color: var(--text-muted); }
.legend .dot {
  display: inline-block; width: 9px; height: 9px; border-radius: 50%;
  margin: 0 4px 0 10px; vertical-align: middle;
}
.plan { width: 100%; height: auto; display: block; }
.geo-label { font-size: 11px; fill: var(--text-muted); }
.st { cursor: pointer; }
.st:hover circle { filter: brightness(1.08); }
.st-kind { font-size: 11px; fill: #fff; text-anchor: middle; font-weight: 600; pointer-events: none; }
.st-name { font-size: 12px; fill: var(--text-sub); text-anchor: middle; }
.ring {
  fill: none;
  stroke: var(--alert-red);
  stroke-width: 2;
  animation: ring-pulse 1.6s ease-out infinite;
}
@keyframes ring-pulse {
  0% { opacity: 0.9; stroke-width: 2; r: 12; }
  100% { opacity: 0; stroke-width: 1; r: 26; }
}
</style>

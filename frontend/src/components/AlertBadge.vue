<template>
  <span class="lv-tag" :class="[level, { ref: isReference }]" :title="tooltip">
    {{ label }}{{ isReference ? ' · 参考' : '' }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    level?: string | null
    isReference?: boolean
    tooltip?: string
  }>(),
  { level: null, isReference: false, tooltip: '' },
)

const label = computed(() => {
  switch (props.level) {
    case 'blue': return '蓝色'
    case 'yellow': return '黄色'
    case 'orange': return '橙色'
    case 'red': return '红色'
    default: return '正常'
  }
})
</script>

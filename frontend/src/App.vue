<template>
  <AlertNotifier />
  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<script setup lang="ts">
import AlertNotifier from '@/components/AlertNotifier.vue'
</script>